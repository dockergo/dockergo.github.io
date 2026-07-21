# TensorFlow 核心原理 · 支撑能力域 · 设备与后端

> **定位**：把图节点分配到物理设备的能力域。`Placer` 结合 colocation 约束与 soft placement 给每个节点定 CPU/GPU/TPU；图按设备切分、跨设备边自动插 Send/Recv 拷贝张量。核实基准：官方源码（`tensorflow/core/common_runtime/placer.cc:223`、`tensorflow/core/common_runtime/colocation_graph.cc:660`、`tensorflow/core/graph/graph_partition.cc:185`）。

## 一、Placer：给每个节点定设备

![放置与colocation](TensorFlow原理_设备后端_01放置与colocation.svg)

`Placer::Run`（`placer.cc:223`）分四步：

① **收集约束**——用户显式 `with tf.device(...)` 加上各节点 kernel 支持的设备集（`SupportedDeviceTypesForNode`，见 `placer.cc:177`）；
② **ColocationGraph**（`tensorflow/core/common_runtime/colocation_graph.h:225` `Initialize`）用**并查集**（`Member::FindRoot`，`colocation_graph.cc:387`，带路径压缩）把"必须同设备"的节点归并成组——`ColocateAllNodes`（`colocation_graph.cc:660`）依据 `_class`/colocation 属性调用 `ColocateNodes`（`colocation_graph.cc:729`）把两组的根合并，典型如 Variable 与其更新 op、Send/Recv 对端，保证同组落同一设备、避免无谓跨设备拷贝；
③ **按组求可行设备并选一个**——`LimitToPossibleDevices`（`colocation_graph.cc:561`）对每组求各成员支持设备的交集，`GetDevicesForNode`（`colocation_graph.h:255`）产出候选，通常优先 GPU（若该 op 有 GPU kernel）；
④ **soft placement**——`allow_soft_placement=True` 时（参数流经 `colocation_graph.cc:396` 等），指定了不存在 kernel 的设备不报错、自动**回退 CPU**；放置结果经 `LogDeviceAssignment`（`placer.cc:164`）在开 `log_device_placement` 时打印。

并查集的意义在于：colocation 首先是**正确性约束**（有状态资源与其读写必须同设备），其次才顺带减少跨设备拷贝。

## 二、跨设备：自动插 Send/Recv

![图切分与SendRecv](TensorFlow原理_设备后端_02图切分与SendRecv.svg)

放置完成后图按设备切分（graph partition），跨设备的边被替换成 **Send/Recv 节点对**（见图）：`AddSend`（`graph_partition.cc:185`）在源设备侧插发送节点、`AddRecv`（`:243`）在目标侧插接收节点，运行时由它们做 H2D/D2H 拷贝与跨设备同步。若源目标同设备但需跨内存空间（如 host↔device pinned），`NeedSameDeviceSendRecv`（`:127`）判定并落成 `_HostSend`/`_HostRecv`（`:230`、`:289`）而非普通 `_Send`/`_Recv`。因此"减少跨设备来回"就是让强关联算子 colocate 同设备。

后端实现：CPU 用 Eigen/oneDNN 向量化，GPU 用 CUDA kernel + cuBLAS/cuDNN，TPU 经 XLA 编译——同一 op 在各设备各注册一份 kernel（见「算子与 kernel」）。

## 深化 · 放置关键机制

| 机制 | 说明 | 源码锚点 |
|---|---|---|
| Placer::Run | 放置主流程（四步） | `placer.cc:223` |
| 并查集归组 | `Member::FindRoot` 路径压缩 | `colocation_graph.cc:387` |
| ColocateAllNodes | 依 colocation 属性合并组 | `colocation_graph.cc:660`、`:729` |
| 可行设备交集 | 每组成员支持设备取交 | `colocation_graph.cc:561`、`.h:255` |
| soft placement | 无 kernel 自动回退 CPU | `colocation_graph.cc:396` |
| 设备分配日志 | log_device_placement 打印 | `placer.cc:164` |
| Send/Recv | 跨设备拷贝节点对 | `graph_partition.cc:185`、`:243` |
| Host Send/Recv | 同设备跨内存空间 | `graph_partition.cc:127`、`:230`、`:289` |

## 拓展 · 设备相关配置

| 配置 | 作用 |
|---|---|
| with tf.device('/GPU:0') | 显式指定节点/张量设备 |
| allow_soft_placement | 无对应 kernel 时回退而非报错 |
| log_device_placement | 打印每个节点最终落的设备（调试） |
| memory growth | GPU 显存按需增长而非一次占满 |
| CUDA_VISIBLE_DEVICES | 限定进程可见的 GPU |

## 调优要点

- **让 Variable 与其读写 op colocate**：默认 colocation 会通过并查集处理（`ColocateAllNodes`），自定义放置时别拆散。
- **开 `log_device_placement` 排查回退**：发现关键 op 落 CPU（缺 GPU kernel），针对性换算子或补 kernel。
- **减少跨设备张量传输**：Send/Recv 有拷贝与同步开销，尽量把一条计算链放同设备。
- **多 GPU 用 distribute.Strategy 而非手工放置**：Strategy 帮你镜像变量、做 all-reduce（见「分布式训练」）。

## 常见误区

- **"指定 GPU 就一定在 GPU 跑"**：若该 op 无 GPU kernel 且开了 soft placement，会回退 CPU。
- **"跨设备访问是免费的"**：跨设备边有 Send/Recv 拷贝成本；同设备跨内存空间也要 Host Send/Recv。
- **"colocation 是性能优化"**：更是正确性/一致性约束（Variable 与其更新必须同设备），并查集强制之。
- **"TF 一启动占满显存不合理"**：默认预占减碎片；要按需增长需显式开 memory growth。

## 一句话总纲

**设备与后端的核心是 Placer：按 kernel 可用设备加用户约束、用 ColocationGraph 并查集归并"必须同设备"的组、对每组取支持设备交集优先 GPU、soft placement 缺 kernel 回退 CPU；图按设备切分、跨设备边插 Send/Recv（同设备跨内存空间用 Host Send/Recv）拷贝——同一 op 在各设备各有 kernel 真正落地计算。**
