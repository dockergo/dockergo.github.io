# 接触面 · FileSystem API 与 fs shell

> **定位**：Hadoop 面向用户的第一层门面。`FileSystem` 是一个**可插拔抽象基类**，HDFS 只是它的一种实现（`DistributedFileSystem`），本地盘、S3、ABFS 是另外的实现——同一套 `open/create/append/rename/delete/listStatus` API 屏蔽后端差异。`hdfs dfs` 命令行（`FsShell`）不过是这套 API 的一层 CLI 包装。上承用户程序与运维脚本，下启 NameNode 元数据操作与 DataNode 数据传输。

## FileSystem 抽象与实现

![FileSystem 抽象与实现](Hadoop原理_接口_文件系统API_01抽象与实现.svg)

`FileSystem`（`hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/FileSystem.java:172`）是抽象基类，定义统一文件操作契约。`FileSystem.get(conf)`（`:268`）按 URI scheme（`hdfs://` / `file://` / `s3a://`）从配置查实现类并实例化，且带一层进程级 `CACHE`（`:205`）复用连接。

HDFS 的实现是 `DistributedFileSystem`（`getScheme` 返回 `hdfs`）。它自己不实现协议，而是**委托内部的 `DFSClient`**——`create`/`open` 都转成 `DFSClient` 调用；`DFSClient` 通过 `ClientProtocol` 这个 RPC 代理与 NameNode 通信取块位置。

## fs shell 与 ClientProtocol RPC

![fs shell 与 RPC](Hadoop原理_接口_FileSystem_02shell命令.svg)

`hdfs dfs -put/-get/-ls` 走 `FsShell`（`hadoop-common/.../fs/FsShell.java:45`），它是一个 `Tool`：`registerCommands`（`:111`）注册命令表，把参数解析成 `Command` 对象后**同样经 `FileSystem` API 落地**——与编程接口共用一条路，没有捷径。

元数据操作（create/mkdir/rename/delete/addBlock/complete）经 `ClientProtocol` 这一 RPC 接口打到 NameNode，只改命名空间；数据字节则由 `DFSClient` 直连 DataNode（见 pipeline 写主线）。这就是「元数据走 NameNode、数据不经 NameNode」在接触面层的体现。

## 读路径 · 就近副本 + 校验和自愈

![读路径](Hadoop原理_接口_FileSystem_03读路径.svg)

图示读路径如何就近取副本并自愈。`open` 向 NameNode 取块位置，NameNode 的 `sortLocatedBlocks` 为每个块把副本按「状态（在役→stale→退役/慢节点下沉）+ 到 client 的网络距离（本地→同机架→跨机架）」排序后返回。client 取列表首个可用（即最近）节点、跳过 deadNodes；同机走**短路读**（`dfs.client.read.shortcircuit`，绕 TCP 直读本地块文件）、异机走 TCP，逐 chunk 用 .meta 校验 CRC。校验失配或 DN 不可达时标坏节点、retry（默认 2 次）换下一副本，并上报 NameNode——NameNode 从好副本重建、删坏副本，全程无人工。

**不变式**：数据永不经 NameNode（NN 只给位置、带宽由 DataNode 群提供）；就近读是数据本地性根基；HDFS 一次写入多次读取、不支持随机写（仅追加）。

## 深化 · 读路径关键入口

| 环节 | 入口 | 源码 |
|---|---|---|
| 取块位置 | `DFSClient.getLocatedBlocks` | `DFSClient.java:907` |
| 副本按状态+距离排序 | `DatanodeManager.sortLocatedBlocks` | `DatanodeManager.java:574` |
| 选最近可用节点 | `getBestNodeDNAddrPair` | `DFSInputStream.java:1077` |
| 短路/TCP 读 + CRC 校验 | `getBlockReader` | `DFSInputStream.java:695` |
| 坏块换副本 + 上报 | `readWithStrategy`→`reportCheckSumFailure` | `DFSInputStream.java:864`/`1592` |

## 深化 · FileSystem 家族实现对照

| 实现类 | scheme | 后端 | 特点 |
|---|---|---|---|
| DistributedFileSystem | hdfs:// | HDFS 集群 | 委托 DFSClient；块+副本+pipeline |
| LocalFileSystem | file:// | 本地磁盘 | ChecksumFileSystem 带 .crc 校验 |
| S3AFileSystem | s3a:// | AWS S3 对象存储 | 无真正目录/rename 昂贵；最终一致语义 |
| AzureBlobFileSystem | abfs:// | Azure Data Lake | 同一 API、异构后端 |
| ViewFileSystem | viewfs:// | 挂载表 | 客户端挂载多命名空间（Federation） |

## 调优要点

- **复用 FileSystem 实例**：`FileSystem.get` 有 `CACHE`，同 URI+conf 返回同一实例；频繁 `newInstance` 会泄漏连接。用完 `close` 或用带 disable-cache 配置隔离。
- **fs shell 批量操作合并**：逐文件 `-put` 每次一次 RPC；用 `-put` 一个目录或 `distcp` 并行，减少 NameNode RPC 压力。
- **短路读（short-circuit）**：client 与 DataNode 同机时开 `dfs.client.read.shortcircuit`，绕过 TCP 直接读本地块文件。

## 常见误区

- **误以为 rename 在所有实现里都是原子 O(1)**：HDFS 上是元数据原子改；S3A 上 rename = 复制+删除，昂贵且非原子。
- **误以为 shell 命令有特殊通道**：`hdfs dfs` 与 Java API 完全同路，性能特征一致。
- **误把 `hadoop fs` 与 `hdfs dfs` 当不同能力**：`hadoop fs` 面向任意 FileSystem，`hdfs dfs` 等价但语义限定 HDFS，二者底层同一 `FsShell`。

## 一句话总纲

**FileSystem 是可插拔门面、HDFS 只是其一种实现；fs shell 是 API 的 CLI 皮肤——所有入口最终都分成两股：元数据 RPC 打 NameNode、数据字节直连 DataNode。**
