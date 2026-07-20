# Google QUICHE 核心原理 · 接口主线 · IO 与事件驱动

> **定位**：灵魂接触面——库不碰真实 socket/时钟，经 `ProcessUdpPacket`（入）/`QuicPacketWriter`（出）/`QuicAlarm`（时钟）三个抽象由应用驱动。是 QUICHE 可嵌 Chromium/Envoy/测试的根源。核实基准：`quic/core/quic_connection.h`、`quic_packet_writer.h`、`quic_alarm.h`、`quic_alarm_factory.h`、`io/quic_event_loop.h`。

## 一、三个契约点 + 事件循环

![收发驱动](Quiche原理_IO事件_01收发驱动.svg)

应用与库的三个契约点：**① 入站 ProcessUdpPacket**（socket 收到 UDP 报→`QuicConnection::ProcessUdpPacket`，`quic_connection.h:692`，带 self/peer 地址，内部解密解帧、更新状态机、经 Visitor 回调把帧事件推给上层）；**② 出站 QuicPacketWriter**（库要发包时调应用注入的 Writer→`WritePacket`（`quic_packet_writer.h:116`）→`sendto`；写阻塞时 `IsWriteBlocked`（`:123`）返 true、`WritePacket` 返 `WRITE_STATUS_BLOCKED`→库暂停发送，socket 可写后应用调 `SetWritable`（`:127`）+ 连接的 `OnCanWrite`（`quic_connection.h:707`）恢复；Writer 由 `SetQuicPacketWriter`（`:723`）注入、`writer_` 成员持有（`:2229`））；**③ 时钟 QuicAlarm**（库要计时→应用注入的 `QuicAlarmFactory::CreateAlarm`（`quic_alarm_factory.h:23`）建 `QuicAlarm`（`quic_alarm.h:20`），库调 `Set`（`:67`）设截止时间、到点回调 `Delegate::OnAlarm`（`:34`）；`alarm_factory_` 成员（`quic_connection.h:2226`）由构造函数注入（`:562`）；用途覆盖重传/PTO、pacing、idle/keepalive、ack、MTU 探测（`OnMtuDiscoveryAlarm` `:1116`），全无库自跑线程）。库还经 `QuicConnectionHelperInterface`（`quic_connection.h:528`）拿 `GetClock`（`:533`）时钟与 `GetRandomGenerator`（`:536`）随机数——连时间与熵都由应用提供，这是确定性测试（注入假时钟/假随机）的基础。

## 二、控制反转：谁调谁

方向上分两半：**应用→库**只有一个入口 `ProcessUdpPacket`（喂一个收到的 UDP 报字节 + 双端地址）；**库→应用**经三条回路——出站 `WritePacket`、计时 `QuicAlarm`/`OnAlarm`、语义事件 `QuicConnectionVisitorInterface`（`quic_connection.h:128`，`OnStreamFrame:133`/`OnWriteBlocked:174`/`OnCanWrite:181`/`OnConnectionClosed:170`）。典型事件循环：应用用 `QuicEventLoop`（`io/quic_event_loop.h:42`，`RegisterSocket:56`、`CreateAlarmFactory:78`）等 socket 可读或 alarm 到期→可读则 recv 后 `ProcessUdpPacket`→库内部按需 `WritePacket` 发包 / `Set` 闹钟→alarm 到期触发 `OnAlarm` 处理超时重传/pacing。QUICHE 自带 `io/quic_default_event_loop.h`、`io/quic_poll_event_loop.h` 两个参考实现，但生产可换成 Chromium 的 MessageLoop、Envoy 的 libevent——库只依赖 `QuicEventLoop`/`QuicPacketWriter`/`QuicAlarmFactory` 接口，不依赖任何具体 IO 栈。

## 深化 · 三个抽象的源码锚点

| 抽象 | 方向 | 核心方法 | 源码锚点 |
|---|---|---|---|
| ProcessUdpPacket | 入站 | 喂 UDP 报，触发解密解帧 | `quic_connection.h:692` |
| QuicPacketWriter | 出站 | WritePacket 把包写 socket | `quic_packet_writer.h:116` |
| IsWriteBlocked / SetWritable | 反压 | 写阻塞探测与解除 | `quic_packet_writer.h:123` / `:127` |
| OnCanWrite | 反压 | 阻塞解除后库恢复发送 | `quic_connection.h:707` |
| QuicAlarm::Set / Delegate::OnAlarm | 时钟 | 设截止时间 / 到点回调 | `quic_alarm.h:67` / `:34` |
| QuicAlarmFactory::CreateAlarm | 时钟 | 应用建库要的定时器 | `quic_alarm_factory.h:23` |
| QuicConnectionHelperInterface | 辅助 | GetClock / GetRandomGenerator | `quic_connection.h:528`（`:533`/`:536`） |
| QuicEventLoop | 编排 | RegisterSocket / CreateAlarmFactory | `io/quic_event_loop.h:56` / `:78` |

## 深化 · 失败与边界路径

| 场景 | 库的行为 | 锚点 |
|---|---|---|
| Writer 返回 BLOCKED | 停发、置写阻塞、等 SetWritable+OnCanWrite | `quic_packet_writer.h:123`、`quic_connection.h:707` |
| Writer 返回 ERROR | 关连接（写失败不可恢复） | `quic_packet_writer.h` WriteResult |
| MSG_TOO_BIG | IsMsgTooBig 判定、降 MTU | `quic_connection.h:714` |
| alarm 未接事件循环 | OnAlarm 不触发→重传/keepalive 失效 | `quic_alarm.h:34` |
| 包超 MTU | SendMtuDiscoveryPacket 探测上限 | `quic_connection.h:1103` |

## 调优要点（关键开关）

- Writer 支持 GSO/批量发降 syscall；务必实现好 `IsWriteBlocked`/`SetWritable`/`OnCanWrite` 三件套，别丢包。
- Alarm 对接 epoll timerfd/事件循环定时器，精度直接影响重传与 pacing。
- 高吞吐用 recvmmsg/GRO 批量收，再逐包 `ProcessUdpPacket`。
- 单线程事件循环最常见；多线程须把同一连接的调用串行化到其归属线程。
- 注入假 `QuicClock`/`QuicRandom` 做确定性重放测试（QUICHE 测试栈的核心手法）。

## 常见误区与工程要点

- **以为库自己收发**：库经 `WritePacket`/`ProcessUdpPacket` 抽象，socket 归应用。
- **不处理写阻塞**：Writer 返回 `WRITE_STATUS_BLOCKED` 却不实现 `SetWritable`+`OnCanWrite` 会卡死发送。
- **Alarm 不接事件循环**：`OnAlarm` 不触发→重传/keepalive/pacing 全失效。
- **多线程乱用**：一个连接的调用需串行化到其所属线程，QUICHE 不做内部锁。
- **以为有内部时钟**：连时间都经 `GetClock` 取，库无 `now()` 直调。

## 一句话总纲

**IO 与事件驱动是 QUICHE 的灵魂接触面：库不碰真实 socket/时钟，而经三个抽象由应用驱动——入站 `ProcessUdpPacket`（`quic_connection.h:692`）喂 UDP 报、出站 `QuicPacketWriter::WritePacket`（`quic_packet_writer.h:116`）让库发包并用 `IsWriteBlocked`/`SetWritable`/`OnCanWrite` 做反压、时钟 `QuicAlarm`（`quic_alarm.h:20`）让库计时（重传/PTO/pacing/idle），连时钟与随机数都经 `QuicConnectionHelperInterface`（`:528`）注入；应用在自己的 `QuicEventLoop`（`io/quic_event_loop.h:42`）里编排收包→库处理→按需发包/设闹钟，可注入模拟做确定性测试——这是它可嵌 Chromium/Envoy 的根源。**
