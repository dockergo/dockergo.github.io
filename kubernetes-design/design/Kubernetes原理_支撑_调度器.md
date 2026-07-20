# Kubernetes 核心原理 · 支撑能力域 · 调度器

> **定位**：一个专职控制器——为处于 Pending、未绑定节点的 Pod 挑一个最合适的节点，写回 `pod.spec.nodeName`（绑定）。它本身不启动容器，只做"选址"。调度分两段：**调度周期**（filter→score→选点，串行、需全局视图）与**绑定周期**（reserve/permit/prebind/bind，可异步）。核实基准：`pkg/scheduler/schedule_one.go`、`pkg/scheduler/framework/interface.go`。

## 一、调度框架：filter → score → bind

![filter-score-bind](Kubernetes原理_支撑_调度器_01filter-score-bind.svg)

调度器从内部优先级队列取一个 Pod，进入 `schedulePod`（`pkg/scheduler/schedule_one.go:411`）：① **findNodesThatFitPod**（schedule_one.go:463）→ `findNodesThatPassFilters`（schedule_one.go:591）——**Filter（预选）**：逐节点跑所有 FilterPlugin（`fwk.RunFilterPluginsWithNominatedPods`，schedule_one.go:629；接口见 `pkg/scheduler/framework/interface.go:831`、`FilterPlugin` 定义 interface.go:540），把"放不下"的节点全部剔除（资源不足 / 端口冲突 / 亲和性不满足 / 污点不容忍 / PVC 不可用…）；结果是"可行节点集"，空集则触发抢占（`RunPostFilterPlugins`，schedule_one.go:175）。**大集群剪枝**：`numFeasibleNodesToFind`（schedule_one.go:676）按 `percentageOfNodesToScore` 只找够用的可行节点就停，不必遍历全部。② **prioritizeNodes**（schedule_one.go:755）——**Score（优选）**：对可行节点跑所有 ScorePlugin 打分（每插件返回 `[MinNodeScore=0, MaxNodeScore=100]`，interface.go:258/255；`ScorePlugin` 定义 interface.go:607），按权重加权求和。③ **selectHost**（schedule_one.go:873）——选最高分节点（同分随机，避免热点）。**随后进 schedulingCycle**（schedule_one.go:138）：`sched.assume`（schedule_one.go:946，调用于:197）**乐观地**把 `NodeName` 写进调度器内存缓存（不等 API Server 确认，好让下一个 Pod 调度时把它算作已占用）→ `RunReservePluginsReserve`（:208）预留资源 → `RunPermitPlugins`（:231，可延迟/拒绝，如 gang 调度等齐一批）。**绑定周期**（`bindingCycle`，schedule_one.go:266，可与下个 Pod 的调度并行）：prebind → `bind`（schedule_one.go:968）默认实现 = 向 API Server 创建一个 Binding 对象，API Server 把 `pod.spec.nodeName` 写实。若中途失败，`ForgetPod`（:211）回滚缓存里的假设并 `RunReservePluginsUnreserve`（:210）。**为何 assume**：调度是串行的全局决策，若每次都等 etcd 写完再调度下一个会极慢；乐观假设让吞吐大增，失败再回滚。

## 深化 · 调度队列的三段结构与失败重试

调度不是"从一个 FIFO 取 Pod"这么简单。`PriorityQueue`（`pkg/scheduler/backend/queue/scheduling_queue.go`）内部分三段（scheduling_queue.go:20-24 注释）：

- **activeQ**（scheduling_queue.go:66）：等待调度、按优先级排序的堆，`Pop`（scheduling_queue.go:857）取队头。
- **backoffQ**（:67）：刚调度失败的 Pod 先在此按指数退避冷却，`flushBackoffQCompleted`（scheduling_queue.go:804）到点把它们搬回 activeQ——**避免热失败 Pod 疯狂空转占满调度器**。
- **unschedulablePods**（:68 附近）：确定当前无处可放的 Pod 存这里，不占 activeQ；`flushUnschedulablePodsLeftover`（scheduling_queue.go:834）超时（默认 5min）兜底搬回。

**关键的事件驱动重试**：当集群发生"可能让某 Pod 变得可调度"的变化（如某 Pod 被删释放资源、新增 Node），`MoveAllToActiveOrBackoffQueue`（scheduling_queue.go:1056）把 unschedulable 里相关 Pod 唤醒——这是 level-triggered 思想在调度器里的体现，Pod 不会"一次调度失败就永久卡死"。

**失败与抢占路径**：
- 调度周期出错走 `handleSchedulingFailure`（schedule_one.go:1023）——把 Pod 送回 unschedulable/backoff，并按 `nominatingInfo` 记录抢占提名节点（`AddNominatedPod`，schedule_one.go:1090 → `nominator.go:67`）。
- 可行集为空且注册了 PostFilter 时，默认抢占插件 `SelectVictimsOnNode`（`pkg/scheduler/framework/preemption/preemption.go:705`）在候选节点上算出**最小驱逐集**（尊重 PDB），驱逐低优 Pod 给高优 Pod 腾位；被提名节点记在 Pod 的 `status.nominatedNodeName`，下一轮优先尝试。
- assume 后绑定失败（如节点已不满足、API 写冲突）→ `ForgetPod`（schedule_one.go:211）撤销内存占位，Pod 重新入队——**内存缓存与 etcd 的最终一致由这条回滚路径兜底**。

## 深化 · 调度扩展点（framework）

| 扩展点 | 作用 | 空集/拒绝后果 |
|---|---|---|
| PreFilter / Filter | 预处理 + 剔除放不下的节点 | 可行集空 → 抢占或 Pending |
| PostFilter | 无可行节点时触发（抢占） | 驱逐低优 Pod 腾位 |
| PreScore / Score | 对可行节点打分（0~100） | 决定优选排序 |
| Reserve / Permit | 预留资源 / 准入（可等齐） | Unreserve 回滚 |
| PreBind / Bind / PostBind | 绑定前后钩子 + 写 nodeName | 失败 ForgetPod 回滚 |

## 拓展 · 调度器不是什么

| 误解 | 实情 |
|---|---|
| 启动容器 | 只写 nodeName，容器由目标节点 kubelet 拉起 |
| 全局最优解 | 逐 Pod 贪心 + 打分，非全局最优 |
| 同步落库再调下一个 | assume 乐观占位，绑定异步，失败回滚 |
| 只看资源 | 亲和/反亲和、污点容忍、拓扑分布、PVC 拓扑都参与 filter/score |

## 调优要点

- 大集群开 `percentageOfNodesToScore`：只对部分节点打分，牺牲少量最优换调度吞吐。
- 用 PodTopologySpread / 亲和性控制分布，但插件越多单次调度越慢。
- 抢占（PriorityClass）保障高优 Pod 抢占低优；谨慎设置避免抖动。
- 绑定周期与调度周期解耦，volume 绑定等慢操作放绑定周期不阻塞调度队列。

## 常见误区

- **调度器启动 Pod**：它只做绑定（写 nodeName），执行是 kubelet。
- **Filter 给节点打分**：Filter 只做布尔可行性剔除，打分是 Score 阶段。
- **assume 后就一定绑定成功**：assume 是内存乐观占位，绑定失败会 ForgetPod 回滚。
- **调度一次考虑所有 Pod 全局最优**：逐 Pod 处理，是贪心而非全局优化。

## 一句话总纲

**调度器是"选址"专职控制器：对每个待调度 Pod 先 Filter 剔除放不下的节点、再 Score 给可行节点打分（0~100）选最高分，然后乐观 assume 占位以维持串行调度的高吞吐，最后在可异步的绑定周期把 pod.spec.nodeName 写回 API Server——它只决定"去哪台"，真正拉起容器的是目标节点的 kubelet。**
