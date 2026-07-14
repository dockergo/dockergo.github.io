# Hudi 原理 · 支撑主线 · 表服务与并发

> **定位**：属"保障能力域"。管后台维护与多写并发:表服务(compaction/cleaning/clustering)+ 并发控制(OCC 乐观并发 + 锁 provider + marker)。依赖【时间线】记服务动作、维护【表类型】的文件。源码基准 **Hudi(1dfbdcb)**(`hudi-client/`、`hudi-common/`)。

Hudi 表要长期健康运行,靠**表服务**后台整理(compaction 合 log、cleaning 清旧、clustering 重组);多引擎并发写靠**并发控制**(OCC + 锁 + marker 文件)。这些都记在时间线上作为动作(compaction/clean/replacecommit),与写动作交织但状态独立管理。理解表服务 + 并发,就懂了 Hudi 的运维与多写保障。

---

## 一、表服务:compaction / cleaning / clustering

![Hudi 表服务](Hudi原理_服务_01表服务.svg)

三大后台服务(都是时间线上的动作):

- **Compaction**(MOR:合 log 进 base):`RunCompactionActionExecutor` 执行 `HoodieCompactionPlan`(`RunCompactionActionExecutor.java:19`),把 MOR 文件片的 log 合并进 base 产新 base 文件——缩小读时合并量。可有 3 状态(requested/inflight/completed)。log-compaction(`WriteOperationType.LOG_COMPACT`)是轻量变体。
- **Cleaning**(清旧文件片):`CleanActionExecutor`(`CleanActionExecutor.java:61`)按策略删旧 slice。`HoodieCleaningPolicy`(`HoodieCleaningPolicy.java:34`):`KEEP_LATEST_FILE_VERSIONS`/`KEEP_LATEST_COMMITS`(默认)/`KEEP_LATEST_BY_HOURS`——保留多少版本/提交/小时,余者回收。
- **Clustering**(重组数据):经 `WriteOperationType.CLUSTER`(`BaseHoodieWriteClient.java:1414`),用 replacecommit 动作重排文件(如按列排序、合并小文件),提查询性能。一致性哈希桶的动态调整用 `HoodieConsistentHashingMetadata`。

服务动作与写动作在同一时间线,但独立调度——写不阻塞于服务、服务后台异步跑。

---

## 二、并发控制:OCC + 锁 + marker

![Hudi 并发控制](Hudi原理_服务_02并发.svg)

多写并发靠**乐观并发控制(OCC)**:

- **并发模式**(`WriteConcurrencyMode.java:30`):`SINGLE_WRITER` / `OPTIMISTIC_CONCURRENCY_CONTROL` / `NON_BLOCKING_CONCURRENCY_CONTROL`。OCC 和 NBCC 支持多写。
- **事务管理**:`TransactionManager`(`TransactionManager.java:33`)"允许客户端开始/结束事务,保证原子",`beginStateChange`/`endStateChange` 在需要锁时经 `LockManager` 获取/释放。
- **冲突检测**:提交前 `resolveWriteConflict(table, metadata, pendingInstants)`(`BaseHoodieWriteClient.java:435`);`SimpleConcurrentFileWritesConflictResolutionStrategy.hasConflict` 算**改动的 (partition, fileId) 对的交集**,非空即冲突(`:133`)——两个并发写改了同一文件组才冲突。
- **锁 provider**(可插拔):`InProcessLockProvider`、`ZookeeperBasedLockProvider`、AWS `DynamoDBBasedLockProvider` 等。
- **marker 文件**(`MarkerType { DIRECT, TIMELINE_SERVER_BASED }`,`MarkerType.java:30`):每次写创建 marker 标记产生的文件 + IOType,失败回滚时按 marker 删部分写的文件。

**为什么 OCC**:数据湖多引擎写,悲观锁开销大;OCC 假设冲突少(写不同文件组不冲突),冲突时靠 (partition,fileId) 交集检测——只有真改同一文件组才失败。

---

## 拓展 · 表服务与并发关键结构一览

| 结构 | 定义 | 职责 |
|---|---|---|
| RunCompactionActionExecutor | `table/action/compact/RunCompactionActionExecutor.java:19` | 合 log 进 base |
| CleanActionExecutor | `table/action/clean/CleanActionExecutor.java:61` | 清旧文件片 |
| HoodieCleaningPolicy | `model/HoodieCleaningPolicy.java:34` | 保留策略(版本/提交/小时) |
| TransactionManager | `client/transaction/TransactionManager.java:33` | 事务原子 + 锁 |
| SimpleConcurrentFileWritesConflictResolutionStrategy | `client/transaction/...java:133` | (partition,fileId) 交集冲突检测 |
| MarkerType | `common/table/marker/MarkerType.java:30` | DIRECT / TIMELINE_SERVER_BASED |

## 调优要点（关键开关）

- **compaction 策略/频率**:MOR 表按 log 量/提交数触发 compaction;太疏读慢、太勤耗资源。
- **cleaning 策略**:`KEEP_LATEST_COMMITS`(默认)平衡时间旅行与空间;时间旅行需求低可 KEEP_LATEST_FILE_VERSIONS 省空间。
- **并发模式**:单写用 SINGLE_WRITER(无锁开销);多引擎写用 OCC + 配锁 provider(ZK/DynamoDB)。
- **marker 类型**:HDFS/流式用 DIRECT;大规模用 TIMELINE_SERVER_BASED(减少小文件)。

## 常见误区与工程要点

- **误区:MOR 不用管 compaction。** 不 compaction 则 log 无限攒、快照读越来越慢;必须定期 compaction 合进 base。
- **误区:OCC 下并发写总冲突。** 只有改**同一文件组**((partition,fileId) 交集非空)才冲突;写不同分区/文件组不冲突。
- **误区:cleaning 会删正在用的数据。** 按策略保留最新 N 版本/提交;只清超出保留窗口的旧 slice。
- **误区:marker 是元数据。** marker 标"本次写产生了哪些文件",用于失败回滚清理孤儿文件,不是表元数据。
- **归属提醒**:服务动作(compaction/clean/cluster)记在【时间线】;合并/清理的文件片在【表类型】;并发提交的 instant 在【时间线】;写入本身在【写入与索引】。

## 一句话总纲

**Hudi 靠表服务维护 + OCC 保多写并发:表服务都是时间线动作——compaction(RunCompactionActionExecutor 合 MOR 的 log 进 base 缩小读合并)、cleaning(CleanActionExecutor 按 HoodieCleaningPolicy 保留最新 N 提交/版本清旧 slice)、clustering(replacecommit 重排文件提查询);多写并发用乐观并发控制(WriteConcurrencyMode OCC/NBCC,TransactionManager + 可插拔锁 provider ZK/DynamoDB,提交前按改动的 (partition,fileId) 交集检测冲突——只有改同一文件组才失败),marker 文件标记写产物用于失败回滚清理。**
