# nginx 核心原理 · 支撑能力域 · SSL/TLS

> **定位**：后端与安全能力域。在事件循环内做非阻塞 TLS 握手、按 SNI 选证书、终止加密（解密后明文转后端）。依赖**进程与事件模型**（握手不阻塞 worker），与 phase 引擎的暂停/恢复机制同构。核实基准：官方源码 `nginx/src`（`event/ngx_event_openssl.c`）。

## 一、握手、SNI 与优化

![握手与终止](Nginx原理_SSL_01握手与终止.svg)

**TLS 握手嵌进事件循环**：ClientHello（含 SNI 目标域名）→ 按 SNI 选证书（一个 IP 多域名各自证书）→ 密钥协商（证书 + ECDHE 等）。关键：`SSL_do_handshake` 返回 `WANT_READ`/`WANT_WRITE` 时挂起等事件，与 phase 引擎的 AGAIN 机制一致——**慢握手不占线程**，worker 转去处理别的连接。握手很贵，故有复用与优化：**会话复用**（session cache 共享内存 / session ticket 免全握手）、**OCSP stapling**（nginx 代取证书状态省客户端外部查询）、**TLS 1.3/0-RTT**（更少往返，`ssl_protocols` 控版本）。

**TLS 终止（termination）**：加密边界在 nginx——客户端⇄nginx 走 HTTPS（nginx 解密）、nginx⇄后端走明文 HTTP（内网）或再加密（proxy_ssl）。收益：后端不必管证书/加密、证书集中在 nginx 统一管理。

---

## 拓展 · SSL 相关指令

| 指令 | 作用 |
|---|---|
| `ssl_certificate` / `ssl_certificate_key` | 证书与私钥（可多组按 SNI） |
| `ssl_protocols` / `ssl_ciphers` | 允许的协议版本与加密套件 |
| `ssl_session_cache` / `ssl_session_tickets` | 会话复用 |
| `ssl_stapling on` | OCSP stapling |
| `ssl_prefer_server_ciphers` | 加密套件选择偏好 |
| `proxy_ssl_*` | 到后端再加密 |

---

## 调优要点（关键开关）

- 开 `ssl_session_cache shared:...` + tickets，握手复用降 CPU 与延迟。
- 用 TLS 1.3 减少往返；禁用老旧协议/弱套件。
- `ssl_stapling on` 提升客户端首次连接速度。
- 大量 HTTPS 时握手是 CPU 大头，worker 数与会话复用要一起调。

---

## 常见误区与工程要点

- **以为握手会阻塞 worker**：握手是事件驱动非阻塞的，WANT_READ/WRITE 时让出线程。
- **不开会话复用**：每次全握手 CPU 昂贵，高并发 HTTPS 必开 cache/tickets。
- **SNI 证书配错**：多域名要为每个 server_name 配对应证书，否则回退默认证书告警。
- **终止后忘了内网安全**：nginx→后端明文只在可信内网可接受，跨网段应 proxy_ssl。

---

## 一句话总纲

**SSL/TLS 在事件循环内做非阻塞握手：ClientHello 带 SNI → 按 SNI 选证书 → 密钥协商，SSL_do_handshake 返回 WANT_READ/WRITE 时像 phase 引擎的 AGAIN 一样挂起让出线程；握手昂贵故用 session cache/ticket 复用、OCSP stapling、TLS 1.3 优化；nginx 作 TLS 终止点——对客户端 HTTPS 加密、对后端明文（或 proxy_ssl 再加密），把证书与加密集中管理、卸载后端负担。**
