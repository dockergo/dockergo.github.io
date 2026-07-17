# 接触面 · YARN 应用提交

> **定位**：计算平面的入口。用户程序（MapReduce、Spark、Flink 都一样）经 `YarnClient` 把一个「应用」提交给 ResourceManager，RM 先启动一个 **ApplicationMaster（AM）**容器，之后由 AM 自己向 RM 申请后续资源、由 NodeManager 就地拉起 Container 跑任务。YARN 把「集群资源仲裁」与「应用内部调度」解耦：RM 只管分配资源不管应用逻辑，AM 才懂业务。上承任意计算框架的提交请求，下启 YARN 资源调度与各框架的 AM。

## 应用提交时序 · 两阶段

![应用提交时序](Hadoop原理_接口_YARN应用提交_01时序.svg)

提交是两阶段：**① 提交应用**——client 向 RM 申请 applicationId，构造 `ApplicationSubmissionContext`（含 AM 启动命令、资源需求、本地资源），RM 的 `ApplicationMasterService`（`hadoop-yarn-server-resourcemanager/.../ApplicationMasterService.java:84`）与调度器受理，在某个 NodeManager 上启动**第一个 Container 跑 AM**。**② AM 自调度**——AM 启动后向 RM `registerApplicationMaster`（`:243`）注册，随后循环调 `allocate`（`:390`）申请/领取 Container，拿到后请对应 NodeManager `startContainers`（`ContainerManagerImpl.java:996`）就地启动任务；应用结束 `finishApplicationMaster`（`:300`）。

以 MapReduce 为例，client 侧走 `YARNRunner`（`hadoop-mapreduce-client-jobclient/.../mapred/YARNRunner.java:110`）：`submitJob`（`:320`）→ `createApplicationSubmissionContext`（`:574`）把 job 打包成 YARN 应用，AM 即 `MRAppMaster`。

## 深化 · RM / AM / NM 职责边界

| 角色 | 管什么 | 不管什么 | 源码 |
|---|---|---|---|
| ResourceManager | 全集群资源仲裁、启动 AM、调度 Container | 应用内部任务编排 | `ResourceManager.java:170` |
| ApplicationMaster | 本应用的任务切分、资源申请、失败重试 | 别的应用、物理资源池 | `MRAppMaster.java:180`（MR 的 AM） |
| NodeManager | 本节点资源上报、拉起/监控/杀 Container | 全局调度决策 | `NodeManager.java:100` |

## 调优要点

- **AM 资源要够但别浪费**：`yarn.app.mapreduce.am.resource.mb` 过小 AM 自身 OOM，过大挤占任务额度。
- **提交端本地资源用共享缓存**：jar/配置作为 LocalResource 分发，`public` 可见性可跨应用复用，减少重复上传。
- **合理设置 AM 最大重试**：`yarn.resourcemanager.am.max-attempts`，AM 挂了 RM 会重拉，但重试上限要匹配作业时长。

## 常见误区

- **误以为 RM 调度任务**：RM 只分配 Container 资源；任务如何切分、跑什么由 AM 决定。这是 YARN 相较老 MRv1 JobTracker 的核心解耦。
- **误以为提交即运行**：提交只是入队；实际运行要等调度器按队列容量分到 Container。
- **误把 AM 当常驻服务**：AM 生命周期 = 应用生命周期，应用结束即退出，不是守护进程。

## 一句话总纲

**YARN 提交是「RM 先给你一个 AM 容器、AM 再自己去要干活的容器」两阶段——资源仲裁与应用调度彻底解耦，任何计算框架只要实现一个 AM 就能跑在 YARN 上。**
