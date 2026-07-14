# PostgreSQL 核心原理 · 支撑能力域 · 事务与 MVCC

> **定位**：保障、灵魂能力域之一。tuple 多版本 + 快照可见性 + VACUUM 回收，是读写不互阻塞与正确性的根基。被 **DML**（写造版本）、**DQL**（快照读）依赖，死元组回收依赖后台 **VACUUM**。核实基准：官方源码 `postgres/src`。

## 一、可见性：快照 + xmin/xmax

![MVCC 可见性](Postgres原理_MVCC_01可见性.svg)

查询开始时取**快照**（`GetSnapshotData`，`procarray.c`）：`xmin`（最老仍活跃 xid，小于它的都已定论）、`xmax`（下一个未分配 xid，≥它的都还没开始）、`xip[]`（拍照时仍进行中的 xid）。一行 tuple 是否可见看它的 `t_xmin`（谁插入）与 `t_xmax`（谁删除，`HeapTupleSatisfiesMVCC`，`heapam_visibility.c:917`）：① 插入事务已提交且对快照可见？否（未提交/在 xip/≥xmax）→ 不可见；② 删除事务已提交且对快照可见？是 → 已删不可见，否/为 0 → 可见。效果：读不阻塞写、写不阻塞读，同行多版本并存供不同快照读。xid 提交状态查 CLOG，首次判定后写回 tuple 的 infomask hint bits 省后续查询。

---

## 二、隔离级别与 VACUUM

![隔离与 VACUUM](Postgres原理_MVCC_02隔离与VACUUM.svg)

三种隔离级别就是快照粒度不同：**Read Committed**（默认，每条语句取新快照）、**Repeatable Read**（事务级快照，防不可重复读）、**Serializable**（SSI 可串行化快照隔离，检测读写依赖环冲突回滚）。MVCC 的代价是**死元组堆积**——UPDATE/DELETE 留旧版本，无快照需要后即成死元组，不回收则表/索引膨胀、扫描变慢；且 xid 32 位会回卷，老 tuple 不冻结会误判可见性触发强制停写。**VACUUM**（autovacuum 自动，`vacuumlazy.c`）：① 回收死元组与死索引项（空间可复用）② 冻结足够老的事务防 XID 回卷 ③ 更新 FSM/VM + 顺带 ANALYZE；`VACUUM FULL` 真正缩文件但锁表慎用。关掉 autovacuum 是生产大忌。

---

## 拓展 · MVCC 组件

| 组件 | 职责 | 锚点 |
|---|---|---|
| GetSnapshotData | 取快照 | `storage/ipc/procarray.c` |
| HeapTupleSatisfiesMVCC | 可见性判定 | `access/heap/heapam_visibility.c:917` |
| CLOG | xid 提交状态 | `access/transam/clog.c` |
| VACUUM | 回收/冻结 | `access/heap/vacuumlazy.c` |
| autovacuum | 后台触发 VACUUM/ANALYZE | `postmaster/autovacuum.c` |

---

## 调优要点（关键开关）

- 保持 autovacuum 开启并按更新频率调（`autovacuum_vacuum_scale_factor` 等）。
- 长事务会压住"最老快照"阻止死元组回收——避免长事务/未关闭的空闲事务。
- 监控膨胀与年龄（`age(relfrozenxid)`），临近回卷阈值前加强 VACUUM。
- 高更新表配 fillfactor 提高 HOT，减少版本与索引膨胀。

---

## 常见误区与工程要点

- **UPDATE 就地改**：实为造版本；死元组靠 VACUUM 回收。
- **长事务无害**：它让 VACUUM 无法回收其后产生的死元组，膨胀失控。
- **VACUUM 只是清垃圾**：它还冻结防 XID 回卷、维护 FSM/VM——是正确性与性能双关。
- **Serializable 免费**：SSI 有额外跟踪开销与序列化失败重试成本。

---

## 一句话总纲

**事务与 MVCC 用快照（xmin/xmax/xip）+ 每行 tuple 的 t_xmin/t_xmax 判可见性（HeapTupleSatisfiesMVCC），实现读写互不阻塞与三种隔离级别（RC/RR/Serializable）；代价是 UPDATE/DELETE 留下的死元组，由 autovacuum 后台 VACUUM 回收空间、冻结老事务防 XID 回卷、维护 FSM/VM——长事务会阻止回收、关闭 autovacuum 会导致膨胀与回卷，都是生产大忌。**
