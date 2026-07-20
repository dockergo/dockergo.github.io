# nginx 核心原理 · 支撑能力域 · upstream 负载均衡

> **定位**：后端与安全能力域。反向代理时在多后端间选 peer、做被动健康检查、复用连接。是 **upstream 模块**（一种 content handler）的核心，被反代类 **HTTP 阶段处理**（CONTENT）驱动，peer 状态用**共享内存**跨 worker 共享。核实基准：官方源码 `nginx/src`（`commit 9e32c636`，nginx 1.31.3）。

## 一、负载均衡策略

![负载均衡](Nginx原理_upstream_01负载均衡.svg)

`upstream{}` 声明策略选 peer，全部构建在 round_robin 基座上：`ngx_http_upstream_init_round_robin`（`http/ngx_http_upstream_round_robin.c:37`）把 `server` 展开成 `peer[]` 数组，逐 peer 初始化 `effective_weight/current_weight`（`http/ngx_http_upstream_round_robin.c:191`）与 `max_fails/fail_timeout`（`http/ngx_http_upstream_round_robin.c:194`）。**round robin（默认）** 的核心是**平滑加权轮询**：`ngx_http_upstream_get_peer`（`http/ngx_http_upstream_round_robin.c:811`）每轮给每个 peer `current_weight += effective_weight`（`http/ngx_http_upstream_round_robin.c:884`），选 `current_weight` 最大者（`http/ngx_http_upstream_round_robin.c:891`），再让胜者 `best->current_weight -= total`（`http/ngx_http_upstream_round_robin.c:910`）——权重高的被选更频繁但不会连续扎堆，分布平滑。入口 `ngx_http_upstream_get_round_robin_peer`（`http/ngx_http_upstream_round_robin.c:697`）先跳过熔断的 peer 再调上面的选法。

**其它策略**：**ip_hash/hash** 按客户端 IP 或自定 key 哈希（会话保持，consistent 减少后端增减时的重分布）；**least_conn/least_time** 选当前连接最少/响应最快（适合请求耗时不均）；**random（power of two choices）** 随机选 2 个取较优（近似 least_conn 更省状态，大规模后端友好）。这些都是独立模块（`ngx_http_upstream_ip_hash_module.c` 等）在 round_robin 基座上换 `get` 回调实现；共享内存 zone（`ngx_http_upstream_zone_module.c`）让多 worker 共享 peer 状态与统计。

---

## 二、健康检查与连接复用

![健康与复用](Nginx原理_upstream_02健康与复用.svg)

**被动健康检查**（开源版内建）：转发失败（超时/拒绝/错误）后 `ngx_http_upstream_free_round_robin_peer`（`http/ngx_http_upstream_round_robin.c:1008`，加锁版 `:1023`）里 `peer->fails++`（`:1059`）累计并记 `peer->accessed` 时间戳；选 peer 时若 `fails >= max_fails` 且仍在 `fail_timeout` 窗口内则跳过该 peer，窗口过后放一个请求半开重试恢复。`proxy_next_upstream` 控哪些错误（error/timeout/http_5xx…）触发 `ngx_http_upstream_next`（`http/ngx_http_upstream.c:4591`）换到别的 peer 重试。

**keepalive 连接池**：请求完不关到后端的连接、`ngx_http_upstream_free_keepalive_peer`（`http/modules/ngx_http_upstream_keepalive_module.c:278`）把连接挂进 cache 队列，下次 `ngx_http_upstream_get_keepalive_peer`（`:205`）从队头取复用并置 `pc->cached=1`（`:271`），省 TCP+TLS 握手降延迟，需配 `proxy_http_version 1.1` + 清 Connection 头。一次反向代理完整链路：CONTENT 阶段 proxy_pass 触发 `ngx_http_upstream_init`（`http/ngx_http_upstream.c:543`）→ 选 peer（跳过坏的）→ `ngx_http_upstream_connect`（`:1563`，keepalive 优先）→ 非阻塞发请求、`ngx_http_upstream_process_header`（`:2451`）收响应头 → 经 filter 回客户端（可同时写缓存）→ 连接放回池。

---

## 三、失败路径与边界

- **全部 peer 不可用**：`ngx_http_upstream_next`（`:4591`）遍历完所有 peer 仍失败时返回 502 Bad Gateway；若开了熔断且全被标坏，nginx 会临时重置尝试而非永久拒服。
- **重试放大风险**：`proxy_next_upstream` 若含幂等性差的方法（POST）可能导致重复副作用；用 `proxy_next_upstream_tries`/`proxy_next_upstream_timeout` 限制重试次数与总时长。
- **keepalive 连接失效**：复用的后端连接可能已被后端关闭，取用后发请求遇 RST 时 `ngx_http_upstream_next` 会重连并换 peer；`ngx_http_upstream_free_keepalive_peer`（`:278`）在连接异常时不入池、直接关闭。
- **不配 zone 的统计漂移**：无 `zone` 时 peer 计数是各 worker 私有，熔断判定各算各的、不一致——生产必配共享内存 zone。
- **权重饥饿**：某 peer 权重为 0 或长期熔断时，平滑加权算法自动不再选它，恢复后 `current_weight` 从 0 重新爬升，避免恢复瞬间被打爆。

---

## 拓展 · upstream 相关指令

| 指令 | 作用 | 锚点 |
|---|---|---|
| `upstream name { server ...; }` | 定义后端池 | `http/ngx_http_upstream_round_robin.c:37` |
| `server ... weight= max_fails= fail_timeout=` | peer 参数与健康检查阈值 | `http/ngx_http_upstream_round_robin.c:194` |
| `ip_hash` / `hash` / `least_conn` / `random` | 选负载均衡策略 | `http/modules/ngx_http_upstream_ip_hash_module.c` |
| `keepalive N` | 到后端的长连接池大小 | `http/modules/ngx_http_upstream_keepalive_module.c:205` |
| `proxy_next_upstream` | 何种错误重试到下一 peer | `http/ngx_http_upstream.c:4591` |
| `zone name size` | 共享内存，多 worker 共享 peer 状态 | `http/modules/ngx_http_upstream_zone_module.c` |

---

## 调优要点（关键开关）

- 生产用 `zone` 让 peer 状态跨 worker 一致（否则各 worker 各判健康）。
- 配 `keepalive` + HTTP/1.1 到后端，显著降延迟与握手开销。
- `max_fails`/`fail_timeout` 按后端稳定性调，避免误熔断或迟熔断。
- 会话敏感用 ip_hash/hash（consistent），否则默认 round robin 即可。
- POST 等非幂等请求慎配 `proxy_next_upstream`，防重试重复副作用。

---

## 常见误区与工程要点

- **以为开源版有主动健康检查**：开源版是被动（靠真实请求失败判定 `peer->fails++`）；主动探测在商业版或第三方模块。
- **keepalive 不清 Connection 头**：不清会导致连接被关，池失效——必须配 `proxy_set_header Connection ""`。
- **ip_hash 后端增减致大量重分布**：用 consistent 哈希缓解。
- **不配 zone 却依赖统计一致**：多 worker 下 peer 计数各算，健康判定不准。
- **误以为加权轮询会连续打同一台**：平滑加权算法（`current_weight += effective_weight`，`:884`）保证分布均匀不扎堆。

---

## 一句话总纲

**upstream 负载均衡在反代 CONTENT 阶段于多后端间选 peer：round robin（默认平滑加权，`ngx_http_upstream_get_peer` `round_robin.c:811`，`current_weight += effective_weight` `:884`）/ip_hash/hash（会话保持）/least_conn/least_time/random 各是 round_robin 基座上不同的 get 回调，peer 状态经共享内存 zone 跨 worker 共享；被动健康检查按 `peer->fails++`（`:1059`）达 max_fails/fail_timeout 熔断坏 peer、半开重试恢复，`ngx_http_upstream_next`（`ngx_http_upstream.c:4591`）换 peer、keepalive 连接池（`keepalive_module.c:205/278`）复用到后端的长连接省握手——共同实现高可用、低延迟的后端分流。**
