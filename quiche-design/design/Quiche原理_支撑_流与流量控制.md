# Google QUICHE 核心原理 · 支撑能力域 · 流与流量控制

> **定位**：多路复用的核心——一连接多条独立流、消除队头阻塞，`QuicFlowController` 做流级+连接级两级窗口，`QuicConfig` 管流数上限。核实基准：`quic/core/quic_flow_controller.h`、`quic_stream.h`、`quic_config.h`。

## 一、多流 + 两级流控

![多流两级窗](Quiche原理_支撑_流与流量控制_01多流两级窗.svg)

**一连接多流（对比 TCP）**：TCP 是单有序字节流，一处丢包全队阻塞，HTTP/2 的多路复用仍受 TCP 层队头阻塞拖累；QUIC 一连接多条独立流，流 A 丢包只阻塞 A、流 B/C 照常交付（流号奇偶区分主/被动发起、双向/单向）。**两级流量控制**：**流级** `QuicFlowController`（`:37`，每流独立窗口，收方经 MAX_STREAM_DATA 拨额度）+ **连接级**（所有流字节总和窗口，MAX_DATA 更新，防单连接吃爆内存）。**流数上限**：`QuicConfig`（`:311` SetMaxBidirectionalStreamsToSend）设初值，MAX_STREAMS 帧动态放开。**反压闭环**：发方按双窗口发→窗口耗尽发 BLOCKED 帧暂停→收方消费后拨额度（MAX_DATA/MAX_STREAM_DATA）→发方窗口滑动恢复。

---

## 拓展 · 流与窗口

| 机制 | 层级 | 帧 |
|---|---|---|
| 流级流控 | 单流 | MAX_STREAM_DATA / STREAM_DATA_BLOCKED |
| 连接级流控 | 全连接 | MAX_DATA / DATA_BLOCKED |
| 流数上限 | 全连接 | MAX_STREAMS / STREAMS_BLOCKED |
| 流中止 | 单流 | RESET_STREAM / STOP_SENDING |

---

## 调优要点（关键开关）

- 初始窗口（stream/connection）越大越省 RTT，但吃内存。
- 自动调窗（auto-tuning）按 BDP 放大窗口。
- 流数上限权衡并发 vs 资源。
- 及时发 MAX_DATA 避免发方饿死。

---

## 常见误区与工程要点

- **QUIC 无队头阻塞是绝对的**：流内仍有序，只是流间独立；同一流丢包仍阻塞该流。
- **只有一级流控**：QUIC 是流级 + 连接级两级。
- **流可无限开**：受流数上限约束，需 MAX_STREAMS 放开。
- **窗口不更新**：不发 MAX_DATA 会把发方卡死。

---

## 一句话总纲

**流与流量控制是 QUICHE 多路复用的核心：一条连接承载多条独立流、流间无队头阻塞（区别于 TCP 单字节流），QuicFlowController 做流级 + 连接级两级窗口反压、QuicConfig 管流数上限；发方受双窗口约束、耗尽发 BLOCKED、收方消费后经 MAX_DATA/MAX_STREAM_DATA 拨额度——这是 QUIC 相比 TCP+HTTP/2 消除队头阻塞的关键。**
