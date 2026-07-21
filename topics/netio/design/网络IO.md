@eco
高性能网络 I/O 要省掉「字节从网卡到应用」这条链上多余的拷贝、陷入与上下文切换，同时让跨语言、跨版本的服务用一套可演进的协议高效通信。上图是通用生态脊：`网卡 DMA → (内核态协议栈 or 用户态旁路，二选一) → 传输 / 协议复用 → 序列化编解码 → 应用`——**数据面**求最少搬运，**控制面**求兼容与复用。下列各机制逐一展开这条脊上的关键取舍。

@n1
零拷贝的核心洞察是：**传统路径里最贵的不是网络，而是主机内部的搬运**——网卡收帧要经中断进内核、在协议栈里被 socket 缓冲，再由一次 `syscall` 从内核拷到用户空间。用户态旁路把这条链短路：驱动映射到用户态，网卡 **DMA 引擎直接把帧写进预分配的 `mbuf`**，应用以**轮询模式驱动（PMD）**忙查 `rx ring`，就地读字节——无系统调用、无中断、无内核-用户拷贝。处理完的 `mbuf` 归还内存池立即复用，稳态下零分配、零拷贝。代价很直白：独占一核持续轮询、绕过内核，安全与通用性得由应用自己扛。

@n2
`epoll` 与 `io_uring` 代表两种异步范式。`epoll` 是**就绪通知**：内核只报「fd 可读 / 可写了」，真正的 `read` / `write` 仍是独立 `syscall`、仍要一次内核-用户拷贝，N 个就绪 fd 就要 1 次 `epoll_wait` + N 次 `read`。`io_uring` 换成**完成通知**：应用把请求批量写进共享的**提交队列 SQ**、内核完成后把结果写回**完成队列 CQ**，两环共享内存、可批量提交，`SQPOLL` 下内核线程主动拉取甚至做到零 `syscall`。分野就是「先问就绪再自己做」还是「交出去等回执」，后者把 syscall 摊薄到接近旁路的成本。

@n3
把并发 RPC 塞进一条连接要解决两件事：**多请求共用连接而互不阻塞，且快的一方不能压垮慢的一方**。HTTP/2 的答案是 `stream`：每个 RPC 是一个带流 id 的 stream，帧**交织**在同一条 TCP 上发送、接收端按流 id 归并重组，一个慢请求不再堵住整条连接（对比 HTTP/1.1 一连接一次一请求）。反压靠**双层流控**：每条 stream 一个窗口、整条连接一个总窗口，任一耗尽即停发，接收方处理完回 `WINDOW_UPDATE` 抬升窗口才续发——信用式反压。头部再用 **HPACK**（静态表 + 动态表 + Huffman）把重复 header 压到几字节。

@n4
序列化的兼容性本质是同一个问题：**字段增删后，老代码读新数据、新代码读老数据都不能崩**。`Protobuf` 把消息编成一串 `⟨tag, wire-type, value⟩`、整数用 **varint**，**靠标签号自描述定位**：老代码遇未知 `tag` 按 wire-type 跳过、缺失字段取默认值，铁律是 tag 只增不复用、类型不改；代价是取任一字段都要从头流式解析。`FlatBuffers` 反其道：数据按固定布局就地存放，**`vtable` 偏移表记录每个字段在哪个偏移**，读时查表直接跳过去取值——**零解析、O(1) 随机访问**，兼容来自「新字段只追加到 vtable 末尾、旧偏移永不改」。一句话——**Protobuf 用解析换紧凑，FlatBuffers 用空间换零解析**。

@cmp
两组机制在「谁来做搬运 / 解析、何时做」上取舍。异步 I/O：**epoll** 报就绪、读写与拷贝甩回应用当场做、syscall 随并发线性增长；**io_uring** 报完成、SQ/CQ 双环批量提交与回写、syscall 摊薄到近零（SQPOLL 下为 0），代价是接口与内存序更复杂。序列化：**Protobuf** 靠 tag-varint 流式解析、O(n) 取值但编码紧凑；**FlatBuffers** 靠 vtable-offset 就地直取、O(1) 零解析但 buffer 偏大。两组同构：分歧都落在「当场自己动手（就绪 / 流式）」还是「预置结构、按需直取（完成 / 偏移）」。

@eng
同一批机理落到真实系统，取舍点集中在**谁来搬字节、用什么连接模型、在内核内还是旁路**四处。**nginx** 走 `master-worker` 多进程、每个 worker 单线程非阻塞事件循环（epoll 边缘触发），静态大文件靠 `sendfile` 把数据面留在内核零拷贝——省心、可移植，代价是数据面吞吐受内核路径约束。**gRPC** 把一条 TCP/TLS 连接复用成 N 个 HTTP/2 stream（客户端与服务端共用同一 chttp2 transport），用 `CompletionQueue`（每核一 CQ 一线程）承载并发、用 `Slice` 引用计数切帧不复制载荷、两级流控 + BDP 动态调窗约束发送量——以「编程模型复杂度」换「连接复用与自适应吞吐」。作为对照的两极：**DPDK** 用 PMD 轮询把网卡 DMA 直写用户态 `mbuf`、彻底旁路内核（无中断、无 syscall、独占核），把数据面榨到极致但须自建协议栈、自扛安全；**Envoy** 以 L7 sidecar 多 worker 线程做 HTTP/gRPC/TCP 通吃代理、连接池复用上游连接。

一句话：**越靠近内核越通用，越旁路 / 越专用越极致**。nginx / gRPC 的实现细节已在本库 [nginx 进程与事件模型](../../projects/nginx/) 与 [gRPC HTTP/2 传输](../../projects/grpc/) 中源码核实。权威落地依据见：[nginx 官方文档](https://nginx.org/en/docs/)、[gRPC Core Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/)、[DPDK Programmer's Guide](https://doc.dpdk.org/guides/prog_guide/)、[Envoy Architecture Overview](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/intro/threading_model)。

@refs
[RFC 9113 HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)

[RFC 7541 HPACK](https://www.rfc-editor.org/rfc/rfc7541)

[DPDK Programmer's Guide](https://doc.dpdk.org/guides/prog_guide/)

[io_uring_setup(2)](https://man7.org/linux/man-pages/man2/io_uring_setup.2.html)

[Protobuf Encoding](https://protobuf.dev/programming-guides/encoding/)

[FlatBuffers](https://flatbuffers.dev/)
