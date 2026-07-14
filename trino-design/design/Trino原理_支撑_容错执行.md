# Trino 原理 · 支撑主线 · 容错执行（FTE）

> **定位**：属"保障能力域"。让长查询在 worker/task 失败时**不整个重来**——按 `RetryPolicy` 做查询级或任务级重试，任务级依赖 spooling exchange 把中间结果落外部存储以便重试去重。被【分布式执行】按策略选用（默认 NONE 不启用），依赖【数据交换】的 ExchangeManager SPI。源码基准 **Trino 483-SNAPSHOT**。

默认 Trino 是"尽力而为"——一个 worker 挂了，整条查询失败。对跑几十分钟的 ETL 这代价太大。FTE 通过 `RetryPolicy` 提供两档容错：**QUERY**（整查询重试）与 **TASK**（任务级重试，需 exchange-manager）。

---

## 一、RetryPolicy 三档：容错级别与调度器选择

![Trino RetryPolicy · NONE/QUERY/TASK 与调度器映射](Trino原理_容错_01RetryPolicy.svg)

`RetryPolicy`（`io.trino.operator`）有三值，`SqlQueryExecution.createQueryScheduler` 据此选调度器：

- **NONE**（默认）：不重试，`PipelinedQueryScheduler`，任一失败整查询挂。
- **QUERY**：整查询重试，仍用 `PipelinedQueryScheduler`（内部 `shouldRetry` 判可重试错误码 + 未超 `query-retry-attempts`，默认 4，排除 fatal/USER_ERROR），流式直连 exchange。
- **TASK**：任务级重试，`EventDrivenFaultTolerantQueryScheduler` + spooling exchange，单 task 失败只重跑该 task。

`retry-policy.allowed` 可限制允许的策略集（483 新增）。

---

## 二、任务级重试：EventDrivenFaultTolerantQueryScheduler

![Trino 任务级重试 · 每分区独立重试 + 内存增长](Trino原理_容错_02任务重试.svg)

FTE 调度器为每个 stage partition 建一个 `StagePartition`，`remainingAttempts` 初始 = `task-retry-attempts-per-task`+1（默认 5）。task 失败时 `StageExecution.taskFailed`：

- **给不给重试**：`remainingAttempts==0` 或 USER_ERROR 或 fatal 错误码 → `stage.fail`（放弃）；否则重新发一个 `PrioritizedScheduledTask` 到同 partition（重试）。
- **内存感知重试**：OOM 失败时 `getNextRetryMemoryRequirements` 给下次更大的内存估计（`ExponentialGrowthPartitionMemoryEstimator`）；`BinPackingNodeAllocatorService` 据此选节点。
- **每 attempt 新 sink 实例**：`exchange.instantiateSink(handle, attempt)` 按 attempt 键控，实现结果去重。
- speculative（未 sealed）partition 不重试。

---

## 三、Spooling exchange：中间结果落外部存储

![Trino spooling exchange · ExchangeManager 暂存与去重](Trino原理_容错_03spooling.svg)

TASK 策略下，stage 间数据不走流式直连，而经 **ExchangeManager SPI**（引擎内部叫 spooling exchange）落到外部存储：

- 上游 task 经 `ExchangeSink.add(partition, Slice)` 写；`FileSystemExchangeSink` 把每分区写成 `.data` 文件，`finish()` 时落 `committed` 标记。
- 下游经 `ExchangeSource.read()` 读；**忽略无 `committed` 标记的目录**——这是去重关键：某 task 重试产生的多份输出，只有 committed 的那份被读。
- `ExchangeManagerRegistry` 从 `exchange-manager.properties` 加载（`filesystem`/S3）；未配则 `EXCHANGE_MANAGER_NOT_CONFIGURED`——**FTE-TASK 必须配 exchange-manager**。

---

## 深化 · QUERY vs TASK 重试对比

![Trino QUERY vs TASK 重试 · 粒度与代价对比](Trino原理_容错_04对比.svg)

- **QUERY**：整查询重跑，无需 exchange-manager，实现简单（`PipelinedQueryScheduler.shouldRetry` 内），适合中短查询——失败率低时开销小，但一旦失败代价大（全部重算）。
- **TASK**：单 task 重跑，需 exchange-manager 暂存中间结果，适合长 ETL/大查询——失败只赔一个 task，但中间结果落盘有持续开销。
- 二者都排除 USER_ERROR（用户 SQL 错误重试无意义）与 fatal 错误码。

## 调优要点（关键开关）

- `retry-policy`（`NONE`/`QUERY`/`TASK`）、`retry-policy.allowed`（允许集）。
- `query-retry-attempts`（QUERY，默认 4）、`task-retry-attempts-per-task`（TASK，默认 4，上限 126）。
- `exchange-manager.properties`（TASK 必需）：`exchange-manager.name=filesystem` + 存储路径（本地/S3）。
- FTE 运行期自适应：`fault-tolerant-execution-runtime-adaptive-partitioning-enabled`（AdaptivePartitioning 治倾斜）。

## 常见误区与工程要点

- **误区：FTE 默认开启。** 默认 `RetryPolicy.NONE`，不容错。要显式配 `retry-policy`。
- **误区：TASK 策略不用额外配置。** 必须配 exchange-manager（落中间结果），否则启动即报 `EXCHANGE_MANAGER_NOT_CONFIGURED`。
- **误区：还有 `FaultTolerantQueryScheduler`/`FaultTolerantStageScheduler`。** 483 只有 `EventDrivenFaultTolerantQueryScheduler`（旧类已移除），且在 `faulttolerant/` 子包。
- **误区：QUERY 重试也用 spooling。** 不。QUERY 用流式直连（PipelinedQueryScheduler 内重试整查询）；只有 TASK 用 spooling exchange。
- **归属提醒**：AdaptivePlanner（运行期再优化）仅 FTE 路径存在（见【DQL】优化器篇），是 FTE 的附加能力，非通用查询优化。

## 一句话总纲

**FTE 按 RetryPolicy 提供两档容错：QUERY（整查询重试，流式直连，无需额外配置，适合中短查询）与 TASK（任务级重试，EventDrivenFaultTolerantQueryScheduler + spooling exchange 把中间结果落外部存储并靠 committed 标记去重，每分区独立重试且 OOM 时内存指数增长，适合长 ETL）——默认 NONE 不容错;二者都不重试 USER_ERROR 与 fatal 错误。**
