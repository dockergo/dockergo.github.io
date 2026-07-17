# Kubernetes 核心原理 · 支撑能力域 · 调度器

> **定位**：一个专职控制器——为处于 Pending、未绑定节点的 Pod 挑一个最合适的节点，写回 `pod.spec.nodeName`（绑定）。它本身不启动容器，只做"选址"。调度分两段：**调度周期**（filter→score→选点，串行、需全局视图）与**绑定周期**（reserve/permit/prebind/bind，可异步）。核实基准：`pkg/scheduler/schedule_one.go`、`pkg/scheduler/framework/interface.go`。

## 一、调度框架：filter → score → bind

![filter-score-bind](Kubernetes原理_支撑_调度器_01filter-score-bind.svg)

调度器从内部优先级队列取一个 Pod，进入 `schedulePod`（schedule_one.go:411）：① **findNodesThatFitPod**（:463）——**Filter（预选）**：逐节点跑所有 FilterPlugin（`RunFilterPluginsWithNominatedPods`:629），把"放不下"的节点全部剔除（资源不足 / 端口冲突 / 亲和性不满足 / 污点不容忍 / PVC 不可用…）；结果是"可行节点集"，空集则 Pod 保持 Pending 并触发抢占（PostFilter）。② **prioritizeNodes**（:755）——**Score（优选）**：对可行节点跑所有 ScorePlugin 打分（每插件返回 `[MinNodeScore=0, MaxNodeScore=100]`，interface.go:255/258），按权重加权求和。③ **selectHost**（:873）——选最高分节点（同分随机，避免热点）。**随后进 schedulingCycle**：`sched.assume`（:197）**乐观地**把 `NodeName` 写进调度器内存缓存（不等 API Server 确认，好让下一个 Pod 调度时把它算作已占用）→ `RunReservePluginsReserve`（:208）预留资源 → `RunPermitPlugins`（:231，可延迟/拒绝，如 gang 调度等齐一批）。**绑定周期**（`bindingCycle`:266，可与下个 Pod 的调度并行）：prebind → `bind`（:968）默认实现 = 向 API Server 创建一个 Binding 对象，API Server 把 `pod.spec.nodeName` 写实。若绑定失败，`ForgetPod` 回滚缓存里的假设。**为何 assume**：调度是串行的全局决策，若每次都等 etcd 写完再调度下一个会极慢；乐观假设让吞吐大增，失败再回滚。

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
