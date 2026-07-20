# Google QUICHE 核心原理 · 支撑能力域 · 连接管理与迁移

> **定位**：连接身份与移动性——连接由 Connection ID 标识（非四元组），换网/IP 变而连接不断，路径迁移经 PATH_CHALLENGE 验证防伪造。核实基准：`quic/core/quic_connection_id_manager.h`、`quic_path_validator.h`、`quic_connection.h`。

## 一、Connection ID + 路径验证

![CID与路径验证](Quiche原理_支撑_连接管理与迁移_01CID与路径验证.svg)

**连接标识**：TCP 连接 = 四元组（src/dst IP+port），换 WiFi→蜂窝 IP 变即断连、NAT 重绑也可能断；QUIC 连接 = **Connection ID**，IP/端口变了 CID 不变→连接存活。两侧各自管一组 CID：`QuicPeerIssuedConnectionIdManager`（`quic_connection_id_manager.h:57`）管对端下发的 CID，`OnNewConnectionIdFrame`（`:70`）收 NEW_CONNECTION_ID 帧入库、`ConsumeOneUnusedConnectionId`（`:81`）取一个可用 CID 用于新路径；`QuicSelfIssuedConnectionIdManager`（`:124`）管本端签发给对端的 CID，经 `QuicConnectionIdManagerVisitorInterface`（`:46`）通知连接。RETIRE_CONNECTION_ID 帧弃用旧 CID、轮换防被动关联跟踪。

**路径迁移与验证**：连接检测到新对端地址→`OnConnectionMigration`（`quic_connection.h:187`）触发路径验证（不盲信，防地址伪造放大攻击）；`QuicPathValidator`（`quic_path_validator.h:136`）`StartPathValidation`（`:183`）在新路径发最多 3 个 PATH_CHALLENGE（随机数挑战），对端 PATH_RESPONSE 原样回→证明双向可达；验证前对新路径限速防放大；连接关闭走 CONNECTION_CLOSE 帧 + 排空期（drain）容迟到包。

**换网时序**：手机切蜂窝源 IP 变（CID 不变）→连接 `OnConnectionMigration`（`:187`）感知新地址→`QuicPathValidator` 发 PATH_CHALLENGE→客户端回 PATH_RESPONSE 证明可达→连接继续不重建（重置拥塞状态防新路径过发）。

## 二、迁移为何必须验证

若不验证即在新地址上全速回包，攻击者可伪造受害者 IP 做源、诱导服务端把大流量打向受害者（反射放大）。故 QUIC 规定：见到新路径先走 `QuicPathValidator`（`:136`）的 PATH_CHALLENGE/RESPONSE 往返证明该地址真能收包，验证通过前受放大限额约束（见抗攻击主线）。迁移成功后拥塞状态需重置——新路径带宽/RTT 未知，沿用旧 cwnd 会瞬间过发。CID 轮换（`ConsumeOneUnusedConnectionId:81`）还兼顾隐私：每换路径用新 CID，中间盒无法凭 CID 跨路径关联同一用户。

## 深化 · Connection ID 管理

| 组件 | 职责 | 锚点 |
|---|---|---|
| QuicPeerIssuedConnectionIdManager | 管对端下发的 CID | `quic_connection_id_manager.h:57` |
| OnNewConnectionIdFrame | 收 NEW_CONNECTION_ID 入库 | `quic_connection_id_manager.h:70` |
| ConsumeOneUnusedConnectionId | 取可用 CID 换路径 | `quic_connection_id_manager.h:81` |
| QuicSelfIssuedConnectionIdManager | 管本端签发的 CID | `quic_connection_id_manager.h:124` |
| VisitorInterface | 通知连接 CID 变化 | `quic_connection_id_manager.h:46` |

## 深化 · 路径验证与迁移

| 环节 | 方法/帧 | 锚点 |
|---|---|---|
| 感知对端地址变化 | OnConnectionMigration | `quic_connection.h:187` |
| 路径验证器 | QuicPathValidator | `quic_path_validator.h:136` |
| 启动验证（发 PATH_CHALLENGE） | StartPathValidation | `quic_path_validator.h:183` |
| CID 轮换 | RETIRE_CONNECTION_ID 帧 | `frames/` |
| 主动关连接 | CONNECTION_CLOSE 帧 + 排空期 | `frames/` |

## 深化 · 路径验证器状态

`QuicPathValidator`（`quic_path_validator.h:136`）对一条待验证路径最多发 3 个 PATH_CHALLENGE，每个带不同随机数，任一 PATH_RESPONSE 原样回即算通过；超时未回则判验证失败、放弃该路径。它经 `QuicPathValidationContext` 抽象"在哪条路径上用哪个 writer 发挑战"，`StartPathValidation`（`:183`）启动挑战并挂重试定时器（经 QuicAlarm，见 IO 主线）。验证期间对新路径的出站受放大限额约束（见抗攻击主线）——这保证"未证真的地址不会被用来放大攻击"。

| 环节 | 说明 | 锚点 |
|---|---|---|
| 验证器 | 最多 3 个 PATH_CHALLENGE | `quic_path_validator.h:136` |
| 启动验证 | 发挑战 + 挂重试定时器 | `quic_path_validator.h:183` |
| 感知迁移 | 连接侧回调 | `quic_connection.h:187` |

## 调优要点（关键开关）

- 预下发多个 CID（`ConsumeOneUnusedConnectionId:81`）支持无缝迁移。
- 迁移后重置拥塞窗口，重新探测新路径带宽。
- CID 长度权衡负载均衡路由 vs 隐私。
- 排空期长度权衡资源 vs 迟到包处理。

## 常见误区与工程要点

- **连接绑 IP**：QUIC 连接绑 CID，不绑四元组，换网不断。
- **迁移即无验证**：新路径必经 `QuicPathValidator`（`:136`）PATH_CHALLENGE 验证防伪造放大。
- **迁移后照旧发**：应重置拥塞状态，新路径带宽未知。
- **CID 固定**：CID 应经 RETIRE_CONNECTION_ID 轮换以防被动关联跟踪。

## 一句话总纲

**连接管理与迁移是 QUICHE 的移动性基石：连接由 Connection ID 标识而非四元组，换 WiFi/蜂窝、IP 变而 CID 不变故连接不断；`QuicPeerIssuedConnectionIdManager`（`quic_connection_id_manager.h:57`）`OnNewConnectionIdFrame`（`:70`）管对端 CID、`ConsumeOneUnusedConnectionId`（`:81`）换路径取新 CID 并轮换防跟踪；对端地址变化经 `OnConnectionMigration`（`quic_connection.h:187`）感知，`QuicPathValidator`（`quic_path_validator.h:136`）`StartPathValidation`（`:183`）发 PATH_CHALLENGE/RESPONSE 验证可达（防地址伪造放大）、验证前限速、迁移后重置拥塞——这是移动端 QUIC 体验远胜 TCP 的关键。**
