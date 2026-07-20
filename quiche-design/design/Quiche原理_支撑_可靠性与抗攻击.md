# Google QUICHE 核心原理 · 支撑能力域 · 可靠性与抗攻击

> **定位**：入口防线——`QuicDispatcher` 作服务端关卡，抗放大（3 倍限额）、抗 DoS（Retry 地址验证 + 缓冲限流）、抗指纹（ChaosProtector）。核实基准：`quic/core/quic_dispatcher.h`、`quic_buffered_packet_store.h`、`quic_chaos_protector.h`、`quic_utils.h`。

## 一、三类威胁与 Dispatcher 防护

![入口防护](Quiche原理_支撑_可靠性与抗攻击_01入口防护.svg)

**三类威胁与防护**：**放大攻击**（伪造源 IP 让服务端猛回包做反射放大）→ 未验证地址前回包 ≤ 收到的 3 倍（anti-amplification limit，RFC 9000 §8）；**洪泛 DoS**（海量新连接 Initial 打爆内存/CPU）→ Retry 强制地址验证 + 缓冲/限流，`QuicBufferedPacketStore`（`quic_buffered_packet_store.h:57`）`EnqueuePacket`（`:199`）暂存乱序/早到 Initial、CHLO 齐后 `DeliverPackets`（`:235`）/`DeliverPacketsForNextConnection`（`:256`）交付建连；**指纹/审查**（Initial 结构可被中间盒识别封锁）→ `QuicChaosProtector`（`quic_chaos_protector.h:26`）`BuildDataPacket`（`:42`）打乱首包帧布局抗指纹。

**Dispatcher 关卡**（`quic_dispatcher.h:62`）：`ProcessPacket`（`:85`）所有入站包先过它→`MaybeDispatchPacket`（`:220`）按 CID 分流/判新连接/丢无效包；新连接经 `TryExtractChloOrBufferEarlyPacket`（`:379`）提取 CHLO 或缓冲，判定放行才 `CreateQuicSession`（`:209`），资源不足则 `OnNewConnectionRejected`（`:321`）拒绝；不认识的短头包 `MaybeResetPacketsWithNoVersion`（`:339`）回 Stateless Reset（令牌由 `QuicUtils::GenerateStatelessResetToken` `quic_utils.h:195` 生成）。Retry 回令牌要求客户端带回证明源地址真实才建 Session。

**Retry 时序**：Client→Initial（源未验证）→Server→Retry(令牌，不建状态)→Client→Initial(带令牌)→Server 校验→`CreateQuicSession`（`:209`）建 Session。

## 二、把攻击挡在建立状态之前

抗攻击的核心思想是"未验证前不投入资源"：地址未证真前，服务端既受 3× 放大限额约束（回包不超收包 3 倍），又可用 Retry 把建立连接状态（内存、crypto 计算）推迟到客户端证明地址可达之后——Retry 本身无状态（服务端不为它存任何东西，令牌自校验）。早到但 CHLO 未齐的 Initial 先进 `QuicBufferedPacketStore`（`:57`）有界缓冲，缓冲满即丢而非无限堆积。Stateless Reset 则让重启后收到旧连接包的服务端，无需保留状态也能让对端优雅关连接。这套"无状态优先 + 有界缓冲 + 放大限额"是 QUIC 面向开放公网部署的安全基石。

## 深化 · 三类威胁与防护

| 威胁 | 防护 | 锚点 |
|---|---|---|
| 反射放大 | 3× anti-amplification limit | RFC 9000 §8 / `quic_connection.h` |
| 洪泛 DoS | Retry + 缓冲 + 限流 | `quic_dispatcher.h:62` / `quic_buffered_packet_store.h:57` |
| 指纹/审查 | Initial 帧布局打乱 | `quic_chaos_protector.h:26` |
| 迟到/无效包 | Stateless Reset | `quic_utils.h:195` |

## 深化 · Dispatcher 与缓冲关键方法

| 环节 | 方法 | 锚点 |
|---|---|---|
| 入站总入口 | ProcessPacket | `quic_dispatcher.h:85` |
| 分流/判新连接 | MaybeDispatchPacket | `quic_dispatcher.h:220` |
| 提取 CHLO 或缓冲 | TryExtractChloOrBufferEarlyPacket | `quic_dispatcher.h:379` |
| 放行建会话 | CreateQuicSession | `quic_dispatcher.h:209` |
| 资源不足拒绝 | OnNewConnectionRejected | `quic_dispatcher.h:321` |
| 缓冲早到 Initial | EnqueuePacket | `quic_buffered_packet_store.h:199` |
| CHLO 齐后交付 | DeliverPackets | `quic_buffered_packet_store.h:235` |
| 生成重置令牌 | GenerateStatelessResetToken | `quic_utils.h:195` |

## 深化 · CHLO 提取与建连门槛

判定一个 Initial 是否够格建连的关键是能否提取出完整 ClientHello（CHLO）。旧格式用 `ChloExtractor::Extract`（`chlo_extractor.h:33`），TLS 1.3 用 `tls_chlo_extractor.h`——从（可能跨多个乱序 Initial 的）CRYPTO 帧里拼出 CHLO，读出 SNI/ALPN 等参数供 `CreateQuicSession`（`quic_dispatcher.h:209`）决策。CHLO 未齐则包进 `QuicBufferedPacketStore`（`quic_buffered_packet_store.h:57`）`EnqueuePacket`（`:199`）等待，齐了 `DeliverPackets`（`:235`）交付建连；缓冲有界，满即丢——攻击者无法靠海量半截 Initial 撑爆内存。这道"先提 CHLO、够格才建状态"的门槛，是把 DoS 挡在连接状态之前的具体落点。

| 环节 | 组件 | 锚点 |
|---|---|---|
| 提取 CHLO（旧格式） | ChloExtractor::Extract | `chlo_extractor.h:33` |
| 提取 CHLO（TLS 1.3） | TlsChloExtractor | `tls_chlo_extractor.h` |
| 缓冲未齐 Initial | EnqueuePacket | `quic_buffered_packet_store.h:199` |

## 调优要点（关键开关）

- 高负载下开 Retry 强制地址验证防洪泛。
- 缓冲区大小（`QuicBufferedPacketStore:57`）权衡容忍乱序 vs 内存耗尽。
- 放大限额与握手包体积权衡建连速度。
- 限流阈值按部署规模调，防单源打爆。

## 常见误区与工程要点

- **服务端可随便回包**：未验证地址前受 3 倍放大限额约束。
- **Retry 总是必需**：Retry 是可选防护，负载高/疑似攻击时启用；本身无状态。
- **Dispatcher 只做路由**：它还是抗 DoS/放大的核心入口关卡（`MaybeDispatchPacket:220`）。
- **首包结构固定**：`QuicChaosProtector`（`:26`）会打乱 Initial 抗指纹与审查。

## 一句话总纲

**可靠性与抗攻击是 QUICHE 的入口防线：`QuicDispatcher`（`quic_dispatcher.h:62`）作服务端关卡 `ProcessPacket`（`:85`）先过所有入站包，用 3 倍 anti-amplification limit 抗反射放大、Retry 地址验证 + `QuicBufferedPacketStore`（`quic_buffered_packet_store.h:57`）`EnqueuePacket`（`:199`）有界缓冲抗洪泛 DoS、`QuicChaosProtector`（`quic_chaos_protector.h:26`）打乱 Initial 抗指纹审查、Stateless Reset（`quic_utils.h:195`）处理迟到包；`TryExtractChloOrBufferEarlyPacket`（`:379`）判放行才 `CreateQuicSession`（`:209`）——把攻击挡在建立连接状态之前，是 QUIC 面向公网部署的安全基石。**
