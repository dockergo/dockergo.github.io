# Kubernetes 核心原理 · 支撑能力域 · 控制器管理器与垃圾回收

> **定位**：几十个控制器的"运行时底座"与集群级清理器。`kube-controller-manager` 把众多控制器编排进一个进程（共享 Informer、leader 选举保只有一个实例在跑），而**垃圾回收（GC）**控制器沿 `ownerReferences` 构成的对象图做级联删除、`finalizers` 提供删除前钩子——它们是让"控制器群"稳定运行、让"删除"正确收敛的公共机制。核实基准：`cmd/kube-controller-manager/app/controllermanager.go`、`pkg/controller/garbagecollector/garbagecollector.go`。

## 一、多控制器编排 + ownerReferences 级联 GC

![编排与GC](Kubernetes原理_支撑_控制器管理器与GC_01编排与GC.svg)

**控制器编排**：controller-manager 启动时 `NewControllerDescriptors`（controllermanager.go:248）注册全部控制器（Deployment/ReplicaSet/Node/Job/PV/GC…），共用一个 SharedInformerFactory（同一资源只 List+Watch 一次）。**高可用靠 leader 选举**：多副本时用 `leaderelection`（:51、LeaderCallbacks:315）竞争一个 Lease 锁，**只有 leader 真正运行控制器循环**，其余待命——避免多实例同时 reconcile 同一对象产生冲突。**垃圾回收（GC）**：K8s 的删除不是控制器一个个手动删下游。GC 控制器（garbagecollector.go）在内存里维护一张**对象依赖图**——边就是 `ownerReferences`（子对象 metadata 里指向 owner）。当一个 owner 被删，GC 沿图找到所有孤儿子对象 `attemptToDeleteItem`（:342）级联删除（如删 Deployment → 删其 ReplicaSet → 删 Pod）；`absentOwnerCache`（:73）缓存"已确认不存在的 owner"避免反复查。**删除传播策略**：`Foreground`（先删下游、owner 最后消失）/ `Background`（owner 先删、GC 后台清下游）/ `Orphan`（保留下游、只删 owner）。**finalizers**：对象 metadata 里的 finalizer 列表让删除**可阻塞**——API Server 收到删除只是打上 `deletionTimestamp`，对象要等所有 finalizer 被对应控制器处理并移除后才真正消失（用于删除前做外部资源清理，如释放云盘、注销 LB）。GC + finalizer 共同保证"删除"这件事也在声明式 + reconcile 框架内正确收敛。

## 深化 · 删除传播策略

| 策略 | 行为 | 用途 |
|---|---|---|
| Foreground | 先删所有下游，owner 最后删 | 需保证下游先清理 |
| Background（默认多数） | owner 先删，GC 后台清下游 | 快速返回 |
| Orphan | 只删 owner，保留下游 | 保留子对象（解绑管理） |

## 拓展 · 对象图与清理机制

| 机制 | 数据 | 作用 |
|---|---|---|
| ownerReferences | 子对象 → owner 的边 | GC 级联删除的图 |
| GC 控制器 | 内存依赖图 + attemptToDelete | 删 owner 连带删孤儿 |
| finalizers | metadata 字符串列表 | 删除前置钩子（阻塞至清理完） |
| deletionTimestamp | 删除标记 | "正在删除"而非立即消失 |
| leader 选举 | Lease 锁 | 保证控制器单实例运行 |

## 调优要点

- controller-manager 多副本 + leader 选举做 HA：`--leader-elect` 默认开，调 lease 时长权衡切换速度与抖动。
- `--concurrent-*-syncs` 调各控制器 worker 数，权衡收敛速度与 API Server 压力。
- 卡在 Terminating 的对象几乎总是 finalizer 未被移除：排查对应控制器是否健康，勿盲目强删。
- 大规模集群 GC 依赖图内存与 discovery 开销大：关注 GC 控制器的同步（Sync:175）健康。

## 常见误区

- **每个控制器一个进程**：几十个控制器共处 kube-controller-manager 一个进程、共享 Informer。
- **多副本控制器同时工作**：leader 选举保证只有一个实例跑循环。
- **删 Deployment 要手动删 Pod**：GC 沿 ownerReferences 级联删除下游。
- **删除即刻生效**：有 finalizer 时先打 deletionTimestamp，待 finalizer 清完才真正删除。

## 一句话总纲

**控制器管理器是控制器群的运行时底座：把几十个控制器编排进一个进程、共享 Informer、用 leader 选举保单实例运行；而垃圾回收沿 ownerReferences 对象图做级联删除、finalizers 提供可阻塞的删除前钩子、deletionTimestamp 标记"正在删除"——让"删除"也纳入声明式 + reconcile 的正确收敛，是支撑整个控制平面稳定运转的公共机制。**
