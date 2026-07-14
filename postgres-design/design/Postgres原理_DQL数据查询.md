# PostgreSQL 核心原理 · DQL 数据查询（SELECT）

> **定位**：读数据接口主线，骨架 = backend 内 `Parser → Analyze → Rewrite → Plan → Execute`（`tcop/postgres.c` `exec_simple_query:1030`）。强依赖**查询优化器**（选计划）、**执行引擎**（volcano 执行）、**索引方法**与**存储引擎**（读取），跨事务时依赖**事务与 MVCC**（快照可见性）。核实基准：官方源码 `postgres/src`。

## 一、生命周期总览：五段流水线

![DQL 生命周期](Postgres原理_DQL_01总览.svg)

一条 SELECT 在单个 backend 内顺序走五段：**Parser**（SQL→raw parse tree，纯语法，`:617`）→ **Analyze**（名称/类型绑定查系统目录→query tree，`:1213`）→ **Rewrite**（视图/规则展开、RLS 注入）→ **Plan/Optimize**（CBO 选最省代价计划→plan tree，`:1216`）→ **Execute**（Portal 逐行拉取，`PortalRun:1297`）。前四段是编译（纯 CPU，可被 prepared statement 缓存复用），第五段才真正读数据。全库用同一贯穿示例 `SELECT u.name, count(o.id) FROM users u JOIN orders o ON o.user_id=u.id WHERE u.city='NYC' GROUP BY u.name ORDER BY 2 DESC LIMIT 10;`。

---

## 二、volcano / pull 执行模型

![volcano 执行](Postgres原理_DQL_02volcano执行.svg)

执行是**火山模型**：每个 plan node 是一个迭代器（`ExecProcNode`），顶层反复向下 pull "要一行"、数据自底向上逐行返回（tuple-at-a-time）。性质：统一迭代器接口（Init/Proc/End，组合任意算子树，实现简洁）、按需拉取天然流水线（LIMIT 拿够就停、上游不必算完）。代价是每行每 node 一次函数调用——逐行开销大，OLAP 大扫描不如列存向量化（对照 DuckDB 的 push）；缓解手段：JIT 编译表达式（`jit/`）、并行查询（Gather + worker）、Memoize 缓存重复子查询。

---

## 深化 · 扫描方法选择

![扫描方法](Postgres原理_DQL_03扫描方法.svg)

优化器按选择率与代价挑读表方式（`executor/node*scan.c`）：**Seq Scan**（选择率高/表小/无索引，顺序读所有 page）、**Index Scan**（选择率低，走索引定位再回堆表取行，含随机 IO）、**Index-Only Scan**（查询列全在索引里、经 Visibility Map 确认可见则免回表，最快）、**Bitmap Heap Scan**（中等选择率/多索引组合，先建 TID 位图再按 page 有序回表，减少随机 IO）。关键是选择率：命中占比越低越倾向索引、越高越倾向全表顺序读，由 `random_page_cost`/`seq_page_cost` 与统计权衡。

---

## 深化 · 三种 Join 算法

![Join 算法](Postgres原理_DQL_04Join算法.svg)

优化器为每种 Join 算代价选最小者：**Nested Loop**（外表每行探内表，适合外表小 + 内表有索引，可配 Memoize 缓存）、**Merge Join**（两表按 key 排序后双指针归并，适合已有序或结果需有序）、**Hash Join**（小表 build hash、大表 probe，等值大 Join 主力，超 work_mem 分批落盘）。经验对应（外小内有索引→NL、有序→Merge、大表等值→Hash）只是常见结果，实际以代价为准；Join 顺序由 DP/GEQO 决定（见"查询优化器"）。

---

## 拓展 · 常见 plan node

| 类别 | node | 说明 |
|---|---|---|
| 扫描 | SeqScan / IndexScan / IndexOnlyScan / BitmapHeapScan | 读表 |
| 连接 | NestLoop / MergeJoin / HashJoin | 连接两表 |
| 聚合 | Agg（Hash/Group）/ WindowAgg | 分组/窗口 |
| 排序/限量 | Sort / IncrementalSort / Limit | 排序、取前 N |
| 并行 | Gather / GatherMerge | 汇聚并行 worker 结果 |
| 其他 | Material / Memoize / Append / ModifyTable | 物化/缓存/合并/写 |

---

## 调优要点（关键开关）

- `EXPLAIN (ANALYZE, BUFFERS)`：看真实计划、行数估计误差与缓冲命中——调优第一手段。
- `work_mem`：排序/Hash 的内存上限；不够则落盘，影响 Join/Sort/Agg 选择。
- `random_page_cost`/`seq_page_cost`：SSD 上调低 random_page_cost 使索引更受青睐。
- `max_parallel_workers_per_gather`：开并行查询分摊大扫描。
- 保持统计新鲜（`ANALYZE`/autovacuum），否则估计失真选坏计划。

---

## 常见误区与工程要点

- **以为有索引就一定走索引**：选择率高时全表顺序读更省；优化器按代价选。
- **忽视统计陈旧**：estimate 依赖 pg_statistic，数据大改后不 ANALYZE 会选坏计划。
- **work_mem 设太大又高并发**：每个 Sort/Hash 节点各占 work_mem，并发下可能爆内存。
- **把 volcano 当向量化**：逐行执行，纯分析大扫描性能不如列存引擎。

---

## 一句话总纲

**DQL 在 backend 内经 Parser→Analyze→Rewrite→Plan(CBO)→Execute 五段流水线：前四段编译成 plan tree（可缓存），执行用 volcano/pull 火山模型逐行拉取；读表按选择率在 Seq/Index/IndexOnly/BitmapHeap 间选、连接按代价在 NestLoop/Merge/Hash 间选、Join 顺序由 DP+GEQO 定，逐行开销靠 JIT、并行查询与 Memoize 缓解——一切选择以优化器的代价估计为准。**
