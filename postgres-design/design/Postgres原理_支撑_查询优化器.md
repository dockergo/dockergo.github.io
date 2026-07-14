# PostgreSQL 核心原理 · 支撑能力域 · 查询优化器

> **定位**：计算能力域的规划侧。基于代价（CBO）为查询生成候选路径、按代价选最优，再转成 plan tree 交执行器。为 **DQL** 定"怎么算最省"，依赖**索引方法**（候选扫描）、**存储引擎**（统计）。核实基准：官方源码 `postgres/src`。

## 一、代价与路径生成

![代价与路径](Postgres原理_优化_01代价与路径.svg)

CBO 主流程（`make_one_rel`，`allpaths.c:183`）：① 单表路径（为每表列候选 seq/index/bitmap 扫描各算代价）→ ② Join 定序 + 算法（枚举连接顺序 × Join 算法，DP/GEQO）→ ③ 加顶层算子（agg/sort/limit/window）→ ④ 选最小代价路径转成 plan tree。**代价模型**：代价 = IO + CPU 加权和（`seq_page_cost`/`random_page_cost`/`cpu_tuple_cost`…），关键输入是**基数估计**（来自 `pg_statistic`：直方图、MCV、n_distinct）——估准选对、估错选坏，统计陈旧是坏计划头号原因。统计从 ANALYZE 采样收集（autovacuum 顺带或手动）存进 pg_statistic，扩展统计（`CREATE STATISTICS`）处理多列相关性。

---

## 二、Join 定序：DP vs GEQO

![Join 定序](Postgres原理_优化_02Join定序.svg)

按待连接表数二选一（`allpaths.c:3915`）：**表少（< geqo_threshold，默认 12）→ 精确 DP**（`standard_join_search:3918`，动态规划按 join level 逐层构建、最优子结构复用，搜索空间内保证最优但复杂度随表数指数增长，适合绝大多数查询）；**表多（≥ threshold）→ GEQO 遗传算法**（把 Join 顺序编码成染色体、选择/交叉/变异迭代进化，不保证最优但规划时间可控，避免 DP 在大量表时爆炸）。对照 DuckDB："小 join DP、大 join 近似"是同一思路，算法不同（GEQO 遗传 vs 贪心）。

---

## 拓展 · 优化器组件

| 组件 | 职责 | 锚点 |
|---|---|---|
| make_one_rel | 路径生成主流程 | `optimizer/path/allpaths.c:183` |
| standard_join_search | DP Join 定序 | `optimizer/path/allpaths.c:3918` |
| geqo | 遗传 Join 定序 | `optimizer/geqo/` |
| cost_* | 各算子代价函数 | `optimizer/path/costsize.c` |
| createplan | path → plan tree | `optimizer/plan/createplan.c` |
| pg_statistic | 列统计 | `catalog`（由 ANALYZE 填） |

---

## 调优要点（关键开关）

- 保持统计新鲜（autovacuum ANALYZE / 手动 ANALYZE），是选对计划的前提。
- `random_page_cost`（SSD 调低）影响索引 vs 顺序扫的偏好。
- `geqo_threshold` / `geqo`：多表 Join 规划太慢时调整。
- 多列相关性导致估计偏差时用 `CREATE STATISTICS` 扩展统计。
- `EXPLAIN ANALYZE` 对比估计行数与实际行数，定位估计误差。

---

## 常见误区与工程要点

- **怪优化器选错，实为统计陈旧**：先 ANALYZE 再评估。
- **迷信 hint**：PostgreSQL 无查询 hint（设计取向）；靠统计+参数+改写引导。
- **忽视多列相关性**：`WHERE a AND b` 相关列的独立性假设会低估，用扩展统计。
- **join 表极多规划慢**：GEQO 生效，可调 geqo_threshold 或拆查询。

---

## 一句话总纲

**查询优化器是基于代价的 CBO：make_one_rel 为每表生成候选扫描路径、按 DP（表少，精确最优）或 GEQO（表多，遗传近似）枚举 Join 顺序与算法、加顶层算子后选最小代价路径转 plan tree；代价 = IO+CPU 加权、核心输入是来自 pg_statistic 的基数估计——统计新鲜度决定计划好坏，PostgreSQL 无 hint、靠统计与参数引导。**
