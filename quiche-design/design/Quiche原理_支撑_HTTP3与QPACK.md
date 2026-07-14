# Google QUICHE 核心原理 · 支撑能力域 · HTTP/3 与 QPACK

> **定位**：应用层适配——HTTP 请求映射到 QUIC 双向流，QPACK 压缩头字段且用 blocking manager 抗队头阻塞（HPACK 的 QUIC 版改造）。核实基准：`quic/core/http/`、`quic/core/qpack/`（`new_qpack_blocking_manager.h`）。

## 一、请求映射 + QPACK 压缩

![请求映射与压缩](Quiche原理_支撑_HTTP3与QPACK_01请求映射与压缩.svg)

**HTTP/3 = HTTP 语义映射到 QUIC 流**：一请求 = 一双向 QuicSpdyStream（header 帧 + data 帧，流间独立无队头阻塞）；控制流（单向）传 SETTINGS 等（Send/ReceiveControlStream）；QPACK 另有编码流/解码流（单向各一对，动态表指令与确认走这两条流）。**QPACK（qpack/）**：静态表 + 动态表 + Huffman（qpack_encoder/qpack_decoder，常见头查表省字节）；核心问题——HPACK 动态表要求严格有序，而 QUIC 流可乱序到达会引入队头阻塞；**解法** `new_qpack_blocking_manager` 追踪头对动态表项的依赖，某头依赖的表项未到则该流暂"阻塞"、不拖累别流。**响应头编码旅程**：HTTP 头字段集→查静/动态表 + Huffman 编成索引/字面→经请求流发出（动态表指令走 encoder 流）→对端 decoder 依赖到齐才还原。

---

## 拓展 · QPACK 组件

| 组件 | 职责 |
|---|---|
| 静态表 | 预定义常见头（固定索引） |
| 动态表 | 连接内累积的头（可增删） |
| encoder/decoder 流 | 单向流传动态表指令与确认 |
| blocking manager | 追踪依赖、隔离阻塞到单流 |

---

## 调优要点（关键开关）

- 动态表越大压缩率越高，但阻塞风险与内存上升。
- 允许的最大阻塞流数权衡压缩 vs 时延。
- 高频头进动态表收益大。
- SETTINGS 提前协商参数降首包开销。

---

## 常见误区与工程要点

- **HTTP/3 用 HPACK**：HTTP/3 用 QPACK，HPACK 是 HTTP/2。
- **QPACK 无队头阻塞**：动态表依赖仍可能阻塞该流，但被隔离不扩散。
- **头压缩走请求流**：动态表指令走独立 encoder/decoder 流。
- **静态表够用**：动态表才是高频头压缩率的来源。

---

## 一句话总纲

**HTTP/3 与 QPACK 是 QUICHE 的应用层适配：HTTP 请求映射到双向 QuicSpdyStream（header+data 帧、流间独立），QPACK 用静态表+动态表+Huffman 压缩头；针对 HPACK 严格有序在乱序 QUIC 流上会引入队头阻塞的问题，QPACK 用独立 encoder/decoder 流传动态表指令、blocking manager 追踪依赖把阻塞隔离到单流——既保压缩率又不牺牲 QUIC 的无队头阻塞优势。**
