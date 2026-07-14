# Google QUICHE 核心原理 · 接口主线 · HTTP 与流

> **定位**：应用层接触面——`QuicSpdySession` 承载 HTTP/2·HTTP/3 语义，服务端 `QuicDispatcher` 按 connection ID 接客分流。是 QUICHE 作 Web 服务器/客户端的入口。核实基准：本地源码 `quic/core/http/`、`quic_dispatcher.h`。

## 一、HTTP 语义 + Dispatcher 接客

![HTTP与Dispatcher](Quiche原理_HTTP流_01HTTP与Dispatcher.svg)

**QuicSpdySession**（`quic/core/http/`，QuicSession 子类，加 HTTP 语义）：每个 HTTP 请求一条双向 **QuicSpdyStream**（`quic_spdy_stream.h`，承载 header+body），另有控制流 `QuicSendControlStream`/`QuicReceiveControlStream`（HTTP/3 设置、QPACK 编解码流）；HTTP/2 走 `quiche/http2/`（HPACK），HTTP/3 走这里（QPACK）。**QuicDispatcher**（服务端接客，`quic_dispatcher.h:62`）：所有入站包先到 `ProcessPacket`（`:85`），按 connection ID 查已有会话→路由到对应 QuicSession；新 CID + 合法 Initial→建新 Session（`CreateQuicSession`）；兼做入口防护（Retry 地址验证、缓冲 Initial、限流抗 DoS，见抗攻击）。**一个 HTTP/3 请求的旅程**：Dispatcher 按 CID 路由→Connection 解密解帧→STREAM 帧到 SpdySession/Stream→QPACK 解头组装请求→应用生成响应写回 stream→回程 QPACK 编头经 Writer 发出。

---

## 拓展 · HTTP 与流关键类

| 类 | 职责 | 锚点 |
|---|---|---|
| QuicSpdySession | HTTP over QUIC 语义 | `quic/core/http/` |
| QuicSpdyStream | 一请求一双向流 | `quic_spdy_stream.h` |
| QuicDispatcher | 服务端按 CID 接客分流 | `quic_dispatcher.h:62` |
| 控制流 | HTTP/3 设置、QPACK 流 | Send/ReceiveControlStream |

---

## 调优要点（关键开关）

- 应用继承 QuicSpdyStream 处理请求/响应，别裸拼 header。
- Dispatcher 层做限流/Retry，抗放大与 DoS（见抗攻击）。
- QPACK 动态表大小权衡压缩率 vs 队头阻塞。
- 长连接复用多请求，控制并发流上限。

---

## 常见误区与工程要点

- **一请求一连接**：QUIC 是一连接多流，一请求一双向流。
- **绕过 Dispatcher 建连**：服务端新连接经 Dispatcher 判定 + 建 Session。
- **混淆 HPACK/QPACK**：HTTP/2 用 HPACK，HTTP/3 用 QPACK（抗队头阻塞）。
- **不做入口防护**：Initial 不限流会被放大攻击/DoS 打爆。

---

## 一句话总纲

**HTTP 与流是 QUICHE 的应用层接触面：QuicSpdySession 在 QuicSession 上加 HTTP/2·HTTP/3 语义，每请求一条 QuicSpdyStream 承载 header+body，控制流跑 HTTP/3 设置与 QPACK；服务端 QuicDispatcher 按 connection ID 接客——收包查会话/建新连接、兼做 Retry 与限流防护；一个请求经 Dispatcher 路由→Connection 解帧→SpdyStream QPACK 解头→应用处理→回程编头经 Writer 发出。**
