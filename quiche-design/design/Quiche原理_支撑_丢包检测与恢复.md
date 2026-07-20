# Google QUICHE 核心原理 · 支撑能力域 · 丢包检测与恢复

> **定位**：可靠性引擎——单调包号 + 显式 ACK，`QuicSentPacketManager` 追踪在途包、`UberLossAlgorithm` 判丢、按需用新包号重传（RFC 9002）。核实基准：`quic/core/quic_sent_packet_manager.h`、`congestion_control/uber_loss_algorithm.h`、`general_loss_algorithm.h`、`rtt_stats.h`。

## 一、包号与判丢机制

![包号与判丢](Quiche原理_支撑_丢包检测与恢复_01包号与判丢.svg)

**与 TCP 的关键区别**：QUIC 包号单调递增、永不复用——重传用新包号，故无 TCP 的"重传歧义"（Karn 问题），RTT 采样精确；ACK 帧带已收包号区间 + ACK 延迟，比 TCP SACK 表达力更强；数据与包号解耦——丢的帧内容重新封进新包重发，不重发原包。

**判丢与重传**：`QuicSentPacketManager`（`quic_sent_packet_manager.h:55`）记录每包发送时间/内容，收 ACK 时 `OnAckFrameStart`（`:365`）起处理判交付/丢失；`UberLossAlgorithm`（`congestion_control/uber_loss_algorithm.h:45`，按加密级各持一个 `GeneralLossAlgorithm` `general_loss_algorithm.h:23`）`DetectLosses`（`:56` / `general_loss_algorithm.h:34`）用**乱序阈值**（后续包号被 ACK 超过 `reordering_threshold_` `general_loss_algorithm.h:122`）+ **时间阈值**（超过 RTT×系数）判丢，`SetReorderingShift`（`uber_loss_algorithm.h:81`）调灵敏度；无 ACK 时 `OnRetransmissionTimeout`（`quic_sent_packet_manager.h:261`）触发 PTO 探测，重传时机由 `GetRetransmissionTime`（`:273`）/`GetRetransmissionMode`（`:529`）决定，`MarkForRetransmission`（`:577`）把丢失帧标记重发。

**RTT 估计**：`rtt_stats.h` 维护 `smoothed_rtt`（`:64`）、`min_rtt`（`:94`）、`latest_rtt`（`:90`）、`mean_deviation`（`:96`），由 `GetRttStats`（`quic_sent_packet_manager.h:288`）暴露，喂 PTO 与拥塞控制。

**闭环**：发 #10-#20→收 ACK 确认 #10-18/#20（#19 疑似丢）→`DetectLosses` 判 #19 丢失→`MarkForRetransmission` 把 #19 内容封进新包 #21 重发 + `OnCongestionEvent` 通知拥塞控制。

## 二、PTO 与探测重传

当既无新 ACK 也无乱序信号（如尾包全丢），乱序/时间阈值都不触发，必须靠 PTO 兜底：`OnRetransmissionTimeout`（`:261`）超时后发探测包（可携带新数据或重传旧帧），逼对端回 ACK 以恢复信号；连续 PTO 会指数退避。PTO 初值/退避直接决定尾延迟（tail latency）。`GetRetransmissionMode`（`:529`）区分握手重传、PTO、丢包重传三种模式，各有独立定时与退避策略。

## 深化 · 判丢信号

| 机制 | 触发 | 锚点 |
|---|---|---|
| 乱序阈值 | 后续包号已被 ACK 超过阈值 | `general_loss_algorithm.h:122` |
| 时间阈值 | 超过 RTT × 系数仍未 ACK | `uber_loss_algorithm.h:56` |
| PTO | 长时间无 ACK，探测性重传 | `quic_sent_packet_manager.h:261` |
| 灵敏度调节 | SetReorderingShift | `uber_loss_algorithm.h:81` |
| RTT 估计 | smoothed/min/latest/deviation | `rtt_stats.h:64`/`:94`/`:90`/`:96` |

## 深化 · QuicSentPacketManager 关键方法

| 环节 | 方法 | 锚点 |
|---|---|---|
| 类定义 | QuicSentPacketManager | `quic_sent_packet_manager.h:55` |
| 处理 ACK | OnAckFrameStart | `quic_sent_packet_manager.h:365` |
| PTO 超时 | OnRetransmissionTimeout | `quic_sent_packet_manager.h:261` |
| 下次重传时刻 | GetRetransmissionTime | `quic_sent_packet_manager.h:273` |
| 重传模式判定 | GetRetransmissionMode | `quic_sent_packet_manager.h:529` |
| 标记重传 | MarkForRetransmission | `quic_sent_packet_manager.h:577` |
| RTT 统计 | GetRttStats | `quic_sent_packet_manager.h:288` |

## 深化 · 三种重传模式

`GetRetransmissionMode`（`quic_sent_packet_manager.h:529`）把重传归为三态，各有独立定时与退避：

| 模式 | 触发 | 行为 |
|---|---|---|
| 握手重传 | 握手包未确认 | 尽快重发 CRYPTO 数据，保建连速度 |
| 丢包重传 | DetectLosses 判丢 | `MarkForRetransmission`（`:577`）把帧封新包 |
| PTO 探测 | 长时间无 ACK | `OnRetransmissionTimeout`（`:261`）发探测逼 ACK |

`GetRetransmissionTime`（`:273`）取三者中最近的截止时刻，经 QuicAlarm（见 IO 主线）挂定时器——到点回调触发相应处理。三态分离让"握手快、稳态准、尾部有兜底"三个目标互不干扰。

## 调优要点（关键开关）

- PTO 初值/退避策略（`OnRetransmissionTimeout:261`）影响尾延迟。
- 乱序阈值 / `SetReorderingShift`（`:81`）权衡误判 vs 恢复速度。
- ACK 频率（延迟 ACK）省带宽 vs RTT 精度。
- 丢包信号及时喂拥塞控制避免过发。

## 常见误区与工程要点

- **重传用原包号**：QUIC 重传用新包号，原包号永不复用。
- **RTT 有歧义**：无重传歧义，故 RTT 采样精确（`rtt_stats.h`），优于 TCP。
- **只靠超时判丢**：主要靠乱序/时间阈值（`DetectLosses:56`）快速判丢，PTO（`:261`）是兜底。
- **重发整包**：重发的是帧内容重新封的新包（`MarkForRetransmission:577`），不是原包。

## 一句话总纲

**丢包检测与恢复是 QUICHE 的可靠性引擎：包号单调递增永不复用、重传封进新包，消除 TCP 的重传歧义使 RTT 采样精确；`QuicSentPacketManager`（`quic_sent_packet_manager.h:55`）`OnAckFrameStart`（`:365`）追踪在途包，`UberLossAlgorithm`（`uber_loss_algorithm.h:45`）`DetectLosses`（`:56`）用乱序阈值（`general_loss_algorithm.h:122`）+ 时间阈值判丢、`OnRetransmissionTimeout`（`:261`）PTO 兜底探测，`MarkForRetransmission`（`:577`）把丢失帧封新包重发并通知拥塞控制，`rtt_stats.h` 精确估 RTT——数据与包号解耦是 QUIC 精准恢复的基础。**
