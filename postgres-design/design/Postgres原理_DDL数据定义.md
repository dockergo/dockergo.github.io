# PostgreSQL 核心原理 · DDL 数据定义（CREATE / ALTER / DROP）

> **定位**：定义对象接触面主线，骨架 `ProcessUtility 分派 → 取锁 → 改系统目录表行 → 建物理文件/记依赖/写 WAL`。以**系统目录**（元数据即表）为主轴，事务性依赖**事务与 MVCC**、并发保护依赖**并发控制与锁**。核实基准：官方源码 `postgres/src`（commit 572c3b2）。

## 一、总览：定义对象 = 改系统目录表的行

![DDL 总览](Postgres原理_DDL_01总览.svg)

DDL 语句不进 Planner/Executor，而经 utility 通道分派：`ProcessUtility`（`tcop/utility.c:504`）→ `standard_ProcessUtility`（`tcop/utility.c:548`），简单命令就地处理、复杂命令走 `ProcessUtilitySlow`（`tcop/utility.c:1094`）再分派到 `commands/` 各处理器（如 `DefineRelation`，`commands/tablecmds.c:818`；`DefineIndex`，`commands/indexcmds.c:555`）。

处理链四步：① `ProcessUtility` 分派 → ② 取锁防并发冲突（如 ALTER 取 `AccessExclusiveLock`=8，`storage/lockdefs.h:45`）→ ③ 改系统目录表的行（`CatalogTupleInsert`，`catalog/indexing.c:233`；`CatalogTupleUpdate`，`:313`——就是普通 heap 表写，同样走 MVCC/WAL）→ ④ 建物理文件、`recordDependencyOn`（`catalog/pg_depend.c:51`）记依赖、写 WAL；COMMIT 时目录变更随事务原子生效。

三个特点：**事务性 DDL**（CREATE/ALTER/DROP 可与 DML 一起原子提交/回滚，少数如 `CREATE INDEX CONCURRENTLY`、`CREATE DATABASE` 例外）、**目录即普通表**（改元数据就是往 pg_class 写行，复用 tuple 版本/hint bits/VACUUM 那一整套）、**锁保护**（DDL 常取重锁、可能阻塞读写，生产变更须先评估锁影响）。

---

## 二、系统目录：元数据本身就是表

![系统目录](Postgres原理_DDL_02系统目录.svg)

核心系统目录都是普通 heap 表：`pg_class`（所有表/索引/视图/序列）、`pg_attribute`（列）、`pg_index`（索引定义）、`pg_statistic`（优化器用的列统计）、`pg_depend`（对象依赖，支撑 DROP CASCADE）、`pg_proc`/`pg_type`（函数/类型）、`pg_authid`/`pg_class.relacl`（角色与权限）。妙处：目录是表 → DDL 复用 heap 写 + MVCC + WAL，查元数据就是 `SELECT`（可 `SELECT * FROM pg_class`）。

因每次查询编译都频繁读目录，用每 backend **私有**的两级缓存：**syscache**（按 key 缓存单条目录行，如按 oid 查 pg_class）与 **relcache**（缓存一张表的完整描述 `RelationData`：列、索引、约束、访问方法）。DDL 提交后经**共享失效消息**（shared invalidation queue）广播，让所有 backend 把相关 syscache/relcache 条目失效、下次访问重建，从而看到新定义——这是"目录改了、别的连接立刻可见"的机制。

---

## 深化 · DDL 的锁级别与失败路径

不同 DDL 取的锁级别决定了它对并发读写的影响（相容矩阵在 `storage/lockdefs.h`，`AccessShareLock=1`（SELECT）… `AccessExclusiveLock=8`（ALTER/DROP/VACUUM FULL））：

- **AccessExclusiveLock**（多数 ALTER TABLE 子命令、DROP TABLE、TRUNCATE、VACUUM FULL）：与一切锁互斥，会**排队等待并阻塞该表全部读写**；且 DDL 排队时会挡住它后面所有新查询——一次不当 ALTER 可瞬间雪崩。
- **ShareUpdateExclusiveLock**（`CREATE INDEX CONCURRENTLY`、`ANALYZE`、普通 VACUUM）：与读写兼容，只互斥同类维护——生产加索引应优先它。
- **失败与回滚**：普通 DDL 在事务里失败会随事务整体回滚（因目录变更也是 MVCC tuple）；但 `CREATE INDEX CONCURRENTLY` 是**非事务**多阶段构建，中途失败会留下一个 `INVALID` 索引（`pg_index.indisvalid=false`），需手动 DROP 重建——这是"事务性 DDL"的显著例外。
- **依赖阻断**：裸 `DROP` 一个被别的对象依赖的对象时，`pg_depend` 检查（`RemoveRelations`，`commands/tablecmds.c:1597` → `performDeletion`，`catalog/dependency.c:279`；批量走 `performMultipleDeletions:388`）会报错，需 `CASCADE` 递归删或先删依赖方。
- **建表的物理落地**：`DefineRelation` 内经 `heap_create_with_catalog`（`catalog/heap.c:1140`）既往 pg_class/pg_attribute 写目录行、又建物理文件，两者在同一事务内一致提交。
- **缓存失效广播**：DDL 提交时经 `CacheInvalidateHeapTuple`（`utils/cache/inval.c:1568`）登记失效消息，其他 backend 在拿锁时 `AcceptInvalidationMessages`（`inval.c:930`）消费、把过期的 syscache/relcache 条目清掉——这是"改了目录、别的连接下次访问就看到新定义"的机制。

---

## 拓展 · 常见 DDL 与目录落点

| DDL | 主要目录变更 | 备注 |
|---|---|---|
| CREATE TABLE | pg_class + pg_attribute + 建文件 | 事务性 |
| CREATE INDEX | pg_class + pg_index + 建索引文件 | CONCURRENTLY 非事务、不阻塞写 |
| ALTER TABLE ADD COLUMN | pg_attribute（多数不重写数据） | 加 volatile 默认值可能全表重写 |
| DROP ... CASCADE | 删目录行、按 pg_depend 递归 | RESTRICT 有依赖则拒绝 |
| CREATE EXTENSION | 注册一组对象 | 可插拔能力 |

---

## 调优要点（关键开关）

- 生产加索引用 `CREATE INDEX CONCURRENTLY`：取 ShareUpdateExclusiveLock、不阻塞写（代价是更慢、非事务）。
- 评估 ALTER 的锁级别：取 AccessExclusiveLock 的 ALTER 会短暂阻塞全表读写且挡住后续查询。
- 迁移脚本包在事务里（DDL 事务性），失败自动回滚；但 CONCURRENTLY 例外。
- 大表加列避免带 volatile 默认值（可能触发全表重写与长时间锁持有）。
- 上线变更设 `lock_timeout`，避免 DDL 长时间排队引发查询雪崩。

---

## 常见误区与工程要点

- **以为 DDL 不阻塞**：多数 DDL 取重锁；高并发上线需选低锁方案或错峰。
- **忽视 pg_depend**：裸 DROP 被依赖对象会报错，需 CASCADE 或先删依赖。
- **认为目录很神秘**：目录就是表，可直接查询排查（pg_class/pg_attribute…）。
- **CREATE INDEX 阻塞写**：普通 CREATE INDEX 取 ShareLock 阻塞写，生产用 CONCURRENTLY。
- **CONCURRENTLY 也是事务性**：它非事务、中途失败会留 INVALID 索引需手工清理。

---

## 一句话总纲

**DDL 把 CREATE/ALTER/DROP 统一为对系统目录表（pg_class/pg_attribute/pg_index…，本身就是 heap 表）的行增删改：经 `ProcessUtility`→`standard_ProcessUtility`→`ProcessUtilitySlow` 分派到 commands/ 处理器（`DefineRelation`/`DefineIndex`），取锁防并发后用 `CatalogTupleInsert/Update` 改目录行、建物理文件、`recordDependencyOn` 记 pg_depend 依赖、写 WAL，随事务原子提交/回滚；目录复用 MVCC/WAL，查询编译经 syscache/relcache 缓存加速、DDL 提交后广播失效消息——生产变更的关键是评估 DDL 取的锁级别（多数 ALTER/DROP 取 AccessExclusiveLock 会阻塞全表并挡住后续查询），加索引优先用非事务的 CONCURRENTLY。**
