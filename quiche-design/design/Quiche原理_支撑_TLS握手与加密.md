# Google QUICHE 核心原理 · 支撑能力域 · TLS 握手与加密

> **定位**：安全地基——TLS 1.3 内嵌于 QUIC 传输，`QuicCryptoStream` 经 CRYPTO 帧跑握手，按 Initial/Handshake/1-RTT 三级密钥分层保护。核实基准：`quic/core/quic_crypto_stream.h`、`quic/core/crypto/`。

## 一、加密级与握手承载

![加密级](Quiche原理_支撑_TLS握手与加密_01加密级.svg)

**三个加密级逐步升级**：**Initial**（用连接 ID 派生的公开密钥，人人可算，仅防篡改不防窃听）→ **Handshake**（ClientHello/ServerHello 交换后派生，保护握手消息）→ **1-RTT**（握手完成后保护应用数据，密钥可轮换 Key Update）。**承载**：`QuicCryptoStream`（`:54`）是特殊 QuicStream，走 CRYPTO 帧传 TLS 消息（不占流号）；`crypto/` 目录做 TLS 适配 + AEAD 载荷加密认证 + 包号头单独 header protection。**0-RTT**：复用会话票据的首包即带应用数据（有重放风险，需应用侧幂等保护）。**1-RTT 握手时序**：Client→ClientHello（Initial 级+密钥参数）→Server→ServerHello+证书（派生 Handshake/1-RTT）→Client→Finished→双向 1-RTT 加密应用数据。相比 TCP+TLS 的 2-RTT，QUIC 把传输握手与 TLS 合一省一个 RTT。

---

## 拓展 · 密钥与保护

| 机制 | 作用 |
|---|---|
| AEAD | 载荷加密 + 完整性认证 |
| Header Protection | 遮蔽包号等头部字段 |
| Key Update | 1-RTT 密钥定期轮换 |
| 0-RTT | 首包带数据（重放风险） |
| 加密级隔离 | 不同级密钥独立，防降级 |

---

## 调优要点（关键开关）

- 会话票据 + 0-RTT 降建连延迟，但需防重放。
- 证书链精简、OCSP stapling 降握手体积。
- Key Update 频率权衡安全 vs 开销。
- 握手包 coalesce 减少往返。

---

## 常见误区与工程要点

- **TLS 在 QUIC 之上**：反了——TLS 1.3 内嵌在 QUIC 握手里，共用一套消息。
- **Initial 密钥保密**：Initial 密钥公开，只防篡改不防窃听。
- **0-RTT 随便用**：0-RTT 数据可被重放，非幂等操作危险。
- **握手数据走 STREAM**：握手走 CRYPTO 帧，不占用流号。

---

## 一句话总纲

**TLS 握手与加密是 QUICHE 的安全地基：TLS 1.3 内嵌进 QUIC 传输握手，QuicCryptoStream 经 CRYPTO 帧交换 TLS 消息，密钥按 Initial→Handshake→1-RTT 三级升级、载荷用 AEAD 加密 + 包号 header protection；1-RTT 握手比 TCP+TLS 省一个往返，0-RTT 可复用票据首包带数据（有重放风险）——传输与加密合一是 QUIC 低延迟安全的核心。**
