#!/usr/bin/env python3
"""Build a self-contained, drill-down interactive HTML for the lakehouse SELECT
flow (FE + BE). Audience: Doris kernel & big-data engineers.

Diagrams (architecture / sequence / FE flow / BE flow) are hand-authored;
every node id is a semantic key matching .codegraph/drilldown.json, whose entries
carry verified {file,line}, a source slice, and an expert note. Clicking a node
opens an in-page side panel (signature + note + real source) and highlights the
node's upstream/downstream — no external navigation. mermaid runtime and the
drill-down data are inlined so the file works offline.
"""
import json
import os
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- CLI:支持指定 design 素材目录 / 输出路径,生成当前导航页面 ----
# --design-dir: 手绘 SVG + prose 文档所在目录(默认:脚本同级 ./design)
# --out:       输出 HTML 路径(默认:脚本同级 index.html —— 自包含产物)
# 本脚本完全自包含:仅读取同级 design/,不依赖任何外部代码库或目录。
_ap = argparse.ArgumentParser(description="生成 Kafka 引擎交互式核心原理图谱(离线自包含 HTML)")
_ap.add_argument("--design-dir", default=None, help="手绘 SVG + prose 文档目录")
_ap.add_argument("--out", default=None, help="输出 HTML 路径")
_args, _ = _ap.parse_known_args()

def _first_existing(*cands):
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]

# design 目录:CLI > 环境变量 > 脚本同级 design(自包含产物,默认即此)
_DESIGN_DIR = _first_existing(
    _args.design_dir,
    os.environ.get("DORIS_MAP_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("DORIS_MAP_OUT") or os.path.join(HERE, "index.html")

# mermaid 依赖已移除:所有图改为手绘工业风 SVG(base64 <img> 或 renderFlow/Seq/Tree/Table/Struct SVG)。
# 保留一个 no-op stub,兼容历史死代码里残留的 mermaid.render/initialize 调用(实际不可达)。
mermaid_js = ("window.mermaid={initialize:function(){},"
              "render:function(id,txt){return Promise.resolve({svg:''});}};")
# 源码下钻已移除:不再读取 drilldown.json;DRILL 置空对象。
drill_json = "{}"

# ---- Diagram 2: 端到端时序图 ----
SEQ = r"""
sequenceDiagram
  autonumber
  actor U as Client
  participant SE as StmtExecutor (FE)
  participant NP as NereidsPlanner
  participant HSN as HiveScanNode
  participant HMS as HiveMetaStoreCache
  participant CO as Coordinator
  participant IS as InternalService (BE)
  participant FM as FragmentMgr
  participant PT as PipelineTask
  participant FS as FileScanner
  participant OR as OrcReader
  participant DFS as HDFS/S3

  U->>SE: SELECT * FROM hive_catalog.db.orc_tbl
  SE->>NP: plan(stmt)  [解析→逻辑计划]
  NP->>NP: planWithLock (CBO 优化)
  NP->>HSN: 生成物理计划 / getSplits(numBackends)
  HSN->>HMS: getFilesByPartitions(分区)
  HMS->>DFS: list files (ORC)
  DFS-->>HMS: 文件列表 + 大小
  HMS-->>HSN: FileCacheValue
  HSN->>HSN: splitToScanRange → TScanRangeLocations
  NP->>CO: splitFragments / distribute
  SE->>CO: exec()
  CO->>IS: RPC exec_plan_fragment(TPipelineFragmentParams)
  IS->>FM: exec_plan_fragment
  FM->>PT: PipelineFragmentContext.prepare → execute
  loop 每个 ScanRange (ORC split)
    PT->>FS: get_block()
    FS->>FS: _get_next_reader → _init_orc_reader
    FS->>OR: init_reader / get_next_block
    OR->>DFS: 读 ORC stripe / column
    DFS-->>OR: 原始列数据
    OR-->>FS: _get_next_block_impl → Block
    FS->>FS: _convert_to_output_block (类型转换)
    FS-->>PT: 输出 Block
  end
  PT-->>CO: 结果分片回传
  CO-->>SE: 汇总结果
  SE-->>U: ResultSet
"""

# ---- Diagram 3: FE 详细流程 (节点 id = drilldown key) ----
FE_FLOW = r"""
flowchart TB
  subgraph S1["① 接入 & 路由"]
    StmtExec["StmtExecutor.execute()<br/><small>qe/StmtExecutor.java:481</small>"] --> queryRetry["queryRetry(queryId)<br/><small>StmtExecutor.java:491</small>"]
    queryRetry --> C{"是否 Nereids?"}
  end
  subgraph S2["② Nereids 优化 (CBO)"]
    Planner["NereidsPlanner.plan<br/><small>NereidsPlanner.java:138</small>"] --> planWithLock["planWithLock<br/><small>analyze → rewrite → optimize</small>"]
    planWithLock --> distribute["distribute(physicalPlan)<br/><small>NereidsPlanner.java:678</small>"]
    distribute --> splitFragments["splitFragments + doDistribute<br/><small>NereidsPlanner.java:579</small>"]
  end
  subgraph S3["③ Scan 规划 & Split 生成"]
    doInit["FileQueryScanNode.doInitialize<br/><small>FileQueryScanNode.java:140</small>"] --> initBackend["initBackendPolicy<br/><small>BE 负载均衡策略</small>"]
    doInit --> initSchema["initSchemaParams<br/><small>建 TFileScanRangeParams</small>"]
    doInit --> createScanRange["doFinalize → createScanRangeLocations<br/><small>FileQueryScanNode.java:285</small>"]
    createScanRange --> K{"batch 模式?"}
    K -->|否| getSplits["getSplits(numBackends)<br/><small>HiveScanNode.java:261</small>"]
    getSplits --> getFileSplit["getFileSplitByPartitions<br/><small>HiveScanNode.java:392</small>"]
    getFileSplit --> hmsCache["HiveMetaStoreCache.getFilesByPartitions<br/><small>HiveMetaStoreCache.java:658</small>"]
    hmsCache --> splitToScanRange["splitToScanRange<br/><small>→ TScanRangeLocations (ORC)</small>"]
    K -->|是| batchSplit["SplitAssignment (惰性 split)<br/><small>BE 主动拉取 split</small>"]
  end
  subgraph S4["④ 调度下发"]
    Coord["Coordinator.exec<br/><small>qe/Coordinator.java:683</small>"] --> thrift["ThriftPlansBuilder.plansToThrift<br/><small>→ 下发 BE RPC</small>"]
  end
  C -->|是| Planner
  splitFragments --> doInit
  splitToScanRange --> Coord
  batchSplit --> Coord

  classDef entry stroke:#12a37a,color:#0f766e;
  classDef scan stroke:#0a94d6,color:#0e7490;
  classDef meta stroke:#7c5fe6,color:#5b3fd6;
  class StmtExec entry;
  class getSplits,getFileSplit,splitToScanRange scan;
  class hmsCache meta;
"""

# ---- Diagram 4: BE 详细流程 (节点 id = drilldown key) ----
BE_FLOW = r"""
flowchart TB
  subgraph B1["① RPC 接入"]
    exec_rpc["exec_plan_fragment (RPC)<br/><small>service/internal_service.cpp:319</small>"] --> exec_impl["_exec_plan_fragment_impl<br/><small>internal_service.cpp:541</small>"]
    exec_impl --> fragMgr["FragmentMgr::exec_plan_fragment<br/><small>runtime/fragment_mgr.cpp:610</small>"]
  end
  subgraph B2["② Pipeline 调度"]
    pipeCtx["PipelineFragmentContext.prepare<br/><small>pipeline_fragment_context.cpp:256</small>"] --> pipeTask["PipelineTask::execute<br/><small>pipeline/pipeline_task.cpp:386</small>"]
    pipeTask --> scanSched["ScannerScheduler::_scanner_scan<br/><small>scanner_scheduler.cpp:127</small>"]
  end
  subgraph B3["③ 格式分派 (File Scanner)"]
    getBlock["FileScanner::get_block<br/><small>vec/exec/scan/file_scanner.cpp:408</small>"] --> getBlockWrapped["_get_block_wrapped<br/><small>file_scanner.cpp:437</small>"]
    getBlockWrapped --> getNextReader["_get_next_reader<br/><small>file_scanner.cpp:924</small>"]
    getNextReader --> J{"文件格式?"}
    J -->|FORMAT_ORC| initOrc["_init_orc_reader<br/><small>file_scanner.cpp:1320</small>"]
    J -->|FORMAT_PARQUET| initParquet["_init_parquet_reader<br/><small>file_scanner.cpp:1214</small>"]
  end
  subgraph B4["④ ORC 向量化读取"]
    orcInit["OrcReader::init_reader<br/><small>format/orc/vorc_reader.cpp:431</small>"] --> orcCreateFile["_create_file_reader<br/><small>vorc_reader.cpp:350</small>"]
    orcInit --> orcInitCols["_init_read_columns<br/><small>vorc_reader.cpp:484</small>"]
    orcInit --> orcGetNext["OrcReader::get_next_block<br/><small>vorc_reader.cpp:2266</small>"]
    orcGetNext --> orcGetNextImpl["_get_next_block_impl<br/><small>vorc_reader.cpp:2280 读 stripe/column</small>"]
    orcGetNextImpl --> convertOut["_convert_to_output_block<br/><small>file_scanner.cpp:724 类型转换</small>"]
  end
  fragMgr --> pipeCtx
  scanSched --> getBlock
  getNextReader -.FORMAT_ORC.-> orcInit
  convertOut --> outBlock["输出 Block → 上游 Operator"]
  outBlock --> resultBack["结果经 Coordinator 回传 FE"]

  classDef entry stroke:#12a37a,color:#0f766e;
  classDef reader stroke:#c99512,color:#8a5f0a;
  class exec_rpc entry;
  class orcInit,orcGetNext,orcGetNextImpl reader;
"""

# ---- Diagram 5: 内表 OLAP 扫描 (对比外表; 节点 id = drilldown key) ----
OLAP_FLOW = r"""
flowchart TB
  subgraph FEG["FE 规划 (内表)"]
    olapScanNode["OlapScanNode.init<br/><small>planner/OlapScanNode.java:348</small>"] --> computePartition["computePartitionInfo<br/><small>分区裁剪 OlapScanNode.java:730</small>"]
    computePartition --> computeTablet["computeTabletInfo<br/><small>tablet 定位/副本选择:887</small>"]
    computeTablet --> olapAddRange["addScanRangeLocations<br/><small>→ TPaloScanRange:472</small>"]
  end
  olapAddRange ==>|"TScanRangeLocations<br/>(tablet_id + version + 副本 BE)"| exec_rpc["exec_plan_fragment (RPC)<br/><small>service/internal_service.cpp:319</small>"]
  exec_rpc --> fragMgr["FragmentMgr::exec_plan_fragment<br/><small>fragment_mgr.cpp:610</small>"]
  fragMgr --> pipeCtx["PipelineFragmentContext.prepare<br/><small>pipeline_fragment_context.cpp:256</small>"]
  pipeCtx --> pipeTask["PipelineTask::execute<br/><small>pipeline_task.cpp:386</small>"]
  pipeTask --> scanSched["ScannerScheduler::_scanner_scan<br/><small>scanner_scheduler.cpp:127</small>"]
  scanSched --> olapGetBlock["OlapScanner::_get_block_impl<br/><small>vec/exec/scan/olap_scanner.cpp:578</small>"]
  olapGetBlock --> olapInitReader["_init_tablet_reader_params<br/><small>谓词/列/版本 olap_scanner.cpp:281</small>"]
  olapGetBlock --> blockReader["BlockReader::next_block_with_aggregation<br/><small>vec/olap/block_reader.cpp:65</small>"]
  blockReader --> K{"数据模型?"}
  K -->|DUP 明细| segIter["SegmentIterator::next_batch<br/><small>segment_v2/segment_iterator.cpp:2380</small>"]
  K -->|AGG/UNIQUE| merge["多路归并 (merge heap)<br/><small>_agg_key / _unique_key_next_block</small>"]
  merge --> segIter
  segIter --> segIterInternal["_next_batch_internal<br/><small>segment_iterator.cpp:2469<br/>向量化谓词+延迟物化</small>"]
  segIterInternal --> vecPred["_evaluate_vectorization_predicate<br/><small>向量化谓词过滤:2235</small>"]
  segIterInternal --> shortPred["_evaluate_short_circuit_predicate<br/><small>短路径/索引:2311</small>"]
  segIterInternal --> readByRowids["_read_columns_by_rowids<br/><small>延迟物化 segment_iterator.cpp:2336</small>"]
  readByRowids --> outBlk["输出 Block → 上游 Operator"]

  classDef entry stroke:#12a37a,color:#0f766e;
  classDef store stroke:#c77e12,color:#8a5f0a;
  classDef pred stroke:#c99512,color:#8a5f0a;
  class olapScanNode entry;
  class segIterInternal,readByRowids store;
  class vecPred,shortPred pred;
"""

# ---- Diagram 6: 数据写入链路 (Load; 节点 id = drilldown key) ----
WRITE_FLOW = r"""
flowchart TB
  src([Stream Load / Broker Load / INSERT]):::src
  src ==>|"一批 Block"| loadRpc["tablet_writer_add_block (RPC)<br/><small>service/internal_service.cpp:489</small>"]
  loadRpc --> loadChanMgr["LoadChannelMgr::add_batch<br/><small>按 load_id 路由 load_channel_mgr.cpp:151</small>"]
  loadChanMgr --> loadChan["LoadChannel::add_batch<br/><small>按 tablet 分发 load_channel.cpp:177</small>"]
  loadChan --> deltaWrite["DeltaWriter::write<br/><small>olap/delta_writer.cpp:143</small>"]
  deltaWrite --> memInsert["MemTable::insert<br/><small>写入内存有序表 memtable.cpp:197</small>"]
  memInsert --> full{"MemTable 满?"}
  full -->|否| memInsert
  full -->|是, 异步 flush| memFlush["MemtableFlushExecutor::_flush_memtable<br/><small>独立线程池 memtable_flush_executor.cpp:221</small>"]
  memFlush --> memToBlock["MemTable::to_block<br/><small>排序+聚合/去重 memtable.cpp:742</small>"]
  memToBlock --> segWrite["SegmentWriter::append_block<br/><small>列式编码+建索引 segment_writer.cpp:701</small>"]
  segWrite --> rowsetClose["BetaRowsetWriter::close<br/><small>生成 rowset beta_rowset_writer.cpp:131</small>"]
  rowsetClose ==>|"事务提交后可见"| done([新 rowset → tablet 版本]):::done

  classDef src stroke:#c77e12,color:#8a5f0a;
  classDef done stroke:#12a37a,color:#0f766e;
  classDef mem stroke:#c77e12,color:#8a5f0a;
  classDef disk stroke:#0a94d6,color:#0e7490;
  class memInsert,memToBlock mem;
  class segWrite,rowsetClose disk;
"""

# ---- Diagram 10: 内存管理模型 ----
MEM_FLOW = r"""
flowchart TB
  subgraph M1["线程上下文 (归属)"]
    memThreadCtx["ThreadContext (SCOPED_ATTACH_TASK)<br/><small>runtime/thread_context.h:162</small>"] --> memThreadMgr["ThreadMemTrackerMgr::consume<br/><small>thread_mem_tracker_mgr.h:51</small>"]
  end
  subgraph M2["树形 Tracker"]
    memTracker["MemTrackerLimiter<br/><small>runtime/memory/mem_tracker_limiter.h:71</small>"]
  end
  subgraph M3["进程级仲裁 & GC"]
    memArbitrator["GlobalMemoryArbitrator<br/><small>global_memory_arbitrator.h:26</small>"] --> memReclaim["MemoryReclamation::revoke_tasks_memory<br/><small>memory_reclamation.cpp:35</small>"]
  end
  subgraph M4["导入反压"]
    memLoadLimiter["MemTableMemoryLimiter::handle_memtable_flush<br/><small>memtable_memory_limiter.cpp:124</small>"]
  end
  memThreadMgr ==>|"consume/release 记账"| memTracker
  memTracker -->|"QUERY/LOAD/... 归属"| memArbitrator
  memArbitrator -->|"超 hard limit"| memReclaim
  memReclaim -.cancel/spill 最大 task.-> memTracker
  memLoadLimiter -.整机 memtable 超限.-> memArbitrator

  classDef ctx stroke:#12a37a,color:#0f766e;
  classDef trk stroke:#7c5fe6,color:#5b3fd6;
  classDef gc stroke:#c99512,color:#8a5f0a;
  class memThreadCtx,memThreadMgr ctx;
  class memTracker trk;
  class memArbitrator,memReclaim gc;
  style M1 stroke:#2f8f5e;
  style M2 stroke:#7c5fe6;
  style M3 stroke:#b08b3a;
  style M4 stroke:#7089b0;
"""

# ---- Diagram 11: 负载管理模型 ----
WG_FLOW = r"""
flowchart TB
  subgraph W1["FE 资源组 & 排队"]
    wgCoordExec["Coordinator.exec (排队入口)<br/><small>qe/Coordinator.java:683</small>"] --> wgQueue["QueryQueue.getToken<br/><small>workloadgroup/QueryQueue.java:37</small>"]
    wgMgrFe["WorkloadGroupMgr<br/><small>workloadgroup/WorkloadGroupMgr.java:64</small>"] --> wgDef["WorkloadGroup 定义<br/><small>CPU/内存/并发 属性:52</small>"]
  end
  subgraph W2["BE 资源隔离"]
    wgBe["WorkloadGroup (BE)<br/><small>runtime/workload_group/workload_group.h:60</small>"] --> wgCgroup["CgroupCpuCtl::update_cpu_hard_limit<br/><small>agent/cgroup_cpu_ctl.cpp:178</small>"]
    wgMgrBe["WorkloadGroupMgr::handle_paused_queries<br/><small>workload_group_manager.cpp:316</small>"]
  end
  wgMgrFe --> wgCoordExec
  wgDef -.toThrift TPipelineWorkloadGroup.-> wgBe
  wgQueue ==>|"取到 token 随 fragment 下发"| wgBe
  wgBe --> wgMgrBe

  classDef fe stroke:#0a94d6,color:#0e7490;
  classDef be stroke:#12a37a,color:#0f766e;
  class wgCoordExec,wgQueue,wgMgrFe,wgDef fe;
  class wgBe,wgCgroup,wgMgrBe be;
  style W1 stroke:#7089b0;
  style W2 stroke:#2f8f5e;
"""

# ---- Diagram 12: 优化器原理 (Nereids CBO) ----
OPT_FLOW = r"""
flowchart TB
  subgraph O1["① 绑定 & RBO"]
    optAnalyzer["Analyzer (bind)<br/><small>jobs/executor/Analyzer.java:70</small>"] --> optRewriter["Rewriter (RBO 改写)<br/><small>jobs/executor/Rewriter.java:206</small>"]
  end
  subgraph O2["② CBO 搜索 (Cascades)"]
    optOptimizer["Optimizer.execute<br/><small>jobs/executor/Optimizer.java:37</small>"] --> optOptGroupJob["OptimizeGroupJob<br/><small>cascades/OptimizeGroupJob.java:34</small>"]
    optOptGroupJob --> optApplyRule["ApplyRuleJob<br/><small>cascades/ApplyRuleJob.java:45</small>"]
    optApplyRule --> optDeriveStats["DeriveStatsJob<br/><small>cascades/DeriveStatsJob.java:45</small>"]
    optDeriveStats --> optCostEnforcer["CostAndEnforcerJob<br/><small>cascades/CostAndEnforcerJob.java:48</small>"]
  end
  subgraph O3["搜索空间 & 统计"]
    optMemo["Memo (记忆化)<br/><small>nereids/memo/Memo.java:72</small>"]
    optStatsCalc["StatsCalculator<br/><small>nereids/stats/StatsCalculator.java:181</small>"]
  end
  optRewriter ==>|"进入 CBO"| optOptimizer
  optApplyRule -.copyIn 去重.-> optMemo
  optDeriveStats -.估行数/NDV.-> optStatsCalc
  optCostEnforcer -.取 lowestCost + 插 enforcer.-> optMemo

  classDef rbo stroke:#0a94d6,color:#0e7490;
  classDef cbo stroke:#12a37a,color:#0f766e;
  classDef aux stroke:#7c5fe6,color:#5b3fd6;
  class optAnalyzer,optRewriter rbo;
  class optOptimizer,optOptGroupJob,optApplyRule,optDeriveStats,optCostEnforcer cbo;
  class optMemo,optStatsCalc aux;
  style O1 stroke:#7089b0;
  style O2 stroke:#2f8f5e;
  style O3 stroke:#7c5fe6;
"""

TABS = [
    ("apiwalk", "原理详解", ""),
    ("logwalk", "原理详解", ""),
    ("replwalk", "原理详解", ""),
    ("groupwalk", "原理详解", ""),
    ("kraftwalk", "原理详解", ""),
    ("netwalk", "原理详解", ""),
    ("txnwalk", "原理详解", ""),
    ("panowalk", "全景框架", ""),
    ("compare", "流平台对比", ""),
]


first_tab = TABS[0][0]

# Meta for each tab: (icon, subtitle, 五维维度名)。二级 Tab 用维度名统一命名。
TAB_META = {
    "apiwalk":   ("◷", "原理详解 · 生产/消费 API：Producer 攒批+分区+acks，Consumer poll+fetch+提交", "原理"),
    "logwalk":   ("▤", "原理详解 · 日志存储：Partition→Segment 稀疏索引 + 记录批 + 清理 + 零拷贝", "原理"),
    "replwalk":  ("⬡", "原理详解 · 副本 ISR：Leader/Follower 复制 + HW + acks/min.insync + epoch", "原理"),
    "groupwalk": ("◐", "原理详解 · 消费者组：协调器两层 + KIP-848 rebalance + 位点", "原理"),
    "kraftwalk": ("⬢", "原理详解 · KRaft：元数据即事件日志 + Raft 共识 + 传播 + 角色", "原理"),
    "netwalk":   ("◱", "原理详解 · 网络：Reactor 线程模型 + KafkaApis 分派 + Purgatory", "原理"),
    "txnwalk":   ("⇅", "原理详解 · 事务幂等：PID+序列号 + 跨分区原子 + read_committed", "原理"),
    "panowalk":  ("◇", "全景框架 · 双维模型 → 总架构 → 依赖矩阵 → 依赖关系", "整体架构"),
    "compare":   ("▦", "流平台对比 · Kafka vs Pulsar/RabbitMQ/RocketMQ 设计取舍", "整体架构"),
}

# 维度固定顺序(主题内二级 Tab 按此排序,仅显示存在的维度)
DIM_ORDER = ["整体架构", "查询流程", "写入流程", "FE 流程", "BE 流程", "时序流程",
             "数据结构", "示例", "Profile"]

# 每个视图的常驻导航卡片数据: summary(整体逻辑) + stages(逻辑阶段) + keys(关键可下钻节点)
VIEW_GUIDE = {
    "seq": {
        "summary": "一次 SELECT 查询 Hive ORC 外表的端到端时序:从 Client 发 SQL,经 FE 解析规划、生成 Split,RPC 下发 BE,到 BE 逐 ScanRange 读 ORC 并回传结果的完整生命周期。",
        "stages": ["FE 解析规划", "Split 生成", "RPC 下发", "BE 循环读取 ORC", "结果回传"],
        "keys": []},
    "feflow": {
        "summary": "FE 查询规划全流程:StmtExecutor 接入 → Nereids CBO 优化 → Scan 规划生成 Hive 文件 Split → Coordinator 编排并通过 Thrift 下发 BE。",
        "stages": ["① 接入 & 路由", "② Nereids 优化", "③ Scan 规划 & Split", "④ 调度下发"],
        "keys": ["StmtExec", "Planner", "getSplits", "hmsCache", "Coord", "thrift"]},
    "beflow": {
        "summary": "BE 外表扫描全流程:RPC 接入 → Pipeline 调度 → FileScanner 按格式分派 → OrcReader 向量化读取(谓词下推 + 延迟物化)。",
        "stages": ["① RPC 接入", "② Pipeline 调度", "③ 格式分派", "④ ORC 向量化读取"],
        "keys": ["exec_rpc", "pipeTask", "getNextReader", "orcInit", "orcGetNextImpl", "convertOut"]},
    "olapflow": {
        "summary": "内表 OLAP 扫描:OlapScanner 经 TabletReader/BlockReader 按 DUP/AGG/UNIQUE 合并,SegmentIterator 两阶段谓词 + 延迟物化读列存。",
        "stages": ["FE tablet 定位", "RPC + Pipeline", "BlockReader 合并", "SegmentIterator 向量化"],
        "keys": ["olapScanNode", "olapGetBlock", "blockReader", "segIterInternal", "readByRowids"]},
    "writeflow": {
        "summary": "数据写入(LSM):tablet_writer_add_block 经 LoadChannel → DeltaWriter → MemTable 内存有序表,满则异步 flush 成 segment,最终 close 出 rowset。",
        "stages": ["RPC 接入", "LoadChannel 路由", "MemTable 写入", "异步 flush", "rowset 生成"],
        "keys": ["loadRpc", "deltaWrite", "memInsert", "memFlush", "segWrite", "rowsetClose"]},
    "memflow": {
        "summary": "内存管理:分配经 ThreadContext 归属到 query/load 的 MemTrackerLimiter(树形),进程超限时 GlobalMemoryArbitrator 触发 GC/cancel,导入侧有独立反压。",
        "stages": ["线程上下文归属", "树形 Tracker", "进程仲裁 & GC", "导入反压"],
        "keys": ["memThreadCtx", "memTracker", "memArbitrator", "memReclaim", "memLoadLimiter"]},
    "wgflow": {
        "summary": "负载管理:FE 按 Workload Group 排队(QueryQueue),随 fragment 下发;BE 侧每组独立 cgroup CPU/内存/IO 隔离与 pipeline 调度器,实现多租户隔离。",
        "stages": ["FE 资源组 & 排队", "BE 资源隔离"],
        "keys": ["wgCoordExec", "wgQueue", "wgDef", "wgBe", "wgCgroup", "wgMgrBe"]},
    "optflow": {
        "summary": "Nereids CBO:绑定(Analyzer)→ RBO 改写(Rewriter)→ Cascades 搜索(Optimizer 驱动 OptimizeGroupJob→ApplyRule→DeriveStats→CostAndEnforcer,Memo 记忆化去重)→ 物理计划。",
        "stages": ["① 绑定 & RBO", "② CBO 搜索", "搜索空间 & 统计"],
        "keys": ["optAnalyzer", "optRewriter", "optOptimizer", "optMemo", "optCostEnforcer", "optStatsCalc"]},
}

# 主题(顶级) × 子视图(二级 tid)。全局架构为独立总览主题。
THEMES = [
    # ── 接触面主线 · 用户可见 · Kafka 是分布式事件流平台(新家族):生产/消费 API,非 SQL ──
    {"id": "api", "icon": "◷", "title": "生产与消费 API", "cat": "iface", "ord": 0,
     "desc": "接触面:Producer 攒批发送 + Consumer 拉取消费提交位点。design 走查——Producer 发送路径(攒批+分区+acks)→ Consumer 消费路径(poll+fetch+提交)→ 投递语义(至少/精确一次),附调优/误区/总纲",
     "tabs": ["apiwalk"]},

    # ── 支撑主线 · 引擎内部(6 条)· 严格以 design 走查为主干 ──
    {"id": "log", "icon": "▤", "title": "日志存储", "cat": "support", "ord": 0,
     "desc": "核心能力域:design 走查——Topic→Partition→Log→Segment 层级 → Segment 磁盘格式(稀疏索引)→ 记录批 magic v2 → retention/compaction 清理 → 页缓存+零拷贝,附调优/误区/总纲",
     "tabs": ["logwalk"]},
    {"id": "repl", "icon": "⬡", "title": "副本与 ISR", "cat": "support", "ord": 1,
     "desc": "容错能力域(灵魂):design 走查——Leader/Follower 复制 → ISR 与高水位 → acks/min.insync 不丢语义 → leader epoch 与截断,附调优/误区/总纲",
     "tabs": ["replwalk"]},
    {"id": "group", "icon": "◐", "title": "消费者组与协调", "cat": "support", "ord": 2,
     "desc": "协调能力域:design 走查——组协调器两层架构 → KIP-848 服务端主导 rebalance → 位点管理(__consumer_offsets),附调优/误区/总纲",
     "tabs": ["groupwalk"]},
    {"id": "kraft", "icon": "⬢", "title": "KRaft 元数据", "cat": "support", "ord": 3,
     "desc": "元数据/共识能力域(4.x 灵魂):design 走查——控制器(元数据即事件日志)→ Raft 共识 → 元数据传播 → Broker 角色与 quorum,附调优/误区/总纲",
     "tabs": ["kraftwalk"]},
    {"id": "net", "icon": "◱", "title": "网络与请求处理", "cat": "support", "ord": 4,
     "desc": "通信能力域:design 走查——Reactor 线程模型(Acceptor/Processor/IO 线程)→ KafkaApis 请求分派 → Purgatory 延迟操作,附调优/误区/总纲",
     "tabs": ["netwalk"]},
    {"id": "txn", "icon": "⇅", "title": "事务与幂等", "cat": "support", "ord": 5,
     "desc": "一致性能力域:design 走查——幂等生产者(PID+序列号)→ 事务(跨分区原子写)→ read_committed(消费端只读已提交),附调优/误区/总纲",
     "tabs": ["txnwalk"]},

    # ── Appendix · 参考 ──
    {"id": "overallarch", "icon": "◇", "title": "全景框架", "cat": "appendix", "ord": 1,
     "desc": "全景框架:双维模型(能力域×执行时机)· 总架构图(Broker 数据面 + KRaft 元数据面)· 依赖矩阵 · 能力域依赖关系",
     "tabs": ["panowalk"]},
    {"id": "refolap", "icon": "▦", "title": "流平台对比", "cat": "appendix", "ord": 2,
     "desc": "Kafka vs Pulsar / RabbitMQ / RocketMQ —— 分区追加日志 + 副本 ISR + KRaft 的设计取舍横向对比",
     "tabs": ["compare"]},
]

# tid -> themeId(供跨视图跳转时定位所属主题)
TAB2THEME = {tid: th["id"] for th in THEMES for tid in th["tabs"]}


def _theme_of(tid):
    return TAB2THEME.get(tid, "lakehouse")


# 主题卡片(首页)—— 按大类分组,每组一个小标题 + 紧凑卡片网格
CAT_ORDER = [
    ("start",    "Getting Started · 快速上手"),
    ("iface",    "接口主线 · 用户可见(DDL / DML / DQL / DCL)"),
    ("support",  "支撑主线 · 引擎内部"),
    ("appendix", "Appendix · 参考"),
]

def _card(th):
    return (
        '<button class="tcard" data-theme-id="{tid}" data-cat="{cat}">'
        '<span class="tcard-ico">{ico}</span>'
        '<span class="tcard-body"><span class="tcard-titlerow"><span class="tcard-title">{title}</span></span>'
        '<span class="tcard-desc">{desc}</span>'
        '<span class="tcard-meta">{n} 个视图 →</span></span></button>'.format(
            tid=th["id"], ico=th["icon"], title=th["title"], desc=th["desc"],
            n=len(th["tabs"]), cat=th.get("cat", "core")))

_parts = []
for _cat, _label in CAT_ORDER:
    _group = [th for th in THEMES if th.get("cat", "core") == _cat]
    _group.sort(key=lambda th: th.get("ord", 0))  # 稳定排序:ord 小的在前,未设 ord 默认 0 保持定义序
    if not _group:
        continue
    _parts.append('<div class="cat-sec">' + _label + '</div>')
    _parts.append('<div class="tcards">' + "\n".join(_card(th) for th in _group) + '</div>')
theme_cards = "\n".join(_parts)

# tab 顺序即各主题 tabs 字段的书写顺序(叙事顺序,人工策划) —— 不再按维度重排,
# 否则会把湖仓的 原理①FE→②BE→③ORC→④Hudi 叙事打散(查询流程维度会抢到 FE/BE 之前)

# tid -> 短标题(TABS 第 2 元素),tab 按钮文字用它以区分同维度多视图
TAB_TITLE = {tid: title for (tid, title, _) in TABS}

# 二级 tab 按钮:标题用短标题(同一维度多视图可区分);带 data-theme 归属;副标题作 tooltip
# 只为归属于某主题的 tid 生成按钮 —— 未挂载的 tid(旧视图)不泄漏进任何主题的 tab 栏
THEMED_TIDS = {tid for th in THEMES for tid in th["tabs"]}
# legacy 主题 31 视图集中一栏 —— 加原主题前缀,按主题聚拢可读(仅影响 legacy 内 tab 标签,
# 这些 tid 已从原主题移除、只属 legacy,改标签无副作用)
_LEGACY_LABEL = {
    "sctree": "DDL·变更结构",
    "loadstruct": "DML·分桶结构", "writedata": "DML·落盘结构", "mowmerge": "DML·MoW 合并",
    "qlifevars": "DQL·调优开关", "qlifeterms": "DQL·术语表",
    "steOlap": "存储·内表存储", "steFmt": "存储·存储格式", "steExt": "存储·外表读取",
    "steIdx": "存储·索引检索", "steMv": "存储·物化视图", "steOrg": "存储·数据组织",
    "optq": "优化·查询优化器", "optrf": "优化·Runtime Filter", "opttopn": "优化·TOPN", "optstat": "优化·统计信息",
    "optpipe": "执行·Pipeline", "threadtree": "执行·线程架构", "threadseq": "执行·线程调度",
    "memflow": "执行·内存管理", "jeflow": "执行·jemalloc", "memseq": "执行·内存调度",
    "memtree": "执行·MemTracker 树", "jemalloctree": "执行·内存交互",
    "txnswim": "事务·双泳道", "txntree": "事务·结构", "versiongraph": "事务·版本读快照",
    "metatree": "元数据·结构", "wgtree": "资源·资源组隔离", "tablettree": "自愈·调度结构",
    "compacttree": "后台·Compaction 结构",
}
tab_buttons = "\n".join(
    '<button class="tab" data-tab="{tid}" data-theme="{th}" title="{sub}">'
    '<span class="tab-ico">{ico}</span><span class="tab-tt">{tt}</span></button>'.format(
        tid=tid, th=_theme_of(tid), ico=TAB_META[tid][0],
        tt=_LEGACY_LABEL.get(tid, TAB_TITLE[tid]), sub=TAB_META[tid][1])
    for (tid, title, _) in TABS if tid in THEMED_TIDS)

# =====================================================================
# 导航样式:除主题卡片外,再提供两种等价入口 —— 架构图导航 + 树状导航。
# 三者内容完全一致(同一 THEMES/openTheme),仅引导方式不同。
# =====================================================================
_THEME_BY_ID = {th["id"]: th for th in THEMES}

# ---- 架构图导航:内嵌总架构 SVG(base64,自包含免转义),覆盖透明可点热区 ----
# 热区坐标取自 SVG 各模块 rect;SVG 主体包在 <g transform="translate(0,70)"> 内,
# 故除“外部数据生态/接入层”外的模块 y 需 +70 才是根坐标。viewBox 1080×850。
import base64 as _b64
_ARCH_SVG_TEXT = open(
    os.path.join(_DESIGN_DIR, "Kafka原理_总架构图.svg"),
    encoding="utf-8").read()
_ARCH_SVG_B64 = _b64.b64encode(_ARCH_SVG_TEXT.encode("utf-8")).decode("ascii")

# 架构热区从总架构 SVG 的 data-tid 矩形自动派生(SVG = 唯一真源,消除双真源漂移)。
# (x, y, w, h, theme_id, 标签):坐标取自带 data-tid 的 <rect>,theme_id = data-tid,标签 = data-lab。
import re as _re_hot
import xml.etree.ElementTree as _ET_hot


def _parse_arch_hotspots(svg_text):
    vb = _re_hot.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg_text or "")
    if not vb:
        return [], 1080.0, 800.0
    vbw, vbh = float(vb.group(1)), float(vb.group(2))
    root = _ET_hot.fromstring(svg_text)
    hots = []

    def walk(el, dx, dy):
        m = _re_hot.search(r'translate\(\s*([-\d.]+)(?:[,\s]+([-\d.]+))?', el.get("transform") or "")
        if m:
            dx += float(m.group(1))
            if m.group(2):
                dy += float(m.group(2))
        if el.tag.rsplit("}", 1)[-1] == "rect" and el.get("data-tid"):
            hots.append((float(el.get("x", 0)) + dx, float(el.get("y", 0)) + dy,
                         float(el.get("width", 0)), float(el.get("height", 0)),
                         el.get("data-tid"), el.get("data-lab") or ""))
        for c in el:
            walk(c, dx, dy)

    walk(root, 0.0, 0.0)
    return hots, vbw, vbh


_ARCH_HOTSPOTS, _ARCH_VBW, _ARCH_VBH = _parse_arch_hotspots(_ARCH_SVG_TEXT)
_arch_hotspots_html = "\n".join(
    '<button class="arch-hot" style="left:{lp:.4f}%;top:{tp:.4f}%;width:{wp:.4f}%;height:{hp:.4f}%" '
    'data-theme-id="{tid}" title="{lab} → {ttitle}"><span class="arch-hot-lab">{lab}</span></button>'.format(
        lp=x/_ARCH_VBW*100, tp=y/_ARCH_VBH*100, wp=w/_ARCH_VBW*100, hp=h/_ARCH_VBH*100,
        tid=tid, lab=lab, ttitle=_THEME_BY_ID[tid]["title"])
    for (x, y, w, h, tid, lab) in _ARCH_HOTSPOTS)

# 未描绘主题(时间与窗口无独立架构区域、全景框架、对比)→ 底部补充 chip,保证主题→可达
_ARCH_ALWAYS_CHIP = {"overallarch"}
_ARCH_DEPICTED = {h[4] for h in _ARCH_HOTSPOTS} - _ARCH_ALWAYS_CHIP
_arch_extra_chips = "\n".join(
    '<button class="arch-chip" data-theme-id="{tid}">{ico} {title}</button>'.format(
        tid=th["id"], ico=th["icon"], title=th["title"])
    for th in THEMES if th["id"] not in _ARCH_DEPICTED)

# ---- 树状导航:CAT 分组 → 主题(可折叠)→ 视图叶子 ----
def _tree_leaf(tid):
    return ('<button class="tree-leaf" data-tab="{tid}" title="{sub}">'
            '<span class="tree-leaf-ico">{ico}</span>{tt}</button>').format(
        tid=tid, ico=TAB_META[tid][0], tt=TAB_TITLE.get(tid, tid),
        sub=TAB_META[tid][1] if tid in TAB_META else "")

def _tree_theme(th):
    leaves = "\n".join(_tree_leaf(tid) for tid in th["tabs"])
    return ('<div class="tree-theme">'
            '<button class="tree-thead" data-theme-id="{tid}">'
            '<span class="tree-chev">▸</span>'
            '<span class="tree-tico">{ico}</span>'
            '<span class="tree-ttl">{title}</span>'
            '<span class="tree-tcount">{n}</span></button>'
            '<div class="tree-leaves">{leaves}</div></div>').format(
        tid=th["id"], ico=th["icon"], title=th["title"], n=len(th["tabs"]), leaves=leaves)

_tree_parts = []
for _cat, _label in CAT_ORDER:
    _group = [th for th in THEMES if th.get("cat", "core") == _cat]
    _group.sort(key=lambda th: th.get("ord", 0))
    if not _group:
        continue
    _tree_parts.append('<div class="tree-cat">' + _label + '</div>')
    _tree_parts.append("\n".join(_tree_theme(th) for th in _group))
tree_nav = "\n".join(_tree_parts)

# =====================================================================
# design 原理图集成(优化型混合):57 张权威手绘 SVG → 各主题「原理详解」
# 走查 tab。复用架构图导航已验证的 base64 <img> + 暗色 invert 机制,
# 复刻 _build_multi_blocks 的左垂直 TAB 结构(每 .do-sec 放 <img> 而非 mermaid)。
# =====================================================================
# _DESIGN_DIR 已在文件顶部由 CLI/env/回退链确定;此处直接复用。

def _design_b64(fname):
    _p = os.path.join(_DESIGN_DIR, fname)
    if not os.path.isfile(_p):        # 素材缺失容错:返回空 base64,不因单图崩全局
        return ""
    with open(_p, encoding="utf-8") as _f:
        return _b64.b64encode(_f.read().encode("utf-8")).decode("ascii")

# SVG-walk 视图:tid → [(标题, 文件名), ...](顺序取自 prose 文档的图序)
_SVG_WALK_SPECS = {
    "apiwalk": [("Producer 发送路径 · 攒批+分区+acks", "Kafka原理_API_01Producer.svg"),
                ("Consumer 消费路径 · poll+fetch+提交", "Kafka原理_API_02Consumer.svg"),
                ("投递语义 · 至少一次/精确一次", "Kafka原理_API_03语义.svg")],
    "logwalk": [("层级 · Topic→Partition→Log→Segment", "Kafka原理_存储_01层级.svg"),
                ("Segment 磁盘格式 · 稀疏索引", "Kafka原理_存储_02Segment.svg"),
                ("记录批 · magic v2 + 追加路径", "Kafka原理_存储_03记录批.svg"),
                ("清理 · retention 删除 vs compaction 压缩", "Kafka原理_存储_04清理.svg"),
                ("页缓存 + 零拷贝 sendfile", "Kafka原理_存储_05零拷贝.svg")],
    "replwalk": [("Leader/Follower 复制", "Kafka原理_副本_01复制.svg"),
                 ("ISR 与高水位 HW", "Kafka原理_副本_02ISR.svg"),
                 ("acks / min.insync · 不丢语义", "Kafka原理_副本_03acks.svg"),
                 ("leader epoch 与截断", "Kafka原理_副本_04epoch.svg")],
    "groupwalk": [("组协调器 · 两层架构", "Kafka原理_消费组_01协调器.svg"),
                  ("rebalance · KIP-848 服务端分配", "Kafka原理_消费组_02rebalance.svg"),
                  ("位点管理 · __consumer_offsets", "Kafka原理_消费组_03位点.svg")],
    "kraftwalk": [("KRaft 控制器 · 元数据即事件日志", "Kafka原理_KRaft_01控制器.svg"),
                  ("Raft 共识 · KafkaRaftClient", "Kafka原理_KRaft_02Raft.svg"),
                  ("元数据传播 · 控制器→Broker", "Kafka原理_KRaft_03传播.svg"),
                  ("Broker 角色与 quorum", "Kafka原理_KRaft_04角色.svg")],
    "netwalk": [("Reactor 线程模型", "Kafka原理_网络_01线程模型.svg"),
                ("KafkaApis 请求分派", "Kafka原理_网络_02分派.svg"),
                ("Purgatory 延迟操作", "Kafka原理_网络_03purgatory.svg")],
    "txnwalk": [("幂等生产者 · PID+序列号", "Kafka原理_事务_01幂等.svg"),
                ("事务 · 跨分区原子写", "Kafka原理_事务_02事务.svg"),
                ("read_committed · 只读已提交", "Kafka原理_事务_03读已提交.svg")],
    "panowalk": [("双维模型 · 能力域 × 执行时机", "Kafka原理_双维模型.svg"),
                 ("总架构图 · Broker 数据面 + KRaft 元数据面", "Kafka原理_总架构图.svg"),
                 ("依赖矩阵 · 接触面 × 能力域", "Kafka原理_依赖矩阵.svg"),
                 ("能力域依赖关系图", "Kafka原理_依赖关系图.svg")],
}
# 快速开始「上手总览」用独立复合渲染器 renderQsTour(总览 SVG + 5 步选择器 + 内容区),不走通用 SVG-walk
_QSTOUR_OVERVIEW_B64 = _design_b64("Kafka上手_00总览.svg")  # 无此素材 → 空;quickstart 未挂载

def _build_svg_blocks(specs, tips=None, table=None):
    """复刻 _build_multi_blocks 的左垂直 TAB 结构,每 .do-sec 放静态 base64 <img>。
    tips 非空时,末尾追加一个「要点」sec(一句话总纲 banner + 调优 + 误区)。
    table=(label, tid) 时,末尾追加一个 sec,内含空 .do-out(由 renderSvgWalk 用 renderTableSVG 填表)。"""
    n_svg = len(specs)
    navs = "".join(
        '<button class="do-nav{act}" data-idx="{i}"><span class="do-nav-n">{n}</span>'
        '<span class="do-nav-t">{s}</span></button>'.format(
            act=(" active" if i == 0 else ""), i=i, n=i + 1, s=title)
        for i, (title, _fn) in enumerate(specs))
    secs = "".join(
        '<div class="do-sec{act}" data-idx="{i}"><h3 class="do-h">{t}</h3>'
        '<div class="do-out svg-walk-out">'
        '<img class="svg-walk-img" src="data:image/svg+xml;base64,{b64}" alt="{t}" draggable="false"/>'
        '</div></div>'.format(
            act=(" active" if i == 0 else ""), t=title, i=i, b64=_design_b64(fn))
        for i, (title, fn) in enumerate(specs))
    idx = n_svg
    if table:
        _tlabel, _ttid = table
        navs += ('<button class="do-nav" data-idx="{i}"><span class="do-nav-n">✦</span>'
                 '<span class="do-nav-t">{l}</span></button>').format(i=idx, l=_tlabel)
        secs += ('<div class="do-sec" data-idx="{i}"><h3 class="do-h">{l}</h3>'
                 '<div class="do-out" id="svgwalk-tbl-{tt}"></div></div>').format(i=idx, l=_tlabel, tt=_ttid)
        idx += 1
    if tips:
        navs += ('<button class="do-nav" data-idx="{i}"><span class="do-nav-n">✦</span>'
                 '<span class="do-nav-t">要点</span></button>').format(i=idx)
        secs += _build_tips_sec(idx, tips)
    return ('<div class="do-nav-col"><div class="do-nav-sticky">{navs}</div></div>'
            '<div class="do-stage">{secs}</div>').format(navs=navs, secs=secs)

# ---- prose 要点集成:解析 13 篇 design 文档尾三节(总纲/调优/误区)----
import html as _html
import re as _re_prose

def _md_inline(s):
    """把 md 行内 **bold**/`code` 转 HTML,其余转义。
    先 bold(非贪婪,容忍 `code` 内的 * 如 SELECT *)再 code。"""
    s = _html.escape(s)
    s = _re_prose.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = _re_prose.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return s

def _parse_prose_tips(path):
    """从一篇 md 抽 {summary, tuning, pitfalls, tables}。缺节返回空串/空列表。
    tables:深化/拓展/编号章节里的对比表 [{caption, headers, rows}]。"""
    import re as _r
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return None
    def _section(name):
        m = _r.search(r'^##\s+' + name + r'[^\n]*\n(.*?)(?=^##\s|\Z)', txt, _r.S | _r.M)
        return m.group(1).strip() if m else ""
    def _bullets(sec):
        return [_md_inline(ln[1:].strip())
                for ln in sec.splitlines() if ln.strip().startswith("-")]
    summary_raw = _section("一句话总纲")
    summary = _md_inline(" ".join(l.strip() for l in summary_raw.splitlines() if l.strip()))
    # 定位声明:文首 `> **定位**：...` blockquote —— 该主题是什么能力域、与其他主题的关系
    _pos = _r.search(r'^>\s*\*\*定位\*\*[:：]\s*(.+)$', txt, _r.M)
    position = _md_inline(_pos.group(1).strip()) if _pos else ""
    # 提取深化对比表:遍历所有 ## 章节,标题含 深化/拓展/编号 且正文有 md 表
    tables = []
    seen_caps = set()
    for m in _r.finditer(r'^##\s+(.+?)\n(.*?)(?=^##\s|\Z)', txt, _r.S | _r.M):
        title, body = m.group(1).strip(), m.group(2)
        # 章节筛选:深化/拓展/补充 或 中文数字编号开头
        if not _r.search(r'深化|拓展|补充|^[一二三四五六七八九十]、', title):
            continue
        rows_raw = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
        if len(rows_raw) < 3:   # 需 表头 + 分隔 + ≥1 行
            continue
        def _cells(ln):
            return [_md_inline(c.strip()) for c in ln.strip().strip("|").split("|")]
        headers = _cells(rows_raw[0])
        # rows_raw[1] 是 |---| 分隔行,跳过
        data = [_cells(ln) for ln in rows_raw[2:] if not _r.match(r'^\|[\s:|-]+\|?$', ln)]
        if not data:
            continue
        cap = _r.sub(r'^(深化|拓展|补充)\s*[·:：]?\s*', '', title)
        cap = _r.sub(r'^[一二三四五六七八九十]+、\s*', '', cap)
        cap = _r.sub(r'（.*?）|\(.*?\)', lambda x: x.group(0), cap).strip()
        if cap in seen_caps:
            continue
        seen_caps.add(cap)
        tables.append({"caption": _md_inline(cap), "headers": headers, "rows": data})
    return {
        "summary": summary,
        "position": position,
        "tuning": _bullets(_section("调优要点")),
        "pitfalls": _bullets(_section("常见误区")),
        "tables": tables,
    }

# walk tid → prose md 文件(全局 2 图无 prose)
_WALK_PROSE = {
    "apiwalk": "Kafka原理_接触面_生产与消费API.md",
    "logwalk": "Kafka原理_支撑_日志存储.md",   "replwalk": "Kafka原理_支撑_副本与ISR.md",
    "groupwalk": "Kafka原理_支撑_消费者组与协调.md", "kraftwalk": "Kafka原理_支撑_KRaft元数据.md",
    "netwalk": "Kafka原理_支撑_网络与请求处理.md", "txnwalk": "Kafka原理_支撑_事务与幂等.md",
}
_PROSE_TIPS = {tid: _parse_prose_tips(os.path.join(_DESIGN_DIR, fn))
               for tid, fn in _WALK_PROSE.items()}

def _md_table(tbl):
    """一张对比表 → Apple 工业风 HTML table。tbl={caption, headers, rows}。"""
    th = "".join("<th>" + h + "</th>" for h in tbl["headers"])
    trs = "".join("<tr>" + "".join("<td>" + c + "</td>" for c in r) + "</tr>" for r in tbl["rows"])
    return ('<table class="walk-dtable"><caption>{cap}</caption>'
            '<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>').format(
        cap=tbl["caption"], th=th, trs=trs)

def _build_tips_sec(idx, tips):
    """要点 sec:一句话总纲 banner + 调优/误区 两栏 + 深化对比表。"""
    def _col(title, items):
        if not items:
            return ""
        lis = "".join('<li>' + it + '</li>' for it in items)
        return ('<div class="walk-tipcol"><div class="walk-tiph">{t}</div>'
                '<ul class="walk-tiplist">{lis}</ul></div>').format(t=title, lis=lis)
    position = ('<div class="walk-position"><span class="walk-position-tag">定位</span>{p}</div>'.format(p=tips["position"])
                if tips.get("position") else "")
    banner = ('<div class="walk-summary">{s}</div>'.format(s=tips["summary"])
              if tips.get("summary") else "")
    cols = _col("调优要点 · 关键开关", tips.get("tuning")) + _col("常见误区 · 工程要点", tips.get("pitfalls"))
    deepen = ""
    if tips.get("tables"):
        deepen = ('<div class="walk-deepen"><div class="walk-deepen-h">深化 · 对比速查</div>'
                  + "".join(_md_table(t) for t in tips["tables"]) + '</div>')
    return ('<div class="do-sec" data-idx="{i}"><h3 class="do-h">要点 · 定位 / 总纲 / 调优 / 误区 / 深化</h3>'
            '<div class="do-out walk-tips-out">{position}{banner}<div class="walk-tips">{cols}</div>{deepen}</div></div>').format(
        i=idx, position=position, banner=banner, cols=cols, deepen=deepen)

_SVG_WALK_TABLES = {"deploywalk": ("要点", "archcompare")}
_SVG_WALK_PANES = {tid: _build_svg_blocks(specs, _PROSE_TIPS.get(tid), _SVG_WALK_TABLES.get(tid))
                   for tid, specs in _SVG_WALK_SPECS.items()}

# === 数据组织架构:四张 mermaid 图(替代原层级树)==========================
# 约定:图一节点 ID = 下钻 key(olapScanNode/rowsetClose/segWrite/segIter/blockReader),
# 使其可下钻真实源码;图二~四为 ID 加前缀的说明图(不与下钻 key 冲突)。
DATAORG_MMS = [
 ("图一 · 总体层级(Catalog → Block)", r'''flowchart TB
  C["Catalog / Database<br/><small>命名空间与元数据容器</small>"]
  C --> T["Table / OlapTable<br/><small>Schema · Key Model · 分区/分桶/副本/Rollup-MV 策略</small>"]
  T --> P1["Partition<br/><small>版本可见性边界 visible_version · TTL · 冷热分层单元</small>"]
  P1 --> BI["Base MaterializedIndex<br/><small>主表物化数据视图</small>"]
  P1 --> RI1["Rollup / 同步 MV Index<br/><small>预聚合 · 裁剪列 · 改变排序键</small>"]
  BI --> olapScanNode["Tablet / Bucket<br/><small>P×I×B 后的分布式分片 · 调度/副本/Compaction 核心单位</small>"]
  olapScanNode --> RP1["Replica (BE-1)<br/><small>物理副本 · 持有 Rowset · MoW 额外持 Delete Bitmap</small>"]
  olapScanNode --> RP2["Replica (BE-2)"]
  olapScanNode --> RP3["Replica (BE-3)"]
  RP1 --> rowsetClose["Rowset [start-end]<br/><small>不可变版本化文件组 · 事务或 Compaction 产物</small>"]
  rowsetClose --> segWrite["Segment {rowset_id}_{seg}.dat<br/><small>列式不可变文件 · 通常 1 次 flush 产 1 个</small>"]
  segWrite --> PG["Column Data Pages<br/><small>编码/压缩/读取/裁剪粒度 · 默认约 64KB</small>"]
  segWrite --> segIter["Segment 内部索引<br/><small>Ordinal(每列必须) · ShortKey · ZoneMap · Bloom · PK(MoW)</small>"]
  segWrite --> FT["Segment Footer<br/><small>行数 · 列元数据 · 索引位置 · 编码压缩信息</small>"]
  rowsetClose -. "查询时读取解码生成" .-> blockReader["Block<br/><small>内存列式批次 · 向量化执行单位 · 不对应磁盘 · 行数可变</small>"]
  classDef fe stroke:#3d6fe0,color:#1d5fb8;
  classDef be stroke:#c1962a,color:#8a5a12;
  classDef mem stroke:#12a37a,color:#146c4b;
  class C,T,P1,BI,RI1,olapScanNode,RP1,RP2,RP3 fe;
  class rowsetClose,segWrite,PG,segIter,FT be;
  class blockReader mem;'''),

 ("图二 · FE 元数据 ↔ BE 物理存储对应", r'''flowchart LR
  subgraph FE["FE 元数据层"]
    direction TB
    fT["Table"] --> fP["Partition<br/><small>visible_version</small>"] --> fMI["MaterializedIndex<br/><small>Base / Rollup / Sync MV</small>"] --> fTB["Tablet"] --> fR["Replica 元信息<br/><small>backend_id · version · state · schema_hash</small>"]
  end
  subgraph BE["BE 物理存储层"]
    direction TB
    bBE["BE Node"] --> bDD["DataDir<br/><small>每块磁盘一个</small>"] --> bSH["data/{shard_id}/<br/><small>分散目录,避免单目录文件过多</small>"] --> bTD["{tablet_id}/"] --> bSD["{schema_hash}/<br/><small>tablet schema 的哈希值</small>"]
    bSD --> bTM["tablet_meta (RocksDB)<br/><small>schema · Rowset 列表 · cumulative_point · Delete Bitmap(MoW)</small>"]
    bSD --> bRS["Rowset 文件组"]
    bRS --> bSG["Segment .dat<br/><small>列数据 + 内部索引 + footer</small>"]
    bRS --> bIX["Inverted Index .idx<br/><small>可选,独立文件</small>"]
  end
  fR -. "定位到具体 BE 副本" .-> bTD
  classDef fe stroke:#3d6fe0,color:#1d5fb8;
  classDef be stroke:#c1962a,color:#8a5a12;
  class fT,fP,fMI,fTB,fR fe;
  class bBE,bDD,bSH,bTD,bSD,bTM,bRS,bSG,bIX be;'''),

 ("图三 · Rowset 版本链与 Compaction", r'''flowchart TB
  subgraph W["写入后:多个小 Rowset(OVERLAPPING)"]
    direction LR
    wA0["[0-1] Base"] --> wA1["[2-2]"] --> wA2["[3-3]"] --> wA3["[4-4]"] --> wA4["[5-5]"] --> wA5["[6-6]"]
  end
  subgraph CC["Cumulative Compaction<br/><small>合并 cumulative_point 以上的小 Rowset</small>"]
    direction LR
    cB0["[0-1] Base"] --> cB1["[2-4] NONOVERLAPPING"] --> cB2["[5-5]"] --> cB3["[6-6]"]
  end
  subgraph BC["Base Compaction<br/><small>[2-4] 晋升后合入 Base</small>"]
    direction LR
    xC0["[0-4] 新 Base"] --> xC1["[5-5]"] --> xC2["[6-6]"]
  end
  W ==> CC ==> BC
  classDef w stroke:#c1962a,color:#8a5a12;
  classDef c stroke:#3d6fe0,color:#1d5fb8;
  class wA0,wA1,wA2,wA3,wA4,wA5 w;
  class cB0,cB1,cB2,cB3,xC0,xC1,xC2 c;'''),

 ("图四 · Segment 内部结构", r'''flowchart TB
  SEG["Segment (.dat 文件)<br/><small>列式存储 · 写入后不可变</small>"]
  SEG --> sC0["Column 0 Data Pages<br/><small>按列独立存储 · LZ4F/ZSTD 压缩</small>"]
  SEG --> sC1["Column 1 Data Pages"]
  sC0 --> sP0["Page 0(默认 64KB)<br/><small>编码/压缩/索引定位基础粒度 · ≠ OS IO 粒度</small>"]
  sC0 --> sP1["Page 1"]
  SEG --> sOI["Ordinal Index<br/><small>每列必须 · 行号→Page 定位 · 缺失报 Corruption</small>"]
  SEG --> sSKI["Short Key Index Page<br/><small>每 num_rows_per_block(默认1024)行一项 · sort key 前缀</small>"]
  SEG --> sZMI["Zone Map Index<br/><small>每 Page 的 min/max · 跳过不相关 Page</small>"]
  SEG --> sBFI["Bloom Filter Index<br/><small>可选 · 等值查询加速</small>"]
  SEG --> sPKI["Primary Key Index Page<br/><small>MoW 专有 · 写入时构建</small>"]
  SEG --> sFTR["Segment Footer (Protobuf)<br/><small>列元数据 · 索引位置 · 行数</small>"]
  SEG -.-> sINV["Inverted Index (.idx 独立文件,可选)<br/><small>全文/范围检索 · 随 Segment 生命周期管理</small>"]
  sBM["★ 旧 Bitmap Index 已废弃<br/><small>proto 标 deprecated · ColumnReader 不初始化 · 改用 Inverted Index</small>"]
  classDef be stroke:#c1962a,color:#8a5a12;
  classDef idx stroke:#3d6fe0,color:#1d5fb8;
  classDef dep stroke:#d0555f,color:#b03a44;
  class SEG,sC0,sC1,sP0,sP1,sFTR be;
  class sOI,sSKI,sZMI,sBFI,sPKI,sINV idx;
  class sBM dep;'''),
]

# === 集成架构:三栏分层图(数据源 → Doris 引擎栈 → 服务消费,治理横切)============
# 逻辑:业务源→接入→数仓分层→消费(写入链);数据湖→联邦 Catalog→消费(联邦链);
# 数仓分层「运行于」执行与存储引擎(substrate,虚线);治理横切。edge 全部走亮色 linkStyle。
ARCHINTEG_MM = r'''flowchart LR
  subgraph SRC["数据源 · DATA SOURCES"]
    direction TB
    s_db["业务库<br/><small>MySQL · PG · Oracle</small>"]
    s_mq["消息流<br/><small>Kafka · Pulsar</small>"]
    s_http["IoT / 埋点<br/><small>HTTP 直推</small>"]
    s_lake["数据湖<br/><small>Hive · Iceberg · Paimon</small>"]
  end
  subgraph DORIS["Apache Doris 引擎"]
    direction TB
    subgraph INGEST["① 接入层 · 写入"]
      direction TB
      g_cdc["Flink CDC<br/><small>2PC Exactly-Once</small>"]
      g_rl["Routine Load<br/><small>Kafka At-Least-Once</small>"]
      g_sl["Stream Load + Group Commit<br/><small>高频小批必用</small>"]
    end
    g_fed["External Catalog<br/><small>联邦直查 · 免搬运</small>"]
    subgraph WH["② 数仓分层"]
      direction LR
      w_ods["ODS 原始层<br/><small>Duplicate Key 贴源</small>"] --> w_dwd["DWD 明细层<br/><small>Unique/MoW 去重</small>"] --> w_dws["DWS 汇总层<br/><small>Aggregate+同步MV</small>"] --> w_ads["ADS 应用层<br/><small>异步MTMV·SPJG</small>"]
    end
    subgraph ENG["③ 执行与存储引擎(数仓分层运行于此)"]
      direction LR
      e_fe["FE<br/><small>Nereids·Catalog·元数据</small>"]
      e_be["BE<br/><small>Pipeline·向量化·列存</small>"]
      e_st["存储<br/><small>Tablet/Rowset/Segment</small>"]
    end
  end
  subgraph CONS["服务消费 · CONSUMPTION"]
    direction TB
    c_bi["BI 报表<br/><small>JDBC 9030 · &lt;5s · 并发100+</small>"]
    c_api["数据 API<br/><small>点查+倒排 · &lt;100ms · 并发1000+</small>"]
    c_ds["数据科学<br/><small>Arrow Flight SQL (ADBC)</small>"]
    c_exp["导出交换<br/><small>OUTFILE → HDFS / S3</small>"]
  end
  gv["治理 + 稳定性(横切)· RBAC · 行列权限 · 审计 · TTL · Workload Group · 监控 · 备份恢复"]
  s_db --> g_cdc
  s_mq --> g_rl
  s_http --> g_sl
  s_lake --> g_fed
  g_cdc --> w_ods
  g_rl --> w_ods
  g_sl --> w_ods
  w_ads --> c_bi
  w_ads --> c_ds
  w_ads --> c_exp
  g_fed --> c_api
  w_dwd -. 运行于 .-> e_be
  e_fe -.-> gv
  classDef src stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef ingest stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef fed stroke:#b04fc0,color:#7a3fb0,stroke-width:1.4px;
  classDef wh stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  classDef eng stroke:#7c5fe6,color:#5b3fd6,stroke-width:1.4px;
  classDef cons stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef gov stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  class s_db,s_mq,s_lake,s_http src;
  class g_cdc,g_rl,g_sl ingest;
  class g_fed fed;
  class w_ods,w_dwd,w_dws,w_ads wh;
  class e_fe,e_be,e_st eng;
  class c_bi,c_api,c_ds,c_exp cons;
  class gv gov;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''

# === 索引过滤链路:查询时索引按层裁剪的执行顺序 ==========================
IDXCHAIN_MM = r'''flowchart TB
  Q["示例 SQL<br/><small>SELECT * FROM sales WHERE dt BETWEEN '2026-01-01' AND '2026-01-07'<br/>AND user_id = 10086 AND content MATCH_ALL '促销 秒杀' ORDER BY id</small>"]
  Q --> S1
  subgraph L1["① Segment 级粗过滤"]
    S1["Short Key / Primary Key Index<br/><small>dt 是排序键前缀 → 前缀二分定位 rowid 范围;MoW 主键点查走 PK</small>"]
  end
  S1 --> S2
  subgraph L2["② Page 级跳过(统计索引)"]
    direction TB
    S2["Zone Map Index<br/><small>dt BETWEEN → 按 Page min/max 跳整段不相关 Page</small>"]
    S3["Bloom Filter / NGram BF<br/><small>user_id = 10086 → BF hash 探测跳不命中 Page(有假阳性,只跳不误留)</small>"]
    S2 --> S3
  end
  S3 --> S4
  subgraph L3["③ 行级精确定位"]
    S4["Inverted Index<br/><small>content MATCH_ALL '促销 秒杀' → 倒排链 Roaring Bitmap,直接得 rowid 集合</small>"]
    S4b["ANN Index<br/><small>(若 ORDER BY l2_distance) HNSW/IVF 近似 → 候选 rowid TopK</small>"]
  end
  S4 --> S5
  S4b -.-> S5
  subgraph L4["④ 删除语义(MoW)"]
    S5["Delete Bitmap<br/><small>RocksDB 行级位图 → 扣掉已删除/被覆盖行</small>"]
  end
  S5 --> S6["⑤ 读取 Column Pages → 解码 → 向量化谓词二次过滤<br/><small>user_id=10086 等 BF 假阳性在此精确复核;dt 边界精确判定</small>"]
  S6 --> R["结果行"]
  classDef q stroke:#7c5fe6,color:#5b3fd6;
  classDef l1 stroke:#2f9e6e,color:#146c4b;
  classDef l2 stroke:#b08b3a,color:#8a5a12;
  classDef l3 stroke:#3d6fe0,color:#1d5fb8;
  classDef ann stroke:#d9722a,color:#8a5a12;
  classDef l4 stroke:#e02b68,color:#b03060;
  classDef fin stroke:#8b93a3,color:#3a4a63;
  class Q q; class S1 l1; class S2,S3 l2; class S4 l3; class S4b ann; class S5 l4; class S6,R fin;'''

# === 核心优化策略架构关系图:9 类资源主轴在 FE/BE/Storage/写入主线上的落点 ===
OPTARCH_MM = r'''flowchart TB
    Q["SQL / Insert / Load 请求"] --> FE_ENTRY["FE SQL 入口<br/>ConnectProcessor / StmtExecutor"]
    FE_ENTRY --> FE_PLAN["FE 编译调度层<br/>Nereids Planner / Coordinator"]
    FE_PLAN --> O1["规划开销<br/>缓存元数据/统计/复用计划<br/>Catalog Cache · Stats · Plan Cache"]
    FE_PLAN --> O2["扫描对象数量<br/>分区/Tablet/文件裁剪<br/>Partition/Tablet/Bucket/File Prune"]
    FE_PLAN --> O5S["流入算子行数(静态)<br/>谓词下推/推导<br/>Predicate Pushdown/Inference"]
    FE_PLAN --> O6P["网络 Shuffle(规划决策)<br/>Broadcast/Shuffle/Bucket Shuffle/Colocate"]
    FE_PLAN --> O7P["算子计算状态(计划优化)<br/>Join Reorder · 聚合/TopN 下推"]
    FE_PLAN --> O8P["重复计算(规划复用)<br/>MV 改写 · Plan Cache · Prepared Plan"]
    O1 --> FRAG["Fragment / Scan Range / RF 描述"]
    O2 --> FRAG
    O5S --> FRAG
    O6P --> FRAG
    O7P --> FRAG
    O8P --> FRAG
    FRAG --> BE_ENTRY["BE 执行入口<br/>PInternalService / FragmentMgr"]
    BE_ENTRY --> PIPE["BE Pipeline 执行层<br/>PipelineTask / Operators"]
    PIPE --> SCAN["Scan Operators<br/>OlapScan / FileScan"]
    PIPE --> JOIN["Join Operators"]
    PIPE --> AGG["Aggregate Operators"]
    PIPE --> SORT["Sort / TopN Operators"]
    PIPE --> EXCHANGE["Exchange / Local Exchange"]
    PIPE --> RESULT["Result Sink<br/>FE ResultReceiver 拉取结果"]
    SCAN --> O3["存储单元读取<br/>调索引/统计跳数据<br/>ZoneMap/Bloom/倒排/Parquet MinMax/Page Index/ORC SARG"]
    SCAN --> O4["读取列和字节<br/>延迟物化/字典过滤/少解码<br/>Column Pruning · Lazy Materialization · Dict Filter"]
    SCAN --> O5C["流入算子行数(动态消费)<br/>Runtime Filter Probe 消费 · TopN Filter 消费"]
    JOIN --> O5B["流入算子行数(动态生成)<br/>Join Build 侧生成 RF → 传给 Probe 侧 Scan"]
    JOIN --> O6E["网络 Shuffle(Join 执行)<br/>Broadcast/Shuffle/Bucket Shuffle/Colocate"]
    JOIN --> O7J["算子计算状态(Join)<br/>Hash Table 控制 · Join Reorder 执行结果"]
    AGG --> O7A["算子计算状态(Agg)<br/>本地预聚合 · 两阶段聚合"]
    SORT --> O7T["算子计算状态(Sort/TopN)<br/>TopN Pushdown · 局部 TopN"]
    EXCHANGE --> O6E2["网络 Shuffle(Exchange)<br/>Local Exchange · 减跨节点传输"]
    PIPE --> O8E["重复计算(执行复用)<br/>Query Cache · Data Cache"]
    SCAN --> STORAGE["Storage 存储引擎层<br/>Tablet / Rowset / Segment"]
    STORAGE --> S1["Tablet · 分区/分桶/副本"]
    STORAGE --> S2["Rowset · 版本化数据集合"]
    STORAGE --> S3["Segment · 列存/编码/压缩"]
    STORAGE --> S4["Index & Statistics<br/>ZoneMap/Bloom/倒排/字典/Footer/Page Index"]
    STORAGE --> S5["Version & Delete<br/>Version Graph · Delete Bitmap"]
    STORAGE --> S6["Compaction · 合并 Rowset · 降读放大"]
    S4 --> O3
    S3 --> O4
    S4 --> O8S["重复计算(Storage 复用)<br/>Footer Cache · 数据块缓存"]
    Q --> WRITE["写入主线<br/>Insert / Stream Load / Broker Load"]
    WRITE --> FE_WRITE["FE 写入计划<br/>Sink / Tablet 路由 / 并行度"]
    FE_WRITE --> BE_WRITE["BE 写入入口<br/>tablet_writer_open / add_block"]
    BE_WRITE --> LOAD["Load Channel<br/>LoadChannelMgr / LoadChannel / TabletsChannel"]
    LOAD --> SEGWRITE["MemTable / Segment Writer<br/>排序/聚合/编码/压缩/索引构建"]
    SEGWRITE --> O9["写入与维护<br/>Load Channel/Tablet Writer<br/>Rowset/Segment/Compaction/版本管理"]
    O9 --> STORAGE
    RESULT --> OUT["结果返回客户端"]
    classDef fe stroke:#6BA3D6,color:#1F3B57;
    classDef be stroke:#73B987,color:#21452C;
    classDef storage stroke:#D6A35C,color:#5A3B12;
    classDef opt stroke:#9D7DD8,color:#38235F;
    classDef io stroke:#D97B7B,color:#5C1F1F;
    class FE_ENTRY,FE_PLAN,FRAG,FE_WRITE fe;
    class BE_ENTRY,PIPE,SCAN,JOIN,AGG,SORT,EXCHANGE,RESULT,BE_WRITE,LOAD,SEGWRITE be;
    class STORAGE,S1,S2,S3,S4,S5,S6 storage;
    class O1,O2,O3,O4,O5S,O5C,O5B,O6P,O6E,O6E2,O7P,O7J,O7A,O7T,O8P,O8E,O8S,O9 opt;
    class Q,WRITE,OUT io;
    linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''

# === 湖仓架构:融合「FE→BE→存储 查询执行链」与「Multi-Catalog 联邦」的统一分层图 ====
LAKEHOUSE_MM = r'''flowchart TB
  Client["MySQL Client / JDBC / Arrow Flight SQL"]
  subgraph FE["FE 前端 · Java(元数据 + 规划 + 调度)"]
    direction LR
    f_nereids["Nereids 优化器<br/><small>解析→绑定→RBO/CBO→分布式计划</small>"]
    f_cat["CatalogMgr<br/><small>Internal + External Catalog</small>"]
    f_cache["ExternalMetaCacheMgr<br/><small>partition/file/schema · Caffeine+TTL</small>"]
    f_coord["Coordinator<br/><small>切 Fragment · 下发 BE RPC</small>"]
    f_nereids --> f_coord
    f_cat --> f_cache
  end
  subgraph BE["BE 后端 · C++(Pipeline 向量化执行)"]
    direction LR
    b_pipe["PipelineTask<br/><small>调度 · 向量化算子</small>"]
    b_scan["ScannerScheduler<br/><small>并行扫描调度</small>"]
    subgraph RD["格式分派 Reader"]
      direction TB
      b_seg["内表 SegmentIterator<br/><small>列存 + 三索引 + 延迟物化</small>"]
      b_native["外表 NativeReader<br/><small>C++ 直读 Parquet/ORC</small>"]
      b_jni["外表 JniConnector<br/><small>JNI 读 Hudi/Avro/复杂格式</small>"]
    end
    b_pipe --> b_scan --> RD
  end
  subgraph SRC["数据源 · 内表 + 外部 Catalog(Doris 侧连接器)"]
    direction TB
    i_tab["内表 Tablet/Rowset/Segment<br/><small>Doris 自有列存(本地/对象)</small>"]
    x_hms["HMSExternalCatalog<br/><small>Hive · Hudi</small>"]
    x_ice["IcebergExternalCatalog<br/><small>REST/HMS/Glue/DLF</small>"]
    x_paimon["PaimonExternalCatalog<br/><small>Apache Paimon</small>"]
    x_jdbc["JdbcExternalCatalog<br/><small>MySQL/PG/Oracle</small>"]
  end
  subgraph MS["Metastore · 外部元数据服务(库表/分区/schema/快照)"]
    direction LR
    m_hms["Hive Metastore<br/><small>Thrift · 库表/分区/SD</small>"]
    m_rest["Iceberg Catalog<br/><small>REST / Glue / DLF / HMS</small>"]
    m_paimon["Paimon Catalog<br/><small>FileSystem / HMS</small>"]
    m_jdbc["JDBC 源库字典<br/><small>information_schema</small>"]
  end
  subgraph STO["底层存储 · 数据文件"]
    direction LR
    st_local["本地磁盘<br/><small>存算一体</small>"]
    st_hdfs["HDFS"]
    st_obj["S3 / OSS / COS / GCS"]
  end
  Client ==> f_nereids
  f_coord ==> b_pipe
  b_seg ==> i_tab
  b_native ==> x_ice
  b_native ==> x_paimon
  b_jni ==> x_hms
  x_hms -.取元数据.-> m_hms
  x_ice -.取元数据.-> m_rest
  x_paimon -.取元数据.-> m_paimon
  x_jdbc -.取元数据.-> m_jdbc
  f_cache -.缓存.-> m_hms
  f_cache -.缓存.-> m_rest
  m_hms -.定位文件.-> st_hdfs
  m_rest -.定位文件.-> st_obj
  m_paimon -.定位文件.-> st_obj
  i_tab ==> st_local
  b_native ==> st_obj
  b_jni ==> st_hdfs
  classDef cli stroke:#7c5fe6,color:#5b3fd6,stroke-width:1.4px;
  classDef fe stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  classDef be stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef ms stroke:#b04fc0,color:#7a3fb0,stroke-width:1.4px;
  classDef src stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef sto stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  class Client cli;
  class f_nereids,f_cat,f_cache,f_coord fe;
  class b_pipe,b_scan,b_seg,b_native,b_jni be;
  class i_tab,x_hms,x_ice,x_paimon,x_jdbc src;
  class m_hms,m_rest,m_paimon,m_jdbc ms;
  class st_local,st_hdfs,st_obj sto;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''

# === 索引体系架构:三张图(存储层位置 / 查询协同 / 能力分层),左侧竖 tab 切换 =====
# 图一节点 ID 复用下钻 key(olapScanNode/rowsetClose/segWrite/segIter/blockReader),可下钻源码。
IDXARCH_MMS = [
 ("图一 · 索引在存储层级中的位置", r'''flowchart TB
  T["Table / OlapTable"] --> P["Partition<br/><small>visible_version</small>"]
  P --> MI["MaterializedIndex<br/><small>Base / Rollup / Sync MV</small>"]
  MI --> olapScanNode["Tablet / Bucket"]
  olapScanNode --> RP["Replica<br/><small>BE 上的物理副本</small>"]
  RP --> TM["Tablet Meta / RocksDB<br/><small>Rowset 列表 / cumulative_point / Delete Bitmap</small>"]
  RP --> rowsetClose["Rowset<br/><small>带版本区间的不可变文件组</small>"]
  rowsetClose --> segWrite["Segment .dat<br/><small>列式不可变文件</small>"]
  rowsetClose --> IDXFILE["独立 .idx 文件<br/><small>Inverted / ANN</small>"]
  segWrite --> COL["Column Data Pages"]
  segWrite --> segIter["Ordinal / ShortKey / PK / ZoneMap / Bloom / NGram BF<br/><small>Segment 内部索引</small>"]
  segWrite --> FT["Footer<br/><small>索引位置 / 行数 / 编码压缩</small>"]
  IDXFILE --> INV["Inverted Index<br/><small>全文 / 等值 / 范围 / LIKE</small>"]
  IDXFILE --> ANN["ANN Index<br/><small>向量近似检索</small>"]
  TM --> DBM["Delete Bitmap<br/><small>MoW 行级删除标记</small>"]
  COL --> blockReader["Block<br/><small>解码后的内存列式批次</small>"]
  classDef fe stroke:#3d6fe0,color:#1d5fb8;
  classDef be stroke:#c1962a,color:#8a5a12;
  classDef idx stroke:#9d4fe0,color:#5b3fd6;
  classDef mem stroke:#12a37a,color:#146c4b;
  class T,P,MI,olapScanNode,RP fe;
  class TM,rowsetClose,segWrite,COL,segIter,FT be;
  class IDXFILE,INV,ANN,DBM idx;
  class blockReader mem;'''),

 ("图二 · 查询时索引协同流程", r'''flowchart TB
  SQL["SQL 谓词 / ORDER BY / LIMIT"] --> FE["FE 优化器<br/><small>谓词下推 / Index 选择 / Tablet 裁剪</small>"]
  FE --> SCAN["BE Scanner"]
  SCAN --> RV["Rowset 版本选择<br/><small>选择连续版本链</small>"]
  RV --> SK["Short Key Index<br/><small>排序键定位扫描范围</small>"]
  RV --> PK["Primary Key Index<br/><small>MoW 主键点查定位</small>"]
  RV --> INV["Inverted / ANN Index<br/><small>独立 .idx 得候选 rowid</small>"]
  RV --> DBM["Delete Bitmap<br/><small>过滤被更新/删除 rowid</small>"]
  SK --> SEG["Segment 候选集"]
  PK --> ROWID["RowId 候选集"]
  INV --> ROWID
  DBM --> ROWID
  SEG --> ZM["ZoneMap<br/><small>Segment/Page min-max 裁剪</small>"]
  ZM --> BF["Bloom / NGram BF<br/><small>Page 级概率过滤</small>"]
  BF --> OI["Ordinal Index<br/><small>rowid/ordinal 定位到 Page</small>"]
  ROWID --> OI
  OI --> PAGE["读取必要 Column Page"]
  PAGE --> DECODE["解压 / 解码 / 谓词复核"]
  DECODE --> BLK["Block"] --> OP["Vectorized Operators"]
  classDef fe stroke:#3d6fe0,color:#1d5fb8;
  classDef loc stroke:#2f9e6e,color:#146c4b;
  classDef pg stroke:#b08b3a,color:#8a5a12;
  classDef rid stroke:#9d4fe0,color:#5b3fd6;
  classDef fin stroke:#8b93a3,color:#3a4a63;
  class SQL,FE,SCAN,RV fe;
  class SK,PK,SEG,ROWID loc;
  class ZM,BF,OI pg;
  class INV,DBM rid;
  class PAGE,DECODE,BLK,OP fin;'''),

 ("图三 · 索引能力分层", r'''flowchart LR
  subgraph L1["范围定位层"]
    direction TB
    SK["Short Key Index"]
    PK["Primary Key Index"]
  end
  subgraph L2["Page 裁剪层"]
    direction TB
    ZM["ZoneMap"]
    BF["Bloom Filter"]
    NGBF["NGram BF"]
  end
  subgraph L3["RowId 候选层"]
    direction TB
    INV["Inverted Index"]
    ANN["ANN Index"]
    DBM["Delete Bitmap"]
  end
  subgraph L4["内部寻址层"]
    OI["Ordinal Index"]
  end
  subgraph L5["执行层"]
    direction TB
    PAGE["Column Page"]
    BLOCK["Block"]
  end
  L1 ==> L2 ==> L4 ==> PAGE ==> BLOCK
  L3 ==> L4
  classDef a stroke:#2f9e6e,color:#146c4b;
  classDef b stroke:#b08b3a,color:#8a5a12;
  classDef c stroke:#9d4fe0,color:#5b3fd6;
  classDef d stroke:#3d6fe0,color:#1d5fb8;
  classDef e stroke:#8b93a3,color:#3a4a63;
  class SK,PK a; class ZM,BF,NGBF b; class INV,ANN,DBM c; class OI d; class PAGE,BLOCK e;'''),
]

# === 向量检索与倒排索引:两图(倒排全文 / 向量 ANN),各含建表+查询 SQL 与执行链 =====
# 图节点 ID 复用下钻 key(segIter/annReader/faissIndex/olapScanNode)可下钻源码。
VECSEARCH_MMS = [
 ("倒排索引 · 全文检索(INVERTED)", r'''flowchart TB
  DDL["建表<br/><small>INDEX idx_content (content) USING INVERTED<br/>PROPERTIES('parser'='chinese','support_phrase'='true')</small>"]
  SQL["查询<br/><small>SELECT * FROM docs<br/>WHERE content MATCH_ALL '数据库 引擎'<br/>AND ts &gt; '2026-01-01'</small>"]
  DDL -.建索引.-> BUILD
  subgraph WRITE["写入期 · 构建倒排"]
    direction TB
    BUILD["分词 Analyzer<br/><small>chinese/english/unicode</small>"] --> POST["倒排链 term→rowid<br/><small>CLucene 格式</small>"] --> IDXF["独立 .idx 文件<br/><small>V1/V2/V3 · 随 Segment</small>"]
  end
  subgraph READ["查询期 · MATCH 下推裁行"]
    direction TB
    FE["FE:MATCH 谓词下推<br/><small>Nereids 识别倒排可用</small>"] --> segIter["BE SegmentIterator<br/><small>_apply_inverted_index</small>"]
    segIter --> invR["读 .idx → term 查询<br/><small>Roaring Bitmap</small>"]
    invR --> RID["命中 rowid 集合<br/><small>可跳过整 Page</small>"]
    RID --> REST["回读列 + 其余谓词复核<br/><small>ts&gt; 范围二次过滤</small>"]
  end
  SQL --> FE
  IDXF -.查询时读取.-> invR
  classDef ddl stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef sql stroke:#7c5fe6,color:#5b3fd6,stroke-width:1.4px;
  classDef w stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef r stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  class DDL ddl; class SQL sql; class BUILD,POST,IDXF w; class FE,segIter,invR,RID,REST r;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("向量检索 · ANN 近似 TopK", r'''flowchart TB
  DDL["建表<br/><small>emb ARRAY&lt;FLOAT&gt; NOT NULL,<br/>INDEX idx_emb (emb) USING ANN<br/>PROPERTIES('index_type'='hnsw','metric_type'='l2_distance','dim'='768')</small>"]
  SQL["查询<br/><small>SELECT id, content,<br/>l2_distance(emb, [0.1,...]) AS dist<br/>FROM docs ORDER BY dist LIMIT 10</small>"]
  DDL -.建索引.-> BUILD
  subgraph WRITE["写入期 · 构建向量图/聚类"]
    direction TB
    BUILD["向量归一化 + 训练<br/><small>HNSW ef_construction / IVF nlist</small>"] --> faissIndex["FaissVectorIndex<br/><small>HNSW 图 / IVF 倒排</small>"] --> AIDXF["独立 .idx 文件<br/><small>随 Segment 持久化</small>"]
  end
  subgraph READ["查询期 · TopN 下推召回"]
    direction TB
    FE["FE:PushDownVectorTopNIntoOlapScan<br/><small>ORDER BY dist LIMIT k → 下推</small>"] --> annReader["BE AnnTopNRuntime<br/><small>_apply_ann_topn_predicate</small>"]
    annReader --> SEARCH["ANN 搜索<br/><small>hnsw_ef_search / ivf_nprobe</small>"]
    SEARCH --> CAND["候选 rowid TopK<br/><small>近似,非精确</small>"]
    CAND --> RESC["回读向量精确 rerank<br/><small>算精确 distance 排序</small>"]
  end
  SQL --> FE
  AIDXF -.查询时读取.-> SEARCH
  classDef ddl stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef sql stroke:#7c5fe6,color:#5b3fd6,stroke-width:1.4px;
  classDef w stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef r stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  class DDL ddl; class SQL sql; class BUILD,faissIndex,AIDXF w; class FE,annReader,SEARCH,CAND,RESC r;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]

# === 三张架构形态图改用 Mermaid(存算一体 / 存算分离 / 冷热分离),节点 ID 复用 FLOW 的 key ===
ARCHINTEG_INTG_MM = r'''flowchart TB
  subgraph W["① 写入路径"]
    direction LR
    ag_sl["Stream Load<br/><small>HTTP 直推</small>"]
    ag_bl["Broker Load<br/><small>HDFS/S3 导入</small>"]
    ag_rl["Routine Load<br/><small>Kafka 消费</small>"]
  end
  subgraph FE["② FE 集群 · Java(BDB JE)"]
    direction LR
    ag_fem["FE Master<br/><small>元数据读写 + Raft 同步</small>"]
    ag_fef["FE Follower<br/><small>只读,可选举</small>"]
    ag_feo["FE Observer<br/><small>只读,扩并发</small>"]
  end
  subgraph BE["③ BE 集群 · C++(存储+计算一体)"]
    direction LR
    ag_pipe["Pipeline 执行<br/><small>PipelineTask/Dependency 非阻塞</small>"] --> ag_op["向量化算子<br/><small>Scan/Join/Agg · 4096 行/批 SIMD</small>"] --> ag_st["StorageEngine<br/><small>Tablet 管理 + Compaction</small>"]
  end
  subgraph ST["④ 本地存储结构"]
    direction LR
    ag_tablet["Tablet(分区×Bucket)<br/><small>多副本默认 3,Rowset 同步</small>"] --> ag_rowset["Rowset<br/><small>不可变 + MVCC 多版本</small>"] --> ag_seg["Segment(.dat)<br/><small>列存 + Page 编码 LZ4/ZSTD</small>"]
    ag_rowset --> ag_idx["多级索引<br/><small>ShortKey/ZoneMap/Bloom/Inverted</small>"]
  end
  subgraph DM["⑤ 数据模型"]
    direction LR
    ag_dup["Duplicate<br/><small>明细</small>"]
    ag_uniq["Unique(MoW)<br/><small>主键 + Delete Bitmap</small>"]
    ag_agg["Aggregate<br/><small>预聚合</small>"]
  end
  ag_sl --> ag_fem
  ag_bl --> ag_fem
  ag_rl --> ag_fem
  ag_fem -.选举/同步.-> ag_fef
  ag_fem -.只读扩展.-> ag_feo
  ag_fem ==> ag_pipe
  ag_st ==> ag_tablet
  ag_seg --> ag_dup
  ag_seg --> ag_uniq
  ag_seg --> ag_agg
  classDef w stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef fe stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  classDef be stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef st stroke:#7c5fe6,color:#5b3fd6,stroke-width:1.4px;
  classDef dm stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  class ag_sl,ag_bl,ag_rl w; class ag_fem,ag_fef,ag_feo fe;
  class ag_pipe,ag_op,ag_st be; class ag_tablet,ag_rowset,ag_seg,ag_idx st;
  class ag_dup,ag_uniq,ag_agg dm;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''

ARCHDECOUPLED_MM = r'''flowchart TB
  subgraph L1["① FE(无本地数据元数据)"]
    ad_fe["FE 查询规划<br/><small>经 MetaService RPC 取 Tablet/Rowset 元数据</small>"]
  end
  subgraph L2["② MetaService · 独立 C++ 服务"]
    direction LR
    ad_ms["MetaServiceImpl<br/><small>管 Tablet/Rowset/Txn + Storage Vault</small>"] --> ad_fdb["FdbTxnKv → FoundationDB<br/><small>分布式 ACID KV · 强一致</small>"]
  end
  subgraph L3["③ BE 计算节点(无状态)"]
    ad_cn["Compute Node × N<br/><small>CloudStorageEngine · 无本地数据</small>"]
  end
  subgraph L4["④ BlockFileCache · 本地 SSD 四队列"]
    direction LR
    ad_ttl["TTL Queue(50%)<br/><small>优先级最高不驱逐</small>"]
    ad_idx["INDEX Queue(5%)<br/><small>索引缓存</small>"]
    ad_norm["NORMAL Queue(40%)<br/><small>LRU 淘汰</small>"]
    ad_disp["DISPOSABLE(5%)<br/><small>最先驱逐</small>"]
  end
  subgraph L5["⑤ 共享对象存储 + Recycler"]
    direction LR
    ad_obj["S3/OSS/COS(Storage Vault)<br/><small>所有 BE 共享单副本</small>"]
    ad_rc["Recycler<br/><small>异步清理孤立 Segment</small>"]
  end
  ad_fe ==> ad_ms
  ad_fe ==> ad_cn
  ad_ms -.元数据.-> ad_cn
  ad_cn --> ad_ttl
  ad_cn --> ad_idx
  ad_cn --> ad_norm
  ad_cn --> ad_disp
  ad_ttl ==> ad_obj
  ad_norm ==> ad_obj
  ad_rc -.清理.-> ad_obj
  classDef fe stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  classDef ms stroke:#b04fc0,color:#7a3fb0,stroke-width:1.4px;
  classDef be stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef ca stroke:#12a37a,color:#146c4b,stroke-width:1.4px;
  classDef ob stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  class ad_fe fe; class ad_ms,ad_fdb ms; class ad_cn be;
  class ad_ttl,ad_idx,ad_norm,ad_disp ca; class ad_obj,ad_rc ob;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''

ARCHTIERING_MM = r'''flowchart TB
  subgraph L1["① 配置层"]
    direction LR
    at_res["CREATE RESOURCE<br/><small>type=s3/hdfs 指向远程</small>"] --> at_pol["CREATE STORAGE POLICY<br/><small>绑 Resource + cooldown_ttl</small>"] --> at_tbl["建表设 storage_policy"]
  end
  at_hot["② 热数据(本地磁盘)· 新写 Rowset<br/><small>本地 Segment,rs-&gt;is_local()=true</small>"]
  subgraph L3["③ 冷却过程 · BE 后台"]
    direction TB
    at_need["need_cooldown()<br/><small>newest_write_ts + ttl &lt; now</small>"] --> at_cool["Tablet::cooldown()<br/><small>仅 cooldown_replica 上传,余副本 follow</small>"] --> at_upload["upload_to(resource)<br/><small>传 Segment,生成新 RowsetMeta</small>"] --> at_meta["write_cooldown_meta()<br/><small>传 meta 供其他副本同步</small>"]
  end
  at_cold["④ 冷数据(远程)· S3/HDFS<br/><small>is_local()=false,直读无 FileCache</small>"]
  at_cc["⑤ 冷数据 Compaction · cold_compaction<br/><small>远程 Rowset 合并回写,持 cold_compaction_lock</small>"]
  at_tbl ==> at_hot ==> at_need
  at_meta ==> at_cold ==> at_cc
  classDef cfg stroke:#3d6fe0,color:#1d5fb8,stroke-width:1.4px;
  classDef hot stroke:#d9722a,color:#8a5a12,stroke-width:1.4px;
  classDef cool stroke:#c1962a,color:#8a5a12,stroke-width:1.4px;
  classDef cold stroke:#8b93a3,color:#3a4a63,stroke-width:1.4px;
  class at_res,at_pol,at_tbl cfg; class at_hot hot;
  class at_need,at_cool,at_upload,at_meta cool; class at_cold,at_cc cold;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''

# 查询生命周期主线:一条 SELECT 从 Query Text 到结果返回的形态演进(11 图,dataorg 式左侧垂直堆叠)
# 贯穿示例 SQL 见 _qlife_sqlbar。节点仅用 stroke/color(不写 fill),随暗/亮主题回落 primaryColor。
QLIFE_MMS = [
 ("图〇 · 总览:计划的状态演进(两列并行:左=形态 名词,右=转换 动词)", r'''flowchart TB
  subgraph ACT["逻辑动作(转换 · 动词)"]
    direction TB
    A1["① 词法分析<br/><small>DorisLexer</small>"]
    A2["② 语法分析<br/><small>DorisParser</small>"]
    A3["③ 构建计划<br/><small>LogicalPlanBuilder</small>"]
    A4["④ 分析绑定<br/><small>Analyze / Bind</small>"]
    A5["⑤ RBO 改写<br/><small>Rewrite</small>"]
    A6["⑥ CBO 优化<br/><small>Optimize(Memo)</small>"]
    A7["⑦ 翻译<br/><small>PhysicalPlanTranslator</small>"]
    A8["⑧ 分布式规划<br/><small>DistributePlanner</small>"]
    A9["⑨ 调度下发<br/><small>Coordinator / BRPC</small>"]
    A10["⑩ 执行<br/><small>Pipeline 引擎</small>"]
    A11["⑪ 汇聚返回<br/><small>Gather</small>"]
    A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7 --> A8 --> A9 --> A10 --> A11
  end
  subgraph OBJ["内存对象(数据形态 · 名词)"]
    direction TB
    O1["Query Text<br/><small>字符串</small>"]
    O2["Token 流<br/><small>CommonTokenStream</small>"]
    O3["解析树 ParseTree<br/><small>ANTLR Context</small>"]
    O4["Unbound LogicalPlan<br/><small>引用未解析</small>"]
    O5["Bound LogicalPlan<br/><small>已绑定/类型确定</small>"]
    O6["Rewritten LogicalPlan<br/><small>等价改写后</small>"]
    O7["PhysicalPlan<br/><small>FE 内存对象</small>"]
    O8["PlanFragment · Thrift<br/><small>⇄ 序列化边界 FE→BE</small>"]
    O9["DistributedPlan<br/><small>含实例/worker</small>"]
    O10["Pipeline 运行时<br/><small>Operator / Block</small>"]
    O11["结果集 ResultSet"]
    O1 --> O2 --> O3 --> O4 --> O5 --> O6 --> O7 --> O8 --> O9 --> O10 --> O11
  end
  CLIENT(["客户端 / BI"])
  O1 -.->|消费| A1
  A1 -.->|产出| O2
  O2 -.->|消费| A2
  A2 -.->|产出| O3
  O3 -.->|消费| A3
  A3 -.->|产出| O4
  O4 -.->|消费| A4
  A4 -.->|产出| O5
  O5 -.->|消费| A5
  A5 -.->|产出| O6
  O6 -.->|消费| A6
  A6 -.->|产出| O7
  O7 -.->|消费| A7
  A7 -.->|产出| O8
  O8 -.->|消费| A8
  A8 -.->|产出| O9
  O9 -.->|消费| A9
  A9 -.->|产出| O10
  O10 -.->|消费| A10
  A10 -.->|产出| O11
  O11 -.->|消费| A11
  A11 -.->|返回| CLIENT
  classDef obj stroke:#2f9e6e,color:#146c4b;
  classDef bd  stroke:#d0873a,color:#8a5410;
  classDef act stroke:#5b7db1,color:#1b4a8a;
  classDef cli stroke:#c25b5b,color:#a03434;
  class O1,O2,O3,O4,O5,O6,O7,O9,O10,O11 obj;
  class O8 bd;
  class A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A11 act;
  class CLIENT cli;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图✚ · 接入层与缓存(Receive · Auth · Cache)", r'''flowchart TB
  Q["Query Text · 原始 SQL"]
  CONN["MySQL 协议接入 · 鉴权 · 会话变量<br/><small>SQL Block Rule 拦截</small>"]
  CACHE{"缓存命中判断<br/><small>CacheAnalyzer · CacheMode</small>"}
  RET["命中 SQL / Partition Cache<br/><small>→ 直接返回结果</small>"]
  REUSE["命中 Nereids SQL Cache<br/><small>PhysicalSqlCache → 复用编译结果</small>"]
  GO["未命中<br/><small>→ 进入词法分析(①)</small>"]
  Q --> CONN --> CACHE
  CACHE -->|数据缓存| RET
  CACHE -->|计划缓存| REUSE
  CACHE -->|未命中| GO
  classDef txt stroke:#5b7db1,color:#1b4a8a;
  classDef dec stroke:#d0873a,color:#8a5410;
  classDef hit stroke:#2f9e6e,color:#146c4b;
  classDef go  stroke:#c25b5b,color:#a03434;
  class Q,CONN txt; class CACHE dec; class RET,REUSE hit; class GO go;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图① · Token 化(词法分析 · DorisLexer)", r'''flowchart TB
  TEXT["Query Text(示例 WHERE 片段)<br/><small>WHERE o.dt >= '2026-01-01'</small>"]
  LEXER["DorisLexer<br/><small>切分字符流 · 去空白/注释 · 关键字大小写不敏感 · 产出 CommonTokenStream</small>"]
  TEXT --> LEXER
  subgraph STREAM["Token 流(带类型的记号序列)"]
    direction LR
    T1["WHERE<br/><small>关键字</small>"] --> T2["o<br/><small>标识符</small>"] --> T3[".<br/><small>符号</small>"] --> T4["dt<br/><small>标识符</small>"] --> T5[">=<br/><small>运算符</small>"] --> T6["'2026-01-01'<br/><small>字符串字面量</small>"]
  end
  LEXER --> T1
  classDef txt stroke:#5b7db1,color:#1b4a8a;
  classDef kw  stroke:#5b7db1,color:#1b4a8a;
  classDef id  stroke:#2f9e6e,color:#146c4b;
  classDef op  stroke:#d0873a,color:#8a5410;
  classDef lit stroke:#8a5bb1,color:#5b2f8a;
  class TEXT,LEXER txt; class T1 kw; class T2,T4 id; class T3,T5 op; class T6 lit;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图② · 语法分析 → 解析树 ParseTree(DorisParser)", r'''flowchart TB
  PARSER["DorisParser<br/><small>按文法归约 Token 流 → 解析树(Context 节点)</small>"]
  PARSER --> ROOT["querySpecification"]
  subgraph CLAUSES["子句节点(DorisParser.g4 真实规则名)"]
    direction LR
    SEL["selectClause<br/><small>c.region · SUM(o.amount)</small>"]
    FROM["fromClause<br/><small>orders o JOIN customers c</small>"]
    WHERE["whereClause<br/><small>o.dt >= '2026-01-01'</small>"]
    AGG["aggClause<br/><small>GROUP BY c.region</small>"]
    HAV["havingClause<br/><small>(无)</small>"]
    ORG["queryOrganization<br/><small>sortClause + limitClause</small>"]
  end
  ROOT --> SEL
  ROOT --> FROM
  ROOT --> WHERE
  ROOT --> AGG
  ROOT --> HAV
  ROOT --> ORG
  classDef parser stroke:#5b7db1,color:#1b4a8a;
  classDef stmt stroke:#5b7db1,color:#1b4a8a;
  classDef clause stroke:#2f9e6e,color:#146c4b;
  class PARSER parser; class ROOT stmt; class SEL,FROM,WHERE,AGG,HAV,ORG clause;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图③④ · 构建 Unbound + 分析绑定(Unbound → Bound)", r'''flowchart TB
  PARSE["解析树 ParseTree"]
  BUILD["LogicalPlanBuilder(访问器)"]
  PARSE --> BUILD
  UNBOUND["Unbound LogicalPlan(算子树,引用未解析)<br/><small>LogicalProject ▸ LogicalAggregate ▸ LogicalFilter ▸ LogicalJoin ▸ UnboundRelation×2</small>"]
  BUILD --> UNBOUND
  CAT[("Catalog<br/><small>库·表·列·函数·统计</small>")]
  ANALYZE["Analyze / Bind(规则驱动)<br/><small>BindRelation · BindExpression · BindSink · CheckAnalysis</small>"]
  UNBOUND --> ANALYZE
  CAT --> ANALYZE
  BOUND["Bound / Analyzed LogicalPlan<br/><small>(列→Slot、类型确定、函数解析、权限校验)</small>"]
  ANALYZE --> BOUND
  classDef in   stroke:#5b7db1,color:#1b4a8a;
  classDef cat  stroke:#d0873a,color:#8a5410;
  classDef proc stroke:#2f9e6e,color:#146c4b;
  classDef out  stroke:#8a5bb1,color:#5b2f8a;
  class PARSE,UNBOUND in; class CAT cat; class BUILD,ANALYZE proc; class BOUND out;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⑤⑥ · RBO 改写 + CBO 代价优化(Rewritten → Physical)", r'''flowchart TB
  BOUND["Bound LogicalPlan"]
  RBO["⑤ Rewrite / RBO(规则 · 等价变换)<br/><small>谓词下推 · 列裁剪(ColumnPruning) · 常量折叠<br/>子查询解嵌套 · 外连接消除 · Limit/TopN 下推<br/>分区/分桶裁剪(PruneOlapScanPartition/Tablet) · 聚合下推</small>"]
  REWRITTEN["Rewritten LogicalPlan"]
  CBO["⑥ Optimize / CBO(Cascades · Memo)<br/><small>Memo:Group / GroupExpression 等价类<br/>DeriveStatsJob 估基数 · CostAndEnforcerJob 择优<br/>Join Reorder · 分布方式 DistributionSpec(Hash/Gather/Shuffle)<br/>物化视图透明改写(exploration/mv)</small>"]
  PHYS["PhysicalPlan<br/><small>PhysicalHashJoin / PhysicalOlapScan … FE 内存对象</small>"]
  STATS[("统计信息<br/><small>行数·NDV·Min/Max·直方图</small>")]
  BOUND --> RBO --> REWRITTEN --> CBO --> PHYS
  STATS --> CBO
  classDef in   stroke:#5b7db1,color:#1b4a8a;
  classDef rbo  stroke:#2f9e6e,color:#146c4b;
  classDef cbo  stroke:#5b7db1,color:#1b4a8a;
  classDef stat stroke:#d0873a,color:#8a5410;
  classDef out  stroke:#8a5bb1,color:#5b2f8a;
  class BOUND,REWRITTEN in; class RBO rbo; class CBO cbo; class STATS stat; class PHYS out;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⑦ · 翻译层:PhysicalPlan → PlanFragment", r'''flowchart TB
  PHYS["PhysicalPlan(FE 内存对象)"]
  TRANS["PhysicalPlanTranslator<br/><small>+ ExpressionTranslator(表达式→Thrift)<br/>+ RuntimeFilterTranslator(规划 RF,含 V2)</small>"]
  FRAG["PlanFragment 树(可序列化下发 BE)<br/><small>含 TPlanNode · DataSink · DataPartition(分布方式)<br/>F2:ScanCustomers │ F1:ScanOrders+Join+局部聚合 │ F0:全局聚合+TopN+ResultSink</small>"]
  PHYS --> TRANS --> FRAG
  classDef in  stroke:#8a5bb1,color:#5b2f8a;
  classDef mid stroke:#2f9e6e,color:#146c4b;
  classDef out stroke:#5b7db1,color:#1b4a8a;
  class PHYS in; class TRANS mid; class FRAG out;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⑧⑨ · 分布式规划 + 调度下发", r'''flowchart TB
  CLIENT(["客户端 / BI"])
  subgraph FE["FE(任一节点担任 Coordinator)"]
    direction LR
    DIST["DistributePlanner<br/><small>→ DistributedPlan / PipelineDistributedPlan<br/>选 worker · Bucket/Default 定实例</small>"]
    COORD["Coordinator<br/><small>Scan Range 分配 · MVCC 版本选定<br/>资源组绑定 · BRPC 下发 TPipelineFragmentParams · 汇聚</small>"]
    DIST --> COORD
  end
  subgraph BES["BE 集群(share-nothing · Pipeline 引擎)"]
    direction LR
    BE1["BE-1<br/><small>Fragment 实例 · 本地 Tablet</small>"]
    BE2["BE-2 …×N<br/><small>Fragment 实例 · 本地 Tablet</small>"]
  end
  CLIENT -->|SQL| DIST
  COORD -->|BRPC 下发| BE1
  COORD -->|BRPC 下发| BE2
  BE1 ==>|Exchange| BE2
  BE1 -->|Gather| COORD
  BE2 -->|Gather| COORD
  COORD -->|结果集| CLIENT
  classDef fe stroke:#5b7db1,color:#1b4a8a;
  classDef be stroke:#2f9e6e,color:#146c4b;
  classDef cli stroke:#c25b5b,color:#a03434;
  class DIST,COORD fe; class BE1,BE2 be; class CLIENT cli;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⑩ · Pipeline 执行 + Runtime Filter", r'''flowchart TB
  subgraph FRAG1["Fragment-1(BE 内 · 按 ★Breaker 拆 Pipeline)"]
    direction TB
    P1["Pipe1 · Build 侧<br/><small>ExchangeSrc(customers) ▸ HashJoin BuildSink ★<br/>(生成 Runtime Filter:IN/Bloom/MinMax)</small>"]
    P2["Pipe2 · Scan+Probe+局部聚合<br/><small>ScanSrc(orders)×Tablet ▸ LocalExchange ▸ HJ Probe×DOP ▸ Agg(Partial)Sink ★</small>"]
    P3["Pipe3 · 发送<br/><small>Agg(Partial)Src ▸ ExchangeSink(Shuffle by region)</small>"]
    P1 -. "★Breaker:Build 完成 → Probe" .-> P2
    P1 -. "Runtime Filter 下推过滤大表" .-> P2
    P2 -. "Sink/Source 配对" .-> P3
  end
  subgraph FRAG0["Fragment-0(Coordinator BE)"]
    direction TB
    P4["Pipe4 · 全局聚合<br/><small>ExchangeSrc ▸ LocalExchange ▸ Agg(Final)Sink ★</small>"]
    P5["Pipe5 · TopN<br/><small>Agg(Final)Src ▸ TopN Sink ★</small>"]
    P6["Pipe6 · 返回<br/><small>TopN Src ▸ ResultSink</small>"]
    P4 -. 配对 .-> P5
    P5 -. "排序完成→输出" .-> P6
  end
  P3 ==>|Exchange 网络 Shuffle · 唯一跨节点| P4
  classDef pipe stroke:#5b7db1,color:#1b4a8a;
  classDef send stroke:#8a5bb1,color:#5b2f8a;
  classDef res  stroke:#c25b5b,color:#a03434;
  class P1,P2,P4,P5 pipe; class P3 send; class P6 res;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⑪ · 结果汇聚与返回", r'''flowchart TB
  BE["顶层 Fragment 输出(ResultSink)"]
  GATHER["Coordinator 汇聚各实例结果"]
  MERGE["最终 merge<br/><small>全局 sort / limit / 去重</small>"]
  FILL["回填 SQL / Partition Cache"]
  PROTO["MySQL 协议编码 + 汇总 Query Profile"]
  CLIENT(["返回客户端 / BI"])
  BE --> GATHER --> MERGE --> FILL --> PROTO --> CLIENT
  classDef be stroke:#2f9e6e,color:#146c4b;
  classDef mid stroke:#5b7db1,color:#1b4a8a;
  classDef cli stroke:#c25b5b,color:#a03434;
  class BE be; class GATHER,MERGE,FILL,PROTO mid; class CLIENT cli;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),

 ("图⊕ · 横切关注点:可观测性与资源治理", r'''flowchart TB
  Q["贯穿全链路的工程维度<br/><small>不属于某一环节</small>"]
  subgraph OBS["可观测性"]
    direction TB
    E1["EXPLAIN / EXPLAIN VERBOSE<br/><small>看计划与分布方式</small>"]
    E2["Query Profile<br/><small>每个 Operator 耗时/行数/内存/等待 · 定位慢查询第一工具</small>"]
    E3["审计日志<br/><small>SQL 与资源消耗</small>"]
  end
  subgraph GOV["资源治理"]
    direction TB
    G1["Workload Group<br/><small>CPU/内存软硬限 · 多租户隔离</small>"]
    G2["SQL Block Rule<br/><small>拦截扫描分区过多/返回行过大等坏 SQL</small>"]
    G3["查询级内存限制 + Spill 落盘<br/><small>防 OOM</small>"]
  end
  subgraph CON["一致性"]
    direction TB
    C1["MVCC 版本<br/><small>Coordinator 为整条查询选定可见 rowset 版本 · 快照一致 · 不读并发导入中间态</small>"]
  end
  Q --> OBS
  Q --> GOV
  Q --> CON
  classDef q stroke:#8a5bb1,color:#5b2f8a;
  classDef obs stroke:#5b7db1,color:#1b4a8a;
  classDef gov stroke:#d0873a,color:#8a5410;
  classDef con stroke:#2f9e6e,color:#146c4b;
  class Q q; class E1,E2,E3 obs; class G1,G2,G3 gov; class C1 con;
  linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]
_qlife_shortmap = ["总览 · 状态演进", "接入层与缓存", "① 词法分析", "② 语法分析", "③④ 构建+绑定", "⑤⑥ RBO+CBO", "⑦ 翻译层", "⑧⑨ 分布式规划+下发", "⑩ Pipeline 执行", "⑪ 汇聚返回", "⊕ 横切关注点"]

# ───────────────────────────────────────────────────────────────────
# 原理概览:12 篇权威原理文档的 mermaid 图集(每主题一个多图视图)
# 节点标签英文 ASCII 原样保留;classDef 转暗色(去 fill,留 stroke+color);末尾补 linkStyle。
# stateDiagram-v2 / sequenceDiagram 原生适配暗色主题,无需改。
# ───────────────────────────────────────────────────────────────────

# DCL 数据控制(接口主线)—— 填充原空占位
DCL_PRIN_MMS = [
 ("生命周期总览:定义线 × 执行线", r'''flowchart LR
    subgraph DEF["Definition (low frequency)"]
        direction TB
        G["GRANT / REVOKE / CREATE USER·ROLE·Workload Group"] --> LOG["write EditLog"] --> REP["replicate to all FE"] --> EFF["policy consistent everywhere"]
    end
    subgraph RUN["Per-request enforcement"]
        direction TB
        CONN["Connect: Authentication"] --> AUTHZ["Authorization"] --> RES["Workload Group + limits"] --> EXEC["execute under limits"] --> AUDIT["Audit"]
    end
    DEF -. supplies policy .-> RUN
    classDef def stroke:#5b7db1,color:#1b4a8a;
    classDef run stroke:#3aa06b,color:#12402a;
    class G,LOG,REP,EFF def;
    class CONN,AUTHZ,RES,EXEC,AUDIT run;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
 ("权限模型 · RBAC(User → Role → Privilege → Scope)", r'''flowchart TB
    U["User (+ Authentication)"]
    R["Role (privilege set)"]
    P["Privilege<br/>SELECT / LOAD / ALTER / ADMIN…"]
    S["Scope<br/>Global · Catalog · DB · Table · Column · Resource"]
    U -->|granted| R
    U -->|granted directly| P
    R -->|contains| P
    P -->|scoped to| S
    classDef u stroke:#c25b5b,color:#a03434;
    classDef r stroke:#5b7db1,color:#1b4a8a;
    classDef p stroke:#3aa06b,color:#12402a;
    classDef s stroke:#d0873a,color:#8a5410;
    class U u;
    class R r;
    class P p;
    class S s;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
 ("请求管控时序:Connect → AuthN → AuthZ → Workload Group → Audit", r'''sequenceDiagram
    autonumber
    participant C as Client
    participant FE as FE
    participant AZ as Authorization
    participant RG as Workload Group
    C->>FE: Connect (identity + credential)
    FE->>FE: Authentication
    Note over FE: fail -> reject connection
    C->>FE: submit SQL
    FE->>FE: SQL Block Rule check
    FE->>AZ: authorize by op + scope
    Note over AZ: no privilege -> reject
    AZ->>RG: assign Workload Group + limits
    RG-->>FE: execute under limits
    FE-->>C: result + Audit'''),
 ("资源隔离与限流:Workload Group 管控 CPU/Memory/Concurrency", r'''flowchart TB
    Q["Query / Load"]
    WG["Workload Group"]
    CPU["CPU soft / hard limit"]
    MEM["Memory quota (+ Spill)"]
    CC["Concurrency / Queue / Timeout"]
    Q --> WG
    WG --> CPU
    WG --> MEM
    WG --> CC
    classDef q stroke:#c25b5b,color:#a03434;
    classDef wg stroke:#5b7db1,color:#1b4a8a;
    classDef lim stroke:#3aa06b,color:#12402a;
    class Q q;
    class WG wg;
    class CPU,MEM,CC lim;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]
_dcl_shortmap = ["生命周期总览", "RBAC 权限模型", "请求管控时序", "资源隔离限流"]




# ── 支撑主线 8 篇原理概览 ──

# 优化技术 → opttech 主题(新顶层平铺 tab)
OPT_PRIN_MMS = [
 ("优化的四个位置:Planning/Execution/Storage/Cache", r'''flowchart TB
    subgraph PLAN["Planning (reduce what to do)"]
        direction LR
        R1["RBO Rewrite"]
        R2["CBO Optimize"]
        R3["Materialized View rewrite"]
    end
    subgraph EXEC["Execution (reduce actual work)"]
        direction LR
        E1["Runtime Filter"]
        E2["Vectorization / Parallelism"]
        E3["Partial Agg / TopN"]
    end
    subgraph STORE["Storage (skip / less read)"]
        direction LR
        S1["Partition / Tablet prune"]
        S2["Index skip"]
        S3["Column prune / Late Materialization"]
    end
    subgraph CACHE["Cache (avoid recompute)"]
        direction LR
        C1["SQL / Result Cache"]
        C2["Plan Cache"]
        C3["Data / Meta Cache"]
    end
    PLAN --> EXEC --> STORE
    CACHE -. short-circuit .-> PLAN
    classDef p stroke:#5b7db1,color:#1b4a8a;
    classDef e stroke:#3aa06b,color:#12402a;
    classDef s stroke:#d0873a,color:#8a5410;
    classDef c stroke:#c25b5b,color:#a03434;
    class R1,R2,R3 p;
    class E1,E2,E3 e;
    class S1,S2,S3 s;
    class C1,C2,C3 c;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]
_opt_prin_shortmap = ["优化的四个位置"]





# 集群自愈 → tabletsched 主题
TS_PRIN_MMS = [
 ("自愈环:Detect → Decide → Act", r'''flowchart LR
    DETECT["Detect<br/>replica count / health / balance"]
    DECIDE["Decide<br/>missing? corrupt? skewed?"]
    ACT["Act<br/>add / clone-repair / migrate-balance"]
    DETECT --> DECIDE --> ACT --> DETECT
    classDef s stroke:#5b7db1,color:#1b4a8a;
    class DETECT,DECIDE,ACT s;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]
_ts_prin_shortmap = ["自愈环"]

# 后台任务 → compaction 主题
CP_PRIN_MMS = [
 ("异步维护:摊平成本、错峰服务", r'''flowchart LR
    subgraph BG["Background Daemons (async)"]
        direction TB
        T1["Compaction (Cumulative / Base)"]
        T2["Replica Repair / Balance (Clone)"]
        T3["Materialized View Refresh"]
        T4["Statistics Collection"]
        T5["Checkpoint → Image"]
        T6["GC / Cleanup (expired versions/files)"]
    end
    T1 -. serves .-> Q["faster query"]
    T3 -. serves .-> Q
    T4 -. serves .-> Q
    T2 -. serves .-> A["more available / balanced"]
    T5 -. serves .-> A
    T6 -. serves .-> A
    classDef bg stroke:#5b7db1,color:#1b4a8a;
    classDef tgt stroke:#3aa06b,color:#12402a;
    class T1,T2,T3,T4,T5,T6 bg;
    class Q,A tgt;
    linkStyle default stroke:#94a0b3,stroke-width:1.8px;'''),
]
_cp_prin_shortmap = ["异步维护平衡"]

_dataorg_shortmap = ["总体层级", "FE↔BE 对应", "版本链 & Compaction", "Segment 内部"]
_idxarch_shortmap = ["存储层位置", "查询协同流程", "能力分层"]

# 部署形态概览:4 种部署形态合成一个多图视图(垂直 TAB 切换),末尾单独 archcompare 对比表
DEPLOY_MMS = [
 ("湖仓查询部署", LAKEHOUSE_MM),
 ("存算一体部署", ARCHINTEG_INTG_MM),
 ("存算分离部署", ARCHDECOUPLED_MM),
 ("冷热分离部署", ARCHTIERING_MM),
]
_deploy_shortmap = ["湖仓查询部署", "存算一体部署", "存算分离部署", "冷热分离部署"]

# === EXPLAIN 诊断:一条 SQL 随 planType 阶段推进的计划变化(垂直 TAB) ===
_EXPLAIN_SQL = ("SELECT o.region, sum(o.amount)\n"
                "FROM orders o JOIN users u ON o.uid = u.uid\n"
                "WHERE u.age &gt; 30 AND o.dt = '2026-01-01'\n"
                "GROUP BY o.region\n"
                "ORDER BY 2 DESC\n"
                "LIMIT 10;")
_explain_shortmap = ["PARSED", "ANALYZED", "REWRITTEN(RBO)", "OPTIMIZED(CBO)", "DISTRIBUTED"]
EXPLAIN_MMS = [
 ("EXPLAIN PARSED PLAN · 未绑定 AST 逻辑计划", r'''flowchart TB
  p_sql["SQL 文本"] --> p_parse["Parser · antlr4 语法树"]
  p_parse --> p_plan["未绑定 LogicalPlan<br/><small>列/表仅按名字占位,未解析元数据</small>"]
  p_plan --> p_limit["LogicalLimit 10"]
  p_limit --> p_sort["LogicalSort · ORDER BY 2 DESC"]
  p_sort --> p_agg["LogicalAggregate · GROUP BY region · sum(amount)"]
  p_agg --> p_filter["LogicalFilter · u.age&gt;30 AND o.dt='2026-01-01'"]
  p_filter --> p_join["LogicalJoin · o.uid=u.uid(类型未定)"]
  p_join --> p_o["UnboundRelation orders"]
  p_join --> p_u["UnboundRelation users"]
  classDef s stroke:#4a90d9,color:#1a3a5c,stroke-width:1.4px;
  classDef n stroke:#8b5cd6,color:#3a1a5c,stroke-width:1.4px;
  class p_sql,p_parse s; class p_plan,p_limit,p_sort,p_agg,p_filter,p_join,p_o,p_u n;
  linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''),
 ("EXPLAIN ANALYZED PLAN · 绑定元数据后的逻辑计划", r'''flowchart TB
  a_note["绑定:列/类型/权限解析,UnboundRelation→LogicalOlapScan"] --> a_limit
  a_limit["LogicalLimit 10"] --> a_sort["LogicalSort · $2 DESC"]
  a_sort --> a_agg["LogicalAggregate · region:VARCHAR · sum(amount:DECIMAL)"]
  a_agg --> a_filter["LogicalFilter · u.age:INT&gt;30 AND o.dt:DATE='2026-01-01'"]
  a_filter --> a_join["LogicalJoin INNER · o.uid=u.uid(BIGINT=BIGINT)"]
  a_join --> a_o["LogicalOlapScan orders · 已绑定 schema"]
  a_join --> a_u["LogicalOlapScan users · 已绑定 schema"]
  classDef s stroke:#3c9d5c,color:#1a4a2c,stroke-width:1.4px;
  classDef n stroke:#8b5cd6,color:#3a1a5c,stroke-width:1.4px;
  class a_note s; class a_limit,a_sort,a_agg,a_filter,a_join,a_o,a_u n;
  linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''),
 ("EXPLAIN REWRITTEN PLAN · RBO 规则改写后", r'''flowchart TB
  r_note["RBO:谓词下推到 Scan · 列裁剪 · Filter 拆分下沉"] --> r_limit
  r_limit["LogicalLimit 10"] --> r_sort["LogicalSort · $2 DESC"]
  r_sort --> r_agg["LogicalAggregate · GROUP BY region · sum(amount)"]
  r_agg --> r_join["LogicalJoin INNER · o.uid=u.uid"]
  r_join --> r_o["LogicalOlapScan orders<br/><small>↓下推 dt='2026-01-01' · 只取 uid,amount,region,dt</small>"]
  r_join --> r_u["LogicalOlapScan users<br/><small>↓下推 age&gt;30 · 只取 uid,age</small>"]
  classDef s stroke:#d0913a,color:#5c3d0f,stroke-width:1.4px;
  classDef n stroke:#8b5cd6,color:#3a1a5c,stroke-width:1.4px;
  class r_note s; class r_limit,r_sort,r_agg,r_join,r_o,r_u n;
  linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''),
 ("EXPLAIN OPTIMIZED PLAN · CBO 定型物理计划", r'''flowchart TB
  o_note["CBO:Join Reorder + 分布策略 + 两阶段聚合(Cascades/Memo 择优)"] --> o_topn
  o_topn["PhysicalTopN 10 · $2 DESC<br/><small>Sort+Limit 合并为 TopN</small>"] --> o_aggG["PhysicalHashAggregate(GLOBAL) · sum merge"]
  o_aggG --> o_shuf["PhysicalDistribute · SHUFFLE by region"]
  o_shuf --> o_aggL["PhysicalHashAggregate(LOCAL) · 预聚合"]
  o_aggL --> o_join["PhysicalHashJoin INNER · o.uid=u.uid<br/><small>users 为 build 侧(较小)</small>"]
  o_join --> o_o["PhysicalOlapScan orders · dt 分区裁剪 + 谓词下推"]
  o_join --> o_ub["PhysicalDistribute · BROADCAST users"] --> o_u["PhysicalOlapScan users · age&gt;30"]
  classDef s stroke:#d0913a,color:#5c3d0f,stroke-width:1.4px;
  classDef n stroke:#5b8cff,color:#1a3a5c,stroke-width:1.4px;
  class o_note s; class o_topn,o_aggG,o_shuf,o_aggL,o_join,o_o,o_ub,o_u n;
  linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''),
 ("EXPLAIN DISTRIBUTED PLAN · 分片 + Exchange", r'''flowchart TB
  d_note["切 PlanFragment + Exchange 边界,下发多 BE 并行"] --> F0
  subgraph F0["Fragment 0 · 汇聚(1 实例)"]
    f0_res["ResultSink → FE ResultReceiver"] --> f0_topn["TopN 10(final)"] --> f0_aggG["HashAgg GLOBAL"] --> f0_ex["ExchangeNode ← SHUFFLE"]
  end
  subgraph F1["Fragment 1 · Join+预聚合(N 实例)"]
    f1_aggL["HashAgg LOCAL"] --> f1_join["HashJoin INNER"] --> f1_scanO["OlapScan orders(分区裁剪)"]
    f1_join --> f1_bex["ExchangeNode ← BROADCAST"]
  end
  subgraph F2["Fragment 2 · 广播 users(N 实例)"]
    f2_scanU["OlapScan users(age&gt;30)"]
  end
  f0_ex -. SHUFFLE by region .-> f1_aggL
  f1_bex -. BROADCAST .-> f2_scanU
  classDef s stroke:#8b5cd6,color:#3a1a5c,stroke-width:1.4px;
  classDef n stroke:#5b8cff,color:#1a3a5c,stroke-width:1.4px;
  class d_note s; class f0_res,f0_topn,f0_aggG,f0_ex,f1_aggL,f1_join,f1_scanO,f1_bex,f2_scanU n;
  linkStyle default stroke:#aab4c2,stroke-width:1.6px;'''),
]

def _build_multi_blocks(mms, shortmap):
    navs = "".join(
        '<button class="do-nav{act}" data-idx="{i}"><span class="do-nav-n">{n}</span>'
        '<span class="do-nav-t">{s}</span></button>'.format(
            act=(" active" if i == 0 else ""), i=i, n=i + 1,
            s=shortmap[i] if i < len(shortmap) else t)
        for i, (t, code) in enumerate(mms))
    secs = "".join(
        '<div class="do-sec{act}" data-idx="{i}"><h3 class="do-h">{t}</h3>'
        '<script type="text/plain" class="do-mm" data-idx="{i}">{code}</script>'
        '<div class="do-out" id="do-out-{i}"></div></div>'.format(
            act=(" active" if i == 0 else ""), t=t, i=i, code=code)
        for i, (t, code) in enumerate(mms))
    return ('<div class="do-nav-col"><div class="do-nav-sticky">{navs}</div></div>'
            '<div class="do-stage">{secs}</div>').format(navs=navs, secs=secs)

_MULTI_DIAGRAM_PANES = {
    "dataorg": _build_multi_blocks(DATAORG_MMS, _dataorg_shortmap),
    "idxarch": _build_multi_blocks(IDXARCH_MMS, _idxarch_shortmap),
    "vecsearch": _build_multi_blocks(VECSEARCH_MMS, ["倒排 · 全文检索", "向量 · ANN 检索"]),
    "qlife": _build_multi_blocks(QLIFE_MMS, _qlife_shortmap),
    "dclprin": _build_multi_blocks(DCL_PRIN_MMS, _dcl_shortmap),
    "deployview": _build_multi_blocks(DEPLOY_MMS, _deploy_shortmap),
    "optprin": _build_multi_blocks(OPT_PRIN_MMS, _opt_prin_shortmap),
    "tsprin": _build_multi_blocks(TS_PRIN_MMS, _ts_prin_shortmap),
    "cpprin": _build_multi_blocks(CP_PRIN_MMS, _cp_prin_shortmap),
}
# 贯穿示例 SQL(查询生命周期主线,顶部悬挂)
_QLIFE_SQL = ("SELECT c.region, SUM(o.amount) AS gmv\n"
              "FROM orders o JOIN customers c ON o.cust_id = c.id\n"
              "WHERE o.dt &gt;= '2026-01-01'\n"
              "GROUP BY c.region\n"
              "ORDER BY gmv DESC\n"
              "LIMIT 10;")
# 顶部示例 SQL 条(仅部分多图视图需要);pane 发射时置于 dataorg-wrap 之前
import re as _re_sql
_SQL_KW = {"SELECT","FROM","WHERE","GROUP","BY","ORDER","HAVING","LIMIT","OFFSET","JOIN","LEFT",
  "RIGHT","INNER","OUTER","FULL","CROSS","ON","AS","AND","OR","NOT","IN","IS","NULL","LIKE",
  "BETWEEN","CASE","WHEN","THEN","ELSE","END","DISTINCT","UNION","ALL","INSERT","INTO","VALUES",
  "UPDATE","SET","DELETE","CREATE","TABLE","VIEW","MATERIALIZED","WITH","DESC","ASC","USING","EXISTS","OVER","PARTITION"}
_SQL_FN = {"SUM","COUNT","AVG","MIN","MAX","CAST","COALESCE","CONCAT","SUBSTR","SUBSTRING",
  "DATE_FORMAT","NOW","ABS","ROUND","FLOOR","CEIL","IF","IFNULL","NULLIF","ROW_NUMBER","RANK",
  "DENSE_RANK","LAG","LEAD","NDV","HLL_UNION","BITMAP_UNION","ARRAY_AGG"}
def _sql_highlight(sql):
    # sql 可能已含 &gt;/&lt;/&amp; 实体(调用方已转义 >/< );保留实体、只给词元着色。
    # 颜色:关键字紫、函数蓝、字符串绿、数字橙、其余默认(继承 --c-ink)。
    def esc(t):  # 转义尚未成实体的裸 & < > "
        return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    out = []
    # 先按 已有实体 / 字符串字面量 / 其它 切分,避免破坏 &gt; 等
    # token 规则:'...' 字符串 | 标识符/关键字 | 数字 | 实体 &xxx; | 其它单字符
    pat = _re_sql.compile(r"'[^']*'|&[a-z]+;|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|\s+|.")
    for m in pat.finditer(sql):
        tok = m.group(0)
        if tok.startswith("'") and tok.endswith("'") and len(tok) >= 2:
            out.append('<span style="color:#3aa06b">' + esc(tok) + '</span>')  # 字符串
        elif tok.startswith("&") and tok.endswith(";"):
            out.append(tok)  # 已是实体,原样
        elif tok.strip() == "":
            out.append(tok)  # 空白
        elif tok[0].isdigit():
            out.append('<span style="color:#d08b3a">' + tok + '</span>')  # 数字
        elif _re_sql.match(r"[A-Za-z_]", tok):
            up = tok.upper()
            if up in _SQL_KW:
                out.append('<span style="color:#a679e0;font-weight:600">' + tok + '</span>')  # 关键字
            elif up in _SQL_FN:
                out.append('<span style="color:#5db0f0">' + tok + '</span>')  # 函数
            else:
                out.append(esc(tok))
        else:
            out.append(esc(tok))
    return "".join(out)
_MULTI_SQLBAR = {
    "explaincmd": ('<div class="do-sqlbar"><span class="do-sqlbar-tag">示例 SQL</span>'
                   '<code class="do-sqlbar-code">' + _sql_highlight(_EXPLAIN_SQL) + '</code></div>'),
    "qlife": ('<div class="do-sqlbar"><span class="do-sqlbar-tag">贯穿示例 SQL</span>'
              '<code class="do-sqlbar-code">' + _sql_highlight(_QLIFE_SQL) + '</code></div>'),
}

tab_panes = "\n".join(
    ('<section class="pane" id="pane-{tid}" data-sub="{sub}">'
     '<div class="mmout" id="mm-{tid}"></div></section>'.format(
        tid=tid, sub=TAB_META[tid][1])
     if tid == "qstour" else
     '<section class="pane" id="pane-{tid}" data-sub="{sub}">'
     '<div class="do-paneflow"><div class="dataorg-wrap svg-walk-wrap" data-multi="{tid}">{blocks}</div></div>'
     '<div class="mmout" id="mm-{tid}"></div></section>'.format(
        tid=tid, sub=TAB_META[tid][1], blocks=_SVG_WALK_PANES[tid])
     if tid in _SVG_WALK_PANES else
     '<section class="pane" id="pane-{tid}" data-sub="{sub}">'
     '<div class="do-paneflow">{sqlbar}<div class="dataorg-wrap" data-multi="{tid}">{blocks}</div></div>'
     '<div class="mmout" id="mm-{tid}"></div></section>'.format(
        tid=tid, sub=TAB_META[tid][1], blocks=_MULTI_DIAGRAM_PANES[tid],
        sqlbar=_MULTI_SQLBAR.get(tid, ""))
     if tid in _MULTI_DIAGRAM_PANES else
     '<section class="pane" id="pane-{tid}" data-sub="{sub}">'
     '<script type="text/plain" class="mmsrc" data-target="mm-{tid}">{code}</script>'
     '<div class="mmout" id="mm-{tid}"></div></section>'.format(
        tid=tid, sub=TAB_META[tid][1],
        code=(ARCHINTEG_MM if tid == "archintegrated"
              else OPTARCH_MM if tid == "optarch"
              else code)))
    # 只为"可达"(有顶层按钮 = 主题内)的 tid 发 pane;嵌套/多图子视图 tid 由 renderInto/NEST_MM 从 spec 现渲,
    # 其独立 pane 是冗余(约 71 个 / ~46KB)。见 memory「P2 孤儿 pane」。
    for i, (tid, title, code) in enumerate(TABS) if tid in THEMED_TIDS)

# HTML shell + world-class dark design system. Plain string with __TOKENS__
# (no f-string/.format) so CSS/JS braces need no escaping.
HTML_SHELL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Kafka 引擎 · 交互式核心原理图谱</title>
<style>
:root{
  --bg:#08090c; --bg2:#0d0f14; --panel:#14171e; --panel2:#0e1116;
  --line:#20242e; --line2:#2b313d;
  --ink:#eceef2; --ink2:#a6adbb; --ink3:#6b7280;
  --brand:#5b8cff; --brand2:#8b6cff; --accent:#38bdf8;
  --ok:#2dd4a7; --warn:#fbbf24; --hot:#f43f7e;
  --fe:#4f9dff; --be:#2dd4a7; --store:#f472b6; --write:#f59e0b;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  --r:14px; --shadow:0 12px 44px -14px rgba(0,0,0,.75);
  /* ── chrome 语义令牌:DEFAULT = 深色(Xcode/Logic 石墨风) ── */
  --c-bg:#1c1c1e; --c-bg2:#161618; --c-panel:#242426; --c-panel2:#2c2c2e;
  --c-line:rgba(255,255,255,.11); --c-line2:rgba(255,255,255,.17);
  --c-ink:#f5f5f7; --c-ink2:#c4c4c9; --c-ink3:#8e8e93;
  --c-brand:#0a84ff; --c-brand-ink:#409cff;
  --c-hover:rgba(255,255,255,.07);
  --c-glass:rgba(28,28,30,.82); --c-glass-tint:color-mix(in srgb,var(--c-brand) 22%,transparent);
  --c-shadow-sm:0 1px 2px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.28);
  --c-shadow-md:0 4px 16px rgba(0,0,0,.4),0 12px 28px rgba(0,0,0,.35);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.5),0 24px 48px rgba(0,0,0,.45);
  /* 画布语义令牌:DEFAULT = 深色(跟随主题) */
  --cv-bg:#161618; --cv-dot:rgba(255,255,255,.045);
  --cv-card:#202024; --cv-card-alt:#26262b;
  --cv-border:#34343a; --cv-border-ghost:#2a2a2f;
  --cv-ink:#e8e8ea; --cv-ink2:#9a9aa2;
  --cv-edge:#5a5a64; --cv-edge-strong:#7a8494;
  --cv-vec:#a78bfa; --cv-merge:#4ade80; --cv-scan:#38bdf8; --cv-warn:#fbbf24; --cv-danger:#f472b6;
}
/* ── LIGHT chrome:Apple Store 风(白/浅灰 + SF Pro + 柔投影) ── */
:root[data-theme="light"]{
  --c-bg:#f5f5f7; --c-bg2:#fbfbfd; --c-panel:#ffffff; --c-panel2:#f0f0f3;
  --c-line:rgba(0,0,0,.09); --c-line2:rgba(0,0,0,.14);
  --c-ink:#1d1d1f; --c-ink2:#424245; --c-ink3:#86868b;
  --c-brand:#0071e3; --c-brand-ink:#0066cc;
  --c-hover:rgba(0,0,0,.04);
  --c-glass:rgba(255,255,255,.9); --c-glass-tint:color-mix(in srgb,var(--c-brand) 12%,#fff);
  --c-shadow-sm:0 1px 2px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.05);
  --c-shadow-md:0 4px 16px rgba(0,0,0,.08),0 12px 28px rgba(0,0,0,.07);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.10),0 24px 48px rgba(0,0,0,.10);
  /* 画布语义令牌:浅色覆盖 */
  --cv-bg:#f5f5f7; --cv-dot:rgba(0,0,0,.05);
  --cv-card:#ffffff; --cv-card-alt:#f5f6f8;
  --cv-border:#e3e7ee; --cv-border-ghost:#eceef2;
  --cv-ink:#1d1d1f; --cv-ink2:#86868b;
  --cv-edge:#c9cfda; --cv-edge-strong:#8a93a5;
  --cv-vec:#7c5fe6; --cv-merge:#2f8f5e; --cv-scan:#0a94d6; --cv-warn:#b8801f; --cv-danger:#c0417a;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--c-bg);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;overflow:hidden}
body{background:var(--c-bg)}
#app{display:flex;flex-direction:column;height:100vh;background:var(--c-bg)}

/* ---- 加载进度覆盖层（首帧内联图解码期,避免空白被误读为内容错误） ---- */
#loadingOverlay{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;
  background:var(--c-bg);transition:opacity .45s ease,visibility .45s ease}
#loadingOverlay.lo-hidden{opacity:0;visibility:hidden;pointer-events:none}
.lo-inner{display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 32px;max-width:520px}
.lo-logo{width:56px;height:56px;border-radius:15px;
  background:linear-gradient(135deg,var(--c-brand),#8b6cff);
  box-shadow:0 8px 28px color-mix(in srgb,var(--c-brand) 40%,transparent);
  animation:loPulse 1.5s ease-in-out infinite}
@keyframes loPulse{0%,100%{transform:scale(1);opacity:.92}50%{transform:scale(1.08);opacity:1}}
.lo-title{margin-top:22px;font-size:22px;font-weight:700;letter-spacing:-.01em;color:var(--c-ink)}
.lo-sub{margin-top:8px;font-size:13px;color:var(--c-ink2)}
.lo-bar{margin-top:24px;width:260px;height:4px;border-radius:4px;overflow:hidden;
  background:color-mix(in srgb,var(--c-ink3) 26%,transparent);position:relative}
.lo-bar-fill{position:absolute;left:0;top:0;height:100%;width:40%;border-radius:4px;
  background:linear-gradient(90deg,transparent,var(--c-brand),transparent);
  animation:loSlide 1.15s ease-in-out infinite}
@keyframes loSlide{0%{left:-40%}100%{left:100%}}
.lo-hint{margin-top:18px;font-size:11px;line-height:1.5;color:var(--c-ink3)}
@media (prefers-reduced-motion:reduce){.lo-logo,.lo-bar-fill{animation:none}}

/* ---- Top bar (Apple 浅色毛玻璃) ---- */
header{padding:16px 30px 14px;border-bottom:1px solid var(--c-line);display:flex;align-items:center;justify-content:space-between;
  background:color-mix(in srgb, var(--c-bg2) 82%, transparent);backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px)}
.theme-toggle{width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);
  color:var(--c-ink2);cursor:pointer;display:grid;place-items:center;font-size:16px;transition:all .2s ease;flex-shrink:0}.msearch{position:relative;display:flex;align-items:center;gap:8px;width:min(300px,34vw);padding:0 12px;height:38px;border-radius:19px;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);margin-left:auto;margin-right:12px}.msearch svg{flex:none;opacity:.7}.msearch input{flex:1;border:0;background:transparent;color:var(--c-ink);outline:0;font-size:13px}.msearch kbd{flex:none;font:600 11px var(--mono,monospace);color:var(--c-ink3);border:1px solid var(--c-line);border-radius:5px;padding:1px 6px}.mq-list{position:absolute;top:44px;left:0;right:0;z-index:60;background:var(--c-panel);border:1px solid var(--c-line);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.28);overflow:hidden;display:none}.mq-list.on{display:block}.mq-item{display:block;width:100%;text-align:left;border:0;background:transparent;cursor:pointer;padding:9px 14px;color:var(--c-ink);font-size:13px;border-bottom:1px solid var(--c-line)}.mq-item:last-child{border-bottom:0}.mq-item:hover,.mq-item.sel{background:var(--c-hover,rgba(120,120,140,.14))}.mq-item .s{display:block;color:var(--c-ink3);font-size:11px;margin-top:2px}
.theme-toggle:hover{border-color:var(--c-ink3);color:var(--c-ink);background:var(--c-hover)}
.homeico{display:inline-flex;color:var(--c-ink2);transition:color .15s}
.nn-n{fill:var(--c-ink2)}.nn-h{fill:var(--c-brand)}.nn-e{stroke:var(--c-line);stroke-width:1.4}
.brand[href]{text-decoration:none;cursor:pointer}
.brand[href]:hover .homeico{display:inline-grid;place-items:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);transition:color .15s} a:hover .homeico,.logo:hover .homeico,.homelink:hover .homeico{color:var(--c-brand);border-color:var(--c-brand)}
.back-portal{display:inline-flex;align-items:center;margin-left:auto;margin-right:12px;padding:7px 14px;border-radius:9px;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);font-size:12.5px;font-weight:500;text-decoration:none;transition:all .15s}
.back-portal:hover{border-color:var(--c-brand);color:var(--c-brand);background:var(--c-hover)}
.theme-toggle .tt-ico{grid-area:1/1;transition:opacity .2s,transform .3s}
.theme-toggle .tt-sun{opacity:0;transform:rotate(-90deg) scale(.5)}
.theme-toggle .tt-moon{opacity:1}
:root[data-theme="light"] .theme-toggle .tt-sun{opacity:1;transform:none}
:root[data-theme="light"] .theme-toggle .tt-moon{opacity:0;transform:rotate(90deg) scale(.5)}
.brand{display:flex;align-items:center;gap:13px}
.logo{width:34px;height:34px;flex-shrink:0;display:grid;place-items:center;position:relative;text-decoration:none}


h1{margin:0;font-size:19px;font-weight:600;letter-spacing:-.02em;color:var(--c-ink)}
h1 .dim{color:var(--c-ink3);font-weight:400;font-size:13px;margin-left:9px;letter-spacing:0}
.sub{margin:5px 0 0 47px;font-size:12px;color:var(--c-ink3);line-height:1.5}
.sub b{color:var(--c-brand-ink);font-weight:600}

/* ---- Tabs (Apple 浅色胶囊) ---- */
.tabs{display:flex;gap:4px;padding:12px 26px 0;overflow-x:auto;scrollbar-width:none;background:var(--c-bg)}
.tabs::-webkit-scrollbar{display:none}
.tab{display:flex;align-items:center;gap:8px;padding:9px 15px;border:1px solid transparent;
  background:transparent;color:var(--c-ink2);cursor:pointer;font-size:13px;font-weight:500;font-family:var(--sans);
  border-radius:10px;transition:all .18s ease;white-space:nowrap;position:relative}
.tab .tab-ico{font-size:14px;opacity:.6;transition:all .18s}
.tab:hover{background:rgba(0,0,0,.045);color:var(--c-ink)}
.tab.active{background:var(--c-panel);color:var(--c-ink);font-weight:600;
  border-color:var(--c-line);box-shadow:var(--c-shadow-sm)}
.tab.active::before{content:"";position:absolute;left:14px;right:14px;bottom:-1px;height:2px;border-radius:2px;
  background:var(--c-brand)}
.tab.active .tab-ico{opacity:1;color:var(--c-brand)}

/* ---- Toolbar (Apple 浅灰工具条) ---- */
.toolbar{display:flex;align-items:center;gap:8px;padding:11px 28px;border-top:1px solid var(--c-line);
  border-bottom:1px solid var(--c-line);background:var(--c-glass);backdrop-filter:blur(12px)}
.tb-sub{font-size:12.5px;color:var(--c-ink2);margin-right:auto;display:flex;align-items:center;gap:9px;font-weight:500}
.tb-sub .dot{width:7px;height:7px;border-radius:50%;background:var(--c-brand);box-shadow:0 0 0 3px rgba(0,113,227,.14)}
.btn{padding:7px 14px;border:1px solid var(--c-line2);background:var(--c-panel);color:var(--c-ink2);
  border-radius:980px;cursor:pointer;font-size:12.5px;font-weight:500;font-family:var(--sans);transition:all .15s;display:inline-flex;align-items:center;gap:6px}
.btn:hover{background:var(--c-panel);color:var(--c-ink);border-color:var(--c-ink3);box-shadow:var(--c-shadow-sm)}
.btn.play{background:var(--c-brand);color:#fff;border:none;font-weight:600;padding:7px 18px}
.btn.play:hover{background:#0077ed;box-shadow:0 4px 14px -2px rgba(0,113,227,.5)}
.btn.play.on{background:linear-gradient(135deg,var(--hot),#f43f5e)}


/* ---- Stage (Apple 浅色画布 · 图节点浅 tint + 深色字) ---- */
.stage{flex:1;position:relative;overflow:hidden;display:flex!important;flex-direction:column;min-height:0;
  background:
    radial-gradient(circle at center, var(--cv-dot,rgba(0,0,0,.05)) 1px, transparent 1px) 0 0/28px 28px,
    radial-gradient(1100px 560px at 88% -14%, rgba(0,113,227,.05), transparent 60%),
    radial-gradient(900px 520px at 2% 112%, rgba(122,90,240,.045), transparent 58%),
    var(--cv-bg,#f0f0f3);
  box-shadow:inset 0 1px 0 rgba(0,0,0,.05)}
.scroll{position:relative!important;inset:auto!important;flex:1;width:100%;min-height:0;overflow:auto;padding:34px}
.pane{display:none}
.pane.active{display:flex;justify-content:center;align-items:flex-start;min-height:100%}
/* 下钻页(垂直 tab 文档)块级贴顶,规避画布式 flex 居中顶部空白;隐藏冗余空 mmout */
.pane.active:has(.do-paneflow){display:block}
.do-paneflow ~ .mmout{display:none}
.mmout{transform-origin:top center;transition:transform .12s ease}
/* 嵌套/多图视图(renderNested 注入 .do-paneflow 到 .mmout)需占满宽度,否则 flex 居中会随子内容缩放导致切 tab 宽度剧烈波动 */
.mmout:has(.do-paneflow){width:100%;align-self:stretch;transform:none!important}
.mmout svg{max-width:none!important;height:auto;display:block}
.mmout svg.tblsvg{max-width:100%!important;width:100%!important}
/* 竖向子标签 + 图:合为一体的连接式卡片(左导航栏 → 右浅色画板,无缝) */
.do-paneflow{display:flex;flex-direction:column;width:100%;min-width:0}
.dataorg-wrap{display:flex;align-items:stretch;width:100%;background:var(--c-panel2);
  border:1px solid var(--c-line);border-radius:18px;box-shadow:var(--c-shadow-md);overflow:hidden;min-height:520px}
.do-nav-col{flex:0 0 240px;background:var(--c-panel2);border-right:1px solid var(--c-line);padding:14px 12px}
.do-nav-sticky{position:sticky;top:14px;display:flex;flex-direction:column;gap:4px}
.do-nav{display:flex;flex-direction:row;align-items:center;gap:9px;text-align:left;cursor:pointer;position:relative;
  background:transparent;border:1px solid transparent;border-radius:10px;
  padding:10px 14px;color:var(--c-ink2);font-family:var(--sans);transition:background .18s ease,color .18s ease}
.do-nav:hover{background:var(--c-hover,rgba(0,0,0,.04));color:var(--c-ink)}
.do-nav.active{background:var(--cv-bg,#f5f5f7);color:var(--cv-ink,#1d1d1f)}
/* 活动项左侧品牌色指示条(无阴影/无右缘咬边,避免 nav 边缘出现阴影带) */
.do-nav.active::before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:2px;background:var(--c-brand)}
.do-nav .do-nav-n{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;
  width:20px;height:20px;border-radius:6px;background:color-mix(in srgb,var(--c-brand) 12%,transparent);
  font:700 11px/1 var(--mono);color:var(--c-brand)}
.do-nav .do-nav-t{flex:1 1 auto;min-width:0;font:600 12.5px/1.3 var(--sans);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.do-nav.active .do-nav-n{background:var(--c-brand);color:#fff}
.do-nav.active .do-nav-t{color:var(--cv-ink,#1d1d1f)}
.do-stage{flex:1 1 0;min-width:0;position:relative;z-index:1;background:var(--cv-bg,#f5f5f7);overflow:hidden}
.do-sec{display:none;background:var(--cv-bg,#f5f5f7);padding:22px 26px 26px}
.do-sec.active{display:block}
.do-h{margin:0 0 16px;font:600 15px/1.4 var(--sans);color:var(--cv-ink,#1d1d1f);letter-spacing:-.01em;
  padding-left:11px;border-left:3px solid var(--c-brand)}
.do-out{overflow-x:auto}
.do-out svg{max-width:100%;height:auto}
/* EXPLAIN 视图:顶部示例 SQL 条 */
.do-sqlbar{display:flex;align-items:center;gap:12px;background:var(--c-panel2);border:1px solid var(--c-line);
  border-radius:14px;padding:12px 16px;margin-bottom:14px}
.do-sqlbar-tag{flex:0 0 auto;font:700 11px/1 var(--mono);color:var(--c-brand);
  background:color-mix(in srgb,var(--c-brand) 12%,transparent);padding:5px 9px;border-radius:6px}
.do-sqlbar-code{flex:1 1 auto;min-width:0;font:500 12.5px/1.5 var(--mono);color:var(--c-ink);white-space:pre-wrap;word-break:break-word}
.dataorg-body{min-height:480px}
/* 快速开始 步骤面板:描述 + 三列并排码卡 */
.step-desc{font:400 12.5px/1.6 var(--sans);color:var(--c-ink2);margin:0 0 12px}
.step-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.step-col{background:var(--c-panel2);border:1px solid var(--c-line);border-radius:12px;padding:12px 14px;min-width:0}
.step-col-h{font:600 13px/1.4 var(--sans);color:var(--c-ink);margin-bottom:6px}
.step-cols .do-out{overflow-x:auto}
/* 代码码卡:深色底 + 点击复制 */
.codewrap{position:relative}
.codeblk{margin:0;background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:12px 14px;
  overflow-x:auto;font:500 12.5px/1.55 var(--mono);color:#c9d1d9;white-space:pre}
.codeblk code{font:inherit;white-space:pre}
.codecopy{position:absolute;top:8px;right:8px;z-index:2;cursor:pointer;
  font:600 11px/1 var(--sans);color:#9aa4b2;background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.14);border-radius:6px;padding:5px 9px;transition:all .15s}
.codecopy:hover{color:#fff;background:rgba(255,255,255,.12)}
.codecopy.ok{color:#3fb950;border-color:#3fb95055}
.do-out .node.clickable{cursor:pointer}
.do-out .node.clickable:hover{filter:drop-shadow(0 0 6px rgba(0,113,227,.4))}
.do-out .node.clickable rect,.do-out .node.clickable polygon{transition:filter .12s ease}
/* 深色背景兜底:任何未显式着色的 SVG 元素默认会是黑色(不可见);仅对"无显式颜色"者给安全色,绝不覆盖已着色元素。默认线条用黄色 */
.mmout svg text:not([fill]):not([style*="fill"]){ fill:var(--cv-ink); }
.mmout svg tspan:not([fill]):not([style*="fill"]){ fill:var(--cv-ink); }
.mmout svg line:not([stroke]):not([style*="stroke"]){ stroke:var(--cv-edge); }
.mmout svg path:not([stroke]):not([fill]):not([style*="stroke"]):not([style*="fill"]){ stroke:#c1962a; fill:none; }
.mmout svg polyline:not([stroke]):not([fill]){ stroke:#c1962a; fill:none; }
.mmout .chainstep:hover .hovcard{display:block!important}
.mmout .chainstep:hover{filter:drop-shadow(0 4px 10px rgba(0,0,0,.6))}
/* 快速开始 · SVG 流程图内的富文本描述面板(foreignObject) */
/* 快速开始 · 分层结构化卡片(FE 单点 / BE 并行 / 返回) */
.tcard2{background:#ffffff;border:1px solid var(--c-line);border-left:3px solid var(--sa,#0071e3);border-radius:14px;overflow:hidden;font-family:var(--sans);height:100%;display:flex;flex-direction:column;box-shadow:var(--c-shadow-sm)}
.tcard2-hd{display:flex;align-items:center;gap:8px;padding:9px 13px;background:var(--c-panel2);border-bottom:1px solid var(--c-line)}
.tcard2-badge{flex:0 0 20px;width:20px;height:20px;border-radius:50%;color:#fff;font-size:11.5px;font-weight:700;display:flex;align-items:center;justify-content:center}
.tcard2-ph{font-size:13px;font-weight:600;color:var(--c-ink);flex:1;line-height:1.2}
.tcard2-bd{padding:10px 13px 11px;flex:1;display:flex;flex-direction:column}
.tcard2-what{font-size:11.5px;color:var(--c-ink2);line-height:1.55;margin-bottom:8px;flex:1}
.tcard2-syms{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.tcard2-sym{font-family:var(--mono);font-size:10.5px;color:var(--c-ink3);padding:2px 8px;border-radius:5px;background:var(--c-panel2);border:1px solid var(--c-line)}
.tcard2-sym.hot{color:var(--c-brand);border-color:rgba(0,113,227,.35);cursor:pointer;background:rgba(0,113,227,.06)}
.tcard2-sym.hot:hover{background:rgba(0,113,227,.12);border-color:var(--c-brand)}
.tcard2-out{font-size:10.5px;font-family:var(--mono);margin-bottom:8px;color:var(--c-ink2)}
.tcard2-jump{font-size:11px;font-weight:600;color:var(--sa,#0071e3);background:transparent;border:1px solid var(--sa,#0071e3);border-radius:8px;padding:4px 11px;cursor:pointer;font-family:var(--sans);align-self:flex-start;transition:all .15s}
.tcard2-jump:hover{background:var(--sa,#0071e3);color:#fff}
.mmout .tour-op.hot:hover rect,.mmout .tour-op.hot:hover{filter:drop-shadow(0 0 6px #0071e3)}

/* mermaid theming — Apple 浅色:通透节点 · 细线 · 圆角 · 侧边阶段轴 · 克制留白 */
.mmout .cluster rect{rx:16;ry:16;stroke-width:1px!important;stroke-dasharray:3 4!important}
.mmout .cluster .cluster-label,.mmout .cluster text{fill:var(--cv-ink2)!important;font-weight:600!important;
  font-size:12px!important;letter-spacing:.3px}
.mmout .node rect,.mmout .node polygon,.mmout .node circle,.mmout .node path{
  rx:8;ry:8;transition:all .2s}
.mmout .node .label,.mmout .node text{font-family:var(--mono)!important}
.mmout .nodeLabel,.mmout .node .label{white-space:nowrap!important;line-height:1.5!important}
.mmout .nodeLabel small,.mmout .node small{font-family:var(--mono)!important;font-size:10px!important;opacity:.62;font-weight:400}
.mmout foreignObject{overflow:visible!important}
.mmout .node.clickable{cursor:pointer}
.tnode{transition:opacity .15s}
.tnode.tclick{cursor:pointer}
.tnode.tclick:hover rect:first-of-type{filter:brightness(1.35)}
.tnode.tdim{opacity:.28}
.tnode.thot rect:first-of-type{filter:brightness(1.25);stroke-width:2}
.tedge{transition:opacity .15s}
.mmout .node.clickable:hover rect,.mmout .node.clickable:hover polygon{
  stroke-width:2px!important;filter:drop-shadow(0 0 10px var(--brand))}
.mmout .node.dimmed{opacity:.16;transition:opacity .25s}
.mmout .node.hot rect,.mmout .node.hot polygon{stroke:var(--hot)!important;stroke-width:2.5px!important;
  filter:drop-shadow(0 0 14px var(--hot))}
.mmout .edgePath path,.mmout .flowchart-link{stroke-width:1.3px!important}
.mmout .edgePath.dimmed,.mmout .flowchart-link.dimmed{opacity:.07}
.mmout .edgeLabel{background:transparent!important}
.mmout .edgeLabel foreignObject div{background:rgba(245,245,247,.92)!important;color:#4a5568!important;
  padding:1px 6px;border-radius:5px;font-size:10.5px!important;backdrop-filter:blur(4px);box-shadow:0 0 0 1px rgba(0,0,0,.05)}

/* flow animation dash */
.mmout path.flowchart-link.flowing,.mmout .edgePath.flowing path,.mmout line.tour-flowline.flowing,.mmout svg path.flowing,.mmout svg line.flowing{
  stroke-dasharray:7 6;animation:dash 1s linear infinite;stroke:var(--accent)!important;stroke-width:2.8px!important;
  opacity:1!important;filter:drop-shadow(0 0 6px var(--accent))}
@keyframes dash{to{stroke-dashoffset:-26}}
/* 结构图/schema 表/诊断:无流动边时,按顺序脉冲高亮节点 */
.mmout .pulsing rect,.mmout rect.pulsing{stroke:var(--accent)!important;stroke-width:2.4px!important;filter:drop-shadow(0 0 7px var(--accent))}
.mmout g.pulsing{animation:pulseNode .8s ease-in-out}
@keyframes pulseNode{0%,100%{opacity:1}50%{opacity:.55}}
/* 边序号徽标 */
.mmout .edge-seq circle{fill:var(--cv-card);stroke:var(--brand);stroke-width:1.5px}
.mmout .edge-seq text{fill:var(--accent);font-size:11px;font-weight:700;font-family:var(--mono)}
/* ---- 图例浮层 ---- */
/* ---- 视图内右侧常驻导航卡片 ---- */
.vguide{position:absolute;top:16px;right:16px;width:284px;z-index:38;
  background:var(--c-glass);
  border:1px solid var(--c-line);border-radius:16px;box-shadow:var(--c-shadow-lg);
  backdrop-filter:blur(20px) saturate(1.4);transition:width .2s,padding .2s}
.vguide.collapsed{width:42px}
.vguide.collapsed .vguide-inner{display:none}
.vguide-collapse{position:absolute;top:10px;right:10px;width:24px;height:24px;border-radius:7px;
  border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;font-size:12px;
  transition:transform .2s;z-index:1}
.vguide.collapsed .vguide-collapse{transform:rotate(0deg)}
.vguide:not(.collapsed) .vguide-collapse{transform:rotate(180deg)}
.vguide-inner{padding:16px 16px 14px;max-height:calc(100vh - 220px);overflow-y:auto;scrollbar-width:thin}
.vguide-inner::-webkit-scrollbar{width:6px}.vguide-inner::-webkit-scrollbar-thumb{background:var(--c-line2);border-radius:3px}
.vg-sec{padding:11px 0;border-bottom:1px solid var(--c-line)}
.vg-sec:last-child{border-bottom:none}
.vg-sec.vg-head{padding-top:2px}
.vg-title{font-size:14px;font-weight:650;color:var(--c-ink);margin-bottom:7px;padding-right:26px}
.vg-summary{font-size:12px;line-height:1.7;color:var(--c-ink2)}
.vg-h{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:var(--c-brand);margin-bottom:8px;font-weight:600}
.vg-stages{display:flex;flex-direction:column;gap:5px}
.vg-stage{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--c-ink2);padding:4px 8px;border-radius:7px;
  background:var(--c-panel2);border:1px solid var(--c-line)}
.vg-stage .vg-num{width:16px;height:16px;flex-shrink:0;display:grid;place-items:center;border-radius:50%;
  background:rgba(0,113,227,.12);color:var(--c-brand);font-size:10px;font-weight:700}
.legend{position:absolute;right:18px;bottom:18px;z-index:40}
.legend-toggle{width:34px;height:34px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);
  color:var(--c-brand);font-size:16px;font-weight:700;cursor:pointer;box-shadow:var(--c-shadow-md);transition:all .18s}
.legend-toggle:hover{background:var(--c-glass-tint);border-color:var(--c-brand)}
.legend-body{position:absolute;right:0;bottom:44px;width:290px;padding:14px 16px;border-radius:16px;
  background:var(--c-glass);border:1px solid var(--c-line);
  box-shadow:var(--c-shadow-lg);backdrop-filter:blur(20px) saturate(1.4);display:none}
.legend-body.show{display:block}
.legend-sec{padding:8px 0;border-bottom:1px solid var(--c-line)}
.legend-sec:last-child{border-bottom:none}
.legend-h{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--c-brand);margin-bottom:7px;font-weight:600}
.legend-row{font-size:12px;color:var(--c-ink2);line-height:1.9;display:flex;align-items:center;gap:7px}
.legend-row b{color:var(--c-ink);font-weight:600}
.lg-seq{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;background:var(--c-glass-tint);
  border:1.5px solid var(--c-brand);color:var(--c-brand);font-size:10px;font-weight:700;flex-shrink:0}
.lg-box{display:inline-block;width:16px;height:12px;border:2px solid;border-radius:3px;flex-shrink:0}
.lg-stage{display:inline-block;width:16px;height:12px;border:1px dashed var(--c-line2);border-radius:4px;background:rgba(0,113,227,.06);flex-shrink:0}
.legend-tags{display:flex;flex-wrap:wrap;gap:6px}
.legend-tags .lt{font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;background:var(--c-panel2);border:1px solid var(--c-line)}

.empty{display:grid;place-items:center;height:100%;color:var(--ink3);gap:14px;text-align:center}
.empty .big{font-size:44px;opacity:.35}
/* ---- breadcrumb ---- */
.breadcrumb{display:none;align-items:center;gap:11px;padding:11px 30px;font-size:12.5px;background:var(--c-glass);backdrop-filter:blur(12px);border-bottom:1px solid var(--c-line)}
.breadcrumb.show{display:flex}
.crumb-home{background:transparent;border:none;color:var(--c-brand);cursor:pointer;font-size:12.5px;font-weight:500;padding:5px 10px;border-radius:8px;transition:background .15s}
.crumb-home:hover{background:rgba(0,113,227,.08)}
.crumb-sep{color:var(--c-ink3)}
.crumb-cur{color:var(--c-ink);font-weight:600}
.brand{cursor:pointer}
/* ---- home (Apple Store 商品网格 · 浅色) ---- */
.home{display:none;height:100%;overflow-y:auto;padding:56px 32px 72px;position:relative;background:var(--c-bg)}
.home-legend{position:absolute;top:44px;right:40px;width:392px;z-index:30}
.home-legend-toggle{width:100%;display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:10px 15px;border-radius:12px;border:1px solid var(--c-line);background:var(--c-panel);
  color:var(--c-ink);font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit;box-shadow:var(--c-shadow-sm)}
.home-legend-toggle:hover{border-color:var(--c-ink3);background:var(--c-panel)}
.home-legend-toggle .chev{color:var(--c-ink3);font-size:11px;transition:transform .18s}
.home-legend:not(.collapsed) .home-legend-toggle .chev{transform:rotate(180deg)}
.home-legend-body{display:none;margin-top:8px;padding:20px 22px;border:1px solid var(--c-line);
  border-radius:16px;background:var(--c-panel);box-shadow:var(--c-shadow-md)}
.home-legend:not(.collapsed) .home-legend-body{display:block}
.legend-block{margin-bottom:16px}
.legend-block:last-child{margin-bottom:0}
.legend-cap{font-size:10.5px;font-weight:700;color:var(--c-ink3);text-transform:uppercase;letter-spacing:.7px;margin-bottom:9px}
.legend-item{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.legend-item:last-child{margin-bottom:0}
.legend-tag{flex:0 0 52px;font-size:11.5px;font-weight:700;text-align:center;padding:2px 0;border-radius:6px;
  background:var(--c-panel2);border:1px solid var(--c-line)}
.legend-item .lt{font-size:11.5px;color:var(--c-ink2);line-height:1.5;flex:1}
.legend-swatches{display:grid;grid-template-columns:1fr 1fr;gap:7px 14px}
.legend-sw{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--c-ink2)}
.legend-sw i{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
.legend-foot{font-size:10.5px;color:var(--c-ink3);margin-top:14px;border-top:1px solid var(--c-line);padding-top:10px;line-height:1.55}
.home.show{display:block}
.home-hero{max-width:1180px;margin:8px auto 28px;text-align:center}
.home-title{font-size:66px;font-weight:700;letter-spacing:-.03em;color:var(--c-ink);line-height:1.02;
  background:linear-gradient(180deg,var(--c-ink),color-mix(in srgb,var(--c-ink) 62%,var(--c-brand)));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.home-desc{margin:20px auto 0;font-size:20px;color:var(--c-ink2);line-height:1.55;font-weight:400;max-width:720px;letter-spacing:-.01em}
/* ===== 导航方式切换(卡片 / 架构图 / 目录树)===== */
.nav-switch{display:inline-flex;margin:30px auto 0;padding:4px;gap:2px;border-radius:13px;
  background:var(--c-panel2);border:1px solid var(--c-line);box-shadow:var(--c-shadow-sm)}
.nav-seg{border:0;background:transparent;color:var(--c-ink2);font-size:13.5px;font-weight:600;
  padding:8px 18px;border-radius:10px;cursor:pointer;transition:all .2s;white-space:nowrap;letter-spacing:-.01em}
.nav-seg:hover{color:var(--c-ink)}
.nav-seg.active{background:var(--c-panel);color:var(--c-brand);box-shadow:var(--c-shadow-sm)}
.nav-mode{display:none;animation:navfade .3s ease}
.nav-mode.active{display:block}
@keyframes navfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
/* ---- 架构图导航 ---- */
.arch-stage{max-width:1120px;margin:0 auto;padding:8px}
.arch-canvas{position:relative;width:100%;border-radius:20px;overflow:hidden;
  background:var(--c-panel);border:1px solid var(--c-line);box-shadow:var(--c-shadow-md)}
.arch-img{display:block;width:100%;height:auto;user-select:none}
html:not([data-theme="light"]) .arch-img{filter:invert(.9) hue-rotate(180deg) saturate(1.05) brightness(.97)}
/* design 原理图走查:每 .do-sec 内一张静态 base64 SVG,居中自适应,暗色反相 */
.svg-walk-out{display:flex;justify-content:center;padding:4px 0}
.svg-walk-img{display:block;max-width:100%;height:auto;user-select:none;
  border-radius:14px;background:#fbfbfd;box-shadow:var(--c-shadow-sm)}
html:not([data-theme="light"]) .svg-walk-img{filter:invert(.9) hue-rotate(180deg) saturate(1.05) brightness(.97)}
/* 快速开始上手总览复合视图:总览图 + 步骤选择器 + 内容区 */
.qst-wrap{display:flex;flex-direction:column;gap:20px;padding:8px 4px 4px;max-width:1120px;margin:0 auto}
.qst-overview{position:relative;display:inline-block;align-self:center;line-height:0}
.qst-overview .svg-walk-img{display:block;width:100%}
.qst-hot{position:absolute;border:2px solid transparent;border-radius:14px;background:transparent;
  cursor:pointer;padding:0;transition:all .16s}
.qst-hot:hover{border-color:var(--c-brand,#0a84ff);background:color-mix(in srgb,var(--c-brand,#0a84ff) 10%,transparent)}
.qst-hot.active{border-color:var(--c-brand,#0a84ff);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand,#0a84ff) 22%,transparent);
  background:color-mix(in srgb,var(--c-brand,#0a84ff) 8%,transparent)}
.qst-content{border-top:1px solid var(--cv-border,#e8e8ea);padding-top:20px;min-height:200px}
/* design prose 要点区(总纲 banner + 调优/误区 两栏)——用画布语义 token,随主题翻转 */
.walk-tips-out{padding:6px 2px}
.walk-summary{font-size:15px;line-height:1.7;color:var(--cv-ink,#1d1d1f);background:var(--cv-card-alt,#f2f6ff);
  border:1px solid var(--cv-border,#e2e8f2);border-left:3px solid var(--c-brand,#0a84ff);
  border-radius:12px;padding:16px 20px;margin-bottom:20px}
.walk-summary b{color:var(--c-brand,#0a84ff);font-weight:700}
.walk-position{font-size:13.5px;line-height:1.65;color:var(--cv-ink2,#4a4e57);
  border:1px dashed var(--cv-border,#d8dee8);border-radius:11px;padding:12px 16px;margin-bottom:14px}
.walk-position-tag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.06em;color:var(--cv-bg,#fff);
  background:var(--cv-ink2,#8a94a6);border-radius:6px;padding:2px 8px;margin-right:10px;vertical-align:1px}
.walk-position b{color:var(--cv-ink,#1d1d1f);font-weight:700}
.walk-tips{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:900px){.walk-tips{grid-template-columns:1fr}}
.walk-tipcol{background:var(--cv-card,#fff);border:1px solid var(--cv-border,#e8e8ea);border-radius:12px;padding:16px 18px}
.walk-tiph{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:var(--cv-ink2,#6e6e73);margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--cv-border,#e8e8ea)}
.walk-tiplist{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:9px}
.walk-tiplist li{font-size:13.5px;line-height:1.6;color:var(--cv-ink,#1d1d1f)}
.walk-tiplist li b{color:var(--cv-ink,#1d1d1f);font-weight:700}
.walk-tips code,.walk-summary code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:12px;
  background:var(--cv-card-alt,#eef1f6);color:var(--c-brand,#0a84ff);padding:1.5px 6px;border-radius:5px}
/* 深化对比表(Apple 工业风,随明暗翻转)*/
.walk-deepen{margin-top:22px;padding-top:18px;border-top:1px solid var(--cv-border,#e8e8ea)}
.walk-deepen-h{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:var(--cv-ink2,#6e6e73);margin-bottom:14px}
.walk-dtable{width:100%;border-collapse:separate;border-spacing:0;margin:0 0 20px;font-size:12.5px;
  background:var(--cv-card,#fff);border:1px solid var(--cv-border,#e8e8ea);border-radius:12px;overflow:hidden;
  box-shadow:var(--c-shadow-sm)}
.walk-dtable caption{caption-side:top;text-align:left;font-size:13.5px;font-weight:600;color:var(--cv-ink,#1d1d1f);
  padding:0 2px 9px;letter-spacing:-.01em}
.walk-dtable thead th{background:var(--cv-card-alt,#f2f6ff);color:var(--cv-ink2,#4a4e57);font-weight:600;
  text-align:left;padding:9px 13px;font-size:11.5px;border-bottom:1px solid var(--cv-border,#e8e8ea);white-space:nowrap}
.walk-dtable tbody td{padding:9px 13px;color:var(--cv-ink,#1d1d1f);line-height:1.5;
  border-bottom:1px solid var(--cv-border,#eceef2);vertical-align:top}
.walk-dtable tbody tr:last-child td{border-bottom:0}
.walk-dtable tbody tr:nth-child(even){background:color-mix(in srgb,var(--cv-card-alt,#f2f6ff) 45%,transparent)}
.walk-dtable td:first-child{font-weight:600;color:var(--cv-ink,#1d1d1f)}
.walk-dtable code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:11px;
  background:var(--cv-card-alt,#eef1f6);color:var(--c-brand,#0a84ff);padding:1px 5px;border-radius:4px}
.walk-dtable b{color:var(--cv-ink,#1d1d1f);font-weight:700}
.arch-hot{position:absolute;border:1.5px solid transparent;border-radius:11px;background:transparent;
  cursor:pointer;padding:0;transition:all .18s;display:grid;place-items:center}
.arch-hot:hover{border-color:var(--c-brand);background:color-mix(in srgb,var(--c-brand) 12%,transparent);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand) 16%,transparent)}
.arch-hot:focus-visible{outline:none;border-color:var(--c-brand);background:color-mix(in srgb,var(--c-brand) 10%,transparent)}
.arch-hot-lab{opacity:0;font-size:11px;font-weight:700;color:#fff;background:var(--c-brand);
  padding:3px 9px;border-radius:7px;transition:opacity .18s;pointer-events:none;box-shadow:var(--c-shadow-md);white-space:nowrap}
.arch-hot:hover .arch-hot-lab{opacity:1}
.arch-extra{max-width:1120px;margin:22px auto 0;text-align:center}
.arch-extra-h{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--c-ink3);font-weight:600;margin-bottom:12px}
.arch-chips{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}
.arch-chip{font-size:13px;font-weight:600;color:var(--c-ink2);padding:8px 16px;border-radius:11px;cursor:pointer;
  background:var(--c-panel);border:1px solid var(--c-line);transition:all .2s;box-shadow:var(--c-shadow-sm)}
.arch-chip:hover{color:var(--c-brand);border-color:var(--c-brand);transform:translateY(-2px)}
/* ---- 目录树导航 ---- */
.tree-wrap{max-width:900px;margin:0 auto;text-align:left;
  background:var(--c-panel);border:1px solid var(--c-line);border-radius:20px;padding:14px 20px 24px;box-shadow:var(--c-shadow-md)}
.tree-cat{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--c-ink3);
  margin:22px 4px 8px;padding-bottom:7px;border-bottom:1px solid var(--c-line)}
.tree-cat:first-child{margin-top:6px}
.tree-theme{border-radius:12px;overflow:hidden}
.tree-thead{width:100%;display:flex;align-items:center;gap:10px;padding:11px 12px;border:0;cursor:pointer;
  background:transparent;color:var(--c-ink);font-size:15px;font-weight:600;text-align:left;transition:background .18s;border-radius:10px}
.tree-thead:hover{background:var(--c-panel2)}
.tree-chev{font-size:11px;color:var(--c-ink3);transition:transform .2s;width:12px;flex-shrink:0}
.tree-theme.open .tree-chev{transform:rotate(90deg)}
.tree-tico{font-size:16px;color:var(--c-brand);width:22px;text-align:center;flex-shrink:0}
.tree-ttl{flex:1}
.tree-tcount{font-size:11px;font-weight:700;color:var(--c-ink3);background:var(--c-panel2);border:1px solid var(--c-line);
  border-radius:20px;padding:2px 9px;min-width:24px;text-align:center}
.tree-leaves{display:none;padding:2px 0 10px 34px}
.tree-theme.open .tree-leaves{display:block}
.tree-leaf{display:flex;align-items:center;gap:9px;width:100%;padding:7px 12px;border:0;border-radius:8px;cursor:pointer;
  background:transparent;color:var(--c-ink2);font-size:13.5px;text-align:left;transition:all .16s;border-left:2px solid var(--c-line)}
.tree-leaf:hover{background:var(--c-panel2);color:var(--c-brand);border-left-color:var(--c-brand)}
.tree-leaf-ico{font-size:13px;color:var(--c-ink3);width:16px;text-align:center;flex-shrink:0}
.tree-leaf:hover .tree-leaf-ico{color:var(--c-brand)}
.tcards{max-width:1180px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(256px,1fr));gap:18px}
/* 单卡板块(如 Getting Started 只有 1 张卡):居中且不拉伸,避免 auto-fill 左对齐留空轨道 */
.tcards:has(> .tcard:only-child){display:flex;justify-content:center}
.tcards > .tcard:only-child{width:min(360px,100%);flex:none}
.tcard{display:flex;gap:15px;align-items:flex-start;text-align:left;padding:22px;border-radius:22px;cursor:pointer;
  background:var(--c-panel);border:1px solid var(--c-line);
  transition:transform .35s cubic-bezier(.32,.72,0,1),box-shadow .35s cubic-bezier(.32,.72,0,1),border-color .3s;position:relative;overflow:hidden;box-shadow:var(--c-shadow-sm)}
.tcard::before{content:"";position:absolute;inset:0;background:radial-gradient(420px 200px at 100% 0,color-mix(in srgb,var(--c-brand) 12%,transparent),transparent 62%);opacity:0;transition:opacity .35s}
.tcard:hover{transform:translateY(-6px) scale(1.008);border-color:var(--c-line2);box-shadow:var(--c-shadow-lg)}
.tcard:hover::before{opacity:1}
.tcard-ico{font-size:22px;line-height:1;flex-shrink:0;width:48px;height:48px;display:grid;place-items:center;border-radius:14px;
  background:var(--c-panel2);color:var(--c-brand);border:1px solid var(--c-line);transition:transform .35s cubic-bezier(.32,.72,0,1)}
.tcard:hover .tcard-ico{transform:scale(1.06)}
/* 主题按大类的语义色(Apple 浅底:柔和 tint icon 底) */
.tcard[data-cat] .tcard-ico{background:color-mix(in srgb,var(--tint) 14%,var(--c-panel2));color:var(--tint);border-color:color-mix(in srgb,var(--tint) 22%,var(--c-line))}
/* 克制色阶(Apple 式:S≤40%,明度收窄带,仅色相区分)。覆盖 4 板块 + 残留 cat */
.tcard[data-cat="start"]{--tint:#6e90c0}
.tcard[data-cat="iface"]{--tint:#5e9aa8}
.tcard[data-cat="support"]{--tint:#8a93a3}
.tcard[data-cat="appendix"]{--tint:#82868e}
.tcard[data-cat="core"]{--tint:#8a93a3}
.tcard[data-cat="acceleration"]{--tint:#8e82be}
.tcard[data-cat="operations"]{--tint:#b7975e}
.tcard-body{display:flex;flex-direction:column;gap:5px;z-index:1;min-width:0;flex:1}
.tcard-titlerow{display:flex;align-items:center;gap:0;min-width:0}
.tcard-title{font-size:16px;font-weight:600;letter-spacing:-.015em;color:var(--c-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.tcard-desc{font-size:12.5px;color:var(--c-ink2);line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tcard-meta{font-size:11px;color:var(--c-brand);margin-top:4px;font-weight:600}
.tcard:hover .tcard-desc{-webkit-line-clamp:5}
.cat-sec{max-width:1180px;margin:44px auto 18px;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--c-ink3);display:flex;align-items:center;gap:14px}
.cat-sec::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--c-line),transparent)}
</style>
</head>
<body>
<div id="loadingOverlay" role="status" aria-live="polite">
  <div class="lo-inner">
    <div class="lo-logo"></div>
    <div class="lo-title">Kafka Engine Atlas</div>
    <div class="lo-sub">正在装载引擎图谱…</div>
    <div class="lo-bar"><span class="lo-bar-fill"></span></div>
    <div class="lo-hint">首帧正在解码内联原理图,稍候即现 —— 空白属正常装载,非内容缺失</div>
  </div>
</div>
<div id="app">
  <header>
    <a class="brand" id="brandHome" href="../index.html" title="返回导航主页">
      <div class="logo"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></div>
    </a>
    <div class="brand-intro" style="display:flex;flex-direction:column;align-items:flex-start;margin-left:12px;min-width:0;max-width:min(60vw,760px)"><div style="font-size:15px;font-weight:600;color:var(--c-ink);line-height:1.3">Apache Kafka · 核心原理图谱</div><span style="margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5;text-align:left">分布式事件流平台:分区 append-only 日志 + 副本 ISR 复制,顺序写磁盘 + 零拷贝高吞吐,消费者组按位点拉取。</span></div>
    <label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label>
    <a href="https://github.com/apache/kafka" target="_blank" rel="noopener" title="GitHub 源码仓库" style="margin-left:auto;display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://kafka.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjMjMxRjIwIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+QXBhY2hlIEthZmthPC90aXRsZT48cGF0aCBkPSJNOS43MSAyLjEzNmExLjQzIDEuNDMgMCAwIDAtMi4wNDcgMGgtLjAwN2ExLjQ4IDEuNDggMCAwIDAtLjQyMSAxLjA0MmMwIC40MS4xNjEuNzc3LjQyMiAxLjAzOWwuMDA3LjAwN2MuMjU3LjI2NC42MTYuNDI2IDEuMDE5LjQyNi40MDQgMCAuNzY2LS4xNjIgMS4wMjctLjQyNmwuMDAzLS4wMDdjLjI2MS0uMjYyLjQyMS0uNjI5LjQyMS0xLjAzOSAwLS40MDgtLjE1OS0uNzc3LS40MjEtMS4wNDJIOS43MXpNOC42ODMgMjIuMjk1Yy40MDQgMCAuNzY2LS4xNjcgMS4wMjctLjQyOWwuMDAzLS4wMDhjLjI2MS0uMjYxLjQyMS0uNjMxLjQyMS0xLjAzNiAwLS40MS0uMTU5LS43NzgtLjQyMS0xLjA0NEg5LjcxYTEuNDIgMS40MiAwIDAgMC0xLjAyNy0uNDMyIDEuNCAxLjQgMCAwIDAtMS4wMi40MzJoLS4wMDdjLS4yNi4yNjYtLjQyMi42MzQtLjQyMiAxLjA0NCAwIC40MDYuMTYxLjc3NS40MjIgMS4wMzZsLjAwNy4wMDhjLjI1OC4yNjIuNjE3LjQyOSAxLjAyLjQyOXptNy44OS00LjQ2MmMuMzU5LS4wOTYuNjgzLS4zMy44ODItLjY4NGwuMDI3LS4wNTJhMS40NyAxLjQ3IDAgMCAwIC4xMTQtMS4wNjcgMS40NTQgMS40NTQgMCAwIDAtLjY3NS0uODk2bC0uMDIxLS4wMTRhMS40MjUgMS40MjUgMCAwIDAtMS4wNzgtLjEzMmMtLjM2LjA5MS0uNjg0LjMzNS0uODgxLjY4Ni0uMi4zNDktLjI0MS43NS0uMTQ2IDEuMTE5LjA5OS4zNjMuMzMuNjkxLjY3NS44OTZoLjAwMmMuMzQ2LjIwMy43MzcuMjM5IDEuMTAxLjE0NHptLTYuNDA1LTcuMzQyYTIuMDgzIDIuMDgzIDAgMCAwLTEuNDg1LS42MjdjLS41OCAwLTEuMTAzLjI0Mi0xLjQ4Mi42MjctLjM3OC4zODUtLjYxMi45MTYtLjYxMiAxLjUwN3MuMjMzIDEuMTI0LjYxMiAxLjUxNGEyLjA4IDIuMDggMCAwIDAgMi45NjcgMGMuMzc5LS4zOS42MTItLjkyMy42MTItMS41MTRzLS4yMzMtMS4xMjItLjYxMi0xLjUwN3ptLS44MzUtMi41MWMuODQzLjE0MSAxLjYuNTUyIDIuMTc4IDEuMTQ0aC4wMDRjLjA5Mi4wOTMuMTgyLjE5Ni4yNjUuMjk5bDEuNDQ2LS44NTFhMy4xNzYgMy4xNzYgMCAwIDEtLjA0Ny0xLjgwOCAzLjE0OSAzLjE0OSAwIDAgMSAxLjQ1Ni0xLjkyNmwuMDI1LS4wMTZhMy4wNjIgMy4wNjIgMCAwIDEgMi4zNDUtLjMwNmMuNzcuMjEgMS40NjUuNzIxIDEuODk4IDEuNDgydi4wMDJjLjQzMS43NTcuNTE4IDEuNjI2LjMxMyAyLjQwOGEzLjE0NSAzLjE0NSAwIDAgMS0xLjQ1NiAxLjkyOGwtLjE5OC4xMThoLS4wMmEzLjA5NSAzLjA5NSAwIDAgMS0yLjE1NC4yMDEgMy4xMjcgMy4xMjcgMCAwIDEtMS41MTQtLjk0NGwtMS40NDQuODQ4YTQuMTYyIDQuMTYyIDAgMCAxIDAgMi44NzlsMS40NDQuODQ2Yy40MTMtLjQ3LjkzOS0uNzg5IDEuNTE0LS45NDRhMy4wNDEgMy4wNDEgMCAwIDEgMi4zNzEuMzE5bC4wNDguMDIzdi4wMDJhMy4xNyAzLjE3IDAgMCAxIDEuNDA4IDEuOTA2IDMuMjE1IDMuMjE1IDAgMCAxLS4zMTMgMi40MDVsLS4wMjYuMDUzLS4wMDMtLjAwNWEzLjE0NyAzLjE0NyAwIDAgMS0xLjg2NyAxLjQzNiAzLjA5NiAzLjA5NiAwIDAgMS0yLjM3MS0uMzE4di0uMDA2YTMuMTU2IDMuMTU2IDAgMCAxLTEuNDU2LTEuOTI3IDMuMTc1IDMuMTc1IDAgMCAxIC4wNDctMS44MDVsLTEuNDQ2LS44NDhhMy45MDUgMy45MDUgMCAwIDEtLjI2NS4yOTRsLS4wMDQuMDA1YTMuOTM4IDMuOTM4IDAgMCAxLTIuMTc4IDEuMTM4djEuNjk5YTMuMDkgMy4wOSAwIDAgMSAxLjU2Ljg2MmwuMDAyLjAwNGMuNTY1LjU3Mi45MTQgMS4zNjguOTE0IDIuMjQzIDAgLjg3My0uMzUgMS42NjQtLjkxNCAyLjIzOWwtLjAwMi4wMDlhMy4xIDMuMSAwIDAgMS0yLjIxLjkzMSAzLjEgMy4xIDAgMCAxLTIuMjA2LS45M2gtLjAwMnYtLjAwOWEzLjE4NiAzLjE4NiAwIDAgMS0uOTE2LTIuMjM5YzAtLjg3NS4zNS0xLjY3Mi45MTYtMi4yNDN2LS4wMDRoLjAwMmEzLjEgMy4xIDAgMCAxIDEuNTU4LS44NjJ2LTEuNjk5YTMuOTI2IDMuOTI2IDAgMCAxLTIuMTc2LTEuMTM4bC0uMDA2LS4wMDVhNC4wOTggNC4wOTggMCAwIDEtMS4xNzMtMi44NzRjMC0xLjEyMi40NTItMi4xMzYgMS4xNzMtMi44NzJoLjAwNmEzLjk0NyAzLjk0NyAwIDAgMSAyLjE3Ni0xLjE0NFY2LjI4OWEzLjEzNyAzLjEzNyAwIDAgMS0xLjU1OC0uODY0aC0uMDAydi0uMDA0YTMuMTkyIDMuMTkyIDAgMCAxLS45MTYtMi4yNDNjMC0uODcxLjM1LTEuNjY5LjkxNi0yLjI0M2wuMDAyLS4wMDJBMy4wODQgMy4wODQgMCAwIDEgOC42ODMgMGMuODYxIDAgMS42NDEuMzU1IDIuMjEuOTMydi4wMDJoLjAwMmMuNTY1LjU3NC45MTQgMS4zNzIuOTE0IDIuMjQzIDAgLjg3Ni0uMzUgMS42NjctLjkxNCAyLjI0M2wtLjAwMi4wMDVhMy4xNDIgMy4xNDIgMCAwIDEtMS41Ni44NjR2MS42OTJ6bTguMTIxLTEuMTI5bC0uMDEyLS4wMTlhMS40NTIgMS40NTIgMCAwIDAtLjg3LS42NjggMS40MyAxLjQzIDAgMCAwLTEuMTAzLjE0NmguMDAyYy0uMzQ3LjItLjU4LjUyOS0uNjc3Ljg5Ni0uMDk1LjM2NS0uMDU0Ljc2OC4xNDYgMS4xMTlsLjAwNy4wMDljLjIuMzQ3LjUxOS41NzkuODc0LjY3My4zNTcuMTAzLjc1NS4wNTkgMS4wOTgtLjE0NGwuMDE5LS4wMDlhMS40NyAxLjQ3IDAgMCAwIC42NTctLjg4NSAxLjQ5MyAxLjQ5MyAwIDAgMC0uMTQxLTEuMTE4Ii8+PC9zdmc+" width="18" height="18" alt="官网" style="display:block"/></a><button class="theme-toggle" id="themeToggle" title="切换深色 / 浅色主题" aria-label="切换主题">
      <span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span>
    </button>
  </header>
  <div class="breadcrumb" id="breadcrumb">
    <button class="crumb-home" id="crumbHome">← 全部主题</button>
    <span class="crumb-sep">/</span>
    <span class="crumb-cur" id="crumbCur"></span>
  </div>
  <nav class="tabs" id="tabbar">__TAB_BUTTONS__</nav>
  <div class="toolbar" id="toolbar">
    <div class="tb-sub"><span class="dot"></span><span id="paneSub"></span></div>
    <button class="btn play" id="flowPlay">▶ 播放数据流</button>
    <button class="btn" id="zoomOut">−</button>
    <button class="btn" id="zoomReset">100%</button>
    <button class="btn" id="zoomIn">+</button>
    <button class="btn" id="fitBtn">⤢ 适应</button>
  </div>
  <div class="stage">
    <div class="home" id="home">
      <div class="nav-mode nav-arch active" id="navArch">
        <div class="arch-stage">
          <div class="arch-canvas">
            <img class="arch-img" src="data:image/svg+xml;base64,__ARCH_SVG_B64__" alt="Kafka 总架构图" draggable="false"/>
            __ARCH_HOTSPOTS__
          </div>
        </div>
        <div class="arch-extra">
          <div class="arch-extra-h">架构图未直接标注 · 点此进入</div>
          <div class="arch-chips">__ARCH_EXTRA_CHIPS__</div>
        </div>
      </div>
      </div>
    <div class="scroll" id="scroll">__TAB_PANES__</div>
    <aside class="vguide collapsed" id="vguide">
      <button class="vguide-collapse" id="vguideCollapse" title="折叠/展开">▸</button>
      <div class="vguide-inner" id="vguideInner">
        <div class="vg-sec vg-head">
          <div class="vg-title" id="vgTitle"></div>
          <div class="vg-summary" id="vgSummary"></div>
        </div>
        <div class="vg-sec" id="vgStagesSec">
          <div class="vg-h">逻辑阶段</div>
          <div class="vg-stages" id="vgStages"></div>
        </div>
      </div>
    </aside>
    </div>
  </div>
</div>

<script>__MERMAID__</script>
<script>
__APP_JS__
</script>
</body>
</html>"""

# App JS: plain string. __DRILL__ / __FIRST__ replaced later. Braces/backslashes safe.
APP_JS = r"""
const DRILL = __DRILL__;
const NEST_MM = __NEST_MM__;   // 嵌套子视图里的多图数组: tid -> [[title, mermaidSrc], ...]
const RAW_MM = __RAW_MM__;     // 嵌套子视图里的单张 raw mermaid: tid -> mermaidSrc
const SVG_WALK_TIDS = __SVG_WALK_TIDS__;  // design 原理图走查 tid 集合(pane 内容已静态注入)
const QSTOUR_OVERVIEW_B64 = "__QSTOUR_OVERVIEW_B64__";  // 快速开始上手总览 SVG(base64)
const EDGES = {};   // tid -> [{from,to}]

const MM_THEME_LIGHT = {
    fontFamily:'-apple-system,PingFang SC,sans-serif', fontSize:'13px',
    primaryColor:'#eef1f6', primaryTextColor:'#1d1d1f', primaryBorderColor:'#c9cfda',
    lineColor:'#8a93a5', secondaryColor:'#f0f1f4', tertiaryColor:'#f7f8fa',
    clusterBkg:'rgba(0,0,0,0.03)', clusterBorder:'#d2d7e0',
    nodeBorder:'#c9cfda', edgeLabelBackground:'#f5f5f7',
    actorBkg:'#eef1f6', actorBorder:'#c9cfda', actorTextColor:'#1d1d1f',
    signalColor:'#6b7280', signalTextColor:'#33384a', labelBoxBkgColor:'#eef1f6',
    loopTextColor:'#1d1d1f', noteBkgColor:'#fff7e0', noteTextColor:'#5a4a1a'
};
const MM_THEME_DARK = {
    fontFamily:'-apple-system,PingFang SC,sans-serif', fontSize:'13px',
    primaryColor:'#202024', primaryTextColor:'#e8e8ea', primaryBorderColor:'#34343a',
    lineColor:'#5a5a64', secondaryColor:'#26262b', tertiaryColor:'#202024',
    clusterBkg:'rgba(255,255,255,0.03)', clusterBorder:'#34343a',
    nodeBorder:'#34343a', edgeLabelBackground:'#161618',
    actorBkg:'#202024', actorBorder:'#34343a', actorTextColor:'#e8e8ea',
    signalColor:'#7a8494', signalTextColor:'#c4c4c9', labelBoxBkgColor:'#202024',
    loopTextColor:'#e8e8ea', noteBkgColor:'#3a3320', noteTextColor:'#e8d9a8'
};
function isDarkTheme(){
  /* 优先读 DOM 属性;首屏 initMermaid 早于主题 apply 时 DOM 尚无属性,回退读 localStorage */
  if(document.documentElement.hasAttribute('data-theme')) return document.documentElement.getAttribute('data-theme') !== 'light';
  try{ return localStorage.getItem('atlas-nav-theme') !== 'light'; }catch(e){ return true; }
}
function initMermaid(){
  mermaid.initialize({
    startOnLoad:false, theme:'base', securityLevel:'loose',
    flowchart:{ curve:'basis', useMaxWidth:false, htmlLabels:true, padding:22, nodeSpacing:70, rankSpacing:88, diagramPadding:24 },
    sequence:{ useMaxWidth:false, mirrorActors:true },
    themeVariables: isDarkTheme() ? MM_THEME_DARK : MM_THEME_LIGHT
  });
}
initMermaid();

const rendered = {};
let _mmSeq = 0;  /* mermaid 渲染唯一 id 计数器:避免重渲染时 svg id 冲突导致空白 */

function parseEdges(src){
  const edges=[];
  src.split('\n').forEach(line=>{
    const stripped=line.replace(/\[[^\]]*\]/g,'').replace(/\{[^}]*\}/g,'').replace(/\([^)]*\)/g,'');
    const tokens=stripped.split(/\s*(?:--+>|==+>|-\.[^>]*\.-*->|-\.->)\s*/).map(s=>s.trim()).filter(Boolean);
    const ids=tokens.map(t=>t.replace(/\|[^|]*\|/g,'').trim()).filter(t=>/^\w+$/.test(t));
    for(let i=0;i+1<ids.length;i++) edges.push({from:ids[i],to:ids[i+1]});
  });
  return edges;
}

async function renderPane(tid){
  if(rendered[tid]) return;
  if(tid==='qstour'){
    await renderQsTour(tid);
    rendered[tid]=true; EDGES[tid]=[];
    return;
  }
  if(typeof SVG_WALK_TIDS!=='undefined' && SVG_WALK_TIDS[tid]){
    renderSvgWalk(tid);
    rendered[tid]=true; EDGES[tid]=[];
    return;
  }
  if(STEPS_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    if(tid==='qsddl'||tid==='qsingest'||tid==='qsexport') renderStepsTabs(out, tid);
    else renderStepsSVG(out, tid);
    rendered[tid]=true; EDGES[tid]=[];
    out.style.transform='none';
    return;
  }
  if(typeof NEST_BLOCKS!=='undefined' && NEST_BLOCKS[tid]){
    await renderNested(tid);
    rendered[tid]=true; EDGES[tid]=[];
    return;
  }
  if(tid==='tourjoin'){
    _tourScenario='join';
    renderTourSVG(document.getElementById('mm-'+tid), tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    return;
  }
  if(tid==='glossary'){
    renderTableSVG(document.getElementById('mm-glossary'), GLOSSARY_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='compare'){
    renderTableSVG(document.getElementById('mm-compare'), COMPARE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='failure'){
    renderTableSVG(document.getElementById('mm-failure'), FAILURE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='bottleneck'){
    renderTableSVG(document.getElementById('mm-bottleneck'), BOTTLENECK_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='archcompare'){
    renderTableSVG(document.getElementById('mm-archcompare'), ARCHCOMPARE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='mvcompare'){
    renderTableSVG(document.getElementById('mm-mvcompare'), MVCOMPARE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optcompare'){
    renderTableSVG(document.getElementById('mm-optcompare'), OPTCOMPARE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='qlifevars'){
    renderTableSVG(document.getElementById('mm-qlifevars'), QLIFEVARS_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='qlifeterms'){
    renderTableSVG(document.getElementById('mm-qlifeterms'), QLIFETERMS_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optaxis'){
    renderTableSVG(document.getElementById('mm-optaxis'), OPTAXIS_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optgoal'){
    renderTableSVG(document.getElementById('mm-optgoal'), OPTGOAL_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optlifecycle'){
    renderTableSVG(document.getElementById('mm-optlifecycle'), OPTLIFECYCLE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optrelation'){
    renderTableSVG(document.getElementById('mm-optrelation'), OPTRELATION_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optgranularity'){
    renderTableSVG(document.getElementById('mm-optgranularity'), OPTGRANULARITY_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optphase'){
    renderTableSVG(document.getElementById('mm-optphase'), OPTPHASE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optoperator'){
    renderTableSVG(document.getElementById('mm-optoperator'), OPTOPERATOR_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optworkload'){
    renderTableSVG(document.getElementById('mm-optworkload'), OPTWORKLOAD_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='optobserve'){
    renderTableSVG(document.getElementById('mm-optobserve'), OPTOBSERVE_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='idxpano'){
    renderTableSVG(document.getElementById('mm-idxpano'), IDXPANO_SPEC);
    rendered[tid]=true; EDGES[tid]=[]; return;
  }
  if(tid==='archintegrated'||tid==='optarch'){
    const src=document.querySelector('.mmsrc[data-target="mm-'+tid+'"]');
    const out=document.getElementById('mm-'+tid);
    const text=src.textContent.trim();
    EDGES[tid]=[];
    try{
      const {svg}=await mermaid.render('svg-'+tid+'-'+(_mmSeq++), text);
      out.innerHTML=svg;
      rendered[tid]=true;
      wireNodes(tid,out);
      requestAnimationFrame(fitActive);
    }catch(e){
      out.innerHTML='<div class="empty"><div class="big">⚠</div><div>渲染失败: '+String(e&&e.message||e)+'</div></div>';
    }
    return;
  }
  if(FLOW_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderFlowSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=FLOW_SPECS[tid].edges.map(e=>({from:e[0],to:e[1]}));
    requestAnimationFrame(fitActive);
    return;
  }
  if(SEQ_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderSeqSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  if(DATA_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderDataSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  if(CASE_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderCaseSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  if(tid==='explaincmd'||tid==='qlife'||tid==='deployview'||tid==='dclprin'||tid==='optprin'||tid==='tsprin'||tid==='cpprin'){
    await renderMultiDiagrams(tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  if(TREE_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderTreeSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    out.style.transform='none';   // 树图用 tblsvg 宽度自适应,不走 fit 缩放(否则长树被压成细条)
    return;
  }
  if(MERGE_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderMergeSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  if(STRUCT_SPECS[tid]){
    const out=document.getElementById('mm-'+tid);
    renderStructSVG(out, tid);
    rendered[tid]=true;
    EDGES[tid]=[];
    requestAnimationFrame(fitActive);
    return;
  }
  const src=document.querySelector('.mmsrc[data-target="mm-'+tid+'"]');
  const out=document.getElementById('mm-'+tid);
  if(!src||!out) return;
  const text=src.textContent.trim();
  EDGES[tid]=parseEdges(text);
  try{
    const {svg}=await mermaid.render('svg-'+tid+'-'+(_mmSeq++),text);
    out.innerHTML=svg;
    rendered[tid]=true;
    wireNodes(tid,out);
    requestAnimationFrame(fitActive);   // 首次渲染后自动适应视口(大图避免看似空白)
  }catch(e){
    out.innerHTML='<div class="empty"><div class="big">⚠</div><div>渲染失败: '+String(e&&e.message||e)+'</div></div>';
  }
}

/* ── 嵌套主题:顶部块 tab + 每块内部垂直 TAB(通用,opttech/存储引擎 共用)── */
/* 通用渲染器:把任意已存在视图 tid 的内容渲染进给定容器 out。
   同步类型(FLOW/SEQ/DATA/CASE/MERGE/STRUCT/TREE + 表)直接渲;
   多图(idxarch/vecsearch/dataorg)与 raw-mermaid(idxchain)走 async mermaid。 */
/* 表格视图 tid → 取 spec 的惰性函数(spec const 定义在后面,调用时才求值,避开 TDZ)*/
function _tableSpecOf(tid){
  switch(tid){
    case 'optcompare': return typeof OPTCOMPARE_SPEC!=='undefined'?OPTCOMPARE_SPEC:null;
    case 'idxpano': return typeof IDXPANO_SPEC!=='undefined'?IDXPANO_SPEC:null;
    case 'mvcompare': return typeof MVCOMPARE_SPEC!=='undefined'?MVCOMPARE_SPEC:null;
    case 'glossary': return typeof GLOSSARY_SPEC!=='undefined'?GLOSSARY_SPEC:null;
    case 'compare': return typeof COMPARE_SPEC!=='undefined'?COMPARE_SPEC:null;
    case 'failure': return typeof FAILURE_SPEC!=='undefined'?FAILURE_SPEC:null;
    case 'bottleneck': return typeof BOTTLENECK_SPEC!=='undefined'?BOTTLENECK_SPEC:null;
    case 'archcompare': return typeof ARCHCOMPARE_SPEC!=='undefined'?ARCHCOMPARE_SPEC:null;
    case 'optgoal': return typeof OPTGOAL_SPEC!=='undefined'?OPTGOAL_SPEC:null;
    case 'optlifecycle': return typeof OPTLIFECYCLE_SPEC!=='undefined'?OPTLIFECYCLE_SPEC:null;
    case 'optgranularity': return typeof OPTGRANULARITY_SPEC!=='undefined'?OPTGRANULARITY_SPEC:null;
    case 'optoperator': return typeof OPTOPERATOR_SPEC!=='undefined'?OPTOPERATOR_SPEC:null;
    case 'optworkload': return typeof OPTWORKLOAD_SPEC!=='undefined'?OPTWORKLOAD_SPEC:null;
    case 'optobserve': return typeof OPTOBSERVE_SPEC!=='undefined'?OPTOBSERVE_SPEC:null;
    default: return null;
  }
}
async function renderInto(out, tid){
  // 表格视图
  const tsp=_tableSpecOf(tid);
  if(tsp){ renderTableSVG(out, tsp); return; }
  // 多图视图(左侧再一层竖 tab):idxarch/vecsearch/dataorg → 复用 NEST_MM 的图数组,纵向堆叠渲染
  if(typeof NEST_MM!=='undefined' && NEST_MM[tid]){
    const arr=NEST_MM[tid]; let html='';
    arr.forEach(function(pair,i){ html+='<div class="do-h" style="margin:'+(i?'22px':'2px')+' 0 10px">'+pair[0]+'</div><div class="nest-mm" id="ni-'+tid+'-'+i+'"></div>'; });
    out.innerHTML=html;
    for(let i=0;i<arr.length;i++){
      try{ const r=await mermaid.render('svg-ni-'+tid+'-'+i+'-'+(_mmSeq++), arr[i][1]);
        const c=out.querySelector('#ni-'+tid+'-'+i); if(c){ c.innerHTML=r.svg; }
      }catch(e){ const c=out.querySelector('#ni-'+tid+'-'+i); if(c) c.innerHTML='<div class="empty"><div class="big">⚠</div><div>渲染失败</div></div>'; }
    }
    return;
  }
  // raw-mermaid 单图(idxchain 等):从隐藏 .mmsrc 读取源码
  if(typeof RAW_MM!=='undefined' && RAW_MM[tid]){
    try{ const r=await mermaid.render('svg-raw-'+tid+'-'+(_mmSeq++), RAW_MM[tid]); out.innerHTML=r.svg;
    }catch(e){ out.innerHTML='<div class="empty"><div class="big">⚠</div><div>渲染失败</div></div>'; }
    return;
  }
  if(typeof FLOW_SPECS!=='undefined' && FLOW_SPECS[tid]){ renderFlowSVG(out, tid); return; }
  if(typeof SEQ_SPECS!=='undefined' && SEQ_SPECS[tid]){ renderSeqSVG(out, tid); return; }
  if(typeof DATA_SPECS!=='undefined' && DATA_SPECS[tid]){ renderDataSVG(out, tid); return; }
  if(typeof CASE_SPECS!=='undefined' && CASE_SPECS[tid]){ renderCaseSVG(out, tid); return; }
  if(typeof MERGE_SPECS!=='undefined' && MERGE_SPECS[tid]){ renderMergeSVG(out, tid); return; }
  if(typeof STRUCT_SPECS!=='undefined' && STRUCT_SPECS[tid]){ renderStructSVG(out, tid); return; }
  if(typeof TREE_SPECS!=='undefined' && TREE_SPECS[tid]){ renderTreeSVG(out, tid); out.style.transform='none'; return; }
  out.innerHTML='<div class="empty"><div class="big">▤</div><div>暂无内容</div></div>';
}
/* 每个顶部块 → 内部子视图列表:[显示名, 已存在的视图 tid] */
const NEST_BLOCKS={
  // 优化技术(4 块;Pipeline 已移到执行引擎)
  optq:{title:'查询优化器', subs:[["优化流程","optflow"],["RBO/CBO/HBO 对比","optcompare"],["优化时序","optseq"],["Memo 结构","memotree"],["分布式 Join 策略","joinflow"]]},
  optrf:{title:'Runtime Filter', subs:[["RF 全景","rfflow"],["RF 时序","rfseq"],["Filter 结构","rfstruct"]]},
  opttopn:{title:'TOPN', subs:[["TOPN 全景","topnflow"],["TOPN 时序","topnseq"],["堆结构","topnstruct"]]},
  optstat:{title:'统计信息', subs:[["统计全景","statflow"],["统计时序","statseq"],["表统计","stattbl"],["列统计","statcol"]]},
  // 存储引擎(6 块)
  steOlap:{title:'内表存储', subs:[["OLAP 扫描","olapflow"],["OLAP 时序","olapseq"],["列存结构","olapdata"],["存储+索引结构","integstruct"],["聚合合并","aggmerge"]]},
  steFmt:{title:'存储格式', subs:[["存储格式全景","fmtflow"],["湖仓层次关系","lakerel"],["格式并行对比","fmtcompare"],["端到端时序","seq"]]},
  steExt:{title:'外表读取', subs:[["FE 查询规划","feflow"],["BE 扫描执行","beflow"],["Hive ORC 读取","hiveorcflow"],["Hudi 读取","hudiflow"],["Iceberg 读取","icebergflow"]]},
  steIdx:{title:'索引与检索', subs:[["索引体系架构","idxarch"],["向量检索与倒排","vecsearch"],["索引全景透视","idxpano"],["索引过滤链路","idxchain"],["索引结构","anntree"]]},
  steMv:{title:'物化视图', subs:[["MV 全景","mvflow"],["同步/异步对比","mvcompare"],["MV 时序","mvseq"],["改写结构","mvtree"],["SPJG 原理","mvspjg"],["适用场景","mvscene"],["精确/近似去重","dedupflow"]]},
  steOrg:{title:'数据组织', subs:[["总体层级","dataorg0"],["FE↔BE 对应","dataorg1"],["版本链 & Compaction","dataorg2"],["Segment 内部","dataorg3"]]},
  // 优化原理·原理概览:6 张透视表垂直切换(保留 优化架构/优化总表 独立 tab)
  optpersp:{title:'原理概览', subs:[["资源消耗","optgoal"],["生命周期","optlifecycle"],["数据粒度","optgranularity"],["执行算子","optoperator"],["工作负载","optworkload"],["可观测性","optobserve"]]},
};
/* 子视图 tid → 顶部块 tid(供跨视图下钻链路 openInTab 定位到嵌套的正确位置)*/
const _SUB2TOP={};
Object.keys(NEST_BLOCKS).forEach(function(top){ NEST_BLOCKS[top].subs.forEach(function(s){ _SUB2TOP[s[1]]=top; }); });
/* 渲染一个顶部块:左侧垂直 nav(子视图)+ 右侧 stage,首项即时渲染,其余点击时懒渲染 */
async function renderNested(tid){
  const blk=NEST_BLOCKS[tid]; const out=document.getElementById('mm-'+tid);
  if(!blk||!out) return;
  let navs='', secs='';
  blk.subs.forEach(function(s,si){
    navs+='<button class="do-nav'+(si===0?' active':'')+'" data-idx="'+si+'" data-sub="'+s[1]+'">'
        +'<span class="do-nav-n">'+(si+1)+'</span><span class="do-nav-t">'+s[0]+'</span></button>';
    secs+='<div class="do-sec'+(si===0?' active':'')+'" data-idx="'+si+'" data-sub="'+s[1]+'">'
        +'<h3 class="do-h">'+s[0]+'</h3><div class="do-out" id="optt-out-'+tid+'-'+si+'"></div></div>';
  });
  out.innerHTML='<div class="do-paneflow"><div class="dataorg-wrap"><div class="do-nav-col"><div class="do-nav-sticky">'+navs+'</div></div>'
    +'<div class="do-stage">'+secs+'</div></div></div>';
  const done={};
  const draw=function(si){ if(done[si]) return; const c=out.querySelector('#optt-out-'+tid+'-'+si); if(c){ done[si]=true; renderInto(c, blk.subs[si][1]); } };
  draw(0);
  const nv=[].slice.call(out.querySelectorAll('.do-nav')), sc=[].slice.call(out.querySelectorAll('.do-sec'));
  nv.forEach(function(n){ n.addEventListener('click',function(){ var i=n.getAttribute('data-idx');
    nv.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);});
    sc.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);});
    draw(parseInt(i,10)); }); });
}

/* 数据组织架构 — 四张 mermaid 图纵向堆叠;图一节点 ID = 下钻 key,可下钻真实源码 */
async function renderMultiDiagrams(tid){
  const pane=document.getElementById('pane-'+tid);
  if(!pane) return;
  const blocks=pane.querySelectorAll('.do-mm');
  for(const src of blocks){
    const idx=src.getAttribute('data-idx');
    const out=pane.querySelector('.do-out#do-out-'+idx) || pane.querySelectorAll('.do-out')[idx];
    if(!out) continue;
    const text=src.textContent.trim();
    try{
      const {svg}=await mermaid.render('svg-'+tid+'-'+idx+'-'+(_mmSeq++), text);
      out.innerHTML=svg;
    }catch(e){
      out.innerHTML='<div class="empty"><div class="big">⚠</div><div>渲染失败: '+String(e&&e.message||e)+'</div></div>';
    }
  }
  // 左侧垂直 tab 切换:点 nav → 高亮 + 显示对应图(在本 pane 内 scope)
  const navs=[].slice.call(pane.querySelectorAll('.do-nav'));
  const secs=[].slice.call(pane.querySelectorAll('.do-sec'));
  navs.forEach(function(nav){
    nav.addEventListener('click',function(){
      const i=nav.getAttribute('data-idx');
      navs.forEach(function(n){n.classList.toggle('active', n.getAttribute('data-idx')===i);});
      secs.forEach(function(s){s.classList.toggle('active', s.getAttribute('data-idx')===i);});
    });
  });
}

/* 左侧垂直 TAB 切换:点 nav → 高亮 nav + 显示对应 sec(pane 内 scope)。
   renderMultiDiagrams 尾部同款逻辑,抽出供 SVG-walk 复用。 */
function wireDoNav(pane){
  const navs=[].slice.call(pane.querySelectorAll('.do-nav'));
  const secs=[].slice.call(pane.querySelectorAll('.do-sec'));
  navs.forEach(function(nav){
    nav.addEventListener('click',function(){
      const i=nav.getAttribute('data-idx');
      navs.forEach(function(n){n.classList.toggle('active', n.getAttribute('data-idx')===i);});
      secs.forEach(function(s){s.classList.toggle('active', s.getAttribute('data-idx')===i);});
    });
  });
}

/* design 原理图走查 — pane 内容(base64 <img> + 左垂直 TAB)已在生成期静态注入,
   此处只需绑定 nav 切换(无 async mermaid)。 */
function renderSvgWalk(tid){
  const pane=document.getElementById('pane-'+tid);
  if(!pane || pane.dataset.wired) return;
  // 若该走查末尾含一个「要点」表(如 deploywalk 的部署形态对比),渲染进内嵌容器
  const tblMap={deploywalk:['archcompare', (typeof ARCHCOMPARE_SPEC!=='undefined'?ARCHCOMPARE_SPEC:null)]};
  const t=tblMap[tid];
  if(t && t[1]){ const out=document.getElementById('svgwalk-tbl-'+t[0]); if(out) renderTableSVG(out, t[1]); }
  wireDoNav(pane);
  pane.dataset.wired='1';
}

/* 快速开始「上手总览」复合视图:总览 SVG 置顶 + 5 步选择器 + 内容区。
   点击某步 → 用其原渲染器(renderStepsSVG/renderStepsTabs/renderTourSVG)渲进内容区。默认第一步。 */
const _QSTOUR_STEPS=[
  {tid:'qssetup', n:'1', label:'环境搭建', kind:'steps',     box:[40,96,184,96]},
  {tid:'qsddl',   n:'2', label:'建库建表', kind:'stepstabs', box:[256,96,184,96]},
  {tid:'qsingest',n:'3', label:'数据写入', kind:'stepstabs', box:[472,96,184,96]},
  {tid:'tourjoin',n:'4', label:'查询分析', kind:'tour',      box:[688,96,184,96]},
  {tid:'qsexport',n:'5', label:'数据导出', kind:'stepstabs', box:[888,96,152,96]},
];
const _QSTOUR_VB=[1080,440];   // 总览 SVG viewBox,用于热区百分比定位
async function renderQsTour(tid){
  const host=document.getElementById('mm-'+tid);
  if(!host || host.dataset.built) return;
  const VW=_QSTOUR_VB[0], VH=_QSTOUR_VB[1];
  const hots=_QSTOUR_STEPS.map(function(s){
    const b=s.box;
    return '<button class="qst-hot" data-step="'+s.tid+'" title="'+s.label+'" '+
      'style="left:'+(b[0]/VW*100).toFixed(3)+'%;top:'+(b[1]/VH*100).toFixed(3)+'%;'+
      'width:'+(b[2]/VW*100).toFixed(3)+'%;height:'+(b[3]/VH*100).toFixed(3)+'%"></button>';
  }).join('');
  host.innerHTML=
    '<div class="qst-wrap">'+
      '<div class="qst-overview"><img class="svg-walk-img" src="data:image/svg+xml;base64,'+QSTOUR_OVERVIEW_B64+'" alt="上手路线总览" draggable="false"/>'+hots+'</div>'+
      '<div class="qst-content" id="qst-content"></div>'+
    '</div>';
  host.style.transform='none';
  const content=host.querySelector('#qst-content');
  const hotEls=[].slice.call(host.querySelectorAll('.qst-hot'));
  function show(stid){
    const step=_QSTOUR_STEPS.find(function(x){return x.tid===stid;});
    hotEls.forEach(function(b){b.classList.toggle('active', b.getAttribute('data-step')===stid);});
    content.innerHTML='';
    if(step.kind==='steps') renderStepsSVG(content, stid);
    else if(step.kind==='stepstabs') renderStepsTabs(content, stid);
    else if(step.kind==='tour') renderTourSVG(content, stid);
    content.style.transform='none';
  }
  hotEls.forEach(function(b){ b.addEventListener('click',function(){ show(b.getAttribute('data-step')); }); });
  show(_QSTOUR_STEPS[0].tid);   // 默认第一步
  host.dataset.built='1';
}



/* 通用手写 SVG 流程引擎 — 阶段带(横向) × 步骤(纵向网格) + 正交走线 + 序号。
   spec: { accent, stages:[{title, nodes:[{key,t,s} | {ghost,t,s}]}], edges:[[fromKey,toKey,label?,dash?]] } */
const FLOW_SPECS={
  feflow:{ accent:'#38bdf8', stages:[
    {title:'① 接入 & 路由', nodes:[{key:'StmtExec',t:'StmtExecutor.execute',s:'StmtExecutor.java:481'},{key:'queryRetry',t:'queryRetry',s:'StmtExecutor.java:491'}]},
    {title:'② Nereids 优化 (CBO)', nodes:[{key:'Planner',t:'NereidsPlanner.plan',s:'NereidsPlanner.java:138'},{key:'planWithLock',t:'planWithLock',s:'analyze→rewrite→optimize'},{key:'distribute',t:'distribute',s:'NereidsPlanner.java:678'},{key:'splitFragments',t:'splitFragments',s:'NereidsPlanner.java:579'}]},
    {title:'③ 物理翻译 & 切 fragment', nodes:[{key:'translatePlan',t:'PhysicalPlanTranslator',s:'translatePlan:297'},{key:'visitDistribute',t:'visitPhysicalDistribute',s:'按 exchange 切 fragment:337'}]},
    {title:'④ Scan 规划 & Split', nodes:[{key:'doInit',t:'FileQueryScanNode',s:'doInitialize:140'},{key:'getSplits',t:'HiveScanNode.getSplits',s:'HiveScanNode.java:261'},{key:'getFileSplit',t:'getFileSplitByPartitions',s:':392'},{key:'hmsCache',t:'HiveMetaStoreCache',s:'getFilesByPartitions:658'}]},
    {title:'⑤ Split 分配 (一致性哈希)', nodes:[{key:'splitAssign',t:'computeSplitAssignment',s:'FileQueryScanNode.java:389'},{key:'backendPolicy',t:'FederationBackendPolicy',s:'consistentHash+murmur3_128:224'},{key:'splitToScanRange',t:'splitToScanRange',s:'→ TScanRangeLocations:439'}]},
    {title:'⑥ 调度下发', nodes:[{key:'Coord',t:'Coordinator.exec',s:'computeFragmentExecParams:683'},{key:'sendPipe',t:'sendPipelineCtx',s:'组 TPipelineFragmentParams:814'},{key:'thrift',t:'execPlanFragmentsAsync',s:'BackendServiceProxy:199'}]}
  ], edges:[['StmtExec','queryRetry'],['queryRetry','Planner'],['Planner','planWithLock'],['planWithLock','distribute'],['distribute','splitFragments'],['splitFragments','translatePlan'],['translatePlan','visitDistribute'],['visitDistribute','doInit'],['doInit','getSplits'],['getSplits','getFileSplit'],['getFileSplit','hmsCache'],['hmsCache','splitAssign'],['splitAssign','backendPolicy'],['backendPolicy','splitToScanRange'],['splitToScanRange','Coord'],['Coord','sendPipe'],['sendPipe','thrift']] },
  beflow:{ accent:'#2dd4a7', stages:[
    {title:'① RPC 接入', nodes:[{key:'exec_rpc',t:'exec_plan_fragment',s:'internal_service.cpp:319'},{key:'exec_impl',t:'_exec_plan_fragment_impl',s:':541'},{key:'fragMgr',t:'FragmentMgr',s:'fragment_mgr.cpp:610'}]},
    {title:'② Pipeline 调度', nodes:[{key:'pipeCtx',t:'PipelineFragmentContext',s:'prepare:256'},{key:'pipeTask',t:'PipelineTask::execute',s:'pipeline_task.cpp:386'},{key:'scanSched',t:'ScannerScheduler',s:'_scanner_scan:127'}]},
    {title:'③ 谓词下推 & 优化', nodes:[{key:'procConj',t:'_process_conjuncts',s:'按 slot 拆谓词:330'},{key:'rfPrune',t:'RF 分区裁剪',s:'_process_runtime_filters_partition_prune:245'},{key:'countPush',t:'count 元数据下推',s:'COUNT_FROM_METADATA:1051'}]},
    {title:'④ 格式分派', nodes:[{key:'getBlock',t:'FileScanner::get_block',s:'file_scanner.cpp:408'},{key:'getBlockWrapped',t:'_get_block_wrapped',s:':437'},{key:'getNextReader',t:'_get_next_reader (switch)',s:':991'},{key:'initOrc',t:'_init_orc_reader',s:':1077'}]},
    {title:'⑤ ORC 向量化读取', nodes:[{key:'orcInit',t:'OrcReader::init_reader',s:'vorc_reader.cpp:431'},{key:'orcGetNext',t:'get_next_block',s:':2266'},{key:'lateRf',t:'延迟到达 RF',s:'_process_late_arrival_conjuncts:361'}]},
    {title:'⑥ 组装输出 Block', nodes:[{key:'fillPath',t:'_fill_columns_from_path',s:'分区列:627'},{key:'fillMiss',t:'_fill_missing_columns',s:'缺失列:666'},{key:'convertOut',t:'_convert_to_output_block',s:'类型转换/字典解码:724'},{key:'doProj',t:'Scanner::_do_projections',s:'投影输出:151'}]}
  ], edges:[['exec_rpc','exec_impl'],['exec_impl','fragMgr'],['fragMgr','pipeCtx'],['pipeCtx','pipeTask'],['pipeTask','scanSched'],['scanSched','procConj'],['procConj','rfPrune'],['rfPrune','countPush'],['countPush','getBlock'],['getBlock','getBlockWrapped'],['getBlockWrapped','getNextReader'],['getNextReader','initOrc'],['initOrc','orcInit'],['orcInit','orcGetNext'],['orcGetNext','lateRf'],['lateRf','fillPath'],['fillPath','fillMiss'],['fillMiss','convertOut'],['convertOut','doProj']] },
  writeflow:{ accent:'#f59e0b', stages:[
    {title:'① RPC 接入', nodes:[{key:'loadRpc',t:'tablet_writer_add_block',s:'internal_service.cpp:489'},{key:'loadChanMgr',t:'LoadChannelMgr::add_batch',s:'load_channel_mgr.cpp:151'},{key:'loadChan',t:'LoadChannel::add_batch',s:'load_channel.cpp:177'}]},
    {title:'② 内存写入', nodes:[{key:'deltaWrite',t:'DeltaWriter::write',s:'delta_writer.cpp:143'},{key:'memInsert',t:'MemTable::insert',s:'memtable.cpp:197'}]},
    {title:'③ 异步 flush', nodes:[{key:'memFlush',t:'MemtableFlushExecutor',s:'_flush_memtable:221'},{key:'memToBlock',t:'MemTable::to_block',s:'memtable.cpp:742'}]},
    {title:'④ 落盘 rowset', nodes:[{key:'segWrite',t:'SegmentWriter::append_block',s:'segment_writer.cpp:701'},{key:'rowsetClose',t:'BetaRowsetWriter::close',s:'beta_rowset_writer.cpp:131'}]}
  ], edges:[['loadRpc','loadChanMgr'],['loadChanMgr','loadChan'],['loadChan','deltaWrite'],['deltaWrite','memInsert'],['memInsert','memFlush'],['memFlush','memToBlock'],['memToBlock','segWrite'],['segWrite','rowsetClose']] },
  olapflow:{ accent:'#38bdf8', stages:[
    {title:'① FE tablet 定位', nodes:[{key:'olapScanNode',t:'OlapScanNode.init',s:'OlapScanNode.java:348'},{key:'computePartition',t:'computePartitionInfo',s:'分区裁剪:730'},{key:'computeTablet',t:'computeTabletInfo',s:'副本选择:887'},{key:'olapAddRange',t:'addScanRangeLocations',s:'→ TPaloScanRange:472'}]},
    {title:'② RPC + Pipeline', nodes:[{key:'exec_rpc',t:'exec_plan_fragment',s:'internal_service.cpp:319'},{key:'pipeTask',t:'PipelineTask::execute',s:'pipeline_task.cpp:386'},{key:'scanSched',t:'ScannerScheduler',s:'_scanner_scan:127'}]},
    {title:'③ TabletReader 合并', nodes:[{key:'olapGetBlock',t:'OlapScanner',s:'_get_block_impl:578'},{key:'olapInitReader',t:'_init_tablet_reader_params',s:'olap_scanner.cpp:281'},{key:'blockReader',t:'BlockReader',s:'next_block_with_aggregation:65'}]},
    {title:'④ Segment 向量化', nodes:[{key:'segIter',t:'SegmentIterator::next_batch',s:'segment_iterator.cpp:2380'},{key:'segIterInternal',t:'_next_batch_internal',s:':2469 两阶段谓词'},{key:'readByRowids',t:'_read_columns_by_rowids',s:'延迟物化:2336'}]}
  ], edges:[['olapScanNode','computePartition'],['computePartition','computeTablet'],['computeTablet','olapAddRange'],['olapAddRange','exec_rpc'],['exec_rpc','pipeTask'],['pipeTask','scanSched'],['scanSched','olapGetBlock'],['olapGetBlock','olapInitReader'],['olapInitReader','blockReader'],['blockReader','segIter'],['segIter','segIterInternal'],['segIterInternal','readByRowids']] },
  cloudflow:{ accent:'#38bdf8', stages:[
    {title:'FE 层 (SQL 元数据)', nodes:[{key:'cloudEnv',t:'CloudEnv',s:'cloud/catalog/CloudEnv.java:62'},{key:'msProxy',t:'MetaServiceProxy',s:'cloud/rpc:40'}]},
    {title:'Meta Service (数据级元数据)', nodes:[{key:'metaService',t:'MetaServiceImpl::get_rowset',s:'meta_service.cpp:3171'}]},
    {title:'Compute Node (无状态 BE)', nodes:[{key:'cloudEngine',t:'CloudStorageEngine',s:'cloud_storage_engine.h:55'},{key:'cloudSyncRowsets',t:'CloudTablet::sync_rowsets',s:'cloud_tablet.cpp:304'},{key:'cloudMetaMgr',t:'CloudMetaMgr',s:'sync_tablet_rowsets:479'},{key:'cachedReader',t:'CachedRemoteFileReader',s:'read_at_impl:285'}]},
    {title:'缓存 & 预热', nodes:[{key:'fileCacheFactory',t:'FileCacheFactory',s:'block_file_cache_factory.h:46'},{key:'warmUp',t:'CloudWarmUpManager',s:'cloud_warm_up_manager.cpp'}]}
  ], edges:[['cloudEnv','msProxy'],['msProxy','metaService'],['metaService','cloudEngine'],['cloudEngine','cloudSyncRowsets'],['cloudSyncRowsets','cloudMetaMgr'],['cloudMetaMgr','cachedReader'],['cachedReader','fileCacheFactory'],['fileCacheFactory','warmUp']] },
  cloudwriteflow:{ accent:'#38bdf8', stages:[
    {title:'① 写本地临时段', nodes:[
      {key:'clWrite',t:'CloudRowsetWriter.init',s:'segment 写本地 tmp:42'}]},
    {title:'② 上传共享存储', nodes:[
      {key:'clUpload',t:'FileWriter → 对象存储',s:'按 StorageResource 上传 S3/HDFS'}]},
    {title:'③ 提交元数据到 MetaService', nodes:[
      {key:'clCommit',t:'CloudMetaMgr.commit_rowset',s:'prepare→commit RPC:1320'}]},
    {title:'④ MOW delete bitmap', nodes:[
      {key:'clBitmap',t:'update_delete_bitmap',s:'拿锁+RPC 提交:1660'}]}
  ], edges:[['clWrite','clUpload'],['clUpload','clCommit'],['clCommit','clBitmap']] },
  vecflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① 列式数据单元', nodes:[
      {key:'vecBlock',t:'Block(列式容器)',s:'core/block.h:71'},
      {key:'vecColumn',t:'ColumnVector<T>',s:'定宽 PODArray:71'},
      {key:'vecPod',t:'PODArray',s:'连续+padding 底座:307'}]},
    {title:'② 向量化表达式', nodes:[
      {key:'vecExpr',t:'VExpr::execute',s:'整块求值追加列:138'},
      {key:'vecFnCall',t:'VectorizedFnCall',s:'dispatch 函数:47'},
      {key:'vecFunction',t:'IFunction::execute_impl',s:'列级批量算:375'}]},
    {title:'③ 向量化算子', nodes:[
      {key:'vecOperator',t:'OperatorXBase',s:'pull/push/sink 契约:865'},
      {key:'vecHashJoin',t:'HashJoinProbe find_batch',s:'批量探测:129'},
      {key:'vecAgg',t:'AggSink 批量入表',s:'_emplace_into_hash_table:131'}]},
    {title:'④ 批量过滤 + SIMD', nodes:[
      {key:'vecFilter',t:'Block::filter_block',s:'Filter 批量裁行:804'},
      {key:'vecSimd',t:'SIMD 内核',s:'count_zero_num 等:130'}]}
  ], edges:[['vecBlock','vecColumn'],['vecColumn','vecPod'],['vecPod','vecExpr'],['vecExpr','vecFnCall'],['vecFnCall','vecFunction'],['vecFunction','vecOperator'],['vecOperator','vecHashJoin'],['vecOperator','vecAgg'],['vecHashJoin','vecFilter'],['vecAgg','vecFilter'],['vecFilter','vecSimd']] },
  joinflow:{ accent:'#e8b93d', stages:[
    {title:'① 请求候选分布', nodes:[
      {key:'djRequest',t:'RequestPropertyDeriver',s:'提 shuffle+broadcast 候选:225'}]},
    {title:'② 代价择优 + 策略分派', nodes:[
      {key:'djCost',t:'CostModel.visitDistribute',s:'broadcast vs shuffle 代价:317'},
      {key:'djRegulator',t:'ChildrenPropertiesRegulator',s:'策略中枢分派:355'}]},
    {title:'③ 四种策略', nodes:[
      {key:'djColocate',t:'Colocate(免交换)',s:'couldColocateJoin:302'},
      {key:'djBucket',t:'Bucket Shuffle(单侧)',s:'shouldBucketShuffleJoin:248'},
      {key:'djTrans',t:'ShuffleType→TPartitionType',s:'toDataPartition:3088'}]},
    {title:'④ BE 执行交换', nodes:[
      {key:'djExchange',t:'ExchangeSinkOperatorX::sink',s:'广播/分区分派:375'},
      {key:'djPartitioner',t:'Crc32HashPartitioner',s:'hash%n 定 channel:31'}]}
  ], edges:[['djRequest','djCost'],['djCost','djRegulator'],['djRegulator','djColocate'],['djRegulator','djBucket'],['djRegulator','djTrans'],['djColocate','djExchange'],['djBucket','djExchange'],['djTrans','djExchange'],['djExchange','djPartitioner']] },
  invflow:{ accent:'#c084fc', stages:[
    {title:'① 构建期(随 segment)', nodes:[
      {key:'iiWriter',t:'InvertedIndexColumnWriter',s:'add_values 逐行写:361'},
      {key:'iiAnalyzer',t:'分词器工厂',s:'standard/IK/ICU:133'}]},
    {title:'② on-disk 布局', nodes:[
      {key:'iiFile',t:'IndexFileWriter V1/V2',s:'_idx 文件布局:84'}]},
    {title:'③ 查询期检索', nodes:[
      {key:'iiReader',t:'FullTextIndexReader::query',s:'match_index_search:292'}]},
    {title:'④ 扫描期谓词下推', nodes:[
      {key:'iiMatch',t:'_apply_inverted_index',s:'MATCH→行 bitmap 裁行:1281'}]}
  ], edges:[['iiWriter','iiAnalyzer'],['iiAnalyzer','iiFile'],['iiFile','iiReader'],['iiReader','iiMatch']] },
  dedupflow:{ accent:'#34d399', stages:[
    {title:'① count(distinct) 改写', nodes:[
      {key:'cntDistinct',t:'CountDistinctRewrite',s:'→bitmap_union_count/hll:41'}]},
    {title:'② 两种去重值', nodes:[
      {key:'bmValue',t:'BitmapValue(精确)',s:'4 态自适应 Roaring:873'},
      {key:'hllValue',t:'HyperLogLog(近似)',s:'16K 寄存器±1%:79'}]},
    {title:'③ 聚合函数', nodes:[
      {key:'bmAgg',t:'bitmap_union',s:'res|=data 精确并:256'},
      {key:'hllAgg',t:'hll_union_agg',s:'寄存器 SIMD 合并:94'}]},
    {title:'④ AGG 模型预聚合', nodes:[
      {key:'aggReader',t:'BlockReader 列合并',s:'导入/compaction 预 union:178'}]}
  ], edges:[['cntDistinct','bmValue'],['cntDistinct','hllValue'],['bmValue','bmAgg'],['hllValue','hllAgg'],['bmAgg','aggReader'],['hllAgg','aggReader']] },
  fmtflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① 格式分派', nodes:[
      {key:'getNextReader',t:'FileScanner 按格式 switch',s:'_get_next_reader:991'}]},
    {title:'② 外表格式 reader(谓词下推)', nodes:[
      {key:'fmtOrcSarg',t:'ORC · SearchArgument',s:'_init_search_argument:1065'},
      {key:'fmtParquetRG',t:'Parquet · RowGroup 过滤',s:'min/max+bloom:1160'},
      {key:'fmtHudiJni',t:'Hudi · COW原生/MOR JNI',s:'hudi_jni_reader:54'},
      {key:'fmtIcebergDelete',t:'Iceberg · delete 应用',s:'init_row_filters:120'}]},
    {title:'③ 内表列存 V2(自有格式)', nodes:[
      {key:'fmtSegFooter',t:'Segment footer 解析',s:'_parse_footer:393'},
      {key:'fmtColReader',t:'ColumnReader 三索引',s:'zonemap/bloom/ordinal:353'},
      {key:'fmtPageEnc',t:'页编码族',s:'dict/bitshuffle/RLE/FOR'}]}
  ], edges:[['getNextReader','fmtOrcSarg'],['getNextReader','fmtParquetRG'],['getNextReader','fmtHudiJni'],['getNextReader','fmtIcebergDelete'],['getNextReader','fmtSegFooter'],['fmtSegFooter','fmtColReader'],['fmtColReader','fmtPageEnc']] },
  aiflow:{ accent:'var(--cv-ink)', stages:[
    {title:'FE · 向量 TopN 下推', nodes:[{key:'vecTopnPush',t:'PushDownVectorTopN',s:'IntoOlapScan.java:53'},{key:'aiFunc',t:'AI/LLM 函数簇',s:'functions/ai (12 个)'}]},
    {title:'BE · 扫描层 ANN 应用', nodes:[{key:'annApply',t:'_apply_ann_topn_predicate',s:'segment_iterator.cpp:784'},{key:'annHasIndex',t:'_column_has_ann_index',s:':777'}]},
    {title:'ANN 索引实现', nodes:[{key:'annTopnRt',t:'AnnTopNRuntime',s:'evaluate_vector_ann_search:199'},{key:'annReader',t:'AnnIndexReader::query',s:'ann_index_reader.cpp:97'},{key:'faissIndex',t:'FaissVectorIndex(HNSW/IVF)',s:'ann_topn_search:428'}]}
  ], edges:[['vecTopnPush','annApply'],['aiFunc','annApply'],['annApply','annHasIndex'],['annHasIndex','annTopnRt'],['annTopnRt','annReader'],['annReader','faissIndex']] },
  threadflow:{ accent:'#2dd4a7', stages:[
    {title:'① FE 协调器 · brpc 下发', nodes:[{key:'fragMgr',t:'FragmentMgr',s:'exec_plan_fragment / 超时取消'}]},
    {title:'② 构建 Pipeline DAG(常驻管理线程)', nodes:[{key:'plPipeCtx',t:'PipelineFragmentContext',s:'建 Pipeline DAG'}]},
    {title:'③ 执行池 · HybridTaskScheduler(p_<wg>)', nodes:[{key:'plPipeTask',t:'PipelineTask.execute()',s:'主循环:get_block→sink'},{key:'thrHybrid',t:'blocking / simple pool',s:'阻塞 vs 非阻塞算子'}]},
    {title:'④ 扫描池 · 与计算解耦(ls_<wg>/rs_<wg>)', nodes:[{key:'thrScanPool',t:'ScannerScheduler',s:'异步填 _completed_tasks 队列'},{key:'segIterInternal',t:'SegmentIterator→PageIO',s:'StoragePageCache'}]},
    {title:'⑤ Sink · 跨 Pipeline 唤醒 / 跨机', nodes:[{key:'vecHashJoin',t:'HashJoinBuildSink',s:'Dependency.set_ready 唤醒 Probe'},{key:'djPartitioner',t:'ExchangeSink → brpc',s:'streaming 到对端 Source'}]},
    {title:'⑥ 内存超限 · 溢写降级', nodes:[{key:'wgMgrBe',t:'WorkloadGroupMgr',s:'add_paused_query 反压'},{key:'memReclaim',t:'Spill 线程写临时文件',s:'PartitionedAgg/HashJoin 落盘'}]}
  ], edges:[
    ['fragMgr','plPipeCtx','创建'],
    ['plPipeCtx','plPipeTask','提交任务'],
    ['plPipeTask','thrHybrid'],
    ['plPipeTask','thrScanPool','驱动 Scan'],
    ['thrScanPool','segIterInternal'],
    ['segIterInternal','plPipeTask','填 Block 队列',true],
    ['plPipeTask','vecHashJoin','_sink->sink'],
    ['vecHashJoin','djPartitioner'],
    ['plPipeTask','wgMgrBe','reserve 失败',true],
    ['wgMgrBe','memReclaim']
  ] },
  memflow:{ accent:'#f0abfc', stages:[
    {title:'线程上下文归属', nodes:[{key:'memThreadCtx',t:'ThreadContext',s:'SCOPED_ATTACH_TASK:162'},{key:'memThreadMgr',t:'ThreadMemTrackerMgr',s:'consume:51'}]},
    {title:'树形 Tracker', nodes:[{key:'memTracker',t:'MemTrackerLimiter',s:'mem_tracker_limiter.h:71'}]},
    {title:'进程仲裁 & GC', nodes:[{key:'memArbitrator',t:'GlobalMemoryArbitrator',s:'global_memory_arbitrator.h:26'},{key:'memReclaim',t:'MemoryReclamation',s:'revoke_tasks_memory:35'}]},
    {title:'导入反压', nodes:[{key:'memLoadLimiter',t:'MemTableMemoryLimiter',s:'handle_memtable_flush:124'}]}
  ], edges:[['memThreadCtx','memThreadMgr'],['memThreadMgr','memTracker'],['memTracker','memArbitrator'],['memArbitrator','memReclaim'],['memLoadLimiter','memArbitrator']] },
  jeflow:{ accent:'#f0abfc', stages:[
    {title:'① 入口 · 计算 size class', nodes:[
      {key:'je_req',t:'malloc(size) / mallocx',s:'src/jemalloc.c imalloc_fastpath'},
      {key:'je_sz',t:'sz_size2index',s:'size→size class index(39 小类)'}]},
    {title:'② tcache 线程缓存 · 无锁快路径', nodes:[
      {key:'je_tcs',t:'small bin(≤14KB)',s:'cache_bin_alloc 命中 O(1) 无锁'},
      {key:'je_tcl',t:'large bin(16–32KB)',s:'cache_bin_alloc 命中直接返回'}]},
    {title:'③ miss 慢路径', nodes:[
      {key:'je_fill',t:'tcache_alloc_small_hard',s:'批量填充(加 bin shard 锁)'},
      {key:'je_large',t:'large_malloc',s:'一次只分配一个,不批量'}]},
    {title:'④ Arena · 多竞技场分散锁', nodes:[
      {key:'je_arena',t:'arena_t',s:'线程轮询绑定,锁从全局分散'},
      {key:'je_bin',t:'bins_t[SC_NBINS] · bin shard',s:'线程绑定特定 shard 再降竞争'},
      {key:'je_slab',t:'slab + bitmap',s:'连续页组等分槽位,减内部碎片'}]},
    {title:'⑤ 页分配 pa_shard · HPA / PAC 两后端', nodes:[
      {key:'je_pa',t:'pa_alloc(pa_shard_t)',s:'>32KB 或 large miss 入此'},
      {key:'je_hpa',t:'hpa_shard.sec → hpa_central',s:'SEC 前端缓存 + 跨 arena hugepage(THP)'},
      {key:'je_pac',t:'pac_t · dirty→muzzy→retained',s:'经典页分配器,emap/rtree O(1) 定址'}]},
    {title:'⑥ OS · 延迟批量归还', nodes:[
      {key:'je_os',t:'mmap / MADV_FREE / MADV_DONTNEED',s:'decay 超时才归还,减少系统调用'}]}
  ], edges:[
    ['je_req','je_sz'],
    ['je_sz','je_tcs'],['je_sz','je_tcl'],
    ['je_tcs','je_fill'],['je_tcl','je_large'],
    ['je_fill','je_arena'],['je_arena','je_bin'],['je_bin','je_slab'],
    ['je_slab','je_pa'],['je_large','je_pa'],['je_sz','je_pa'],
    ['je_pa','je_hpa'],['je_pa','je_pac'],
    ['je_hpa','je_os'],['je_pac','je_os']
  ] },
  metaflow:{ accent:'#eab308', stages:[
    {title:'① 变更入口', nodes:[
      {key:'edLog',t:'EditLog.logEdit',s:'persist/EditLog.java:1585'}]},
    {title:'② 日志复制(BDB-JE)', nodes:[
      {key:'edBdbje',t:'BDBJEJournal.write',s:'分配 journalId+多数派:230'}]},
    {title:'③ 角色 & 追平', nodes:[
      {key:'edRole',t:'Env.transferToMaster',s:'选主后迁移:1636'},
      {key:'edReplay',t:'Env.replayJournal',s:'Follower 重放追平:3081'}]},
    {title:'④ 镜像压缩', nodes:[
      {key:'edCkpt',t:'Checkpoint.doCheckpoint',s:'editlog→image:90'}]}
  ], edges:[['edLog','edBdbje'],['edBdbje','edRole'],['edBdbje','edReplay'],['edRole','edCkpt'],['edReplay','edCkpt']] },
  tabletflow:{ accent:'#f97316', stages:[
    {title:'① 巡检发现', nodes:[
      {key:'tsCheck',t:'TabletChecker.checkTablets',s:'巡检欠副本:236'},
      {key:'tsHealth',t:'Tablet.getHealth',s:'算 12 态健康:542'}]},
    {title:'② 调度排队', nodes:[
      {key:'tsSched',t:'TabletScheduler 主循环',s:'runAfterCatalogReady:353'}]},
    {title:'③ 分派修复', nodes:[
      {key:'tsHandle',t:'handleTabletByTypeAndStatus',s:'按状态分派:685'},
      {key:'tsClone',t:'CloneTask.toThrift',s:'下发 BE 克隆:82'}]},
    {title:'④ 负载均衡', nodes:[
      {key:'tsBalance',t:'Rebalancer.selectAlt…',s:'BeLoad/Disk 均衡:88'}]}
  ], edges:[['tsCheck','tsHealth'],['tsHealth','tsSched'],['tsSched','tsHandle'],['tsHandle','tsClone'],['tsSched','tsBalance']] },
  scflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① ALTER 分派', nodes:[
      {key:'scHandler',t:'SchemaChangeHandler.process',s:'light/heavy 分类:1924'},
      {key:'scCreateJob',t:'createJob 建影子索引',s:'SHADOW index+tablet:1278'}]},
    {title:'② PENDING · 建影子副本', nodes:[
      {key:'scPending',t:'runPendingJob',s:'取 watershedTxnId:411'}]},
    {title:'③ WAITING_TXN · 等旧事务', nodes:[
      {key:'scWaitTxn',t:'runWaitingTxnJob',s:'排空 watershed 前事务:469'}]},
    {title:'④ RUNNING · BE 转数据', nodes:[
      {key:'scBeConvert',t:'process_alter_tablet',s:'schema_change.cpp:812'},
      {key:'scProc',t:'SchemaChange 转换器族',s:'Linked/Directly/Sorting:556'}]},
    {title:'⑤ 原子切换', nodes:[
      {key:'scRunning',t:'runRunningJob→onFinished',s:'影子替换原始:596'}]}
  ], edges:[['scHandler','scCreateJob'],['scCreateJob','scPending'],['scPending','scWaitTxn'],['scWaitTxn','scBeConvert'],['scBeConvert','scProc'],['scProc','scRunning']] },
  icebergflow:{ accent:'#26a69a', stages:[
    {title:'① 多目录元数据', nodes:[
      {key:'mcCatalogMgr',t:'CatalogMgr.createCatalog',s:'catalog 注册表:248'},
      {key:'mcExtCatalog',t:'ExternalCatalog.makeSureInit',s:'懒加载+SchemaCache:321'},
      {key:'icCatalog',t:'IcebergExternalCatalog',s:'接入 Iceberg Catalog'}]},
    {title:'② FE 切分(读 manifest)', nodes:[
      {key:'icScan',t:'IcebergScanNode.getSplits',s:'snapshot→manifest→split:381'}]},
    {title:'③ BE 读取 + delete', nodes:[
      {key:'icReader',t:'IcebergTableReader',s:'包 Parquet/ORC+过滤:102'},
      {key:'icDelete',t:'init_row_filters',s:'eq/pos delete 应用:120'}]}
  ], edges:[['mcCatalogMgr','mcExtCatalog'],['mcExtCatalog','icCatalog'],['icCatalog','icScan'],['icScan','icReader'],['icReader','icDelete']] },
  wgflow:{ accent:'#38bdf8', stages:[
    {title:'① FE 选组 & 准入排队', nodes:[{key:'wgCoordExec',t:'Coordinator 取 QueryQueue',s:'execInternal 前:700'},{key:'wgMgrFe',t:'WorkloadGroupMgr::getWorkloadGroup',s:'按 ctx 选组+鉴权:143'},{key:'wgQueue',t:'QueryQueue::getToken',s:'校 maxConcurrency/QueueSize:104'},{key:'wgToken',t:'QueueToken::get',s:'阻塞等 TokenState:87'}]},
    {title:'② 下发 BE', nodes:[{key:'wgDispatch',t:'params.setWorkloadGroups',s:'wg 随 fragment 下发:3260'},{key:'wgMgrBe',t:'get_or_create_workload_group',s:'BE 建/更新组:62'}]},
    {title:'③ CPU 隔离 (cgroup)', nodes:[{key:'wgCreateCg',t:'create_cgroup_cpu_ctl',s:'workload_group.cpp:514'},{key:'wgCgroup',t:'CgroupCpuCtl V1/V2',s:'cpu.shares/cpu.weight:165'}]},
    {title:'④ 内存 & 并发管控', nodes:[{key:'wgPaused',t:'add_paused_query',s:'超限入 _paused_queries:707'},{key:'wgHandlePaused',t:'handle_paused_queries',s:'挑查询 spill/cancel:316'},{key:'wgSlot',t:'total_query_slot_count',s:'限组内并发:797'}]}
  ], edges:[['wgCoordExec','wgMgrFe'],['wgMgrFe','wgQueue'],['wgQueue','wgToken'],['wgToken','wgDispatch'],['wgDispatch','wgMgrBe'],['wgMgrBe','wgCreateCg'],['wgCreateCg','wgCgroup'],['wgCgroup','wgPaused'],['wgPaused','wgHandlePaused'],['wgHandlePaused','wgSlot']] },
  optflow:{ accent:'#2dd4a7', stages:[
    {title:'① Parser', nodes:[{key:'optParse',t:'NereidsParser::parse',s:'ANTLR→AST:350'},{key:'optBuilder',t:'LogicalPlanBuilder',s:'visit→LogicalPlan:1172'}]},
    {title:'② Analyze 绑定', nodes:[{key:'optAnalyzer',t:'Analyzer::analyze',s:'NereidsPlanner:410'},{key:'optBind',t:'BindRelation/Expression',s:'绑表/列/函数:131'},{key:'optSubquery',t:'SubqueryToApply',s:'子查询转 Apply:219'}]},
    {title:'③ Rewrite (RBO)', nodes:[{key:'optRewriter',t:'Rewriter::execute',s:'NereidsPlanner:431'},{key:'optFixpoint',t:'迭代到不动点',s:'AbstractBatchJob:149'},{key:'optRbo',t:'RBO 规则集(→ 原理页)',s:'谓词下推/列裁剪…'}]},
    {title:'④ Optimize (CBO)', nodes:[{key:'optOptimizer',t:'Optimizer::execute',s:'toMemo:48'},{key:'optDeriveStats',t:'DeriveStatsJob',s:'派生统计:75'},{key:'optCostEnforcer',t:'CostAndEnforcerJob',s:'代价+enforcer:116'},{key:'optMemo',t:'Memo/Group(→ 原理页)',s:'记忆化枚举:72'}]},
    {title:'⑤ 选计划', nodes:[{key:'optChoose',t:'chooseNthPlan',s:'取最低代价:319'},{key:'optHbo',t:'HBO 历史修正(→ 原理页)',s:'HboStatsCalculator:94'}]}
  ], edges:[['optParse','optBuilder'],['optBuilder','optAnalyzer'],['optAnalyzer','optBind'],['optBind','optSubquery'],['optSubquery','optRewriter'],['optRewriter','optFixpoint'],['optFixpoint','optRbo'],['optRbo','optOptimizer'],['optOptimizer','optDeriveStats'],['optDeriveStats','optCostEnforcer'],['optCostEnforcer','optMemo'],['optMemo','optChoose'],['optChoose','optHbo']] },
  pipeflow:{ accent:'#2dd4a7', stages:[
    {title:'① 构建', nodes:[{key:'plPipeCtx',t:'PipelineFragmentContext',s:'prepare:256'},{key:'plBuildPipe',t:'_build_pipelines',s:'_create_tree_helper:634'},{key:'plPipeline',t:'Pipeline',s:'operator 链模板:42'}]},
    {title:'② 调度', nodes:[{key:'plTaskSched',t:'TaskScheduler::submit',s:'task_scheduler.cpp:72'},{key:'plTaskQueue',t:'MultiCoreTaskQueue',s:'work-stealing:106'},{key:'plPipeTask',t:'PipelineTask::execute',s:'pipeline_task.cpp:386'}]},
    {title:'③ 执行 (pull-sink)', nodes:[{key:'plOperator',t:'OperatorXBase',s:'get_block/pull:865'},{key:'plDependency',t:'Dependency',s:'阻塞/唤醒:103'}]},
    {title:'④ 数据交换', nodes:[{key:'plLocalExchange',t:'LocalExchange',s:'local shuffle:71'},{key:'plExchangeSink',t:'ExchangeSinkOperatorX',s:'跨 fragment:189'}]}
  ], edges:[['plPipeCtx','plBuildPipe'],['plBuildPipe','plPipeline'],['plPipeline','plTaskSched'],['plTaskSched','plTaskQueue'],['plTaskQueue','plPipeTask'],['plPipeTask','plOperator'],['plOperator','plDependency'],['plPipeTask','plLocalExchange'],['plLocalExchange','plExchangeSink']] },
  mvflow:{ accent:'var(--cv-ink)', stages:[
    {title:'A. 异步 MTMV 刷新', nodes:[{key:'mvMtmv',t:'MTMVService::registerMTMV',s:'广播 HookService:78'},{key:'mvJobMgr',t:'MTMVJobManager::createJob',s:'注册调度:115'},{key:'mvTaskRun',t:'MTMVTask::run',s:'刷新主入口:181'},{key:'mvNeedRefresh',t:'getMTMVNeedRefreshPartitions',s:'增量算分区:633'},{key:'mvSnapshot',t:'generatePartitionSnapshots',s:'记录版本快照:259'}]},
    {title:'B. 透明改写 (Nereids 查询期)', nodes:[{key:'mvInitHook',t:'InitMaterializationContextHook',s:'收集可用 MV:87'},{key:'mvStructInfo',t:'StructInfo::of',s:'HyperGraph+Predicates:285'},{key:'mvRewrite',t:'AbstractMaterializedViewRule::rewrite',s:'规则入口:118'},{key:'mvMatchMode',t:'doRewrite→decideMatchMode',s:'COMPLETE/PARTIAL:215'},{key:'mvAggRollup',t:'AggregateRule 补上卷',s:'aggregateRewriteByView:89'}]},
    {title:'C. 同步 MV (Rollup)', nodes:[{key:'mvSyncHandler',t:'MaterializedViewHandler',s:'processCreateMV:194'},{key:'mvRollupJob',t:'RollupJobV2',s:'runPendingJob→onFinished:338'},{key:'mvPreAgg',t:'SetPreAggStatus',s:'查询期选 index:149'}]}
  ], edges:[['mvMtmv','mvJobMgr'],['mvJobMgr','mvTaskRun'],['mvTaskRun','mvNeedRefresh'],['mvNeedRefresh','mvSnapshot'],['mvInitHook','mvStructInfo'],['mvStructInfo','mvRewrite'],['mvRewrite','mvMatchMode'],['mvMatchMode','mvAggRollup'],['mvSyncHandler','mvRollupJob'],['mvRollupJob','mvPreAgg']] },
  statflow:{ accent:'#38bdf8', stages:[
    {title:'① 采集调度', nodes:[{key:'statAutoCollector',t:'StatisticsAutoCollector',s:'自动收集:53'},{key:'statAnalysisMgr',t:'AnalysisManager',s:'createAnalyze:117'}]},
    {title:'② 统计缓存', nodes:[{key:'statColumnStat',t:'ColumnStatistic + Cache',s:'ndv/min/max:41'}]},
    {title:'③ 喂给 CBO', nodes:[{key:'optStatsCalc',t:'StatsCalculator',s:'行数估算:181'},{key:'optCostEnforcer',t:'CostAndEnforcerJob',s:'代价比较:48'}]}
  ], edges:[['statAutoCollector','statAnalysisMgr'],['statAnalysisMgr','statColumnStat'],['statColumnStat','optStatsCalc'],['optStatsCalc','optCostEnforcer']] },
  loadflow:{ accent:'#f59e0b', stages:[
    {title:'① 导入入口', nodes:[{key:'loadStreamAction',t:'StreamLoadAction (BE)',s:'_on_header:202'},{key:'loadBroker',t:'BrokerLoadJob (FE)',s:'Broker/HDFS 批量:84'},{key:'loadMgr',t:'RoutineLoadJob',s:'Kafka 持续导入:90'}]},
    {title:'② 事务 begin', nodes:[{key:'loadStreamExec',t:'StreamLoadExecutor::begin_txn',s:'向 FE 开事务:160'},{key:'loadGtm',t:'GlobalTransactionMgr',s:'全局事务管理'}]},
    {title:'③ 分桶分发 (Sink)', nodes:[{key:'loadVtablet',t:'VTabletWriter::write',s:'按 tablet 分桶:2060'},{key:'loadNodeChan',t:'VNodeChannel::add_block',s:'组 RPC 发各 BE:735'}]},
    {title:'④ BE 接收路由', nodes:[{key:'loadRpc',t:'tablet_writer_add_block',s:'RPC 接收:489'},{key:'loadChanMgr',t:'LoadChannelMgr::add_batch',s:'路由 channel:151'},{key:'loadTabletsChan',t:'TabletsChannel::add_batch',s:'分发 DeltaWriter:636'}]},
    {title:'⑤ 落盘成 rowset', nodes:[{key:'deltaWrite',t:'DeltaWriter::write',s:'→MemTableWriter:143'},{key:'memInsert',t:'MemTable 预聚合',s:'排序+聚合:197'},{key:'memFlush',t:'MemtableFlushTask',s:'异步 flush→segment:210'},{key:'segWrite',t:'SegmentWriter',s:'append_block 落盘:701'}]},
    {title:'⑥ 事务 publish', nodes:[{key:'loadPublish',t:'commitTransaction / publish',s:'version 可见:775'}]}
  ], edges:[['loadStreamAction','loadStreamExec'],['loadBroker','loadStreamExec'],['loadMgr','loadStreamExec'],['loadStreamExec','loadGtm'],['loadGtm','loadVtablet'],['loadVtablet','loadNodeChan'],['loadNodeChan','loadRpc'],['loadRpc','loadChanMgr'],['loadChanMgr','loadTabletsChan'],['loadTabletsChan','deltaWrite'],['deltaWrite','memInsert'],['memInsert','memFlush'],['memFlush','segWrite'],['segWrite','loadPublish']] },
  gcflow:{ accent:'#f59e0b', stages:[
    {title:'① FE 判定组提交', nodes:[
      {key:'gcFePlan',t:'OlapGroupCommitInsertExecutor',s:'fastAnalyzeGroupCommit 判定资格'},
      {key:'gcFeSelect',t:'GroupCommitManager.selectBackend',s:'同表粘同 BE 合批'}]},
    {title:'② BE 攒批队列', nodes:[
      {key:'gcSink',t:'GroupCommitBlockSink',s:'挂共享队列:66'},
      {key:'gcQueue',t:'LoadBlockQueue.add_block',s:'追加+写 WAL:51'}]},
    {title:'③ 组提交落盘', nodes:[
      {key:'gcCreate',t:'_create_group_commit_load',s:'开事务+建 WAL+拉 fragment:324'}]}
  ], edges:[['gcFePlan','gcFeSelect'],['gcFeSelect','gcSink'],['gcSink','gcQueue'],['gcQueue','gcCreate']] },
  rlflow:{ accent:'#f59e0b', stages:[
    {title:'① 作业级调度', nodes:[
      {key:'rlSched',t:'RoutineLoadScheduler.process',s:'选 NEED_SCHEDULE 作业:62'},
      {key:'rlDivide',t:'KafkaRoutineLoadJob.divide',s:'分区轮询切 task+取 offset:230'}]},
    {title:'② 任务级调度', nodes:[
      {key:'rlTaskSched',t:'RoutineLoadTaskScheduler',s:'scheduleOneTask→选 BE:121'}]},
    {title:'③ BE 消费落盘', nodes:[
      {key:'rlBe',t:'TRoutineLoadTask (BE)',s:'消费 Kafka 分区区间→事务导入'}]}
  ], edges:[['rlSched','rlDivide'],['rlDivide','rlTaskSched'],['rlTaskSched','rlBe']] },
  rfflow:{ accent:'#38bdf8', stages:[
    {title:'① FE 计划生成 · 遍历物理树', nodes:[{key:'rfGenFe',t:'RuntimeFilterGenerator',s:'visitPhysicalHashJoin:生成 TRuntimeFilterDesc(filter_id/src_expr/IN_OR_BLOOM)'},{key:'rfTranslate',t:'RuntimeFilterPushDownVisitor',s:'沿 Probe 侧下推,绑到 OlapScan(orders)目标 slot'}]},
    {title:'② BE 消费端注册 · 阻塞 Scan', nodes:[{key:'rfConsumer',t:'ConsumerHelper.init',s:'建 Consumer(NOT_READY)+ filter_dependency(_ready=false)'},{key:'rfWait',t:'RuntimeFilterTimer 入队',s:'remote→wait_time_ms(默认1000ms);local→execution_timeout'},{key:'rfBlock',t:'PipelineTask._wait_to_start',s:'dependency 未就绪 → Scan 进 BLOCKED'},{key:'rfTimeout',t:'TimerQueue.call_timeout',s:'超时 set_always_ready 强制放行(降级,无 RF 过滤)'}]},
    {title:'③ Build 侧 · 两阶段大小协议', nodes:[{key:'rfSendSize',t:'send_filter_size',s:'brpc → FE MergeController 收齐 N 实例 → sync 全局行数'},{key:'rfInitType',t:'init(synced_size) 自适应',s:'≤max_in_num→IN(精确);否则→BLOOM(FPP=0.05,K=8 算 BF 大小)'},{key:'rfProducer',t:'build(block) 插入',s:'IN→HybridSet;BF→insert_fixed_len 批量'}]},
    {title:'④ 发布合并 → 消费端接收', nodes:[{key:'rfPublish',t:'publish → merge_filter',s:'brpc → FE merge_from × N,ready 后广播'},{key:'rfApply',t:'FragmentMgr.apply_filterv2',s:'consumer.signal → dependency.set_ready → Task.wake_up'}]},
    {title:'⑤ Scan 应用 · RF→conjunct', nodes:[{key:'rfAcquire',t:'acquire_runtime_filter',s:'RF→VExpr→conjuncts;READY→APPLIED'},{key:'rfScanPush',t:'_normalize_predicate 下推',s:'IN/BLOOM/MinMax → _slot_id_to_predicates → 存储层'},{key:'rfLate',t:'try_append_late_arrival',s:'Scanner 每次调度追加迟到 RF,对后续 Block 生效'}]},
    {title:'⑥ 存储层 · SIMD 谓词评估', nodes:[{key:'rfEval',t:'_evaluate_vectorization_predicate',s:'IN 字典 code 查找 / BF find_batch / MinMax ZoneMap 跳 page'},{key:'rfSel',t:'sel_rowid_idx + 延迟物化',s:'先过滤再按 rowid 读非谓词列'}]}
  ], edges:[
    ['rfGenFe','rfTranslate'],
    ['rfTranslate','rfConsumer'],['rfConsumer','rfWait'],['rfWait','rfBlock'],
    ['rfTranslate','rfSendSize'],['rfSendSize','rfInitType'],['rfInitType','rfProducer'],
    ['rfProducer','rfPublish'],['rfPublish','rfApply'],
    ['rfApply','rfAcquire'],['rfBlock','rfAcquire','唤醒'],['rfAcquire','rfScanPush'],['rfScanPush','rfLate'],
    ['rfScanPush','rfEval'],['rfEval','rfSel'],
    ['rfWait','rfTimeout','超时降级',true]
  ] },
  topnflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① FE 标记 & 翻译', nodes:[{key:'topnScanOpt',t:'TopNScanOpt',s:'标记 topn-filter 源:40'},{key:'topnPhysical',t:'PhysicalPlanTranslator',s:'visitPhysicalTopN:2465'},{key:'topnThrift',t:'SortNode::toThrift',s:'topn_filter_source_node_ids:220'}]},
    {title:'② 堆维护 top-k', nodes:[{key:'topnSinkInit',t:'SortSinkOperatorX::init',s:'HEAP_SORT set_detected:116'},{key:'topnSink',t:'SortSinkOperatorX::sink',s:'append→比对 old_top:143'},{key:'topnHeap',t:'HeapSorter::get_top_value',s:'堆顶第 k 名:73'}]},
    {title:'③ 更新动态谓词', nodes:[{key:'runtimePredicate',t:'RuntimePredicate::update',s:'刷 _orderby_extrem:68'}]},
    {title:'④ 传到 scan', nodes:[{key:'topnScanInit',t:'ScanLocalState init_target',s:'绑目标 slot cid:1226'},{key:'topnNormalize',t:'_normalize_predicate',s:'取 ColumnPredicate:497'},{key:'topnTablet',t:'TabletReader 条件',s:'灌 predicates:189'}]},
    {title:'⑤ segment 裁剪', nodes:[{key:'topnSegIter',t:'_can_opt_topn_reads',s:'zonemap 提前裁剪:2482'}]}
  ], edges:[['topnScanOpt','topnPhysical'],['topnPhysical','topnThrift'],['topnThrift','topnSinkInit'],['topnSinkInit','topnSink'],['topnSink','topnHeap'],['topnHeap','runtimePredicate'],['runtimePredicate','topnScanInit'],['topnScanInit','topnNormalize'],['topnNormalize','topnTablet'],['topnTablet','topnSegIter']] },
  compactflow:{ accent:'#e6a15a', stages:[
    {title:'① 后台调度', nodes:[{key:'compProducer',t:'_compaction_tasks_producer',s:'olap_server.cpp:647'},{key:'compSubmit',t:'_submit_compaction_task',s:'算 score 挑 tablet:1055'}]},
    {title:'② 选 rowset', nodes:[{key:'compCumuPrepare',t:'CumulativeCompaction::prepare',s:'cumulative_compaction.cpp:89'},{key:'compBasePrepare',t:'BaseCompaction::prepare',s:'base_compaction.cpp:49'},{key:'compPolicy',t:'SizeBased::pick_input_rowsets',s:'累加 score+cumu point:247'}]},
    {title:'③ 执行归并', nodes:[{key:'compExec',t:'CompactionMixin::execute_compact',s:'compaction.cpp:567'},{key:'compMerge',t:'Merger::vertical_merge_rowsets',s:'多路归并:292'}]},
    {title:'④ MoW delete bitmap', nodes:[{key:'compUpdateBitmap',t:'update_delete_bitmap',s:'compaction.cpp:1203'},{key:'compCalcBitmap',t:'calc_compaction_output_...bitmap',s:'rowid 转换重算:1601'}]},
    {title:'⑤ 输出 + 回收', nodes:[{key:'compBuild',t:'_output_rs_writer->build',s:'新 rowset:317'},{key:'compModify',t:'Tablet::modify_rowsets',s:'老 rowset 转 stale:530'},{key:'compGc',t:'start_delete_unused_rowset',s:'GC:1228'}]}
  ], edges:[['compProducer','compSubmit'],['compSubmit','compCumuPrepare'],['compSubmit','compBasePrepare'],['compCumuPrepare','compPolicy'],['compBasePrepare','compPolicy'],['compPolicy','compExec'],['compExec','compMerge'],['compMerge','compUpdateBitmap'],['compUpdateBitmap','compCalcBitmap'],['compCalcBitmap','compBuild'],['compBuild','compModify'],['compModify','compGc']] },
  txnflow:{ accent:'#5aa469', stages:[
    {title:'① 写入事务(FE 两阶段)', nodes:[{key:'txnFeBegin',t:'DatabaseTransactionMgr',s:'FE begin/commit(Java)'},{key:'txnPrepare',t:'TxnManager::prepare_txn',s:'登记事务槽:93'}]},
    {title:'② commit', nodes:[{key:'txnCommit',t:'TxnManager::commit_txn',s:'落 rowset meta:191'},{key:'txnBitmap',t:'set_txn_related_delete_bitmap',s:'MoW bitmap:245'}]},
    {title:'③ publish version', nodes:[{key:'txnPublishTask',t:'EnginePublishVersionTask',s:'engine_publish_version_task.cpp:97'},{key:'txnPublish',t:'TxnManager::publish_txn',s:'给 rowset 定版本:459'},{key:'txnAddInc',t:'Tablet::add_inc_rowset',s:'新 version 生效:696'}]},
    {title:'④ 读时可见性', nodes:[{key:'txnCapture',t:'Tablet::capture_rs_readers',s:'按 version 选 rowset:963'},{key:'txnVersionGraph',t:'VersionGraph 最短路',s:'version_graph.cpp:417'}]}
  ], edges:[['txnFeBegin','txnPrepare'],['txnPrepare','txnCommit'],['txnCommit','txnBitmap'],['txnBitmap','txnPublishTask'],['txnPublishTask','txnPublish'],['txnPublish','txnAddInc'],['txnAddInc','txnCapture'],['txnCapture','txnVersionGraph']] },
  hudiflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① FE 生成 split', nodes:[{key:'hudiSplit',t:'HudiScanNode::getSplits',s:'HudiScanNode.java:603'},{key:'hudiCow',t:'isHoodieCowTable',s:'判 COW/MOR:179'},{key:'hudiNative',t:'canUseNativeReader',s:'COW 走原生:399'}]},
    {title:'② COW(原生 parquet)', nodes:[{key:'hudiCowSplit',t:'addCowNativeReaderSplits',s:':492'},{key:'hudiParquet',t:'HudiParquetReader',s:'包 ParquetReader:33'}]},
    {title:'③ MOR(JNI 合并)', nodes:[{key:'hudiGenSplit',t:'generateHudiSplit',s:'base+log 打包:725'},{key:'hudiJni',t:'HudiJniReader::init_reader',s:'JNI 调 Java:181'},{key:'hudiMerge',t:'getRecordReader (Java)',s:'base parquet+avro log 合并:549'}]},
    {title:'④ 取行', nodes:[{key:'hudiNext',t:'get_next_block',s:'hudi_reader.cpp:28'}]}
  ], edges:[['hudiSplit','hudiCow'],['hudiCow','hudiNative'],['hudiNative','hudiCowSplit'],['hudiCowSplit','hudiParquet'],['hudiCow','hudiGenSplit'],['hudiGenSplit','hudiJni'],['hudiJni','hudiMerge'],['hudiParquet','hudiNext'],['hudiMerge','hudiNext']] },
  hiveorcflow:{ accent:'var(--cv-ink)', stages:[
    {title:'① FE 切 split', nodes:[{key:'horcSplit',t:'HiveScanNode::getSplits',s:'HiveScanNode.java:261'},{key:'horcFileSplit',t:'FileSplitter::splitFile',s:'按 targetSize 切:498'}]},
    {title:'② BE 建 reader', nodes:[{key:'horcInit',t:'OrcReader::init_reader',s:'vorc_reader.cpp:431'}]},
    {title:'③ 谓词下推', nodes:[{key:'horcSarg',t:'_build_search_argument',s:'转 SearchArgument:972'},{key:'horcPush',t:'row_reader.searchArgument',s:'下推 stripe/row-group:1085'}]},
    {title:'④ 延迟物化', nodes:[{key:'horcFill',t:'set_fill_columns',s:'分谓词/lazy 列:1089'},{key:'horcLazy',t:'createRowReader(filter)',s:'先读谓词列:1327'},{key:'horcFilter',t:'OrcReader::filter',s:'谓词回调过滤:2647'}]},
    {title:'⑤ 读剩余列 + 补列', nodes:[{key:'horcDict',t:'dict filter 字典加速',s:'_can_filter_by_dict:2804'},{key:'horcNext',t:'get_next_block',s:'读其余列:2266'},{key:'horcMiss',t:'_fill_missing/partition',s:'补分区/缺失列:1441'}]}
  ], edges:[['horcSplit','horcFileSplit'],['horcFileSplit','horcInit'],['horcInit','horcSarg'],['horcSarg','horcPush'],['horcPush','horcFill'],['horcFill','horcLazy'],['horcLazy','horcFilter'],['horcFilter','horcDict'],['horcDict','horcNext'],['horcNext','horcMiss']] },
  profileflow:{ accent:'#8fb0e8', stages:[
    {title:'① 算子埋点采集', nodes:[{key:'pfCounter',t:'RuntimeProfile::add_counter',s:'算子建计数器树'},{key:'pfTimer',t:'SCOPED_TIMER/COUNTER_UPDATE',s:'执行中累加耗时/行数'}]},
    {title:'② 实例级profile', nodes:[{key:'pfInstance',t:'每 PipelineTask 一棵 profile',s:'算子树 + CommonCounters'},{key:'pfLevel',t:'profile_level 剪枝',s:'prune_the_tree 按 level 1-3'}]},
    {title:'③ BE 上报 FE', nodes:[{key:'pfReport',t:'report_exec_status',s:'各 BE 定期上报 fragment profile'}]},
    {title:'④ FE 聚合', nodes:[{key:'pfMerge',t:'RuntimeProfile::merge',s:'跨 BE 同名 counter 累加/求 min/avg/max'},{key:'pfMerged',t:'MergedProfile',s:'倾斜看 min/avg/max 差'}]},
    {title:'⑤ 展示', nodes:[{key:'pfDetail',t:'DetailProfile',s:'按 BE×instance 未聚合原始值'},{key:'pfShow',t:'SHOW QUERY PROFILE',s:'五段树呈现'}]}
  ], edges:[['pfCounter','pfTimer'],['pfTimer','pfInstance'],['pfInstance','pfLevel'],['pfLevel','pfReport'],['pfReport','pfMerge'],['pfMerge','pfMerged'],['pfMerged','pfDetail'],['pfDetail','pfShow']] },
  // ===== 整体架构主题:5 张架构图 =====
  archintegrated:{ accent:'var(--cv-ink)', stages:[
    {title:'① 数据源', nodes:[{key:'ai_src_db',t:'业务库',s:'MySQL/PG/Oracle'},{key:'ai_src_mq',t:'消息流',s:'Kafka/Pulsar'},{key:'ai_src_lake',t:'数据湖',s:'Hive/Iceberg/Paimon'},{key:'ai_src_http',t:'IoT/埋点',s:'HTTP 直推'}]},
    {title:'② 接入', nodes:[{key:'ai_cdc',t:'Flink CDC',s:'2PC Exactly-Once,需 MoW'},{key:'ai_rl',t:'Routine Load',s:'Kafka 消费 At-Least-Once'},{key:'ai_sl',t:'Stream Load+Group Commit',s:'高频小批必用'},{key:'ai_fed',t:'External Catalog',s:'联邦直查 or 入仓'}]},
    {title:'③ 数仓分层(ODS→DWD→DWS→ADS)', nodes:[{key:'ai_ods',t:'ODS 原始层',s:'Duplicate Key 贴源全量回溯'},{key:'ai_dwd',t:'DWD 明细层',s:'Unique/MoW 清洗去重,CDC 更新'},{key:'ai_dws',t:'DWS 汇总层',s:'Aggregate Key + 同步 MV 预聚合'},{key:'ai_ads',t:'ADS 应用层',s:'异步 MTMV(多表 JOIN) SPJG 改写'}]},
    {title:'④ 服务消费', nodes:[{key:'ai_bi',t:'BI 报表',s:'9030/JDBC <5s 并发100+'},{key:'ai_api',t:'数据 API',s:'点查+倒排 <100ms 并发1000+'},{key:'ai_ds',t:'数据科学',s:'Arrow Flight SQL(ADBC)'},{key:'ai_exp',t:'导出交换',s:'OUTFILE→HDFS/S3'}]},
    {title:'⑤ 治理 + 稳定性(横切)', nodes:[{key:'ai_gov',t:'治理域',s:'RBAC/行列权限/审计/TTL'},{key:'ai_ops',t:'稳定性域',s:'Workload Group/监控/备份'}]}
  ], edges:[
    ['ai_src_db','ai_cdc'],['ai_src_mq','ai_rl'],['ai_src_http','ai_sl'],['ai_src_lake','ai_fed'],
    ['ai_cdc','ai_ods'],['ai_rl','ai_ods'],['ai_sl','ai_ods'],['ai_fed','ai_ods'],
    ['ai_ods','ai_dwd'],['ai_dwd','ai_dws'],['ai_dws','ai_ads'],
    ['ai_ads','ai_bi'],['ai_ads','ai_api'],['ai_ads','ai_ds'],['ai_ads','ai_exp'],
    ['ai_gov','ai_ops']
  ] },
  archlakehouse:{ accent:'var(--cv-ink)', stages:[
    {title:'① 联邦查询入口', nodes:[{key:'al_sql',t:'跨 Catalog SQL',s:'hive.t JOIN iceberg.t2'},{key:'al_fe',t:'FE CatalogMgr',s:'CREATE CATALOG 注册外部源'}]},
    {title:'② Catalog(继承 ExternalCatalog)', nodes:[{key:'al_hms',t:'HMSExternalCatalog',s:'Hive/Hudi-HMS'},{key:'al_ice',t:'IcebergExternalCatalog',s:'REST/HMS/Glue/DLF'},{key:'al_paimon',t:'PaimonExternalCatalog',s:'Apache Paimon'},{key:'al_jdbc',t:'JdbcExternalCatalog',s:'MySQL/PG/Oracle'}]},
    {title:'③ FE 元数据缓存 ExternalMetaCacheMgr', nodes:[{key:'al_mc',t:'各引擎独立缓存',s:'partition/file_list/schema · Caffeine+TTL'},{key:'al_refresh',t:'REFRESH CATALOG/TABLE',s:'手动失效'}]},
    {title:'④ BE 外表 Scan', nodes:[{key:'al_jni',t:'JniConnector',s:'JNI 调 Java 读 Parquet/ORC/Avro'},{key:'al_native',t:'NativeReader',s:'C++ 直读,性能更优'},{key:'al_push',t:'谓词下推',s:'分区裁剪/列裁剪/RowGroup 过滤'}]},
    {title:'⑤ 底层存储', nodes:[{key:'al_hdfs',t:'HDFS',s:''},{key:'al_obj',t:'S3/OSS/COS/GCS',s:''}]}
  ], edges:[
    ['al_sql','al_fe'],['al_fe','al_hms'],['al_fe','al_ice'],['al_fe','al_paimon'],['al_fe','al_jdbc'],
    ['al_hms','al_mc'],['al_ice','al_mc'],['al_paimon','al_mc'],['al_jdbc','al_mc'],['al_mc','al_refresh'],
    ['al_mc','al_jni'],['al_mc','al_native'],['al_jni','al_push'],['al_native','al_push'],
    ['al_push','al_hdfs'],['al_push','al_obj']
  ] },
  archinteg:{ accent:'var(--cv-ink)', stages:[
    {title:'① 写入路径', nodes:[{key:'ag_sl',t:'Stream Load',s:'HTTP 直推'},{key:'ag_bl',t:'Broker Load',s:'HDFS/S3 导入'},{key:'ag_rl',t:'Routine Load',s:'Kafka 消费'}]},
    {title:'② FE 集群(Java,BDB JE)', nodes:[{key:'ag_fem',t:'FE Master',s:'元数据读写 + Raft 同步'},{key:'ag_fef',t:'FE Follower',s:'只读,可选举'},{key:'ag_feo',t:'FE Observer',s:'只读,扩并发'}]},
    {title:'③ BE 集群(C++,存储+计算一体)', nodes:[{key:'ag_pipe',t:'Pipeline 执行',s:'PipelineTask/Dependency 非阻塞'},{key:'ag_op',t:'向量化算子',s:'Scan/Join/Agg 4096 行/批 SIMD'},{key:'ag_st',t:'StorageEngine',s:'Tablet 管理 + Compaction'}]},
    {title:'④ 本地存储结构', nodes:[{key:'ag_tablet',t:'Tablet(分区×Bucket)',s:'多副本默认3,Rowset 同步'},{key:'ag_rowset',t:'Rowset',s:'不可变 + MVCC 多版本'},{key:'ag_seg',t:'Segment(.dat)',s:'列存 + Page 编码 LZ4/Zstd'},{key:'ag_idx',t:'多级索引',s:'ShortKey/ZoneMap/Bloom/Inverted'}]},
    {title:'⑤ 数据模型', nodes:[{key:'ag_dup',t:'Duplicate',s:'明细'},{key:'ag_uniq',t:'Unique(MoW)',s:'主键 + Delete Bitmap'},{key:'ag_agg',t:'Aggregate',s:'预聚合'}]}
  ], edges:[
    ['ag_sl','ag_fem'],['ag_bl','ag_fem'],['ag_rl','ag_fem'],
    ['ag_fem','ag_fef'],['ag_fem','ag_feo'],['ag_fem','ag_pipe'],
    ['ag_pipe','ag_op'],['ag_op','ag_st'],['ag_st','ag_tablet'],
    ['ag_tablet','ag_rowset'],['ag_rowset','ag_seg'],['ag_rowset','ag_idx'],
    ['ag_seg','ag_dup'],['ag_seg','ag_uniq'],['ag_seg','ag_agg']
  ] },
  archdecoupled:{ accent:'var(--cv-ink)', stages:[
    {title:'① FE(无本地元数据)', nodes:[{key:'ad_fe',t:'FE 查询规划',s:'经 MetaService RPC 取 Tablet/Rowset 元数据'}]},
    {title:'② MetaService(独立 C++ 服务)', nodes:[{key:'ad_ms',t:'MetaServiceImpl',s:'管 Tablet/Rowset/Txn 元数据 + Storage Vault'},{key:'ad_fdb',t:'FdbTxnKv → FoundationDB',s:'分布式 ACID KV,强一致'}]},
    {title:'③ BE 计算节点(无状态)', nodes:[{key:'ad_cn',t:'Compute Node × N',s:'CloudStorageEngine,无本地数据'}]},
    {title:'④ BlockFileCache(本地 SSD 四队列)', nodes:[{key:'ad_ttl',t:'TTL Queue(50%)',s:'优先级最高不被驱逐'},{key:'ad_idx',t:'INDEX Queue(5%)',s:'索引缓存'},{key:'ad_norm',t:'NORMAL Queue(40%)',s:'LRU 淘汰'},{key:'ad_disp',t:'DISPOSABLE(5%)',s:'最先驱逐'}]},
    {title:'⑤ 共享对象存储 + Recycler', nodes:[{key:'ad_obj',t:'S3/OSS/COS(Storage Vault)',s:'所有 BE 共享单副本'},{key:'ad_rc',t:'Recycler',s:'异步清理孤立 Segment'}]}
  ], edges:[
    ['ad_fe','ad_ms'],['ad_ms','ad_fdb'],['ad_fe','ad_cn'],['ad_ms','ad_cn'],
    ['ad_cn','ad_ttl'],['ad_cn','ad_idx'],['ad_cn','ad_norm'],['ad_cn','ad_disp'],
    ['ad_ttl','ad_obj'],['ad_norm','ad_obj'],['ad_rc','ad_obj']
  ] },
  archtiering:{ accent:'var(--cv-ink)', stages:[
    {title:'① 配置层', nodes:[{key:'at_res',t:'CREATE RESOURCE',s:'type=s3/hdfs 指向远程'},{key:'at_pol',t:'CREATE STORAGE POLICY',s:'绑 Resource + cooldown_ttl'},{key:'at_tbl',t:'建表设 storage_policy',s:''}]},
    {title:'② 热数据(本地磁盘)', nodes:[{key:'at_hot',t:'新写 Rowset',s:'本地 Segment,rs->is_local()=true'}]},
    {title:'③ 冷却过程(BE 后台)', nodes:[{key:'at_need',t:'need_cooldown()',s:'newest_write_ts + ttl < now'},{key:'at_cool',t:'Tablet::cooldown()',s:'仅 cooldown_replica 上传,余副本 follow'},{key:'at_upload',t:'upload_to(resource)',s:'传 Segment,生成新 RowsetMeta'},{key:'at_meta',t:'write_cooldown_meta()',s:'传 meta 供其他副本同步'}]},
    {title:'④ 冷数据(远程)', nodes:[{key:'at_cold',t:'S3/HDFS',s:'is_local()=false,直读无 FileCache'}]},
    {title:'⑤ 冷数据 Compaction', nodes:[{key:'at_cc',t:'cold_compaction',s:'远程 Rowset 合并回写,持 cold_compaction_lock'}]}
  ], edges:[
    ['at_res','at_pol'],['at_pol','at_tbl'],['at_tbl','at_hot'],
    ['at_hot','at_need'],['at_need','at_cool'],['at_cool','at_upload'],['at_upload','at_meta'],
    ['at_meta','at_cold'],['at_cold','at_cc']
  ] },
  lakerel:{ accent:'var(--cv-ink)', stages:[
    {title:'① 查询引擎(Doris)', nodes:[{key:'lr_engine',t:'Doris 查询引擎',s:'Nereids 规划 + BE 向量化执行;既查内表也查外表'}]},
    {title:'② 表格式(逻辑组织,管快照/schema/事务)', nodes:[{key:'lr_iceberg',t:'Iceberg',s:'manifest + snapshot + delete file'},{key:'lr_hudi',t:'Hudi',s:'timeline + COW/MOR'},{key:'lr_paimon',t:'Paimon',s:'LSM + changelog'},{key:'lr_internal',t:'Doris 内表',s:'Tablet/Rowset/VersionGraph'}]},
    {title:'③ 存储格式(物理文件编码,管列存/编码)', nodes:[{key:'lr_parquet',t:'Parquet',s:'RowGroup→ColumnChunk→Page'},{key:'lr_orc',t:'ORC',s:'Stripe→RowGroup→Stream'},{key:'lr_segv2',t:'Segment V2',s:'内表列存 + 三索引'}]},
    {title:'④ 压缩算法(page/stream 粒度,与格式正交)', nodes:[{key:'lr_zstd',t:'ZSTD',s:'高压缩比'},{key:'lr_snappy',t:'Snappy',s:'快'},{key:'lr_lz4',t:'LZ4',s:'内表默认,均衡'}]},
    {title:'⑤ 文件存储(字节落地)', nodes:[{key:'lr_hdfs',t:'HDFS',s:''},{key:'lr_s3',t:'S3/OSS/COS',s:'对象存储'},{key:'lr_local',t:'本地磁盘',s:'内表/热数据'}]}
  ], edges:[
    ['lr_engine','lr_iceberg'],['lr_engine','lr_hudi'],['lr_engine','lr_paimon'],['lr_engine','lr_internal'],
    ['lr_iceberg','lr_parquet'],['lr_iceberg','lr_orc'],['lr_hudi','lr_parquet'],['lr_paimon','lr_orc'],['lr_internal','lr_segv2'],
    ['lr_parquet','lr_zstd'],['lr_parquet','lr_snappy'],['lr_orc','lr_zstd'],['lr_segv2','lr_lz4'],
    ['lr_zstd','lr_hdfs'],['lr_snappy','lr_s3'],['lr_lz4','lr_local'],['lr_zstd','lr_s3']
  ] }
};

function renderFlowSVG(out, tid){
  const spec=FLOW_SPECS[tid]; if(!spec){out.innerHTML='';return;}
  const NS='http://www.w3.org/2000/svg';
  const bw=210, bh=54, colGap=34, rowGap=26, padX=28, bandLabelH=30, bandGap=22, bandPadY=14;
  const maxCols=Math.max(...spec.stages.map(s=>s.nodes.length));
  const W=padX*2 + maxCols*bw + (maxCols-1)*colGap;
  // 逐阶段计算 y,节点定位
  const pos={}; let y=20; const bands=[];
  spec.stages.forEach(st=>{
    const bandTop=y, rows=1, innerH=bh; // 单行网格
    const bandH=bandLabelH+bandPadY*2+innerH;
    bands.push({title:st.title, y:bandTop, h:bandH});
    const nodeY=bandTop+bandLabelH+bandPadY;
    // 居中排布本阶段节点
    const n=st.nodes.length;
    const rowW=n*bw+(n-1)*colGap;
    const startX=(W-rowW)/2;
    st.nodes.forEach((nd,i)=>{ pos[nd.key||('ghost'+i)]={x:startX+i*(bw+colGap), y:nodeY, nd}; });
    y=bandTop+bandH+bandGap;
  });
  const H=y;
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  svg+='<defs><marker id="fa-'+tid+'" markerWidth="9" markerHeight="9" refX="6.5" refY="3" orient="auto"><path d="M0,0 L6.5,3 L0,6 Z" fill="var(--cv-edge)"/></marker></defs>';
  // 阶段带
  bands.forEach(b=>{
    svg+='<rect x="14" y="'+b.y+'" width="'+(W-28)+'" height="'+b.h+'" rx="16" fill="#00000005" stroke="var(--cv-border)" stroke-width="1"/>';
    svg+='<circle cx="30" cy="'+(b.y+16)+'" r="3.5" fill="'+spec.accent+'"/>';
    svg+='<text x="42" y="'+(b.y+21)+'" fill="var(--cv-ink2)" font-size="12.5" font-weight="600" font-family="var(--sans)">'+b.title+'</text>';
  });
  // 边(正交:同阶段横向直线;跨阶段下折)
  let seq=1;
  spec.edges.forEach(([a,bk,label,dash])=>{
    const pa=pos[a], pb=pos[bk]; if(!pa||!pb) return;
    const ax=pa.x+bw/2, ay=pa.y+bh, bx=pb.x+bw/2, by=pb.y;
    let d, midx, midy;
    if(Math.abs(pa.y-pb.y)<2){ // 同阶段:横向
      const y0=pa.y+bh/2;
      d='M'+(pa.x+bw)+' '+y0+' H'+pb.x; midx=(pa.x+bw+pb.x)/2; midy=y0;
    } else { // 跨阶段:底->中->顶
      const my=(ay+by)/2;
      d='M'+ax+' '+ay+' V'+my+' H'+bx+' V'+by; midx=bx; midy=my;
    }
    svg+='<path d="'+d+'" fill="none" stroke="var(--cv-edge)" stroke-width="1.4"'+(dash?' stroke-dasharray="4 4"':'')+' marker-end="url(#fa-'+tid+')"/>';
    // 序号
    svg+='<g class="edge-seq"><circle cx="'+midx+'" cy="'+midy+'" r="9"/><text x="'+midx+'" y="'+(midy+3.5)+'" text-anchor="middle">'+(seq++)+'</text></g>';
  });
  // 节点盒
  const maxTW=bw-16;
  Object.values(pos).forEach(p=>{
    const nd=p.nd, k=nd.key;
    const cl=nd.ghost?'flow-ghost':'flow-node';
    svg+='<g class="'+cl+'"'+(k&&!nd.ghost?' data-k="'+k+'" style="cursor:pointer"':'')+'>';
    svg+='<rect x="'+p.x+'" y="'+p.y+'" width="'+bw+'" height="'+bh+'" rx="11" fill="var(--cv-card)" stroke="'+(nd.ghost?'#e3e7ee':'#d8dde5')+'" stroke-width="1"/>';
    if(!nd.ghost) svg+='<rect x="'+p.x+'" y="'+p.y+'" width="3.5" height="'+bh+'" rx="1.75" fill="'+spec.accent+'"/>';
    // 主标题自适应:超长(如 CompactionMixin::execute_compact)先缩字号,极端再按 textLength 压缩,永不溢出盒宽
    const t=nd.t||'';
    let tfs=12.5, tExtra='';
    const approxW=t.length*12.5*0.62;
    if(approxW>maxTW){
      tfs=Math.max(9, 12.5*maxTW/approxW);
      if(t.length*tfs*0.62>maxTW) tExtra=' textLength="'+maxTW+'" lengthAdjust="spacingAndGlyphs"';
    }
    svg+='<text x="'+(p.x+bw/2)+'" y="'+(p.y+23)+'" fill="var(--cv-ink)" font-size="'+tfs.toFixed(1)+'" font-weight="600" text-anchor="middle" font-family="var(--mono)"'+tExtra+'>'+t+'</text>';
    // 副标题(file:line)同样自适应
    const s=nd.s||'';
    let sfs=9.5, sExtra='';
    const sW=s.length*9.5*0.62;
    if(sW>maxTW){
      sfs=Math.max(8, 9.5*maxTW/sW);
      if(s.length*sfs*0.62>maxTW) sExtra=' textLength="'+maxTW+'" lengthAdjust="spacingAndGlyphs"';
    }
    svg+='<text x="'+(p.x+bw/2)+'" y="'+(p.y+40)+'" fill="'+(nd.ghost?'#86868b':'#86868b')+'" font-size="'+sfs.toFixed(1)+'" text-anchor="middle" font-family="var(--mono)"'+sExtra+'>'+s+'</text>';
    svg+='</g>';
  });
  svg+='</svg>';
  out.innerHTML=svg;
}

/* 手写 SVG 时序图引擎 — 清晰锐利,替换模糊的 mermaid sequence。
   spec: { actors:[{id,label}], msgs:[{f,t,label,ret?,self?,loopStart?,loopEnd?,note?}] } */
const SEQ_SPECS={
  seq:{ actors:[
    {id:'C',label:'Client'},{id:'SE',label:'StmtExecutor'},{id:'NP',label:'NereidsPlanner'},
    {id:'HSN',label:'HiveScanNode'},{id:'HMS',label:'HMSCache'},{id:'CO',label:'Coordinator'},
    {id:'IS',label:'InternalService'},{id:'PT',label:'PipelineTask'},{id:'FS',label:'FileScanner'},{id:'OR',label:'OrcReader'},{id:'DFS',label:'HDFS/S3'}
  ], msgs:[
    {f:'C',t:'SE',label:'SELECT ... FROM hive_orc_tbl'},
    {f:'SE',t:'NP',label:'plan(stmt) 解析→逻辑计划'},
    {f:'NP',t:'NP',label:'planWithLock CBO 优化',self:true},
    {f:'NP',t:'HSN',label:'getSplits(numBackends)'},
    {f:'HSN',t:'HMS',label:'getFilesByPartitions'},
    {f:'HMS',t:'DFS',label:'list files (ORC)'},
    {f:'DFS',t:'HMS',label:'文件列表+大小',ret:true},
    {f:'HSN',t:'HSN',label:'splitToScanRange→TScanRangeLocations',self:true},
    {f:'SE',t:'CO',label:'exec() 下发'},
    {f:'CO',t:'IS',label:'RPC exec_plan_fragment'},
    {f:'IS',t:'PT',label:'prepare→execute'},
    {f:'PT',t:'FS',label:'get_block()',loopStart:'每个 ScanRange (ORC split)'},
    {f:'FS',t:'OR',label:'_get_next_reader→init_reader'},
    {f:'OR',t:'DFS',label:'读 ORC stripe/column'},
    {f:'DFS',t:'OR',label:'原始列数据',ret:true},
    {f:'OR',t:'FS',label:'_get_next_block_impl→Block',ret:true,loopEnd:true},
    {f:'PT',t:'CO',label:'结果分片回传',ret:true},
    {f:'CO',t:'SE',label:'汇总结果',ret:true},
    {f:'SE',t:'C',label:'ResultSet',ret:true}
  ]},
  pipeseq:{ actors:[
    {id:'FM',label:'FragmentMgr'},{id:'PC',label:'PipelineFragmentCtx'},{id:'SC',label:'TaskScheduler'},
    {id:'TQ',label:'MultiCoreTaskQueue'},{id:'PT',label:'PipelineTask'},{id:'OP',label:'Operator'},{id:'DEP',label:'Dependency'}
  ], msgs:[
    {f:'FM',t:'PC',label:'exec_plan_fragment'},
    {f:'PC',t:'PC',label:'prepare 建 pipeline+task 树',self:true},
    {f:'PC',t:'SC',label:'submit(tasks)'},
    {f:'SC',t:'TQ',label:'push_back'},
    {f:'TQ',t:'PT',label:'take() 本核空则偷取'},
    {f:'PT',t:'DEP',label:'is_blocked_by?',loopStart:'每时间片 (pull-sink 循环)'},
    {f:'DEP',t:'PT',label:'未就绪→挂起 yield',ret:true},
    {f:'PT',t:'OP',label:'get_block (pull)'},
    {f:'OP',t:'PT',label:'Block',ret:true},
    {f:'PT',t:'PT',label:'sink→灌下游;超时间片让出',self:true,loopEnd:true},
    {f:'DEP',t:'PT',label:'set_ready→wake_up 重入队',ret:true},
    {f:'PT',t:'FM',label:'eos→done 关闭',ret:true}
  ]},
  writeseq:{ actors:[
    {id:'RPC',label:'tablet_writer_add_block'},{id:'LC',label:'LoadChannel'},{id:'DW',label:'DeltaWriter'},
    {id:'MT',label:'MemTable'},{id:'FE',label:'FlushExecutor'},{id:'SW',label:'SegmentWriter'},{id:'RS',label:'RowsetWriter'}
  ], msgs:[
    {f:'RPC',t:'LC',label:'add_batch(block)'},
    {f:'LC',t:'DW',label:'按 tablet 分发 write'},
    {f:'DW',t:'MT',label:'insert 行入内存有序表',loopStart:'每批数据'},
    {f:'MT',t:'DW',label:'need_flush?',ret:true,loopEnd:true},
    {f:'DW',t:'FE',label:'MemTable 满→异步 submit flush'},
    {f:'FE',t:'MT',label:'to_block 排序+聚合'},
    {f:'MT',t:'FE',label:'有序 Block',ret:true},
    {f:'FE',t:'SW',label:'append_block 列式编码+建索引'},
    {f:'SW',t:'RS',label:'close→生成 rowset'},
    {f:'RS',t:'RPC',label:'事务提交后可见',ret:true}
  ]},
  rfseq:{ actors:[
    {id:'FE',label:'RuntimeFilterGenerator'},{id:'BJ',label:'HashJoin build'},{id:'PROD',label:'RFProducer'},
    {id:'CONS',label:'RFConsumer'},{id:'SCAN',label:'ScanOperator'}
  ], msgs:[
    {f:'FE',t:'BJ',label:'规划期挂 RF 描述到 join'},
    {f:'BJ',t:'PROD',label:'build 侧 insert 数据'},
    {f:'PROD',t:'PROD',label:'build 完成→publish',self:true},
    {f:'PROD',t:'CONS',label:'RF 就绪 signal'},
    {f:'CONS',t:'CONS',label:'acquire_expr 转过滤表达式',self:true},
    {f:'CONS',t:'SCAN',label:'RF 下推'},
    {f:'SCAN',t:'SCAN',label:'合并进 conjuncts 运行时裁行',self:true},
    {f:'SCAN',t:'FE',label:'probe 侧扫描量大减',ret:true}
  ]},
  topnseq:{ actors:[
    {id:'FE',label:'PhysicalTopN'},{id:'SS',label:'SortSink (堆)'},{id:'RP',label:'RuntimePredicate'},
    {id:'SI',label:'SegmentIterator'}
  ], msgs:[
    {f:'FE',t:'SS',label:'生成 topn + 建 topn→scan 下推'},
    {f:'SS',t:'SS',label:'堆维护 top-k',self:true,loopStart:'每批 sink'},
    {f:'SS',t:'RP',label:'get_top_value→update 第k名极值'},
    {f:'RP',t:'SI',label:'get_predicate 下推',loopEnd:true},
    {f:'SI',t:'SI',label:'zonemap 求交裁 row_bitmap',self:true},
    {f:'SI',t:'SS',label:'跳过不可能进 top-k 的 granule',ret:true}
  ]},
  cloudseq:{ actors:[
    {id:'CO',label:'Coordinator'},{id:'CN',label:'ComputeNode'},{id:'CT',label:'CloudTablet'},{id:'MM',label:'CloudMetaMgr'},{id:'MS',label:'MetaService'},{id:'CR',label:'CachedReader'},{id:'FC',label:'FileCache'},{id:'S3',label:'S3/HDFS'}
  ], msgs:[
    {f:'CO',t:'CN',label:'exec_plan_fragment(无状态节点)'},
    {f:'CN',t:'CT',label:'sync_rowsets()'},
    {f:'CT',t:'MM',label:'sync_tablet_rowsets :479'},
    {f:'MM',t:'MS',label:'get_rowset RPC :614'},
    {f:'MS',t:'MM',label:'rowset meta(最新版本)',ret:true},
    {f:'CN',t:'CR',label:'read_at_impl :285'},
    {f:'CR',t:'FC',label:'get_or_set(hash,offset)'},
    {f:'FC',t:'CR',label:'命中→直接读本地 ~10ms',ret:true},
    {f:'CR',t:'S3',label:'未命中→拉 block :570'},
    {f:'S3',t:'FC',label:'block append 写回缓存',ret:true}
  ]},
  aiseq:{ actors:[
    {id:'FE',label:'PushDownVecTopN'},{id:'SI',label:'SegmentIterator'},{id:'AI',label:'AnnIndexIter'},{id:'AR',label:'AnnIndexReader'},{id:'FA',label:'FaissIndex'}
  ], msgs:[
    {f:'FE',t:'SI',label:'topn 下推 scan(虚拟距离列)'},
    {f:'SI',t:'SI',label:'_apply_ann_topn_predicate :784',self:true},
    {f:'SI',t:'AI',label:'get_reader(ANN) :809'},
    {f:'SI',t:'AR',label:'evaluate_vector_ann_search :854'},
    {f:'AR',t:'FA',label:'ann_topn_search(HNSW/IVF) :428'},
    {f:'FA',t:'AR',label:'top-k rowid + 距离',ret:true},
    {f:'AR',t:'SI',label:'回填 distance 列 + row_bitmap',ret:true},
    {f:'SI',t:'SI',label:'无索引→降级暴力排序 :1138',self:true}
  ]},
  threadseq:{ sql:'SELECT region, sum(amount) FROM sales\nWHERE dt >= \'2026-01-01\' GROUP BY region ORDER BY 2 DESC LIMIT 10;', actors:[
    {id:'BR',label:'brpc(bthread)'},{id:'LP',label:'light_work_pool'},{id:'FM',label:'FragmentMgr'},{id:'PC',label:'PipelineCtx'},{id:'TS',label:'TaskScheduler'},{id:'SC',label:'ScannerSched'},{id:'FL',label:'FlushExecutor'}
  ], msgs:[
    {f:'BR',t:'LP',label:'try_offer 转 pthread :326'},
    {f:'LP',t:'FM',label:'exec_plan_fragment :583'},
    {f:'FM',t:'PC',label:'prepare 建算子/任务 :886'},
    {f:'FM',t:'TS',label:'submit→push_back 多核队列 :923'},
    {f:'TS',t:'TS',label:'_do_work take+execute :99',self:true},
    {f:'TS',t:'SC',label:'扫描转独立扫描池 :88'},
    {f:'TS',t:'FL',label:'flush 转 MemtableFlush 池 :113'},
    {f:'SC',t:'TS',label:'Block 结果',ret:true}
  ]},
  memseq:{ sql:'SELECT a.uid, count(*) FROM big_orders a JOIN big_users b ON a.uid=b.uid\nGROUP BY a.uid ORDER BY 2 DESC;  -- 大 HashAgg/Join,触发 try_reserve 与 spill', actors:[
    {id:'AL',label:'Allocator'},{id:'TM',label:'ThreadMemMgr'},{id:'LT',label:'MemLimiter'},{id:'GA',label:'GlobalArbitrator'},{id:'WG',label:'WorkloadGroupMgr'},{id:'RC',label:'Reclamation'}
  ], msgs:[
    {f:'AL',t:'GA',label:'sys_memory_check(alloc 前) :62'},
    {f:'AL',t:'TM',label:'consume 累加 _untracked :210'},
    {f:'TM',t:'LT',label:'攒够→flush consume :286'},
    {f:'TM',t:'TM',label:'try_reserve 三级检查 :322',self:true},
    {f:'TM',t:'GA',label:'try_reserve_process_memory :354'},
    {f:'GA',t:'TM',label:'超 water_mark→失败',ret:true},
    {f:'TM',t:'WG',label:'add_paused_query :707'},
    {f:'WG',t:'RC',label:'revoke/spill 或 cancel :652'}
  ]},
  wgseq:{ actors:[
    {id:'CO',label:'Coordinator'},{id:'QQ',label:'QueryQueue'},{id:'QT',label:'QueueToken'},{id:'BE',label:'BE WgMgr'},{id:'CG',label:'CgroupCpuCtl'},{id:'PT',label:'PipelineTask'}
  ], msgs:[
    {f:'CO',t:'QQ',label:'getToken :700'},
    {f:'QQ',t:'QT',label:'超并发→waiting 队列 :136'},
    {f:'QT',t:'QT',label:'future.get 阻塞等 :94',self:true},
    {f:'QT',t:'CO',label:'complete() 获准放行',ret:true},
    {f:'CO',t:'BE',label:'params 带 wg 下发'},
    {f:'BE',t:'CG',label:'get_or_create→绑 cgroup :62'},
    {f:'CG',t:'PT',label:'task 在组 cgroup 内执行'},
    {f:'PT',t:'BE',label:'内存超限→handle_paused_queries :316',ret:true}
  ]},
  compactseq:{ actors:[
    {id:'PR',label:'Producer'},{id:'TB',label:'Tablet'},{id:'PO',label:'CompactionPolicy'},{id:'CM',label:'CompactionMixin'},{id:'MG',label:'Merger'},{id:'SE',label:'StorageEngine'}
  ], msgs:[
    {f:'PR',t:'PR',label:'算 score 挑 tablet :647',self:true},
    {f:'PR',t:'TB',label:'submit_compaction_task :1055'},
    {f:'TB',t:'PO',label:'pick_input_rowsets(size-based) :247'},
    {f:'PO',t:'CM',label:'execute_compact :567'},
    {f:'CM',t:'MG',label:'vertical_merge_rowsets 多路归并 :292'},
    {f:'MG',t:'CM',label:'合并成新 rowset',ret:true},
    {f:'CM',t:'CM',label:'MoW 重算 delete bitmap :1203',self:true},
    {f:'CM',t:'SE',label:'老 rowset 转 stale→GC :1228'}
  ]},
  txnseq:{ actors:[
    {id:'FE',label:'FE TxnMgr'},{id:'TM',label:'BE TxnManager'},{id:'PT',label:'PublishTask'},{id:'TB',label:'Tablet'},{id:'VG',label:'VersionGraph'},{id:'RD',label:'Reader'}
  ], msgs:[
    {f:'FE',t:'TM',label:'prepare_txn 登记槽 :93'},
    {f:'TM',t:'TM',label:'commit_txn 落 rowset meta :191',self:true},
    {f:'FE',t:'PT',label:'publish version(2PC 第二阶段)'},
    {f:'PT',t:'TM',label:'publish_txn 定版本 :459'},
    {f:'TM',t:'TB',label:'add_inc_rowset 生效 :696'},
    {f:'TB',t:'VG',label:'version 端点加入 DAG :333'},
    {f:'RD',t:'TB',label:'capture_rs_readers(version) :963'},
    {f:'TB',t:'RD',label:'按 version 选可见 rowset',ret:true}
  ]},
  metaseq:{ actors:[
    {id:'CL',label:'Client/DDL'},{id:'MA',label:'Master FE'},{id:'EL',label:'EditLog'},{id:'BJ',label:'BDB-JE'},{id:'FO',label:'Follower FE'},{id:'CK',label:'Checkpoint'}
  ], msgs:[
    {f:'CL',t:'MA',label:'执行 DDL / 事务状态变更'},
    {f:'MA',t:'EL',label:'logEdit(op, writable) :1585'},
    {f:'EL',t:'BJ',label:'journal.write 分配 journalId :230'},
    {f:'BJ',t:'BJ',label:'put 到 currentJournalDB + 多数派复制',self:true},
    {f:'BJ',t:'FO',label:'复制 journal 到 Follower'},
    {f:'FO',t:'FO',label:'replayJournal 逐条 loadJournal :3081',self:true},
    {f:'MA',t:'CK',label:'周期 doCheckpoint :90'},
    {f:'CK',t:'CK',label:'loadImage→replay→saveImage→deleteJournals',self:true},
    {f:'CK',t:'FO',label:'MetaHelper 推送新 image',ret:true}
  ]},
  tabletseq:{ actors:[
    {id:'CK',label:'TabletChecker'},{id:'TB',label:'Tablet'},{id:'SC',label:'TabletScheduler'},{id:'RB',label:'Rebalancer'},{id:'BE',label:'BE'}
  ], msgs:[
    {f:'CK',t:'TB',label:'checkTablets 巡检 :236'},
    {f:'TB',t:'CK',label:'getHealth 返回 TabletStatus :542',ret:true},
    {f:'CK',t:'SC',label:'addTablet 入优先级队列 :256'},
    {f:'SC',t:'SC',label:'schedulePendingTablets 主循环 :353',self:true},
    {f:'SC',t:'SC',label:'handleTabletByTypeAndStatus 分派 :685',self:true},
    {f:'SC',t:'BE',label:'CloneTask.toThrift 下发克隆 :82'},
    {f:'BE',t:'SC',label:'克隆完成上报 → runningTablets 回收',ret:true},
    {f:'RB',t:'SC',label:'selectAlternativeTablets 均衡候选 :88'},
    {f:'SC',t:'BE',label:'均衡搬迁(复用 clone 通道)'}
  ]},
  scseq:{ actors:[
    {id:'CL',label:'Client'},{id:'SH',label:'SchemaChangeHandler'},{id:'JB',label:'SchemaChangeJobV2'},{id:'TX',label:'TxnMgr'},{id:'BE',label:'BE'}
  ], msgs:[
    {f:'CL',t:'SH',label:'ALTER TABLE :1924'},
    {f:'SH',t:'JB',label:'createJob 建影子索引/tablet :1278'},
    {f:'JB',t:'BE',label:'runPendingJob 建影子副本 :411'},
    {f:'JB',t:'TX',label:'取 watershedTxnId(双写水位) :423'},
    {f:'JB',t:'JB',label:'runWaitingTxnJob 等旧事务排空 :469',self:true},
    {f:'JB',t:'BE',label:'AlterReplicaTask 转历史 rowset :812'},
    {f:'BE',t:'BE',label:'Linked/Directly/Sorting 逐 block 转 :556',self:true},
    {f:'BE',t:'JB',label:'转换完成 + 版本追平',ret:true},
    {f:'JB',t:'JB',label:'onFinished 影子原子替换原始 :729',self:true}
  ]},
  vecseq:{ actors:[
    {id:'OP',label:'上游算子'},{id:'BK',label:'Block'},{id:'EX',label:'VExpr'},{id:'FN',label:'IFunction'},{id:'FL',label:'filter_block'},{id:'DN',label:'下游算子'}
  ], msgs:[
    {f:'OP',t:'BK',label:'产出一批列式 Block'},
    {f:'BK',t:'EX',label:'VExpr::execute(block) :138'},
    {f:'EX',t:'FN',label:'execute_impl 列级批量算 :375'},
    {f:'FN',t:'EX',label:'返回结果列(追加到 block)',ret:true},
    {f:'EX',t:'FL',label:'谓词求出 IColumn::Filter'},
    {f:'FL',t:'FL',label:'filter_block 批量裁行(SIMD count_zero) :804',self:true},
    {f:'FL',t:'DN',label:'裁剪后的 Block 交下游',ret:true}
  ]},
  fmtseq:{ actors:[
    {id:'FS',label:'FileScanner'},{id:'RD',label:'格式 Reader'},{id:'ST',label:'统计/索引'},{id:'PG',label:'数据页'},{id:'BK',label:'Block'}
  ], msgs:[
    {f:'FS',t:'RD',label:'按格式 switch → OrcReader/ParquetReader/… :991'},
    {f:'RD',t:'ST',label:'谓词下推:SArg / RowGroup min-max / ZoneMap'},
    {f:'ST',t:'RD',label:'跳过不命中的 stripe/row-group/page',ret:true},
    {f:'RD',t:'PG',label:'只解压命中的数据页(延迟物化)'},
    {f:'PG',t:'RD',label:'解码(dict/bitshuffle/RLE)',ret:true},
    {f:'RD',t:'BK',label:'装配列式 Block(+ Iceberg/Hudi delete 合并)'},
    {f:'BK',t:'FS',label:'返回一批过滤后的行',ret:true}
  ]},
  hudiseq:{ actors:[
    {id:'FE',label:'HudiScanNode'},{id:'FS',label:'FileScanner'},{id:'JR',label:'HudiJniReader'},{id:'JV',label:'Java Hudi'},{id:'PR',label:'ParquetReader'}
  ], msgs:[
    {f:'FE',t:'FE',label:'isHoodieCowTable 判 COW/MOR :179',self:true},
    {f:'FE',t:'FE',label:'MOR→generateHudiSplit(base+log) :725',self:true},
    {f:'FE',t:'FS',label:'下发 split(THudiFileDesc)'},
    {f:'FS',t:'JR',label:'MOR→HudiJniReader init :181'},
    {f:'JR',t:'JV',label:'JNI 调 Java getRecordReader :549'},
    {f:'JV',t:'JR',label:'base parquet + avro log 合并行',ret:true},
    {f:'FS',t:'PR',label:'COW→HudiParquetReader(原生) :33'},
    {f:'PR',t:'FS',label:'直接读 parquet',ret:true}
  ]},
  hiveorcseq:{ actors:[
    {id:'FE',label:'HiveScanNode'},{id:'FS',label:'FileScanner'},{id:'OR',label:'OrcReader'},{id:'ORC',label:'ORC 库'},{id:'DFS',label:'HDFS/S3'}
  ], msgs:[
    {f:'FE',t:'FE',label:'splitFile 按 targetSize 切 :498',self:true},
    {f:'FE',t:'FS',label:'下发 split'},
    {f:'FS',t:'OR',label:'init_reader :431'},
    {f:'OR',t:'OR',label:'_build_search_argument :972',self:true},
    {f:'OR',t:'ORC',label:'searchArgument 下推 stripe :1085'},
    {f:'ORC',t:'DFS',label:'只读谓词列(lazy) :1327'},
    {f:'DFS',t:'OR',label:'谓词列数据',ret:true},
    {f:'OR',t:'OR',label:'filter 过滤→读其余列 :2647',self:true},
    {f:'OR',t:'FS',label:'补分区/缺失列→Block',ret:true}
  ]},
  olapseq:{ actors:[
    {id:'SN',label:'OlapScanNode'},{id:'TR',label:'TabletReader'},{id:'BR',label:'BlockReader'},{id:'SI',label:'SegmentIterator'},{id:'SS',label:'segment 文件'}
  ], msgs:[
    {f:'SN',t:'TR',label:'init(读参数+谓词) '},
    {f:'TR',t:'BR',label:'capture_rs_readers 选可见 rowset'},
    {f:'BR',t:'SI',label:'next_batch()'},
    {f:'SI',t:'SI',label:'short key/ZoneMap 裁 block',self:true},
    {f:'SI',t:'SS',label:'读谓词列 → 行级过滤'},
    {f:'SS',t:'SI',label:'存活 row_bitmap',ret:true},
    {f:'SI',t:'SS',label:'延迟物化:仅读存活行的非谓词列'},
    {f:'SI',t:'BR',label:'向量化 Block',ret:true},
    {f:'BR',t:'SN',label:'聚合多 rowset 结果',ret:true}
  ]},
  optseq:{ actors:[
    {id:'PL',label:'NereidsPlanner'},{id:'PS',label:'Parser'},{id:'AN',label:'Analyzer'},{id:'RW',label:'Rewriter'},{id:'OP',label:'Optimizer'},{id:'MM',label:'Memo'}
  ], msgs:[
    {f:'PL',t:'PS',label:'parse→AST(LogicalPlan) :350'},
    {f:'PL',t:'AN',label:'analyze 绑定表/列/函数 :410'},
    {f:'AN',t:'PL',label:'bound LogicalPlan',ret:true},
    {f:'PL',t:'RW',label:'rewrite(RBO 规则) :431'},
    {f:'RW',t:'RW',label:'规则迭代到不动点 :149',self:true},
    {f:'PL',t:'OP',label:'optimize(CBO) :517'},
    {f:'OP',t:'MM',label:'toMemo + DeriveStatsJob :51'},
    {f:'MM',t:'MM',label:'枚举+CostAndEnforcerJob 择优 :116',self:true},
    {f:'OP',t:'PL',label:'最低代价物理计划',ret:true}
  ]},
  mvseq:{ actors:[
    {id:'JM',label:'MTMVJobMgr'},{id:'TK',label:'MTMVTask'},{id:'CC',label:'CascadesCtx'},{id:'RL',label:'MvRule'},{id:'SI',label:'StructInfo'}
  ], msgs:[
    {f:'JM',t:'TK',label:'定时触发 run() :181'},
    {f:'TK',t:'TK',label:'算需刷新分区+insert overwrite :633',self:true},
    {f:'TK',t:'JM',label:'刷新完成+refreshSnapshot',ret:true},
    {f:'CC',t:'RL',label:'查询期 rewrite() :118'},
    {f:'RL',t:'SI',label:'查询/MV 各建 StructInfo :285'},
    {f:'SI',t:'RL',label:'HyperGraph+Predicates',ret:true},
    {f:'RL',t:'RL',label:'decideMatchMode+补偿+上卷 :215',self:true},
    {f:'RL',t:'CC',label:'改写 Plan(读 MV)交 CBO 竞争',ret:true}
  ]},
  statseq:{ actors:[
    {id:'AC',label:'AutoCollector'},{id:'AM',label:'AnalysisManager'},{id:'RP',label:'StatsRepository'},{id:'IT',label:'__internal_schema'},{id:'CBO',label:'Nereids CBO'}
  ], msgs:[
    {f:'AC',t:'AC',label:'健康度<90% 触发采集 :644',self:true},
    {f:'AC',t:'AM',label:'提交 AnalysisInfo(SAMPLE/FULL)'},
    {f:'AM',t:'RP',label:'采样统计→alterColumnStatistics :318'},
    {f:'RP',t:'IT',label:'写 column_statistics 表'},
    {f:'CBO',t:'RP',label:'查询期 loadColStats :434'},
    {f:'RP',t:'IT',label:'读 ndv/min/max/hotValues'},
    {f:'IT',t:'CBO',label:'ColumnStatistic',ret:true},
    {f:'CBO',t:'CBO',label:'JoinEstimation 估行数/代价',self:true}
  ]},
  profileseq:{ actors:[
    {id:'OP',label:'Operator'},{id:'RP',label:'RuntimeProfile'},{id:'BE',label:'BE Fragment'},{id:'FE',label:'FE Coordinator'},{id:'UI',label:'SHOW PROFILE'}
  ], msgs:[
    {f:'OP',t:'RP',label:'add_counter 建计数器树'},
    {f:'OP',t:'RP',label:'SCOPED_TIMER 执行中累加',self:true},
    {f:'BE',t:'RP',label:'prune_the_tree 按 profile_level 剪枝'},
    {f:'BE',t:'FE',label:'report_exec_status 上报 profile'},
    {f:'FE',t:'FE',label:'RuntimeProfile::merge 跨 BE 聚合',self:true},
    {f:'FE',t:'FE',label:'算 min/avg/max(看倾斜)',self:true},
    {f:'UI',t:'FE',label:'查 MergedProfile / DetailProfile'},
    {f:'FE',t:'UI',label:'五段树 + 算子计数器',ret:true}
  ]}
};
// insseq = 内表写入时序,复用 writeseq 的 LSM 落盘时序(单一数据源,内表写入主题与导入主题共用)
SEQ_SPECS['insseq'] = SEQ_SPECS['writeseq'];

// 查询生命周期 · 运行时时序:FE ⇄ BE ⇄ 客户端(补"环节图"缺失的交互与时间维度)
SEQ_SPECS['qlifeseq'] = { sql:'SELECT c.region, SUM(o.amount) AS gmv\nFROM orders o JOIN customers c ON o.cust_id = c.id\nWHERE o.dt >= \'2026-01-01\' GROUP BY c.region ORDER BY gmv DESC LIMIT 10;', actors:[
    {id:'C',label:'客户端'},{id:'FE',label:'FE · StmtExecutor/Coordinator'},{id:'BE',label:'BE 集群 · Pipeline'}
  ], msgs:[
    {f:'C',t:'FE',label:'提交 SQL'},
    {f:'FE',t:'FE',label:'缓存判断→Nereids 编译→翻译→分布式规划',self:true},
    {f:'FE',t:'BE',label:'BRPC 下发 TPipelineFragmentParams(Coordinator#exec)'},
    {f:'BE',t:'BE',label:'各 Fragment 实例并行:RuntimeFilter·LocalExchange·Shuffle·必要时 Spill',self:true},
    {f:'BE',t:'FE',label:'结果分块回传(getNext → RowBatch)',ret:true},
    {f:'FE',t:'C',label:'按 MySQL 协议流式返回',ret:true},
    {f:'FE',t:'BE',label:'结束后汇总 Query Profile'}
  ]};


function renderSeqSVG(out, tid){
  const spec=SEQ_SPECS[tid]; if(!spec){out.innerHTML='';return;}
  const NS='http://www.w3.org/2000/svg';
  const sqlLines = spec.sql ? String(spec.sql).split('\n') : [];
  const sqlH = spec.sql ? (14 + sqlLines.length*15 + 10) : 0;
  const acts=spec.actors, colW=150, headH=42, topPad=20+sqlH, msgGap=46, leftPad=20;
  const W=leftPad*2+acts.length*colW;
  const ax={}; acts.forEach((a,i)=>ax[a.id]=leftPad+i*colW+colW/2);
  const startY=topPad+headH+30;
  // 计算高度 + loop 区间
  let rows=spec.msgs.length, H=startY+rows*msgGap+40;
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  svg+='<defs><marker id="sa" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--cv-edge)"/></marker>'
     +'<marker id="sar" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="var(--cv-edge)"/></marker></defs>';
  // SQL 头(说明本时序由哪条 SQL 驱动)
  if(spec.sql){
    svg+='<rect x="'+leftPad+'" y="8" width="'+(W-leftPad*2)+'" height="'+(sqlH-8)+'" rx="8" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1"/>';
    svg+='<text x="'+(leftPad+12)+'" y="24" fill="var(--cv-scan)" font-size="10.5" font-weight="700" font-family="var(--mono)">驱动 SQL</text>';
    sqlLines.forEach((ln,i)=>{ svg+='<text x="'+(leftPad+80)+'" y="'+(23+i*15)+'" fill="var(--cv-ink)" font-size="11" font-family="var(--mono)" xml:space="preserve">'+ln.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</text>'; });
  }
  // 生命线
  acts.forEach(a=>{ svg+='<line x1="'+ax[a.id]+'" y1="'+(topPad+headH)+'" x2="'+ax[a.id]+'" y2="'+(H-16)+'" stroke="var(--cv-border)" stroke-width="1"/>'; });
  // loop 框(先算区间再画背景)
  let ls=-1;
  spec.msgs.forEach((m,i)=>{ if(m.loopStart!==undefined) ls=i; if(m.loopEnd && ls>=0){
    const y1=startY+ls*msgGap-24, y2=startY+i*msgGap+14;
    svg+='<rect x="'+(leftPad+4)+'" y="'+y1+'" width="'+(W-leftPad*2-8)+'" height="'+(y2-y1)+'" rx="10" fill="#38bdf80a" stroke="#38bdf844" stroke-width="1" stroke-dasharray="4 4"/>';
    svg+='<rect x="'+(leftPad+4)+'" y="'+y1+'" width="70" height="18" rx="4" fill="var(--cv-card)" stroke="#38bdf844"/><text x="'+(leftPad+12)+'" y="'+(y1+13)+'" fill="var(--cv-scan)" font-size="10" font-weight="600" font-family="var(--sans)">loop</text>';
    svg+='<text x="'+(leftPad+80)+'" y="'+(y1+13)+'" fill="var(--cv-ink2)" font-size="10" font-family="var(--sans)">'+(spec.msgs[ls].loopStart||'')+'</text>';
    ls=-1;
  }});
  // 参与者头
  acts.forEach(a=>{
    const x=ax[a.id]-colW/2+14, w=colW-28;
    svg+='<rect x="'+x+'" y="'+topPad+'" width="'+w+'" height="'+headH+'" rx="8" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1.3"/>';
    svg+='<text x="'+ax[a.id]+'" y="'+(topPad+26)+'" fill="var(--cv-ink)" font-size="12" font-weight="600" text-anchor="middle" font-family="var(--mono)">'+a.label+'</text>';
  });
  // 消息
  spec.msgs.forEach((m,i)=>{
    const y=startY+i*msgGap;
    const x1=ax[m.f], x2=ax[m.t];
    const seqTxt=(i+1);
    if(m.self){
      const bx=x1;
      svg+='<path d="M'+bx+' '+y+' h34 v16 h-34" fill="none" stroke="var(--cv-edge)" stroke-width="1.3" marker-end="url(#sa)"/>';
      svg+='<text x="'+(bx+40)+'" y="'+(y+2)+'" fill="var(--cv-ink2)" font-size="10.5" font-family="var(--mono)">'+m.label+'</text>';
      svg+='<g class="edge-seq"><circle cx="'+(bx-14)+'" cy="'+(y+8)+'" r="9"/><text x="'+(bx-14)+'" y="'+(y+11.5)+'" text-anchor="middle">'+seqTxt+'</text></g>';
    } else {
      const col=m.ret?'#5b6472':'#8b93a3', dash=m.ret?' stroke-dasharray="5 4"':'';
      svg+='<line x1="'+x1+'" y1="'+y+'" x2="'+x2+'" y2="'+y+'" stroke="'+col+'" stroke-width="1.4"'+dash+' marker-end="url(#'+(m.ret?'sar':'sa')+')"/>';
      const mx=(x1+x2)/2;
      svg+='<text x="'+mx+'" y="'+(y-6)+'" fill="'+(m.ret?'var(--cv-ink2)':'var(--cv-ink)')+'" font-size="10.5" text-anchor="middle" font-family="var(--mono)">'+m.label+'</text>';
      svg+='<g class="edge-seq"><circle cx="'+(Math.min(x1,x2)-2)+'" cy="'+y+'" r="9"/><text x="'+(Math.min(x1,x2)-2)+'" y="'+(y+3.5)+'" text-anchor="middle">'+seqTxt+'</text></g>';
    }
  });
  svg+='</svg>';
  out.innerHTML=svg;
}

/* 数据结构说明引擎 — 参考 ClickHouse Structure-on-disk / Primary-index。 */
const DATA_SPECS={
  olapdata:{ title:'Doris 内表列存结构 (segment 内)', unit:'1024行',
    cols:['date','city','user_id','revenue'], blocks:4,
    idx:{name:'short key index (稀疏)'},
    note:'列存:每列独立文件按 block(默认 1024 行)分块;short key 稀疏索引 + 每列 ZoneMap(min/max)支撑谓词裁剪与延迟物化——扫描时先用索引/ZoneMap 跳过整块,再对存活行读列。' },
  bedata:{ title:'ORC 文件结构 (湖仓外表)', unit:'stripe',
    cols:['date','city','user_id','revenue'], blocks:4,
    idx:{name:'stripe footer + row index'},
    note:'ORC:数据按 stripe 切分,每 stripe 内列式存储 + row group 索引(默认每 10000 行);OrcReader 用 SearchArgument 下推到 stripe/row-group 级过滤,配合 lazy materialization 只解码存活行。' },
  writedata:{ title:'rowset → segment → 列存 (LSM 落盘)', unit:'segment',
    cols:['key','v1','v2','__seq__'], blocks:3,
    idx:{name:'primary key index (MoW)'},
    note:'写入 LSM:MemTable 排序聚合后落成 segment(一个 rowset 含多个 segment);列式编码同步建 short key/ZoneMap/BloomFilter/倒排;MoW 表建主键索引 + delete bitmap 实现读时去旧版本。' }
};

function renderDataSVG(out, tid){
  const spec=DATA_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▤</div><div>该主题暂无数据结构示例</div></div>';return;}
  const NS='http://www.w3.org/2000/svg';
  const colN=spec.cols.length, blocks=spec.blocks;
  const colW=150, colGap=20, blockH=64, blockGap=10, headH=34, topPad=56, leftPad=30, idxW=210;
  const W=leftPad*2 + colN*colW + (colN-1)*colGap + 60 + idxW;
  const H=topPad + headH + blocks*(blockH+blockGap) + 90;
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  svg+='<text x="'+leftPad+'" y="30" fill="var(--cv-ink)" font-size="15" font-weight="650" font-family="var(--sans)">'+spec.title+'</text>';
  spec.cols.forEach((c,ci)=>{
    const x=leftPad+ci*(colW+colGap);
    svg+='<text x="'+(x+colW/2)+'" y="'+(topPad-8)+'" fill="var(--cv-ink2)" font-size="12" text-anchor="middle" font-family="var(--mono)">'+c+'.bin</text>';
    for(let b=0;b<blocks;b++){
      const y=topPad+headH+b*(blockH+blockGap);
      const isKeyCol=ci===0;
      svg+='<rect x="'+x+'" y="'+y+'" width="'+colW+'" height="'+blockH+'" rx="6" fill="var(--cv-card)" stroke="var(--cv-warn)" stroke-width="1.2"/>';
      svg+='<rect x="'+(x+6)+'" y="'+(y+6)+'" width="'+(colW-12)+'" height="16" rx="3" fill="'+(isKeyCol?'#e8f2fd':'#f0f1f4')+'" stroke="'+(isKeyCol?'#0a94d6':'#d8dde5')+'" stroke-width="1"/>';
      svg+='<text x="'+(x+colW/2)+'" y="'+(y+18)+'" fill="'+(isKeyCol?'#0369a1':'#6e6e73')+'" font-size="10" text-anchor="middle" font-family="var(--mono)">block'+(b+1)+' 首行</text>';
      svg+='<text x="'+(x+colW/2)+'" y="'+(y+40)+'" fill="var(--cv-ink2)" font-size="14" text-anchor="middle">⋮</text>';
      svg+='<text x="'+(x+colW/2)+'" y="'+(y+56)+'" fill="var(--cv-ink2)" font-size="9.5" text-anchor="middle" font-family="var(--mono)">'+spec.unit+'</text>';
    }
  });
  const ix=leftPad+colN*(colW+colGap)+40, iy=topPad+headH;
  svg+='<rect x="'+ix+'" y="'+(topPad-2)+'" width="'+idxW+'" height="'+(blocks*(blockH+blockGap)+34)+'" rx="10" fill="var(--cv-card)" stroke="var(--cv-scan)" stroke-width="1.3"/>';
  svg+='<text x="'+(ix+idxW/2)+'" y="'+(topPad+18)+'" fill="var(--cv-scan)" font-size="12" font-weight="600" text-anchor="middle" font-family="var(--mono)">'+spec.idx.name+'</text>';
  for(let b=0;b<blocks;b++){
    const y=iy+22+b*(blockH+blockGap);
    svg+='<rect x="'+(ix+14)+'" y="'+y+'" width="'+(idxW-28)+'" height="20" rx="3" fill="var(--cv-card)" stroke="var(--cv-scan)" stroke-width="1"/>';
    svg+='<text x="'+(ix+24)+'" y="'+(y+14)+'" fill="var(--cv-scan)" font-size="10" font-family="var(--mono)">→ block'+(b+1)+' 首行前缀键</text>';
    svg+='<line x1="'+ix+'" y1="'+(y+10)+'" x2="'+(leftPad+colW)+'" y2="'+(iy+b*(blockH+blockGap)+14)+'" stroke="#38bdf833" stroke-width="1" stroke-dasharray="3 3"/>';
  }
  svg+='<foreignObject x="'+leftPad+'" y="'+(H-72)+'" width="'+(W-leftPad*2)+'" height="64"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:12px;line-height:1.7;color:#4a5568;font-family:-apple-system,sans-serif">'+spec.note+'</div></foreignObject>';
  svg+='</svg>';
  out.innerHTML=svg;
}

/* 通用结构框图引擎 — ClickHouse 风:自由布局的"带标题结构块 + 键值行 + 框间箭头"。
   用真实值展示 RF filter / TOPN 堆 / 分桶哈希表 等异构数据结构。
   spec:{ title, W, H, boxes:[{tag,color,x,y,w,rows:[[k,v]|['--',sub]]}], arrows:[[fx,fy,tx,ty,label]], note } */
const STRUCT_SPECS={
  rfstruct:{ title:'Runtime Filter 结构 · 五种类型(IN / BLOOM / IN_OR_BLOOM / MIN_MAX / BITMAP)', W:1080, H:760,
    boxes:[
      {tag:'build 侧 hash 表 (小表 orders)', color:'#5aa469', x:30, y:60, w:300, rows:[['o_id','(join key)'],['1001','...'],['1002','...'],['1005','...'],['--','distinct=1000 行 → 定 RF 类型']]},
      {tag:'IN filter (ndv 小)', color:'#38bdf8', x:410, y:44, w:300, rows:[['type','IN'],['set','{1001,1002,...,2000}'],['size','1000 个值'],['--','ndv≤1024,精确零误判']]},
      {tag:'BLOOM filter (ndv 大)', color:'#a78bfa', x:410, y:206, w:300, rows:[['type','BLOOM'],['bits','2 MB 位图'],['hash','k 个哈希函数'],['--','ndv 大,省内存有假阳']]},
      {tag:'IN_OR_BLOOM (ndv 未知/自适应)', color:'#2dd4bf', x:410, y:368, w:300, rows:[['type','IN_OR_BLOOM'],['决策','运行时按 synced_size'],['≤max_in_num','用 IN,否则转 BLOOM'],['--','FE 不确定 ndv 时默认']]},
      {tag:'MIN_MAX (范围) / BITMAP (NLJ)', color:'#d0b06a', x:410, y:530, w:300, rows:[['MIN_MAX','min=1001 max=2000'],['用途','非等值 </>/BETWEEN'],['BITMAP','bitmap_contains(NLJ)'],['--','数值裁 zonemap / 位图精确']]},
      {tag:'probe 侧 scan (大表 lineitem)', color:'#c0559f', x:780, y:280, w:270, rows:[['输入','1 亿行'],['应用 RF','l_orderkey ∈ filter'],['输出','100 万行'],['--','裁掉 99%,下推 segment']]}
    ],
    arrows:[[330,150,410,120,'ndv≤1024'],[330,175,410,280,'ndv 大'],[330,200,410,440,'未知'],[330,215,410,600,'非等值/NLJ'],[710,120,780,340,''],[710,280,780,360,'IN/BLOOM'],[710,600,780,400,'MinMax→zonemap']],
    note:'RF 五型:build 侧按 distinct key 数(ndv)决定 —— ndv 小走 IN(精确)、大走 BLOOM(省内存有假阳)、未知走 IN_OR_BLOOM(运行时按 synced_size 自适应切换)、非等值(</>/BETWEEN)附 MIN_MAX(配 zonemap 裁块)、Nested Loop Join 的 bitmap_contains 用 BITMAP(精确位图)。probe 侧 scan 拿到 filter 转成 ColumnPredicate 下推到 segment,运行时把 1 亿裁到百万级——star-schema join 提速的关键。' },
  topnstruct:{ title:'TOPN 堆结构 · ORDER BY salary DESC LIMIT 3(HeapSorter)', W:1040, H:520,
    boxes:[
      {tag:'输入流 (逐 block 灌入)', color:'#5aa469', x:30, y:70, w:260, rows:[['row','salary'],['r1','5000'],['r2','9000'],['r3','3000'],['r4','9500'],['r5','7000'],['--','不排序,逐行 push']]},
      {tag:'top-3 最小堆 (堆顶=第3名)', color:'#a78bfa', x:390, y:70, w:280, rows:[['堆顶(min)','7000 ← 第3名'],['','9000'],['','9500'],['--','size=k=3 满则比堆顶']]},
      {tag:'RuntimePredicate (极值下推)', color:'#38bdf8', x:740, y:120, w:280, rows:[['_orderby_extrem','salary ≥ 7000'],['构造','ColumnPredicate GE'],['下推','scan / segment'],['--','堆顶变则 update 刷新']]}
    ],
    arrows:[[290,180,390,180,'push 每行'],[670,180,740,200,'get_top_value'],[880,300,340,360,'zonemap 跳过 salary<7000 的 block']],
    note:'HEAP_SORT 维护一个 size=k 的最小堆:新行 salary 大于堆顶(当前第 k 名)才入堆、弹出旧堆顶。堆顶值(第 k 名极值)通过 RuntimePredicate 下推给 scan——segment 用它经 zonemap 直接跳过所有 salary < 堆顶 的 block,无需读取。堆顶随扫描不断抬高,裁剪越来越狠。' },
  loadstruct:{ title:'导入分桶结构 · 100 万行按 tablet 路由(VTabletWriter)', W:1080, H:560,
    boxes:[
      {tag:'输入 batch (Block)', color:'#5aa469', x:30, y:80, w:240, rows:[['row','user_id (分布键)'],['...','101 → hash'],['...','202 → hash'],['...','303 → hash'],['--','100 万行列式 Block']]},
      {tag:'分区+分桶计算', color:'#d0b06a', x:320, y:80, w:250, rows:[['① 分区','按 date 找 partition'],['② 分桶','crc32(user_id) % 10'],['输出','tablet_id'],['--','TabletFinder']]},
      {tag:'tablet-3 → BE-A', color:'#38bdf8', x:640, y:40, w:220, rows:[['VNodeChannel','→ BE-A'],['行数','~10 万'],['--','组 AddBlockRequest']]},
      {tag:'tablet-7 → BE-B', color:'#a78bfa', x:640, y:200, w:220, rows:[['VNodeChannel','→ BE-B'],['行数','~10 万'],['--','并行发送']]},
      {tag:'tablet-9 → BE-C', color:'#c0559f', x:640, y:360, w:220, rows:[['VNodeChannel','→ BE-C'],['行数','~10 万'],['--','各 BE DeltaWriter']]},
      {tag:'DeltaWriter → MemTable', color:'#5aa469', x:900, y:200, w:150, rows:[['写','MemTable'],['flush','segment'],['--','LSM']]}
    ],
    arrows:[[270,180,320,180,''],[570,140,640,140,'tablet-3'],[570,180,640,280,'tablet-7'],[570,220,640,430,'tablet-9'],[860,140,900,260,''],[860,280,900,280,''],[860,430,900,300,'']],
    note:'导入不是单点写:VTabletWriter 对每行先按分区键找 partition,再 crc32(分布键)%桶数 定位 tablet,同 tablet 的行攒成 batch 经 VNodeChannel 并行发往持有该 tablet 副本的 BE。各 BE 的 DeltaWriter 独立写 MemTable→flush segment。分桶均匀是导入吞吐与查询并行度的前提——分布键选择不当会导致数据倾斜。' },
  txnswim:{ title:'写入事务 · 双泳道(数据落盘 vs 事务可见)—— rowset 生成 ≠ 对读可见', W:1120, H:680,
    boxes:[
      {tag:'泳道 A · 数据落盘(物理)', color:'#5aa469', x:30, y:70, w:250, rows:[['LoadChannel','open,分 tablet'],['DeltaWriter','write→MemTable'],['flush','segment 文件'],['SegmentFileCollection','close 落盘'],['--','数据已在磁盘,但不可见']]},
      {tag:'泳道 B · 事务状态(逻辑)', color:'#4a90d9', x:30, y:360, w:250, rows:[['begin_txn','分配 Label+TxnId'],['状态','PREPARE'],['幂等','同 Label 拒重复'],['--','GlobalTransactionMgr(FE)']]},
      {tag:'COMMIT(FE 记账)', color:'#d0b06a', x:340, y:200, w:240, rows:[['commit_txn','校验 quorum 副本'],['写 EditLog','txn→COMMITTED'],['delete bitmap','MoW 提交期算'],['--','数据齐但尚未 publish']]},
      {tag:'PUBLISH(版本发布)', color:'#a78bfa', x:640, y:200, w:240, rows:[['publish_version','分发到各 BE'],['add_inc_rowset','rowset 挂到 version'],['version','++,连续无洞'],['--','EnginePublishVersionTask']]},
      {tag:'VISIBLE(对读可见)', color:'#c0559f', x:940, y:200, w:150, rows:[['读快照','capture ≤ 该 version'],['可见','✓'],['--','此刻才可查']]},
      {tag:'失败/回滚路径', color:'#f0873f', x:340, y:430, w:540, rows:[['PREPARE 超时','abort_txn,清临时 segment'],['COMMIT 后 crash','重启 replay EditLog 续 publish'],['publish 部分失败','缺副本重试,version 不推进则不可见'],['--','半成功不会脏读:未 publish 的 rowset 读不到']]}
    ],
    arrows:[[280,300,340,280,'数据就绪'],[280,430,340,360,'txn 提交'],[580,280,640,280,'COMMITTED'],[880,280,940,280,'version 生效'],[600,360,600,430,'异常']],
    note:'关键不变量:rowset 落盘 ≠ 对读可见。数据先在泳道 A 物理落盘(MemTable→segment→SegmentFileCollection::close),但只有泳道 B 的事务走到 PUBLISH、version 单调连续推进后,读端 capture 快照才会纳入该 rowset。这解释了"导入返回成功但查不到"的可见性延迟,以及半成功为何不脏读——未 publish 的数据对任何读快照都不可见。对标 ClickHouse:CH 写入靠 part 落盘 + 最终一致 merge,无 Doris 这样的显式 Label/TxnId/publish-version 强事务发布语义。' },
  versiongraph:{ title:'VersionGraph 与 MVCC · 读快照如何选版本(query snapshot → rowset set → segment)', W:1120, H:640,
    boxes:[
      {tag:'查询读快照', color:'#4a90d9', x:30, y:80, w:230, rows:[['query 到达','取当前 max_version'],['snapshot','version = 12'],['隔离','读 ≤12,后续导入不影响'],['--','读期间版本冻结']]},
      {tag:'Tablet 版本轴(rowset)', color:'#5aa469', x:310, y:60, w:300, rows:[['[0-8]','base rowset'],['[9-10]','cumulative rowset'],['[11-11]','单次导入'],['[12-12]','单次导入'],['[13-13]','导入中(未 publish)'],['--','TimestampedVersionTracker']]},
      {tag:'VersionGraph 选路', color:'#d0b06a', x:660, y:80, w:230, rows:[['目标','拼出 [0-12] 连续区间'],['最短路','[0-8]+[9-10]+[11]+[12]'],['排除','[13] 未 publish,不选'],['缺版本','有洞→报错/等待'],['--','capture_consistent_rowsets']]},
      {tag:'读取的 rowset 集合', color:'#a78bfa', x:940, y:80, w:150, rows:[['rowsets','4 个'],['→ segment','逐个读'],['MoW','应用 delete bitmap'],['--','最终行集']]},
      {tag:'Compaction 后语义保持', color:'#c0559f', x:310, y:390, w:580, rows:[['合并前','[9-10]+[11]+[12] 三个 rowset'],['cumulative','合成 [9-12] 一个新 rowset'],['旧 rowset','仍被在读快照引用→延迟 GC'],['version 连续','[0-8]+[9-12] 仍可拼出任意 ≤12 快照'],['--','合并只改物理组织,不改版本可见语义']]}
    ],
    arrows:[[260,140,310,140,'max_version=12'],[610,160,660,160,'候选 rowset'],[890,160,940,160,'选中集合'],[600,300,600,390,'后台 compaction']],
    note:'MVCC 核心:每次导入 publish 生成一个连续 version 区间的 rowset,查询到达时取 max_version 作读快照(如 12),之后经 VersionGraph 用最短路拼出 [0-12] 的 rowset 集合——未 publish 的 [13] 天然被排除,缺版本(有洞)则报错或等待。Compaction 把多个小 rowset 合成一个大 rowset(如 [9-12]),但旧 rowset 若仍被活跃读快照引用会延迟回收,且合并后版本轴仍连续,任意 ≤max 的历史快照都能拼出——这就是"Compaction 不破坏读一致性"的保证。对标 ClickHouse:CH 是 part + mark/granule,merge 后旧 part 立即可弃;Doris 的 Rowset+VersionGraph 提供更强的快照版本连续性语义。' },
  profilesrc:{ title:'可观测闭环 · 慢 SQL 如何反查到源码(query_id → Profile → Counter → Metrics → Source)', W:1120, H:600,
    boxes:[
      {tag:'① 定位慢查询', color:'#4a90d9', x:30, y:80, w:220, rows:[['入口','FE Web UI / audit log'],['拿到','query_id'],['开关','set enable_profile=true'],['--','show query profile "/<id>"']]},
      {tag:'② Query Profile 五段', color:'#5aa469', x:290, y:70, w:240, rows:[['Summary','总耗时/扫描量'],['Execution','各 Fragment'],['MergedProfile','min/avg/max 找倾斜'],['定位','最慢算子/最慢实例'],['--','RuntimeProfile 计数器树']]},
      {tag:'③ Operator Counter', color:'#d0b06a', x:570, y:80, w:250, rows:[['ScanRows/ScanBytes','扫描量→存储层'],['ExecTime','算子自身耗时'],['WaitForDependency','阻塞→调度/RF'],['MemoryUsage','内存→是否 spill'],['--','TUnit 决定单位']]},
      {tag:'④ 源码模块', color:'#a78bfa', x:860, y:80, w:230, rows:[['ScanRows 大','SegmentIterator 未裁'],['ExecTime 高','看具体 OperatorX'],['WaitForDep','ScannerScheduler/RF'],['spill','PartitionedAggSink'],['--','counter→类/文件可反查']]},
      {tag:'⑤ 与 FE/BE Metrics 交叉', color:'#c0559f', x:290, y:380, w:530, rows:[['单查询 profile + 全局 metrics 一起看',''],['doris_be_* (BE)','compaction/内存/IO 速率'],['fe metrics','连接/query 并发/失败率'],['判定','单点慢 vs 集群性问题'],['--','profile 定位算子,metrics 定位资源']]}
    ],
    arrows:[[250,140,290,140,'query_id'],[530,140,570,140,'最慢算子'],[820,140,860,140,'counter 异常'],[540,300,540,380,'交叉验证']],
    note:'排障闭环(ClickHouse 有 system.query_log/trace_log,Doris 用 Profile+Metrics):① audit log 拿 query_id → set enable_profile=true 取 Profile;② 五段树看 Summary 总量、MergedProfile 的 min/avg/max 找倾斜实例;③ 下钻 Operator Counter——ScanRows 大=存储层没裁干净、ExecTime 高=该算子重、WaitForDependency 高=卡调度或等 RF、MemoryUsage 高=触发 spill;④ 每个 counter 都能反查到源码类/文件(如 ScanRows→SegmentIterator、spill→PartitionedAggSinkOperator);⑤ 再和 FE/BE Metrics 交叉,区分"单查询算子慢"还是"集群资源瓶颈"。这条链让地图从"看架构"升级为"能排障"。' },
  fmtcompare:{ title:'存储格式并行对比 · 读取方式(上)+ 文件结构(下),外表三格式 + 内表 V2/V3 同屏', W:1476, stacked:true,
    boxes:[
      {tag:'Hive ORC · 读取', color:'#4a90d9', x:24, y:60, w:270, rows:[['FE 切分','HiveScanNode.getSplits'],['谓词下推','_build_search_argument → SearchArgument'],['三级跳过','file → stripe → row group'],['延迟物化','先读谓词列,命中再回填其余列'],['--','vorc_reader.cpp']]},
      {tag:'Hudi · 读取', color:'#5aa469', x:314, y:60, w:270, rows:[['FE 切分','HudiScanNode.getSplits'],['COW 表','原生 HudiParquetReader'],['MOR 表','JNI 合并 base 文件 + log 增量'],['判定','isHoodieCowTable'],['--','hudi_reader.cpp / JNI']]},
      {tag:'Iceberg · 读取', color:'#26a69a', x:604, y:60, w:270, rows:[['FE 切分','IcebergScanNode.getSplits'],['base 文件','Parquet / ORC reader'],['delete 文件','position / equality (v2)'],['时间旅行','snapshot id / timestamp'],['--','iceberg delete 合并']]},
      {tag:'内表 V2 · 读取(旧格式)', color:'#a78bfa', x:894, y:60, w:262, rows:[['入口','SegmentIterator'],['打开代价','先全量反序列化 Footer 里所有列 meta'],['三索引','Ordinal / ZoneMap / Bloom'],['下推','page 级裁剪 + 延迟物化'],['适用','普通表(几十列)']]},
      {tag:'内表 V3 · 读取(4.1.0+ 宽表)', color:'#c4b5fd', x:1184, y:60, w:262, rows:[['入口','SegmentIterator(扫描路径与 V2 完全一致)'],['★核心差异','精简 Footer,只按需拉查询用到的列 meta'],['收益','宽表/VARIANT/对象存储 打开快 ~16×'],['三索引/下推','与 V2 完全相同,正交于格式'],['启用','PROPERTIES "storage_format"="V3"']]},
      {tag:'ORC 文件结构', color:'#4a90d9', x:24, y:340, w:270, rows:[['PostScript','压缩类型 / Footer 长度'],['Footer','schema + stripe 位置 + file 统计'],['Stripe(~64MB)','StripeFooter + Index + Data'],['RowGroup(1万行)','row index 存 min/max'],['Stream','PRESENT/DATA/LENGTH/DICT']]},
      {tag:'Hudi(表格式叠 Parquet)', color:'#5aa469', x:314, y:340, w:270, rows:[['底层','base = Parquet'],['COW','只读 base'],['MOR','base + avro log 合并'],['表格式','管快照 / 增量 / 删除'],['跳过粒度','File → RowGroup → Page']]},
      {tag:'Iceberg(表格式叠 Parquet/ORC)', color:'#26a69a', x:604, y:340, w:270, rows:[['底层','base = Parquet / ORC'],['manifest','文件清单 + 分区统计'],['delete file','position / equality'],['快照','snapshot 元数据 + schema 演进'],['跳过粒度','File → RowGroup → Page']]},
      {tag:'内表 Segment V2 结构(旧)', color:'#a78bfa', x:894, y:340, w:262, rows:[['Footer','version=1;集中打包全部列 ColumnMetaPB'],['★痛点','列数上千时 Footer 膨胀到几 MB,查2列也全量反序列化'],['数值编码','BitShuffle(默认)'],['字符串','旧 BinaryPlain(尾部带偏移表)'],['三索引/DataPage','Ordinal/ZoneMap/Bloom + 页压缩 LZ4/ZSTD']]},
      {tag:'内表 Segment V3 结构(宽表)', color:'#c4b5fd', x:1184, y:340, w:262, rows:[['Footer','version=2;仅存指向各列 meta 的轻量指针'],['★列 meta 区','从 Footer 拆出为独立区域(CMO),按需加载'],['数值编码','PLAIN(原始二进制,配 LZ4/ZSTD 更快)'],['字符串/JSONB','BinaryPlain V2([len varuint][raw],去偏移表)'],['三索引/DataPage','与 V2 布局不变']]}
    ],
    arrows:[],
    note:'★格式核心差异(V2 vs V3):旧格式(V2)把一个 Segment 内所有列的 ColumnMetaPB 集中打包在文件末尾 Footer——打开 Segment 必须先全量反序列化整个 Footer,哪怕 SQL 只查 2 列也要付全部代价;列数上千时 Footer 自身膨胀到几 MB,对象存储上网络延迟进一步放大。V3(Apache Doris 4.1.0+,建表 PROPERTIES "storage_format"="V3")把列元数据从 Footer 拆出、放到文件中独立区域(Column Meta Region / CMO),Footer 只保留指向各列 meta 的轻量指针,真正用到哪列才去拉对应 meta——这是宽表提速的主因。另两项:数值类型默认编码 BitShuffle→PLAIN;字符串/JSONB 用 BinaryPlain V2([长度 varuint][原始数据] 流式布局,去掉旧编码尾部偏移表)。实测 7000 列/1 万 Segment:Segment 打开 65s→4s(快 16×)、峰值内存 60GB→<1GB(降 60×)。适用:几百列以上宽表、含 VARIANT 列、部署在 S3/OSS 等对象/分层存储;几十列普通表无需切换。读取扫描路径 V2/V3 完全一致(同走 SegmentIterator + 三索引),差异只在写出的元数据布局与编码。' },
  integstruct:{ title:'内表存储结构 + 索引原理(并行)· 顶部示例表 → 存储布局 vs 索引加速', W:1160, H:660,
    boxes:[
      {tag:'示例表 site_visit (DUPLICATE KEY(visit_date,user_id) DISTRIBUTED BY HASH(user_id) BUCKETS 10)', color:'#5db0f0', x:30, y:56, w:1100, rows:[['visit_date DATE | user_id BIGINT | page VARCHAR | duration INT','4 列,前2列=排序键(short key)'],['分区','按 visit_date RANGE 分区'],['分桶','HASH(user_id) % 10 → 10 个 Tablet'],['--','一行数据在:某分区 → 某 Tablet → 某 Rowset → 某 Segment → 某 Page']]},
      {tag:'① 存储结构(数据怎么存)', color:'#6fb87d', x:30, y:250, w:540, rows:[['Tablet','分区×分桶的最小管理单元,多副本'],['Rowset','一次导入=一个 Rowset,不可变,MVCC 版本'],['Segment(.dat)','列式;每列独立成 ColumnData'],['Page(64KB)','列内分页;编码 RLE/dict/bitshuffle + 压缩 LZ4/ZSTD'],['SegmentFooter','ColumnMetaPB + 索引位置 + 统计'],['--','列存 = 同列连续 → 高压缩比 + 向量化友好']]},
      {tag:'② 索引原理(怎么少扫)', color:'#d0b06a', x:590, y:250, w:540, rows:[['ShortKeyIndex','前缀排序键稀疏索引 → 定位起始 block'],['ZoneMap','每 page/segment 存 min/max/null → 范围谓词跳 page'],['BloomFilter','高基数列等值谓词 → 概率跳 page(可选建)'],['BitmapIndex','低基数列 → 位图交并快速过滤'],['InvertedIndex','文本 MATCH / 等值 → 倒排跳行(可选建)'],['--','裁剪顺序:分区→Tablet→Rowset→Segment→ZoneMap/BF 跳 Page→行级']]}
    ],
    arrows:[[300,178,300,250,'物理落盘'],[860,178,860,250,'建索引加速']],
    note:'一张表两个视角并行看:① 存储结构(左)——一行数据落到 Tablet(分区×分桶)→ Rowset(一次导入,不可变+MVCC)→ Segment(列式)→ Page(编码+压缩),列存让同列连续、压缩比高、向量化友好;② 索引原理(右)——ShortKey 稀疏索引定位起始、ZoneMap 用 min/max 跳 page、BloomFilter/Bitmap/Inverted 按列特征进一步跳。二者协同:存储把数据分层组织,索引在每层留统计,查询自顶向下逐层裁剪(分区→Tablet→Rowset→Segment→Page→行),越早跳过越省 IO——这正是列存 OLAP 快的根因。' }
};

function renderStructSVG(out, tid){
  const spec=STRUCT_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▤</div><div>暂无结构图</div></div>';return;}
  const NS='http://www.w3.org/2000/svg', W=spec.W;
  const stacked=!!spec.stacked;
  // 按中文宽度估算的按词换行(英数.-_ 视为整词,中文逐字)
  function wrapK(raw, px){
    raw=String(raw); const per=Math.max(4, Math.floor(px/6.6));
    const toks=raw.match(/[A-Za-z0-9_.:\-]+|[^A-Za-z0-9_.:\-]/g)||[raw];
    let lines=[], cur='';
    const wof=s=>s.replace(/[^\x00-\xff]/g,'xx').length;
    toks.forEach(tk=>{
      if(wof(cur)+wof(tk)>per && cur.length>0){ lines.push(cur); cur=''; }
      if(wof(tk)>per){ if(cur){lines.push(cur);cur='';} for(let i=0;i<tk.length;i+=per){lines.push(tk.slice(i,i+per));} cur=lines.pop()||''; }
      else cur+=tk;
    });
    if(cur) lines.push(cur);
    return lines.length?lines:[''];
  }
  // 预计算每个 box 高度(stacked 模式行高按内容换行动态算)
  const lineH=15, padTop=32, padBot=10;
  const boxH=b=>{
    if(!stacked) return padTop+b.rows.length*22+8;
    let h=padTop;
    b.rows.forEach(r=>{
      if(r[0]==='--'){ h+=lineH*(wrapK(r[1], b.w-28).length)+8; return; }
      const kl=wrapK(r[0], b.w-28).length, vl=wrapK(r[1], b.w-28).length;
      h+=lineH*(kl+vl)+9;
    });
    return h+padBot;
  };
  const noteLines=stacked?wrapK(spec.note, W-72).length:2;
  const noteH=stacked?Math.max(64, noteLines*20+16):64;
  const H=spec.H||(Math.max.apply(null, spec.boxes.map(b=>b.y+boxH(b)))+noteH+40);
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  svg+='<defs><marker id="stArr-'+tid+'" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="var(--cv-edge)"/></marker></defs>';
  svg+='<text x="30" y="30" fill="var(--cv-ink)" font-size="15" font-weight="650" font-family="var(--sans)">'+spec.title+'</text>';
  (spec.arrows||[]).forEach(a=>{
    const fx=a[0],fy=a[1],tx=a[2],ty=a[3],label=a[4];
    svg+='<path d="M'+fx+','+fy+' C'+((fx+tx)/2)+','+fy+' '+((fx+tx)/2)+','+ty+' '+tx+','+ty+'" fill="none" stroke="var(--cv-edge)" stroke-width="1.4" marker-end="url(#stArr-'+tid+')"/>';
    if(label){ svg+='<text x="'+((fx+tx)/2)+'" y="'+((fy+ty)/2-5)+'" fill="var(--cv-ink2)" font-size="10" text-anchor="middle" font-family="var(--mono)">'+label+'</text>'; }
  });
  const esc2=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  spec.boxes.forEach(b=>{
    const bh=boxH(b);
    svg+='<text x="'+(b.x+b.w/2)+'" y="'+(b.y-8)+'" fill="'+b.color+'" font-size="11.5" font-weight="600" text-anchor="middle" font-family="var(--mono)">'+b.tag+'</text>';
    svg+='<rect x="'+b.x+'" y="'+b.y+'" width="'+b.w+'" height="'+bh+'" rx="10" fill="var(--cv-card)" stroke="'+b.color+'" stroke-width="1.3"/>';
    if(stacked){
      let cy=b.y+22;
      b.rows.forEach(r=>{
        if(r[0]==='--'){
          const vls=wrapK(r[1], b.w-28);
          svg+='<line x1="'+(b.x+10)+'" y1="'+(cy-8)+'" x2="'+(b.x+b.w-10)+'" y2="'+(cy-8)+'" stroke="'+b.color+'44" stroke-width="1"/>';
          vls.forEach((ln,i)=>{ svg+='<text x="'+(b.x+14)+'" y="'+(cy+i*lineH+3)+'" fill="'+b.color+'cc" font-size="10.5" font-weight="600" font-family="var(--mono)">'+esc2(ln)+'</text>'; });
          cy+=lineH*vls.length+8;
        } else {
          const kls=wrapK(r[0], b.w-28), vls=wrapK(r[1], b.w-28);
          kls.forEach((ln,i)=>{ svg+='<text x="'+(b.x+14)+'" y="'+(cy+i*lineH)+'" fill="var(--cv-ink2)" font-size="10.5" font-weight="600" font-family="var(--mono)">'+esc2(ln)+'</text>'; });
          cy+=lineH*kls.length;
          vls.forEach((ln,i)=>{ svg+='<text x="'+(b.x+18)+'" y="'+(cy+i*lineH+1)+'" fill="var(--cv-ink2)" font-size="11" font-family="var(--sans)">'+esc2(ln)+'</text>'; });
          cy+=lineH*vls.length+9;
        }
      });
    } else {
      const rowH=22;
      b.rows.forEach((r,ri)=>{
        const ry=b.y+24+ri*rowH;
        if(r[0]==='--'){ svg+='<line x1="'+(b.x+10)+'" y1="'+(ry-13)+'" x2="'+(b.x+b.w-10)+'" y2="'+(ry-13)+'" stroke="'+b.color+'44" stroke-width="1"/>'; svg+='<text x="'+(b.x+14)+'" y="'+(ry+1)+'" fill="'+b.color+'bb" font-size="10.5" font-family="var(--mono)">'+r[1]+'</text>'; }
        else { svg+='<text x="'+(b.x+14)+'" y="'+(ry+1)+'" fill="var(--cv-ink2)" font-size="11" font-family="var(--mono)">'+r[0]+'</text>'; svg+='<text x="'+(b.x+b.w-14)+'" y="'+(ry+1)+'" fill="var(--cv-ink2)" font-size="11" text-anchor="end" font-family="var(--mono)">'+r[1]+'</text>'; }
      });
    }
  });
  svg+='<foreignObject x="30" y="'+(H-noteH-4)+'" width="'+(W-60)+'" height="'+(noteH+2)+'"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:12px;line-height:1.7;color:#4a5568;font-family:-apple-system,sans-serif">'+spec.note+'</div></foreignObject>';
  svg+='</svg>';
  out.innerHTML=svg;
}

/* 示例 CASE 引擎 — 参考 ClickHouse Merge-time Data Transformation。
   用一条具体 SQL 贯穿,横向展示数据漏斗:每阶段剩余行数如何逐级收敛。
   spec: { sql, source:{rows,label}, stages:[{name, rows, note, drop?}] } */
const CASE_SPECS={
  becase:{ sql:'SELECT o_orderkey, o_totalprice FROM hive.orders\nWHERE o_orderdate >= \'1995-01-01\'\n  AND o_orderstatus = \'F\' LIMIT 1000',
    source:{rows:15000000, label:'ORC 外表 (60 stripe)'},
    stages:[
      {name:'① 文件/分区裁剪', rows:5000000, note:'FE HMS 按 o_orderdate 分区裁剪 split → 20 stripe'},
      {name:'② stripe 统计', rows:2500000, note:'OrcReader 用 stripe footer min/max 跳过 status≠F 的 stripe'},
      {name:'③ row group 索引', rows:800000, note:'SearchArgument 下推到 row group(每 1w 行)级'},
      {name:'④ lazy 物化', rows:120000, note:'先解码谓词列过滤,存活行才解码 o_totalprice'},
      {name:'⑤ LIMIT', rows:1000, note:'满 1000 行即短路停止,不再拉后续 batch'}
    ],
    accent:'var(--cv-ink)' },
  cloudcase:{ sql:'-- 存算分离:冷/热查询对比\nSELECT count(*) FROM events\nWHERE dt = \'2024-06-01\'',
    source:{rows:200000000, label:'events(数据在 S3 对象存储)'},
    stages:[
      {name:'① MetaService 取元数据', rows:200000000, note:'CloudMetaMgr 拉 tablet/rowset 元数据(与本地缓存比对版本)'},
      {name:'② 分区裁剪', rows:20000000, note:'dt=2024-06-01 只需 1 个分区 → 2000 万行相关'},
      {name:'③ FileCache 查询(热)', rows:20000000, note:'block 命中本地 SSD 缓存 → 直接读,~10ms'},
      {name:'③ FileCache 未命中(冷)', rows:20000000, note:'miss → 从 S3 拉 block 到本地缓存,首次 ~500ms'},
      {name:'④ 向量化 count', rows:1, note:'count(*) 走 segment 行数元信息,几乎零解码'}
    ],
    accent:'var(--cv-scan)' },
  threadcase:{ sql:'-- 一次查询的线程流转时间线\nSELECT ... (一次典型查询)', unit:'μs',
    source:{rows:1000, label:'brpc bthread 收包', disp:'0 μs'},
    stages:[
      {name:'① 转投 light_work_pool', rows:950, disp:'+5 μs', note:'bthread 把闭包 try_offer 到 pthread 池,避免阻塞 brpc'},
      {name:'② FragmentMgr 起 task', rows:900, disp:'+50 μs', note:'exec_plan_fragment 建 PipelineFragmentContext'},
      {name:'③ TaskScheduler 调度', rows:800, disp:'+100 μs', note:'PipelineTask 入 MultiCoreTaskQueue,work-stealing 取'},
      {name:'④ ScannerScheduler 扫描', rows:600, disp:'+2 ms', note:'扫描任务转独立扫描池,与执行池隔离并行'},
      {name:'⑤ pull-sink 执行', rows:400, disp:'+50 ms', note:'算子 pull Block;缺数据 block 到 Dependency 让出线程'},
      {name:'⑥ 结果返回', rows:200, disp:'+80 ms', note:'ExchangeSink 汇聚,全程无线程阻塞空转'}
    ],
    accent:'var(--cv-ink)' },
  veccase:{ sql:"SELECT price * 1.1 AS p2 FROM sales\nWHERE revenue > 100  -- 一个 4096 行的 Block 如何被向量化处理", unit:'行',
    source:{rows:4096, label:'一个 Block(4096 行)', disp:'列式输入'},
    stages:[
      {name:'① VExpr 求谓词', rows:4096, disp:'算 Filter', note:'revenue>100 对整列批量比较,产出 UInt8 Filter 向量'},
      {name:'② filter_block 裁行', rows:1200, disp:'SIMD 批量裁', note:'count_zero_num(SSE2)预算大小,对每列一次性裁掉 0 位行'},
      {name:'③ VExpr 算投影', rows:1200, disp:'price*1.1', note:'对裁剪后的列批量算 price*1.1,IFunction::execute_impl 列级运算'},
      {name:'④ 追加结果列', rows:1200, disp:'新增 p2 列', note:'结果作为新 ColumnVector<Double> 追加进 Block'},
      {name:'⑤ 交下游算子', rows:1200, disp:'Block 流转', note:'裁剪+投影后的 Block 按 pull/push 契约交给下游'}
    ],
    accent:'var(--cv-ink)' },
  fmtcase:{ sql:"-- ORC 外表:一列存 1 亿行,查一天且高消费\nSELECT * FROM hive.sales\nWHERE dt='2024-06-01' AND revenue>1000", unit:'行',
    source:{rows:100000000, label:'ORC 文件 1 亿行', disp:'全量'},
    stages:[
      {name:'① SearchArgument 下推', rows:100000000, disp:'SArg 构建', note:'dt/revenue 谓词编译成 ORC SearchArgument'},
      {name:'② stripe 级跳过', rows:8000000, disp:'跳 92% stripe', note:'ORC 用内建统计跳过 dt≠目标 的 stripe(解压前)'},
      {name:'③ row-group 级裁剪', rows:1200000, disp:'ZoneMap 裁', note:'命中 stripe 内再按 row-group 统计裁 revenue'},
      {name:'④ 延迟物化', rows:1200000, disp:'只读命中行', note:'先读谓词列算 sel,只物化命中行的其余列'},
      {name:'⑤ 输出 Block', rows:1200000, disp:'1.2% 数据', note:'最终只解码/传输 ~1.2% 的原始数据'}
    ],
    accent:'var(--cv-ink)' },
  hudicase:{ sql:'-- 读 Hudi MOR 表(base + log 合并)\nSELECT * FROM hudi_catalog.db.orders_mor', unit:'文件',
    source:{rows:100, label:'一个 file slice', disp:'base+log'},
    stages:[
      {name:'① FE 判 COW/MOR', rows:90, disp:'MOR', note:'isHoodieCowTable=false → MOR,需合并 log'},
      {name:'② 取最新 file slice', rows:80, disp:'base parquet', note:'getLatestMergedFileSlicesBeforeOrOn(queryInstant)'},
      {name:'③ 打包 base + log', rows:70, disp:'+avro log', note:'generateHudiSplit:base parquet + delta log files'},
      {name:'④ JNI 调 Java 合并', rows:50, disp:'HudiJniReader', note:'走 JNI,Java Hudi getRecordReader 合并 base+log'},
      {name:'⑤ 返回合并后行', rows:50, disp:'最新快照', note:'log 的更新/删除应用到 base → 最新视图'}
    ],
    accent:'var(--cv-ink)' },
};

function fmtRows(n){ if(n>=1e8)return (n/1e8).toFixed(n%1e8?1:0)+'亿'; if(n>=1e4)return (n/1e4).toFixed(n%1e4?0:0)+'万'; return ''+n; }

// SQL 语法高亮:把一行 SQL 分词成带色 <tspan>(供 SVG <text> 内使用)。GitHub-dark 配色。
// 返回 innerHTML 字符串;color 表:关键字紫、函数蓝、字符串绿、数字橙、注释灰、标点默认。
const SQL_KW=/^(SELECT|FROM|WHERE|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AS|AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END|DISTINCT|UNION|ALL|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|VIEW|MATERIALIZED|WITH|DESC|ASC|USING|EXISTS|COUNT|OVER|PARTITION)$/i;
const SQL_FN=/^(sum|count|avg|min|max|cast|coalesce|concat|substr|substring|date_format|now|abs|round|floor|ceil|if|ifnull|nullif|row_number|rank|dense_rank|lag|lead|ndv|hll_union|bitmap_union|array_agg)$/i;
function sqlHighlight(line){
  const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // 先切注释
  const ci=line.indexOf('--');
  let code=line, cmt='';
  if(ci>=0){ code=line.slice(0,ci); cmt=line.slice(ci); }
  let outp='';
  // 分词:标识符/数字/字符串/其它
  const re=/('[^']*'|"[^"]*"|`[^`]*`|\b\d+(?:\.\d+)?\b|[A-Za-z_][A-Za-z0-9_]*|\s+|[^\sA-Za-z0-9_'"`]+)/g;
  let m;
  while((m=re.exec(code))!==null){
    const tk=m[0];
    let color=null;
    if(/^\s+$/.test(tk)){ outp+=esc(tk); continue; }
    if(/^['"`]/.test(tk)) color='#7ee787';                 // 字符串 绿
    else if(/^\d/.test(tk)) color='#ffa657';                // 数字 橙
    else if(SQL_KW.test(tk)) color='#ff7b72';               // 关键字 红/紫
    else if(SQL_FN.test(tk)) color='#79c0ff';               // 函数 蓝
    else if(/^[^\sA-Za-z0-9_'"`]+$/.test(tk)) color='#8b949e'; // 标点 灰
    else color='#c9d1d9';                                   // 标识符 浅灰
    outp+='<tspan fill="'+color+'">'+esc(tk)+'</tspan>';
  }
  if(cmt) outp+='<tspan fill="#6e7681" font-style="italic">'+esc(cmt)+'</tspan>';
  return outp;
}

const PLAN_NODE=/^(PLAN|FRAGMENT|RESULT|SINK|AGGREGATE|EXCHANGE|DATA|STREAM|OlapScanNode|ScanNode|SCAN|HASH|JOIN|BUILD|SOURCE|SORT|UNION|PROJECT|FILTER|REPEAT|ASSERT|TOP|EXPLAIN|DESC|DESCRIBE|PARSED|ANALYZED|REWRITTEN|LOGICAL|OPTIMIZED|PHYSICAL|SHAPE|MEMO|DISTRIBUTED|ALL|VERBOSE|TREE|GRAPH|DUMP|PROCESS|set|show|query|profile|enable_profile|true|SELECT|FROM|WHERE)$/;
const PLAN_MOD=/^(Coordinator|GATHER|BROADCAST|PARTITIONED|HASH_PARTITIONED|merge|finalize|update|serialize|INNER|OUTER|LEFT|RIGHT|SEMI|ANTI|CROSS|BE|N)$/;
// EXPLAIN 物理计划着色:节点类型/分发修饰/表名/序号
function planHighlight(text){
  const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const re=/('[^']*'|\b\d+(?:\.\d+)?\b|[A-Za-z_][A-Za-z0-9_]*|\s+|[^\sA-Za-z0-9_'"`]+)/g;
  let outp='', m, sawColon=false;
  while((m=re.exec(text))!==null){
    const tk=m[0]; let color;
    if(/^\s+$/.test(tk)){ outp+=esc(tk); continue; }
    if(tk===':'){ sawColon=true; outp+='<tspan fill="#8b949e">:</tspan>'; continue; }
    if(sawColon && /^[A-Za-z_]/.test(tk)) color='#7ee787';        // 表名 绿
    else if(/^\d/.test(tk)) color='#ffa657';                       // 序号 橙
    else if(PLAN_NODE.test(tk)) color='#79c0ff';                   // 节点类型 蓝
    else if(PLAN_MOD.test(tk)) color='#d2a8ff';                    // 分发/合并修饰 紫
    else if(/^[^\sA-Za-z0-9_'"`]+$/.test(tk)) color='#8b949e';     // 标点 灰
    else color='#c9d1d9';                                          // 其它 浅灰
    outp+='<tspan fill="'+color+'">'+esc(tk)+'</tspan>';
  }
  return outp;
}

function renderCaseSVG(out, tid){
  const spec=CASE_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▤</div><div>该主题暂无示例 CASE</div></div>';return;}
  const NS='http://www.w3.org/2000/svg';
  const rows=[{name:spec.source.label,rows:spec.source.rows,note:'',src:true}].concat(spec.stages);
  const cardW=220, cardH=92, gapY=30, leftPad=40, topPad=140, barMaxW=cardW-30;
  const maxRows=spec.source.rows;
  const W=760, H=topPad + rows.length*(cardH+gapY) + 20;
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  // SQL 卡片
  svg+='<rect x="'+leftPad+'" y="24" width="'+(W-leftPad*2)+'" height="84" rx="10" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1.2"/>';
  svg+='<text x="'+(leftPad+16)+'" y="46" fill="var(--cv-ink2)" font-size="11" font-family="var(--mono)">示例 SQL</text>';
  spec.sql.split('\n').forEach((ln,i)=>{
    svg+='<text x="'+(leftPad+16)+'" y="'+(66+i*17)+'" font-size="12.5" font-family="var(--mono)">'+sqlHighlight(ln)+'</text>';
  });
  // 漏斗:纵向阶段
  const cx=leftPad+cardW/2;
  rows.forEach((s,i)=>{
    const y=topPad+i*(cardH+gapY);
    const frac=s.rows/maxRows;
    const barW=Math.max(6, barMaxW*Math.pow(frac,0.18)); // 非线性,防止后段过窄
    const isSrc=s.src;
    svg+='<rect x="'+leftPad+'" y="'+y+'" width="'+cardW+'" height="'+cardH+'" rx="11" fill="var(--cv-card)" stroke="'+(isSrc?'#c9cfda':'#d8dde5')+'" stroke-width="'+(isSrc?1.4:1)+'"/>';
    svg+='<rect x="'+leftPad+'" y="'+y+'" width="3.5" height="'+cardH+'" rx="1.75" fill="'+spec.accent+'"/>';
    svg+='<text x="'+(leftPad+16)+'" y="'+(y+24)+'" fill="var(--cv-ink)" font-size="13" font-weight="600" font-family="var(--sans)">'+s.name+'</text>';
    // 行数条
    svg+='<rect x="'+(leftPad+16)+'" y="'+(y+34)+'" width="'+barMaxW+'" height="10" rx="5" fill="var(--cv-card-alt)"/>';
    svg+='<rect x="'+(leftPad+16)+'" y="'+(y+34)+'" width="'+barW+'" height="10" rx="5" fill="'+spec.accent+'"/>';
    svg+='<text x="'+(leftPad+cardW-14)+'" y="'+(y+24)+'" fill="var(--cv-ink2)" font-size="12.5" font-weight="700" text-anchor="end" font-family="var(--mono)">'+(s.disp!==undefined?s.disp:(fmtRows(s.rows)+' '+(spec.unit||'行')))+'</text>';
    // 说明
    if(s.note){
      svg+='<foreignObject x="'+(leftPad+cardW+24)+'" y="'+(y+12)+'" width="'+(W-leftPad*2-cardW-24)+'" height="'+(cardH-16)+'"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:12px;line-height:1.6;color:#4a5568;font-family:-apple-system,sans-serif">'+s.note+'</div></foreignObject>';
    }
    // 收敛箭头 + 收敛率
    if(i<rows.length-1){
      const ny=y+cardH, my=ny+gapY;
      svg+='<line x1="'+cx+'" y1="'+ny+'" x2="'+cx+'" y2="'+my+'" stroke="'+spec.accent+'" stroke-width="1.5" marker-end="url(#caseArr-'+tid+')"/>';
      if(!spec.unit){
        const nextFrac=rows[i+1].rows/s.rows;
        const pct=nextFrac<1?('保留 '+(nextFrac*100<1?(nextFrac*100).toFixed(2):(nextFrac*100).toFixed(nextFrac*100<10?1:0))+'%'):'—';
        svg+='<rect x="'+(cx+8)+'" y="'+(ny+gapY/2-9)+'" width="78" height="18" rx="9" fill="var(--cv-card)" stroke="'+spec.accent+'44" stroke-width="1"/>';
        svg+='<text x="'+(cx+47)+'" y="'+(ny+gapY/2+3)+'" fill="'+spec.accent+'" font-size="10" text-anchor="middle" font-family="var(--mono)">'+pct+'</text>';
      }
    }
  });
  svg+='<defs><marker id="caseArr-'+tid+'" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="'+spec.accent+'"/></marker></defs>';
  svg+='</svg>';
  out.innerHTML=svg;
}

/* Merge-time 数据流转引擎 — 参考 ClickHouse Merge-time Data Transformation。
   用具体数据值贯穿:源行 → 每 rowset 部分聚合状态 → compaction 合并 → 读时再合并。
   spec:{ ddl, cols:[名], parts:[{tag,color,rows:[[..]]}], merged:{rows:[[..]]}, readSql, note } */
const MERGE_SPECS={
  aggmerge:{
    title:'AGGREGATE 模型 · 预聚合 → compaction 合并(Doris 版 Merge-time Transformation)',
    ddl:['CREATE TABLE region_lat (','  region VARCHAR,  -- AGG KEY','  max_lat MAX INT,  -- 部分状态','  sum_lat SUM INT,  cnt SUM INT  -- avg=sum/cnt',') AGGREGATE KEY(region)'],
    cols:['region','max_lat','sum(sum_lat,cnt)'],
    parts:[
      {tag:'rowset-1 (load A)', color:'#4a90d9', rows:[['EMEA','200','300, 2'],['APAC','80','80, 1']]},
      {tag:'rowset-2 (load B)', color:'#c0559f', rows:[['APAC','70','180, 3']]}
    ],
    merged:{tag:'compaction 合并后', rows:[['EMEA','200','300, 2'],['APAC','80','260, 4']]},
    readSql:['-- 读时再合并(未 compaction 的 rowset)','SELECT region, max(max_lat),','       sum(sum_lat)/sum(cnt) avg_lat','FROM region_lat GROUP BY region'],
    note:'与 ClickHouse AggregatingMergeTree 同构:MemTable 排序时先做一次预聚合;每个 rowset 落地的是"部分聚合状态"(如 avg 存 sum,count 而非最终值);cumulative/base compaction 后台把同 key 的部分状态按聚合函数合并(MAX 取大、SUM 相加);查询若遇未合并的 rowset,BlockReader 在读时再合并一次——保证结果正确且写入永远 O(1) 不阻塞。'
  },
  mowmerge:{
    title:'Merge-on-Write · delete bitmap 标删旧版本(Doris 主键表)',
    ddl:['CREATE TABLE orders (','  id INT,  -- UNIQUE KEY','  status VARCHAR, amount INT',') UNIQUE KEY(id)','PROPERTIES("enable_unique_key_merge_on_write"="true")'],
    cols:['id','status','amount','__DORIS_VERSION__'],
    parts:[
      {tag:'rowset-1', color:'#4a90d9', rows:[['1','NEW','100','v2'],['2','NEW','200','v2']]},
      {tag:'rowset-2 (UPSERT id=1)', color:'#c0559f', rows:[['1','PAID','150','v3']]}
    ],
    merged:{tag:'读取有效行(delete bitmap 生效)', rows:[['1','PAID','150','v3 ✓'],['2','NEW','200','v2 ✓']]},
    readSql:['-- 写入即时算 delete bitmap,标记 rowset-1 的 id=1 为删','-- 读时直接跳过被标删行,无需读时归并去重','SELECT * FROM orders WHERE id = 1;  -- 命中 v3'],
    note:'MoW 与 Merge-on-Read 的关键区别:写入 rowset-2 时,主键索引查出 id=1 旧版本在 rowset-1 的行位置,写 delete bitmap 标记为删(写时付出代价);读取时直接按 bitmap 跳过旧行,不做读时归并——点查/主键更新场景读性能接近明细表,代价是写入要查主键索引 + 维护 bitmap。'
  }
};

function renderMergeSVG(out, tid){
  const spec=MERGE_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▤</div><div>暂无数据流转示例</div></div>';return;}
  const NS='http://www.w3.org/2000/svg';
  const colN=spec.cols.length, cw=140, rh=30, hh=32, pad=14;
  const partW=pad*2+colN*cw, partGap=40;
  const W=Math.max(1000, pad+spec.parts.length*(partW+partGap)+partW+120);
  const ddlY=52, partsY=ddlY+spec.ddl.length*17+40;
  const maxPartRows=Math.max(...spec.parts.map(p=>p.rows.length), spec.merged.rows.length);
  const partH=hh+hh+maxPartRows*rh+pad;
  const mergedY=partsY+partH+70;
  const readY=mergedY+partH+50;
  const H=readY+spec.readSql.length*17+130;
  let svg='<svg id="svg-'+tid+'" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="'+NS+'">';
  svg+='<defs><marker id="mgArr-'+tid+'" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="var(--cv-merge)"/></marker></defs>';
  svg+='<text x="'+pad+'" y="28" fill="var(--cv-ink)" font-size="15" font-weight="650" font-family="var(--sans)">'+spec.title+'</text>';
  // DDL
  svg+='<text x="'+pad+'" y="'+(ddlY-4)+'" fill="var(--cv-ink2)" font-size="10.5" font-family="var(--mono)">建表 DDL</text>';
  spec.ddl.forEach((ln,i)=>{ svg+='<text x="'+pad+'" y="'+(ddlY+15+i*17)+'" fill="var(--cv-scan)" font-size="12" font-family="var(--mono)">'+ln.replace(/</g,'&lt;')+'</text>'; });
  // 画一个 part 表
  function drawPart(x,y,tag,color,rows){
    svg+='<text x="'+(x+partW/2)+'" y="'+(y-8)+'" fill="'+color+'" font-size="11.5" font-weight="600" text-anchor="middle" font-family="var(--mono)">'+tag+'</text>';
    svg+='<rect x="'+x+'" y="'+y+'" width="'+partW+'" height="'+(hh+rows.length*rh+pad/2)+'" rx="10" fill="var(--cv-card)" stroke="'+color+'" stroke-width="1.3"/>';
    spec.cols.forEach((c,ci)=>{ svg+='<text x="'+(x+pad+ci*cw+cw/2)+'" y="'+(y+21)+'" fill="var(--cv-ink2)" font-size="10.5" text-anchor="middle" font-family="var(--mono)">'+c+'</text>'; });
    svg+='<line x1="'+(x+6)+'" y1="'+(y+hh-4)+'" x2="'+(x+partW-6)+'" y2="'+(y+hh-4)+'" stroke="'+color+'55" stroke-width="1"/>';
    rows.forEach((r,ri)=>{ r.forEach((v,ci)=>{ const hot=ci===colN-1; svg+='<text x="'+(x+pad+ci*cw+cw/2)+'" y="'+(y+hh+16+ri*rh)+'" fill="'+(hot?color:'#d4d9e2')+'" font-size="12" text-anchor="middle" font-family="var(--mono)"'+(hot?' font-weight="600"':'')+'>'+v+'</text>'; }); });
  }
  // parts 行
  spec.parts.forEach((p,i)=>{ drawPart(pad+i*(partW+partGap), partsY, p.tag, p.color, p.rows); });
  svg+='<text x="'+(W-pad-260)+'" y="'+(partsY+30)+'" fill="var(--cv-ink2)" font-size="11" font-family="var(--mono)">← 每 rowset 存"部分聚合状态"</text>';
  svg+='<text x="'+(W-pad-260)+'" y="'+(partsY+48)+'" fill="var(--cv-ink2)" font-size="11" font-family="var(--mono)">  (avg 存 sum,count 而非最终值)</text>';
  // 合并箭头
  const cx=pad+partW/2;
  spec.parts.forEach((p,i)=>{ const px=pad+i*(partW+partGap)+partW/2; svg+='<path d="M'+px+','+(partsY+partH-10)+' C'+px+','+(mergedY-30)+' '+cx+','+(partsY+partH-10)+' '+cx+','+(mergedY-8)+'" fill="none" stroke="var(--cv-merge)" stroke-width="1.5" marker-end="url(#mgArr-'+tid+')"/>'; });
  svg+='<text x="'+(cx+partW/2+16)+'" y="'+(mergedY-24)+'" fill="var(--cv-merge)" font-size="12" font-weight="600" font-family="var(--sans)">▸ compaction / 读时聚合合并</text>';
  // 合并结果
  drawPart(pad, mergedY, spec.merged.tag, '#5aa469', spec.merged.rows);
  // 读 SQL
  svg+='<text x="'+pad+'" y="'+(readY-4)+'" fill="var(--cv-ink2)" font-size="10.5" font-family="var(--mono)">读取</text>';
  spec.readSql.forEach((ln,i)=>{ svg+='<text x="'+pad+'" y="'+(readY+15+i*17)+'" fill="var(--cv-scan)" font-size="12" font-family="var(--mono)">'+ln.replace(/</g,'&lt;')+'</text>'; });
  // 说明
  svg+='<foreignObject x="'+pad+'" y="'+(H-72)+'" width="'+(W-pad*2)+'" height="64"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:12px;line-height:1.7;color:#4a5568;font-family:-apple-system,sans-serif">'+spec.note+'</div></foreignObject>';
  svg+='</svg>';
  out.innerHTML=svg;
}

// 快速开始:一条 SQL 贯穿全引擎的可展开全流程。每个阶段含"发生了什么"叙述 + 深入对应主题(openTheme)。
// 快速开始:同一条 SQL 在三种存储/计算形态下的执行(数据访问路径不同,MPP+向量化骨架相同)
// 场景切换器选 integrated / decoupled / lakehouse;共享 stages 2-3 + exchanges + sink
// 快速开始:两个"逻辑算子图"——单表聚合 / 多表 JOIN。7 层结构(FE 全局→存储引擎),
// L5 展开物理算子 pipeline。两场景切换,均以具体 SQL 逐层映射。
// 7 层骨架:每层含固定"组件节点"+ 该层的 SQL 映射(map,场景相关)。L5 是算子层(pipelines)。
const _tourLevels=[
  {lv:'L1', name:'Query Context · FE 全局资源管控', accent:'#0a4d9e',
   nodes:['QueryContext / MemTracker','全局 OOM 监控与生命周期管理']},
  {lv:'L2', name:'Fragment · BE 分布式执行树', accent:'#1667c4',
   nodes:['PlanFragmentExecutor / PipelineDAG','跨机 PBRPC 网络分区 & Exchange 切分']},
  {lv:'L3', name:'Pipeline · BE 无锁管道拓扑', accent:'#0071e3',
   nodes:['Pipeline 阻塞边界切割','状态解耦 & COW 零拷贝推送']},
  {lv:'L4', name:'PipelineTask · BE 协程调度单元', accent:'#3d8bea',
   nodes:['PipelineXTask(Runnable 协程)','绑核 / 时间片轮转 / Yield 让出','并行实例 Task-1 … Task-N']},
  {lv:'L5', name:'Operator · 物理算子执行链路', accent:'#5b9ff0', pipelines:true},
  {lv:'L6', name:'Vectorized Engine · 寄存器计算核心', accent:'#78b2f4',
   nodes:['vectorized::Block / IColumn','AVX-512 SIMD 过滤','64B 缓存行对齐 · 零拷贝列式传递']},
  {lv:'L7', name:'Storage Engine · 物理存储驱动', accent:'#9fc9f7',
   nodes:['SegmentIterator / PageReader','ZoneMap 索引 + 短键范围裁剪','延迟物化(Late Materialization)']}
];
// 层间三类流(参考 Mermaid):控制流(↓ 调度下发)· 数据流(↑ 零拷贝回填)· 反馈闭环(⇢ 异步)
const _tourFlows={
  ctrl:[['L1','L2','资源管控下发'],['L2','L3','物理执行树生成'],['L3','L4','管道拓扑切分'],['L4','L5','唤醒并调度'],['L5','L6','列式读取下压'],['L6','L7','I/O 请求下发']],
  data:[['L7','L6','物化列数组(原生指针)'],['L6','L5','封装 Block(Zero-Copy)'],['L5','L1','结果 RowBatch 流式投递']],
  fb:[['L5','L4','Task 完成状态'],['L4','L3','Pipeline 收束'],['L3','L2','Fragment 数据汇合'],['L2','L1','查询结束确认'],['L4','L7','异步唤醒(依赖就绪)'],['L7','L4','I/O 完成通知']]
};
// 逻辑链路:Query Text → … → Block,每步 = {产物, 转换器/动作, file:line}
// 逻辑链路:每节点 = {产物 o, 转换器 act, file:line s, hover 边详情, star ★机制(挂在该节点下方的边上)}
const _tourChain=[
  {o:'Query Text', act:'SQL 文本入口', s:'',
   hover:['★ SQL Cache 短路 · CacheAnalyzer.innerCheckCacheModeForNereids()','条件: now - latestPartitionTime ≥ cache_last_version_interval_second','命中→直接返回,跳过后续全部阶段','· resultSetInFe: 结果在 FE 内存,直接返回','· cacheValues: 结果在 BE ResultCache,从 BE 拉取','未命中→走完整链路'], star:'SQL Cache'},
  {o:'Token 流', act:'DorisLexer(ANTLR4)', s:'DorisLexer.g4:20',
   hover:['DorisLexer 将 SQL 字符串切分为 Token 流','识别 SELECT/FROM/WHERE/标识符/字面量','NereidsParser.scan() 是 Token 化入口']},
  {o:'AST (ParseTree)', act:'DorisParser(ANTLR4)', s:'NereidsParser.toAst:400',
   hover:['按语法规则将 Token 流组装为 ParseTree','NereidsParser.toAst() 构建 AST','parseSQL() 最终返回 LogicalPlan']},
  {o:'LogicalPlan(未绑定)', act:'LogicalPlanBuilder Visitor', s:'',
   hover:['遍历 AST 节点映射为 LogicalPlan 算子树','列名/表名尚未绑定','以 UnboundSlot / UnboundRelation 表示']},
  {o:'analyzedPlan(已绑定)', act:'Analyzer.analyze', s:'ExpressionAnalyzer.java:306', k:'planWithLock',
   hover:['NereidsPlanner.analyze() 驱动分析阶段','cascadesContext.newAnalyzer().analyze() 执行绑定','visitUnboundSlot 将列名绑定到 SlotReference','表/列/函数解析 · 类型推导 · 隐式转换','视图展开 · CTE 内联 · 权限检查']},
  {o:'rewrittenPlan', act:'Rewriter.execute 100+ RBO', s:'Rewriter.java:722',
   hover:['getWholeTreeRewriter().execute() 执行 100+ 启发式规则','PruneOlapScanPartition 分区裁剪','PushDownFilter 谓词下推','EliminateSort 消除冗余排序','LimitSortToTopN','★ MV 透明改写 preMaterializedViewRewrite:用异步 MV 替换子树'], star:'MV 改写'},
  {o:'PhysicalPlan', act:'Optimizer.execute Cascades+DPHyp', s:'Optimizer.java:71', k:'joJob',
   hover:['DeriveStatsJob 自底向上推导统计(行数/NDV/直方图)','OptimizeGroupJob 枚举物理实现(HashJoin/NLJoin)','DPHyp 动态规划超图连接重排(可选)','含 PhysicalDistribute 节点','★ RuntimeFilter 计划生成:Build key→RF 描述符下推 Scan'], star:'RF 生成'},
  {o:'PlanFragment 列表', act:'PhysicalPlanTranslator + Coordinator brpc', s:'PhysicalPlanTranslator.java:349', k:'distribute',
   hover:['每遇 PhysicalDistribute:建 ExchangeNode 包裹上游 planRoot','以 ExchangeNode 为根建下游 Fragment','上游装 DataStreamSink 指向下游','Coordinator.sendPipelineCtx 序列化 TPipelineFragmentParamsList','按数据本地性选 BE,brpc 并行发送']},
  {o:'BE 接收 & 建 Operator', act:'exec_plan_fragment → _build_pipelines', s:'internal_service.cpp:322', k:'exec_rpc',
   hover:['light_work_pool 异步接收 RPC','_create_operator 遍历 TPlanNode 逐个建 C++ Operator','OlapScanNode→OlapScanOperatorX 等','★ RuntimeFilter 消费端注册:RuntimeFilterConsumerHelper.init 建 Dependency','acquire_runtime_filter 在 Open 获取已到 RF 下推;迟到 RF 动态追加 conjuncts'], star:'RF 消费'},
  {o:'Operator 链', act:'add_pipeline 切分', s:'pipeline_fragment_context.cpp:1566', k:'fragMgr',
   hover:['遇阻塞算子 add_pipeline 切新 Pipeline','HashJoin: Build 灌完哈希表 Probe 才开始','Agg/Sort: Sink 完成 Source 才输出','_dag 记录依赖 · Dependency.set_ready 无锁唤醒','★ RF 生产端:HashJoinBuildSink.close 构建 BloomFilter/IN/MinMax → publish'], star:'RF 生产'},
  {o:'Pipeline DAG', act:'TaskScheduler 调度', s:'pipeline_task.cpp:562', k:'pipeTask',
   hover:['PipelineTask.execute 主循环:_is_blocked 检查 Dependency','超时间片主动 yield(协作式调度)','★ 内存三层:MemTrackerLimiter(Query)/WorkloadGroup(组)/GlobalMemoryArbitrator(进程)','try_reserve 分配前预留;超高水位→Spill 或 Cancel','★ Spill:预留失败→add_paused_query→revoke_memory 序列化落盘→释放后唤醒(多级重分区 depth=8)'], star:'内存+Spill'},
  {o:'PipelineTask 执行', act:'get_block_after_projects', s:'',
   hover:['_root->get_block_after_projects 驱动 Operator 链拉数据','★ ScannerContext 多线程扫描:多个 OlapScanner 在 scanner_thread_pool 并发','Scanner 产出 Block 入 block_queue,get_block 取出(IO≠执行线程解耦)','★ Exchange 传输层(跨 Fragment):发送端 VDataStreamSender→PBlock→brpc streaming','接收端 VDataStreamRecvr.add_blocks→唤醒 ExchangeSource;背压:SenderQueue 超限延迟 done callback'], star:'Scanner+Exchange'},
  {o:'Block(列式批次)', act:'SIMD 谓词评估', s:'segment_iterator.cpp:2631', k:'segIterInternal',
   hover:['Block=向量化核心,每列 MutableColumn,~4096 行/批','_evaluate_vectorization_predicate SSE2/AVX2 一次 16/32 行','count_bytes_in_filter 统计通过行→sel_rowid_idx 选择向量','短路谓词处理 BloomFilter/String/Date','★ 字典编码谓词:低基数列在字典 code(整数)上 SIMD 比较,免解码字符串'], star:'字典编码'},
  {o:'存储层读取', act:'SegmentIterator → FileColumnIterator', s:'column_reader.cpp:2396', k:'olapGetBlock',
   hover:['索引过滤:ShortKey/ZoneMap/BloomFilter/InvertedIndex/NGram','★ Delete Bitmap/MVCC(Unique MoW):每 Segment 有 Roaring DeleteBitmap','读前用 delete_bitmap.get_agg(version) 过滤已删/覆盖行','★ 延迟物化:一读谓词列→过滤→二读只读通过行的非谓词列(_read_columns_by_rowids)'], star:'DeleteBitmap+延迟物化'},
  {o:'列数据回填 Block', act:'PageIO 读取解压 → PageDecoder', s:'column_reader.cpp:2434', k:'fmtPageEnc',
   hover:['★ PageCache:先查 StoragePageCache(LRU-K),key=(路径,大小,page偏移)','命中→返回缓存,跳过 IO+解压','未命中→read_at 读压缩 page→立即解压→插入 cache','PageDecoder 解码(字典/RLE/BitPacking)→填 MutableColumn'], star:'PageCache'}
];
const TOUR_PLANS={
  single:{
    label:'单表聚合',
    sql:"SELECT user_id, SUM(score)\nFROM site_access\nWHERE date >= '2026-01-01'\nGROUP BY user_id;",
    map:{  // 每层的 SQL 映射(接在层名后)
      L1:'维护 SUM(score) 聚合内存上限', L2:'GROUP BY 触发上下游 Shuffle',
      L3:'LocalAgg 与 GlobalAgg 物理隔离', L4:'按并行度打散 GROUP BY 分片任务',
      L6:"AVX-512 过滤 date >= '2026-01-01'", L7:'延迟物化仅读 user_id 与 score'
    },
    pipelines:[
      {name:'Pipeline A · 扫描+预聚合', ops:[
        {t:'OlapScanOperator',d:'读 site_access',k:'olapGetBlock',theme:'integrated',tab:'olapflow'},
        {t:'AggregationSink',d:'局部预聚合 PHMap',k:'vecAgg',theme:'vectorization',tab:'vecflow'}]},
      {name:'Pipeline B · Shuffle 发送', ops:[
        {t:'DataStreamSink',d:'按 user_id 哈希分区',k:'djPartitioner',theme:'optimizer',tab:'joinflow'}]},
      {name:'Pipeline C · 接收+全局聚合', ops:[
        {t:'ExchangeSource',d:'拉跨机 brpc 数据',k:'djPartitioner',theme:'pipeline',tab:'pipeflow'},
        {t:'AggregationSource',d:'全局合并 Global PHMap',k:'vecAgg',theme:'vectorization',tab:'vecflow'},
        {t:'ResultSink',d:'收束结果回传 FE',k:'convertOut',theme:'lakehouse',tab:'seq'}]}
    ],
    breaker:'AggregationSink 是 pipeline breaker:全局聚合须等各 Pipeline A 预聚合完成',
    physical:[
      {d:0,t:'PLAN FRAGMENT 1 (Coordinator)',s:'结果汇聚节点'},
      {d:1,t:'RESULT SINK',s:'→ MySQL 协议回传 FE'},
      {d:1,t:'AGGREGATE (merge finalize)',s:'全局 SUM(score) / Global PHMap'},
      {d:2,t:'EXCHANGE (GATHER)',s:'拉取各 BE 局部聚合'},
      {d:0,t:'PLAN FRAGMENT 0 (BE ×N)',s:'扫描 + 预聚合,按并行度实例化'},
      {d:1,t:'DATA STREAM SINK',s:'HASH_PARTITIONED by user_id'},
      {d:2,t:'AGGREGATE (update serialize)',s:'局部预聚合 PHMap'},
      {d:3,t:'OlapScanNode: site_access',s:'谓词 date>=... 下推;延迟物化 user_id,score'}
    ]
  },
  join:{
    label:'多表 JOIN',
    sql:"SELECT c.c_name, SUM(o.o_totalprice)\nFROM customer c\nJOIN orders o ON c.c_custkey = o.c_custkey\nWHERE o.o_orderdate >= '1994-01-01'\nGROUP BY c.c_name;",
    map:{
      L1:'监控 JOIN 哈希表 + 聚合 PHMap 合并内存', L2:'Broadcast Join 规划(customer 广播)',
      L3:'Build 侧(customer)与 Probe 侧(orders)物理隔离', L4:'并发 Build 任务与 Probe 任务协同调度',
      L6:"AVX-512 过滤 o_orderdate >= '1994-01-01'", L7:'ZoneMap 裁 o_orderdate · 延迟物化仅读 c_name/o_totalprice'
    },
    pipelines:[
      {name:'Pipeline A · Build 侧', ops:[
        {t:'OlapScanOperator',d:'读 customer',k:'olapGetBlock',theme:'integrated',tab:'olapflow'},
        {t:'HashJoinBuild',d:'构建哈希表 c_custkey→c_name',k:'vecHashJoin',theme:'vectorization',tab:'vecflow'}]},
      {name:'Pipeline B · Probe + 预聚合', ops:[
        {t:'OlapScanOperator',d:'读 orders(谓词下推)',k:'fmtOrcSarg',theme:'storageformat',tab:'fmtflow'},
        {t:'Filter',d:"o_orderdate ≥ '1994-01-01'",k:'segIterInternal',theme:'integrated',tab:'olapflow'},
        {t:'HashJoinProbe',d:'探测哈希表 o_custkey',k:'vecHashJoin',theme:'vectorization',tab:'vecflow'},
        {t:'AggregationSink',d:'局部预聚合 c_name→SUM',k:'vecAgg',theme:'vectorization',tab:'vecflow'},
        {t:'DataStreamSink',d:'发送全局合并',k:'djPartitioner',theme:'optimizer',tab:'joinflow'}]},
      {name:'Pipeline C · 全局收束', ops:[
        {t:'ExchangeSource',d:'拉跨机聚合数据',k:'djPartitioner',theme:'pipeline',tab:'pipeflow'},
        {t:'AggregationSource',d:'全局合并 SUM',k:'vecAgg',theme:'vectorization',tab:'vecflow'},
        {t:'ResultSink',d:'回传 FE 协调器',k:'convertOut',theme:'lakehouse',tab:'seq'}]}
    ],
    breaker:'HashJoinBuild 是 pipeline breaker:Probe 侧须等 Build 侧哈希表构建完成(WaitForDependency 唤醒)',
    physical:[
      {d:0,t:'PLAN FRAGMENT 2 (Coordinator)',s:'结果汇聚'},
      {d:1,t:'RESULT SINK',s:'→ FE 协调器'},
      {d:1,t:'AGGREGATE (merge finalize)',s:'全局 SUM(o_totalprice)'},
      {d:2,t:'EXCHANGE (GATHER)',s:'拉取各 BE 局部聚合'},
      {d:0,t:'PLAN FRAGMENT 1 (BE ×N)',s:'Probe + 预聚合'},
      {d:1,t:'DATA STREAM SINK',s:'HASH_PARTITIONED by c_name'},
      {d:2,t:'AGGREGATE (update)',s:'局部 c_name→SUM'},
      {d:3,t:'HASH JOIN (INNER, BROADCAST)',s:'probe o_custkey = build c_custkey'},
      {d:4,t:'OlapScanNode: orders',s:'谓词 o_orderdate>=... 下推'},
      {d:4,t:'EXCHANGE (BROADCAST)',s:'← Fragment 0 广播 customer'},
      {d:0,t:'PLAN FRAGMENT 0 (BE ×N)',s:'Build 侧'},
      {d:1,t:'HASH JOIN BUILD SINK',s:'构建 c_custkey→c_name 哈希表'},
      {d:2,t:'OlapScanNode: customer',s:'延迟物化 c_custkey,c_name'}
    ]
  }
};

// 术语表:FE/BE/CN、存储层级、执行层级、优化器、检索等首次解释 + 缩写
const GLOSSARY_SPEC={
  id:'glossary', title:'术语表 · Doris 核心概念与缩写',
  note:'首次接触先读这张表;涵盖 组件 / 存储 / 执行 / 优化 / 检索 各层。缩写在括号内标注全称。',
  rowH:38,
  cols:[{h:'术语',w:250,accent:'var(--cv-scan)'},{h:'一句话解释',w:660,accent:'var(--cv-ink)'}],
  rows:[
    ['FE（Frontend）','前端节点(Java):SQL 解析、优化、元数据、调度;高可用靠 BDB-JE 复制'],
    ['BE（Backend）','后端节点(C++):数据存储 + 向量化执行;存算一体下有状态'],
    ['CN（Compute Node）','存算分离下的无状态计算节点(不持久化数据,数据在共享存储)'],
    ['Tablet','表按分区+分桶切分的最小数据管理/调度单元;多副本;调度器保证副本健康'],
    ['Rowset','一次导入/compaction 产生的一批数据(含多个 Segment),带 version 区间'],
    ['Segment','Rowset 内的列存文件(Doris 自有 V2 格式:footer + 列数据 + 三索引)'],
    ['Fragment（PlanFragment）','物理计划按 Exchange 切开的子计划片段;分发到 BE 执行'],
    ['Pipeline','Fragment 在 BE 上的执行载体;算子链拆成可并行的 PipelineTask'],
    ['Nereids','Doris 新一代 CBO 优化器(Cascades 风格:Memo + 代价枚举)'],
    ['RBO / CBO / HBO（Rule/Cost/History Based Opt）','基于规则 / 代价 / 历史行数反馈 的三层优化'],
    ['MoW（Merge-on-Write）','主键模型写时合并:写入即定位并标删旧版本(delete bitmap),读快'],
    ['MoR（Merge-on-Read）','读时合并(如 Hudi MOR):读时合并 base + log,写快读慢'],
    ['RF（Runtime Filter）','运行时过滤:join build 侧生成过滤器下推 probe 侧 scan 裁行'],
    ['MV（Materialized View）','物化视图:异步 MTMV(透明改写)/ 同步 Rollup(预聚合)'],
    ['ZoneMap','每 page/segment 的 min/max 索引,用于谓词下推跳过不命中数据'],
    ['MPP（Massively Parallel Processing）','查询切成 Fragment 在多 BE 上并行,Exchange 洗牌通信']
  ]
};

// 查询生命周期 · 调优开关速查(session variables)
const QLIFEVARS_SPEC={
  id:'qlifevars', title:'调优开关速查 · session variables',
  note:'贯穿查询全链路的常用会话变量;"相关环节"对应生命周期主线的 ①–⑪ 与接入/横切阶段。',
  rowH:40,
  cols:[{h:'变量',w:250,accent:'var(--cv-scan)',mono:true},{h:'作用',w:430,accent:'var(--cv-ink)'},{h:'相关环节',w:150,accent:'var(--cv-ink)'}],
  rows:[
    ['enable_nereids_planner','启用 Nereids 优化器(默认 true)','③–⑥'],
    ['enable_sql_cache','SQL 结果缓存','接入 / 缓存'],
    ['enable_pipeline_engine','Pipeline 执行引擎(默认)','⑩'],
    ['parallel_pipeline_task_num','单 Fragment 每 BE 的并行度(DOP)','⑧ ⑩'],
    ['runtime_filter_type / _mode','RF 类型(IN/Bloom/MinMax)与模式','⑩'],
    ['enable_spill','算子内存不足时落盘防 OOM','⑩'],
    ['exec_mem_limit','单查询内存上限','⑧ ⑩'],
    ['query_timeout','查询超时(秒)','全链路'],
    ['enable_profile','生成 Query Profile','⑪ / 可观测性']
  ]
};

// 查询生命周期 · 术语表
const QLIFETERMS_SPEC={
  id:'qlifeterms', title:'术语表 · 查询生命周期核心概念',
  note:'配合生命周期主线各图阅读;区分 FE 内存对象与下发 BE 的 Thrift 结构是关键。',
  rowH:42,
  cols:[{h:'术语',w:230,accent:'var(--cv-scan)'},{h:'含义',w:600,accent:'var(--cv-ink)'}],
  rows:[
    ['LogicalPlan / PhysicalPlan','Nereids 的逻辑 / 物理计划(均为 FE 内存对象)'],
    ['PlanNode / PlanFragment','翻译后下发 BE 的 Thrift 结构 / 以 Exchange 切分的执行单元'],
    ['Memo / Group / GroupExpression','Cascades 优化器的搜索结构与等价类'],
    ['Breaker','阻塞型算子(Join Build、Agg、Sort),Pipeline 的切分点'],
    ['Local Exchange','节点内数据重分布(不走网络),解耦 Scan 与计算并行度'],
    ['Enforcer / DistributionSpec','CBO 为满足分布需求插入 Exchange 的机制'],
    ['Runtime Filter','运行期由 Join Build 侧生成、下推 Probe 侧 Scan 的过滤器'],
    ['MVCC 版本','查询选定的可见 rowset 快照,保证读一致性']
  ]
};

// 架构对比:Doris vs ClickHouse / StarRocks / Trino / Spark / DuckDB —— 设计取舍
const COMPARE_SPEC={
  id:'compare', title:'计算引擎对比 · Flink 在流计算生态中的定位',
  note:'突出设计取舍(非优劣);同族流引擎看差异,微批(Spark)看设计哲学分野。',
  rowH:40,
  cols:[{h:'维度',w:140,accent:'var(--cv-scan)'},{h:'Flink',w:200,accent:'var(--cv-ink)'},{h:'Spark Structured Streaming',w:200,accent:'var(--cv-ink)'},{h:'Kafka Streams',w:170,accent:'var(--cv-ink)'},{h:'Storm',w:130,accent:'var(--cv-ink)'}],
  rows:[
    ['模型','流优先(有界=流特例)','微批(micro-batch)','流(嵌入库)','流(原生)'],
    ['接触面','多 API:DataStream/Table-SQL','DataFrame/SQL','Streams DSL/KSQL','Spout/Bolt'],
    ['状态','一等公民:keyed/operator + RocksDB','有状态(受限)','RocksDB 本地 + changelog','弱/外部'],
    ['容错','分布式快照(检查点)精确一次','微批+WAL 精确一次','changelog+事务精确一次','at-least-once(Trident 才 EOS)'],
    ['时间语义','事件时间+水位线(强)','事件时间(较弱)','事件时间','弱'],
    ['延迟','低(逐条+mailbox)','较高(批间隔)','低','低'],
    ['部署','独立集群/YARN/K8s','Spark 集群','嵌入应用(无集群)','独立集群'],
    ['定位','通用流批统一计算','批为主+流','Kafka 生态轻量流处理','早期流引擎(渐被取代)'],
    ['可借鉴','—','批优化/Catalyst','嵌入式+changelog','—']
  ]
};

// 失败与一致性语义:各关键流程的 失败点 / 重试条件 / 幂等边界 / 可见性时刻
const FAILURE_SPEC={
  id:'failure', title:'失败与一致性语义 · 关键流程的失败点/重试/幂等/可见性',
  note:'分布式写入与变更的正确性边界;设计/排障时先看这张表。',
  rowH:44,
  cols:[{h:'流程',w:130,accent:'var(--cv-scan)'},{h:'失败点',w:200,accent:'var(--cv-danger)'},{h:'重试 / 恢复',w:210,accent:'var(--cv-warn)'},{h:'幂等边界',w:150,accent:'var(--cv-merge)'},{h:'可见性时刻',w:170,accent:'var(--cv-vec)'}],
  rows:[
    ['事务/MVCC','commit 后 publish 前 BE 宕机','FE 重发 publish;version 未定则不可见','publish 幂等(version 已定则跳过)','publish 定 version 后,读 ≥该 version 才可见'],
    ['Stream Load','导入中 BE 挂 / 超时','整批失败回滚,客户端按 label 重试','label 唯一→重复 label 拒绝(幂等)','事务 publish 后整批一次性可见'],
    ['Group Commit','攒批 flush 前 BE 宕机','WAL 重放恢复未提交的 block','wal_id=txn_id;重放按 txn 去重','组提交事务 publish 后可见(ASYNC 有窗口)'],
    ['Routine Load','消费/导入失败 / offset 提交失败','task 超时回收重排;从上次 offset 重消费','offset 存 FE 元数据;事务+offset 原子提交','子事务 publish 后可见;exactly-once 靠原子提交'],
    ['Schema Change','转换中 BE 挂 / 版本追不上','job 状态机可重入;失败 CANCELLED 清影子','watershed 后双写;转换只处理历史版本','onFinished 原子切换后,查询走新 schema'],
    ['Compaction','归并中崩溃 / 输出未提交','失败丢弃输出 rowset,输入不变(安全)','输出未 commit 则无副作用','modify_rowsets 提交后,读走新 rowset'],
    ['Tablet 修复','clone 中源/目标 BE 挂','调度器超时回收,重新选源 clone','clone 幂等(版本追平即完成)','新副本版本追平后计入多数派、可读'],
    ['存算分离写','上传对象存储 / commit MetaService 失败','重试 RPC;ALREADY_EXISTED 幂等跳过','rowset_id 幂等;commit_rowset 可重入','MetaService commit 成功后,其他 CN 可见']
  ]
};

// 瓶颈模型:每条关键链路"最容易慢在哪里" + 症状 + 调优方向
const BOTTLENECK_SPEC={
  id:'bottleneck', title:'瓶颈模型 · 关键链路最易慢点与调优方向',
  note:'排查慢查询/慢导入先按链路定位;每格是"通常瓶颈 → 症状 → 调优"。',
  rowH:44,
  cols:[{h:'环节',w:150,accent:'var(--cv-scan)'},{h:'最易慢点',w:250,accent:'var(--cv-danger)'},{h:'症状 / 观测',w:230,accent:'var(--cv-warn)'},{h:'调优方向',w:200,accent:'var(--cv-merge)'}],
  rows:[
    ['FE · CBO','大 join 的 join reorder(DPhyp)枚举空间爆炸','plan 时间长;FE CPU 高','控 MAX_JOIN_NUMBER;统计信息准确;必要时 hint'],
    ['FE · Split 枚举','外表文件数巨大,getSplits 慢','FE 卡在规划;Split 数百万','分区裁剪;合并小文件;并行 listing'],
    ['FE→BE · RPC 扇出','fragment 扇出到很多 BE,序列化/RPC 开销','下发延迟高;小查询也慢','控并行度;复用连接;减 fragment 数'],
    ['BE · Scan IO','冷数据 / 外表 / 存算分离缓存未命中','scan 时间占比高;磁盘/网络 IO 打满','FileCache 预热;谓词下推;列裁剪'],
    ['BE · 谓词下推失效','谓词没下推到存储层,全量读再过滤','扫描行数≫返回行数;ZoneMap 未命中','建索引/分区;让谓词可下推;避免函数包裹列'],
    ['BE · Exchange','shuffle 数据量大 / 数据倾斜','某 lane 慢拖累整体;网络打满','bucket shuffle/colocate 免 shuffle;打散热点 key'],
    ['BE · 聚合/排序','高基数聚合 HashTable 大;spill 落盘','内存高;触发 spill;query 变慢','提并行度;预聚合(MV);增内存或接受 spill'],
    ['Compaction','后台 compaction 与查询抢 IO/CPU','导入后查询抖动;compaction 积压','调 compaction 线程/策略;错峰;控写入频率'],
    ['内存 · MemTracker','查询超 limit 被 cancel','query 报 MEM_LIMIT_EXCEEDED','调 workload group 配额;开 spill;优化计划降内存'],
    ['MoW 写','delete bitmap 计算 + 点查旧版本','高频更新写放大;导入变慢','控更新频率;合理分桶;评估 MoR 替代']
  ]
};

// ===== Doris 核心优化策略(start 主题:优化目标 / 资源主轴 / 生命周期 / 数据粒度 / 算子 / 负载 / 可观测)=====
const OPTGOAL_SPEC={
  title:'Doris 优化目标 · 按「减少什么资源消耗」归 9 类(核心目录)',
  note:'最稳定的主目录:每类优化都对应一个"减少什么"的目标 + 一组核心策略 + 主要落点(FE/BE/Storage)+ 典型收益。这是理解 Doris 所有优化的第一层地图。',
  rowH:40,
  cols:[
    {h:'主类',w:170,accent:'var(--cv-scan)'},
    {h:'优化目标',w:250,accent:'var(--cv-ink)'},
    {h:'核心策略',w:430,accent:'var(--cv-ink)'},
    {h:'主要位置',w:160,accent:'var(--cv-ink)'},
    {h:'典型收益',w:180,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['① 减少规划开销','少访问元数据、少枚举对象、少做无效计划搜索','Catalog Cache、Schema Cache、Partition Cache、File List Cache、统计信息、Plan Cache','FE','降低查询启动延迟'],
    ['② 减少扫描对象数量','少扫分区、Tablet、Bucket、文件、Split','分区裁剪、Tablet 裁剪、Bucket 裁剪、文件裁剪、Split 合并','FE 规划 + BE Scan','减少 Scan 任务和打开文件数'],
    ['③ 减少存储单元读取','少读 Segment、Row Group、Page、Stripe','ZoneMap、Bloom Filter、倒排索引、NGram Bloom、Parquet Min/Max、Page Index、ORC SARG','Storage + BE Scan','减少磁盘 / 对象存储 IO'],
    ['④ 减少读取列和字节','少读无关列、少解码、少反序列化','列裁剪、嵌套列裁剪、延迟物化、字典过滤、COUNT 下推','FE 改写 + BE Scan','宽表查询收益最大'],
    ['⑤ 减少流入算子的行数','少让无效行进入 Join / Agg / Sort','谓词下推、Join 谓词推导、Runtime Filter、TopN Filter','FE + BE','降低 CPU、内存、Join 状态'],
    ['⑥ 减少网络和 Shuffle','少跨节点传输、少重分布','Broadcast Join、Shuffle Join、Bucket Shuffle Join、Colocate Join、Local Exchange','FE 选型 + BE 执行','大表 Join 收益明显'],
    ['⑦ 减少算子计算与内存状态','少 Hash、少排序、少聚合状态','Join Reorder、两阶段聚合、预聚合、TopN 下推、Pipeline、向量化','FE + BE','降低 CPU 和内存峰值'],
    ['⑧ 减少重复计算和冷启动','复用计划、结果、数据、文件元信息','同步 MV、异步 MV、Query Cache、Data Cache、Footer Cache、Prepared Plan','FE + BE + Storage','Dashboard、湖仓查询收益明显'],
    ['⑨ 优化写入与存储维护','提升导入吞吐,降低后续查询成本','Load Channel、Tablet Writer、MemTable、Segment Writer、Compaction、版本管理、索引构建','FE + BE + Storage','写入更稳,读查询更快']
  ]
};
const OPTAXIS_SPEC={
  title:'Doris 核心优化策略多维透视总表 · 主轴 = 资源消耗',
  note:'主分类轴用资源名(规划开销/扫描对象数量/存储单元读取…),FE/BE/Storage 是实现分工轴。一句话:FE 让查询「选对路、少派活」;BE 让执行「少算、少传、少等待」;Storage 让数据「少读、可跳过、可维护」。',
  rowH:52,
  cols:[
    {h:'主轴 · 资源消耗',w:120,accent:'var(--cv-scan)'},
    {h:'生命周期位置',w:110,accent:'var(--cv-ink)'},
    {h:'FE 做什么',w:150,accent:'#4a90d9'},
    {h:'BE 做什么',w:150,accent:'#d0913a'},
    {h:'Storage 做什么',w:140,accent:'#3c9d5c'},
    {h:'作用粒度',w:150,accent:'var(--cv-ink)'},
    {h:'生效时机',w:110,accent:'var(--cv-ink)'},
    {h:'代表优化策略',w:280,accent:'var(--cv-ink)'},
    {h:'核心收益',w:200,accent:'var(--cv-ink)'},
    {h:'观察入口',w:170,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['规划开销','SQL 分析/优化','缓存元数据、统计、复用计划','-','提供元信息','Catalog/DB/Table/Partition/Plan','规划期','Catalog/Schema/Partition Cache · Stats · Prepared/Plan Cache','降短查询启动延迟,减 HMS/外部元数据访问','FE Profile · 规划耗时 · EXPLAIN'],
    ['扫描对象数量','Scan Range 生成','分区/Tablet/文件裁剪','执行裁剪后 Scan','组织 Tablet/Rowset/Segment','Partition/Tablet/Bucket/File/Split','规划期为主,Scan 执行','Partition/Tablet/Bucket/File Prune · Split 合并','少派 Scan、少打开文件、少扫分区/文件','EXPLAIN 分区数/Tablet 数/ScanRange 数'],
    ['存储单元读取','Scan 执行','下发谓词和列信息','调索引/统计跳数据','ZoneMap/Bloom/倒排/Page Index','Segment/RowGroup/Stripe/Page','Scan 执行期','ZoneMap · Bloom · 倒排 · NGram BF · Parquet MinMax/Page Index · ORC SARG','减磁盘/SSD/对象存储读取与解压','Scan Profile · RowGroup/Page/Segment 过滤数'],
    ['读取列和字节','Scan 执行','列裁剪、COUNT 改写','延迟物化/字典过滤/少解码','列存/编码/压缩','Column/Nested/Dict/RowId','规划期定,Scan 生效','Column/Nested Pruning · Lazy Materialization · Dict Filter · COUNT 元信息','宽表少读列、大字段少解码,降 IO/CPU','ReadBytes · 读取列数 · 解码耗时'],
    ['流入算子行数','Filter/Join/TopN','谓词推导、RF 计划','生成/消费 RF/TopN Filter','提供行级过滤能力','Row/Batch/Scan Block','静态 + 动态','Predicate Pushdown/Inference · Runtime Filter · TopN Filter','少让无效行进 Join/Agg/Sort,降算子压力','RowsRead · RowsReturned · RF 过滤行数'],
    ['网络 Shuffle','Fragment/Exchange','选 Broadcast/Shuffle/Colocate','执行 Exchange/Local Exchange','分桶/副本分布支撑','Fragment/Node/Bucket/Exchange','规划决策,执行生效','Broadcast/Shuffle/Bucket Shuffle/Colocate Join · Local Exchange','减跨节点传输、序列化、网络等待','Exchange Profile · SendBytes · NetworkTime'],
    ['算子计算状态','Join/Agg/Sort','Join Reorder、聚合/TopN 下推','向量化/Pipeline/两阶段聚合','数据布局影响输入规模','Operator/HashTable/AggState/SortBuf','静态 + 动态','Join Reorder/类型选择 · Two-Phase Agg · Pre-Agg · TopN Pushdown · 向量化 · Pipeline','少建 Hash、少排序、少聚合状态,降 CPU/内存峰值','OperatorTime · HashTableSize · AggRows · SortTime'],
    ['重复计算','查询前后','MV 改写、Plan Cache','Query Cache、Data Cache','Footer Cache、数据块缓存','Query/Plan/MV/Result/FileBlock/Footer','命中时生效','同步/异步 MV · Plan/Prepared Cache · Query/Data Cache · Footer/Index Cache','重复查询更快、湖仓冷读更快,减重复编译/IO','MV 命中 · Cache Hit · RemoteReadBytes'],
    ['写入与维护','Load/Compaction','生成写入计划和路由','Load Channel、Tablet Writer','Rowset/Segment/Compaction/版本管理','Load/Tablet/Rowset/Segment/Version','写入期 + 后台维护','Load Channel · Tablet/Segment Writer · MemTable · Compaction · Version Graph · Delete Bitmap · 索引构建','提升导入吞吐,降读放大,提高未来跳过能力','Load Profile · Compaction 指标 · Rowset/Segment 数']
  ]
};
const OPTRELATION_SPEC={
  title:'九类主轴之间的专业关系 · 本质问题与相互作用',
  note:'九类主轴不是并列独立,而是沿查询流水线层层递进:规划开销是入口,统计信息质量影响后续所有裁剪与择优;越靠前越粗粒度的跳过省得越多;写入与维护横跨读写,决定未来查询的跳过上限。',
  rowH:44,
  cols:[
    {h:'主轴 · 资源消耗',w:150,accent:'var(--cv-scan)'},
    {h:'本质问题',w:360,accent:'var(--cv-ink)'},
    {h:'与其他主轴的关系',w:560,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['规划开销','查询还没执行,就已花了多少时间','是所有优化的入口;统计信息质量会影响 Join Reorder、分布选择、裁剪效果'],
    ['扫描对象数量','要不要扫描这个分区/Tablet/文件/Split','决定 Scan 的任务规模,是比 RowGroup/Page 过滤更粗粒度的优化'],
    ['存储单元读取','文件/Segment 选中后,能不能跳过内部数据块','依赖 Storage 索引和文件格式统计,是 Scan 阶段的核心 IO 优化'],
    ['读取列和字节','数据块要读时,能不能少读列、少解码','对宽表、大字段、嵌套列、低选择率谓词特别关键'],
    ['流入算子行数','数据读出来后,能不能少进入 Join/Agg/Sort','连接 Scan 与执行算子的桥梁;Runtime Filter 是典型动态优化'],
    ['网络 Shuffle','多节点执行时,数据是否需要大规模重分布','与 Join 类型、表分布、分桶设计强相关'],
    ['算子计算状态','Join/Agg/Sort 内部需要多少 CPU 和内存','受输入行数、Join 顺序、聚合基数、排序规模影响'],
    ['重复计算','同样的计划/数据/结果是否被反复生成','横跨 FE/BE/Storage;MV、Cache、Plan 复用分别解决不同重复成本'],
    ['写入与维护','写入是否高效,存储布局是否利于未来查询','不只影响导入吞吐,也决定后续 ZoneMap/Bloom/Compaction/读放大效果']
  ]
};
const OPTLIFECYCLE_SPEC={
  title:'Doris 优化 · 按查询生命周期透视(对应查询主线)',
  note:'对应主线:SQL 入口→StmtExecutor→NereidsPlanner→Coordinator→BE Fragment→Pipeline→OlapScan→ResultReceiver。每个阶段的关键优化及其本质。',
  rowH:34,
  cols:[
    {h:'查询阶段',w:150,accent:'var(--cv-scan)'},
    {h:'Doris 主体',w:230,accent:'var(--cv-ink)'},
    {h:'关键优化',w:430,accent:'var(--cv-ink)'},
    {h:'优化本质',w:220,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['SQL 接入','FE ConnectProcessor/StmtExecutor','连接复用 · 会话变量 · Prepared Statement · Plan Cache','降短查询启动成本'],
    ['语义分析','FE Analyzer/Nereids','Catalog Cache · Schema Cache · 权限与元数据缓存','少访问外部元数据'],
    ['逻辑改写','FE Nereids Rewrite','谓词下推 · 列裁剪 · COUNT/TopN/聚合下推 · 常量折叠','提前消除无效工作'],
    ['CBO 优化','FE Nereids Planner','Join Reorder · Join 类型选择 · 分布方式选择 · MV 改写','选整体代价最低计划'],
    ['Fragment 生成','FE Planner/Coordinator','分区/Tablet/Bucket 裁剪 · Fragment 拆分','少派任务,派对任务'],
    ['Fragment 下发','FE Coordinator→BE','Scan Range 分配 · 并行度 · Pipeline 参数','提高调度效率'],
    ['BE 接收执行','BE PInternalService/FragmentMgr','Fragment 注册 · Pipeline 拆分 · 资源控制','提高并行执行效率'],
    ['Pipeline 执行','BE PipelineTask','向量化 · Pipeline · Local Exchange · 两阶段聚合','降阻塞与 CPU 开销'],
    ['Scan 读取','BE OlapScan/FileScan','ZoneMap · Bloom · 倒排 · Page Index · 列裁剪 · 延迟物化','少读数据/少解码'],
    ['Join/Agg/Sort','BE Operators','Runtime Filter · TopN Filter · Broadcast · Colocate · 预聚合','少行/少 Shuffle/少状态'],
    ['结果返回','BE Result Sink + FE ResultReceiver','Limit 下推 · 结果批量传输 · Query Cache','少返回/少重复计算']
  ]
};
const OPTGRANULARITY_SPEC={
  title:'Doris 优化 · 按数据粒度透视(到底跳过了什么)',
  note:'从查询级到 Batch 级,每层都有对应的跳过手段。这个视角最适合解释"为什么会快"——越早越粗地跳过,省得越多。',
  rowH:32,
  cols:[
    {h:'粒度',w:140,accent:'var(--cv-scan)'},
    {h:'Doris / 湖仓对象',w:280,accent:'var(--cv-ink)'},
    {h:'代表优化',w:390,accent:'var(--cv-ink)'},
    {h:'跳过效果',w:220,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['查询级','整个 SQL','Query Cache · MV 透明改写','整个查询不再重算'],
    ['表级','Base/Rollup/MV','Rollup 选择 · 同步 MV · 异步 MV','改扫更小或预聚合结果'],
    ['分区级','Doris/Hive/Iceberg Partition','分区裁剪','跳过整批 Tablet/目录'],
    ['Tablet 级','Doris Tablet','Tablet 裁剪 · 副本选择','少扫 Tablet'],
    ['Bucket 级','Hash Bucket','Bucket 裁剪 · Bucket Shuffle Join','少扫 Bucket,少 Shuffle'],
    ['文件级','Parquet/ORC/Data File','File Prune · Manifest Metrics · File-List Cache','跳过整个文件'],
    ['Rowset 级','Doris Rowset','版本裁剪 · Rowset 选择','只读可见版本'],
    ['Segment 级','Doris Segment','Segment ZoneMap · Bloom · 倒排','跳过 Segment'],
    ['RowGroup/Stripe','Parquet RowGroup / ORC Stripe','Min/Max · Bloom · ORC SARG','跳过大块文件数据'],
    ['Page 级','Doris/Parquet Page','Page Index · Page ZoneMap · 字典过滤','更细粒度跳过'],
    ['列级','Column / Nested Field','列裁剪 · 嵌套列裁剪','不读无关列'],
    ['行级','Row / RowId','谓词过滤 · Runtime Filter · TopN Filter · Delete Bitmap','少输出无效行'],
    ['Batch 级','Vectorized Block','向量化 · SIMD · 表达式批处理','降逐行执行成本']
  ]
};
const OPTPHASE_SPEC={
  title:'Doris 优化 · 静态/动态透视 + 常见误区纠偏',
  note:'静态=规划期确定(EXPLAIN 可见);动态=执行期按中间结果生成(看 Profile);存储内生=依赖文件/Segment 自带统计索引。判断优化是否生效要看 EXPLAIN + Profile,不能只看理论。',
  rowH:36,
  cols:[
    {h:'类型',w:150,accent:'var(--cv-scan)'},
    {h:'定义',w:230,accent:'var(--cv-ink)'},
    {h:'代表优化',w:420,accent:'var(--cv-ink)'},
    {h:'观察方式',w:200,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['静态优化','规划期就能确定','列裁剪 · 分区裁剪 · 谓词下推 · Join Reorder · MV 改写 · COUNT 下推','EXPLAIN / EXPLAIN VERBOSE'],
    ['半静态优化','规划期定框架,执行期体现收益','TopN 下推 · 聚合下推 · 文件裁剪 · Data Cache','EXPLAIN + Profile'],
    ['动态优化','执行期按中间结果生成','Runtime Filter · TopN Filter · Pipeline 调度 · 缓存命中','Query Profile'],
    ['存储内生优化','依赖文件/Segment 自带统计与索引','ZoneMap · Bloom · Page Index · ORC SARG · 倒排','Scan Profile'],
    ['⚠ 纠偏 · Runtime Filter','不是 FE 下推','BE 执行期由 Join Build 侧生成,再注入 Probe 侧 Scan','Runtime Filter Profile'],
    ['⚠ 纠偏 · COUNT(*) 下推','不是普通执行层优化','FE 先识别改写,再由 Scan 利用元信息减少读取','EXPLAIN + Scan Profile'],
    ['⚠ 纠偏 · 延迟物化','不是 Join/Agg 层优化','发生在 Scan 内部,目标是少读非谓词列','Scan Profile'],
    ['⚠ 纠偏 · 文件格式过滤','不是独立大类','Parquet/ORC 优化本质属于"减少存储单元读取"','—']
  ]
};
const OPTOPERATOR_SPEC={
  title:'Doris 优化 · 按算子透视(每个算子的成本与核心优化)',
  note:'从算子视角看:每个算子有其主要成本,对应一组核心优化,本质都是"少读/少算/少传/少输出"。',
  rowH:36,
  cols:[
    {h:'算子',w:130,accent:'var(--cv-scan)'},
    {h:'主要成本',w:200,accent:'var(--cv-ink)'},
    {h:'核心优化',w:470,accent:'var(--cv-ink)'},
    {h:'本质',w:250,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['Scan','IO · 解码 · 过滤','分区/Tablet 裁剪 · 列裁剪 · ZoneMap · Bloom · 倒排 · 延迟物化','少读 · 少解码 · 少输出'],
    ['Filter','表达式计算','谓词下推 · 常量折叠 · 字典过滤 · 向量化表达式','更早、更便宜地过滤'],
    ['Join','Hash 表 · 网络 · 中间结果','Join Reorder · Runtime Filter · Broadcast · Bucket Shuffle · Colocate','小表建表 · 大表少扫 · 少 Shuffle'],
    ['Aggregate','Hash 状态 · 内存 · Shuffle','两阶段聚合 · 本地预聚合 · 聚合下推 · MV','提前压缩行数'],
    ['Sort / TopN','排序 CPU · 内存 · Spill','TopN 下推 · 局部 TopN · TopN Filter','避免全量排序'],
    ['Exchange','网络传输 · 序列化','Colocate · Bucket Shuffle · Broadcast · Local Exchange','减少跨节点移动'],
    ['Sink','输出 · 写入 · 结果传输','Result Cache · Limit 下推 · Tablet Writer · 批量写入','降低输出/写入开销'],
    ['Expression','函数调用 · 解释执行','向量化 · 表达式复用 · 字典执行 · SIMD','降低 CPU']
  ]
};
const OPTWORKLOAD_SPEC={
  title:'Doris 优化 · 按工作负载透视(不同业务类型的优先策略)',
  note:'不同查询/业务类型瓶颈不同,优先优化策略也不同。先按负载类型定位瓶颈,再选对应策略组合。',
  rowH:34,
  cols:[
    {h:'查询/业务类型',w:150,accent:'var(--cv-scan)'},
    {h:'主要瓶颈',w:250,accent:'var(--cv-ink)'},
    {h:'优先优化策略',w:520,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['点查','定位数据慢 · 全表扫风险','分区裁剪 · Bucket 裁剪 · Bloom · 主键索引 · 倒排索引'],
    ['明细过滤','扫描行数大','谓词下推 · ZoneMap · Bloom · Page Index · Runtime Filter'],
    ['宽表查询','读取字节和解码成本高','列裁剪 · 嵌套列裁剪 · 延迟物化 · 字典过滤'],
    ['多表 Join','Join 顺序 · Hash 表 · 网络','统计信息 · Join Reorder · Runtime Filter · Broadcast · Colocate'],
    ['大表聚合','Shuffle · 聚合状态 · 内存','两阶段聚合 · 本地预聚合 · 聚合下推 · MV'],
    ['TopN 排序','全量排序成本高','TopN 下推 · 局部 TopN · TopN Filter · 排序键设计'],
    ['Dashboard','重复查询 · 低延迟','Query Cache · 同步 MV · 异步 MV · Data Cache'],
    ['湖仓外表','元数据慢 · 远端 IO 慢','HMS Cache · File List Cache · Manifest 裁剪 · Footer Cache · Data Cache'],
    ['日志检索','字符串过滤慢','倒排索引 · NGram Bloom · 列裁剪 · 谓词下推'],
    ['高并发短查询','启动成本 · 调度成本','Plan Cache · Prepared Statement · Query Cache · Pipeline 并发控制'],
    ['高频导入','写入吞吐 · Compaction 压力','Load Channel · 批量写入 · 分桶均衡 · Compaction 调优']
  ]
};
const OPTOBSERVE_SPEC={
  title:'Doris 优化 · 按可观测性透视(EXPLAIN / Profile 验证优化是否生效)',
  note:'优化是否生效不能只看理论,要看 EXPLAIN(静态计划)与 Profile(执行实况)。每个观察入口对应一类优化的验证指标。',
  rowH:34,
  cols:[
    {h:'观察入口',w:200,accent:'var(--cv-scan)'},
    {h:'重点指标',w:420,accent:'var(--cv-ink)'},
    {h:'对应优化',w:300,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['EXPLAIN','分区数量 · Tablet 数量 · Join 类型 · 是否命中 MV','静态规划优化'],
    ['EXPLAIN VERBOSE','谓词是否下推 · Runtime Filter 是否生成 · Fragment 分布','FE 计划细节'],
    ['Scan Profile','RowsRead · RowsReturned · ReadBytes · FilteredRows','Scan 裁剪 · 列裁剪 · 谓词过滤'],
    ['Parquet/ORC Profile','Row Group 过滤数 · Page 过滤数 · Footer 命中','文件格式裁剪'],
    ['Runtime Filter Profile','构建时间 · 等待时间 · 过滤行数 · 命中率','Runtime Filter 效果'],
    ['Join Profile','BuildRows · ProbeRows · HashTableSize','Join 顺序和 Join 类型'],
    ['Exchange Profile','SendBytes · ShuffleRows · NetworkTime','Shuffle / Broadcast 成本'],
    ['Cache Profile','DataCacheHit · FooterCacheHit · RemoteReadBytes','湖仓缓存效果'],
    ['Pipeline Profile','OperatorTime · BlockedTime · ScheduleTime','Pipeline 并行和阻塞'],
    ['Load Profile','写入行数 · Flush 时间 · Segment 数 · Channel 等待','导入和写入瓶颈']
  ]
};
// 优化器三种规则引擎对比 RBO/CBO/HBO
const OPTCOMPARE_SPEC={
  title:'优化器规则引擎对比 · RBO / CBO / HBO',
  note:'Nereids 分三层协同:RBO 靠固定规则改写(确定性、不看数据),CBO 靠统计信息+代价模型搜索(Cascades/Memo),HBO 靠历史执行反馈校正估算偏差。执行顺序:先 RBO 改写到不动点 → 再进 CBO 搜索最优物理计划,HBO 在有历史时修正 CBO 的基数/代价估算。',
  cols:[{h:'维度',w:120,accent:'var(--cv-scan)'},{h:'RBO 规则优化',w:320,accent:'var(--cv-ink)'},{h:'CBO 代价优化',w:340,accent:'var(--cv-ink)'},{h:'HBO 历史优化',w:280,accent:'var(--cv-ink)'}],
  rows:[
    ['全称','Rule-Based Optimization','Cost-Based Optimization','History-Based Optimization'],
    ['决策依据','固定改写规则(不看数据)','统计信息 + 代价模型','历史执行的真实行数/代价反馈'],
    ['解决什么','等价变换:下推/裁剪/化简','选最优:Join 顺序/分发/算子','校正 CBO 估算偏差(尤其基数)'],
    ['典型手段','谓词下推、列裁剪、常量折叠、子查询解相关','Join Reorder(DPHyp)、分布式策略、enforcer','用历史 rowcount 覆盖估算,防坏计划复发'],
    ['是否确定性','确定(同 SQL 同结果)','依赖统计,估算可能偏','依赖历史,冷启动无数据则退化到 CBO'],
    ['执行阶段','Rewriter.execute 迭代到不动点','Optimizer.execute(Cascades Memo 搜索)','CBO 内校正基数/代价'],
    ['核心结构','规则集 RuleSet','Memo/Group/GroupExpression + CostModel','历史统计缓存'],
    ['关系','最先跑,把计划改写规整','在 RBO 结果上搜索最优','给 CBO 喂更准的估算']
  ]
};
// 同步 MV vs 异步 MTMV 对比
const MVCOMPARE_SPEC={
  title:'物化视图对比 · 同步 MV(Rollup) vs 异步 MV(MTMV)',
  note:'两类 MV 本质不同:同步 MV 是表的一个 Rollup 索引,写入时同步维护、查询自动命中,但仅单表聚合;异步 MTMV 是独立表,定时刷新、支持多表 JOIN,靠 SPJG 透明改写命中。选型:实时单表预聚合用同步 MV,复杂多表宽表用异步 MTMV。',
  cols:[{h:'维度',w:130,accent:'var(--cv-scan)'},{h:'同步 MV(Rollup / 旧物化索引)',w:420,accent:'var(--cv-ink)'},{h:'异步 MV(MTMV)',w:440,accent:'var(--cv-ink)'}],
  rows:[
    ['本质','表的一个 Rollup 索引(附属于基表)','独立的物理表(自己的 Tablet/Rowset)'],
    ['刷新时机','写入基表时同步维护(强一致,无延迟)','定时/手动刷新(MTMVTask.run),有数据延迟'],
    ['能力范围','仅单表:前缀重排 + 单表聚合(SUM/MIN/MAX…)','支持多表 JOIN + 聚合 + 过滤(SPJG 全谱)'],
    ['命中方式','计划期按前缀/聚合匹配自动选 Rollup(CollectRelation 阶段)','SPJG 透明改写(StructInfo+HyperGraph,InitMaterializationContextHook 收集)'],
    ['一致性','与基表强一致','刷新前查到旧数据;可查刷新状态'],
    ['存储成本','增量索引,较小','完整独立表,较大'],
    ['写放大','写基表即同步写 MV,有写放大','异步刷新,不阻塞基表写'],
    ['典型场景','实时单表预聚合(count/sum 加速)','多表宽表、复杂聚合、报表加速'],
    ['核心类/入口','CREATE MATERIALIZED VIEW(基表内)· CollectRelation','CREATE MATERIALIZED VIEW(独立)· MTMVService/MTMVTask · AbstractMaterializedViewRule']
  ]
};
// 部署形态对比 · 湖仓/存算一体/存算分离/冷热分离
const ARCHCOMPARE_SPEC={
  title:'部署形态对比 · 湖仓 / 存算一体 / 存算分离 / 冷热分离',
  note:'四种架构形态的取舍:数据在哪(归属)、元数据谁管、存储介质、计算在哪读、副本与可靠性、性能特征、典型场景。选型核心=数据归属 + 成本/弹性诉求。',
  cols:[{h:'维度',w:120,accent:'var(--cv-scan)'},{h:'湖仓架构',w:255,accent:'var(--cv-ink)'},{h:'存算一体',w:235,accent:'var(--cv-ink)'},{h:'存算分离',w:255,accent:'var(--cv-ink)'},{h:'冷热分离',w:230,accent:'var(--cv-ink)'}],
  rows:[
    ['数据归属','外部湖仓/外部数据库','Doris 内部','Doris 内部','Doris 内部(本地+远程)'],
    ['主要目标','跨源查询、湖仓联邦分析','高性能 OLAP、部署简单','弹性计算、降副本成本','降冷数据本地磁盘成本'],
    ['元数据管理','外部 Catalog + FE 缓存','FE BDB JE','MetaService + FoundationDB','FE BDB JE + Storage Policy'],
    ['存储介质','HDFS/S3/外部系统','BE 本地磁盘','对象存储/共享存储','本地磁盘 + 远程存储'],
    ['计算位置','BE 执行算子,外部 Scan 读湖仓','BE 本地计算+本地读','Compute Node 计算+远程读+FileCache','BE 本地计算,冷热分别本地/远程读'],
    ['副本策略','外部系统负责','多副本(默认 3)','对象存储保障,计算节点无本地副本','热数据多副本,冷数据远程'],
    ['性能特点','灵活,受外部元数据/远程存储影响','稳定,低网络开销','弹性强,依赖 FileCache 命中+对象存储','热快,冷成本低但读链路更长'],
    ['典型场景','数据湖探索、跨 Catalog JOIN、低频联邦','核心数仓、BI、实时、服务化查询','云上弹性数仓、多租户、冷热容量巨大','历史明细保留、低频冷查、成本优化'],
    ['核心类','ExternalCatalog / ExternalMetaCacheMgr','StorageEngine / Tablet','CloudStorageEngine / MetaServiceImpl / FdbTxnKv','Tablet::cooldown() / StoragePolicy']
  ]
};
const IDXPANO_SPEC={
  id:'idxpano', title:'Doris 索引全景透视表 · 9 类索引 × 关键维度',
  note:'9 类索引各司其职:ShortKey/PK 定位 rowid;Ordinal 每列强制(缺失报 Corruption);ZoneMap 自动 min/max 跳 Page;Bloom/NGram BF 有假阳性做等值/模糊预筛;Inverted 精确到行(Roaring Bitmap)做全文;ANN 近似向量 TopK;Delete Bitmap 是 MoW 删除语义(存 RocksDB 非磁盘文件)。会话变量:NGram LIKE 下推需 enable_function_pushdown;Inverted 有 skip_threshold 降级;ANN 有 hnsw_ef_search/ivf_nprobe(默 32)。DDL:BF 用 bloom_filter_columns;NGram/Inverted/ANN 用 INDEX...USING;其余全自动。',
  rowH:38,
  cols:[
    {h:'维度',w:100,accent:'var(--cv-scan)'},
    {h:'Short Key 前缀',w:148,accent:'var(--cv-ink)'},
    {h:'Primary Key 主键',w:148,accent:'var(--cv-ink)'},
    {h:'Ordinal 行号',w:128,accent:'var(--cv-ink)'},
    {h:'Zone Map 区间',w:150,accent:'var(--cv-ink)'},
    {h:'Bloom 布隆',w:148,accent:'var(--cv-ink)'},
    {h:'NGram BF',w:148,accent:'var(--cv-ink)'},
    {h:'Inverted 倒排',w:172,accent:'var(--cv-ink)'},
    {h:'ANN 向量',w:160,accent:'var(--cv-ink)'},
    {h:'Delete Bitmap',w:150,accent:'var(--cv-ink)'}
  ],
  rows:[
    ['核心定位','排序键前缀范围定位','MoW 主键点查','行号→Page 内部寻址','min/max/null 裁剪','Page 级等值概率过滤','字符串子串概率过滤','rowid 级倒排过滤','向量 TopK 候选召回','MoW 更新删除可见性'],
    ['是否可选','非 MoW 强制','MoW 强制','每列强制 缺失报错','自动创建','手动指定列','手动指定列','手动指定列','手动指定列','MoW 强制'],
    ['适用 Key','DUP/AGG/UNI-MOR','UNI-MOW 专有','全部','全部','全部','全部','DUP/MOW;AGG仅Key;MOR非Key受限','仅 DUP 或 MOW','UNI-MOW 专有'],
    ['适用列','Sort Key 前 ≤3列/36B','全部主键列','每列(强制)','除 STRUCT/ARRAY/MAP','除 STRUCT/ARRAY/MAP','仅字符串 VARCHAR等','字符串/数值/日期/VARIANT','ARRAY<FLOAT> NOT NULL','行级(无列限制)'],
    ['存储位置','.dat 内 ShortKey Page','.dat 内 PK Index Page','.dat 内 Ordinal Page','.dat 内 Footer+ZoneMap','.dat 内 BF Page','.dat 内(与 BF 共用)','独立 .idx(V1/V2/V3)','独立 .idx(V2/V3 无V1)','BE RocksDB(rowset,seg,ver)'],
    ['索引粒度','每 1024 行一项','每行(BTree)','每 Page 一偏移','Segment+Page(min/max)','Page 级(每Page一BF)','Page 级(NGram BF)','行级(精确 rowid)','Segment 级(向量图/聚类)','行级(精确 rowid)'],
    ['支持谓词','前缀范围 =<> BETWEEN','等值点查 =','内部定位 不过滤','=<><=>= BETWEEN ISNULL','= / IN','LIKE %sub%(需下推)','MATCH/=/</>/IN/LIKE','ORDER BY dist LIMIT k','标记删除(非谓词)'],
    ['过滤精度','精确 无假阳','精确 BTree','精确 行号映射','Page 精确 min/max','有假阳 FPP=0.05','有假阳(bf_size 定)','精确 Roaring','近似 非精确 TopK','精确 位图'],
    ['过滤层级','Segment 级','Segment 级','Page 级(内部)','Page 级(跳 Page)','Page 级(跳 Page)','Page 级(跳 Page)','行级(跳整 Page)','Segment 级(候选 rowid)','行级(跳删除行)'],
    ['写入开销','极低','中(BTree+bitmap)','极低','极低(min/max)','低(Murmur3)','低~中(n-gram hash)','高(分词+Lucene)','高(向量图+Faiss训练)','中(异步+RowIdConv)'],
    ['查询开销','极低(二分)','极低(BTree 点查)','极低(透明)','极低(内存比较)','低(hash 探测)','低(NGram hash)','低~中(Roaring AND+缓存)','中~高(向量距离)','极低(RocksDB 点查)'],
    ['在线 ADD INDEX','否(需 SC)','否','否','否','是(SET 触发 SC)','是(ADD 触发重建)','是(可仅对新数据)','是','否'],
    ['Compaction','随 Segment 重建','随重建 +RowIdConv','随 Segment 重建','随 Segment 重建','随 Segment 重建','随 Segment 重建','Index Compaction 独立合 .idx','随 Segment 重建','RowIdConversion 映射新 Rowset'],
    ['典型场景','时间/ID 范围扫描','MoW 主键点查/CDC','支撑所有列读取','数值/日期范围过滤','高基数列等值','URL/日志模糊匹配','全文检索/日志分析','向量相似/推荐/图像','MoW 更新/删除语义'],
    ['主要限制','仅 Sort Key 前缀有效','仅 MoW;写有 bitmap 开销','不可禁用 缺失报错','字符串 max 截断 512B','无范围;5% 假阳;无嵌套','仅字符串;bf≤65535','写开销高;有降级机制','仅 ARRAY<FLOAT> NOT NULL 近似','仅 MoW;存 RocksDB 非文件'],
    ['主要收益','缩小有序扫描范围','加速 MoW 更新/点查','支撑 Page 精确寻址','跳过不命中 Page/Segment','跳过等值不命中 Page','加速包含型字符串过滤','大幅减少行扫描 支持全文','向量相似搜索降成本','保证更新删除语义 不读旧行'],
    ['核心心智模型','按有序前缀找到大概范围','主键直接找到行','知道 rowid 后找到 Page','用 min/max 判定此页不可能命中','用概率结构判定此页大概率没有','切片字符串后 BF 判是否可能含','用词项/值直接拿 rowid 集合','用近似图/聚类先召回相似向量','把被覆盖的旧行扣掉']
  ]
};

const EXPLAIN_SPEC={
  title:'EXPLAIN 诊断命令 · 语法 EXPLAIN [planType] [level] [PROCESS] <query>(只看计划,不执行)',
  note:'planType 选阶段产物:PARSED(未绑定 AST 计划)→ANALYZED(绑定后)→REWRITTEN=LOGICAL(RBO 改写后)→OPTIMIZED=PHYSICAL(CBO 定型)→SHAPE(只留结构做回归)→MEMO(Cascades 搜索空间/代价)→DISTRIBUTED(分片/Exchange)→ALL(默认,全阶段)。level 控输出形态:VERBOSE(带表达式/类型/统计)、TREE、GRAPH(点线图)、PLAN、DUMP。★ Doris 无 EXPLAIN ANALYZE —— 真实运行耗时看 Query Profile(set enable_profile=true 后从 FE Web UI / show query profile 取)。',
  cols:[{h:'命令',w:300,accent:'var(--cv-scan)',mono:true,hi:true},{h:'输出内容',w:300,accent:'var(--cv-ink)'},{h:'对应阶段',w:200,accent:'var(--cv-ink)'},{h:'何时用',w:290,accent:'var(--cv-ink)'}],
  rows:[
    ['EXPLAIN <sql>','默认 = EXPLAIN ALL,各阶段计划全打','Parser→CBO 全程','快速总览一条 SQL 的计划'],
    ['EXPLAIN PARSED PLAN','Parser 产出的未绑定逻辑计划(AST→Plan)','① 解析','看 SQL 是否被正确解析'],
    ['EXPLAIN ANALYZED PLAN','绑定元数据后的逻辑计划(列/类型已解析)','② 分析绑定','排查列歧义/类型/权限绑定问题'],
    ['EXPLAIN REWRITTEN / LOGICAL PLAN','RBO 规则改写后逻辑计划(谓词下推/列裁剪/子查询解相关)','③ RBO 改写','看规则是否生效(下推/裁剪)'],
    ['EXPLAIN OPTIMIZED / PHYSICAL PLAN','CBO 定型的物理计划(Join 顺序/分发/算子)','④ CBO 优化','看最终执行计划与 Join 策略'],
    ['EXPLAIN SHAPE PLAN','只留计划结构(去掉 id/统计),稳定可比','④ 之后','计划形状回归测试对比'],
    ['EXPLAIN MEMO PLAN','Cascades Memo:Group/GroupExpression + 各候选代价','④ CBO 内部','排查为何没选中期望计划/代价'],
    ['EXPLAIN DISTRIBUTED PLAN','分片计划:PlanFragment 切分 + Exchange 分发','⑤ 分片','看并行度/Shuffle/Fragment 边界'],
    ['EXPLAIN VERBOSE <sql>','在上述基础上附表达式、输出列类型、行数估算','(修饰 level)','需要看统计估算/表达式细节时'],
    ['EXPLAIN GRAPH <sql>','ASCII 点线拓扑图(节点+边)','(修饰 level)','直观看算子拓扑'],
    ['set enable_profile=true; <sql>','非 EXPLAIN:真实执行后产出 Query Profile','运行时实测','量真实耗时/行数/内存,定位瓶颈'],
    ['show query profile "/<queryId>"','取已执行查询的 Profile 五段树','运行时实测','事后按 queryId 拉 Profile']
  ]
};

// 通用表格渲染器(术语表 / 架构对比)—— DuckDB/ClickHouse 文档式干净多列表
// spec:{title, note, cols:[{h,w}], rows:[[cell,...]], groups?:[{label,at}]}
function renderTableSVG(out, spec){
  const NS='http://www.w3.org/2000/svg';
  const esc=t=>String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const padX=24, top0=18, W=spec.cols.reduce((a,c)=>a+c.w,0)+padX*2;
  const titleH=spec.note?76:32, headH=34, rowH=spec.rowH||40;
  // 计算每行高度(按最长单元格折行)
  const cpl=c=>Math.max(4,Math.floor((c.w-20)/(c.mono?6.9:12.6)));
  // 按词/标点边界折行(避免把 SearchArgument、s3.endpoint 等词从中间截断)
  function wrapCell(raw, per){
    raw=String(raw); if(raw.length<=per) return [raw];
    var toks=raw.match(/[A-Za-z0-9_.\-]+|[^A-Za-z0-9_.\-]/g)||[raw];  // 连续英数.-_ 为一个词,其余(含中文/空格/标点)逐字
    var lines=[], cur='';
    toks.forEach(function(tk){
      if(cur.length+tk.length>per && cur.length>0){ lines.push(cur); cur=''; }
      if(tk.length>per){ // 超长单词硬切
        if(cur){lines.push(cur);cur='';}
        for(var i=0;i<tk.length;i+=per) lines.push(tk.slice(i,i+per));
        cur=lines.pop()||'';
      } else cur+=tk;
    });
    if(cur) lines.push(cur);
    return lines.length?lines:[''];
  }
  const rowLines=spec.rows.map(r=>Math.max.apply(null,r.map((cell,ci)=>{
    const txt=String(cell||'').replace(/<[^>]+>/g,'');
    return Math.max(1, wrapCell(txt, cpl(spec.cols[ci])).length);
  })));
  const rowHs=rowLines.map(n=>Math.max(rowH,14+n*17));
  let H=top0+titleH+headH+rowHs.reduce((a,b)=>a+b,0)+18;
  let svg='<svg id="svg-'+(spec.id||'tbl')+'" class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block;margin:0 auto" xmlns="'+NS+'">';
  // 外框
  svg+='<rect x="'+(padX-1)+'" y="'+top0+'" width="'+(W-padX*2+2)+'" height="'+(H-top0-10)+'" rx="12" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1"/>';
  // 标题
  svg+='<text x="'+padX+'" y="'+(top0+22)+'" fill="var(--cv-ink)" font-size="15" font-weight="700" font-family="var(--sans)">'+esc(spec.title)+'</text>';
  if(spec.note) svg+='<foreignObject x="'+padX+'" y="'+(top0+30)+'" width="'+(W-padX*2)+'" height="40"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:11px;line-height:1.5;color:var(--cv-ink2);font-family:var(--sans)">'+esc(spec.note)+'</div></foreignObject>';
  // 表头
  let hy=top0+titleH;
  let cxs=[padX]; spec.cols.forEach(c=>cxs.push(cxs[cxs.length-1]+c.w));
  svg+='<rect x="'+padX+'" y="'+hy+'" width="'+(W-padX*2)+'" height="'+headH+'" fill="var(--cv-card-alt)"/>';
  spec.cols.forEach((c,ci)=>{
    svg+='<text x="'+(cxs[ci]+12)+'" y="'+(hy+headH/2+4)+'" fill="'+(c.accent||'#5b8cff')+'" font-size="12" font-weight="700" font-family="var(--sans)">'+esc(c.h)+'</text>';
    if(ci>0) svg+='<line x1="'+cxs[ci]+'" y1="'+hy+'" x2="'+cxs[ci]+'" y2="'+(H-18)+'" stroke="var(--cv-border)" stroke-width="1"/>';
  });
  // 行
  let ry=hy+headH;
  spec.rows.forEach((r,ri)=>{
    const rh=rowHs[ri];
    svg+='<rect x="'+padX+'" y="'+ry+'" width="'+(W-padX*2)+'" height="'+rh+'" fill="'+(ri%2?'var(--cv-card)':'var(--cv-card-alt)')+'"/>';
    r.forEach((cell,ci)=>{
      const c=spec.cols[ci], first=(ci===0);
      const fill=first?'var(--cv-ink)':'var(--cv-ink2)', fw=first?'600':'400', fam=c.mono?'var(--mono)':'var(--sans)', fs=c.mono?'10.5':'11.5';
      // 折行输出(按词边界)
      const raw=String(cell||''); const lines=wrapCell(raw, cpl(c));
      lines.forEach((ln,k)=>{
        const painted=c.hi?planHighlight(ln):esc(ln);
        svg+='<text x="'+(cxs[ci]+12)+'" y="'+(ry+18+k*17)+'" fill="'+fill+'" font-size="'+fs+'" font-weight="'+fw+'" font-family="'+fam+'">'+painted+'</text>';
      });
    });
    ry+=rh;
  });
  svg+='</svg>';
  out.innerHTML=svg;
  out.style.transform='none';   // 表格自然尺寸,清除上一个流图残留缩放
}

// ===== 快速开始:上手教程步骤数据(命令/SQL 可照做)=====
const STEPS_SPECS={
  qssetup:{ accent:'#0071e3', title:'环境搭建 · 官方 start-doris.sh 一键启动', single:true,
    intro:'Docker 一键拉起本地 FE+BE。仅本地开发用(容器销毁丢数据、示例单副本);前提:Docker + vm.max_map_count≥2000000。',
    steps:[
      {t:'一键启动并验证', d:'', lang:'bash',
       code:"# 1) 一键安装并启动集群(-v 指定版本)\ncurl -fsSL https://doris.apache.org/files/start-doris.sh | bash -s -- -v 4.1.2\n\n# 2) 验证:FE 的 join/alive 均 true、BE 的 alive=1 即就绪\nmysql -uroot -P9030 -h127.0.0.1 -e 'SELECT `host`,`join`,`alive` FROM frontends(); SELECT `host`,`alive` FROM backends();'"}
    ]},
  qsddl:{ accent:'#0071e3', title:'建库建表 · 三步:建库 → 三种表模型 → 验证',
    intro:'Doris 表三选一模型并行对比:Duplicate(明细可重复)、Aggregate(导入预聚合)、Unique(主键 MoW 实时更新)。共性:分区(Partition 按时间裁剪)+ 分桶(DISTRIBUTED BY HASH 决定并行度与均衡)。',
    steps:[
      {t:'创建数据库', d:'库是命名空间,后续表都建在库下;USE 切当前库', lang:'sql',
       code:'CREATE DATABASE IF NOT EXISTS demo;\nUSE demo;'},
      {t:'三种表模型(并行对比,按场景三选一)', d:'KEY 语义不同:DUPLICATE 只排序不去重;UNIQUE 主键去重可更新(MoW);AGGREGATE 按 KEY 预聚合 VALUE',
       cols:[
        {t:'Duplicate · 明细日志', d:'不去重,DUPLICATE KEY 仅定前缀排序列',
         code:"CREATE TABLE site_visit (\n  visit_date DATE NOT NULL,\n  user_id BIGINT NOT NULL,\n  page VARCHAR(128),\n  duration INT\n)\nDUPLICATE KEY(visit_date,user_id)\nPARTITION BY RANGE(visit_date)(\n  PARTITION p202601\n  VALUES LESS THAN('2026-02-01')\n)\nDISTRIBUTED BY HASH(user_id)\n  BUCKETS 10\nPROPERTIES('replication_num'='1');"},
        {t:'Unique · 主键 MoW', d:'导入即去重,支持实时更新/删除,查询无 merge 开销',
         code:"CREATE TABLE user_profile (\n  user_id BIGINT NOT NULL,\n  city VARCHAR(64),\n  level INT,\n  update_ts DATETIME\n)\nUNIQUE KEY(user_id)\nDISTRIBUTED BY HASH(user_id)\n  BUCKETS 10\nPROPERTIES(\n 'replication_num'='1',\n 'enable_unique_key_merge_on_write'\n   ='true'\n);"},
        {t:'Aggregate · 预聚合', d:'导入按 KEY 预聚合,VALUE 声明 SUM/MAX/REPLACE',
         code:"CREATE TABLE sales_agg (\n  dt DATE NOT NULL,\n  city VARCHAR(64),\n  revenue BIGINT SUM,\n  orders BIGINT SUM\n)\nAGGREGATE KEY(dt,city)\nDISTRIBUTED BY HASH(city)\n  BUCKETS 8\nPROPERTIES('replication_num'='1');"}
       ]},
      {t:'验证表结构', d:'SHOW CREATE TABLE 回显最终 DDL(含默认属性);DESC 看列;SHOW TABLES 列出库内表', lang:'sql',
       code:'SHOW TABLES;\nDESC demo.site_visit;\nSHOW CREATE TABLE demo.user_profile\\G'}
    ]},
  qsingest:{ accent:'#0071e3', title:'数据写入 · 三条导入通路(视图内切换)', colsAsTabs:true,
    intro:'按数据来源选通路:本地文件/程序实时→Stream Load(HTTP,同步);已在表里/子查询→INSERT INTO SELECT;HDFS/对象存储大批量→Broker Load(异步)。三者都走同一套导入事务:MemTable→Segment→publish 后可见。',
    steps:[
      {t:'三条导入通路(点左侧切换)', d:'按来源选:实时/本地→Stream Load;表间加工→INSERT;大批量→Broker Load',
       cols:[
        {t:'Stream Load(同步 HTTP)', d:'curl PUT 到 stream_load 接口;label 保证幂等(重复 label 拒绝);同步返回 JSON 看 Status。CSV 用 column_separator/columns;JSON 加 format:json + jsonpaths + strip_outer_array',
         code:"# CSV\ncurl --location-trusted -u root: \\\n  -H 'label:visit_20260101_1' \\\n  -H 'column_separator:,' \\\n  -H 'columns:visit_date,user_id,page,duration' \\\n  -T ./visit.csv \\\n  http://<fe_ip>:8030/api/demo/site_visit/_stream_load\n\n# JSON\ncurl --location-trusted -u root: \\\n  -H 'format:json' -H 'strip_outer_array:true' \\\n  -H 'jsonpaths:[\"$.user_id\",\"$.city\"]' \\\n  -T ./users.json \\\n  http://<fe_ip>:8030/api/demo/user_profile/_stream_load"},
        {t:'INSERT(VALUES / SELECT)', d:'小批量直插或表间加工;INSERT INTO SELECT 可跨表/带聚合,内部同样走导入事务(MemTable→Segment→publish)',
         code:"-- 直插小批量\nINSERT INTO demo.site_visit VALUES\n  ('2026-01-01', 1001, '/home', 30),\n  ('2026-01-01', 1002, '/item', 75);\n\n-- 表间加工(带聚合)\nINSERT INTO demo.sales_agg\nSELECT dt, city, sum(revenue), count(*)\nFROM demo.raw_orders\nGROUP BY dt, city;"},
        {t:'Broker Load(HDFS/S3 异步)', d:'大批量首选;FE 拆子任务后台并行,提交即返回 label,SHOW LOAD 轮询进度',
         code:"LOAD LABEL demo.bulk_20260101 (\n  DATA INFILE('s3://bucket/visit/*.parquet')\n  INTO TABLE site_visit\n  FORMAT AS 'parquet'\n)\nWITH S3 (\n  's3.endpoint'='...',\n  's3.access_key'='...',\n  's3.secret_key'='...'\n);"}
       ]},
      {t:'查看导入结果', d:'Stream Load 同步返回 JSON;Broker Load 用 SHOW LOAD 看 State=FINISHED;再 count 验证行数', lang:'sql',
       code:"SHOW LOAD FROM demo ORDER BY CreateTime DESC LIMIT 5\\G\nSELECT count(*) FROM demo.site_visit;"}
    ]},
  qsexport:{ accent:'#0071e3', title:'数据导出 · 三条通路并行对比', colsAsTabs:true,
    intro:'按目标选通路并行对比:OUTFILE(随查询同步写远端,灵活带过滤/聚合)、EXPORT(整表/分区后台拆子任务并行,适合大表)、mysqldump(兼容协议,结构+小数据迁库)。前两者写 S3/HDFS,后者走 MySQL 协议到本地。',
    steps:[
      {t:'三条导出通路(并行对比,按数据量与目标选)', d:'OUTFILE 随 SELECT 一次性写;EXPORT 异步拆分并行;mysqldump 迁移小表/结构',
       cols:[
        {t:'OUTFILE · 查询结果同步导', d:'任意 SELECT→S3/HDFS/本地;csv/parquet/orc;同步返回行数与路径',
         code:"SELECT * FROM site_visit\nWHERE visit_date>='2026-01-01'\nINTO OUTFILE\n  's3://bucket/export/visit_'\nFORMAT AS PARQUET\nPROPERTIES(\n 's3.endpoint'='...',\n 's3.access_key'='...',\n 's3.secret_key'='...'\n);"},
        {t:'EXPORT · 整表/分区异步导', d:'FE 拆多子任务并行,适合大表;提交即返回,SHOW EXPORT 查进度',
         code:"EXPORT TABLE site_visit\nPARTITION (p202601)\nTO 's3://bucket/export/sv/'\nPROPERTIES(\n 'format'='csv',\n 'max_file_size'='512MB'\n)\nWITH S3(\n 's3.endpoint'='...',\n 's3.access_key'='...',\n 's3.secret_key'='...'\n);"},
        {t:'mysqldump · 迁库/小表', d:'兼容 MySQL 协议,导结构+数据到本地;大表改用 OUTFILE/EXPORT',
         code:"mysqldump\n -h 127.0.0.1 -P 9030\n -u root\n --no-tablespaces\n demo site_visit\n > site_visit.sql\n\n# 恢复:\n# mysql ... < site_visit.sql"}
       ]},
      {t:'查看进度与选型', d:'OUTFILE/mysqldump 同步返回;EXPORT 异步用 SHOW EXPORT 看 State=FINISHED;OUTFILE 可带 GROUP BY 只导聚合结果', lang:'sql',
       code:"SHOW EXPORT FROM demo ORDER BY CreateTime DESC LIMIT 5\\G  -- State/Progress/OutfileInfo\n-- OUTFILE 只导聚合结果:\nSELECT user_id,count(*) c FROM site_visit GROUP BY user_id\nINTO OUTFILE 's3://bucket/export/uv_' FORMAT AS CSV PROPERTIES('s3.endpoint'='...');"}
    ]}
};
// 极简 shell 高亮(ClickHouse 深色配色):默认近白,注释灰斜体,字符串绿,数字暖黄,首命令/sudo 青,-flag 紫。始终包 tspan,绝不裸文本(否则默认黑=不可见)
function shHighlight(line){
  const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const CMD=/^(sudo|mysql|curl|tar|cd|ls|sh|bash|jps|ps|tail|grep|java|echo|export|systemctl|kill|scp|ssh)$/;
  var h=line.indexOf('#'); var code=line, cmt='';
  if(h>=0){ code=line.slice(0,h); cmt=line.slice(h); }
  var out='', re=/('[^']*'|"[^"]*"|\b\d+(?:\.\d+)?\b|--?[A-Za-z][\w-]*|[A-Za-z_][\w./-]*|\s+|[^\sA-Za-z0-9_'"]+)/g, m, first=true;
  while((m=re.exec(code))!==null){
    var tk=m[0], color;
    if(/^\s+$/.test(tk)){ out+=esc(tk); continue; }
    if(/^['"]/.test(tk)) color='#98c379';                 // 字符串 绿
    else if(/^\d/.test(tk)) color='#e5c07b';               // 数字 暖黄
    else if(/^--?[A-Za-z]/.test(tk)) color='#c397d8';      // -flag/--flag 紫
    else if(/^[A-Za-z_]/.test(tk)){ if(first&&CMD.test(tk)) color='#2dd4bf'; else color='#e6e6e6'; first=false; }  // 命令 青(CH 风),其余 近白
    else color='#abb2bf';                                  // 标点 灰
    out+='<tspan fill="'+color+'">'+esc(tk)+'</tspan>';
  }
  if(cmt) out+='<tspan fill="#6e7681" font-style="italic">'+esc(cmt)+'</tspan>';
  return out;
}
// ClickHouse 风 SQL 高亮:关键字/引擎 青(标志性),函数 蓝,字符串 绿,数字 暖黄,默认近白
function chSqlHi(line){
  const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  var ci=line.indexOf('--'); var code=line, cmt=''; if(ci>=0){code=line.slice(0,ci);cmt=line.slice(ci);}
  var out='', re=/('[^']*'|\b\d+(?:\.\d+)?\b|[A-Za-z_][A-Za-z0-9_]*|\s+|[^\sA-Za-z0-9_']+)/g, m;
  while((m=re.exec(code))!==null){
    var tk=m[0], color;
    if(/^\s+$/.test(tk)){ out+=esc(tk); continue; }
    if(/^'/.test(tk)) color='#98c379';                      // 字符串 绿
    else if(/^\d/.test(tk)) color='#e5c07b';                // 数字 暖黄
    else if(SQL_KW.test(tk)) color='#2dd4bf';               // 关键字 青(ClickHouse 标志色)
    else if(SQL_FN.test(tk)) color='#61afef';               // 函数 蓝
    else if(/^[^\sA-Za-z0-9_']+$/.test(tk)) color='#abb2bf';// 标点 灰
    else color='#e6e6e6';                                   // 标识符/类型 近白
    out+='<tspan fill="'+color+'">'+esc(tk)+'</tspan>';
  }
  if(cmt) out+='<tspan fill="#6e7681" font-style="italic">'+esc(cmt)+'</tspan>';
  return out;
}
// 快速开始:步骤作垂直 TAB(与「数据组织架构」一致的 .do-nav 左栏 + 右侧代码面板)
function renderStepsTabs(out, tid){
  const spec=STEPS_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▶</div><div>暂无内容</div></div>';return;}
  const escH=t=>String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const isSh=(spec.steps.some(s=>s.lang==='bash')||tid==='qssetup');
  // 一个代码块 → HTML 码卡(可选中/点击复制;复用 chSqlHi/shHighlight,tspan→span)
  function codeCard(code, lang){
    const raw=String(code);
    const t2s=s=>s.replace(/<tspan fill="([^"]*)"( font-style="italic")?>/g,
      function(_,c,it){return '<span style="color:'+c+(it?';font-style:italic':'')+'">';})
      .replace(/<\/tspan>/g,'</span>');
    const body=raw.split('\n').map(function(ln){
      return t2s((lang==='bash')?shHighlight(ln):chSqlHi(ln));
    }).join('\n');
    const enc=raw.replace(/&/g,'&amp;').replace(/"/g,'&quot;');
    return '<div class="codewrap"><button class="codecopy" data-code="'+enc+'">复制</button>'
      +'<pre class="codeblk"><code>'+body+'</code></pre></div>';
  }
  // nav(步骤作 tab)+ stage(每步一面板)
  // colsAsTabs 模式:把含 cols 的步骤展开成"每个 col 一个垂直 tab"(如 导入/导出 的三条通路),其余普通步骤照常
  const flat=[];
  spec.steps.forEach(function(st){
    if(spec.colsAsTabs && st.cols){
      st.cols.forEach(function(cc){ flat.push({t:cc.t, d:cc.d, code:cc.code, lang:cc.lang||'sql'}); });
    }else{
      flat.push(st);
    }
  });
  let navs='', secs='';
  flat.forEach(function(st,si){
    navs+='<button class="do-nav'+(si===0?' active':'')+'" data-idx="'+si+'">'
        +'<span class="do-nav-n">'+(si+1)+'</span><span class="do-nav-t">'+escH(st.t)+'</span></button>';
    let panel='<h3 class="do-h">'+escH(st.t)+'</h3>';
    if(st.d) panel+='<div class="step-desc">'+escH(st.d)+'</div>';
    if(st.cols){
      panel+='<div class="step-cols">';
      st.cols.forEach(function(cc){
        panel+='<div class="step-col"><div class="step-col-h">'+escH(cc.t)+'</div>'
             +(cc.d?'<div class="step-desc">'+escH(cc.d)+'</div>':'')
             +'<div class="do-out">'+codeCard(cc.code,'sql')+'</div></div>';
      });
      panel+='</div>';
    }else{
      panel+='<div class="do-out">'+codeCard(st.code, st.lang||(isSh?'bash':'sql'))+'</div>';
    }
    secs+='<div class="do-sec'+(si===0?' active':'')+'" data-idx="'+si+'">'+panel+'</div>';
  });
  const intro=spec.intro?('<div class="do-sqlbar"><span class="do-sqlbar-tag">说明</span><code class="do-sqlbar-code">'+escH(spec.intro)+'</code></div>'):'';
  out.innerHTML='<div class="do-paneflow">'+intro
    +'<div class="dataorg-wrap"><div class="do-nav-col"><div class="do-nav-sticky">'+navs+'</div></div>'
    +'<div class="do-stage">'+secs+'</div></div></div>';
  // nav 切换(pane 内 scope)
  const nv=[].slice.call(out.querySelectorAll('.do-nav')), sc=[].slice.call(out.querySelectorAll('.do-sec'));
  nv.forEach(function(n){ n.addEventListener('click',function(){ var i=n.getAttribute('data-idx');
    nv.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);});
    sc.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);}); }); });
  // 代码点击复制
  [].slice.call(out.querySelectorAll('.codecopy')).forEach(function(btn){
    btn.addEventListener('click',function(){
      var txt=(btn.getAttribute('data-code')||'').replace(/&quot;/g,'"').replace(/&amp;/g,'&');
      var done=function(){var o=btn.textContent;btn.textContent='已复制';btn.classList.add('ok');
        setTimeout(function(){btn.textContent=o;btn.classList.remove('ok');},1400);};
      if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,done);}
      else{var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);done();}
    });
  });
}
function renderStepsSVG(out, tid){
  const spec=STEPS_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▶</div><div>暂无内容</div></div>';return;}
  const NS='http://www.w3.org/2000/svg';
  const esc=t=>String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const W=1200, padX=18, ac=spec.accent;
  // 折行:说明文字按中文宽度估算
  function wrap(s, cpl){ s=String(s); var out=[],cur=''; for(var i=0;i<s.length;i++){var ch=s[i]; cur+=ch; var w=cur.replace(/[^\x00-\xff]/g,'xx').length; if(w>=cpl){out.push(cur);cur='';}} if(cur)out.push(cur); return out; }
  // 预计算高度
  const introLines=wrap(spec.intro, 116);
  let y=16;
  const titleH=30, introH=introLines.length*16+16;
  const introTop=y+titleH;
  let body=introTop+introH+14;
  // 每步:头(序号+标题) + 说明(折行) + 代码块(按行);cols 步骤为"视图内垂直 tab 切换"
  const TABW=168, TABH=34, TABGAP=6;   // 左侧垂直 tab 尺寸
  const metrics=spec.steps.map(function(st){
    var descLines=wrap(st.d, 108);
    if(st.cols){
      // 垂直 tab:每个 tab 一个面板 {t,d,code};面板区高 = 各面板最大高
      var panelInnerW=(W-padX*2)-44-TABW-24;   // 面板可用宽(减 tab 列 + 间距)
      var colMetrics=st.cols.map(function(cc){ return {dl:wrap(cc.d||'', 78), cl:cc.code.split('\n')}; });
      var panelH=Math.max.apply(null,colMetrics.map(c=>18+c.dl.length*14+8+(c.cl.length*16+16)));
      var tabsH=st.cols.length*TABH+(st.cols.length-1)*TABGAP;
      var areaH=Math.max(panelH, tabsH);
      var h=26 + descLines.length*15 + 10 + areaH + 16;
      return {descLines:descLines, cols:colMetrics, panelH:panelH, areaH:areaH, panelInnerW:panelInnerW, h:h};
    }
    var codeLines=st.code.split('\n');
    var h=26 /*头*/ + descLines.length*15 + 8 + (codeLines.length*16+18) + 16;
    return {descLines:descLines, codeLines:codeLines, h:h};
  });
  let cy=body; metrics.forEach(function(m){ m.top=cy; cy+=m.h+12; });
  const H=cy+8;
  let svg='<svg id="svg-'+tid+'" class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block;margin:0 auto" xmlns="'+NS+'">';
  // 顶部标题条
  svg+='<rect x="'+padX+'" y="'+y+'" width="'+(W-padX*2)+'" height="'+titleH+'" rx="8" fill="'+ac+'18" stroke="'+ac+'66"/>';
  svg+='<rect x="'+padX+'" y="'+y+'" width="4" height="'+titleH+'" rx="2" fill="'+ac+'"/>';
  svg+='<text x="'+(padX+16)+'" y="'+(y+20)+'" fill="'+ac+'" font-size="14" font-weight="700" font-family="var(--sans)">'+esc(spec.title)+'</text>';
  // 引言
  svg+='<rect x="'+padX+'" y="'+introTop+'" width="'+(W-padX*2)+'" height="'+introH+'" rx="8" fill="var(--cv-card)" stroke="var(--cv-border)"/>';
  introLines.forEach(function(ln,i){ svg+='<text x="'+(padX+14)+'" y="'+(introTop+18+i*16)+'" fill="var(--cv-ink2)" font-size="11" font-family="var(--sans)">'+esc(ln)+'</text>'; });
  // 步骤
  spec.steps.forEach(function(st,si){
    var m=metrics[si], top=m.top, bx=padX, bw=W-padX*2;
    svg+='<rect x="'+bx+'" y="'+top+'" width="'+bw+'" height="'+m.h+'" rx="12" fill="var(--cv-card)" stroke="var(--cv-border)"/>';
    var tx0=bx+44;
    if(spec.single){ tx0=bx+16; }   // 一键完成:不显序号圆,标题左移
    else { svg+='<circle cx="'+(bx+22)+'" cy="'+(top+20)+'" r="13" fill="'+ac+'"/><text x="'+(bx+22)+'" y="'+(top+25)+'" text-anchor="middle" fill="var(--cv-card)" font-size="13" font-weight="800" font-family="var(--sans)">'+(si+1)+'</text>'; }
    // 标题
    svg+='<text x="'+tx0+'" y="'+(top+25)+'" fill="var(--cv-ink)" font-size="12.5" font-weight="700" font-family="var(--sans)">'+esc(st.t)+'</text>';
    var yy=top+26+14;
    m.descLines.forEach(function(ln,i){ svg+='<text x="'+tx0+'" y="'+(yy+i*15)+'" fill="#86868b" font-size="10" font-family="var(--sans)">'+esc(ln)+'</text>'; });
    var codeTop=yy+m.descLines.length*15+6, cX=tx0;
    if(m.cols){
      // ===== 视图内垂直 tab 切换(连接式:左 rail 一体 → 活动 tab 咬入右侧深色代码面板)=====
      var grp=tid+'-'+si;                       // 该步的 tab 组 id
      var tabX=cX, panelX=tabX+TABW+16, panelW=bw-(cX-bx)-TABW-16-12;
      var railH=st.cols.length*TABH;            // tab 连续排布(无间隙)成 rail
      // rail 背景(浅色画板色)+ 描边;活动 tab 会盖住右缘形成连接
      svg+='<rect x="'+tabX+'" y="'+codeTop+'" width="'+TABW+'" height="'+railH+'" rx="10" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1"/>';
      st.cols.forEach(function(cc,ci){
        var active=(ci===0);
        var ty=codeTop+ci*TABH;                 // 连续排布
        svg+='<g class="stab" data-grp="'+grp+'" data-idx="'+ci+'" style="cursor:pointer">';
        if(active){
          // 活动:深色填充(与代码面板同色)并向右延伸 +16 盖住 rail↔面板 的缝 → 连成一体
          svg+='<rect x="'+tabX+'" y="'+ty+'" width="'+(TABW+16)+'" height="'+TABH+'" rx="10" fill="#0d1117" class="stab-bg"/>';
          svg+='<rect x="'+(tabX+1)+'" y="'+(ty+7)+'" width="3" height="'+(TABH-14)+'" rx="1.5" fill="'+ac+'" class="stab-bar"/>';
        } else {
          svg+='<rect x="'+tabX+'" y="'+ty+'" width="'+TABW+'" height="'+TABH+'" rx="0" fill="transparent" class="stab-bg"/>';
          svg+='<rect x="'+(tabX+1)+'" y="'+(ty+7)+'" width="3" height="'+(TABH-14)+'" rx="1.5" fill="transparent" class="stab-bar"/>';
        }
        svg+='<text x="'+(tabX+18)+'" y="'+(ty+TABH/2+4)+'" fill="'+(active?'#e6edf3':'#86868b')+'" font-size="11" font-weight="'+(active?'700':'500')+'" font-family="var(--sans)" class="stab-tx">'+esc(cc.t)+'</text></g>';
      });
      st.cols.forEach(function(cc,ci){
        var cm=m.cols[ci], active=(ci===0);
        // 右侧面板(全宽);非首个默认隐藏
        svg+='<g class="spanel" data-grp="'+grp+'" data-idx="'+ci+'" style="display:'+(active?'block':'none')+'">';
        var pdesc=cm.dl;
        pdesc.forEach(function(ln,k){ svg+='<text x="'+panelX+'" y="'+(codeTop+14+k*14)+'" fill="#86868b" font-size="10.5" font-family="var(--sans)">'+esc(ln)+'</text>'; });
        var pCodeTop=codeTop+14+pdesc.length*14+4;
        svg+='<rect x="'+panelX+'" y="'+pCodeTop+'" width="'+panelW+'" height="'+(cm.cl.length*16+14)+'" rx="8" fill="#0d1117" stroke="#21262d"/>';
        cm.cl.forEach(function(ln,k){ svg+='<text x="'+(panelX+12)+'" y="'+(pCodeTop+16+k*16)+'" font-size="11" font-family="var(--mono)">'+chSqlHi(ln)+'</text>'; });
        svg+='</g>';
      });
    }else{
      // 代码块(单列 · 深色码卡,高对比语法)
      var codeH=m.codeLines.length*16+14;
      svg+='<rect x="'+cX+'" y="'+codeTop+'" width="'+(bw-(cX-bx)-14)+'" height="'+codeH+'" rx="8" fill="#0d1117" stroke="#21262d"/>';
      var langTag=(st.lang==='sql')?'SQL':'SHELL';
      svg+='<text x="'+(bx+bw-22)+'" y="'+(codeTop+13)+'" text-anchor="end" fill="#8b949e" font-size="8" font-weight="700" font-family="var(--mono)">'+langTag+'</text>';
      m.codeLines.forEach(function(ln,i){
        var painted=(st.lang==='sql')?chSqlHi(ln):shHighlight(ln);
        svg+='<text x="'+(cX+12)+'" y="'+(codeTop+16+i*16)+'" font-size="11" font-family="var(--mono)">'+painted+'</text>';
      });
    }
  });
  svg+='</svg>';
  out.innerHTML=svg;
  out.style.transform='none';
  // 垂直 tab 点击切换:同组内切 active + 显隐面板
  out.querySelectorAll('.stab').forEach(function(tab){
    tab.addEventListener('click',function(){
      var grp=tab.getAttribute('data-grp'), idx=tab.getAttribute('data-idx');
      out.querySelectorAll('.stab[data-grp="'+grp+'"]').forEach(function(t){
        var on=(t.getAttribute('data-idx')===idx), bg=t.querySelector('.stab-bg'), tx=t.querySelector('.stab-tx'), bar=t.querySelector('.stab-bar');
        // 活动:深色咬入(宽 TABW+16 盖住缝)+ 蓝左条;非活动:透明
        bg.setAttribute('fill', on?'#0d1117':'transparent');
        bg.setAttribute('width', on?(TABW+16):TABW);
        bg.setAttribute('rx', on?'10':'0');
        if(bar) bar.setAttribute('fill', on?ac:'transparent');
        tx.setAttribute('fill', on?'#e6edf3':'#86868b'); tx.setAttribute('font-weight', on?'700':'500');
      });
      out.querySelectorAll('.spanel[data-grp="'+grp+'"]').forEach(function(p){
        p.style.display=(p.getAttribute('data-idx')===idx)?'block':'none';
      });
    });
  });
}

let _tourScenario='single';
// 查询分析:SQL 置顶 + 三列(逻辑流程/物理执行计划/算子流程)改为垂直 TAB 切换,每列单独渲染成一张全宽 SVG。
const _tourEsc=t=>String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function _tourSqlBar(p){
  let h='<div class="do-sqlbar"><span class="do-sqlbar-tag">示例查询 SQL</span><code class="do-sqlbar-code">';
  h+=p.sql.split('\n').map(function(ln){return sqlHighlight(ln);}).join('\n');
  return h+'</code></div>';
}
// 列1:逻辑流程(竖向链,hover 详情)
function _tourCol1(p){
  const NS='http://www.w3.org/2000/svg', esc=_tourEsc, W=880, cin=14;
  const _ch=_tourChain, chH=46, chGap=16;
  const H=_ch.length*(chH+chGap)+20;
  let svg='<svg class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block" xmlns="'+NS+'">';
  svg+='<defs><marker id="tDn1" markerWidth="9" markerHeight="9" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="var(--cv-edge)"/></marker></defs>';
  var hovers=[];
  _ch.forEach(function(st,i){
    var yy=10+i*(chH+chGap), bx=cin, bw=W-cin*2, hov=st.hover||[], star=st.star;
    if(i>0) svg+='<line x1="'+(bx+18)+'" y1="'+(yy-chGap)+'" x2="'+(bx+18)+'" y2="'+yy+'" stroke="var(--cv-edge)" stroke-width="1.2" marker-end="url(#tDn1)"/>';
    svg+='<g class="chainstep" data-hov="'+i+'">';
    svg+='<rect x="'+bx+'" y="'+yy+'" width="'+bw+'" height="'+chH+'" rx="7" fill="var(--cv-card)" stroke="#8b6cff55" stroke-width="1.1"/>';
    svg+='<circle cx="'+(bx+16)+'" cy="'+(yy+chH/2)+'" r="11" fill="#0071e3"/><text x="'+(bx+16)+'" y="'+(yy+chH/2+4)+'" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="var(--sans)">'+(i+1)+'</text>';
    svg+='<text x="'+(bx+34)+'" y="'+(yy+19)+'" fill="var(--cv-ink)" font-size="11.5" font-weight="700" font-family="var(--sans)">'+esc(st.o)+'</text>';
    svg+='<text x="'+(bx+34)+'" y="'+(yy+33)+'" fill="var(--cv-ink2)" font-size="9.2" font-family="var(--sans)">'+esc(st.act)+'</text>';
    if(star){ svg+='<rect x="'+(bx+bw-70)+'" y="'+(yy+5)+'" width="62" height="15" rx="7" fill="#0071e314" stroke="#0071e3"/><text x="'+(bx+bw-39)+'" y="'+(yy+16)+'" text-anchor="middle" fill="#0071e3" font-size="8.5" font-weight="700" font-family="var(--sans)">★'+esc(star)+'</text>'; }
    if(hov.length){ svg+='<circle cx="'+(bx+bw-12)+'" cy="'+(yy+chH-10)+'" r="7" fill="var(--cv-card)" stroke="#3d6fe0"/><text x="'+(bx+bw-12)+'" y="'+(yy+chH-7)+'" text-anchor="middle" fill="#9cc4f5" font-size="9" font-family="var(--sans)" style="pointer-events:none">?</text>'; }
    svg+='</g>';
    if(hov.length){
      var ovW=Math.min(560,bw-40), ovH=26+hov.length*15+10, ovX=bx+40, ovY=(i>=Math.ceil(_ch.length/2))?(yy+chH-ovH):yy;
      var g='<g class="hovcard" data-hov="'+i+'" style="display:none">';
      g+='<rect x="'+ovX+'" y="'+ovY+'" width="'+ovW+'" height="'+ovH+'" rx="9" fill="var(--cv-card)" stroke="#3d6fe0" stroke-width="1.4"/>';
      g+='<text x="'+(ovX+12)+'" y="'+(ovY+16)+'" fill="#0071e3" font-size="10" font-weight="700" font-family="var(--sans)">'+(i+1)+'. '+esc(st.o)+' — 详情</text>';
      hov.forEach(function(ln,li){ var isStar=(ln.charAt(0)==='★'); g+='<text x="'+(ovX+14)+'" y="'+(ovY+38+li*15)+'" fill="'+(isStar?'#b8801f':'var(--cv-ink2)')+'" font-size="9" font-weight="'+(isStar?'700':'400')+'" font-family="var(--sans)">'+esc(ln)+'</text>'; });
      g+='</g>'; hovers.push(g);
    }
  });
  hovers.forEach(function(g){svg+=g;});
  return svg+'</svg>';
}
// 列2:物理执行计划树
function _tourCol2(p){
  const NS='http://www.w3.org/2000/svg', esc=_tourEsc, W=880, cin=14, pRowH=38;
  const H=p.physical.length*pRowH+16;
  let svg='<svg class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block" xmlns="'+NS+'">';
  p.physical.forEach(function(nd,i){
    var yy=10+i*pRowH, ind=cin+2+nd.d*18;
    if(nd.d>0) svg+='<path d="M'+(cin+2+nd.d*18-11)+' '+(yy-2)+' V'+(yy+11)+' H'+(ind-3)+'" fill="none" stroke="var(--cv-edge-strong)" stroke-width="1"/>';
    svg+='<text x="'+ind+'" y="'+(yy+12)+'" font-size="11" font-weight="600" font-family="var(--mono)">'+planHighlight(nd.t)+'</text>';
    svg+='<text x="'+ind+'" y="'+(yy+26)+'" fill="var(--cv-ink2)" font-size="9" font-family="var(--sans)">'+esc(nd.s)+'</text>';
  });
  return svg+'</svg>';
}
// 列3:算子执行流程(7 层)
function _tourCol3(p){
  const NS='http://www.w3.org/2000/svg', esc=_tourEsc, W=880, cin=14;
  function opDr(){return false;}
  const hdH=24, nodeH=24, nodeGap=6, padY=9, lvGap=14;
  const nP=p.pipelines.length, pipeMaxOps=Math.max.apply(null,p.pipelines.map(pl=>pl.ops.length));
  const opH=30, opGap=6, pHeadH=17;
  let ry=10;
  const rrows=_tourLevels.map(function(L){
    var h; if(L.lv==='L5'){ h=hdH+(pHeadH+pipeMaxOps*opH+(pipeMaxOps-1)*opGap+10)+18; }
    else { var n=(L.nodes||[]).length; h=hdH+padY+n*nodeH+(n-1)*nodeGap+padY; }
    var o={L:L,top:ry,h:h}; ry+=h+lvGap; return o;
  });
  const H=ry+8;
  let svg='<svg class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block" xmlns="'+NS+'">';
  svg+='<defs><marker id="tDn3" markerWidth="9" markerHeight="9" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="var(--cv-edge)"/></marker>'
    +'<marker id="tFb3" markerWidth="8" markerHeight="8" refX="5.5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="var(--cv-edge)"/></marker></defs>';
  rrows.forEach(function(r,ri){
    var L=r.L, ac=L.accent, top=r.top, bx=cin, bw=W-cin*2;
    if(ri>0) svg+='<line x1="'+(bx+bw/2)+'" y1="'+(rrows[ri-1].top+rrows[ri-1].h)+'" x2="'+(bx+bw/2)+'" y2="'+top+'" stroke="var(--cv-edge-strong)" stroke-width="1.1" marker-end="url(#tDn3)"/>';
    svg+='<rect x="'+bx+'" y="'+top+'" width="'+bw+'" height="'+r.h+'" rx="8" fill="'+ac+'12" stroke="'+ac+'66" stroke-width="1.1"/>';
    svg+='<rect x="'+bx+'" y="'+top+'" width="4" height="'+r.h+'" rx="2" fill="'+ac+'"/>';
    svg+='<rect x="'+(bx+11)+'" y="'+(top+6)+'" width="28" height="14" rx="3" fill="'+ac+'22" stroke="'+ac+'"/>';
    svg+='<text x="'+(bx+25)+'" y="'+(top+16)+'" text-anchor="middle" fill="'+ac+'" font-size="9" font-weight="700" font-family="var(--mono)">'+L.lv+'</text>';
    svg+='<text x="'+(bx+46)+'" y="'+(top+16)+'" fill="var(--cv-ink)" font-size="11" font-weight="700" font-family="var(--sans)">'+esc(L.name)+'</text>';
    var mp=p.map[L.lv];
    if(mp) svg+='<text x="'+(bx+bw-10)+'" y="'+(top+16)+'" text-anchor="end" fill="'+ac+'" font-size="8.5" font-family="var(--sans)">▸ '+esc(mp)+'</text>';
    if(L.lv!=='L5'){
      var nx=bx+13, ny=top+hdH+padY, nw=bw-26;
      (L.nodes||[]).forEach(function(nd,i){
        var yy=ny+i*(nodeH+nodeGap);
        svg+='<rect x="'+nx+'" y="'+yy+'" width="'+nw+'" height="'+nodeH+'" rx="5" fill="var(--cv-card)" stroke="'+ac+'55" stroke-width="1"/>';
        svg+='<text x="'+(nx+11)+'" y="'+(yy+16)+'" fill="var(--cv-ink2)" font-size="10" font-family="var(--sans)">'+esc(nd)+'</text>';
      });
    }else{
      var innerX=bx+11, innerW=bw-22, pGap=10, pW=(innerW-(nP-1)*pGap)/nP, ptop=top+hdH+3;
      p.pipelines.forEach(function(pl,pi){
        var px=innerX+pi*(pW+pGap), pH=pHeadH+pl.ops.length*opH+(pl.ops.length-1)*opGap+8;
        svg+='<rect x="'+px+'" y="'+ptop+'" width="'+pW+'" height="'+pH+'" rx="6" fill="var(--cv-card)" stroke="'+ac+'88" stroke-width="1" stroke-dasharray="3 4"/>';
        svg+='<text x="'+(px+8)+'" y="'+(ptop+13)+'" fill="'+ac+'" font-size="9" font-weight="700" font-family="var(--sans)">'+esc(pl.name)+'</text>';
        pl.ops.forEach(function(op,oi){
          var oy=ptop+pHeadH+oi*(opH+opGap);
          if(oi>0) svg+='<line x1="'+(px+pW/2)+'" y1="'+(oy-opGap)+'" x2="'+(px+pW/2)+'" y2="'+oy+'" stroke="'+ac+'" stroke-width="1" opacity="0.7" marker-end="url(#tFb3)"/>';
          svg+='<rect x="'+(px+5)+'" y="'+oy+'" width="'+(pW-10)+'" height="'+opH+'" rx="4" fill="var(--cv-card)" stroke="'+ac+'66" stroke-width="1"/>';
          svg+='<text x="'+(px+10)+'" y="'+(oy+12)+'" fill="var(--cv-ink)" font-size="9" font-weight="600" font-family="var(--mono)">'+esc(op.t)+'</text>';
          svg+='<text x="'+(px+10)+'" y="'+(oy+23)+'" fill="var(--cv-ink2)" font-size="7.5" font-family="var(--sans)">'+esc(op.d)+'</text>';
        });
      });
      for(var pi=0;pi<nP-1;pi++){ var lx=innerX+pi*(pW+pGap)+pW, ly=ptop+pHeadH+opH/2; svg+='<line x1="'+lx+'" y1="'+ly+'" x2="'+(lx+pGap)+'" y2="'+ly+'" stroke="'+ac+'" stroke-width="1" stroke-dasharray="3 3" marker-end="url(#tDn3)"/>'; }
      svg+='<text x="'+(bx+bw/2)+'" y="'+(top+r.h-6)+'" text-anchor="middle" fill="var(--cv-danger)" font-size="8" font-family="var(--sans)">⛔ '+esc(p.breaker)+'</text>';
    }
  });
  return svg+'</svg>';
}
function renderTourSVG(out, tid){
  const p=TOUR_PLANS[_tourScenario]||TOUR_PLANS.single;
  const subs=[["① 逻辑流程","逻辑流程(Query Text → Block)",_tourCol1],
              ["② 物理执行计划","物理执行计划(EXPLAIN)",_tourCol2],
              ["③ 算子执行流程","算子执行流程(7 层)",_tourCol3]];
  let navs='', secs='';
  subs.forEach(function(s,si){
    navs+='<button class="do-nav'+(si===0?' active':'')+'" data-idx="'+si+'"><span class="do-nav-n">'+(si+1)+'</span><span class="do-nav-t">'+s[0]+'</span></button>';
    secs+='<div class="do-sec'+(si===0?' active':'')+'" data-idx="'+si+'"><h3 class="do-h">'+s[1]+'</h3><div class="do-out" id="tour-out-'+si+'"></div></div>';
  });
  out.innerHTML='<div class="do-paneflow">'+_tourSqlBar(p)+'<div class="dataorg-wrap"><div class="do-nav-col"><div class="do-nav-sticky">'+navs+'</div></div><div class="do-stage">'+secs+'</div></div></div>';
  out.style.transform='none';
  const done={};
  function draw(si){ if(done[si])return; const c=out.querySelector('#tour-out-'+si); if(c){done[si]=true; c.innerHTML=subs[si][2](p); if(si===0) wireTourHover(c);} }
  draw(0);
  const nv=[].slice.call(out.querySelectorAll('.do-nav')), sc=[].slice.call(out.querySelectorAll('.do-sec'));
  nv.forEach(function(n){ n.addEventListener('click',function(){ var i=n.getAttribute('data-idx');
    nv.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);});
    sc.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-idx')===i);});
    draw(parseInt(i,10)); }); });
}
function wireTourHover(c){
  c.querySelectorAll('.chainstep[data-hov]').forEach(function(step){
    var id=step.getAttribute('data-hov'), card=c.querySelector('.hovcard[data-hov="'+id+'"]');
    if(!card) return; step.style.cursor='help';
    step.addEventListener('mouseenter',function(){card.style.display='block';});
    step.addEventListener('mouseleave',function(){card.style.display='none';});
  });
}


const TREE_SPECS={
  fmttree:[
    {d:0,t:'存储格式全景 · 外表多格式 + 内表列存 V2',s:'BE 按文件格式分派到不同 reader;下方展开 ORC 文件级结构 + 内表 Segment V2 结构,两者都靠"分层统计 + 谓词下推"跳数据',tone:'root',k:'getNextReader'},
    {d:1,t:'ORC 文件结构(湖仓外表)',s:'orc/vorc_reader.cpp;自底向上读:PostScript→Footer→Stripe→RowGroup→Stream',tone:'a',k:'fmtOrcSarg'},
    {d:2,t:'File Tail · PostScript',s:'文件末尾:压缩类型、Footer 长度、version;读文件先读它定位 Footer',tone:'e'},
    {d:2,t:'File Footer',s:'schema(types)、各 Stripe 位置、每列 file 级统计(min/max/count/sum)、row 数',tone:'c'},
    {d:2,t:'Stripe(默认 ~64MB 行组)',s:'水平切分:StripeFooter + 若干列的 Index/Data Stream;SearchArgument 先按 stripe 统计跳过',tone:'e',k:'fmtOrcSarg'},
    {d:3,t:'Row Index Stream',s:'每 10000 行一个 RowGroup 的 min/max 统计 + 各 stream 定位;谓词下推的第二级跳过',tone:'d'},
    {d:3,t:'Data Stream(按列)',s:'PRESENT(null 位图)/DATA/LENGTH/DICTIONARY_DATA;编码 RLE/dict;延迟物化只读命中列',tone:'e'},
    {d:2,t:'谓词下推三级',s:'file footer 统计 → stripe 统计 → row-group(row index)统计,逐级跳过不命中数据',tone:'d',k:'fmtOrcLazy'},
    {d:1,t:'Parquet 文件结构(对照)',s:'类似分层:File→RowGroup→ColumnChunk→Page;三级跳过 row group→page index→dict',tone:'a',k:'fmtParquetRG'},
    {d:2,t:'RowGroup / ColumnChunk / Page',s:'RowGroup=水平切;ColumnChunk=一列;Page=最小编码单元(带 min/max + dict)',tone:'e',k:'fmtParquetCol'},
    {d:1,t:'Hudi / Iceberg(表格式,叠加在 Parquet/ORC 上)',s:'表格式管快照/增量/删除;底层 base 文件仍是 Parquet/ORC',tone:'a'},
    {d:2,t:'Hudi COW / MOR',s:'COW=原生读 base;MOR=JNI 合并 base+log',tone:'e',k:'fmtHudiJni'},
    {d:2,t:'Iceberg delete',s:'position delete(行号)/ equality delete(主键值)v2 语义 + 时间旅行',tone:'e',k:'fmtIcebergDelete'},
    {d:1,t:'内表列存 V2 · Segment on-disk',s:'segment_v2;Doris 自有格式,尾部元数据 + 列数据 + 多索引',tone:'b',k:'fmtSegFooter'},
    {d:2,t:'SegmentFooterPB(尾部)',s:'Footer + PBSize(4) + Checksum(4) + Magic(4);含 columns/num_rows/compress_type',tone:'c',k:'fmtSegFooter'},
    {d:2,t:'ColumnMetaPB(每列)',s:'column_id/type/encoding/compression/is_nullable/indexes/dict_page',tone:'e'},
    {d:2,t:'三索引(page 级裁剪)',s:'OrdinalIndex(行号→page)/ZoneMapIndex(min-max)/BloomFilterIndex',tone:'d',k:'fmtColReader'},
    {d:2,t:'页编码',s:'BinaryDict(字符串字典)/BitShuffle(定宽)/RLE(低基数)/FrameOfReference(整数)/Plain',tone:'e',k:'fmtPageEnc'}
  ],
  profiletree:[
    {d:0,t:'Query Profile',s:'一次查询的完整 Profile 树(profile_level 1–3 控制 Counter 详细度)',tone:'root'},
    {d:1,t:'① Summary',s:'Profile ID · Task Type · Start/End Time · Total · Task State · User · Default Catalog/Db · Sql Statement',tone:'a'},
    {d:1,t:'② Execution Summary',s:'执行过程总结:含 Planner 各阶段耗时',tone:'a'},
    {d:1,t:'③ Changed Session Variables',s:'本次查询改动过的 session 变量(便于复现)',tone:'a'},
    {d:1,t:'④ MergedProfile',s:'跨 BE/PipelineTask 聚合;每计数器给 min/avg/max,对比 InputRows↔RowsProduced 看倾斜',tone:'b'},
    {d:2,t:'Fragment N',s:'一个计划分片',tone:'c'},
    {d:3,t:'Pipeline N (instance_num=X)',s:'instance_num = 所有 BE 上该 Pipeline 的 PipelineTask 数之和',tone:'d'},
    {d:4,t:'HASH_JOIN_OPERATOR',s:'CommonCounters: ExecTime(不含上游)· RowsProduced · WaitForDependency;Custom: ProbeRows',tone:'e'},
    {d:4,t:'HASH_JOIN_SINK_OPERATOR',s:'InputRows(接收行数)· MemoryUsageHashTable(build 侧哈希表内存)',tone:'e'},
    {d:4,t:'AGGREGATION_SINK_OPERATOR',s:'InputRows · MemoryUsageHashTable · MemoryUsageSerializeKeyArena',tone:'e'},
    {d:4,t:'OLAP_SCAN_OPERATOR',s:'RowsProduced · WaitForDependency[OLAP_SCAN_OPERATOR_DEPENDENCY]Time',tone:'e'},
    {d:4,t:'EXCHANGE_OPERATOR',s:'BlocksProduced · OpenTime/InitTime/CloseTime · WaitForData;L2: DecompressTime · DeserializeRowBatchTimer · Remote/LocalBytesReceived',tone:'e'},
    {d:4,t:'DATA_STREAM_SINK_OPERATOR',s:'BlocksProduced · WaitForRpcBufferQueue · WaitForLocalExchangeBuffer',tone:'e'},
    {d:1,t:'⑤ DetailProfile',s:'每个 Fragment/Pipeline 的 PipelineTask 在所有 BE 上的执行细节(未聚合原始值)',tone:'b'},
    {d:2,t:'按 BE × instance 展开(同上层级)',s:'确认瓶颈算子后,深入看是哪个实例/哪个 BE 慢或倾斜',tone:'c'}
  ],
  profilefmt:[
    {d:0,t:'Profile 数据格式 · RuntimeProfile 计数器模型',s:'每个算子一棵 RuntimeProfile;节点 = 有序 Counter 树 + 子 Profile。文本形态即 FE Web UI / show query profile 所见',tone:'root'},
    {d:1,t:'计数器单位 TUnit(决定数值如何格式化)',s:'add_counter(name, TUnit) 决定渲染:12ms / 3.5M rows / 256MB / 1.2K',tone:'a'},
    {d:2,t:'TIME_NS / TIME_MS',s:'耗时,纳秒/毫秒;渲染为 human 时间(如 12s446ms)。SCOPED_TIMER 累加',tone:'e'},
    {d:2,t:'UNIT(计数)',s:'行数/块数;渲染带 K/M/B(如 3.5M)。RowsProduced / InputRows',tone:'e'},
    {d:2,t:'BYTES',s:'内存/网络字节;渲染 KB/MB/GB。MemoryUsage* / BytesReceived',tone:'e'},
    {d:2,t:'UNIT_PER_SECOND / BYTES_PER_SECOND',s:'吞吐速率;派生计数器(rows/s、MB/s)',tone:'e'},
    {d:1,t:'计数器种类',s:'按语义分三类,决定阅读方式',tone:'b'},
    {d:2,t:'CommonCounters(通用)',s:'每算子都有:ExecTime(不含上游)· RowsProduced · WaitForDependency · Open/Init/CloseTime',tone:'c'},
    {d:2,t:'Custom Counters(算子特有)',s:'如 HashJoin 的 ProbeRows/BuildRows · Scan 的 ScannedRows · Exchange 的 DeserializeTime',tone:'c'},
    {d:2,t:'Info String(非数值)',s:'键值文本:算子类型、谓词、表名等;不参与聚合',tone:'c'},
    {d:1,t:'child_counter_map(层级关系)',s:'计数器可挂父计数器 → 缩进树;如 DecompressTime 挂在 ExchangeTime 下',tone:'a'},
    {d:1,t:'聚合格式 min/avg/max(MergedProfile)',s:'跨 BE × PipelineTask 合并:每计数器给 [min, avg, max] 三元组;三者差距大 = 数据倾斜信号',tone:'b'},
    {d:1,t:'profile_level(1–3,控详细度)',s:'1=只 CommonCounters(默认省开销)· 2=+Custom · 3=全量含 L2/L3 细粒度;set profile_level 调',tone:'d'},
    {d:1,t:'采集机制',s:'RuntimeProfile::add_counter 建树;SCOPED_TIMER / COUNTER_UPDATE 执行中累加;结束 BE 序列化上报 → FE 反序列化 + merge',tone:'d'}
  ],
  memtree:[
    {d:0,t:'Process MemTracker(进程根)',s:'process_memory_limit;GlobalMemoryArbitrator 全局仲裁,超限触发 GC/cancel',tone:'root',k:'memArbitrator'},
    {d:1,t:'Type::GLOBAL',s:'生命周期同进程:Cache/元数据/TabletMeta 等常驻内存',tone:'a'},
    {d:1,t:'Type::QUERY',s:'所有 Query 任务;每 query 一个 MemTrackerLimiter,带 _limit(query_mem_limit)',tone:'b',k:'memTracker'},
    {d:2,t:'Query-<id> Limiter',s:'单查询上限;consume/try_reserve 超限返回 QUERY_MEMORY_EXCEEDED',tone:'c'},
    {d:3,t:'consumer MemTracker(算子级)',s:'Hash/Agg/Sort 等算子的 MemTracker(仅统计不限流),push 进 _consumer_tracker_stack',tone:'e'},
    {d:1,t:'Type::LOAD',s:'所有 Load 任务;MemTable 内存,超阈值触发 flush 反压',tone:'b',k:'memLoadLimiter'},
    {d:1,t:'Type::COMPACTION',s:'Base/Cumulative compaction 任务内存',tone:'a'},
    {d:1,t:'Type::SCHEMA_CHANGE',s:'SchemaChange 任务内存',tone:'a'},
    {d:1,t:'Type::OTHER',s:'Clone/Snapshot 等其它任务',tone:'a'},
    {d:1,t:'consume 三级链路(每线程)',s:'ThreadMemTrackerMgr.consume → _untracked_mem 批量攒够 min_size → flush → _limiter_tracker.consume',tone:'d',k:'memThreadMgr'},
    {d:1,t:'try_reserve 三级检查',s:'CHECK_TASK & CHECK_WORKLOAD_GROUP & CHECK_PROCESS;任一超限则逐级 rollback',tone:'d'}
  ],
  stattbl:[
    {d:0,t:'表级统计 TableStatsMeta',s:'每表一个,AnalysisManager 持有 idToTblStats: Map<tblId,TableStatsMeta>;持久化+内存双份;驱动是否重采集',tone:'root'},
    {d:1,t:'规模计数',s:'表整体行数与变更量',tone:'b'},
    {d:2,t:'rowCount',s:'表总行数(上次 analyze 时的快照)',tone:'e'},
    {d:2,t:'updatedRows(AtomicLong)',s:'自上次 analyze 后累计变更行数;与 rowCount 之比 = 过期程度',tone:'e'},
    {d:1,t:'变更标志',s:'触发重采集的信号位',tone:'b'},
    {d:2,t:'partitionChanged(AtomicBoolean)',s:'新分区加载 → 触发重分析',tone:'e'},
    {d:2,t:'userInjected',s:'用户手动注入统计 → 自动采集跳过,尊重人工值',tone:'e'},
    {d:1,t:'关联索引',s:'指向列级统计与物化索引',tone:'b'},
    {d:2,t:'colToColStatsMeta',s:'Pair<idxId,col>→ColStatsMeta,记每列采集元信息(采集时间/方法/版本)',tone:'e'},
    {d:2,t:'indexesRowCount / queriedTimes',s:'各物化索引行数;被查次数(冷热参考)',tone:'e'},
    {d:1,t:'健康度驱动采集',s:'getTableHealth = updatedRows≥total?0:(1−updated/total)×100;<阈值 TABLE_STATS_HEALTH_THRESHOLD=90 则重采',tone:'d'},
    {d:1,t:'采集任务 AnalysisInfo',s:'AnalysisMethod{SAMPLE,FULL} · Type{FUNDAMENTALS,INDEX,HISTOGRAM} · JobType{MANUAL,SYSTEM};大表按 samplePercent 采样',tone:'d'}
  ],
  statcol:[
    {d:0,t:'列级统计 ColumnStatistic',s:'CBO 选择率估算的核心输入;fromResultRow 从 __internal_schema.column_statistics 反序列化,内存缓存',tone:'root'},
    {d:1,t:'基数与空值',s:'决定等值/join/null 选择率',tone:'b'},
    {d:2,t:'count',s:'该列总行数(含 null)',tone:'e'},
    {d:2,t:'ndv(number of distinct)',s:'不同值个数;等值选择率≈1/ndv,join 基数估算核心',tone:'e'},
    {d:2,t:'numNulls',s:'null 行数;outer join 补 null 估算',tone:'e'},
    {d:1,t:'值域',s:'决定范围谓词选择率',tone:'b'},
    {d:2,t:'minValue / maxValue',s:'数值区间;范围谓词 [a,b] 选择率 = 交集占比;minExpr/maxExpr 保留原值',tone:'e'},
    {d:1,t:'宽度',s:'决定内存/shuffle 代价',tone:'b'},
    {d:2,t:'avgSizeByte / dataSize',s:'平均列宽 / 总字节',tone:'e'},
    {d:1,t:'热点值(倾斜修正)',s:'突破均匀分布假设',tone:'b'},
    {d:2,t:'hotValues: Map<Literal,Float>',s:'高频值→占比;等值命中热点值时用真实占比而非 1/ndv',tone:'e'},
    {d:1,t:'分区级统计',s:'partition_statistics 表;ndv 用 HLL 近似;分区裁剪后按分区累计',tone:'a'},
    {d:1,t:'持久化 & 读写',s:'column_statistics 列:id/catalog/db/tbl/idx/col/part/count/ndv/null_count/min/max/data_size/update_time/hot_value',tone:'a'},
    {d:2,t:'StatisticsRepository',s:'读 queryColumnStatisticsByName/ForTable;写 alterColumnStatistics;loadColStats 灌缓存',tone:'e'},
    {d:1,t:'→ 喂 CBO',s:'JoinEstimation:inner join 输出 ndv=min(l.ndv,r.ndv),行数=笛卡尔/max(ndv);统计缺失→回退默认选择率,估算失真',tone:'d'}
  ],
  threadtree:[
    {d:0,t:'BE 进程 · 全线程模型全景(≈840 线程)',s:'ExecEnv 启动期 _init 建各线程池;ThreadPoolBuilder 设 min/max_threads · max_queue_size · set_cgroup_cpu_ctl 绑资源组。★ thread pool 占 94%,是核心执行资源',tone:'root'},
    {d:1,t:'【查询执行层】thread pool(≈790,94%)',s:'查询执行 / 扫描 / 导入 / Agent 任务;790 = WorkloadGroup 池 ×N + 全局 TaskWorkerPool',tone:'a'},
    {d:2,t:'WorkloadGroup 线程池(每组独立)',s:'支持 CGroup CPU 隔离;线程绑定该组 CgroupCpuCtl,端到端 CPU 归属',tone:'a',k:'wgBe'},
    {d:3,t:'HybridTaskScheduler (p_<wg>)',s:'Pipeline Task 执行;blocking_thread_pool(HashJoin Build/Sort 阻塞算子)+ simple_thread_pool(Scan/Filter/Agg 非阻塞算子)',tone:'a',k:'thrHybrid'},
    {d:3,t:'ScannerScheduler (ls_<wg>)',s:'本地表 Scanner(OlapScan);与 Pipeline Task 解耦,经 ScannerContext._completed_tasks 队列;push_back_scan_task()→set_ready() 唤醒 Task',tone:'a',k:'thrScanPool'},
    {d:3,t:'RemoteScanScheduler (rs_<wg>)',s:'外表/远程 Scanner:Hive / Hudi / JDBC 等;远程 IO 密集,线程数远大于本地',tone:'a'},
    {d:2,t:'全局 TaskWorkerPool(Agent 任务)',s:'ThreadPoolBuilder 建;跨查询共享基础设施池',tone:'a'},
    {d:3,t:'DDL Agent 任务',s:'CREATE_TABLE / DROP_TABLE / ALTER_TABLE · PUBLISH_VERSION / CLEAR_TRANSACTION / CLEAR_ALTER_TASK · DOWNLOAD / UPLOAD / MAKE_SNAPSHOT / RELEASE_SNAPSHOT',tone:'a'},
    {d:3,t:'MemTableFlushThreadPool',s:'MemTable 刷盘(导入写入路径):DeltaWriter.write → MemTable → 生成 Rowset',tone:'a',k:'thrFlushPool'},
    {d:3,t:'SendBatchThreadPool',s:'Tablet Sink 批量发送;导入数据下发',tone:'a'},
    {d:1,t:'【Agent 任务执行层】PriorTaskWorkerPool(12)',s:'与 TaskWorkerPool 区别:有双队列优先级调度',tone:'d'},
    {d:2,t:'HighPrior (6)',s:'PUSH 高优先级(3) + CLONE 高优先级(3);PUSH=Broker/Spark Load 数据推送,CLONE=副本修复/均衡 Tablet 克隆',tone:'d'},
    {d:2,t:'Normal (6)',s:'PUSH 普通优先级(3) + CLONE 普通优先级(3)',tone:'d'},
    {d:1,t:'【存储引擎层】StorageEngine(13)',s:'Compaction / GC / 版本管理,独立于查询执行',tone:'b'},
    {d:2,t:'compaction_tasks_producer (1)',s:'Compaction 任务生产者(调度 Cumulative / Base Compaction)',tone:'b'},
    {d:2,t:'cold_data_compaction_producer (1)',s:'冷数据 Compaction 生产者',tone:'b'},
    {d:2,t:'cooldown_tasks_producer (1)',s:'数据冷却任务生产者(本地 → 对象存储)',tone:'b'},
    {d:2,t:'tablet_checkpoint_tasks_producer (1)',s:'Tablet Checkpoint 生产者',tone:'b'},
    {d:2,t:'async_publish (1)',s:'异步发布版本(Rowset 可见性提升)',tone:'b'},
    {d:2,t:'unused_rowset_monitor (1)',s:'清理未使用 Rowset(引用计数为 0)',tone:'b'},
    {d:2,t:'garbage_sweeper (1)',s:'清理过期数据文件(GC 孤立文件)',tone:'b'},
    {d:2,t:'disk_stat_monitor (1)',s:'监控磁盘 IO 状态',tone:'b'},
    {d:2,t:'cache_clean (1)',s:'清理过期 Tablet 元数据缓存',tone:'b'},
    {d:2,t:'update_replica_infos (1)',s:'更新副本信息(供 FE 调度决策)',tone:'b'},
    {d:2,t:'check_delete_bitmap_score (1)',s:'检查 Delete Bitmap 健康度(MoW 模型)',tone:'b'},
    {d:2,t:'path_gc_threads (2)',s:'清理孤立数据路径',tone:'b'},
    {d:1,t:'【系统维护层】Daemon(8)',s:'内存 / 缓存 / 指标维护',tone:'e'},
    {d:2,t:'tcmalloc_gc_thread (1)',s:'TCMalloc GC 触发(定期释放内存到 OS)',tone:'e'},
    {d:2,t:'memory_maintenance_thread (1)',s:'内存维护:刷新 MemTracker / 触发 GC / WorkloadGroup 内存管理',tone:'e'},
    {d:2,t:'memtable_memory_refresh_thread (1)',s:'MemTable 内存刷新(控制导入内存上限)',tone:'e'},
    {d:2,t:'calculate_metrics_thread (1)',s:'指标计算(CPU / 内存 / IO 等 Metrics)',tone:'e'},
    {d:2,t:'je_reset_dirty_decay_thread (1)',s:'JeMalloc dirty decay 重置',tone:'e'},
    {d:2,t:'cache_adjust_capacity_thread (1)',s:'缓存容量动态调整(按内存压力)',tone:'e'},
    {d:2,t:'cache_prune_stale_thread (1)',s:'缓存过期数据清理(LRU 淘汰)',tone:'e'},
    {d:2,t:'query_runtime_statistics_thread (1)',s:'查询运行时统计上报(Profile 汇聚)',tone:'e'},
    {d:1,t:'【FE 上报层】ReportWorker(5)',s:'定期上报 → FE',tone:'c'},
    {d:2,t:'REPORT_TASK (1)',s:'上报 Agent 任务执行状态(每 report_task_interval_seconds)',tone:'c'},
    {d:2,t:'REPORT_DISK_STATE (1)',s:'上报磁盘使用状态(每 report_disk_state_interval_seconds)',tone:'c'},
    {d:2,t:'REPORT_OLAP_TABLET (1)',s:'上报 Tablet 元数据(每 report_tablet_interval_seconds)',tone:'c'},
    {d:2,t:'REPORT_INDEX_POLICY (1)',s:'上报索引策略',tone:'c'},
    {d:2,t:'REPORT_WORKLOAD_GROUP (1)',s:'上报 WorkloadGroup 运行时状态',tone:'c'},
    {d:1,t:'【数据导入层】(4)',s:'Load 生命周期 / WAL',tone:'b'},
    {d:2,t:'LoadChannelMgr (1)',s:'清理超时 LoadChannel(Stream Load / Insert Into)',tone:'b',k:'loadChanMgr'},
    {d:2,t:'LoadPathMgr (1)',s:'清理过期导入临时路径(每 3600s)',tone:'b'},
    {d:2,t:'WalMgr (2)',s:'_update_wal_dirs_info_thread(更新 WAL 目录用量,背压控制)+ _replay_thread(BE 重启后扫描回放残留 WAL)',tone:'b'},
    {d:1,t:'【查询管理层】(3)',s:'超时取消 / 结果缓冲',tone:'c'},
    {d:2,t:'FragmentMgr (1)',s:'检测并取消超时 Fragment(query_timeout)',tone:'c',k:'fragMgr'},
    {d:2,t:'ResultBufferMgr (2)',s:'清理超时 ResultBlockBuffer(cancel_timeout_result)· Arrow Flight 结果管理',tone:'c'},
    {d:1,t:'【其他单线程】(5)',s:'各类管理 / GC',tone:'e'},
    {d:2,t:'BrokerMgr (1)',s:'管理 Broker 连接心跳',tone:'e'},
    {d:2,t:'ExternalScanContextMgr (1)',s:'GC 过期外部扫描上下文(JDBC / Spark Thrift)',tone:'e'},
    {d:2,t:'Spill (1)',s:'管理 Spill 临时文件生命周期(创建 / 清理)',tone:'e'},
    {d:2,t:'workload (1)',s:'WorkloadSchedPolicyMgr 调度策略评估(排队 / 取消 / 降级)',tone:'e',k:'wgMgrBe'},
    {d:2,t:'file-handle-cache (1)',s:'清理过期 HDFS 文件句柄(FileHandleCache LRU)',tone:'e'},
    {d:1,t:'★ 隐藏线程 · BlockFileCache 6×std::thread',s:'不在监控显示,实际进程线程数 > 840;monitor / gc / evict_in_advance / block_lru_update / lru_dump / lru_log_replay',tone:'d'}
  ],
  wgtree:[
    {d:0,t:'WorkloadGroup(资源组)',s:'多租户隔离单元;字段:_min/_max_cpu_percent · _memory_limit · _scan_thread_num · _total_query_slot_count',tone:'root'},
    {d:1,t:'CPU 隔离 → CgroupCpuCtl',s:'V1: cpu.shares(软)+ cpu.cfs_quota_us(硬);V2: cpu.weight + cpu.max',tone:'b'},
    {d:2,t:'/sys/fs/cgroup/{doris}/query/{wg_id}/',s:'每资源组一个 cgroup 目录;add_thread_to_cgroup 把执行/扫描线程写入 tasks/cgroup.procs',tone:'c'},
    {d:1,t:'内存隔离',s:'_memory_limit + _memory_low/high_watermark;超 high 触发组内查询 spill/cancel',tone:'b'},
    {d:1,t:'并发槽位 → query slot',s:'_total_query_slot_count 限制组内并发查询数;满则排队(admission control)',tone:'a'},
    {d:1,t:'IO 隔离',s:'_scan_bytes_per_second / _remote_scan_bytes_per_second 经 IOThrottle 限流(按 data_dir)',tone:'a'},
    {d:1,t:'组内专属线程池',s:'get_memtable_flush_pool 等按 wg 隔离,绑定该组 CgroupCpuCtl,实现端到端 CPU 归属',tone:'e'}
  ],
  cachetree:[
    {d:0,t:'BlockFileCache(本地磁盘缓存)',s:'存算分离下缓存远程对象存储数据;capacity 上限;后台 gc/ttl/evict/lru-dump 多线程维护',tone:'root',k:'fileCacheFactory'},
    {d:1,t:'远程文件 → hash(path) → UInt128',s:'每个远程文件按路径 hash 为 key;get_or_set(hash, offset, size) 命中或拉取',tone:'a'},
    {d:2,t:'split_range_into_cells 切块',s:'[offset, offset+size) 按块切成多个 FileBlock;单块上限 1GB,超大 reject',tone:'c'},
    {d:3,t:'FileBlock.State 状态机',s:'EMPTY → DOWNLOADING → DOWNLOADED;未缓存走 SKIP_CACHE;命中 DOWNLOADED 直接读本地',tone:'e'},
    {d:3,t:'FileBlockCell',s:'持 FileBlock + LRU queue_iterator + atime;releasable 判断能否驱逐(use_count)',tone:'e'},
    {d:1,t:'FileCacheType → 4 类独立 LRU 队列',s:'按数据热度/生命周期分队列,各自 LRU、互不挤占',tone:'b'},
    {d:2,t:'INDEX',s:'索引数据(short key/ZoneMap 等);命中率要求最高',tone:'a'},
    {d:2,t:'NORMAL',s:'普通列数据块;主力缓存',tone:'a'},
    {d:2,t:'TTL',s:'带过期时间;_key_to_time / _time_to_key 维护,后台 ttl_gc 清理',tone:'a'},
    {d:2,t:'DISPOSABLE',s:'一次性/低价值数据;最先被驱逐',tone:'a'},
    {d:1,t:'try_reserve 驱逐',s:'缓存满时按 LRU 驱逐 releasable 块腾空间;失败则本次 SKIP_CACHE 直读远程',tone:'d'}
  ],
  memotree:[
    {d:0,t:'Memo(Cascades 搜索空间)',s:'root Group + copyIn(plan) 去重入库;stateId 追踪变更;整个 CBO 在 Memo 上迭代',tone:'root',k:'optMemo'},
    {d:1,t:'Group(等价计划集合)',s:'一组逻辑等价的表达式;含 logicalProperties;lowestCostPlans: 每 PhysicalProperties → 最优 GroupExpression',tone:'b'},
    {d:2,t:'logicalExpressions[]',s:'该 Group 的逻辑算子(如 LogicalJoin);RBO 探索规则在此展开',tone:'a'},
    {d:2,t:'physicalExpressions[]',s:'物化后的物理算子(如 HashJoin/NestedLoopJoin)候选',tone:'a'},
    {d:2,t:'enforcers{}',s:'为满足所需属性插入的 enforcer(如 Distribution/Sort)',tone:'a'},
    {d:1,t:'GroupExpression(带算子的节点)',s:'plan + children(指向子 Group)+ ruleMasks(已应用规则位图)+ cost',tone:'c'},
    {d:2,t:'lowestCostTable',s:'outputProperties → (cost, 各子 Group 所需输入属性);CBO 自底向上填',tone:'e'},
    {d:1,t:'CostAndEnforcerJob',s:'枚举子 Group 输入属性组合 → 累加 cost → enforce 缺失属性 → recordPropertyAndCost 更新最优',tone:'d'},
    {d:1,t:'→ 抽出最优物理计划',s:'从 root Group 按 requiredProperties 取 lowestCostPlan,递归下钻子 Group 得完整物理树',tone:'d'}
  ],
  mvtree:[
    {d:0,t:'物化视图透明改写(Nereids)',s:'MTMV 异步刷新落表;查询命中时 CBO 阶段自动改写为读 MV,用户无感',tone:'root'},
    {d:1,t:'MTMV(物化视图表)',s:'querySql + refreshInfo(刷新策略)+ relation(依赖基表)+ MTMVCache(预解析计划)',tone:'a',k:'mvMtmv'},
    {d:1,t:'MaterializationContext',s:'每个可用 MV 一个上下文;缓存 MV 的 StructInfo,失败原因记录到此',tone:'b'},
    {d:2,t:'StructInfo(计划结构指纹)',s:'HyperGraph(join 图)+ SplitPredicate(等值/范围/残余)+ EquivalenceClass + relationIdStructInfoNodeMap',tone:'c'},
    {d:1,t:'AbstractMaterializedViewRule.rewrite',s:'遍历所有 MaterializationContext;耗时超阈值 makeFailWithDurationExceeded 兜底',tone:'d',k:'mvRewrite'},
    {d:2,t:'getValidQueryStructInfos',s:'把查询计划也抽成 StructInfo;为空则 bail out',tone:'e'},
    {d:2,t:'doRewrite → rewriteQueryByView',s:'MatchMode 匹配(complete/partial)+ SlotMapping 列映射;SPJG 场景由 AggregateRule 覆写补聚合上卷',tone:'e'},
    {d:1,t:'同步 MV(Rollup)',s:'区别于异步 MTMV:随基表实时预聚合,查询期由 SelectMaterializedIndex 选择最优 index',tone:'a'}
  ],
  anntree:[
    {d:0,t:'AI 检索索引(segment 级)',s:'向量 ANN + 全文倒排两类索引,建在列上,随 segment 持久化',tone:'root'},
    {d:1,t:'ANN 向量索引 → AnnIndexReader',s:'index_type + metric_type(L2/IP)+ dim;query(AnnTopNParam) / range_search',tone:'b'},
    {d:2,t:'FaissVectorIndex',s:'底层 faiss;build(FaissBuildParameter) → train(n,vec) → add(n,vec);受 ScopedOmpThreadBudget 限并发',tone:'c',k:'faissIndex'},
    {d:3,t:'HNSW',s:'图索引:高召回、低延迟;内存占用大',tone:'e'},
    {d:3,t:'IVF',s:'倒排量化:省内存、可训练聚类中心;召回可调',tone:'e'},
    {d:1,t:'全文倒排索引 → IndexSearcher',s:'variant<Fulltext, BKD>;match/match_phrase → Roaring bitmap 行号集',tone:'b'},
    {d:2,t:'FulltextIndexSearcher(CLucene)',s:'分词倒排;TermQuery/PhraseQuery;结果 InvertedIndexQueryCache 缓存 bitmap',tone:'c'},
    {d:2,t:'BKDIndexSearcher',s:'数值/范围列的 BKD 树;RangeQuery 高效裁剪',tone:'c'},
    {d:1,t:'AI 标量函数',s:'FE functions/ai/:LLM 调用、embedding 生成等作为标量表达式参与计划',tone:'a'},
    {d:1,t:'→ 与 TOPN 融合',s:'PushDownVectorTopNIntoOlapScan 把 order by distance limit k 下推;scan 侧 _apply_ann_topn_predicate 走索引',tone:'d'}
  ],
  pipetree:[
    {d:0,t:'PipelineFragmentContext',s:'一个 fragment 的执行上下文;_pipelines + _tasks(每 instance 一组 PipelineTask+RuntimeState)+ _total_tasks/_closed_tasks 计数',tone:'root',k:'plPipeCtx'},
    {d:1,t:'Pipeline(算子链模板)',s:'一串 OperatorX 的拓扑;fragment 按 shuffle 边界切成多条 Pipeline;每条实例化为 N 个 PipelineTask',tone:'a',k:'plPipeline'},
    {d:1,t:'PipelineTask(调度单元)',s:'_operators[](左=_source 右=_root)+ _sink;是 MultiCoreTaskQueue 的最小调度粒度',tone:'b',k:'plPipeTask'},
    {d:2,t:'_exec_state: atomic<State>',s:'状态机 INITED→RUNNABLE→BLOCKED→FINISHED→FINALIZED;_state_transition 受 LEGAL_STATE_TRANSITION 约束',tone:'c'},
    {d:2,t:'依赖集合(非阻塞核心)',s:'_read_dependencies[][] / _write_dependencies[] / _finish_dependencies[] / _execution_dependencies[];_blocked_dep 记当前阻塞源',tone:'e'},
    {d:2,t:'原子标志',s:'_running / _eos / _wake_up_early;blocked(dep) 挂起、wake_up(dep) 唤醒、_is_blocked() 判可运行',tone:'e'},
    {d:1,t:'Dependency(数据/资源就绪信号)',s:'_ready: atomic<bool>;block() 置未就绪、set_ready() 唤醒 _blocked_task;_always_ready 短路;BasicSharedState 共享上下游状态',tone:'b',k:'plDependency'},
    {d:2,t:'非阻塞调度语义',s:'算子缺数据/缺资源时不占线程,而是 block() 挂到 Dependency;上游 set_ready() 才把 task 重新入队——无忙等、无线程阻塞',tone:'e'},
    {d:1,t:'MultiCoreTaskQueue(每核队列)',s:'_prio_task_queues[_core_size](每核一个 PriorityTaskQueue);push_back 按 task.thread_id 或 _next_core 轮询',tone:'b',k:'plTaskQueue'},
    {d:2,t:'work-stealing',s:'take(core_id):先取本核 → 空则 _steal_take 遍历其余核 try_take(is_steal=true)偷任务 → 再空则本核带 WAIT_CORE_TASK_TIMEOUT_MS 等待',tone:'c'},
    {d:2,t:'PriorityTaskQueue(MLFQ)',s:'SubTaskQueue[SUB_QUEUE_LEVEL=6] 多级反馈队列;按 vruntime 累计执行时间调度,防长任务饿死短任务',tone:'e'},
    {d:1,t:'pull-based 执行',s:'OperatorXBase.get_block(state,block,eos) 自顶向下拉;need_more_input_data 控制向下要数据;Stateful/Streaming 算子覆写 pull()/push();DataSinkOperatorX.sink() 落地',tone:'d'}
  ],
  jemalloctree:[
    {d:0,t:'BE 进程内存全景',s:'一个 BE 进程内同住 C++ 堆(jemalloc) + 内嵌 JVM 堆 + OS 视角 RSS,三者边界与追踪各不同',tone:'root'},
    {d:1,t:'① jemalloc(C++ 主分配器)',s:'jemalloc_hook.cpp:doris_malloc/free 经 ALIAS 劫持全局 malloc/free;所有 C++ 分配走 jemalloc',tone:'b'},
    {d:2,t:'MemTracker 计量',s:'不在 jemalloc hook 里,而在 thread_context.h + thread_mem_tracker_mgr:每线程 _untracked_mem 批量攒够 min_size 再 flush 进 MemTrackerLimiter',tone:'c',k:'memThreadMgr'},
    {d:2,t:'tcache(线程缓存)',s:'JemallocControl::je_thread_tcache_flush;当 je_tcache_mem()>1G 时 mallctl(thread.tcache.flush);指标 stats.arenas.<ALL>.tcache_bytes',tone:'e'},
    {d:2,t:'脏页归还 OS',s:'je_purge_all_arena_dirty_pages → mallctl(arena.<ALL>.purge);je_dirty_decay_ms / enable_je_purge_dirty_pages 控制;daemon 在超 soft_mem_limit 时触发 je_reset_dirty_decay',tone:'e',k:'memReclaim'},
    {d:1,t:'② 内嵌 JVM(JNI)',s:'JniUtil::FindOrCreateJavaVM 用 JAVA_OPTS/LIBHDFS_OPTS 建 JVM;跑 Java scanner(Hive/Iceberg)、broker、jdbc catalog、Java UDF',tone:'a'},
    {d:2,t:'JVM 堆上限',s:'从 LIBHDFS_OPTS 的 -Xmx 解析(parse_max_heap_memory_size_from_jvm),存 max_jvm_heap_memory_size_;非 BE config——由 JVM 参数定',tone:'e'},
    {d:2,t:'坑:JVM 堆不计入 process_memory_limit',s:'GlobalMemoryArbitrator/MemInfo 不为 JVM 预留、不扣除;JVM 堆只被 hdfs_file_writer 按 max_hdfs_writer_jni_heap_usage_ratio 消费',tone:'c'},
    {d:1,t:'③ JNI 内存追踪(仅观测)',s:'JVM 内存不受 MemTrackerLimiter 限流;只作为指标:jvm_metrics(JvmStats)经 JniUtil.getJvmMemoryMetrics 采集',tone:'a'},
    {d:2,t:'memory_profile 汇总',s:'memory_profile.cpp 把 jvm_heap_bytes + jvm_non_heap_bytes(committed)计入 all_tracked_mem_sum 与 _jvm_*_memory_usage_counter——仅 profile 可观测,不限流',tone:'e'},
    {d:1,t:'专家提示',s:'排查 BE OOM 要区分:MemTracker 显示的是 jemalloc 侧;若 tracker 总和远小于进程 RSS,差额多半是 JVM 堆 + jemalloc 未 purge 的脏页 + tcache——JVM 堆需另看 jvm_metrics。',tone:'d'}
  ],
  mvspjg:[
    {d:0,t:'SPJG 透明改写算法原理',s:'Nereids 判断查询能否用 MV 等价改写:把查询与 MV 都抽成 StructInfo,逐维度检查"查询 ⊆ MV",再补偿差异',tone:'root'},
    {d:1,t:'① 结构抽取 StructInfo',s:'查询与 MV 各建一个 StructInfo(HyperGraph join 图 + Predicates + EquivalenceClass);改写在结构指纹上比对,而非文本',tone:'b'},
    {d:2,t:'S = Selection 匹配',s:'查询谓词范围必须 ⊆ MV 谓词范围;SplitPredicate 拆成 equal/range/residual 三类分别比对',tone:'a'},
    {d:3,t:'谓词补偿 compensate',s:'查询比 MV 多的残余谓词,改写后在 MV 结果上追加过滤(rewriteExpression)',tone:'e'},
    {d:2,t:'P = Projection 匹配',s:'查询所需列必须 ⊆ MV 输出列;SlotMapping 建立查询列↔MV 列映射',tone:'a'},
    {d:3,t:'表达式二次派生',s:'MV 没直接输出但可由 MV 列算出的表达式,改写后在 MV 上二次计算',tone:'e'},
    {d:2,t:'J = Join 匹配',s:'HyperGraph 比对:查询 join 的表集 ⊆ MV 表集,且等价类一致;外连接/join 顺序敏感更严',tone:'a'},
    {d:2,t:'G = Grouping 匹配',s:'查询 group by ⊆ MV group by 时可上卷;否则需 MV 保留明细',tone:'b'},
    {d:3,t:'聚合上卷 rollup',s:'AggregateRule 在 MV 预聚合结果上补二次聚合(SUM 的 SUM、COUNT 的 SUM),得查询粒度',tone:'e'},
    {d:1,t:'② MatchMode 判定',s:'decideMatchMode:COMPLETE(表集完全一致)/ VIEW_PARTIAL / QUERY_PARTIAL;决定能否改写及补偿方式',tone:'d'},
    {d:1,t:'③ 生成改写 Plan',s:'rewriteQueryByView 产出以 MV 为源的等价 Plan,交回 CBO 与原计划按代价竞争(未必采用)',tone:'d'}
  ],
  mvscene:[
    {d:0,t:'MV 适用性判断(什么时候值得建)',s:'MV 用空间/刷新代价换查询提速;是否划算取决于查询模式与基表写频',tone:'root'},
    {d:1,t:'✓ 适用场景',s:'值得建 MV 的典型情况',tone:'b'},
    {d:2,t:'固定维度高频聚合报表',s:'如按天/地区的 sum/count 大盘,每次全表聚合太贵 → MV 预聚合命中即毫秒返回',tone:'e'},
    {d:2,t:'多表 join 后聚合',s:'星型模型事实表 join 维表再聚合,MV 固化 join+聚合结果,省掉重复 join',tone:'e'},
    {d:2,t:'查询 group by 是 MV 的上卷',s:'MV 按 (region,city) 预聚合,查询按 region 聚合 → 直接在 MV 上卷,无需回明细',tone:'e'},
    {d:2,t:'过滤范围是 MV 子集',s:'MV 覆盖近 30 天,查询近 7 天 → 谓词补偿即可命中',tone:'e'},
    {d:1,t:'✗ 不值得场景',s:'建 MV 反而亏的情况',tone:'c'},
    {d:2,t:'非 SPJG 查询',s:'窗口函数/CTE 递归/复杂子查询不在改写范围,建了也命不中',tone:'a'},
    {d:2,t:'MV 未覆盖的 join/列',s:'查询用到 MV 没有的表或列,无法改写',tone:'a'},
    {d:2,t:'基表高频写',s:'基表频繁变更 → MV 频繁失效/刷新,刷新代价 > 查询收益',tone:'a'},
    {d:2,t:'点查/无聚合收益',s:'主键点查本就快,MV 的预聚合价值为零',tone:'a'},
    {d:1,t:'代价护栏(引擎自保)',s:'改写超 materializedViewRewriteDurationThresholdMs 即 makeFailWithDurationExceeded 放弃;候选数受 getMaterializedViewRewriteSuccessCandidateNum 限',tone:'d'}
  ],
  profilediag:[
    {d:0,t:'用 Profile 定位瓶颈(实战方法)',s:'先看 MergedProfile 的 min/avg/max 找异常算子,再进 DetailProfile 定位具体 BE/instance',tone:'root'},
    {d:1,t:'① 先看总耗时构成',s:'ExecutionSummary 的 Planner 各阶段耗时 vs 执行耗时;Planner 慢查改写/统计,执行慢往下钻',tone:'a'},
    {d:1,t:'② 找最耗时算子',s:'MergedProfile 各算子 ExecTime(不含上游)排序;ExecTime 最大的算子即热点',tone:'b'},
    {d:2,t:'算子 ExecTime 高',s:'看该算子类型:HASH_JOIN 看 ProbeRows/BuildRows 是否巨大;AGGREGATION 看 HashTable 大小;SCAN 看 RowsProduced',tone:'c'},
    {d:2,t:'WaitForDependency 高',s:'算子在等上游/资源就绪(非自身慢);顺依赖链上溯找真正的慢源,而非优化本算子',tone:'e'},
    {d:1,t:'③ 判断数据倾斜',s:'MergedProfile 同一算子的 min/avg/max 差距大 → instance 间负载不均',tone:'b'},
    {d:2,t:'对比 InputRows',s:'某 instance 的 InputRows 远高于 avg → shuffle key 倾斜;考虑加盐/改分布键/开 skew join',tone:'e'},
    {d:2,t:'进 DetailProfile 定位',s:'确认倾斜后按 BE×instance 展开,找到具体哪个 BE 的哪个 PipelineTask 慢',tone:'c'},
    {d:1,t:'④ 判断内存压力',s:'HASH_JOIN_SINK 的 MemoryUsageHashTable、AGGREGATION_SINK 的 MemoryUsageSerializeKeyArena 过高',tone:'b'},
    {d:2,t:'是否触发 spill',s:'内存超 workload group 上限会 spill 落盘;profile 里 spill 相关计数器非 0 即发生,IO 拖慢',tone:'e'},
    {d:1,t:'⑤ 判断 IO/交换瓶颈',s:'EXCHANGE 的 Remote/LocalBytesReceived + DecompressTime;DATA_STREAM_SINK 的 WaitForRpcBufferQueue',tone:'b'},
    {d:2,t:'扫描慢',s:'OLAP_SCAN 的 RowsProduced 大但谓词该裁未裁 → 检查 zonemap/短键索引/RF 是否生效(对照 RuntimeFilter 主题)',tone:'e'},
    {d:1,t:'⑥ profile_level 取舍',s:'level 1 只留关键计数器(生产默认);level 2/3 展开全部(RRCU prune_the_tree 按 level 剪枝),排障时才开高 level',tone:'d'}
  ],
  compacttree:[
    {d:0,t:'Compaction 数据结构',s:'LSM 后台把小 rowset 合并成大 rowset,降读放大;版本连续性由 version graph 保证',tone:'root'},
    {d:1,t:'Version {first, second}',s:'olap_common.h:227;rowset 的版本区间 [start,end] 闭区间;contains 判包含',tone:'a'},
    {d:1,t:'cumulative point',s:'TabletMeta._cumulative_layer_point;point 前=已 base 合并的稳定区,point 后=可 cumulative 合并的增量区',tone:'b'},
    {d:2,t:'cumulative compaction',s:'合并 point 之后的小增量 rowset;高频、低成本',tone:'e'},
    {d:2,t:'base compaction',s:'把 cumulative 结果并入 base(point 前);低频、成本高',tone:'e'},
    {d:1,t:'SizeBasedCumulativeCompactionPolicy',s:'cumulative_compaction_policy.h:113;按 size 累加 compaction_score 挑候选,超阈值从尾裁',tone:'b'},
    {d:2,t:'promotion 阈值',s:'compaction_promotion_size_mbytes=1024 / ratio=0.05;增量攒够才晋升 base',tone:'e'},
    {d:1,t:'MoW delete bitmap 合并',s:'compaction 时 rowid 转换 + calc_compaction_output_rowset_delete_bitmap 重算新 rowset 的删除位图',tone:'c'},
    {d:1,t:'_unused_rowsets(GC)',s:'storage_engine.h:486;老 rowset 转 stale 入此 map,由 start_delete_unused_rowset 后台回收',tone:'d'}
  ],
  txntree:[
    {d:0,t:'事务与 MVCC 版本模型',s:'Doris 多版本并发:每次导入生成新 version 的 rowset,读时按 version 快照选可见集,写读互不阻塞',tone:'root'},
    {d:1,t:'RowsetMeta.version',s:'rowset_meta.h:129;每 rowset 带 [start,end] 版本;导入生成新版本,不改旧数据',tone:'a'},
    {d:1,t:'两阶段事务(FE+BE)',s:'FE DatabaseTransactionMgr 协调;BE TxnManager: prepare_txn→commit_txn→publish_txn',tone:'b'},
    {d:2,t:'prepare(登记事务槽)',s:'txn_manager.cpp:93;占位,数据还不可见',tone:'e'},
    {d:2,t:'commit(落 rowset meta)',s:'txn_manager.cpp:191;rowset 已写但未定版本、不可见',tone:'e'},
    {d:2,t:'publish(定版本生效)',s:'txn_manager.cpp:459;EnginePublishVersionTask 给 rowset 定 version→add_inc_rowset 生效',tone:'e'},
    {d:1,t:'VersionGraph(版本 DAG)',s:'version_graph.h;顶点=version 端点,边=rowset;区间最短路径 = 读时可见 rowset 集',tone:'b'},
    {d:2,t:'capture_rs_readers',s:'tablet.cpp:963;读时按请求 version 从 _rs_version_map 选一致 rowset 建 reader',tone:'c'},
    {d:1,t:'MoW 版本可见性',s:'delete bitmap 按 version 生效;读高版本时旧版本被 bitmap 标删,实现主键最新值语义',tone:'d'}
  ],
  metatree:[
    {d:0,t:'FE 元数据持久化 & 高可用模型',s:'FE 元数据 = 内存对象 + BDB-JE 复制日志。先写日志再改内存;崩溃靠重放日志追平,选主靠 BDB-JE Election',tone:'root'},
    {d:1,t:'EditLog(变更日志)',s:'persist/EditLog.java:127;所有 DDL/事务状态以 (op,Writable) 落 journal',tone:'a'},
    {d:2,t:'logEditDirectly / WithQueue',s:':1555 / :1523;同步直写 vs 异步批量入队 logEditQueue',tone:'e'},
    {d:2,t:'loadJournal(重放分派)',s:':291;按 OperationType 的大 switch 把日志还原成内存对象',tone:'e'},
    {d:1,t:'BDBJEJournal(复制状态机)',s:'journal/bdbje/BDBJEJournal.java:73;implements Journal',tone:'b'},
    {d:2,t:'write 分配 journalId',s:':230;nextJournalId 单调递增;put currentJournalDB→多数派复制到 FOLLOWER',tone:'c'},
    {d:1,t:'FrontendNodeType 角色',s:'Env.java:421;MASTER/FOLLOWER/OBSERVER;isMaster()==feType==MASTER',tone:'b'},
    {d:2,t:'transferToMaster',s:':1636;选主后停 replayer→replayJournal(-1) 追平→对外写',tone:'e'},
    {d:2,t:'replayer + canRead',s:':2876 / :415;Follower 守护线程重放;元数据延迟过大置 canRead=false 拒陈旧读',tone:'e'},
    {d:1,t:'Checkpoint(镜像压缩)',s:'master/Checkpoint.java:53;extends MasterDaemon',tone:'b'},
    {d:2,t:'doCheckpoint',s:':90;loadImage→replay(ckptVer)→saveImage→deleteJournals;MetaHelper 分发 image',tone:'c'}
  ],
  tablettree:[
    {d:0,t:'副本调度与修复模型',s:'Doris 集群自愈:Checker 发现问题→Scheduler 优先级排队→Clone 修复/Rebalancer 均衡。修复永远优先于均衡',tone:'root'},
    {d:1,t:'TabletStatus(12 态健康)',s:'Tablet.java:62;HEALTHY/REPLICA_MISSING/VERSION_INCOMPLETE/REDUNDANT/COLOCATE_MISMATCH…',tone:'a'},
    {d:2,t:'getHealth / getColocateHealth',s:':542 / :766;算 TabletHealth(status+priority);colocate 表走变体',tone:'e'},
    {d:1,t:'TabletChecker(巡检)',s:'clone/TabletChecker.java:66;extends MasterDaemon',tone:'b'},
    {d:2,t:'checkTablets',s:':236;遍历 db/table/partition;prio(用户指定)与 normal 两路入队',tone:'e'},
    {d:1,t:'TabletScheduler(调度)',s:'clone/TabletScheduler.java:103;pendingTablets(MinMaxPriorityQueue)+runningTablets(Map)',tone:'b'},
    {d:2,t:'schedulePendingTablets',s:':353;主循环:updateLoadStatistics→handleRunning→balance→schedulePending',tone:'c'},
    {d:2,t:'handleTabletByTypeAndStatus',s:':685;按状态分派 handleReplicaMissing/VersionIncomplete/Redundant/ColocateMismatch',tone:'e'},
    {d:1,t:'修复与均衡通道',s:'共用 clone 通道,优先级不同',tone:'b'},
    {d:2,t:'CloneTask.toThrift',s:'task/CloneTask.java:82;TCloneReq(tabletId,schemaHash,srcBackends)→BE 拉源副本 rowset',tone:'d'},
    {d:2,t:'Rebalancer',s:'clone/Rebalancer.java:59;BeLoadRebalancer(跨 BE)/DiskRebalancer(BE 内磁盘);优先级低于修复',tone:'d'}
  ],
  sctree:[
    {d:0,t:'Schema Change(在线变更)模型',s:'加影子索引 + 事务水位双写实现在线变更:老查询走原索引,新写双写影子,BE 转历史数据,完成后原子切换',tone:'root'},
    {d:1,t:'变更分类',s:'SchemaChangeHandler.java:1924;process 分 light(仅元数据)/heavy(需转数据)',tone:'a'},
    {d:2,t:'light 变更',s:'加列/删列/改注释;秒级完成,无需 BE 转换',tone:'e'},
    {d:2,t:'heavy 变更',s:'改类型/改排序键/改分桶;走 SchemaChangeJobV2 重型双写转换',tone:'e'},
    {d:1,t:'影子索引(SHADOW)',s:'MaterializedIndex.java:40;IndexState.SHADOW:对 load 可见、对 query 不可见',tone:'b'},
    {d:2,t:'createJob 建影子',s:'SchemaChangeHandler.java:1278;分配 shadowIndexId+影子 tablet/replica;addTabletIdMap 映射影子→原始',tone:'c'},
    {d:1,t:'状态机(SchemaChangeJobV2)',s:'alter/SchemaChangeJobV2.java:100;PENDING→WAITING_TXN→RUNNING→FINISHED',tone:'b'},
    {d:2,t:'watershedTxnId(双写水位)',s:':423;水位后的新事务已双写影子;只需转换水位前的历史 rowset',tone:'e'},
    {d:2,t:'onFinished 原子切换',s:':729;影子索引替换原始;切换前查旧 schema,切换后查新 schema',tone:'e'},
    {d:1,t:'BE 转换器族',s:'olap/schema_change.cpp:556',tone:'b'},
    {d:2,t:'Linked / Directly / Sorting',s:'Linked(仅硬链)/VSchemaChangeDirectly(逐块直转)/WithSorting(改排序键需内外部排序)',tone:'d'}
  ],
  vectree:[
    {d:0,t:'向量化列式内存模型',s:'Doris 执行引擎全列式:一批行按列组织成 Block,算子/表达式对整列批量运算,SIMD + cache 友好',tone:'root',k:'vecBlock'},
    {d:1,t:'Block(列式容器)',s:'core/block.h:71;一批数据 = ColumnsWithTypeAndName(列名+类型+ColumnPtr)',tone:'a',k:'vecBlock'},
    {d:2,t:'get_by_position / insert',s:'block.h:129/:96;按位置取列 / 追加列;算子间传递的就是 Block',tone:'e'},
    {d:1,t:'Column 家族(列实现)',s:'按类型分化,统一 IColumn 接口',tone:'b'},
    {d:2,t:'ColumnVector<T>',s:'column_vector.h:71;定宽(int/float),PaddedPODArray<T> 连续存',tone:'e',k:'vecColumn'},
    {d:2,t:'ColumnString',s:'=ColumnStr<UInt32>;变长:offsets[] + chars[] 两数组',tone:'e'},
    {d:2,t:'ColumnNullable',s:'column_nullable.h:55;null_map(UInt8[]) + nested 列组合',tone:'e'},
    {d:1,t:'PaddedPODArray(底层存储)',s:'pod_array.h:307;连续内存 + 尾部 padding,让 SIMD 越界读安全',tone:'c',k:'vecPod'},
    {d:1,t:'IColumn::Filter / Selector',s:'column.h:422/:495;Filter=UInt8 选择向量(0/1),Selector=行号数组;批量裁行/选行',tone:'d'}
  ],
  rbotree:[
    {d:0,t:'RBO 规则改写(Rewriter 阶段)',s:'启发式规则、无代价、迭代到不动点;AbstractBatchJobExecutor 循环直到 !isRewritten',tone:'root'},
    {d:1,t:'谓词类',s:'把过滤尽早下推、推导新谓词,减少上游数据量',tone:'b'},
    {d:2,t:'PushDownFilterThroughProject',s:'谓词穿过 Project 下推到更靠近扫描处',tone:'e'},
    {d:2,t:'InferPredicates',s:'由等值/连接条件推导新谓词(如 a=b∧b=5⇒a=5)',tone:'e'},
    {d:1,t:'裁剪类',s:'去掉不需要的列与算子',tone:'b'},
    {d:2,t:'ColumnPruning',s:'列裁剪,只保留被引用列(RuleType.COLUMN_PRUNING)',tone:'e'},
    {d:2,t:'EliminateOuterJoin / EliminateLimit',s:'not-null 谓词化简外连接;消冗余 Limit',tone:'e'},
    {d:1,t:'下推类',s:'算子穿过 Join/聚合下推,减少中间结果',tone:'b'},
    {d:2,t:'PushDownAggThroughJoin',s:'聚合下推穿过 Join',tone:'e'},
    {d:2,t:'PushDownTopNThroughJoin / PushDownLimit',s:'TopN/Limit 下推减少上游行数',tone:'e'},
    {d:1,t:'重排/合并类',s:'调整算子结构',tone:'b'},
    {d:2,t:'ReorderJoin',s:'启发式 Join 顺序重排(非代价)',tone:'e'},
    {d:2,t:'MergeFilters / MergeProjects',s:'合并相邻 Filter/Project',tone:'e'}
  ],
  cbotree:[
    {d:0,t:'CBO 代价优化(Optimizer/Memo)',s:'基于统计+代价模型,在 Memo 记忆化搜索空间里枚举等价计划,选最低代价',tone:'root'},
    {d:1,t:'Memo(搜索空间)',s:'toMemo 建;等价计划去重入 Group,避免重复枚举',tone:'b',k:'optMemo'},
    {d:2,t:'Group / GroupExpression',s:'Group=一组逻辑等价表达式;GroupExpression=带算子的节点',tone:'e'},
    {d:1,t:'DeriveStatsJob(统计派生)',s:'自底向上算每 Group 的行数/列统计;默认 StatsCalculator',tone:'b'},
    {d:2,t:'输入 ColumnStatistic',s:'ndv/min/max/hotValues 决定选择率(见统计信息主题)',tone:'e'},
    {d:1,t:'CostAndEnforcerJob(代价+属性)',s:'CostCalculator 算代价;缺分布/顺序属性时插 enforcer(shuffle/sort)',tone:'b'},
    {d:2,t:'CostModel',s:'CPU/内存/网络加权;addChildCost 累加子代价',tone:'e'},
    {d:1,t:'lowestCostTable',s:'每 Group 保存 满足某属性的最优 GroupExpression + 代价',tone:'d'},
    {d:1,t:'Join Reorder(DPhyp)',s:'jobs/executor/Optimizer.java:100;dpHypOptimize 据 isDpHyp/disableJoinReorder 决定重排',tone:'b',k:'joDpHyp'},
    {d:2,t:'JoinOrderJob → HyperGraph',s:'joinorder/JoinOrderJob.java:75;builderForDPhyper 建超图,枚举 CSG/CMP 连通子图对',tone:'c',k:'joJob'},
    {d:2,t:'PlanReceiver 代价择优',s:'hypergraph/receiver/PlanReceiver.java:94;每对 join copyIn Memo 算代价,getBestPlan 取最低',tone:'e',k:'joReceiver'},
    {d:2,t:'GraphSimplifier 兜底',s:'hypergraph/GraphSimplifier.java:168;超预算(dphyperLimit)时贪心简化图后重试,牺牲最优换可解',tone:'e',k:'joSimplify'},
    {d:2,t:'bushy vs 左深',s:'DPhyp 支持 bushy tree(比左深更优);表数超 MAX_JOIN_NUMBER_BUSHY_TREE 退化防爆炸',tone:'d'},
    {d:1,t:'→ 抽最优物理计划',s:'从 root Group 按 requiredProperties 递归取 lowestCost 得完整物理树',tone:'d'}
  ],
  hbotree:[
    {d:0,t:'HBO 历史优化(History-Based)',s:'用历史执行的真实行数反馈,修正 CBO 的估算偏差;sessionVariable.enableHboOptimization 开关',tone:'root'},
    {d:1,t:'介入点:DeriveStatsJob',s:'开启后用 HboStatsCalculator 替代普通 StatsCalculator:110',tone:'b'},
    {d:2,t:'getStatsFromHboPlanStats',s:'HboStatsCalculator:94;对 scan/join/agg 取历史计划统计',tone:'e'},
    {d:2,t:'PlanNodeHash 匹配',s:'HboUtils.getPlanNodeHash 算计划节点哈希,匹配 RecentRunsPlanStatistics',tone:'e'},
    {d:1,t:'历史反馈来源',s:'执行后 collectHboPlanInfo:553 写回真实行数',tone:'b'},
    {d:2,t:'HboPlanStatisticsManager',s:'存历史计划统计;PlanStatisticsMatchStrategy 匹配策略',tone:'e'},
    {d:1,t:'代价侧',s:'CostModel:487 也判 isEnableHboOptimization 修正代价',tone:'d'},
    {d:1,t:'价值',s:'解决 CBO"估算偏差"痛点:重复查询用上次真实行数,估得更准→选更优计划',tone:'d'}
  ]
};
const TREE_TONE={root:'#8fb0e8',a:'#5db0f0',b:'#6fb87d',c:'#d0b06a',d:'#b18cf0',e:'#a6adbb'};
const TREE_BG  ={root:'#0e1626',a:'#0d1a26',b:'#0e1a14',c:'#1a1710',d:'#150e22',e:'#12151c'};

/* 嵌套容器结构图(替代缩进树):父节点为容器,子节点作为卡片嵌入其中,
   用"块中块"的包含关系表达层级 —— 专业架构图风,非树状连线。 */
/* ClickHouse 文档式 schema 表:统一列宽表格,标题行 + 分组色带 + 字段行(名称|说明),
   行等高、左对齐、交替底色、细分隔线 —— 整齐紧凑,非嵌套框。 */
function renderTreeSVG(out, tid){
  const spec=TREE_SPECS[tid]; if(!spec){out.innerHTML='<div class="empty"><div class="big">▤</div><div>暂无内容</div></div>';return;}
  const NS='http://www.w3.org/2000/svg';
  const parent=spec.map((n,i)=>{ if(n.d===0)return -1; for(let j=i-1;j>=0;j--){ if(spec[j].d<n.d) return j; } return -1; });
  const kids=spec.map(()=>[]); parent.forEach((p,i)=>{ if(p>=0)kids[p].push(i); });
  // 布局:固定表宽,两列(名称 / 说明),行等高;根=标题条,d=1=分组带,d≥2=字段行
  const LEFT=30, NAMEW=356, DESCW=576, PAD=16;
  const W=LEFT*2+NAMEW+DESCW, TITLEH=46, GROUPH=34, ROWH=42;
  // 预算总高
  let H=20;
  spec.forEach(n=>{ H += (n.d===0?TITLEH:(n.d===1?GROUPH:ROWH)); if(n.d===0)H+=4; });
  H+=14;
  let svg='<svg id="svg-'+tid+'" class="tblsvg" viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" preserveAspectRatio="xMidYMin meet" style="width:100%;max-width:'+W+'px;height:auto;display:block;margin:0 auto" xmlns="'+NS+'">';
  // 外框
  svg+='<rect x="'+(LEFT-1)+'" y="14" width="'+(NAMEW+DESCW+2)+'" height="'+(H-20)+'" rx="10" fill="var(--cv-card)" stroke="var(--cv-border)" stroke-width="1"/>';
  let y=16, fieldIdx=0, curGroupTone='#5db0f0';
  spec.forEach((n,i)=>{
    const tone=TREE_TONE[n.tone]||'#a6adbb';
    const x=LEFT;
    if(n.d===0){
      // 标题条
      svg+='<g class="tnode" data-idx="'+i+'">';
      svg+='<rect x="'+x+'" y="'+y+'" width="'+(NAMEW+DESCW)+'" height="'+TITLEH+'" rx="10" fill="'+tone+'1c"/>';
      svg+='<rect x="'+x+'" y="'+y+'" width="4" height="'+TITLEH+'" rx="2" fill="'+tone+'"/>';
      svg+='<text x="'+(x+18)+'" y="'+(y+19)+'" fill="var(--cv-ink)" font-size="15" font-weight="700" font-family="var(--sans)">'+n.t+'</text>';
      svg+='<foreignObject x="'+(x+18)+'" y="'+(y+24)+'" width="'+(NAMEW+DESCW-36)+'" height="20"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:11px;line-height:1.25;color:#8b93a3;font-family:var(--sans);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+n.s+'</div></foreignObject>';
      svg+='</g>';
      y+=TITLEH+4; fieldIdx=0;
    } else if(n.d===1){
      // 分组色带
      curGroupTone=tone;
      svg+='<g class="tnode" data-idx="'+i+'">';
      svg+='<rect x="'+x+'" y="'+y+'" width="'+(NAMEW+DESCW)+'" height="'+GROUPH+'" fill="'+tone+'14"/>';
      svg+='<rect x="'+x+'" y="'+y+'" width="3" height="'+GROUPH+'" fill="'+tone+'"/>';
      svg+='<circle cx="'+(x+16)+'" cy="'+(y+GROUPH/2)+'" r="3" fill="'+tone+'"/>';
      svg+='<text x="'+(x+28)+'" y="'+(y+GROUPH/2+4)+'" fill="'+tone+'" font-size="12.5" font-weight="700" font-family="var(--sans)">'+n.t+'</text>';
      svg+='<foreignObject x="'+(x+NAMEW)+'" y="'+(y+6)+'" width="'+(DESCW-16)+'" height="'+(GROUPH-8)+'"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:10.5px;line-height:1.35;color:#8b93a3;font-family:var(--mono);display:flex;align-items:center;height:100%">'+n.s+'</div></foreignObject>';
      svg+='</g>';
      y+=GROUPH; fieldIdx=0;
    } else {
      // 字段行(交替底色)
      const zebra=(fieldIdx%2===0)?'var(--cv-card)':'var(--cv-card-alt)';
      svg+='<g class="tnode" data-idx="'+i+'">';
      svg+='<rect class="trow" x="'+x+'" y="'+y+'" width="'+(NAMEW+DESCW)+'" height="'+ROWH+'" fill="'+zebra+'"/>';
      svg+='<line x1="'+(x+NAMEW)+'" y1="'+(y+5)+'" x2="'+(x+NAMEW)+'" y2="'+(y+ROWH-5)+'" stroke="var(--cv-border)" stroke-width="1"/>';
      const ind=x+24+(n.d-2)*16;
      svg+='<rect x="'+(x+12)+'" y="'+(y+ROWH/2-7)+'" width="3" height="14" rx="1.5" fill="'+curGroupTone+'99"/>';
      svg+='<text x="'+ind+'" y="'+(y+ROWH/2+4)+'" fill="var(--cv-ink)" font-size="12.5" font-weight="600" font-family="var(--mono)">'+n.t+'</text>';
      svg+='<foreignObject x="'+(x+NAMEW+14)+'" y="'+(y+4)+'" width="'+(DESCW-28)+'" height="'+(ROWH-6)+'"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:11px;line-height:1.3;color:var(--cv-ink2);font-family:var(--mono);display:flex;align-items:center;height:100%">'+n.s+'</div></foreignObject>';
      svg+='</g>';
      y+=ROWH; fieldIdx++;
    }
  });
  svg+='</svg>';
  out.innerHTML=svg;
  const gs=[...out.querySelectorAll('g.tnode')];
  gs.forEach(g=>{
    g.addEventListener('mouseenter',ev=>{ ev.stopPropagation(); g.classList.add('thot'); });
    g.addEventListener('mouseleave',ev=>{ ev.stopPropagation(); g.classList.remove('thot'); });
  });
}

function wireNodes(tid,out){
  // 源码下钻已移除:节点不再可点击;仅保留边序号徽标。
  numberEdges(out);
}

/* 给每条边中点放一个序号徽标(近似拓扑执行序),让流程方向一目了然 */
function numberEdges(out){
  const svg=out.querySelector('svg'); if(!svg) return;
  const paths=[...out.querySelectorAll('.edgePaths path, path.flowchart-link, .edgePath path, line.tour-flowline')];
  if(!paths.length) return;
  const NS='http://www.w3.org/2000/svg';
  let g=svg.querySelector('.edge-seq-layer');
  if(g) g.remove();
  g=document.createElementNS(NS,'g'); g.setAttribute('class','edge-seq-layer');
  svg.appendChild(g);
  // 按边的"起点位置"近似拓扑序: 流程图自上而下(TB)/自左而右, 用起点 (y,x) 排序,比 DOM 顺序更贴合执行顺序
  const items=paths.map(p=>{
    let mid,start;
    try{const L=p.getTotalLength(); mid=p.getPointAtLength(L*0.5); start=p.getPointAtLength(0);}
    catch(e){return null;}
    return {p,mid,start};
  }).filter(Boolean);
  items.sort((a,b)=> (a.start.y-b.start.y) || (a.start.x-b.start.x));
  items.forEach((it,i)=>{
    const grp=document.createElementNS(NS,'g'); grp.setAttribute('class','edge-seq');
    grp.setAttribute('transform','translate('+it.mid.x+','+it.mid.y+')');
    const c=document.createElementNS(NS,'circle'); c.setAttribute('r','9');
    const t=document.createElementNS(NS,'text'); t.setAttribute('text-anchor','middle');
    t.setAttribute('dy','3.5'); t.textContent=(i+1);
    grp.appendChild(c); grp.appendChild(t); g.appendChild(grp);
  });
}

async function openInTab(tab,key){
  // 源码下钻已移除;此函数仅用于跨视图/嵌套子视图的 tab 切换(vg-relchip 等)。
  const top=(typeof _SUB2TOP!=='undefined')?_SUB2TOP[tab]:null;
  if(top){
    const th=TAB2THEME[top];
    if(th && (!curTheme || curTheme.id!==th.id)){ openTheme(th.id, top); }
    else { const b=[...document.querySelectorAll('.tab')].find(t=>t.dataset.tab===top); if(b) activateTab(b); }
    await renderPane(top);
    const out=document.getElementById('mm-'+top);
    const nav=out&&out.querySelector('.do-nav[data-sub="'+tab+'"]');
    if(nav) nav.click();
    return;
  }
  const th=TAB2THEME[tab];
  if(th && (!curTheme || curTheme.id!==th.id)){
    openTheme(th.id, tab);          // 跨主题:切主题并激活目标 tab
  } else {
    const btn=[...document.querySelectorAll('.tab')].find(t=>t.dataset.tab===tab);
    if(btn) activateTab(btn);
  }
  await renderPane(tab);
}

/* ---- tabs ---- */
/* ---- 主题 × 子视图 两级导航 ---- */
const THEMES = __THEMES__;
const VIEW_GUIDE = __VIEWGUIDE__;
const TAB2THEME = {}; THEMES.forEach(t=>t.tabs.forEach(x=>TAB2THEME[x]=t));
let curTheme=null;

// 渲染视图内右侧常驻导航卡片
function renderGuide(tid){
  const g=VIEW_GUIDE[tid];
  const box=document.getElementById('vguide');
  if(!g){ box.style.display='none'; return; }
  box.style.display='';
  const tabBtn=[...document.querySelectorAll('.tab')].find(b=>b.dataset.tab===tid);
  document.getElementById('vgTitle').textContent = tabBtn?tabBtn.querySelector('.tab-tt').textContent:tid;
  document.getElementById('vgSummary').textContent = g.summary||'';
  // 阶段
  const st=document.getElementById('vgStages');
  document.getElementById('vgStagesSec').style.display=(g.stages&&g.stages.length)?'':'none';
  st.innerHTML=(g.stages||[]).map((s,i)=>'<div class="vg-stage"><span class="vg-num">'+(i+1)+'</span>'+s+'</div>').join('');
}

function showHome(){
  curTheme=null; stopFlow();
  document.getElementById('home').classList.add('show');
  document.getElementById('scroll').style.display='none';
  document.getElementById('breadcrumb').classList.remove('show');
  document.getElementById('tabbar').style.display='none';
  document.getElementById('toolbar').style.display='none';
  document.getElementById('vguide').style.display='none';
}

function openTheme(themeId, tid){
  const th=THEMES.find(t=>t.id===themeId); if(!th) return;
  curTheme=th;
  document.getElementById('home').classList.remove('show');
  document.getElementById('scroll').style.display='';
  document.getElementById('breadcrumb').classList.add('show');
  document.getElementById('tabbar').style.display='';
  document.getElementById('toolbar').style.display='';
  document.getElementById('crumbCur').textContent=th.icon+' '+th.title;
  // 只显示该主题的 tab 按钮
  document.querySelectorAll('.tab').forEach(b=>{
    b.style.display = (b.dataset.theme===themeId)?'':'none';
  });
  // 按主题 tabs 顺序重排按钮 —— tab 栏严格呈现该主题定义的叙事顺序
  const bar=document.getElementById('tabbar');
  th.tabs.forEach(tt=>{
    const b=[...bar.querySelectorAll('.tab')].find(x=>x.dataset.tab===tt);
    if(b) bar.appendChild(b);
  });
  const target = tid || th.tabs[0];
  const btn=[...document.querySelectorAll('.tab')].find(b=>b.dataset.tab===target);
  if(btn){ activateTab(btn); renderPane(target); }
}

function activateTab(t){
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.pane').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  const pane=document.getElementById('pane-'+t.dataset.tab);
  pane.classList.add('active');
  document.getElementById('paneSub').textContent=pane.dataset.sub||'';
  scale=1; stopFlow();
  // 表格类视图(术语/对比/失败/瓶颈):无数据流 → 隐藏播放按钮
  const TABLE_TABS={glossary:1,compare:1,failure:1,bottleneck:1,archcompare:1,mvcompare:1,optcompare:1,idxpano:1,optgoal:1,optaxis:1,optlifecycle:1,optgranularity:1,optoperator:1,optworkload:1,optobserve:1,qlifevars:1,qlifeterms:1};
  var _isDoc=!!document.querySelector('.pane.active .do-paneflow');['zoomOut','zoomReset','zoomIn','fitBtn'].forEach(function(id){var el=document.getElementById(id);if(el)el.style.display=_isDoc?'none':'';});document.getElementById('flowPlay').style.display=(_isDoc||TABLE_TABS[t.dataset.tab])?'none':'';
  renderGuide(t.dataset.tab);
}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{activateTab(t);renderPane(t.dataset.tab);});
document.getElementById('vguideCollapse').onclick=()=>document.getElementById('vguide').classList.toggle('collapsed');
document.querySelectorAll('.tcard').forEach(c=>c.onclick=()=>openTheme(c.dataset.themeId));
document.getElementById('crumbHome').onclick=showHome;
document.getElementById('brandHome').onclick=showHome;

/* ---- 项目导航:唯一入口 = 架构图下钻(无卡片/目录树/切换)---- */
(function(){
  document.querySelectorAll('.arch-hot').forEach(h=>h.onclick=()=>openTheme(h.dataset.themeId));
  document.querySelectorAll('.arch-chip').forEach(c=>c.onclick=()=>openTheme(c.dataset.themeId));
})();

/* ---- theme toggle (深色默认;localStorage 记忆) ---- */
(function(){
  const KEY='atlas-nav-theme';
  const root=document.documentElement;
  function apply(t){ if(t==='light') root.setAttribute('data-theme','light'); else root.removeAttribute('data-theme'); }
  let saved='dark';
  try{ saved=localStorage.getItem(KEY)||'dark'; }catch(e){}
  apply(saved);
  const btn=document.getElementById('themeToggle');
  if(btn) btn.onclick=()=>{
    const cur=root.getAttribute('data-theme')==='light'?'light':'dark';
    const next=cur==='light'?'dark':'light';
    apply(next);
    try{ localStorage.setItem(KEY,next); }catch(e){}
    /* mermaid 图把颜色烘进 SVG,CSS 变量穿不进 → 换 themeVariables 后重渲染当前图 */
    if(typeof initMermaid==='function') initMermaid();
    if(typeof rendered==='object'){ for(const k in rendered) delete rendered[k]; }
    const activeTab=document.querySelector('.tab.active');
    const tid=activeTab?activeTab.dataset.tab:null;
    if(tid && typeof renderPane==='function') renderPane(tid);
  };
})();

/* ---- zoom ---- */
let scale=1;
function applyZoom(){document.querySelectorAll('.pane.active .mmout').forEach(s=>{s.style.transform='scale('+scale+')';});}
document.getElementById('zoomIn').onclick=()=>{scale=Math.min(2.5,scale+0.12);applyZoom();};
document.getElementById('zoomOut').onclick=()=>{scale=Math.max(0.4,scale-0.12);applyZoom();};
document.getElementById('zoomReset').onclick=()=>{scale=1;applyZoom();};
/* 滚轮缩放:滚轮=缩放(以光标为锚点,Figma/Apple 手感);按住 Shift 保留横向滚动 */
(function(){
  const sc=document.getElementById('scroll');
  if(!sc) return;
  let raf=0;
  sc.addEventListener('wheel',function(e){
    if(e.shiftKey) return;
    const pane=document.querySelector('.pane.active');
    // 表格视图 / 垂直 TAB 视图:不做滚轮缩放(仅正常滚动)
    if(pane && (pane.querySelector('.dataorg-wrap') || pane.querySelector('svg.tblsvg'))) return;
    const out=document.querySelector('.pane.active .mmout');
    if(!out) return;
    e.preventDefault();
    const prev=scale;
    const step=(e.deltaY<0?1:-1)*(e.ctrlKey||e.metaKey?0.08:0.15);
    scale=Math.min(2.5,Math.max(0.3,+(scale+step).toFixed(3)));
    if(scale===prev) return;
    const rect=sc.getBoundingClientRect();
    const ox=e.clientX-rect.left, oy=e.clientY-rect.top;   // 光标在视口内偏移
    const cx=sc.scrollLeft+ox, cy=sc.scrollTop+oy;          // 光标指向的内容坐标(缩放前)
    const r=scale/prev;
    out.style.transition='none';                            // 滚轮期间关过渡,避免锚点漂移
    applyZoom();
    sc.scrollLeft=cx*r-ox;
    sc.scrollTop=cy*r-oy;
    if(raf) cancelAnimationFrame(raf);
    raf=requestAnimationFrame(()=>{out.style.transition='';});
  },{passive:false});
  /* 拖拽平移:在空白处按下拖动即可平移画布(命中可下钻节点时不劫持,保证点击下钻) */
  let panning=false, sx=0, sy=0, sl=0, st=0, moved=false;
  sc.style.cursor='grab';
  sc.addEventListener('mousedown',function(e){
    if(e.button!==0) return;
    // 点在可下钻节点/交互元素上时,不启动平移(让 click 生效)
    if(e.target.closest('.flow-node,[data-k],.node.clickable,a,button,.do-nav,.vg-key,.vg-relchip')) return;
    panning=true; moved=false; sx=e.clientX; sy=e.clientY; sl=sc.scrollLeft; st=sc.scrollTop;
    sc.style.cursor='grabbing'; e.preventDefault();
  });
  window.addEventListener('mousemove',function(e){
    if(!panning) return;
    const dx=e.clientX-sx, dy=e.clientY-sy;
    if(!moved && Math.abs(dx)+Math.abs(dy)>3) moved=true;
    sc.scrollLeft=sl-dx; sc.scrollTop=st-dy;
  });
  window.addEventListener('mouseup',function(){
    if(!panning) return;
    panning=false; sc.style.cursor='grab';
  });
})();
function fitActive(){
  const out=document.querySelector('.pane.active .mmout svg');const sc=document.getElementById('scroll');
  if(!out)return;
  const bb=out.getBBox?out.getBBox():{width:out.clientWidth,height:out.clientHeight};
  const w=bb.width||out.clientWidth||1, h=bb.height||out.clientHeight||1;
  const vg=document.getElementById('vguide');
  const vgW=(vg && getComputedStyle(vg).display!=='none' && !vg.classList.contains('collapsed'))?312:0;
  const pad=48;
  const availW=sc.clientWidth-pad*2-vgW, availH=sc.clientHeight-pad*2;
  // 适应:取宽/高较小缩放保证整图完整;上限放宽到 1.8,小图也能占满不显空旷
  scale=Math.min(1.8, Math.max(.35, Math.min(availW/w, availH/h)));
  applyZoom();
  // CSS flex 已水平居中;仅需复位滚动到顶部,横向居中交给浏览器
  requestAnimationFrame(()=>{
    const cw=w*scale, viewW=sc.clientWidth;
    sc.scrollLeft = cw<=viewW ? 0 : (cw-viewW)/2 + vgW/2;
    sc.scrollTop=0;
  });
}
document.getElementById('fitBtn').onclick=fitActive;

/* ---- flow animation: 按拓扑逐段点亮边 ---- */
let flowTimer=null;
function stopFlow(){
  if(flowTimer){clearInterval(flowTimer);flowTimer=null;}
  document.getElementById('flowPlay').classList.remove('on');
  document.getElementById('flowPlay').textContent='▶ 播放数据流';
  document.querySelectorAll('.mmout .flowing').forEach(e=>e.classList.remove('flowing'));
  document.querySelectorAll('.mmout .pulsing').forEach(e=>e.classList.remove('pulsing'));
}
function startFlow(tid){
  const out=document.getElementById('mm-'+tid);if(!out)return;
  // 通用:所有渲染器的连线都带 marker-end(箭头),据此选中即可,无需每个渲染器单独打类
  let paths=[...out.querySelectorAll('svg path[marker-end], svg line[marker-end], .edgePaths path, path.flowchart-link, .edgePath path, line.tour-flowline')];
  paths=[...new Set(paths)];
  let sweepNodes=null;
  if(!paths.length){
    // 无流动边(结构图/schema 表/诊断):退化为按顺序脉冲高亮各节点/行
    sweepNodes=[...out.querySelectorAll('svg g[data-k], svg g.tree-row, svg g.node-box')];
    if(!sweepNodes.length) sweepNodes=[...out.querySelectorAll('svg > rect, svg g > rect')].filter(r=>+r.getAttribute('height')>20 && +r.getAttribute('width')>60);
    if(!sweepNodes.length)return;
  }
  const btn=document.getElementById('flowPlay');btn.classList.add('on');btn.textContent='■ 停止';
  if(paths.length){
    let i=0;const win=Math.max(3,Math.min(6,Math.ceil(paths.length/3)));
    flowTimer=setInterval(()=>{
      paths.forEach(p=>p.classList.remove('flowing'));
      for(let k=0;k<win;k++){const idx=(i+k)%paths.length;paths[idx].classList.add('flowing');}
      i=(i+1)%paths.length;
    },140);
  }else{
    let i=0;
    flowTimer=setInterval(()=>{
      sweepNodes.forEach(n=>n.classList.remove('pulsing'));
      sweepNodes[i%sweepNodes.length].classList.add('pulsing');
      i=(i+1)%sweepNodes.length;
    },420);
  }
}
document.getElementById('flowPlay').onclick=()=>{
  if(flowTimer){stopFlow();return;}
  const tid=document.querySelector('.tab.active').dataset.tab;
  startFlow(tid);
};

/* init: 首页展示主题卡片 */
showHome();

/* 首帧渲染完成后淡出加载覆盖层：双 rAF 确保浏览器已完成首次布局+绘制，
   再留一小段让内联 base64 图解码，避免"空白被误读为内容错误" */
(function hideLoadingOverlay(){
  var ov=document.getElementById('loadingOverlay');
  if(!ov) return;
  function done(){ ov.classList.add('lo-hidden'); setTimeout(function(){ if(ov&&ov.parentNode) ov.parentNode.removeChild(ov); },600); }
  requestAnimationFrame(function(){ requestAnimationFrame(function(){ setTimeout(done,180); }); });
  setTimeout(done,4000);

/* 模块搜索:过滤 THEMES,回车/点击 openTheme 下钻 */
(function(){
  var mq=document.getElementById('mq'), list=document.getElementById('mqlist');
  if(!mq||!list||typeof THEMES==='undefined') return;
  var sel=-1, cur=[];
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function render(){
    var q=mq.value.trim().toLowerCase();
    cur = !q ? [] : THEMES.filter(function(m){return ((m.title||'')+' '+(m.desc||'')+' '+(m.id||'')).toLowerCase().indexOf(q)>=0;}).slice(0,8);
    if(!cur.length){ list.className='mq-list'; list.innerHTML=''; return; }
    sel=0;
    list.innerHTML=cur.map(function(m,i){return '<button class="mq-item'+(i===0?' sel':'')+'" data-id="'+esc(m.id)+'"><b>'+esc(m.title||m.id)+'</b><span class="s">'+esc((m.desc||'').slice(0,52))+'</span></button>';}).join('');
    list.className='mq-list on';
  }
  function go(id){ mq.value=''; list.className='mq-list'; list.innerHTML=''; if(typeof openTheme==='function') openTheme(id); }
  mq.addEventListener('input',render);
  mq.addEventListener('keydown',function(e){
    if(!cur.length){ if(e.key==='Escape') mq.blur(); return; }
    if(e.key==='ArrowDown'){e.preventDefault();sel=(sel+1)%cur.length;}
    else if(e.key==='ArrowUp'){e.preventDefault();sel=(sel-1+cur.length)%cur.length;}
    else if(e.key==='Enter'){e.preventDefault();go(cur[sel].id);return;}
    else if(e.key==='Escape'){list.className='mq-list';mq.blur();return;}
    else return;
    [].forEach.call(list.children,function(el,i){el.className='mq-item'+(i===sel?' sel':'');});
  });
  list.addEventListener('click',function(e){var b=e.target.closest('.mq-item'); if(b) go(b.dataset.id);});
  document.addEventListener('keydown',function(e){ if(e.key==='/'&&document.activeElement!==mq){e.preventDefault();mq.focus();} });
  document.addEventListener('click',function(e){ if(!e.target.closest('.msearch')){list.className='mq-list';} });
})();

})();
"""

html = (HTML_SHELL
        .replace("__TAB_BUTTONS__", tab_buttons)
        .replace("__THEME_CARDS__", theme_cards)
        .replace("__ARCH_SVG_B64__", _ARCH_SVG_B64)
        .replace("__ARCH_HOTSPOTS__", _arch_hotspots_html)
        .replace("__ARCH_EXTRA_CHIPS__", _arch_extra_chips)
        .replace("__TREE_NAV__", tree_nav)
        .replace("__TAB_PANES__", tab_panes)
        .replace("__MERMAID__", mermaid_js))
# 嵌套子视图用的多图数组 / raw mermaid(供 renderInto 在 存储引擎 等嵌套块里渲染)
_NEST_MM = {
    "idxarch": [[t, c] for (t, c) in IDXARCH_MMS],
    "vecsearch": [["倒排 · 全文检索", VECSEARCH_MMS[0][1]], ["向量 · ANN 检索", VECSEARCH_MMS[1][1]]],
    "dataorg": [[t, c] for (t, c) in DATAORG_MMS],
}
_RAW_MM = {"idxchain": IDXCHAIN_MM}
# 数据组织 4 张图各自作为独立 raw mermaid,供 steOrg 拆成 4 个垂直子 tab(而非堆叠)
for _i, (_t, _c) in enumerate(DATAORG_MMS):
    _RAW_MM["dataorg%d" % _i] = _c

app_js = (APP_JS
          .replace("__DRILL__", drill_json)
          .replace("__NEST_MM__", json.dumps(_NEST_MM, ensure_ascii=False))
          .replace("__RAW_MM__", json.dumps(_RAW_MM, ensure_ascii=False))
          .replace("__SVG_WALK_TIDS__", json.dumps({tid: 1 for tid in _SVG_WALK_PANES}, ensure_ascii=False))
          .replace("__QSTOUR_OVERVIEW_B64__", _QSTOUR_OVERVIEW_B64)
          .replace("__THEMES__", json.dumps(THEMES, ensure_ascii=False))
          .replace("__VIEWGUIDE__", json.dumps(VIEW_GUIDE, ensure_ascii=False))
          .replace("__FIRST__", first_tab))
html = html.replace("__APP_JS__", app_js)

import datetime, re
html = html.replace("__GENDATE__", datetime.date.today().isoformat())

# ── 去掉「代码标注」:源码文件:行号(保留类名/方法名/业务描述/mermaid 配色)──
# 两种表示:mermaid 标签里的 <small>…</small>,与 FLOW_SPECS 的 s:'…' 节点副标题。
def _strip_small(m):
    inner = m.group(1)
    if re.search(r'\.(cpp|java|h):\d+', inner):
        rest = re.sub(r'[\w/]+\.(cpp|java|h):\d+', '', inner).strip(' ·:/→>')
        return '<small>' + rest + '</small>' if rest else ''  # 纯源码位置→整块删
    inner2 = re.sub(r'[:：]\d+(?=\s*$)', '', inner)            # 混合「描述:行号」→ 去尾部行号
    return '<small>' + inner2 + '</small>' if inner2.strip() else ''
def _strip_s(m):
    v = m.group(1)
    if re.search(r'\.(cpp|java|h):\d+', v):
        rest = re.sub(r'[\w/]+\.(cpp|java|h):\d+', '', v).strip(' ·:/→>')
        return "s:'" + rest + "'" if rest else "s:''"
    return "s:'" + re.sub(r'[:：]\d+(?=$)', '', v) + "'"
# 先处理 <small>(可能带前导 <br/>,块删掉时一并去掉 <br/>)
html = re.sub(r'<br/>\s*<small>(.*?)</small>', lambda m: (lambda r: ('<br/>' + r) if r else '')(_strip_small(m)), html)
html = re.sub(r'<small>(.*?)</small>', _strip_small, html)
html = re.sub(r"s:'([^']*)'", _strip_s, html)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("Wrote " + os.path.abspath(OUT) + " (" + str(len(html)//1024) + " KB)")
_mounted = [t["id"] for t in THEMES]
print("  themes (" + str(len(_mounted)) + "): " + ", ".join(_mounted))
