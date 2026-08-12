# Hive 核心原理 · 支撑主线 · 存储与序列化

> **定位**：存储与序列化是 Hive 的**底座能力域之二**——它回答一个根本问题：「一张表在 HDFS/对象存储里到底是一堆什么样的字节，引擎怎么把这堆字节读成行、把行写回字节」。Hive 不自管存储格式，而是把「怎么读写字节」抽象成三个**可插拔契约**：`SerDe`（行 ⇄ 字节）、`InputFormat`/`OutputFormat`（切分 + 读写文件）、`StorageHandler`（把非 HDFS 存储系统整体接进来）。这层解耦让 Hive 能同时吞下 TextFile、ORC、Parquet，乃至 HBase、Iceberg、Kafka。

## 一、原型：为什么读写字节要抽成三层可插拔契约

一体化数据库把存储格式焊死在引擎里（PostgreSQL 的堆表就是 PostgreSQL 定义的页格式）。Hive 反其道而行——**表的物理格式是元数据里的一组可替换类名**：

- **SerDe（Serializer/Deserializer）**：管**单行**的 行对象 ⇄ 字节 双向转换。它不关心文件怎么切、怎么读，只负责「给我一条 `Writable`，我还你一个结构化行对象」和反向。
- **InputFormat / OutputFormat**：继承 Hadoop MapReduce 的同名契约，管**文件级**——怎么把目录里的文件切成 split、怎么给每个 split 造 `RecordReader` 逐条吐 `Writable`。
- **StorageHandler**：管**整个存储系统级**——当数据根本不在 HDFS（如 HBase、Kafka、JDBC、Iceberg）时，用它把 InputFormat + OutputFormat + SerDe + MetaHook **捆绑**成一套，让引擎无感知地当成一张表读写。

> 一句话：**表的物理形态 = 元数据里 `SerDe + InputFormat + OutputFormat`（可选 `StorageHandler`）这组类名；换格式 = 换类名，引擎代码一行不改。**

---

## 二、三层契约的职责边界

| 契约 | 粒度 | 输入 → 输出 | 典型实现 |
|---|---|---|---|
| SerDe | 单行 | `Writable` ⇄ 行对象（配 ObjectInspector 解释字段） | `LazySimpleSerDe`（文本延迟解析）、`OrcSerde`、`AvroSerDe` |
| InputFormat | 文件/split | 目录 → `InputSplit[]` → `RecordReader` 逐条 `Writable` | `HiveInputFormat`、`OrcInputFormat` |
| OutputFormat | 文件 | 行 → 落盘字节 | `OrcOutputFormat`、`HiveIgnoreKeyTextOutputFormat` |
| StorageHandler | 存储系统 | 捆绑上述三者 + MetaHook | `HBaseStorageHandler`、`KafkaStorageHandler`、Iceberg |

**ObjectInspector 是关键配角**：SerDe 反序列化出的行对象并不是 POJO，而是一个「不透明句柄 + 一个能解释它的 ObjectInspector」。引擎拿 OI 去问「第 3 个字段是什么类型、值是多少」，从而避免为每种 SerDe 写一套取值代码——这是 `LazySimpleSerDe` 能「延迟解析」（用到哪列才解析哪列）的基础。

---

## 三、HiveInputFormat：一张表混装多种格式的多路复用器

Hive 允许**同一张表的不同分区用不同存储格式**（老分区 Text、新分区 ORC）。承接这个能力的是 `HiveInputFormat`——它本身不读文件，而是一个**按路径分发的多路复用器**：

| 阶段 | 做什么 |
|---|---|
| `getSplits` | 遍历输入路径，查 `pathToPartitionInfo` 得到每个路径**真正**的 InputFormat 类，委托给它切 split |
| `getRecordReader` | 拿到 split 后，同样按路径查出真实 InputFormat，`getInputFormatFromCache` 复用实例，造出真正的 RecordReader |
| `getInputFormatFromCache` | 按类名缓存 InputFormat 实例，避免每个 split 反射 new |

这就是为什么 Hive 表能「一半 ORC 一半 Text」还能一条 SQL 扫完——`HiveInputFormat` 在 split 层就按分区元数据把活派给了对的格式实现。

---

## 四、ORC：Hive 原生列存 + ACID 的承载者

ORC（Optimized Row Columnar）是 Hive 的一等公民列存格式，也是 ACID 事务表的物理底座。

**三种 split 策略**（`OrcInputFormat.SplitStrategyKind`），按文件数量/大小自适应选择，平衡「切分开销」与「并行度」：

| 策略 | 适用 | 特点 |
|---|---|---|
| `BI` | 少量大文件、交互式 | 按文件粒度切，省去读 footer 的开销，启动快 |
| `ETL` | 大量文件、批处理 | 读每个文件 footer 拿 stripe 边界，切得更细，并行度高 |
| `HYBRID` | 默认自适应 | 文件多时退化到 ETL，文件少时用 BI |

**ACID 文件布局**：ORC 事务表的目录由三类前缀目录组成，读时合并（详见事务一致性篇）：

- `base_*`：某次 major compaction 后的全量基线。
- `delta_*`：一批事务的插入/更新增量。
- `delete_delta_*`：删除标记（按行 ROW__ID 定位）。

---

## 五、表类型与存储格式对比

**managed vs external**：类型字段存在元数据 Table 对象里——managed 表 DROP 连数据目录一起删；external 表 DROP 只删元数据、保留目录。选型本质是「谁拥有数据生命周期」。

| 格式 | 存储 | 压缩/谓词下推 | 典型场景 |
|---|---|---|---|
| ORC | 列存 | 强（stripe/row-group 索引、内建统计） | Hive 数仓主力、ACID 表 |
| Parquet | 列存 | 强（生态通用） | 跨引擎共享（Spark/Trino） |
| TextFile | 行存 | 弱（需外部 gzip/bzip2） | 落地/调试/外部导入 |
| SequenceFile | 行存二进制 | 中（块压缩） | 中间结果 |
| RCFile | 早期列存 | 中 | ORC 前身，遗留 |
| Avro | 行存 | 中（自带 Schema） | Schema 演进场景 |

建表用 `STORED AS ORC`，或显式三段 `INPUTFORMAT ... OUTPUTFORMAT ... ROW FORMAT SERDE ...`——后者正是往元数据里写那组类名。

---

## 六、分区与分桶：目录裁剪 + 哈希分桶

两者都是「把数据按 key 预先物理组织，换查询期少扫」的手段，但机制不同：

- **分区（Partition）**：分区列的每个值 = 一个**子目录**（`/dt=2026-01-01/`）。编译期把 `WHERE dt=...` 转成**目录裁剪**（只扫命中子目录），配合 HMS 的 `get_partitions_by_filter` 在元数据侧就筛掉无关分区。分区列**不进数据文件**，只体现在目录名。
- **分桶（Bucket）**：按分桶列 `hash % num_buckets` 把行散到固定数量的文件（`bucket_00000`…`bucket_0000n`）。桶数固定，便于**分桶 join（bucket map join）** 和**采样**。ACID 表的 ROW__ID 里编入桶号，由 `BucketCodec` 编解码。

> 误区：分区数不是越多越好——百万级分区会把 HMS 背后的 RDBMS 打爆（见元数据服务篇调优）。

---

## 七、调优要点（关键开关）

- **优先 ORC + 向量化**：`hive.vectorized.execution.enabled=true` 让引擎按 1024 行一批走向量化算子，配 ORC 列存收益最大。
- **split 策略选对**：交互式少文件用 `BI`、批处理大量文件用 `ETL`，默认 `HYBRID` 通常够用；文件太碎先做 compaction 而非硬切。
- **谓词下推到存储层**：ORC/Parquet 支持 `hive.optimize.index.filter`，把过滤条件下推到 stripe/row-group 索引，跳过整块。
- **分区裁剪比分桶更常用**：先用分区把大扫描切小，分桶只在稳定 join key + 固定桶数时才划算。
- **别用 TextFile 存大表**：无列裁剪、无谓词下推、无内建压缩，全表扫描代价极高。

---

## 八、常见误区与工程要点

- **SerDe ≠ 存储格式**：SerDe 只管单行编解码，「切文件」是 InputFormat 的活；一个格式（如 ORC）是「OrcSerde + OrcInputFormat + OrcOutputFormat」三件套。
- **Hive 不「拥有」格式**：它只在元数据里存类名，运行期反射加载；这正是能接 HBase/Kafka/Iceberg 的原因——它们各自提供一套 StorageHandler。
- **分区列不在文件里**：分区值来自目录名，误以为「文件里有 dt 列」会导致 schema 对不上。
- **external 表删表不删数据**：把 external 当 managed 用（指望 DROP 清目录）会留下孤儿数据。

---

## 源码锚点（用户分支核实）

> 均已在用户工作区 `/Users/zhangdongdong92/workdir/hive` grep 核实。

- **SerDe 抽象基类**：`serde/src/java/org/apache/hadoop/hive/serde2/AbstractSerDe.java:45`（`abstract class AbstractSerDe implements Deserializer, Serializer`）；`serialize` @ `:144`、`deserialize` @ `:149`。
- **文本延迟 SerDe**：`serde/src/java/org/apache/hadoop/hive/serde2/lazy/LazySimpleSerDe.java:79`（`extends AbstractEncodingAwareSerDe`）；`doDeserialize` @ `:163`、`doSerialize` @ `:208`。
- **字段解释器**：`serde/src/java/org/apache/hadoop/hive/serde2/objectinspector/ObjectInspector.java:43`（`interface ObjectInspector extends Cloneable`）。
- **ORC 行编解码**：`ql/src/java/org/apache/hadoop/hive/ql/io/orc/OrcSerde.java:55`（`class OrcSerde extends AbstractSerDe implements SchemaInference`）。
- **多路复用 InputFormat**：`ql/src/java/org/apache/hadoop/hive/ql/io/HiveInputFormat.java:109`（`class HiveInputFormat<K,V>`）；`getInputFormatFromCache` @ `:402`、`getRecordReader` @ `:423`、`getSplits` @ `:789`。
- **ORC InputFormat 与 split 策略**：`ql/src/java/org/apache/hadoop/hive/ql/io/orc/OrcInputFormat.java:173`（`class OrcInputFormat`）；`enum SplitStrategyKind{HYBRID,BI,ETL}` @ `:183`。
- **ACID 目录前缀**：`ql/src/java/org/apache/hadoop/hive/ql/io/AcidUtils.java:148`（`class AcidUtils`）；`BASE_PREFIX` @ `:151`、`DELTA_PREFIX` @ `:159`、`DELETE_DELTA_PREFIX` @ `:160`。
- **分桶编码**：`ql/src/java/org/apache/hadoop/hive/ql/io/BucketCodec.java:28`（`enum BucketCodec`）。
- **可插拔存储契约**：`ql/src/java/org/apache/hadoop/hive/ql/metadata/HiveStorageHandler.java:104`（`interface HiveStorageHandler extends Configurable`）；`getInputFormatClass` @ `:112`、`getOutputFormatClass` @ `:117`、`getSerDeClass` @ `:122`、`getMetaHook` @ `:128`。

---

## 一句话总纲

**Hive 把「一堆字节如何变成表」抽成三层可插拔契约——SerDe 管单行编解码、InputFormat/OutputFormat 管文件切分读写、StorageHandler 把整个外部存储系统捆绑接入；ORC 作为原生列存承载 ACID 的 base/delta 布局与三种 split 策略，分区靠目录裁剪、分桶靠哈希取模；换格式换存储只是换元数据里的一组类名，引擎代码零改动，这正是 Hive 存算分离数仓门面的存储底座。**