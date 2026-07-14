# Hudi 原理 · 支撑主线 · 写入与索引

> **定位**：属"写入能力域"——Hudi 高效 upsert 的关键。管写入流程:索引 tag(记录键→文件组)→ bucket 路由(UPDATE/INSERT)→ 写 handle。索引是 Hudi 相对 Iceberg(append 导向)的核心差异。依赖【时间线】开 instant、【表类型】选 handle。源码基准 **Hudi(1dfbdcb)**(`hudi-client/`)。

Hudi 为 upsert 而生,难点在"来一批记录,怎么知道每条该更新哪个已有文件、还是新插入"?靠**索引**:`HoodieIndex.tagLocation` 查记录键的已有位置——命中(已存在)→ 路由到那个文件组做 UPDATE,未命中 → INSERT 到新/小文件。这让 upsert 不用全表扫。理解"索引 tag → bucket 路由 → 写"就懂了 Hudi 的写入。

---

## 一、upsert 流程:tag → 路由 → 写

![Hudi upsert 流程](Hudi原理_写入_01upsert.svg)

`BaseHoodieWriteClient.upsert(records, instantTime)`(`BaseHoodieWriteClient.java:468`)的生命周期:

1. **开 instant**:`startCommit` 在时间线分配 instant(`:1088`),`preWrite` 预处理(`:582`)。
2. **索引 tag**:`HoodieIndex.tagLocation(records, context, table)`(`HoodieIndex.java:80`)给每条记录标位置——UPSERT/DELETE 必须 tag(`:141`)。命中已有键 → 带上其文件组位置。
3. **bucket 路由**:`BucketType { UPDATE, INSERT }`(`BucketType.java:21`)——已 tag(键已存在)→ UPDATE bucket(路由到其现有文件组);未 tag → INSERT bucket。小文件处理靠 `SmallFile`/`Partitioner`(把插入塞进未满的小文件)。
4. **写**:COW insert → `HoodieCreateHandle`(CREATE)、COW update → `HoodieWriteMergeHandle`(MERGE 重写)、MOR → `HoodieAppendHandle`(APPEND log)。
5. **更新索引**:写后 `HoodieIndex.updateLocation`(`:88`)记最终位置。

---

## 二、索引类型:记录键 → 文件组

![Hudi 索引类型](Hudi原理_写入_02索引.svg)

`HoodieIndex`(`HoodieIndex.java:40`)是"决定 uuid 映射的索引基类",`IndexType`(`:161`):

- **BLOOM / GLOBAL_BLOOM**:`HoodieBloomIndex`——"基于布隆过滤器,每个 parquet 文件在元数据里含其 row_key 布隆过滤器"(`HoodieBloomIndex.java:59`)。查键时用布隆快速排除 + 键范围剪枝。分区内(BLOOM)vs 跨表(GLOBAL)。
- **SIMPLE / GLOBAL_SIMPLE**:`HoodieSimpleIndex`——"把 incoming 记录与存储上提取的键做精简 join"(分区内 vs 跨表)。
- **BUCKET**:`HoodieBucketIndex`——按 `numBuckets` + 索引键字段哈希定位文件组(`HoodieBucketIndex.java:53`)。`BucketIndexEngineType { SIMPLE, CONSISTENT_HASHING }`(一致性哈希仅 MOR、可 resize)。
- **RECORD_LEVEL_INDEX / GLOBAL**:把记录键→位置映射存 Hudi 元数据表,"支持分片达极高规模"(`:203`)。

索引能力 flag 驱动决策:`isGlobal()`、`canIndexLogFiles()`("可否把插入直接送 log")、`isImplicitWithStorage()`(`:111`)。

---

## 三、写 handle:COW 重写 vs MOR 追加

![Hudi 写 handle](Hudi原理_写入_03handle.svg)

路由后按类型 + bucket 选 handle:

- **HoodieCreateHandle**(COW 新建,IOType=CREATE):新文件组写全新 base 文件。
- **HoodieWriteMergeHandle**(COW 更新,IOType=MERGE):逐行合并到已有 base 文件、产新版本(`HoodieWriteMergeHandle.java:71`)——工作例 rec1_1+rec1_2→rec1_2。
- **HoodieAppendHandle**(MOR,IOType=APPEND):追加到 log 文件(`HoodieAppendHandle.java:68`);`writeRecord` 判 `isUpdateRecord`/删除,`writeInsertAndUpdate`(`:353`)。

每个 handle 写前创建 **marker 文件**(`getIOType()`,标记本次写的 IOType,`HoodieWriteHandle.java:204`)——用于失败清理(回滚时按 marker 删部分写的文件)。

---

## 拓展 · 写入与索引关键结构一览

| 结构 | 定义 | 职责 |
|---|---|---|
| BaseHoodieWriteClient.upsert | `client/BaseHoodieWriteClient.java:468` | upsert 生命周期 |
| HoodieIndex.tagLocation | `index/HoodieIndex.java:80` | 记录键→已有位置标记 |
| BucketType | `table/action/commit/BucketType.java:21` | UPDATE / INSERT 路由 |
| HoodieBloomIndex | `index/bloom/HoodieBloomIndex.java:59` | 布隆过滤器索引 |
| HoodieBucketIndex | `index/bucket/HoodieBucketIndex.java:53` | 哈希桶索引 |
| HoodieWriteMergeHandle / AppendHandle | `io/` | COW 重写 / MOR 追加 |

## 调优要点（关键开关）

- **索引选型**:随机 upsert 用 Bloom(默认);已知分桶用 Bucket(免查);超大规模用 RECORD_LEVEL(元数据表);全局唯一用 GLOBAL_*。
- **小文件合并**:`hoodie.parquet.small.file.limit` 让插入塞进小文件,减少碎片。
- **索引键范围剪枝**:Bloom 索引配合键范围(min/max)先剪分区/文件,减少布隆检查。
- **canIndexLogFiles**:MOR 下某些索引可把插入直送 log,提写吞吐。

## 常见误区与工程要点

- **误区:upsert 要全表扫找记录。** 不。索引把记录键映射到文件组,直接路由——这是 Hudi 高效 upsert 的核心。
- **误区:Bloom 索引精确。** 布隆有假阳性(需再验),但能快速排除大部分不含键的文件;配合键范围剪枝更准。
- **误区:所有索引都跨表唯一。** 分区内(BLOOM/SIMPLE/BUCKET)vs 跨表(GLOBAL_*);全局索引开销大,按需选。
- **误区:marker 文件是数据。** marker 只标"本次写产生了哪些文件"(带 IOType),用于失败回滚清理,非数据。
- **归属提醒**:写用哪个 handle 由【表类型 COW/MOR】定;写动作的 instant 在【时间线】;并发写的冲突检测在【并发控制】;写后的 MOR log 读合并在【MoR 读合并】。

## 一句话总纲

**Hudi 高效 upsert 靠索引:BaseHoodieWriteClient.upsert 开 instant→HoodieIndex.tagLocation 查记录键的已有位置(命中带文件组位置)→按 BucketType 路由(已 tag→UPDATE 到现有文件组、未 tag→INSERT 到小/新文件)→按表类型选 handle(COW CreateHandle/MergeHandle 重写、MOR AppendHandle 追加 log)→updateLocation 记最终位置;索引类型 Bloom(每 parquet 存 row_key 布隆)/Simple(join)/Bucket(哈希)/RECORD_LEVEL(元数据表)决定映射效率,这是 Hudi 相对 append 导向的 Iceberg 的核心差异。**
