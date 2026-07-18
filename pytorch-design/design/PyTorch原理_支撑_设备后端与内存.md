# PyTorch 核心原理 · 支撑能力域 · 设备后端与内存

> **定位**：表示层底座。真正的数值计算（CPU/CUDA kernel）+ 显存管理（CUDA 缓存分配器）+ 异步执行（stream）。被所有算子的落地执行依赖。核实基准：官方源码 `pytorch/src`（`c10/cuda/CUDACachingAllocator.cpp`）。

## 一、后端 kernel、stream 与缓存分配器

![后端与分配器](PyTorch原理_设备内存_01后端与分配器.svg)

**后端 kernel**：Dispatcher 按 Backend key 落到这里——CPU（向量化+OpenMP，MKL/oneDNN）、CUDA（GPU 并行，cuBLAS/cuDNN，自写 kernel），大算子多委托厂商库，扩展新设备=注册新 key 的 kernel。**CUDA stream 异步**：CPU 提交 kernel 到 stream 队列即返回、GPU 按序异步执行、CPU 不阻塞——CPU 与 GPU 重叠、多 kernel 流水，吞吐高；后果是计时须 `synchronize`、报错可能延迟到下次同步。**CUDA 缓存分配器**（为什么不直接 cudaMalloc）：cudaMalloc/Free 慢且同步 device，训练每步海量临时张量直接调会卡死——① 池化复用（向 CUDA 大块申请切小块给张量，释放还池不还 CUDA，下次秒取）② 分桶+流感知（按大小分桶、避免复用未完成块）③ 后果（nvidia-smi 显存=池占用含空闲块、OOM 可能是碎片、`empty_cache` 还池、`PYTORCH_CUDA_ALLOC_CONF` 调策略）。

---

## 拓展 · 设备内存组件

| 组件 | 职责 | 锚点 |
|---|---|---|
| CPU/CUDA kernel | 后端数值计算 | `aten/src/ATen/native/{cpu,cuda}` |
| CUDACachingAllocator | 显存池化 | `c10/cuda/CUDACachingAllocator.cpp` |
| CUDA stream | 异步执行队列 | `c10/cuda/CUDAStream.h` |
| DataPtr / Allocator | 内存句柄与分配器 | `c10/core/Allocator.h` |

---

## 调优要点（关键开关）

- 计时/基准务必 `torch.cuda.synchronize`（异步）。
- OOM 先看碎片：`empty_cache`、`PYTORCH_CUDA_ALLOC_CONF=expandable_segments`。
- 混合精度/更小 dtype 省显存；梯度检查点换显存。
- `non_blocking=True` + pin_memory 重叠 H2D 传输。

---

## 常见误区与工程要点

- **nvidia-smi 显存高 = 泄漏**：多是缓存池占用（含空闲块），非泄漏。
- **同步测时间才准**：不 synchronize 测的是 launch 时间。
- **频繁 empty_cache**：会打断池化、反而变慢；仅在必要时用。
- **cudaMalloc 心智**：PyTorch 不每次调 cudaMalloc，走缓存池。

---

## 一句话总纲

**设备后端与内存是算子的落地：Dispatcher 按 Backend key 分发到 CPU（MKL/oneDNN）或 CUDA（cuBLAS/cuDNN）kernel，CUDA 用 stream 异步执行（CPU 提交即返回、计时须 synchronize），显存由 CUDACachingAllocator 池化复用（避免慢且同步的 cudaMalloc，nvidia-smi 显存=池占用、OOM 常因碎片）——这套机制让 GPU 训练既快又不被显存分配拖垮。**
