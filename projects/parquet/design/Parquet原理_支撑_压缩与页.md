# Parquet 原理 · 支撑主线 · 压缩与页

> **定位**：属"页能力域"。管两件事：**页（Page）** 是列块内的最小 IO / 编码 / 压缩 / 统计单元，`PageType` 分数据页/字典页/索引页等；**压缩 codec** 在编码之后对页数据整体压缩。是【列编码】的下游、【列块与页组装】的组成粒度、【PageIndex】/【读路径】裁页与免解压读的对象。源码基准 **parquet-format**（`Compression.md`、`parquet.thrift` PageType/PageHeader）。

页是 Parquet 里"读多少、压多少、算多少统计"的最小刻度。列块内数据切成一个个页，每页有一个 `PageHeader`（`parquet.thrift:810`）声明类型、未压缩/已压缩大小、可选页级 CRC32。压缩是编码之后的第二道：把编好的页字节整体交给 codec（SNAPPY/ZSTD/…）压。DataPageV2 更进一步——把 rep/def 级别放到压缩区之外，允许**免解压**就能读级别做裁页。理解「页是最小刻度 + 编码后再压 + V2 免解压」就懂了这一层。

---

## 一、压缩 codec：编码之后再压

![Parquet 压缩 codec](Parquet原理_压缩与页_01codec.svg)

`enum CompressionCodec`（`parquet.thrift:650`）定义可选压缩算法（`Compression.md:40-97`）：`UNCOMPRESSED`、`SNAPPY`、`GZIP`、`LZO`、`BROTLI`、`LZ4`（旧，有互操作问题）、`ZSTD`、`LZ4_RAW`（推荐的 LZ4 规范形态）。

- 压缩作用于**编码之后**的页字节（先列编码去结构冗余，再 codec 压残余熵）。
- 每列可独立选 codec，记于 `ColumnMetaData.codec`。
- `PageHeader` 同时记 `uncompressed_page_size` 与 `compressed_page_size`（`parquet.thrift:810`），读者据此分配缓冲、读取正确字节数。

**为什么编码后再压**：编码去掉的是"数据形态的结构冗余"（重复/递增/低基数），codec 去掉的是"字节序列的熵冗余"，两者正交叠加。SNAPPY 快、ZSTD 压缩比高，按冷热/CPU 预算选。

---

## 二、PageType：四类页

![Parquet 页类型](Parquet原理_压缩与页_02页类型.svg)

`enum PageType`（`parquet.thrift:661`）：

- **DATA_PAGE**：数据页 v1，头 `DataPageHeader`（`parquet.thrift:679`）含值数、编码、rep/def 编码、页级 Statistics；rep/def 级别与值**一起压在压缩区内**。
- **DATA_PAGE_V2**：数据页 v2，头 `DataPageHeaderV2`（`parquet.thrift:732`），把 rep/def 级别**移到压缩区外**（见第三节）。
- **DICTIONARY_PAGE**：字典页，存字典编码的取值表，位于列块首。
- **INDEX_PAGE**：索引页（历史遗留，现由尾部 PageIndex 结构替代）。

每页头还可选带 `crc`（`parquet.thrift:837`，CRC32 校验），用于检测存储/传输损坏。

**为什么区分页类型**：字典页与数据页职责不同（一次性取值表 vs 逐页数据）；v1/v2 是数据页的两代格式，v2 为免解压裁页而改进级别布局。

---

## 三、DataPageV2：免解压读级别

![Parquet V2 免解压](Parquet原理_压缩与页_03v2免解压.svg)

`DataPageHeaderV2`（`parquet.thrift:732`）相对 v1 的关键改进：

- rep/def 级别的字节长度单列在页头（`repetition_levels_byte_length` / `definition_levels_byte_length`），且级别**不压缩**、放在压缩区之外，只有值区被压。
- 页头带 `is_compressed`（`parquet.thrift:759`，默认 true）标志值区是否压缩。
- 因此读者**无需解压整页**即可读到 rep/def 级别与页头统计——可先据级别 / 页 min-max（配合 PageIndex）判断这页要不要，再决定是否解压值区。

**为什么 V2 这样布局**：v1 里级别和值压在一起，想看级别必须先解压整页；v2 把级别拎到压缩区外，实现"先廉价看级别/统计、命中才解压值"，配合 PageIndex 大幅省解压 CPU。

---

## 拓展 · 页与压缩关键结构一览

| 结构 | 位置 | 职责 |
|---|---|---|
| enum CompressionCodec | `parquet.thrift:650` | SNAPPY/ZSTD/LZ4_RAW… 可选压缩 |
| enum PageType | `parquet.thrift:661` | DATA_PAGE/V2/DICTIONARY/INDEX |
| PageHeader | `parquet.thrift:810` | 类型 + 未压缩/已压缩大小 + 可选 crc |
| crc（CRC32） | `parquet.thrift:837` | 页级损坏检测 |
| DataPageHeader | `parquet.thrift:679` | v1 数据页头（级别压在区内） |
| DataPageHeaderV2 | `parquet.thrift:732` | v2 数据页头，级别移出压缩区 |
| is_compressed | `parquet.thrift:759` | v2 值区是否压缩标志 |

## 调优要点（关键开关）

- **SNAPPY vs ZSTD**：SNAPPY 解压快、CPU 省，适合热数据；ZSTD 压缩比高，适合冷数据/存储敏感。
- **用 LZ4_RAW 而非旧 LZ4**：旧 LZ4 有跨实现互操作问题，规范推荐 LZ4_RAW。
- **开 DataPageV2**：配合 PageIndex 可免解压裁页，省解压 CPU（注意老读者兼容性）。
- **页级 CRC**：对存储不可靠场景开启，代价是每页多几字节 + 校验开销。

## 常见误区与工程要点

- **误区：压缩就是编码。** 编码（列编码，去结构冗余）在前，codec 压缩（去熵冗余）在后。
- **误区：压缩作用于整个列块。** 压缩以**页**为单位，每页独立压/解压，支持页级裁读。
- **误区：v1 也能免解压读级别。** 只有 v2 把级别移出压缩区，v1 想读级别须先解压整页。
- **误区：INDEX_PAGE 还在用。** 页内索引已被尾部 PageIndex（ColumnIndex/OffsetIndex）取代。
- **归属提醒**：页内值怎么编在【列编码】；页 min/max 统计在【统计与排序】；按页 min/max 裁页在【PageIndex】；字典页位置在【列块与页组装】。

## 一句话总纲

**Parquet 的页是列块内最小 IO/编码/压缩/统计单元，压缩是列编码之后的第二道工序：`enum CompressionCodec`（`parquet.thrift:650`，UNCOMPRESSED/SNAPPY/GZIP/ZSTD/LZ4_RAW…，`Compression.md:40`）对编好的页字节整体压、每列独立选、记于 ColumnMetaData.codec；`enum PageType`（`:661`）分 DATA_PAGE（v1，头 DataPageHeader `:679`，rep/def 级别压在区内）/DATA_PAGE_V2（头 DataPageHeaderV2 `:732`，级别移出压缩区且不压、is_compressed `:759` 标值区是否压）/DICTIONARY_PAGE（列块首取值表）/INDEX_PAGE（遗留）；PageHeader（`:810`）记未压缩/已压缩大小 + 可选 CRC32（`:837`）；先列编码去结构冗余、再 codec 压残余熵两道正交，V2 把级别拎到压缩区外实现"先廉价看级别/统计、命中才解压值区"，配合 PageIndex 大省解压 CPU。**
