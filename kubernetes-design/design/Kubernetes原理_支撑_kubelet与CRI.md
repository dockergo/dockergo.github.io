# Kubernetes 核心原理 · 支撑能力域 · kubelet 与 CRI

> **定位**：节点侧的执行代理，也是一个 reconcile 循环。kubelet 在每台机器上把"绑定到本节点的 Pod（spec）"变成真实运行的容器（实际态），经 CRI 调容器运行时（containerd/CRI-O）。它是 K8s "期望态"落到"真实进程"的最后一公里。核实基准：`pkg/kubelet/kubelet.go`。

## 一、syncLoop：多源事件驱动的节点级 reconcile

![syncLoop](Kubernetes原理_支撑_kubelet与CRI_01syncLoop.svg)

kubelet 的核心是 `syncLoop`（kubelet.go:2387）——一个永续循环，`syncLoopIteration`（:2461）用 select 同时监听多个源：`configCh`（API Server 来的 Pod 增删改，`case u, open := <-configCh`:2464）、`plegCh`（PLEG=Pod Lifecycle Event Generator，`kl.pleg.Watch`:2396，容器实际状态变化，容量 `plegChannelCapacity=1000`:183）、`syncCh`（周期性全量同步 tick）、`housekeepingCh`（清理孤儿）、探针结果。**任一源触发都归结为对某个 Pod 调 `SyncPod`**（:1845）：算出该 Pod 的期望容器集与当前实际容器集的差异 → 需要就创建 Pod 沙箱（pause 容器 + 网络命名空间，经 CNI 配网）→ 拉镜像 → 起/杀容器，全部经 `kl.containerRuntime.SyncPod(...)`（:2029）走 **CRI** gRPC（RunPodSandbox/CreateContainer/StartContainer…）到 containerd。**这就是节点级的 level-triggered reconcile**：不管收到什么事件，`SyncPod` 都重算"这个 Pod 现在该有哪些容器、实际有哪些"，补齐差异；容器崩了 PLEG 会报事件，重算就会按 restartPolicy 重启。`HandlePodAdditions`（:2601）在收到新 Pod 时做准入（资源是否够）再纳管。kubelet 还周期性把节点与 Pod 的 status 写回 API Server（心跳 + 实际态上报），供调度器和控制器决策。

## 深化 · CRI 与相邻接口

| 接口 | 缩写 | 谁实现 | 干什么 |
|---|---|---|---|
| Container Runtime Interface | CRI | containerd / CRI-O | 沙箱/容器/镜像 gRPC |
| Container Network Interface | CNI | Calico / Cilium… | 给 Pod 沙箱配网络 |
| Container Storage Interface | CSI | 各存储驱动 | 挂载卷（见存储篇） |
| PodLifecycleEventGenerator | PLEG | kubelet 内部 | relist 容器状态生成事件 |

## 拓展 · 一个 Pod 从绑定到运行

| 步骤 | 组件 | 动作 |
|---|---|---|
| 1 | 调度器 | 写 pod.spec.nodeName |
| 2 | kubelet syncLoop | configCh 收到本节点新 Pod |
| 3 | SyncPod | RunPodSandbox（pause + CNI 配网） |
| 4 | SyncPod | 拉镜像 + CreateContainer/StartContainer（CRI） |
| 5 | PLEG | relist 发现容器 Running，回灌事件 |
| 6 | kubelet | 探针检测 + 写 Pod status 回 API Server |

## 调优要点

- PLEG relist 周期与 `plegChannelCapacity`（1000）影响状态感知延迟；节点容器过多会拖慢 relist。
- 镜像拉取是常见瓶颈：预热镜像、用 `imagePullPolicy: IfNotPresent`、镜像本地缓存。
- 节点资源预留（`--kube-reserved`/`--system-reserved`）避免 kubelet/系统被业务挤爆。
- liveness/readiness 探针配置不当会误杀或误摘容器，谨慎设初始延迟与阈值。

## 常见误区

- **kubelet 从 etcd 读 Pod**：kubelet 经 API Server（watch）拿分配到本节点的 Pod，不碰 etcd。
- **kubelet 直接运行容器**：它经 CRI 调外部运行时（containerd），自身不含容器引擎。
- **一次事件对应一次固定动作**：SyncPod 是重算差异的 reconcile，事件只是触发。
- **Pod 网络由 kubelet 自己配**：网络由 CNI 插件在建沙箱时配置。

## 一句话总纲

**kubelet 是节点侧的 reconcile 循环：syncLoop 用 select 汇聚 API Server 变更、PLEG 容器事件、周期 tick 等多源信号，任一触发都对相关 Pod 调 SyncPod 重算"期望容器集 vs 实际容器集"的差异、经 CRI 调 containerd 建沙箱（CNI 配网）/拉镜像/起杀容器，并把实际态写回 API Server——它把集群的"期望 Pod"落成机器上真实运行的进程，是声明式期望态的最后一公里。**
