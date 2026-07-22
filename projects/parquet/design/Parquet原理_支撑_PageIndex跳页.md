# Parquet 原理 · 支撑主线 · PageIndex 跳页

> **定位**：属"索引能力域"——比行组统计更细一级的裁剪。管两个尾部集中结构：**ColumnIndex**（`parquet.thrift:1264`：每页 min/max/null_pages）回答"哪些页可能有"，**OffsetIndex**（`parquet.thrift:1239`：PageLocation `:1214`）回答"那页在哪、多大、从第几行起"。二者集中在文件尾部，实现**页级裁剪**（行组级裁块之下更细一层）。是【统计与排序】页级延伸、【读路径】跳页的核心。源码基准 **parquet-format**（`PageIndex.md`、`parquet.thrift`）。

行组级 Statistics 能跳整块，但一个块内可能只有一小段命中——PageIndex 把裁剪细化到**页**。它把"每页的 min/max/null 信息"（ColumnIndex）和"每页的字节偏移/大小/起始行号"（OffsetIndex）从数据页头里**抽出来集中放到文件尾部**，读者一次尾读就能拿到，无需扫过数据区逐页读页头。裁页分两步：先用 ColumnIndex 按值选页号，再用 OffsetIndex 把页号翻成字节偏移直接 seek。理解「两结构分工 + 两步裁页」就懂这一层。

---

## 一、两个结构：ColumnIndex + OffsetIndex

![Parquet PageIndex 两结构](Parquet原理_PageIndex_01两结构.svg)

- **ColumnIndex**（`parquet.thrift:1264`）：每个列块一份，含各页的 `min_values[]`/`max_values[]`、`null_pages[]`（该页是否全 null）、`null_counts[]`、以及 `boundary_order`（BoundaryOrder，页 min/max 是否单调）。回答"按值哪些页可能命中"。
- **OffsetIndex**（`parquet.thrift:1239`）：每个列块一份，含 `page_locations[]`，每个 `PageLocation`（`parquet.thrift:1214`）= `offset`（页字节偏移）+ `compressed_page_size`（读多少字节）+ `first_row_index`（本页首行号）。回答"页在哪、多大、从第几行起"。
- 二者**集中在文件尾部**（数据之后、FileMetaData 附近），其位置由 ColumnMetaData 里的偏移指向；读者按需一次范围读载入。

**为什么拆两个结构**：按值裁剪（ColumnIndex）和按位置定位（OffsetIndex）是两件事，拆开后读者可只读 ColumnIndex 做裁剪、命中后才读 OffsetIndex 定位——避免为裁剪加载不必要的偏移表；集中尾置又避免扫数据区读页头。

---

## 二、两级裁页：选页 → 定位

![Parquet 两级裁页](Parquet原理_PageIndex_02裁页.svg)

裁页流程（`PageIndex.md`）：

- **步骤1 · ColumnIndex 选页**：拿谓词（如 `WHERE x = 120`）逐页比 min/max：`[1,50]`/`[51,99]` 不含 → 弃，`[100,180]` 含 → 选中。若 `boundary_order = ASCENDING` 可**二分**而非逐页扫。`null_pages`/`null_counts` 还能加速 `IS (NOT) NULL`。输出候选页号集合。
- **步骤2 · OffsetIndex 定位**：对候选页号查 `PageLocation`：`offset` → seek 到该字节位置，`compressed_page_size` → 读多少字节，`first_row_index` → 本页首行号（供多列按行对齐拼回整行）。
- 效果：4 页里只读 1 页 → IO 与解码量约降到 1/4；页越多、谓词越挑，收益越大。这是"行组级裁块（Statistics）"之下更细的"页级裁页"，两级叠加逐层缩小要真正读取的字节范围。

**为什么两级**：ColumnIndex 回答"哪些页可能有"（按值），OffsetIndex 回答"那页在哪、多大、从第几行起"（按位置）；裁剪保守——选中的页仍需逐值精确校验谓词。

---

## 拓展 · PageIndex 关键结构一览

| 结构 / 字段 | 位置 | 职责 |
|---|---|---|
| ColumnIndex | `parquet.thrift:1264` | 每页 min/max/null_pages/boundary_order |
| OffsetIndex | `parquet.thrift:1239` | 每页 PageLocation 列表 |
| PageLocation | `parquet.thrift:1214` | offset + compressed_page_size + first_row_index |
| boundary_order | `parquet.thrift:1264`（内字段） | 页 min/max 单调 → 二分裁页 |
| first_row_index | `parquet.thrift:1214`（内字段） | 本页首行号，多列按行对齐 |

## 调优要点（关键开关）

- **默认开 PageIndex**：写侧几乎免费，读侧谓词裁页收益大；点查/高选择性查询尤甚。
- **配合排序写**：数据按谓词列有序 + BoundaryOrder=ASCENDING → 裁页可二分。
- **合适页大小**：页太大裁页粒度粗（一页命中就得读整页），太小则页数多、索引膨胀。
- **只读 ColumnIndex 先裁**：命中后再读 OffsetIndex 定位，避免无谓加载偏移表。

## 常见误区与工程要点

- **误区：PageIndex 在每个数据页头里。** 是从页头抽出、集中放文件尾部，一次尾读即得。
- **误区：裁页是精确的。** 保守裁剪——ColumnIndex 说"可能有"的页仍需逐值校验谓词。
- **误区：INDEX_PAGE 就是 PageIndex。** 老的页内 INDEX_PAGE 已废弃，被尾部 ColumnIndex/OffsetIndex 取代。
- **误区：没有 first_row_index 也能拼行。** 多列裁页后各列命中页不同，靠 first_row_index 按行号对齐才能拼回整行。
- **归属提醒**：页 min/max 的比较语义/BoundaryOrder 定义在【统计与排序】；等值查询进一步裁剪在【布隆过滤器】；跳读发生在【读路径】。

## 一句话总纲

**Parquet PageIndex 把裁剪从行组级细化到页级，用两个尾部集中结构：ColumnIndex（`parquet.thrift:1264`，每列块一份，含各页 min_values/max_values、null_pages、null_counts、boundary_order）回答"按值哪些页可能命中"，OffsetIndex（`:1239`，含 page_locations[]，每 PageLocation `:1214` = offset + compressed_page_size + first_row_index）回答"页在哪、多大、从第几行起"；二者从数据页头抽出集中放文件尾部、按需一次范围读载入；裁页两步——ColumnIndex 逐页比 min/max 选候选页号（BoundaryOrder=ASCENDING 可二分、null_pages 加速判空），OffsetIndex 把页号翻成字节偏移直接 seek 只读命中页、first_row_index 让多列按行对齐拼回整行；这是行组级 Statistics 裁块之下更细的页级裁页，两级叠加逐层缩小读取字节，裁剪保守、命中页仍需逐值精确校验。**
