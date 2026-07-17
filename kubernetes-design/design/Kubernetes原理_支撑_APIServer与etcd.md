# Kubernetes 核心原理 · 支撑能力域 · API Server 与 etcd

> **定位**：声明态的唯一存储与枢纽。API Server 是集群里**唯一读写 etcd** 的组件，对外暴露 REST + watch；etcd 是唯一有状态后端，存全量对象。所有组件都经它读写对象、订阅变更——这是 K8s 松耦合的物理中心。核实基准：`staging/src/k8s.io/apiserver/pkg/registry/generic/registry/store.go`、`storage/etcd3/store.go`、`storage/cacher/cacher.go`、`server/config.go`。

## 一、请求处理链：从 HTTP 到 REST 存储

![请求处理链](Kubernetes原理_支撑_APIServer与etcd_01请求处理链.svg)

一个写请求进入 API Server 后穿过 `DefaultBuildHandlerChain`（config.go）构建的过滤器链，**执行顺序**（请求入向）：PanicRecovery → RequestInfo（解析出 group/version/resource/verb）→ **Authentication**（认证，`WithAuthentication`）→ Audit → Impersonation → **PriorityAndFairness / MaxInFlight**（限流，默认 `MaxRequestsInFlight=400`、`MaxMutatingRequestsInFlight=200`）→ **Authorization**（鉴权，`WithAuthorization`）→ 到达 REST handler。**注意**：认证、鉴权是 http filter；而**准入控制（admission）不在这条链里**，它在 REST 的 `Store.Create`/`Store.Update` 内部、编解码之后、落库之前被调用（详见"认证授权与准入"篇）。REST handler：解码对象 → 默认值/校验 → mutating admission → validating admission → 转换为存储版本 → `Storage.Create`（store.go:526）或 `GuaranteedUpdate`（:638）。**多版本统一**：外部可用 v1/v1beta1 等多个 API 版本，内部统一转换成**存储版本**再落 etcd，读时再转回请求版本——这让 API 演进不破坏已存数据。

## 二、etcd 存储与 watch 缓存

![存储与watch缓存](Kubernetes原理_支撑_APIServer与etcd_02存储与watch缓存.svg)

**etcd3 后端**：对象经 codec 编码成字节，`store.Create`（etcd3store.go:241）用 etcd 事务（`clientv3` Txn：比较 key 不存在才 Put）保证创建原子；`GuaranteedUpdate`（:429）是**读-改-写重试循环**——读当前值、应用变更函数、带版本比较写回，冲突则重读重试，对应对象的乐观并发。etcd 的每次写产生一个全局单调递增的 **revision**，映射为对象的 `resourceVersion`。**watch cache（Cacher）**：若每个 watch 都直连 etcd，etcd 会被压垮。API Server 为每种资源维护一个 `Cacher`（cacher.go:250）——内部起一个 etcd watch 灌入 `watchCache` 环形缓冲，所有客户端 watch 都从这个内存缓存分发（`Cacher.Watch`:516 → `newCacheWatcher`:616；`processEvent`:1025 扇出事件）；`GetList`（:827）也可直接由缓存应答（一致性读除外）。**resourceVersion 语义**：客户端 watch 带上次收到的 rv，断线重连从该点续传，不丢不重；watch 返回的每个事件都是 ADDED/MODIFIED/DELETED + 对象快照。

## 深化 · REST 存储关键路径

| 操作 | 入口 | 落点 | 并发语义 |
|---|---|---|---|
| Create | `Store.Create` store.go:446 | `Storage.Create`:526 → etcd Txn（key 不存在） | 同名冲突 409 |
| Update | `Store.Update` :617 | `GuaranteedUpdate` :638 读-改-写重试 | resourceVersion 不匹配 → Conflict |
| Get | `Store.Get` :844 | etcd Range 或 watch cache | 可选一致性读 |
| Watch | `Store.Watch` :1415 | Cacher 内存缓存分发 | 按 rv 续传 |

## 拓展 · 为什么要 watch 缓存

| 无缓存直连 etcd | 有 Cacher 内存缓存 |
|---|---|
| N 个 watcher = N 个 etcd watch | 1 个 etcd watch 扇出给 N 个客户端 |
| etcd 成瓶颈，扩不动 | etcd 压力与客户端数解耦 |
| List 全打 etcd | List 可由缓存应答，降 etcd 负载 |

## 调优要点

- etcd 磁盘（fsync 延迟）是写吞吐上限：用 SSD、独立盘、监控 `wal_fsync` 时延。
- 控制 etcd 内对象总数与单对象大小：大对象/海量对象拖慢 List 与 compaction。
- `--watch-cache-sizes` 调 watch cache 容量，避免客户端频繁 "too old resource version" 重列。
- 定期 etcd compaction + defrag，回收 revision 历史占用的空间。

## 常见误区

- **控制器直接连 etcd**：只有 API Server 读写 etcd；其它组件一律经 API Server。
- **watch 直达 etcd**：默认经 API Server 的 watch cache 分发，不直连 etcd。
- **resourceVersion 是时间戳/可比大小做业务判断**：它是 etcd revision，仅用于并发与续传，不应参与业务序。
- **多个 API 版本各存一份**：内部只存"存储版本"一份，读写时按需转换。

## 一句话总纲

**API Server 是集群唯一读写 etcd 的枢纽：写请求穿过"认证→限流→鉴权"过滤器链、在 REST 层做准入与多版本转换后经 etcd 事务/读-改-写落库；每次写产生单调 revision（即 resourceVersion），支撑乐观并发与断点续传；而 watch cache（Cacher）用一个 etcd watch 扇出给成千上万客户端，让 etcd 压力与集群规模解耦——这是所有组件松耦合协作的物理基础。**
