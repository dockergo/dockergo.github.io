# 架构原理 8 slug —— 已核实技术事实清单（写 SVG/MD 前必读，不要引入清单外的新技术断言）

本文件是本会话对每个真实项目落点做源码级/文档级核实后的结论摘要，供 8 个 slug 的内容撰写直接取材。
**铁律**：只写这里列出的、或能从这里直接推导的事实；不确定的细节要么不写，要么明确标注"概念参考，未源码级核实"。

---

## consistency（一致性与CAP）

- **etcd ReadIndex 线性读**（已存量核实，见 `projects/etcd/design/etcd原理_支撑_线性一致读.md`）：
  `server/etcdserver/read/read.go` 的 `LinearizableReadLoop` → `sendReadIndex` 向 Raft 请当前 commit index（一次心跳确认自己仍是 leader，不复制这次读本身）→ 等本地 `AppliedIndex()` 追上该 index → 读本地 MVCC。这是 etcd **默认**读语义；`Serializable` flag 可退化为直接读本地（更快但可能读旧）。
- **ZooKeeper ZAB 全局顺序**：`Proposal → Ack → Commit` 两阶段广播，`zxid = ⟨epoch, counter⟩` 给所有写操作定全局序；所有写必须经 leader 广播，各 follower 按 zxid 顺序应用——这保证的是**顺序一致**（所有客户端看到同一操作顺序），不是逐读线性一致。
- **ClickHouse 多主异步复制**（本会话用 WebFetch 核实官方文档 `clickhouse.com/docs/engines/table-engines/mergetree-family/replication`）：原文明确"Replication is asynchronous multi-master"；INSERT/ALTER 可发给任意可用副本，该副本本地处理后异步扩散给其余副本；无 leader 选举/主节点指定/写转发机制。Keeper 只做协调元数据（"used to store replicas' meta information"），不参与 SELECT 路径，也不代理写流量——每条 INSERT 约向 Keeper 写入十条事务性记录做簿记，实际数据体经副本间直接网络传输、不经 Keeper。**结论：这是真正的多主异步，一致性窗口=副本同步延迟。**
- **图示落点建议**：CAP/PACELC 四象限图，三个项目分别落在"CP/线性"（etcd）、"CP/顺序"（ZooKeeper）、"AP 倾向/最终"（ClickHouse 多主异步）三个区域，突出"同样是分布式存储，一致性谱系落点由架构选择决定"。

## replication（复制策略）

- **Postgres WAL 流复制**（已存量核实，见 `projects/postgres/design/Postgres原理_支撑_WAL与恢复复制.md`）：`walsender`(`replication/walsender.c:850` `StartReplication`→`WalSndLoop:3036`→`XLogSendPhysical:3350`) 把 WAL 流式发给备库 `walreceiver`(`replication/walreceiver.c:154` `WalReceiverMain`)；备库持续回放、可 hot standby 只读；主库故障可 promote。`synchronous_commit` 分级：`remote_apply > on > remote_write > off`，级别越高越不丢数据但延迟越高（off/异步下主库崩溃丢未传播的已提交事务，RPO≠0）。
- **ClickHouse 多主异步复制**：见上 consistency 节已核实内容，这里从"复制拓扑"角度复用——任意副本可写，副本间点对点异步传播,无固定主从关系。
- **Dynamo / Cassandra Quorum（N/R/W）**：**本会话未做源码级核实，明确标注为"概念参考"**——经典论文/文档描述的读写仲裁模型（W 个写副本确认即成功、R 个读副本确认即返回、`W+R>N` 保证读写重叠），不要在图和文中包装成已核实事实，如实注明"概念参考，本仓库/本会话未做源码级核实"。
- **图示落点建议**：三种拓扑（主从/多主/无主）的写路径 + 数据丢失窗口对比；无主一格务必带"概念参考"角标。

## partitioning（分片与一致性哈希）

- **Redis Cluster 16384 槎**：`keyHashSlot`（CRC16，`{...}` hash-tag 特殊处理）；`CLUSTER_SLOTS = 1<<14 = 16384`；`MOVED`（槎永久迁移，客户端应更新路由表）vs `ASK`（临时迁移中，需先发 `ASKING` 命令）通过 `getNodeByQuery`/`clusterRedirectClient` 实现。
- **Hudi 一致性哈希环 + 动态 split/merge**（本会话三次尝试后用更精确措辞核实）：`HoodieConsistentHashingMetadata`（字段 version/partitionPath/instant/numBuckets/seqNo/`List<ConsistentHashingNode>`），由 `ConsistentBucketIndexUtils` 管理；动态调整走 `BaseConsistentHashingBucketClusteringPlanStrategy`（构建 split/merge/sort 三类 clustering 分组）；`ConsistentBucketIdentifier.splitBucket()`（bucket 文件超过 `splitSize` 触发）、`ConsistentBucketIdentifier.mergeBucket()`（相邻 bucket 总大小低于 `mergeSize` 触发）；执行走 `SingleSparkJobConsistentHashingExecutionStrategy`。
- **Doris 两级分片**：`PARTITION BY RANGE|LIST(...)`（第一级，范围/枚举分区）+ `DISTRIBUTED BY HASH(...) BUCKETS n`（第二级，哈希分桶）；thrift 定义 `TPartitionType`/`TDistributionType` 枚举确认两级模型是显式区分的。
- **图示落点建议**：三种分片模型的"加/减节点要不要搬全量数据"代价对比——固定槎(Redis,槎数固定/节点变、槎搬迁但槎总数不变)、一致性哈希环(Hudi,只搬相邻 bucket)、两级静态(Doris,扩容通常需重分区，代价最高)。

## caching（缓存模式）

- **nginx proxy_cache**（本会话核实，deepwiki 原话即用"cache-aside style"表述，比原计划预期的核实强度更高）：未命中→回源→`ngx_http_file_cache_new`/`ngx_http_file_cache_update` 落盘填充；独立 cache-manager 进程；过期两条路径——`ngx_http_file_cache_expire`（`inactive` 时间到期）+ `ngx_http_file_cache_forced_expire`（`max_size`/`watermark` 超限时的 LRU 式强制淘汰）。**可以直说"这就是 cache-aside 读路径"，不需要再加"repo 未见字面命名"的免责声明**——deepwiki 官方口径已用该术语描述。
- **InnoDB Buffer Pool 写回**：确认官方术语即"midpoint insertion strategy"（LRU 链表中点插入，新页先进 old sublist 观察一段时间再晋升 young sublist，防止一次性全表扫描把热数据冲刷出缓存）；写回（脏页刷盘）是异步、独立于事务提交的——只要求 redo log 先落盘（WAL 铁律），脏页本身可以晚刷。
- **图示落点建议**：读路径（miss→回源→填充→命中）vs 写路径（写立即改内存+redo log 落盘，脏页异步刷盘，之后才落最终存储）双轨对比。

## flow-control（限流与背压）

- **nginx limit_req**（本会话 4 次尝试，算法级细节未能源码核实）：**已确认存在** `ngx_http_limit_req_module`，核心变量 `excess`（累积的"超额"请求计数），官方 changelog 确认该模块会主动计算并强制速率（曾有 bugfix 记录"speed might exceed configured rate"，侧证其内部确有速率累积计算逻辑）。**未能源码级核实**的是 `excess` 精确计算公式与 `rate`/`burst`/`nodelay` 默认值——图和文案里只描述"漏桶家族限流、按令牌累积/泄漏的思路节流请求"这一概念层描述，不要给出具体数值公式或默认值，如实注明这一层未做源码级核实。
- **k8s client-go 限流**（已核实，且比计划原文更细）：`AddRateLimited` 定义在 `TypedRateLimitingInterface`；默认实现 `DefaultTypedControllerRateLimiter` 实际是**两种策略组合**：`TypedItemExponentialFailureRateLimiter`（每 item 指数退避）**+** `TypedBucketRateLimiter`（令牌桶，控整体速率），通过 `NewTypedMaxOfRateLimiter` 取两者更严格的一个。**务必写成"指数退避+令牌桶组合"，不要简化成"纯令牌桶"**（这是本会话核实后纠正的一个关键细节，计划原始表述有误）。
- **Flink credit-based 反压**（已核实）：`credit`（下游可用 buffer 数，消费者→生产者告知）+ `backlog`（生产者侧未发送 buffer 积压量）双信号；`NetworkBufferPool`（全局池）→`LocalBufferPool`（per-task，exclusive+floating 两类 buffer）；`RemoteInputChannel`/`BufferManager`/`CreditBasedPartitionRequestClientHandler` 交换 `AddCredit` 消息实现反压传导。
- **图示落点建议**："拒绝在门外"（nginx/client-go，边缘限流，请求可能被拒或排队重试）vs "系统内部逐级减速"（Flink，上游主动降低发送速率，无拒绝无丢弃）两种范式并列。

## messaging（消息队列模式）

- **Kafka 全部三个变体均已核实**：
  - 发布订阅：Topic/Partition 广播模型（producer/consumer API 基本读写模型）。
  - 竞争消费者：consumer group rebalance——group coordinator 在成员加入/离开/metadata 变化时触发分区(re)分配。
  - 投递语义：幂等生产者（`ProducerAppendInfo.checkSequence` 校验严格递增序列号+epoch 递增防重复，`ProducerStateEntry.findDuplicateBatch` 做 PID+序列号去重）实现 at-least-once 下的去重；事务生产者实现跨分区原子写 + `isolation.level=read_committed` 消费端配合实现 exactly-once。
- **图示落点建议**：pub-sub 广播 vs 点对点队列 vs 分区内竞争消费 三态对比图；投递语义单独一张（幂等 producer 序列号机制示意）。

## service-discovery（服务发现）

- **etcd Lease**（已核实，且比计划原文更细）：`Lessor` 接口（`Grant`/`Renew`/`Revoke`），周期性过期检查→撤销 channel；**另有** `Checkpointer` 机制——把剩余 TTL 持久化进共识日志，使 leader 换届/进程重启后仍能恢复准确的剩余 TTL（不是简单内存计时器，这是一个值得单独提一句的细节，计划原始表述里没有）。
- **ZooKeeper Session/临时节点**（已存量核实为等价机制）：`SessionTrackerImpl`/`ExpiryQueue`/`roundToNextInterval`——把 session 过期时间分桶到固定间隔，批量检查而非逐个计时器，达到过期桶时间即批量清理该桶所有到期 session（及其临时节点）。
- **图示落点建议**：两种机制的过期判定路径并排对比——etcd 是"显式 TTL + 周期检查 + checkpoint 持久化"，ZooKeeper 是"session 分桶 + 批量清理 + 临时节点随 session 消亡"；强调两者本质是同一个"心跳续约、超时即判定死亡"思想的不同实现外壳。

## resilience（熔断/幂等/重试）

- **nginx 被动健康检查**（已存量核实）：`ngx_http_upstream_next` 在超时/5xx/429 时设置 `NGX_PEER_FAILED`；`ngx_http_upstream_get_least_time_peer`（及同类选择函数）检查 `fails >= max_fails` **且** `now - checked < fail_timeout` 来判定某 upstream 是否"不可用"——`fail_timeout` 窗口过后自动允许再次探测，这是一种"半开探测"式的被动熔断（无独立 half-open 状态机，但效果等价）。
- **gRPC outlier_detection**（已核实）：`OutlierDetectionLb`，源自 xDS `Cluster.outlier_detection` 配置；success_rate / failure_percentage 两种异常检测方式，`multiplier`控制惊出后的退避倍数增长，`EndpointState` 跟踪每端点状态。是 gRPC 官方原生具名"熔断"能力。
- **StarRocks 大查询资源熔断**（已核实，注意与前两者的类型区别）：Resource Group（`big_query_cpu_second_limit`/`big_query_mem_limit`/`big_query_scan_rows_limit`）+ Query Queue（准入控制）；`big_query_mem_limit` 场景官方文档确实用"熔断"一词。**这是资源型熔断**（触发条件=资源超限），区别于 nginx/gRPC 的**网络型熔断**（触发条件=远端故障率），图和文中要点出这个区别，不要混为一谈。
- **Kafka 幂等生产者**：见 messaging 节，`checkSequence`/`findDuplicateBatch` PID+序列号去重，是"幂等键去重"最典范的真实实现。
- **nginx proxy_next_upstream**：失败后自动切换下一个 upstream 重试；**必须**在文案中强调"非幂等方法（如非幂等 POST）配 `proxy_next_upstream` 重试有副作用风险"这一安全警示——这正是"重试为何必须配幂等"的具体例证。
- **图示落点建议**：①网络型熔断（nginx/gRPC）vs 资源型熔断（StarRocks）触发条件对比图；②"重试+幂等"配对图——幂等生产者去重机制 + 非幂等重试的风险警示并排。

---

## 通用写作纪律重申

1. 每个 slug 的 `@cmp` 对比图配文，必须清楚点出"同一模式下不同真实项目的取舍差异"，不是简单并列介绍。
2. 凡本清单标注"概念参考/未源码级核实"的（Dynamo/Cassandra、nginx limit_req 精确公式），最终 HTML 图文中必须原样保留这个诚实标注，不能在撰写过程中把它写"实"了。
3. client-go 限流务必写成"指数退避+令牌桶组合"（`NewTypedMaxOfRateLimiter`），这是本清单相对原计划表述的关键修正点，容易被无意中简化错。
4. etcd Lease 记得提一句 `Checkpointer` 持久化 TTL 的细节，这是比"纯内存计时器"更准确的描述。
