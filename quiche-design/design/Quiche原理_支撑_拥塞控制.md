# Google QUICHE 核心原理 · 支撑能力域 · 拥塞控制

> **定位**：带宽治理——可插拔 `SendAlgorithmInterface`，内置 BBRv1/v2 与 CUBIC，全用户态实现故可热切换/快速实验。核实基准：`congestion_control/send_algorithm_interface.h`、`bbr2_sender.h`、`tcp_cubic_sender_bytes.h`。

## 一、可插拔算法 + BBR 阶段

![可插拔算法](Quiche原理_支撑_拥塞控制_01可插拔算法.svg)

**可插拔**：`SendAlgorithmInterface`（`:32`）统一接口（OnPacketSent/OnCongestionEvent/CanSend），实现有 **BBRv1/BBRv2**（`bbr2_sender.h:27`，测带宽×RTT 建模、不靠丢包信号）与 **CUBIC**（`tcp_cubic_sender_bytes.h`，丢包驱动、三次函数增窗、TCP 兼容）；全用户态实现，无需内核改动，同一 socket 不同连接可用不同算法、便于实验迭代（Google 借此在真实流量上快速试新算法）。**BBR 四阶段**：Startup（指数探带宽，带宽不再增即退）→ Drain（排空 Startup 造的队列）→ ProbeBW（周期探带宽、稳态巡航）→ ProbeRTT（周期降窗测最小 RTT）。**cwnd + Pacing 协作**：算法给出拥塞窗口 + pacing rate→在途字节 < cwnd 才可发（CanSend 门禁）→Pacing 经 Alarm 定时按速率均匀发→避免突发丢包。

---

## 拓展 · 算法对比

| 算法 | 信号 | 特点 |
|---|---|---|
| BBRv1/v2 | 带宽 + RTT 建模 | 高吞吐、抗随机丢包、低排队 |
| CUBIC | 丢包 | TCP 友好、成熟稳定 |
| PCC / 实验算法 | 各异 | 用户态便于灰度 |
| Pacing | — | 平滑注入，配合任意算法 |

---

## 调优要点（关键开关）

- BBR 适合高带宽长肥管道 + 有随机丢包链路。
- CUBIC 在与 TCP 竞争的环境更公平。
- Pacing 精度依赖 Alarm 精度。
- 初始 cwnd（IW10 等）影响短连接性能。

---

## 常见误区与工程要点

- **拥塞控制在内核**：QUIC 拥塞控制在用户态，可随版本升级、热切换。
- **只有丢包一种信号**：BBR 用带宽/RTT 建模，不依赖丢包。
- **cwnd 就够了**：还需 Pacing 平滑注入，否则突发致丢。
- **一个算法通吃**：按链路特性选 BBR/CUBIC，QUICHE 支持并存。

---

## 一句话总纲

**拥塞控制是 QUICHE 的带宽治理层：SendAlgorithmInterface 统一可插拔接口，内置 BBRv1/v2（带宽×RTT 建模、不靠丢包）与 CUBIC（丢包驱动、TCP 友好），全用户态实现故能热切换、快速在真实流量上实验；算法给出 cwnd + pacing rate，在途 < cwnd 才可发、Pacing 经 Alarm 均匀注入避免突发丢包——用户态可迭代是 QUIC 拥塞控制演进快的根源。**
