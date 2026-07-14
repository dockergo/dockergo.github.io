# nginx 核心原理 · 支撑能力域 · 日志与限流

> **定位**：连接底座能力域。access 日志在 LOG 阶段记录、error 日志分级随时写、缓冲写省 IO；限流（limit_req 漏桶 / limit_conn 计数）在 PREACCESS 阶段挡洪峰。依赖**HTTP 阶段处理**（挂载时机）与**共享内存**（跨 worker 计数）、**信号控制**（reopen 切日志）。核实基准：官方源码 `nginx/src`。

## 一、日志：access 在 LOG 阶段、error 分级

![日志](Nginx原理_日志_01日志.svg)

**access log**（LOG 阶段，响应发完后）：`log_format` 是变量模板（`$remote_addr $request $status $body_bytes_sent $request_time`…），变量请求期求值填模板写一行；`buffer=`/`gzip=` 缓冲攒批写盘降 IO 频率。**error log**（分级，随时可写）：级别 debug→info→notice→warn→error→crit，`error_log path level` 只记 ≥ 该级，是诊断第一现场（upstream 错误、超时、配置告警）；debug 需编译/配置开启，生产用 warn/error、排障临时提级。**日志切割配合信号**：mv 日志文件（nginx 仍持旧 inode 写）→ `nginx -s reopen`（worker 重开新文件）→ 压缩归档，不丢日志不停服（见"信号控制"篇）。

---

## 二、限流：漏桶与并发计数

![限流](Nginx原理_日志_02限流.svg)

**limit_req 漏桶**（`limit_req_module.c`）：`rate` 为每秒放行速率，按 key（如 `$binary_remote_addr`）在共享内存记 `excess` 水位（`module.c:27`）——来快了 excess 涨、随时间按 rate 漏掉（`lookup` 算当前 excess，`:68`）；`excess ≤ burst` 放行（可 delay 平滑）、超 burst+nodelay 立即放行计入突发、远超则拒绝返 503。**limit_conn 并发计数**：共享内存计数 by key，连接开始 +1 结束 -1，超上限拒绝新连接。二者都在 **PREACCESS 阶段**——在花代价做鉴权/回源前就把洪峰挡住、保护后端与自身；key 用共享内存跨 worker 统计（一个 IP 的请求可能落不同 worker，必须共享才准）。漏桶平滑速率、计数限并发，常配合用。

---

## 拓展 · 日志与限流指令

| 指令 | 作用 |
|---|---|
| `log_format` / `access_log path fmt buffer= gzip=` | 日志格式与缓冲/压缩写 |
| `error_log path level` | 错误日志与级别 |
| `limit_req_zone key zone= rate=` + `limit_req zone= burst= nodelay` | 请求速率漏桶 |
| `limit_conn_zone key zone=` + `limit_conn zone= N` | 并发连接数限制 |
| `limit_req_status` / `limit_conn_status` | 超限返回码 |

---

## 调优要点（关键开关）

- access log 开 `buffer=`（如 32k）+ `gzip`，高流量下大幅降磁盘 IO。
- 限流 key 用 `$binary_remote_addr`（比字符串省内存）。
- `burst` + `nodelay` 允许合理突发又不排队延迟。
- 排障临时把 error_log 提到 info/debug，完事调回 warn。

---

## 常见误区与工程要点

- **限流不用共享内存**：单 worker 计数无意义；必须 `*_zone`（共享内存）跨 worker 统计。
- **access log 不缓冲**：每请求同步写盘拖慢高并发；开 buffer。
- **limit_req 无 burst**：严格匀速会拒掉正常突发；配合理 burst。
- **logrotate 后不 reopen**：nginx 仍写旧 inode，新文件空——必须 reopen。

---

## 一句话总纲

**日志与限流：access log 在 LOG 阶段按 log_format 变量模板缓冲写盘、error log 分级记录诊断现场、日志切割靠 mv + reopen 不丢不停服；限流在 PREACCESS 阶段抢先挡洪峰——limit_req 漏桶按 rate 放行、excess 水位超 burst 则拒（返 503），limit_conn 共享内存计数限并发，二者的 key 都用共享内存跨 worker 统计才准确。**
