# MySQL 核心原理 · 支撑能力域 · handler 存储引擎 API（灵魂）

> **定位**：MySQL 的定义性抽象、全库灵魂。它是 SQL 层与存储引擎层之间唯一的缝隙——Server 层不知道数据如何存储，只调用一组统一的虚函数；每个引擎（InnoDB/MyISAM/…）实现这组接口即可插入。核实基准：`sql/handler.h`、`sql/handler.cc`、`storage/innobase/handler/ha_innodb.cc`。

## 一、两个抽象：handlerton 与 handler

![handlerton 与 handler](MySQL原理_支撑_handler存储引擎API_01两抽象.svg)

MySQL 用两个层次抽象一个存储引擎。**`handlerton`（handler singleton，每引擎一个）**是引擎的"总入口"：一堆函数指针登记引擎级能力——事务 `commit` / `rollback` / `prepare`（供 2PC），以及最关键的 `create` 用来产出 handler 实例。**`handler`（每表一个实例）**是一组虚函数、描述"对这张表能做什么"——`write_row` 插入一行、`index_read_map` 按索引定位、`rnd_next` 全表顺序读、`external_lock` 在语句起止通知引擎加/放表级锁并划定事务边界。Server 层只面向这套接口编程，不知道底层是 B+树还是堆表。各结构与虚函数落点见深化表。

## 二、双日志与两阶段提交

![2PC](MySQL原理_支撑_handler存储引擎API_02两阶段提交.svg)

handler 缝带来一个独特难题：Server 层有自己的 **binlog**（逻辑日志，用于复制），引擎有自己的 **redo**（物理日志，用于崩溃恢复）——一次提交必须让两者**要么都生效、要么都不生效**，否则主从数据分叉。MySQL 用**两阶段提交（2PC）**解决：`ha_commit_trans` 先做 prepare（触发各引擎 `handlerton::prepare` → InnoDB 写 redo 的 prepare 记录并落盘），再做 commit——此时 binlog 作为事务协调者：先把事件写入 binlog（这一步成功即"提交点"），再通知引擎 `commit`（写 redo 的 commit 记录、释放锁）。崩溃恢复时按"redo 有 prepare 但 binlog 无记录→回滚；binlog 已记→提交"判定，保证一致；`ordered_commit` 再用组提交合并多事务的 fsync。各 2PC 阶段函数落点见深化表。

## 深化 · handler 关键虚函数

| 虚函数 | 作用 | 包装/落点 |
|---|---|---|
| write_row | 插入一行 | `ha_write_row` `sql/handler.h:2437` |
| index_read_map | 按索引定位 | `ha_index_read_map` `:2407` / 虚 `:2819` |
| rnd_next | 全表顺序读下一行 | handler 虚函数 |
| external_lock | 语句起止 + 事务边界 | `ha_external_lock` `:2436` |
| create（hton） | 产出 handler 实例 | `(*create)` `sql/handler.h:772` |

## 深化 · 两阶段提交落点

| 阶段 | 作用 | 落点 |
|---|---|---|
| 提交总入口 | 驱动 2PC | `ha_commit_trans` `sql/handler.cc:1671` |
| prepare | 触发各引擎写 prepare | `tc_log->prepare` `sql/handler.cc:1792` |
| commit | binlog 协调 + 通知引擎 | `tc_log->commit` `sql/handler.cc:1807` |
| InnoDB prepare | 写 redo prepare 记录 | `innobase_xa_prepare` `ha_innodb.cc:17153` |
| InnoDB commit | 写 redo commit、释放锁 | `innobase_commit` `ha_innodb.cc:4370` |
| 组提交 | 合并多事务 fsync | `ordered_commit` `sql/binlog.cc:9520` |

## 深化 · InnoDB 如何"填"这套虚函数

抽象接口落到具体实现才有意义：InnoDB 把 `handler` 的纯虚函数一一实现成 `ha_innobase` 的成员，引擎级能力则由 `handlerton` 的函数指针在启动时登记（`innobase_hton->prepare = innobase_xa_prepare` 等）。**这就是"可插拔"的全部机制**——Server 层永远只见抽象基类的虚函数签名，具体是 B+树还是堆表、走不走 MVCC 全被封进各引擎实现体，换成 MyISAM 只是换一组实现，上层 SQL 与执行器代码一行不改。

| 虚函数（包装） | InnoDB 实现 | 落点 |
|---|---|---|
| `ha_write_row` `sql/handler.cc:8153` | 插入聚簇索引 B+树 | `ha_innobase::write_row` `ha_innodb.cc:7507` |
| 索引定位 | 内部走 `row_search_mvcc` 取可见行 | `ha_innobase::index_read` `ha_innodb.cc:8700` |
| `ha_external_lock` `sql/handler.cc:8054` | 划事务边界、加意向锁 | `handler::ha_external_lock` |

## 拓展 · handlerton vs handler

| handlerton（每引擎单例） | handler（每表实例） |
|---|---|
| 引擎级能力 + 函数指针表 | 表级操作虚函数 |
| commit/rollback/prepare/create | write_row/index_read/rnd_next |
| 全局注册一次 | 打开一张表创建一个 |

## 调优要点

- 选对引擎：需要事务/行锁/崩溃安全用 InnoDB（默认）；只读历史归档场景才考虑其它。
- 事务边界即锁边界：`external_lock` 在语句起止触发，长事务持锁久、拖累并发。
- 2PC 有开销：`innodb_flush_log_at_trx_commit=1` + `sync_binlog=1` 最安全，组提交摊薄 fsync 成本。
- 混用引擎慎重：跨引擎事务无法整体 2PC，一致性保证被打破。

## 常见误区

- **handler 是"驱动程序"**：它是编译进服务器的 C++ 抽象类，不是外部驱动；引擎以插件/静态方式实现。
- **redo 和 binlog 重复可删一个**：职责不同（恢复 vs 复制），2PC 靠两者协调，删任一破坏一致或复制。
- **换引擎要改 SQL**：SQL 不变，只是底层存取实现换了——这正是 handler 缝的价值。

## 一句话总纲

**handler API 是 MySQL 的灵魂：handlerton（每引擎单例，登记 commit/prepare/create 等能力）+ handler（每表实例，暴露 write_row/index_read/external_lock 等虚函数）两级抽象，把"存储引擎"整体做成一层可插拔虚函数。它向上给 Server 层引擎无关的统一接口，向下靠两阶段提交协调 binlog 与 redo 双日志的一致——这条缝同时兑现了"引擎可插拔"与"事务可靠"两个目标。**
