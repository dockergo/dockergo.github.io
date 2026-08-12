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
VIEW_GUIDE = {}  # kafka 不使用视图导航卡片;renderGuide 经 if(!g) 防御

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
    <a class="brand" id="brandHome" href="../../index.html" title="返回导航主页">
      <div class="logo"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></div>
    </a>
    <div class="brand-intro" style="display:flex;flex-direction:column;align-items:flex-start;margin-left:12px;min-width:0;max-width:min(60vw,760px)"><div style="font-size:15px;font-weight:600;color:var(--c-ink);line-height:1.3">Apache Kafka · 核心原理图谱</div><span style="margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5;text-align:left">分布式事件流平台:分区 append-only 日志 + 副本 ISR 复制,顺序写磁盘 + 零拷贝高吞吐,消费者组按位点拉取。</span></div>
    <label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label>
    <a href="https://github.com/apache/kafka" target="_blank" rel="noopener" title="GitHub 源码仓库" style="margin-left:auto;display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://kafka.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDMyIDMyIiBwcmVzZXJ2ZUFzcGVjdFJhdGlvPSJ4TWlkWU1pZCI+PHBhdGggZD0iTTIxLjUzOCAxNy43MjRhNC4xNiA0LjE2IDAgMCAwLTMuMTI4IDEuNDJsLTEuOTYtMS4zODhjLjIwOC0uNTczLjMyOC0xLjE4OC4zMjgtMS44MzJhNS4zNSA1LjM1IDAgMCAwLS4zMTctMS44MDJsMS45NTYtMS4zNzNhNC4xNiA0LjE2IDAgMCAwIDMuMTIyIDEuNDE0IDQuMTggNC4xOCAwIDAgMCA0LjE3Mi00LjE3MiA0LjE4IDQuMTggMCAwIDAtNC4xNzItNC4xNzIgNC4xOCA0LjE4IDAgMCAwLTQuMTcyIDQuMTcyYzAgLjQxMi4wNjIuOC4xNzQgMS4xODVsLTEuOTU3IDEuMzc0Yy0uODE4LTEuMDE0LTEuOTk1LTEuNzIzLTMuMzM2LTEuOTRWOC4yNWE0LjE4IDQuMTggMCAwIDAgMy4zMTMtNC4wODJBNC4xOCA0LjE4IDAgMCAwIDExLjM4OCAwYTQuMTggNC4xOCAwIDAgMC00LjE3MiA0LjE3MmMwIDEuOTggMS4zODcgMy42MzcgMy4yNCA0LjA2M3YyLjRDNy45MjggMTEuMDY3IDYgMTMuMjczIDYgMTUuOTI1YzAgMi42NjUgMS45NDcgNC44OCA0LjQ5MyA1LjMwOHYyLjUyM2MtMS44Ny40LTMuMjc2IDIuMDgtMy4yNzYgNC4wNzJBNC4xOCA0LjE4IDAgMCAwIDExLjM4OCAzMmE0LjE4IDQuMTggMCAwIDAgNC4xNzItNC4xNzJjMC0xLjk5My0xLjQwNS0zLjY2LTMuMjc2LTQuMDcydi0yLjUyM2MxLjMxNS0uMjIgMi40Ny0uOTE2IDMuMjgtMS45MDdsMS45NzMgMS4zOTdhNC4xNSA0LjE1IDAgMCAwLS4xNzEgMS4xNzMgNC4xOCA0LjE4IDAgMCAwIDQuMTcyIDQuMTcyIDQuMTggNC4xOCAwIDAgMCA0LjE3Mi00LjE3MiA0LjE4IDQuMTggMCAwIDAtNC4xNzItNC4xNzJ6bTAtOS43NTRjMS4xMTUgMCAyLjAyMi45MDggMi4wMjIgMi4wMjNzLS45MDcgMi4wMjItMi4wMjIgMi4wMjItMi4wMjItLjkwNy0yLjAyMi0yLjAyMi45MDctMi4wMjMgMi4wMjItMi4wMjN6TTkuMzY2IDQuMTcyYzAtMS4xMTUuOTA3LTIuMDIyIDIuMDIzLTIuMDIyczIuMDIyLjkwNyAyLjAyMiAyLjAyMi0uOTA3IDIuMDIyLTIuMDIyIDIuMDIyLTIuMDIzLS45MDctMi4wMjMtMi4wMjJ6TTEzLjQxIDI3LjgzYzAgMS4xMTUtLjkwNyAyLjAyMi0yLjAyMiAyLjAyMnMtMi4wMjMtLjkwNy0yLjAyMy0yLjAyMi45MDctMi4wMjIgMi4wMjMtMi4wMjIgMi4wMjIuOTA3IDIuMDIyIDIuMDIyem0tMi4wMjMtOS4wODJjLTEuNTU2IDAtMi44Mi0xLjI2NS0yLjgyLTIuODJzMS4yNjUtMi44MiAyLjgyLTIuODIgMi44MiAxLjI2NSAyLjgyIDIuODItMS4yNjUgMi44Mi0yLjgyIDIuODJ6bTEwLjE1IDUuMTcyYy0xLjExNSAwLTIuMDIyLS45MDgtMi4wMjItMi4wMjNzLjkwNy0yLjAyMiAyLjAyMi0yLjAyMiAyLjAyMi45MDcgMi4wMjIgMi4wMjItLjkwNyAyLjAyMy0yLjAyMiAyLjAyM3oiLz48L3N2Zz4=" width="18" height="18" alt="官网" style="display:block"/></a><button class="theme-toggle" id="themeToggle" title="切换深色 / 浅色主题" aria-label="切换主题">
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
/* NEST_BLOCKS 置空:kafka 站点不使用嵌套子视图;置空对象,
   renderNested 经 `NEST_BLOCKS[tid]` 防御式访问自动失效。 */
const NEST_BLOCKS={};
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
/* FLOW_SPECS 置空:kafka 站点走 renderSvgWalk,不触达 FLOW_SPECS;
   renderFlowSVG 经 `if(!spec)return` 防御式失效。 */
const FLOW_SPECS={};

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
/* SEQ_SPECS 置空:kafka 站点不使用时序图数据;
   置空,renderSeqSVG 经 `if(!spec)return` 防御式失效。 */
const SEQ_SPECS={};

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
/* DATA_SPECS 置空:kafka 站点不使用;置空,对应 render 经 `if(!spec)return` 失效。 */
DATA_SPECS={};

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
const STRUCT_SPECS={};

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
/* CASE_SPECS 置空:kafka 站点不使用;置空,对应 render 经 `if(!spec)return` 失效。 */
CASE_SPECS={};

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
const MERGE_SPECS={};

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
const _tourLevels=[];
// 层间三类流(参考 Mermaid):控制流(↓ 调度下发)· 数据流(↑ 零拷贝回填)· 反馈闭环(⇢ 异步)
const _tourFlows={};
// 逻辑链路:Query Text → … → Block,每步 = {产物, 转换器/动作, file:line}
// 逻辑链路:每节点 = {产物 o, 转换器 act, file:line s, hover 边详情, star ★机制(挂在该节点下方的边上)}
const _tourChain=[];
const TOUR_PLANS={};

// 术语表:FE/BE/CN、存储层级、执行层级、优化器、检索等首次解释 + 缩写
const GLOSSARY_SPEC={};

// 查询生命周期 · 调优开关速查(session variables)
const QLIFEVARS_SPEC={};

// 查询生命周期 · 术语表
const QLIFETERMS_SPEC={};

// 架构对比 —— 设计取舍(kafka 站点不使用,置空)
const COMPARE_SPEC={};

// 失败与一致性语义:各关键流程的 失败点 / 重试条件 / 幂等边界 / 可见性时刻
const FAILURE_SPEC={};

// 瓶颈模型:每条关键链路"最容易慢在哪里" + 症状 + 调优方向
const BOTTLENECK_SPEC={};

// ===== 核心优化策略常量(kafka 站点不使用,置空)=====
const OPTGOAL_SPEC={};
const OPTAXIS_SPEC={};
const OPTRELATION_SPEC={};
const OPTLIFECYCLE_SPEC={};
const OPTGRANULARITY_SPEC={};
const OPTPHASE_SPEC={};
const OPTOPERATOR_SPEC={};
const OPTWORKLOAD_SPEC={};
const OPTOBSERVE_SPEC={};
const OPTCOMPARE_SPEC={};
const MVCOMPARE_SPEC={};
const ARCHCOMPARE_SPEC={};
const IDXPANO_SPEC={};

const EXPLAIN_SPEC={};

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
const STEPS_SPECS={};
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


/* TREE_SPECS 置空:kafka 站点不使用;置空,对应 render 经 `if(!spec)return` 失效。 */
TREE_SPECS={};

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
  let saved='light';
  try{ saved=localStorage.getItem(KEY)||'light'; }catch(e){}
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
# 嵌套子视图多图数组 / raw mermaid(kafka 站点不使用),
# 置空,renderInto 经防御式访问自动失效,同时切断对已废弃数据常量的引用。
_NEST_MM = {}
_RAW_MM = {}

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
