# Google QUICHE 核心原理 · 接口主线 · 会话与连接

> **定位**：核心编程接触面——三层对象 QuicConnection/QuicSession/QuicStream + Visitor 回调。是应用操作 QUIC 的主 API，依赖**连接管理**、**流与流量控制**能力域。核实基准：`quic/core/quic_connection.h`、`quic_session.h`、`quic_stream.h`。

## 一、三层对象 + Visitor 回调

![三层对象](Quiche原理_会话连接_01三层对象.svg)

**三层（自上而下）**：**QuicSession**（`quic_session.h:62`，管连接内所有流，`GetOrCreateStream:714` 按流号取/建流、`WritevData:530` 写流数据，收帧事件分发到对应流）→ **QuicStream**（`quic_stream.h:158`，单条流的收发缓冲 + 流控 + fin/reset，应用重写 `StreamInterface::OnDataAvailable`（`:69`）收数据、内含 `flow_controller_`（`:146`））；QuicSession 建在 **QuicConnection**（`quic_connection.h`，连接状态机：收发包、握手、丢包/拥塞、CID/迁移）之上并拥有它。crypto 走 `GetMutableCryptoStream`（`quic_session.h:901`）暴露的特殊流。

**Visitor 回调（控制反转）**：连接把"发生了什么"经 `QuicConnectionVisitorInterface`（`quic_connection.h:128`）回调上层——`OnStreamFrame`（`:133`）来了流数据、`OnWriteBlocked`（`:174`）写被阻塞、`OnCanWrite`（`:181`）可继续写、`OnConnectionClosed`（`:170`）连接关闭、`OnConnectionMigration`（`:187`）路径迁移。**QuicSession 就是 QuicConnection 的 Visitor**：`QuicSession::OnStreamFrame`（`quic_session.h:292`）收到帧→查/建 Stream→喂数据；`QuicSession::OnCanWrite`（`:307`）驱动挂起的流继续发。对比 Cloudflare quiche 的 `readable()` 轮询，QUICHE 用回调推（C++ OO 观察者模式）。

## 二、建连与生命周期

**客户端**：建 `QuicConnection` + `QuicSpdyClientSession`（HTTP 时）发起握手，握手在 `QuicCryptoStream` 上走 CRYPTO 帧；**服务端**：由 `QuicDispatcher` 按 connection ID 把入站包 demux 到会话、新 CID 合法 Initial 建新 Session（见 HTTP 与流 / 可靠性主线）。写路径：应用 `WritevData`（`:530`）→数据进 Stream 发送缓冲 + `flow_controller_` 扣额度→Connection 组包经 Writer 发出；写被反压时 Session 记下待写流，`OnCanWrite`（`:307`）恢复时按调度轮转发送。读路径：Connection 解帧→`OnStreamFrame`（`:292`）→`GetOrCreateStream`（`:714`）→Stream 排序缓冲→回调应用 `OnDataAvailable`（`quic_stream.h:69`）。关连接经 `OnConnectionClosed`（`quic_connection.h:170`）通知所有流。

## 深化 · 三层对象关键方法

| 层 | 对象 | 关键方法 | 锚点 |
|---|---|---|---|
| 会话 | QuicSession | 类定义 | `quic_session.h:62` |
| 会话 | QuicSession | GetOrCreateStream 取/建流 | `quic_session.h:714` |
| 会话 | QuicSession | WritevData 写流数据 | `quic_session.h:530` |
| 会话 | QuicSession | OnStreamFrame 分发帧 | `quic_session.h:292` |
| 会话 | QuicSession | OnCanWrite 驱动挂起流 | `quic_session.h:307` |
| 流 | QuicStream | 类定义 | `quic_stream.h:158` |
| 流 | QuicStream | OnDataAvailable 收数据 | `quic_stream.h:69` |
| 连接 | QuicConnection | 状态机 + 收发包核心 | `quic_connection.h` |
| crypto | QuicCryptoStream | GetMutableCryptoStream | `quic_session.h:901` |

## 深化 · Visitor 回调（连接→会话）

| 回调 | 语义 | 锚点 |
|---|---|---|
| OnStreamFrame | 收到 STREAM 帧数据 | `quic_connection.h:133` |
| OnWriteBlocked | 出站被反压 | `quic_connection.h:174` |
| OnCanWrite | 反压解除可继续发 | `quic_connection.h:181` |
| OnConnectionClosed | 连接终止 | `quic_connection.h:170` |
| OnConnectionMigration | 对端地址变化 | `quic_connection.h:187` |

## 调优要点（关键开关）

- 应用继承 `QuicStream`/`QuicSpdyStream` 重写 `OnDataAvailable`，别裸拆帧。
- 大量小流用流复用而非新建连接，摊薄握手成本。
- 写反压时靠 `OnCanWrite` 回调续写，别忙轮询。
- 一连接一线程串行访问，避免自加锁。

## 常见误区与工程要点

- **一请求一连接**：QUIC 是一连接多流，Session 管多个 Stream。
- **主动轮询读**：QUICHE 用 Visitor 回调推数据（`OnStreamFrame`→`OnDataAvailable`），非轮询。
- **绕过 Session 直操 Connection**：应用面向 Session/Stream API，Connection 是内部状态机。
- **跨线程调用同一连接**：需串行化到归属线程。

## 一句话总纲

**会话与连接是 QUICHE 的核心编程接触面：三层对象 `QuicConnection`（状态机）→ `QuicSession`（`quic_session.h:62`，管所有流、`GetOrCreateStream:714`/`WritevData:530`）→ `QuicStream`（`quic_stream.h:158`，收发缓冲+流控+`OnDataAvailable:69`）；连接经 `QuicConnectionVisitorInterface`（`quic_connection.h:128`）把 `OnStreamFrame`/`OnCanWrite`/`OnConnectionClosed` 等事件回调上层，QuicSession 正是 Connection 的 Visitor（`OnStreamFrame:292`/`OnCanWrite:307`）——C++ OO 观察者模式的控制反转，是应用操作 QUIC 的主 API。**
