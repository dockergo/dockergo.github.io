# Kubernetes 核心原理 · 支撑能力域 · 存储（CSI / PV / PVC）

> **定位**：把"持久存储"也做成声明式期望态。用户用 **PVC**（PersistentVolumeClaim）声明"我要一块 10Gi 的存储"，控制器负责找到或动态创建一块 **PV**（PersistentVolume）与之绑定；真正的挂载经 **CSI**（Container Storage Interface）由存储驱动完成。存储的申领与供给同样由 reconcile 循环驱动。核实基准：`pkg/controller/volume/persistentvolume/pv_controller.go`。

## 一、PVC → PV 绑定与动态供给

![PVC到CSI](Kubernetes原理_支撑_存储_01PVC到CSI.svg)

**图示**：用户只写 PVC（容量、访问模式、StorageClass）声明"要什么存储"；**PV 控制器**跑经典 reconcile——已绑则维护，未绑则先在有序索引里找最小可满足的 PV，找不到且指定了 StorageClass 就触发**动态供给**（调 provisioner 在后端真实建卷）。绑定写的是 **PV.claimRef ↔ PVC.volumeName 双向引用**。**关键不变量**：卷从"供给→绑定→挂载"三段推进——① Provision 建卷、② Attach 挂到节点、③ kubelet 经 CSI driver Mount 进容器；删除必须逆序（Unmount→Detach→按 `reclaimPolicy` 回收/保留），顺序错会泄漏卷或损坏数据。整条存储生命周期都被纳入声明式 + reconcile 框架。

| reconcile 落点 | 符号 | 位置 |
|---|---|---|
| 入口分流 | `syncClaim` | pv_controller.go:237 |
| 未绑处理 | `syncUnboundClaim` | pv_controller.go:331 |
| 选卷 | `findBestMatchForClaim` | pv_controller.go:343（索引 index.go:110） |
| 绑定 | `bind`（双向引用） | pv_controller.go:395 → 1094 |
| 动态供给 | `provisionClaim` | pv_controller.go:376 → 1576 |
| 已绑维护 | `syncBoundClaim` | pv_controller.go:492 |

## 深化 · 绑定竞态、延迟绑定与挂载失败路径

存储链条的每一段都可能失败或竞争，控制器靠"双向引用 + 状态复检 + 逐层重试"收敛：

- **双向绑定的原子补齐**：`bind`（pv_controller.go:1094）分别写 PV.claimRef（`bindVolumeToClaim`:996）与 PVC.volumeName（`bindClaimToVolume`:1037）两步，非事务；若中途只写成功一边，下轮 `syncClaim`（pv_controller.go:237）/`syncVolume`（pv_controller.go:562）会检测到"一边绑了一边没绑"并补齐另一边——**最终一致而非强一致**。
- **抢绑竞争**：多个 PVC 可能同时 `findBestMatchForClaim`（index.go:110）选中同一 PV，只有第一个成功写 claimRef 的胜出，其余在下轮发现该 PV 已被别人 claim（`syncVolume`:562 里校验 claimRef）而回退重新找——乐观并发在存储里的体现。
- **WaitForFirstConsumer 延迟绑定**：StorageClass 设此模式时，`findBestMatchForClaim`（index.go:110）带 `delayBinding=true`，PV 控制器**不立即绑定**，而是等调度器决定 Pod 落哪个节点后再按节点拓扑选卷——避免"卷在 A 区、Pod 被调度到 B 区"的死锁。
- **动态供给失败**：`provisionClaimOperation`（pv_controller.go:1616）调 provisioner 建卷失败（配额不足、后端故障）→ PVC 停在 Pending 并打 event，控制器按退避重试；外部 CSI provisioner 路径 `provisionClaimOperationExternal`（pv_controller.go:1822）则由外部组件 watch PVC 完成。
- **Attach/Mount 卡住**：Attach 失败（云 API 限流、节点已满 attach 上限）或 Mount 超时会让 Pod 卡 `ContainerCreating`；kubelet 侧 `WaitForAttachAndMount` 阻塞并在下轮 SyncPod 重试（见 kubelet 篇）。**删除的逆序**：删 Pod 时必须先 Unmount→Detach 再回收卷，顺序错会导致卷泄漏或数据损坏。

## 深化 · 存储对象职责

| 对象 | 谁写 | 含义 |
|---|---|---|
| PVC | 用户 | 申领：要多大、什么访问模式、哪个 StorageClass |
| PV | 管理员 / provisioner | 实际存储资源（静态或动态生成） |
| StorageClass | 管理员 | 动态供给模板（provisioner + 参数） |
| VolumeAttachment | AttachDetach 控制器 | 卷是否已 attach 到某节点 |
| CSIDriver / CSINode | 驱动注册 | 节点上有哪些 CSI 能力 |

## 拓展 · CSI 挂载三阶段

| 阶段 | 执行者 | 动作 |
|---|---|---|
| Provision | 外部 CSI provisioner | 在后端创建卷 → 生成 PV |
| Attach | AttachDetach 控制器 | 卷挂到目标节点（如云盘 attach VM） |
| Mount | kubelet + 节点 CSI driver | mount 进 Pod 容器目录 |

## 调优要点

- 用 StorageClass + 动态供给替代手工建 PV，避免容量碎片与人工绑定。
- 访问模式（RWO/ROX/RWX）要与工作负载匹配：多数块存储只支持 RWO（单节点读写）。
- `volumeBindingMode: WaitForFirstConsumer` 让卷绑定延迟到 Pod 调度后，避免卷与 Pod 落到不同拓扑域。
- reclaimPolicy 生产慎用 Delete：误删 PVC 会连带删除底层数据。

## 常见误区

- **PVC 就是存储本身**：PVC 是申领，PV 才是实际资源，二者绑定后使用。
- **kubelet 负责创建云盘**：创建（provision）是 CSI provisioner，kubelet 只做节点上的 mount。
- **绑定是单向的**：PVC↔PV 双向引用（volumeName / claimRef），一一对应独占。
- **删 PVC 数据一定没了**：取决于 reclaimPolicy，Retain 会保留 PV 与数据。

## 一句话总纲

**K8s 把持久存储也声明式化：用户用 PVC 声明"要多大的什么存储"，PV 控制器 reconcile 地为其匹配现有 PV 或经 StorageClass 动态供给新 PV 并双向绑定，随后经 CSI 的 Provision→Attach→Mount 三段把卷真正挂进 Pod——存储的申领、供给、挂载、回收全部纳入"期望态 + 控制器收敛"的统一框架，驱动逻辑与具体存储后端由 CSI 解耦。**
