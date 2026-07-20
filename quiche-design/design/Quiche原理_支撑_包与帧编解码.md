# Google QUICHE 核心原理 · 支撑能力域 · 包与帧编解码

> **定位**：线格式的门面——`QuicFramer` 解析入向、`QuicPacketCreator` 组装出向，把字节流 ↔ 结构化帧。是所有 QUIC 语义的字节层地基。核实基准：`quic/core/quic_framer.h`、`quic_packet_creator.h`、`quic_coalesced_packet.h`、`quic/core/frames/`。

## 一、层次与两个门面

![线格式](Quiche原理_支撑_包与帧编解码_01线格式.svg)

**层次**：一个 UDP 载荷 = 一或多个 QUIC 包（`QuicCoalescedPacket`（`quic_coalesced_packet.h:18`）可把 Initial/Handshake/1-RTT 合并进一个 UDP 报，降 RTT/syscall）；每包 = 包头（长头握手/短头 1-RTT）+ 加密包号 + 受保护载荷；载荷 = 帧序列（`frames/`：STREAM/ACK/CRYPTO/MAX_DATA/PING/RESET…）；帧内类型/长度/偏移用变长整数（varint）省字节。

**两个门面**：**`QuicFramer`**（`quic_framer.h:283`，入向）——`ProcessPacket`（`:359`）解密（`DecryptPayload` `:936`，认证失败即静默丢弃、不泄露状态）→`ProcessFrameData`（`:904`）拆帧→逐帧回调 `QuicFramerVisitorInterface`（`:76`，`OnStreamFrame:154`/OnAckFrame/OnCryptoFrame…），负责版本协商、包号恢复（包号在网上是截断的，需按已确认最大包号补全）；**`QuicPacketCreator`**（`quic_packet_creator.h:52`，出向）——`AddFrame`（`:253`）把帧塞进当前包、`ConsumeDataToFillCurrentPacket`（`:170`）填流数据、`SetMaxPacketLength`（`:368`）控 MTU、`FlushCurrentPacket`（`:198`）决定封包时机、`SerializePacket`（`:579`）加密+分配包号→交 Writer；`QuicChaosProtector`（见抗攻击）打乱 Initial 抗指纹。

**链路位置**：UDP 入→Framer `ProcessPacket` 解→Connection 处理→Creator 组包 `SerializePacket`→Writer 发。

## 二、包号恢复与头保护

QUIC 包号在线上按 1/2/3/4 字节截断编码，收端用"最近确认的最大包号 + 半窗回绕"算法补全成 64 位单调值——`QuicFramer` 在解密前先做 header protection 去保护（用 HP key 异或首字节 + 包号字段），才知道包号长度与真实包号，再 `DecryptPayload`（`:936`）用对应加密级密钥解 AEAD。这套"先去头保护、再解载荷"的双层顺序，是防中间盒基于包号做流量分析的关键。认证失败的包在 `ProcessPacket`（`:359`）里被丢弃、连接状态不变。

## 深化 · 入向 QuicFramer

| 环节 | 方法 | 锚点 |
|---|---|---|
| 类定义 | QuicFramer | `quic_framer.h:283` |
| 解一个包 | ProcessPacket | `quic_framer.h:359` |
| 解 AEAD 载荷 | DecryptPayload | `quic_framer.h:936` |
| 拆帧循环 | ProcessFrameData | `quic_framer.h:904` |
| 帧回调接口 | QuicFramerVisitorInterface | `quic_framer.h:76` |
| STREAM 帧回调 | OnStreamFrame | `quic_framer.h:154` |

## 深化 · 出向 QuicPacketCreator

| 环节 | 方法 | 锚点 |
|---|---|---|
| 类定义 | QuicPacketCreator | `quic_packet_creator.h:52` |
| 加一个帧 | AddFrame | `quic_packet_creator.h:253` |
| 填流数据 | ConsumeDataToFillCurrentPacket | `quic_packet_creator.h:170` |
| 控 MTU | SetMaxPacketLength | `quic_packet_creator.h:368` |
| 封包时机 | FlushCurrentPacket | `quic_packet_creator.h:198` |
| 序列化+加密 | SerializePacket | `quic_packet_creator.h:579` |
| 多包合并 UDP | QuicCoalescedPacket | `quic_coalesced_packet.h:18` |

## 深化 · varint 与帧字段编码

QUIC 的所有可变长字段（流号、偏移、长度、包号区间…）用 RFC 9000 的变长整数：最高两位标编码长度（1/2/4/8 字节），小值只花 1 字节。写侧由 `QuicDataWriter`（`quic_data_writer.h:25`，继承 `quiche::QuicheDataWriter`）的 `WriteVarInt62`（`common/quiche_data_writer.h:89`）输出、读侧对称解析；`QuicPacketCreator::AddFrame`（`quic_packet_creator.h:253`）在组包时正是靠 varint 精算每帧占用、决定还能塞下多少数据（`ConsumeDataToFillCurrentPacket` `:170`）。帧类型本身也是 varint，故帧类型空间可无痛扩展——这是 QUIC 相比固定头 TCP 选项更省字节、更易演进的底层原因。

## 调优要点（关键开关）

- coalesce 合并握手包（`quic_coalesced_packet.h:18`）降 RTT/syscall。
- MTU 探测（PMTUD）+ `SetMaxPacketLength`（`:368`）提升单包载荷。
- varint 编码对小值友好，帧顺序影响解析成本。
- 认证失败包静默丢弃（`ProcessPacket:359`），不泄露状态。

## 常见误区与工程要点

- **包 = 帧**：一个包内可含多个不同类型帧，一个 UDP 报可含多个包。
- **包号明文**：包号受 header protection + AEAD 双层保护，需先去保护再解密恢复。
- **STREAM 帧才是数据**：握手数据走 CRYPTO 帧，不占流号。
- **忽略 coalesce**：不合并握手包会多花 RTT。

## 一句话总纲

**包与帧编解码是 QUICHE 的字节层地基：`QuicFramer`（`quic_framer.h:283`）入向 `ProcessPacket`（`:359`）先去头保护、`DecryptPayload`（`:936`）解 AEAD、`ProcessFrameData`（`:904`）拆帧并经 `QuicFramerVisitorInterface`（`:76`）逐帧回调；`QuicPacketCreator`（`quic_packet_creator.h:52`）出向 `AddFrame`（`:253`）组帧、`SerializePacket`（`:579`）加密分配包号交 Writer；一个 UDP 报可 `QuicCoalescedPacket`（`quic_coalesced_packet.h:18`）合并多包，载荷是 STREAM/ACK/CRYPTO 等帧序列、字段用 varint——这层门面之上才谈得上流、握手、拥塞等一切 QUIC 语义。**
