# nginx 核心原理 · 支撑能力域 · HTTP 请求阶段处理

> **定位**：请求处理、灵魂能力域之一。一个 HTTP 请求经 **11 个阶段**（POST_READ→…→CONTENT→LOG）被处理，模块把 handler 挂在某阶段——这是理解一切 HTTP 模块的骨架。依赖**进程与事件模型**（在 worker 事件循环内跑、可暂停恢复），是**模块体系**的执行舞台。核实基准：官方源码 `nginx/src`。

## 一、11 个阶段：请求的生命周期骨架

![11 阶段](Nginx原理_HTTP阶段_01十一阶段.svg)

阶段顺序（`http/ngx_http_core_module.h:111-128`）：**POST_READ**（读完头最早钩子，如 realip）→ **SERVER_REWRITE**（server 级 rewrite）→ **FIND_CONFIG**（按 URI 匹配 location 选配置）→ **REWRITE**（location 级）→ **POST_REWRITE**（URI 变了则跳回 FIND_CONFIG）→ **PREACCESS**（限流 limit_req/limit_conn）→ **ACCESS**（allow/deny、auth）→ **POST_ACCESS**（satisfy 判定）→ **PRECONTENT**（try_files/mirror/auth_request）→ **CONTENT**（产内容：静态文件/proxy_pass/fastcgi）→ **LOG**（记 access log）。CONTENT 产出后经 **header filter 链 + body filter 链**加工再写回客户端（`ngx_http_output_filter`，`core_module.c:1925`）。全库用同一贯穿请求 `GET /api/users` 命中 `location /api/ { proxy_pass http://api; }`。

---

## 二、phase 引擎：数组 + checker 驱动、可暂停恢复

![phase 引擎](Nginx原理_HTTP阶段_02phase引擎.svg)

所有阶段 handler 编译期展平成一个数组，请求带游标 `r->phase_handler` 指当前位置；`ngx_http_core_run_phases`（`core_module.c:884`）逐个推进，每个 phase 有 checker（`generic_phase:906`、`content_phase:1292`）决定如何调 handler 与推进游标。**handler 返回码 → checker 动作**：OK/DECLINED 推进下一个；**AGAIN/DONE 暂停等事件再回来**；HTTP 状态码则结束请求返回响应。正是"暂停/恢复"让阻塞点（等后端、等磁盘）不占线程——返回 AGAIN 后 worker 转处理别的连接，后端就绪事件到时 `write_event_handler = run_phases`（`:878`）从游标续跑。这与"进程与事件模型"的非阻塞循环无缝衔接。

---

## 拓展 · 各阶段可挂什么

| 阶段 | 典型模块/指令 | 作用 |
|---|---|---|
| POST_READ | realip | 取真实客户端 IP |
| SERVER/location REWRITE | rewrite、return | URI 改写/重定向 |
| FIND_CONFIG | （内建） | 匹配 location |
| PREACCESS | limit_req、limit_conn | 限流 |
| ACCESS | allow/deny、auth_basic、auth_request | 鉴权 |
| PRECONTENT | try_files、mirror | 内容前处理 |
| CONTENT | root/index（静态）、proxy_pass、fastcgi_pass | 产响应 |
| LOG | access_log | 记录 |

---

## 调优要点（关键开关）

- 用 `location` 精确/前缀/正则匹配控制 FIND_CONFIG 选中的配置。
- 限流放 PREACCESS（limit_req 漏桶）在鉴权前挡住洪峰。
- `try_files` 在 PRECONTENT 优雅回退（找文件→目录→兜底后端）。
- 避免在 rewrite 里写复杂正则回路（POST_REWRITE 跳回可能循环）。

---

## 常见误区与工程要点

- **以为 handler 随便挂哪都行**：模块必须挂对阶段，如鉴权挂 ACCESS、内容挂 CONTENT，错位则时机不对。
- **rewrite 无限循环**：URI 反复改会在 FIND_CONFIG↔POST_REWRITE 间打转，nginx 有次数上限保护但应避免。
- **LOG 阶段做重活**：LOG 在响应后跑，别在此做阻塞操作拖慢连接回收。
- **把 CONTENT 当可多个**：CONTENT 只跑选中的一个 content handler 产响应，不是链式叠加。

---

## 一句话总纲

**HTTP 请求处理是把一个请求跑过 11 个阶段（POST_READ→SERVER_REWRITE→FIND_CONFIG→REWRITE→POST_REWRITE→PREACCESS→ACCESS→POST_ACCESS→PRECONTENT→CONTENT→LOG）：模块把 handler 挂在对应阶段，ngx_http_core_run_phases 用展平的 handler 数组 + 游标 + 各 phase 的 checker 驱动推进，handler 返回 AGAIN 即暂停让出线程、事件就绪后经 write_event_handler 从游标续跑；CONTENT 产出的响应再经 header/body filter 链加工后非阻塞写回——这条阶段流水线是一切 HTTP 模块的挂载骨架。**
