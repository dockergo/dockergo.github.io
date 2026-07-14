# PostgreSQL 核心原理 · 支撑能力域 · WAL 与恢复复制

> **定位**：保障能力域。先写日志（WAL）保证持久性与崩溃恢复，同一份 WAL 又驱动流复制与 PITR。被所有写路径（**DML/DDL**）依赖，由后台 **checkpointer/walwriter/walsender/startup** 进程执行。核实基准：官方源码 `postgres/src`。

## 一、先写日志（WAL）

![先写日志](Postgres原理_WAL_01先写日志.svg)

一次修改的持久化路径：① 改缓冲池里的页（标脏、未落盘）→ ② 生成 WAL 记录（`XLogInsert`，`xloginsert.c:482`，描述"改了什么"）→ ③ 提交时 WAL 落盘（fsync 到 pg_wal/，此刻才算持久）→ ④ 脏数据页稍后由 bgwriter/checkpointer 异步批量刷。**WAL 规则**：数据页刷盘前描述该修改的 WAL 必须已落盘（write-ahead）——保证崩溃可重放；提交只需 WAL 顺序写 + fsync（快），把随机写摊平成顺序写。**Checkpoint**（`CheckPointGuts:703`）：刷所有脏页到数据文件（此前 WAL 不再需要用于恢复、可回收）、记 redo 点（崩溃从此点重放）；触发时机 `checkpoint_timeout`/`max_wal_size`（默认 1GB，`xlog.c:121`），越频繁恢复越快但刷盘压力越大，`full_page_writes` 防页部分写。

---

## 二、崩溃恢复与复制

![恢复与复制](Postgres原理_WAL_02恢复与复制.svg)

**崩溃恢复**（startup 进程）：从最近 checkpoint 的 redo 点开始 → 顺序重放 WAL（REDO，把每条改动重新应用到页）→ 恢复到崩溃前最后已提交状态（未提交改动忽略）。**流复制**：主库 `walsender` 持续发 WAL 流，备库 `walreceiver` 收下交 startup 回放，备库准实时一致（同步/异步可选、可只读查询做读扩展、主故障时提升备库）。关键洞见：**WAL 是"改动的权威流水"，一份多用**——崩溃恢复（本机重放）、物理复制（字节级 WAL 给备库，高可用+读扩展）、逻辑复制（解码 WAL 成行变更，选择性/跨版本同步）、PITR 时间点恢复（基础备份 + 归档 WAL 恢复到任意时刻）。

---

## 拓展 · WAL 与复制组件

| 组件 | 职责 | 锚点 |
|---|---|---|
| XLogInsert | 写 WAL 记录 | `access/transam/xloginsert.c:482` |
| CreateCheckPoint | 检查点 | `access/transam/xlog.c` |
| startup 进程 | 回放 WAL 恢复 | `postmaster/startup.c` |
| walsender/walreceiver | 流复制收发 | `replication/` |
| 逻辑解码 | WAL→行变更 | `replication/logical/` |

---

## 调优要点（关键开关）

- `max_wal_size`/`checkpoint_timeout`：权衡恢复速度与刷盘压力（稀疏→恢复慢，过密→IO 抖）。
- `checkpoint_completion_target`：把 checkpoint 刷盘摊平到周期内，削峰。
- `wal_level`：replica/logical 决定支持物理/逻辑复制。
- `synchronous_commit`：可为吞吐牺牲少量持久性（异步提交）。
- 归档 WAL（`archive_mode`）+ 基础备份支撑 PITR。

---

## 常见误区与工程要点

- **以为提交就刷了数据页**：提交只保证 WAL 落盘，数据页异步刷——靠 WAL 重放补齐。
- **checkpoint 越频越好**：过密频繁全量刷脏页造成 IO 抖动；要权衡。
- **异步复制零丢失**：异步复制主故障可能丢最后一小段；需零丢失用同步复制。
- **忽视 WAL 归档**：不归档就没有 PITR 与差异恢复能力。

---

## 一句话总纲

**WAL 与恢复复制以"先写日志"为核心：修改先改缓冲页并生成 WAL 记录、提交时 WAL 顺序写 fsync 落盘（数据页由 checkpointer/bgwriter 异步刷、checkpoint 推进 redo 点回收旧 WAL）；崩溃时 startup 进程从 redo 点重放 WAL 恢复到已提交状态，同一份 WAL 又经 walsender/walreceiver 驱动物理/逻辑流复制与 PITR——是持久性、高可用与读扩展的共同支柱。**
