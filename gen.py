#!/usr/bin/env python3
"""生成核心原理图谱的主导航页面 —— 一张"计算机体系架构图"(离线自包含 · 双主题)。

与早期"项目卡片网格"不同:本导航页**本身是一张计算机体系结构图**,按系统层次
(接口/语言层 → 计算引擎 → 存储引擎 → 消息/流 → 分布式协调 → 编排/服务网格 →
OS 内核 → 网络 → AI/ML → 语言运行时)自上而下布局,**每个项目是所属层里的一个
可点模块**,点击进入该项目的 index.html。看图即知"这套库在计算机体系里覆盖哪些层、
每个项目属于哪一层"。

搜索:输入项目/关键词 → 命中的模块在图上 **flash 高亮**(脉冲 + 高对比描边)提示位置,
而非把图换成列表。搜不到则无高亮。

自包含:仅标准库,扫描同级 *-design/ 目录判定状态、抽取主题、探测图标,产出单文件
HTML(内联 JS/CSS,无网络/服务器依赖)。新增项目补一条 LAYER_MAP 映射即在图上落位;
未映射的项目落"其他/待归类"层。

图标(可选):项目 <xxx>-design/design/ 下若有 icon.svg / logo.svg / <key>.svg|png,
自动内联为该模块图标;否则回退首字母 tile。
"""
import base64
import html
import json
import os
import re
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成计算机体系架构图主导航(离线自包含 HTML)")
_ap.add_argument("--root", default=HERE, help="扫描根目录(默认:脚本同级)")
_ap.add_argument("--out", default=None, help="输出 HTML 路径(默认:<root>/index.html)")
_ap.add_argument("--suffix", default="-design", help="项目目录后缀(默认:-design)")
_args, _ = _ap.parse_known_args()

ROOT = os.path.abspath(_args.root)
OUT = _args.out or os.path.join(ROOT, "index.html")
SUFFIX = _args.suffix

# ── 计算机体系层次(自上而下 = 近用户 → 近硬件);对齐 archetype-registry 家族 ──
# 每层:key / 标题 / 副标 / 语义色(与 svg-grammar 语义色一致:蓝=协调 琥珀=存储 绿=网络/成功 紫=接口/AI 青=计算)
# ── 计算系统母能量流(生命周期机制节点,自上而下 = 请求/数据穿过系统的顺序)──
# 母隐喻:一台精密计算机器。项目 = 挂在机制节点上的工业模块实例(非主角)。
# 视觉契约见 design-skills/references/visual-system.md:≤4 语义色,银灰结构 + 单蓝主数据流强调。
LAYERS = [
    ("ingress",  "Ingress · 入口",       "请求接入 · 路由 · TLS · 负载均衡",       "#0a84ff"),
    ("schedule", "Schedule · 调度",      "资源编排 · DAG · slot · 控制循环",       "#a78bfa"),
    ("execute",  "Execute · 执行",       "查询/向量化 · 训练推理 · 算子流水",       "#0a84ff"),
    ("state",    "State · 状态",         "内存 · 索引 · 事务 · 状态后端",           "#2dd4bf"),
    ("persist",  "Persist · 持久化",     "日志 · 表格式 · 列存文件 · 分布式文件",   "#2dd4bf"),
    ("coord",    "Coordinate · 一致性",  "共识 · 选主 · 控制面状态 · 服务发现",     "#a78bfa"),
    ("runtime",  "Runtime · 执行模型",   "语言运行时 · 内存/调度纪律 · GC · 并发",  "#8a8a90"),
    ("misc",     "其他 · 待归类",        "尚未映射到机制节点的项目",                "#6b7280"),
]
LAYER_ORDER = [k for k, *_ in LAYERS]

# ── 项目 → 机制节点 映射(动力学:项目落在"它在计算系统里承担的机制"上,而非技术分类)──
# 系统本就跨层;此处取其**主导机制**落位。新增项目补一条即在母图上落位。
LAYER_MAP = {
    # Ingress:入口/路由/TLS/负载均衡/传输
    "nginx": "ingress", "ffmpeg": "ingress", "grpc": "ingress",
    # Schedule:编排/调度/资源
    "kubernetes": "schedule", "ray": "schedule", "spark": "schedule", "flink": "schedule",
    "containerd": "schedule",
    # Execute:查询执行/向量化/训练推理
    "doris": "execute", "clickhouse": "execute", "starrocks": "execute",
    "trino": "execute", "duckdb": "execute", "hive": "execute",
    "pytorch": "execute", "tensorflow": "execute", "vllm": "execute", "milvus": "execute",
    # State:内存/索引/事务/状态后端/图
    "redis": "state", "rocksdb": "state", "postgres": "state", "neo4j": "state",
    "mysql-server": "state",
    # Persist:日志/表格式/列存/分布式文件
    "kafka": "persist", "hudi": "persist",
    "iceberg": "persist", "orc": "persist", "hadoop": "persist", "arrow": "persist",
    "parquet": "persist",
    # Coordinate:共识/选主/控制面状态
    "etcd": "coord", "zookeeper": "coord", "hashicorp-raft": "coord", "etcd-raft": "coord",
    # Runtime:语言运行时/执行模型/内存纪律
    "go": "runtime", "rust": "runtime", "linux": "runtime", "openjdk": "runtime",
}


# ── 展示元数据(名称 / 描述 / tile 品牌色);未登记的目录用默认值 ──
META = {
    "clickhouse": {"name": "ClickHouse", "init": "CH", "desc": "列式 OLAP 数据库",
                   "lc": "linear-gradient(135deg,#f7c948,#f59e0b)"},
    "doris": {"name": "Apache Doris", "init": "DS", "desc": "MPP 分析型数据库",
              "lc": "linear-gradient(135deg,#0a84ff,#409cff)"},
    "starrocks": {"name": "StarRocks", "init": "SR", "desc": "MPP 分析型数据库",
                  "lc": "linear-gradient(135deg,#00b0ff,#4dd0e1)"},
    "trino": {"name": "Trino", "init": "TR", "desc": "分布式 SQL 查询引擎",
              "lc": "linear-gradient(135deg,#7c5fe6,#a78bfa)"},
    "hive": {"name": "Apache Hive", "init": "HV", "desc": "SQL 数据仓库 · 存算解耦",
             "lc": "linear-gradient(135deg,#fdb515,#f6832b)"},
    "spark": {"name": "Apache Spark", "init": "SP", "desc": "分布式计算引擎",
              "lc": "linear-gradient(135deg,#e25a1c,#f6832b)"},
    "flink": {"name": "Apache Flink", "init": "FL", "desc": "流批一体计算引擎",
              "lc": "linear-gradient(135deg,#e6526e,#f6832b)"},
    "duckdb": {"name": "DuckDB", "init": "DK", "desc": "嵌入式分析型数据库",
               "lc": "linear-gradient(135deg,#fbbf24,#fcd34d)"},
    "redis": {"name": "Redis", "init": "RD", "desc": "内存数据结构存储",
              "lc": "linear-gradient(135deg,#f43f5e,#fb7185)"},
    "rocksdb": {"name": "RocksDB", "init": "RO", "desc": "嵌入式 KV 存储引擎 · LSM",
                "lc": "linear-gradient(135deg,#f59e0b,#fbbf24)"},
    "postgres": {"name": "PostgreSQL", "init": "PG", "desc": "关系型数据库 · MVCC",
                 "lc": "linear-gradient(135deg,#336791,#5b8cb8)"},
    "neo4j": {"name": "Neo4j", "init": "NE", "desc": "原生图数据库 · Cypher",
              "lc": "linear-gradient(135deg,#2dd4a7,#4ade80)"},
    "hadoop": {"name": "Hadoop HDFS", "init": "HD", "desc": "分布式文件系统",
               "lc": "linear-gradient(135deg,#f59e0b,#fcd34d)"},
    "etcd": {"name": "etcd", "init": "ET", "desc": "分布式 KV · Raft",
             "lc": "linear-gradient(135deg,#2dd4a7,#5eead4)"},
    "zookeeper": {"name": "ZooKeeper", "init": "ZK", "desc": "分布式协调 · ZAB",
                  "lc": "linear-gradient(135deg,#4f9dff,#7cb8ff)"},
    "hashicorp-raft": {"name": "HashiCorp Raft", "init": "HR", "desc": "共识算法库 · 电池全含",
                       "lc": "linear-gradient(135deg,#0a84ff,#5b8cff)"},
    "etcd-raft": {"name": "etcd Raft", "init": "ER", "desc": "共识状态机核 · Ready 驱动",
                  "lc": "linear-gradient(135deg,#2dd4a7,#5eead4)"},
    "kafka": {"name": "Apache Kafka", "init": "KF", "desc": "分布式事件流平台",
              "lc": "linear-gradient(135deg,#8e8e93,#4a4a4f)"},
    "kubernetes": {"name": "Kubernetes", "init": "K8", "desc": "容器编排系统",
                   "lc": "linear-gradient(135deg,#326ce5,#5b8cff)"},
    "nginx": {"name": "Nginx", "init": "NG", "desc": "Web 服务器 / 反向代理",
              "lc": "linear-gradient(135deg,#2f8f5e,#4ade80)"},
    "linux": {"name": "Linux Kernel", "init": "LX", "desc": "操作系统内核",
              "lc": "linear-gradient(135deg,#5a5a64,#7a8494)"},
    "go": {"name": "Go", "init": "GO", "desc": "语言核心原理 · 编译期 + 运行期",
           "lc": "linear-gradient(135deg,#00add8,#5dc9e2)"},
    "rust": {"name": "Rust", "init": "RS", "desc": "系统级语言 · 所有权",
             "lc": "linear-gradient(135deg,#dea584,#b7410e)"},
    "pytorch": {"name": "PyTorch", "init": "PT", "desc": "深度学习框架",
                "lc": "linear-gradient(135deg,#ee4c2c,#f6832b)"},
    "tensorflow": {"name": "TensorFlow", "init": "TF", "desc": "深度学习框架",
                   "lc": "linear-gradient(135deg,#f59e0b,#ff6f00)"},
    "ray": {"name": "Ray", "init": "RY", "desc": "分布式 AI 计算框架",
            "lc": "linear-gradient(135deg,#0a84ff,#28a5f5)"},
    "vllm": {"name": "vLLM", "init": "VL", "desc": "LLM 高吞吐推理引擎",
             "lc": "linear-gradient(135deg,#f472b6,#a78bfa)"},
    "milvus": {"name": "Milvus", "init": "MV", "desc": "向量数据库",
               "lc": "linear-gradient(135deg,#00b0ff,#4dd0e1)"},
    "iceberg": {"name": "Apache Iceberg", "init": "IC", "desc": "开放表格式",
                "lc": "linear-gradient(135deg,#38bdf8,#7cc7f0)"},
    "hudi": {"name": "Apache Hudi", "init": "HU", "desc": "数据湖表格式",
             "lc": "linear-gradient(135deg,#f59e0b,#fcd34d)"},
    "orc": {"name": "Apache ORC", "init": "OR", "desc": "列式存储文件格式",
            "lc": "linear-gradient(135deg,#8e8e93,#b0b0b5)"},
    "parquet": {"name": "Apache Parquet", "init": "PQ", "desc": "列式文件格式 · Dremel 嵌套",
                "lc": "linear-gradient(135deg,#0ea5e9,#38bdf8)"},
    "ffmpeg": {"name": "FFmpeg", "init": "FF", "desc": "多媒体编解码",
               "lc": "linear-gradient(135deg,#4ade80,#5dc9e2)"},
    "mysql-server": {"name": "MySQL", "init": "MY", "desc": "关系数据库 · InnoDB",
                     "lc": "linear-gradient(135deg,#00758f,#4a9db5)"},
    "containerd": {"name": "containerd", "init": "CD", "desc": "容器运行时 · 插件化",
                   "lc": "linear-gradient(135deg,#5758a8,#8a8bd0)"},
    "grpc": {"name": "gRPC", "init": "GR", "desc": "HTTP/2 RPC 框架",
             "lc": "linear-gradient(135deg,#2dd4a7,#48b0c4)"},
    "openjdk": {"name": "OpenJDK", "init": "JD", "desc": "JVM · JIT + GC",
                "lc": "linear-gradient(135deg,#e76f00,#f89820)"},
    "arrow": {"name": "Apache Arrow", "init": "AR", "desc": "列式内存格式 · 零拷贝",
              "lc": "linear-gradient(135deg,#4a6fdc,#7b9ff0)"},
}

SKIP_TOP = {
    "双维模型", "总架构图", "依赖矩阵", "依赖关系图", "物理部署图", "部署形态",
    "全景主线框架", "全景", "运行形态", "编程接口层", "诊断原理", "集成架构",
    "常见问题", "Profile透视",
}

# 图标候选文件名(按优先级);置于项目 design/ 下
def _icon_candidates(key):
    return ["icon.svg", "logo.svg", f"{key}.svg", "icon.png", "logo.png", f"{key}.png"]


def analyze(d, key):
    """统计 svg/md 数、抽取主题模块、记录最近更新。返回 (svg, md, chips, topics, latest)。

    key:项目 key,用于识别并排除图标文件(icon.svg/logo.svg/<key>.svg),
    使其不计入图数 / 最近更新 / 主题(否则联网抓来的图标会污染统计、把更新日拉到今天)。
    """
    svg = md = 0
    latest = 0.0
    themes, prose = {}, []
    icons = set(_icon_candidates(key))
    for base, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in files:
            low = f.lower()
            is_svg, is_md = low.endswith(".svg"), low.endswith(".md")
            if not (is_svg or is_md):
                continue
            # 图标文件不计入图数 / 更新时间 / 主题
            if f in icons:
                continue
            svg += is_svg
            md += is_md
            try:
                latest = max(latest, os.path.getmtime(os.path.join(base, f)))
            except OSError:
                pass
            m = re.match(r"^(.+?)原理[_](.+)$", os.path.splitext(f)[0])
            if not m:
                continue
            parts = m.group(2).split("_")
            if len(parts) < 2 or parts[0] in SKIP_TOP:
                continue
            if parts[0] == "支撑":
                prose.append(parts[1])
            else:
                slot = themes.setdefault(parts[0], [0, 0])
                slot[0 if is_svg else 1] += 1
    real = sorted([(k, v[0] + v[1]) for k, v in themes.items() if (v[0] + v[1]) >= 2],
                  key=lambda x: -x[1])
    prose_uniq = list(dict.fromkeys(prose))
    if len(real) >= 3:
        chips, topics = [k for k, _ in real], len(real)
    else:
        chips = prose_uniq + [k for k, _ in real if k not in prose_uniq]
        topics = len(chips)
    return svg, md, chips[:6], topics, latest


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def _find_icon(full, design, key):
    """在 design/ 下按候选名找图标,内联为 data URI;找不到返回 None。"""
    for name in _icon_candidates(key):
        p = os.path.join(design, name)
        if os.path.isfile(p):
            ext = name.rsplit(".", 1)[-1].lower()
            mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
            with open(p, "rb") as f:
                b = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{b}"
    return None


def scan():
    projects = []
    # 项目统一放在 projects/<name>/ 下(name 无 -design 后缀);向后兼容:projects/ 缺失时回退扫描根级 *-design/
    proot = os.path.join(ROOT, "projects")
    if os.path.isdir(proot):
        base, entries = proot, sorted(os.listdir(proot))
    else:
        base, entries = ROOT, sorted(os.listdir(ROOT))
    for entry in entries:
        full = os.path.join(base, entry)
        if not os.path.isdir(full):
            continue
        if base == ROOT:  # 兼容旧结构
            if not entry.endswith(SUFFIX):
                continue
            key = entry[: -len(SUFFIX)].strip()
        else:
            key = entry.strip()
        if not os.path.isfile(os.path.join(full, "gen.py")) and not os.path.isdir(os.path.join(full, "design")):
            continue
        # 归一化查表键:去空格 + 小写,兼容 "FFmpeg" 等目录名瑕疵
        lookup = key.lower()
        meta = dict(META.get(lookup, META.get(key, {})))
        name = meta.get("name", key.replace("-", " ").replace("_", " ").title())
        design = os.path.join(full, "design")
        idx = os.path.join(full, "index.html")
        design_idx = os.path.join(design, "index.html")
        svg, md, chips, topics, latest = analyze(full, key)

        if os.path.isfile(idx):
            status, href = "ready", _rel(idx)
        elif os.path.isfile(design_idx):
            status, href = "ready", _rel(design_idx)
        elif svg or md:
            status = "assets"
            href = _rel(design) + "/" if os.path.isdir(design) else _rel(full) + "/"
        else:
            status, href = "plan", None

        projects.append({
            "name": name, "key": key,
            "layer": LAYER_MAP.get(lookup, LAYER_MAP.get(key, "misc")),
            "desc": meta.get("desc", name),
            "modules": chips, "topics": topics, "svg": svg, "md": md,
            "updated": time.strftime("%Y-%m-%d", time.localtime(latest)) if latest else None,
            "status": status, "href": href,
            "init": meta.get("init", key[:2].upper()),
            "lc": meta.get("lc"),
            "icon": _find_icon(full, design, key) if os.path.isdir(design) else None,
        })
    projects.sort(key=lambda p: p["name"].lower())
    return projects


def _site_latest_mtime():
    """扫描全站所有 svg/md 的最新修改时间(不止 projects/),
    使 scenarios/llm/topics/principles/basic 等任意区域内容改动都能刷新首页「更新」日期。
    忽略隐藏目录(.git/.joycode/.codegraph 等)与图标文件。"""
    latest = 0.0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "__pycache__"]
        for f in files:
            low = f.lower()
            if not (low.endswith(".svg") or low.endswith(".md")):
                continue
            if low in ("icon.svg", "logo.svg"):
                continue
            try:
                latest = max(latest, os.path.getmtime(os.path.join(base, f)))
            except OSError:
                pass
    return latest


def aggregate(projects):
    by_layer = {k: 0 for k in LAYER_ORDER}
    for p in projects:
        by_layer[p["layer"]] = by_layer.get(p["layer"], 0) + 1
    _mt = _site_latest_mtime()
    latest = time.strftime("%Y-%m-%d", time.localtime(_mt)) if _mt else ""
    for p in projects:
        if p["updated"] and p["updated"] > latest:
            latest = p["updated"]
    return {
        "projects": len(projects),
        "accessible": sum(1 for p in projects if p["status"] != "plan"),
        "ready": sum(1 for p in projects if p["status"] == "ready"),
        "svg": sum(p["svg"] for p in projects),
        "md": sum(p["md"] for p in projects),
        "layers": sum(1 for k in LAYER_ORDER if by_layer.get(k)),
        "by_layer": by_layer,
        "updated": latest,
    }


def _gid(key):
    """项目 key → SVG 元素 id;Python 与 JS 必须一致。"""
    return "m_" + re.sub(r"[^a-zA-Z0-9]+", "_", key.lower())


def _esc(s):
    return html.escape(str(s), quote=True)


def _urlq(s):
    """URL query 值编码(拼进 href,供项目页读来路视角面包屑)。"""
    from urllib.parse import quote
    return quote(str(s), safe="")


def _ellip(s, n):
    """按 CJK 宽度截断:CJK 记 1,ASCII 记 0.55,超 n 加省略号。"""
    s = str(s)
    w = 0.0
    for i, ch in enumerate(s):
        w += 1.0 if ord(ch) > 0x2E7F else 0.55
        if w > n:
            return s[:i].rstrip(" ·/") + "…"
    return s


LAYER_TITLE = {k: t for k, t, s, c in LAYERS}
LAYER_SUB = {k: s for k, t, s, c in LAYERS}
LAYER_COLOR = {k: c for k, t, s, c in LAYERS}

# ── 几何(px)── 计算系统架构母图:主路径 + 控制面 + 状态/持久化 + 运行时底座 ──
_CW = 1280
_PAD = 28
_FRAME_X = 28
_FRAME_Y = 28
_FRAME_W = _CW - 2 * _FRAME_X
_NODEH = 42
_NG = 10
_ROWG = 10
_PANEL_HEAD = 96   # 面板顶 → 第一排卡片
_PANEL_PAD = 22    # 末排卡片 → 面板底
# 每面板列数(定死,配合宽度保证卡片可读);高度由项目数 × 列数派生,不再写死。
# 双轴布局:数据通路(spine,宽 680)3–4 列;控制面(ctrl,窄 334)2 列;runtime 全宽 4 列。
_COLS = {"ingress": 3, "schedule": 2, "coord": 2,
         "execute": 3, "state": 4, "persist": 3, "runtime": 4}
# 窄卡展示名覆盖(全名仍进 tooltip/搜索);配合 2 列布局避免文字溢出
_DISP = {"PostgreSQL": "Postgres", "Hadoop HDFS": "Hadoop", "Apache Hadoop HDFS": "Hadoop"}

LAYER_ITEMS = {}


def _node(p, x, y, w, accent, sheen="cardSheen", lens_id="", lens_label=""):
    """项目节点:工业铭牌式模块。点击进入项目架构图。
    lens_id/lens_label:携带来路视角语境,拼进 href query,项目页顶部可显示面包屑。"""
    nav = p["status"] != "plan"
    gid = _gid(p["key"])
    dot = {"ready": "var(--ok)", "assets": "var(--warn)"}.get(p["status"], "var(--c-ink3)")
    cls = "nd" if nav else "nd nd-plan"
    meta = ("{s} 图 · {m} 篇".format(s=p["svg"], m=p["md"]) if (p["svg"] or p["md"])
            else ("规划中" if not nav else "待编译"))
    tip = "{n} · {d} · {m}".format(n=p["name"], d=p["desc"], m=meta)
    href = p["href"]
    if nav and lens_id:
        sep = "&" if "?" in href else "?"
        href = "{h}{sep}lens={lid}".format(h=href, sep=sep, lid=lens_id)
        if lens_label:
            href += "&from=" + _urlq(lens_label)
    if nav:
        head = ('<a href="{h}" class="{c}" id="{i}" tabindex="0">'
                '<title>{t}</title>').format(h=_esc(href), c=cls, i=gid, t=_esc(tip))
        tail = "</a>"
    else:
        head = '<g class="{c}" id="{i}"><title>{t}</title>'.format(c=cls, i=gid, t=_esc(tip))
        tail = "</g>"
    out = [head,
           '<rect class="nd-rect" x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
           'style="--accent:{a}"/>'.format(x=x, y=y, w=w, h=_NODEH, a=accent)]
    isz = 22
    ix, iy = x + 14, y + (_NODEH - isz) / 2
    if p.get("icon"):
        out.append('<image class="nd-ic" x="{ix}" y="{iy:.1f}" width="{s}" height="{s}" href="{u}" '
                   'preserveAspectRatio="xMidYMid meet"/>'.format(ix=ix, iy=iy, s=isz, u=_esc(p["icon"])))
    else:
        out.append('<rect class="tile" x="{ix}" y="{iy:.1f}" width="{s}" height="{s}" rx="6" '
                   'style="--accent:{a}"/>'.format(ix=ix, iy=iy, s=isz, a=accent))
        out.append('<text class="tile-t" x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle">{t}</text>'
                   .format(tx=ix + isz / 2, ty=iy + isz / 2 + 3.5, t=_esc(p["init"])))
    disp = p["name"]
    for _pre in ("Apache ",):  # 门户展示去掉厂牌前缀,窄卡更清爽;全名仍在 tooltip/搜索
        if disp.startswith(_pre):
            disp = disp[len(_pre):]
    disp = _DISP.get(disp, disp)  # 长名覆盖(PostgreSQL→Postgres 等),配合 2 列避免溢出
    name = disp if len(disp) <= 14 else disp[:13] + "…"
    out.append('<text class="nd-name" x="{tx}" y="{ty:.1f}">{n}</text>'.format(
        tx=x + isz + 18, ty=y + _NODEH / 2 + 4, n=_esc(name)))
    if p["status"] != "ready":
        out.append('<circle class="nd-dot" cx="{cx}" cy="{cy}" r="3" style="fill:{d}"/>'.format(
            cx=x + w - 12, cy=y + 12, d=dot))
    out.append(tail)
    return "".join(out)


def _flow_path(cls, points, label=None, lx=0, ly=0):
    d = "M " + " L ".join("{:.1f} {:.1f}".format(x, y) for x, y in points)
    text = '' if not label else '<text class="flow-label" x="{x}" y="{y}">{t}</text>'.format(
        x=lx, y=ly, t=_esc(label))
    return '<path class="{c}" d="{d}" marker-end="url(#{c}-arrow)"/>{text}'.format(c=cls, d=d, text=text)


def _panel_h(key, cols):
    """面板高度由真实项目数派生:标题区 + ceil(items/cols) 行。彻底根治溢出。"""
    n = len(LAYER_ITEMS.get(key, []))
    rows = max(1, -(-n // cols)) if n else 1  # ceil
    return _PANEL_HEAD + rows * (_NODEH + _ROWG) - _ROWG + _PANEL_PAD


def _panel(idx, key, title, sub, x, y, w, h, cols=2):
    items = LAYER_ITEMS.get(key, [])
    accent = LAYER_COLOR.get(key, "#8a8a90")
    parts = [
        '<g class="sys-panel" data-layer="{k}">'.format(k=_esc(key)),
        '<rect class="panel-shell" x="{x}" y="{y}" width="{w}" height="{h}" rx="22"/>'.format(x=x, y=y, w=w, h=h),
        '<text class="panel-num" x="{x}" y="{y}">{n:02d}</text>'.format(x=x + 18, y=y + 42, n=idx),
        '<text class="panel-title" x="{x}" y="{y}">{t}</text>'.format(x=x + 72, y=y + 32, t=_esc(title)),
        '<text class="panel-sub" x="{x}" y="{y}">{s}</text>'.format(x=x + 72, y=y + 55, s=_esc(sub)),
        '<line class="panel-rule" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'.format(x1=x + 20, x2=x + w - 20, y=y + 76),
    ]
    if not items:
        parts.append('<text class="panel-empty" x="{x}" y="{y}">No project mapped</text>'.format(x=x + 24, y=y + 110))
    else:
        inner_x = x + 22
        inner_y = y + 96
        card_w = (w - 44 - (cols - 1) * _NG) / cols
        for i, proj in enumerate(items):
            r, c = divmod(i, cols)
            nx = inner_x + c * (card_w + _NG)
            ny = inner_y + r * (_NODEH + _ROWG)
            parts.append(_node(proj, nx, ny, card_w, accent))
    parts.append('</g>')
    return "".join(parts)


def build_svg(projects):
    """计算机系统架构导航图 · 双轴理论骨架(冯诺依曼数据通路 × 控制面)。
      纵轴 = 冯诺依曼数据通路(von Neumann 1945):I/O 接入 → ALU 执行 → Memory 态 → Storage 外存,
             左侧竖脊,蓝色 Hot Path 自上而下贯穿。
      横切 = 控制/数据面分离(分布式经典,正交):调度控制面 + 共识协调面在右列,
             紫色 Control Path 横向注入数据通路每一级。
      底座 = Runtime(语言运行时/OS),全宽,点线向上支撑。
    面板高度由项目数派生,band/rail/侧轨/总高全部从算出的位置回填——根治溢出与走线穿面板。"""
    global LAYER_ITEMS
    LAYER_ITEMS = {k: [p for p in projects if p["layer"] == k] for k, *_ in LAYERS}

    # —— 双轴几何 —— #
    SPINE_X, SPINE_W = 70, 680          # 左:数据通路竖脊
    CTRL_X, CTRL_W = 786, 338           # 右:控制面列
    Y1, VGAP = 158, 62                  # 数据通路首排顶 / 排间空隙
    meta = {  # key: (序号, 标题, 副标[含理论出处], 轴)
        "ingress":  (1, "I/O · Ingress",      "北向接入 · 网关 · TLS · 传输(数据通路 I/O)",   "spine"),
        "execute":  (4, "ALU · Execution",    "查询/向量化 · 训练推理 · 算子流水(运算器)",    "spine"),
        "state":    (5, "Memory · State",     "内存 · 索引 · 事务 · 状态后端(主存)",          "spine"),
        "persist":  (6, "Storage · Durability","日志 · 表格式 · 列存 · 分布式文件(外存)",      "spine"),
        "schedule": (2, "Control Plane",      "资源编排 · DAG · slot · 控制循环",              "ctrl"),
        "coord":    (3, "Consensus Plane",    "共识 · 选主 · 控制面状态 · 服务发现",           "ctrl"),
        "runtime":  (7, "Runtime Substrate",  "语言运行时 · GC · 调度纪律 · 内核(执行底座)",   "base"),
    }
    spine = ["ingress", "execute", "state", "persist"]   # 纵轴自上而下
    ctrl = ["schedule", "coord"]                          # 横切控制面(右列自上而下)

    rect = {}                                             # key -> (x, y, w, h, cols)
    # 数据通路竖脊:逐级堆叠,高度自适应
    y = Y1
    spine_rows = []
    for k in spine:
        h = _panel_h(k, _COLS[k])
        rect[k] = (SPINE_X, y, SPINE_W, h, _COLS[k])
        spine_rows.append((k, y, h))
        y += h + VGAP
    spine_bottom = spine_rows[-1][1] + spine_rows[-1][2]

    # 控制面右列:每块与其"注入的数据通路级"垂直对齐——
    #   02 Control Plane 注入 04 ALU/Execution(调度决定算子/资源),与 Execution 齐平;
    #   03 Consensus 注入 05 Memory/State(共识决定状态一致性),与 State 齐平。
    #   横向紫箭头因此真正落在目标级右缘,并直观表达"控制面在其所控数据级之侧"。
    inject = {"schedule": "execute", "coord": "state"}
    for k in ctrl:
        h = _panel_h(k, _COLS[k])
        tgt = rect[inject[k]]
        ty = tgt[1] + tgt[3] / 2 - h / 2      # 中心对齐目标级中心
        rect[k] = (CTRL_X, ty, CTRL_W, h, _COLS[k])

    # Runtime 底座:全宽,置于数据通路脊底之下
    rt_y = spine_bottom + 84
    rt_h = _panel_h("runtime", _COLS["runtime"])
    rect["runtime"] = (SPINE_X, rt_y, CTRL_X + CTRL_W - SPINE_X, rt_h, _COLS["runtime"])

    last_bottom = rt_y + rt_h
    total_h = last_bottom + 96

    body = []
    body.append('<rect class="frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="28"/>'.format(
        x=_FRAME_X, y=_FRAME_Y, w=_FRAME_W, h=total_h - 2 * _FRAME_Y))
    body.append('<text class="map-kicker" x="70" y="72">COMPUTER SYSTEM ARCHITECTURE · VON NEUMANN DATA PATH × CONTROL PLANE</text>')
    body.append('<text class="map-title" x="70" y="106">数据通路(I/O → 运算 → 主存 → 外存) 纵贯,控制面 / 共识面 正交横切</text>')
    body.append('<text class="map-subtitle" x="70" y="130">纵轴=冯诺依曼数据通路(1945) · 横切=控制面/数据面分离(分布式经典) · 底座=运行时;点击任意模块下钻项目架构图</text>')

    # —— 轴标注:左脊 DATA PATH,右列 CONTROL —— #
    body.append('<text class="axis-cap" x="{x}" y="{y}" transform="rotate(-90 {x} {y})">DATA PATH · 冯诺依曼数据通路</text>'.format(x=54, y=(Y1 + spine_bottom) / 2))
    body.append('<text class="axis-cap axis-cap-ctrl" x="{x}" y="{y}">CONTROL / COORDINATION PLANE · 正交横切</text>'.format(x=CTRL_X, y=Y1 - 18))

    def cx(k):
        x, yy, w, h, _ = rect[k]; return x + w / 2
    def cyv(k):
        x, yy, w, h, _ = rect[k]; return yy + h / 2

    body.append('<g class="machine-rails">')
    # 纵轴 Hot Path:Ingress → Execute → State → Persist(数据通路竖脊,蓝实线发光)
    for a, b in zip(spine, spine[1:]):
        ax, ay, aw, ah, _ = rect[a]
        body.append(_flow_path('flow-hot', [(SPINE_X + SPINE_W / 2, ay + ah), (SPINE_X + SPINE_W / 2, rect[b][1])]))
    # 横切 Control Path:控制面 → Execute,共识面 → State(紫虚线,水平注入数据通路右缘)
    sx = rect["execute"]
    body.append(_flow_path('flow-ctrl', [(CTRL_X, cyv("schedule")), (sx[0] + sx[2], cyv("schedule"))]))
    stt = rect["state"]
    body.append(_flow_path('flow-ctrl', [(CTRL_X, cyv("coord")), (stt[0] + stt[2], cyv("coord"))]))
    # 底座 Runtime:数据通路脊底 → Runtime(点线向上支撑)
    body.append(_flow_path('flow-opt', [(cx("persist"), spine_bottom), (cx("persist"), rt_y)]))
    body.append(_flow_path('flow-opt', [(cx("coord"), rect["coord"][1] + rect["coord"][3]), (cx("coord"), rt_y)]))
    body.append('<text class="rail-label flow-hot-lab" x="{x}" y="{y}">Hot Path · request / stream / batch</text>'.format(x=SPINE_X + SPINE_W / 2 + 12, y=(rect["ingress"][1] + rect["ingress"][3] + rect["execute"][1]) / 2 + 4))
    body.append('<text class="rail-label flow-ctrl-lab" x="{x}" y="{y}" text-anchor="middle">调度</text>'.format(x=(sx[0] + sx[2] + CTRL_X) / 2, y=cyv("schedule") - 8))
    body.append('<text class="rail-label flow-ctrl-lab" x="{x}" y="{y}" text-anchor="middle">共识</text>'.format(x=(stt[0] + stt[2] + CTRL_X) / 2, y=cyv("coord") - 8))
    body.append('<text class="rail-label" x="{x}" y="{y}">Runtime Substrate · memory / thread / kernel</text>'.format(x=SPINE_X + 8, y=(spine_bottom + rt_y) / 2 - 4))
    body.append('</g>')

    for k in meta:
        idx, title, sub, _axis = meta[k]
        x, yy, w, h, cols = rect[k]
        body.append(_panel(idx, k, title, sub, x, yy, w, h, cols))

    # 侧轨:纵向覆盖数据通路(OBSERVE 上半 / RECOVER 下半),挂在最右
    sr_y, sr_bot = Y1, last_bottom
    sr_h = sr_bot - sr_y
    sr_mid = sr_h / 2
    body.append('<g class="side-rail" transform="translate(1158,{y})">'
                '<rect x="0" y="0" width="44" height="{h}" rx="22"/>'
                '<text x="22" y="42" text-anchor="middle">OBSERVE</text>'
                '<line x1="22" y1="76" x2="22" y2="{m1}"/>'
                '<text x="22" y="{mt}" text-anchor="middle">RECOVER</text>'
                '<line x1="22" y1="{m2}" x2="22" y2="{be}"/>'
                '</g>'.format(y=sr_y, h=sr_h, m1=sr_mid - 40, mt=sr_mid + 46, m2=sr_mid + 80, be=sr_h - 30))

    body.append('<g class="legend" transform="translate(72,{ly})">'
                '<path class="flow-hot" d="M0 0 L34 0"/><text x="44" y="4">Hot data path · 数据通路</text>'
                '<path class="flow-ctrl" d="M196 0 L230 0"/><text x="240" y="4">Control · 控制/协调面(横切)</text>'
                '<path class="flow-opt" d="M470 0 L504 0"/><text x="514" y="4">Runtime substrate · 底座</text>'
                '<circle cx="712" cy="0" r="3.5" style="fill:var(--warn)"/><text x="722" y="4">assets / plan</text>'
                '</g>'.format(ly=last_bottom + 46))
    return ('<svg id="atlas" xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 {w} {h}" width="100%" role="img" '
            'aria-label="计算机系统架构导航图 · 冯诺依曼数据通路×控制面 · 点击任意项目下钻">'
            '<defs>'
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="10" stdDeviation="18" flood-color="#000" flood-opacity="0.18"/>'
            '</filter>'
            '<marker id="flow-hot-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-hot"/></marker>'
            '<marker id="flow-ctrl-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-ctrl"/></marker>'
            '<marker id="flow-state-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-state"/></marker>'
            '<marker id="flow-opt-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-opt"/></marker>'
            '</defs>{body}</svg>').format(w=_CW, h=total_h, body="".join(body))

# ══════════════════════════════════════════════════════════════════ #
# 多视角导航:每个视角 = 一套分层骨架 + 项目子集映射。
#   lens 1 = 冯诺依曼×控制面(dual-axis,复用 build_svg);
#   lens 2-4 = 竖直分层栈(stack,build_stack_svg 通用渲染)。
#   一个项目可出现在多个视角(各视角是独立剖面),这是正确的。
# ══════════════════════════════════════════════════════════════════ #
LENSES = [
    {"id": "theory", "axis": ("强一致 · CP", "最终一致 · AP"), "label": "计算理论", "group": "计算理论与数学模型", "kind": "stack",
     "kicker": "COMPUTATION THEORY · 正确性与一致性谱",
     "title": "线性一致/共识 → ACID 事务 → 快照隔离 → 顺序日志 → 最终一致 → 计算模型",
     "position": "回答「并发/分布式下,系统给多强的正确性保证」:轴 = 一致性强度谱(强一致 CP 递减到最终一致 AP),越往下可用性/吞吐越高。每个项目按其最强正确性保证归层。",
     "subtitle": "一致性强度 + 计算模型边界 · 从 CP 到 AP · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("th_lin", "线性一致 / 共识 · CP", "多数派 Raft/ZAB · 强一致元数据 · 选主", ["etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "kubernetes", "containerd"], "#a78bfa"),
         ("th_acid", "ACID 事务 · Serializable", "MVCC + WAL · 事务隔离级别 · 快照可见性", ["postgres", "mysql-server", "neo4j", "doris", "hive"], "#0a84ff"),
         ("th_snap", "快照隔离 / 时间旅行", "表级快照 + 乐观提交 · 多版本文件", ["iceberg", "hudi", "orc", "arrow", "parquet"], "#2dd4bf"),
         ("th_log", "顺序日志 / 有序 · ISR", "分区内有序 + 副本同步 · exactly-once", ["kafka", "flink"], "#0a84ff"),
         ("th_eventual", "最终一致 / 弱序 · AP", "异步复制 · 读己所写 · 内存弱保证", ["redis", "rocksdb", "milvus"], "#8a8a90"),
         ("th_compute", "计算模型边界 · 有界↔无界", "批(全量重算)↔ 流(增量+状态)↔ 张量(计算图)", ["hadoop", "spark", "clickhouse", "starrocks", "trino", "duckdb", "pytorch", "tensorflow", "vllm", "ray", "go", "rust", "nginx", "grpc", "ffmpeg", "linux", "openjdk"], "#a78bfa"),
     ]},
    {"id": "hardware", "axis": ("热 · 快 · 近 CPU", "冷 · 慢 · 贴硬件"), "label": "物理底座", "group": "物理底座与体系结构", "kind": "stack",
     "kicker": "HARDWARE / STORAGE HIERARCHY · 物理距离与延迟",
     "title": "内存态 → 本地引擎 → 页+日志 → 表格式/文件 → 分布式/远端 → 内核/硬件",
     "position": "回答「数据与执行离 CPU 多远」:轴 = 物理距离/延迟梯度(热·快·近 CPU 递减到冷·慢·贴硬件)。每个项目按其数据/执行主要驻留的物理层归位。",
     "subtitle": "存储层级(register→RAM→disk→远端)+ 运行时/内核底座 · 同一物理轴 · 点击下钻",
     "flow": "state",
     "tiers": [
         ("hw_mem", "内存态 · In-Memory", "纯内存结构 · 微秒级 · 断电即失", ["redis", "milvus", "vllm"], "#2dd4bf"),
         ("hw_local", "本地引擎 · Local Engine", "内存+本地盘 · LSM/向量化 · 单机", ["rocksdb", "duckdb", "clickhouse"], "#0a84ff"),
         ("hw_page", "页 + 日志 · Page & WAL", "缓冲页 + 预写日志 · 持久单机", ["postgres", "mysql-server", "neo4j"], "#a78bfa"),
         ("hw_table", "表格式 / 列存文件", "不可变文件 + 元数据 · 对象存储之上", ["iceberg", "hudi", "orc", "parquet", "arrow", "doris", "starrocks", "trino", "hive"], "#2dd4bf"),
         ("hw_dist", "分布式 / 远端", "多副本分布式文件 · 顺序日志 · 网络访问", ["hadoop", "kafka", "etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "spark", "flink"], "#8a8a90"),
         ("hw_kernel", "运行时 / 内核 / 硬件", "语言运行时 · GC · 系统调用 · cgroup 隔离 · GPU", ["go", "rust", "openjdk", "linux", "kubernetes", "containerd", "nginx", "grpc", "ffmpeg", "pytorch", "tensorflow", "ray"], "#8a8a90"),
     ]},
    {"id": "system", "axis": ("高层抽象 · 声明", "底层实现 · 机器"), "label": "系统抽象", "group": "系统抽象与工程实现", "kind": "stack",
     "kicker": "SYSTEM ABSTRACTION · 抽象层级",
     "title": "接口/协议 → 计算/算子引擎 → 核心数据结构 → 存储/持久化 → 运行时/内核",
     "position": "回答「一个系统从声明式抽象到机器实现怎样分层」:轴 = 抽象度(高层声明递减到贴机器实现)。每个项目按其最能代表的抽象层归位——同一物理位置的项目抽象度可不同。",
     "subtitle": "从接口/协议到运行时的工程抽象栈 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("sy_api", "接口 / 协议 · Interface", "SQL/API · RPC · HTTP · 声明式编排契约", ["grpc", "nginx", "kubernetes", "trino"], "#0a84ff"),
         ("sy_engine", "计算 / 算子引擎 · Engine", "查询规划 · 向量化算子 · DAG · 训练/推理图", ["spark", "flink", "doris", "clickhouse", "starrocks", "duckdb", "pytorch", "tensorflow", "vllm", "ray", "hive"], "#a78bfa"),
         ("sy_ds", "核心数据结构 · Structure", "LSM / B树 / 列式 / 图 / 向量 / 跳表", ["rocksdb", "postgres", "mysql-server", "neo4j", "milvus", "redis", "orc", "parquet", "arrow"], "#0a84ff"),
         ("sy_store", "存储 / 持久化 · Persistence", "日志段 · 表格式 · 分布式文件 · 副本", ["kafka", "iceberg", "hudi", "hadoop", "etcd", "zookeeper", "hashicorp-raft", "etcd-raft"], "#2dd4bf"),
         ("sy_rt", "运行时 / 内核 · Machine", "语言运行时 · GC · 调度 · 系统调用 · 容器", ["go", "rust", "openjdk", "linux", "containerd", "ffmpeg"], "#8a8a90"),
     ]},
    {"id": "workload", "axis": ("数据入口 · 上游", "结果产出 / 底座 · 下游"), "label": "工作负载", "group": "工作负载与领域范式", "kind": "stack",
     "kicker": "WORKLOAD PIPELINE · 数据/负载处理流水",
     "title": "采集/接入 → 计算/训练 → 查询/推理 → 协调/编排 → 运行时底座",
     "position": "回答「一类负载(大数据/AI/在线服务)怎样从入口流到产出」:轴 = 处理流水位置(上游数据入口递进到下游产出/底座)。每个项目按其在负载流水中承担的环节归位。",
     "subtitle": "大数据 + AI + 云原生负载的统一处理流水 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("wl_ingest", "采集 / 接入 · Ingest", "日志总线 · 网关 · RPC · 编解码 · 向量库", ["kafka", "nginx", "grpc", "ffmpeg", "milvus"], "#0a84ff"),
         ("wl_compute", "计算 / 训练 · Compute", "批流计算 DAG · 分布式训练 · shuffle", ["spark", "flink", "hadoop", "pytorch", "tensorflow", "ray"], "#a78bfa"),
         ("wl_query", "查询 / 推理 · Serve", "MPP 查询 · 向量化 · 联邦 · 高吞吐推理", ["doris", "clickhouse", "starrocks", "trino", "duckdb", "vllm", "hive"], "#0a84ff"),
         ("wl_coord", "协调 / 编排 · Coordinate", "元数据 · 选主 · 容器编排 · 表格式治理", ["etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "kubernetes", "containerd", "iceberg", "hudi", "orc", "arrow", "parquet"], "#8a8a90"),
         ("wl_state", "状态 / 底座 · Substrate", "内存/持久状态后端 · 语言运行时 · 内核", ["redis", "rocksdb", "postgres", "mysql-server", "neo4j", "go", "rust", "openjdk", "linux"], "#2dd4bf"),
     ]},
]


# ── 专题视角(一级导航第二模式):6 大跨项目专题,与项目视角并行、不混。──
# 每主题:id / 标题 / 核心一句 / 3 图解点标题 / 相关项目 key(下钻目标,须 ∈ META)。
# 产物 = topics/<id>/index.html 轻量综合页。本 session 交付导航 + 跳转骨架。
TOPICS = [
    {"id": "consensus", "title": "Distributed Consensus & Replication", "accent": "#0a84ff",
     "core": "日志复制 + 多数派仲裁,实现多副本强一致;向上支撑一致性频谱(线性→最终)的选型;复制拓扑(主从/多主/无主)选型详见系统视角 · 复制策略。",
     "dots": ["共识算法:Raft / Multi-Paxos / ZAB 选举 · 日志 · 成员变更", "一致性频谱:线性一致→顺序一致→最终一致的强度权衡", "复制拓扑选型(主从/多主/无主)详见系统视角 · 复制策略"],
     "projects": ["etcd", "etcd-raft", "hashicorp-raft", "zookeeper", "kafka", "postgres", "clickhouse", "redis"]},
    {"id": "transaction", "title": "Transactions & Concurrency Control", "accent": "#a78bfa",
     "core": "时间戳与锁管理,保障并发隔离性。",
     "dots": ["MVCC 快照可见性判定(ID 与时间戳不等关系)", "Percolator 两阶段提交(Primary 锁为仲裁点)", "OCC 验证阶段读写集冲突检测"],
     "projects": ["postgres", "mysql-server"]},
    {"id": "storage", "title": "Storage Engine & Data Layout", "accent": "#2dd4bf",
     "core": "适配磁盘 / SSD 的读写放大控制。",
     "dots": ["LSM Compaction 写放大路径与 L0 停顿根因", "B-link tree 无锁页分裂(兄弟指针)", "列存压缩管线及 SIMD 下推"],
     "projects": ["rocksdb", "clickhouse", "doris"]},
    {"id": "query", "title": "Query Optimization & Execution", "accent": "#0a84ff",
     "core": "搜索最优计划并生成 CPU 密集指令。",
     "dots": ["Join Reorder 自底向上动态规划", "向量化列批执行(RecordBatch + SIMD)", "表达式树 JIT 编译为 IR"],
     "projects": ["doris", "trino", "duckdb", "starrocks"]},
    {"id": "netio", "title": "High-Performance Network I/O", "accent": "#e0742a",
     "core": "零拷贝传输 + 跨语言协议治理。",
     "dots": ["DPDK 用户态 DMA 与 mbuf 循环", "序列化兼容性(Protobuf 标签 vs FlatBuffers 偏移)", "gRPC HTTP/2 流复用与流控 · Sidecar 协议劫持治理"],
     "projects": ["grpc", "nginx"]},
    {"id": "osmem", "title": "OS Memory & Scheduling", "accent": "#8a8a90",
     "core": "地址虚拟化与物理资源隔离。",
     "dots": ["缺页处理 TLB 命中 / 未命中路径", "伙伴系统(大块)+ Slab(小对象)分配链路", "cgroup High/Max 水位线与 OOM 触发状态机"],
     "projects": ["linux"]},
]


# ── 关系视角(一级导航第 3-5 模式):非技术切面,实体+边关系图。──
# 每模式:core/insight 一句 + groups[{label, entities[{name, kind, note, proj?}]}] + relations 图例。
# proj = 关联项目 key(∈META,可下钻);无 proj = 纯外部实体(叶子)。事实按公开常识核实,宁缺勿错。
INDUSTRY = {
    "core": "技术是商业变现与资本推动的产物。",
    "insight": "看清资本推手 —— 为何某些技术突然爆火,或随大厂战略调整走向衰落。",
    "accent": "#e0742a",
    "groups": [
        {"label": "科技巨头 · 开源 + 云托管", "entities": [
            {"name": "Google", "kind": "巨头", "edge": "开源并主导,云托管变现", "projs": ["kubernetes", "tensorflow", "go", "grpc"]},
            {"name": "Meta", "kind": "巨头", "edge": "开源主导(AI/存储)", "projs": ["pytorch", "rocksdb"]},
            {"name": "LinkedIn", "kind": "巨头", "edge": "内部孵化后开源", "projs": ["kafka"]},
            {"name": "Yahoo / 社区", "kind": "巨头", "edge": "Hadoop 生态孵化", "projs": ["hadoop", "zookeeper"]},
        ]},
        {"label": "商业化公司 · 开源变现", "entities": [
            {"name": "Confluent", "kind": "商业化", "edge": "Kafka 主创创立(2014)· 托管变现", "projs": ["kafka"]},
            {"name": "Databricks", "kind": "商业化", "edge": "Spark 母公司 · 收购 Tabular(Iceberg)", "projs": ["spark", "iceberg"]},
            {"name": "ClickHouse Inc. / Yandex", "kind": "商业化", "edge": "Yandex 孵化 → 独立商业化", "projs": ["clickhouse"]},
            {"name": "Redis Ltd.", "kind": "商业化", "edge": "商业化 + 2024 协议变更(争议)", "projs": ["redis"]},
            {"name": "Neo4j / Zilliz / StarRocks Inc.", "kind": "商业化", "edge": "各自开源项目背后公司", "projs": ["neo4j", "milvus", "starrocks"]},
            {"name": "Onehouse / 社区", "kind": "商业化", "edge": "Hudi 商业化;DuckDB Labs 独立", "projs": ["hudi", "duckdb"]},
        ]},
        {"label": "创投基金 · 资本推手(投资关系)", "entities": [
            {"name": "a16z", "kind": "VC", "edge": "投资 Databricks 等基础软件(非拥有项目)", "projs": []},
            {"name": "Benchmark", "kind": "VC", "edge": "早期投资 Confluent 等(非拥有项目)", "projs": []},
        ]},
        {"label": "其他主体 · 厂商 / 社区 / 基金会", "entities": [
            {"name": "Oracle", "kind": "厂商", "edge": "维护(收购自 Sun/MySQL AB)", "projs": ["mysql-server", "openjdk"]},
            {"name": "F5 / Starburst / Ververica", "kind": "厂商", "edge": "各自商业化(Nginx / Trino / Flink)", "projs": ["nginx", "trino", "flink"]},
            {"name": "Anyscale / Rust 基金会", "kind": "厂商/基金会", "edge": "Ray 母公司;Rust 基金会治理", "projs": ["ray", "rust"]},
            {"name": "社区 / 基金会驱动", "kind": "社区", "edge": "无单一商业主体,社区或基金会主导",
             "projs": ["postgres", "linux", "etcd", "etcd-raft", "hashicorp-raft", "containerd", "arrow", "orc", "ffmpeg", "vllm", "doris"]},
        ]},
    ],
    "relations": [("孵化 / 开源", "own"), ("收购", "acquire"), ("投资", "invest"), ("云服务托管", "host"), ("协议变更", "license")],
}
STANDARDS = {
    "core": "技术生态的秩序、规范与治理结构。",
    "insight": "标准是最大公约数 —— 理解标准就理解不同底层技术为何能互操作;基金会托管决定项目的中立性与存续。",
    "accent": "#0a84ff",
    "groups": [
        {"label": "开源基金会 · 托管治理", "entities": [
            {"name": "CNCF", "kind": "基金会", "edge": "托管毕业/孵化项目 · 中立治理",
             "projs": ["kubernetes", "etcd", "containerd"]},
            {"name": "Apache Software Foundation", "kind": "基金会", "edge": "顶级项目托管 · Apache-2.0 · PMC 治理",
             "projs": ["kafka", "spark", "flink", "iceberg", "hudi", "hadoop", "zookeeper", "orc", "doris", "arrow"]},
            {"name": "Linux Foundation", "kind": "基金会", "edge": "托管内核 + 基础设施 · GPL/多协议",
             "projs": ["linux"]},
            {"name": "厂商主导 / 独立治理", "kind": "非基金会", "edge": "由公司或个人主导,未入中立基金会",
             "projs": ["redis", "rocksdb", "clickhouse", "starrocks", "duckdb", "milvus", "neo4j", "pytorch", "tensorflow", "vllm", "ray", "grpc", "nginx", "mysql-server", "postgres", "go", "rust", "ffmpeg", "hashicorp-raft", "etcd-raft", "openjdk"]},
        ]},
        {"label": "标准化组织 · 规范制定", "entities": [
            {"name": "IETF", "kind": "标准组织", "edge": "制定 HTTP/1.1·HTTP/2·HTTP/3 RFC(gRPC/Nginx 依赖)",
             "projs": ["grpc", "nginx"]},
            {"name": "ISO / ANSI", "kind": "标准组织", "edge": "制定 SQL 标准(各关系/分析库实现子集)",
             "projs": ["postgres", "mysql-server", "trino", "duckdb", "doris", "clickhouse", "starrocks"]},
            {"name": "POSIX / IEEE", "kind": "标准组织", "edge": "制定系统调用/文件系统接口标准",
             "projs": ["linux"]},
        ]},
        {"label": "关键规范 · RFC / Spec / 论文", "entities": [
            {"name": "Raft 论文 (2014)", "kind": "规范", "edge": "定义共识算法(多个实现衍生自它)",
             "projs": ["etcd-raft", "hashicorp-raft", "etcd"]},
            {"name": "Paxos / ZAB", "kind": "规范", "edge": "早期共识协议(ZooKeeper 用 ZAB)",
             "projs": ["zookeeper"]},
            {"name": "Protobuf / Arrow 列格式", "kind": "规范", "edge": "跨语言序列化 / 内存列存开放规范",
             "projs": ["grpc", "arrow"]},
            {"name": "Parquet / ORC 文件格式", "kind": "规范", "edge": "开放列存文件格式(表格式之下)",
             "projs": ["orc", "iceberg", "hudi"]},
        ]},
    ],
    "relations": [("制定", "author"), ("托管", "host"), ("兼容 / 实现", "compat"), ("衍生", "derive")],
}
PEOPLE = {
    "core": "一切技术皆由具体的人、师承关系和学术学派演化而来。",
    "insight": "技术有'基因'和'性格' —— 追踪大牛流动与学派演进,可预测新技术的设计哲学。",
    "accent": "#a78bfa",
    "groups": [
        {"label": "顶级实验室 · 学派源头", "entities": [
            {"name": "贝尔实验室", "kind": "实验室", "edge": "Unix/C 诞生 → 内核与语言哲学", "projs": ["linux", "go", "rust"]},
            {"name": "UC Berkeley (AMPLab/RISELab)", "kind": "实验室", "edge": "Spark/Ray 学术源头", "projs": ["spark", "ray"]},
            {"name": "Google Brain / DeepMind", "kind": "实验室", "edge": "深度学习框架与 MapReduce 源头", "projs": ["tensorflow", "hadoop"]},
        ]},
        {"label": "图灵奖 · 理论奠基", "entities": [
            {"name": "Leslie Lamport", "kind": "图灵奖", "edge": "Paxos/逻辑时钟 → 共识理论奠基", "projs": ["etcd-raft", "zookeeper", "hashicorp-raft"]},
            {"name": "Thompson / Ritchie", "kind": "图灵奖", "edge": "Unix/C → 内核与系统语言哲学", "projs": ["linux", "go"]},
            {"name": "Michael Stonebraker", "kind": "图灵奖", "edge": "关系/列存数据库理论(Postgres 之父)", "projs": ["postgres"]},
        ]},
        {"label": "核心 Maintainer · 理念继承", "entities": [
            {"name": "Linus Torvalds", "kind": "Maintainer", "edge": "创建并维护 Linux / Git", "projs": ["linux"]},
            {"name": "Jay Kreps", "kind": "Maintainer", "edge": "Kafka 主创 → 创立 Confluent", "projs": ["kafka"]},
            {"name": "Jeff Dean / Sanjay Ghemawat", "kind": "Maintainer", "edge": "MapReduce → TensorFlow 谱系", "projs": ["tensorflow", "hadoop"]},
            {"name": "Ongaro / Ousterhout", "kind": "Maintainer", "edge": "Raft 作者 → 可理解的共识", "projs": ["etcd-raft", "etcd"]},
        ]},
        {"label": "学派 / 社区谱系", "entities": [
            {"name": "数据库学派 (Berkeley/Wisconsin)", "kind": "学派", "edge": "关系/列存/分析引擎理念继承", "projs": ["mysql-server", "clickhouse", "doris", "starrocks", "trino", "duckdb", "orc", "parquet", "arrow"]},
            {"name": "分布式系统学派", "kind": "学派", "edge": "共识/协调/编排理念继承", "projs": ["zookeeper", "hashicorp-raft", "kubernetes", "containerd", "flink"]},
            {"name": "存储引擎学派 (LSM/图/向量)", "kind": "学派", "edge": "RocksDB LSM → 多引擎;图/向量特化", "projs": ["rocksdb", "redis", "neo4j", "milvus", "hudi", "iceberg"]},
            {"name": "系统 / AI 社区", "kind": "社区", "edge": "多人协作,无单一奠基者", "projs": ["nginx", "grpc", "rust", "ffmpeg", "pytorch", "vllm", "ray", "openjdk"]},
        ]},
    ],
    "relations": [("导师 / 学生", "mentor"), ("前同事", "colleague"), ("理念继承", "lineage")],
}


def build_stack_svg(lens, projects):
    """总线脊接线图:左侧层号栅栏 + 中央竖向总线脊,每层模块经端口接入总线,
    信号沿脊自上而下逐层步进。类 OSI/系统总线工程图——有接线、有端口、有方向。"""
    global LAYER_ITEMS, LAYER_COLOR
    tiers = lens["tiers"]
    by_key = {p["key"]: p for p in projects}
    LAYER_ITEMS = {tk: [by_key[k] for k in keys if k in by_key] for tk, _t, _s, keys, _c in tiers}
    LAYER_COLOR = {tk: c for tk, _t, _s, _keys, c in tiers}

    AXIS_X = 40                       # 左序轴(展示本视角的排序原理)
    GUT_X = 92                         # 层号/层名栏
    LANE_X, LANE_W = 300, 858          # 模块道(层内组件)
    Y1, PAD = 232, 18                  # VGAP=0:层紧贴堆叠 = 栈,不是列表
    NODEH, ROWG, NG = _NODEH, _ROWG, _NG

    def _cols(n):                     # 均衡列数:≤5 单行,否则分行均摊(6→3×2,8→4×2)
        if n <= 5:
            return max(1, n)
        r = -(-n // 5)
        return -(-n // r)
    band = {}
    y = Y1
    for tk, _t, _s, keys, _c in tiers:
        mods = [by_key[k] for k in keys if k in by_key]
        n = len(mods)
        cols = _cols(n)
        rows = max(1, -(-n // cols))
        grid_h = rows * (NODEH + ROWG) - ROWG
        h = max(64, grid_h) + PAD * 2
        band[tk] = (y, h, cols, mods)
        y += h                        # 紧贴:无间隙
    stack_top, stack_bot = Y1, y
    total_h = stack_bot + 108

    body = ['<rect class="frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="28"/>'.format(
        x=_FRAME_X, y=_FRAME_Y, w=_FRAME_W, h=total_h - 2 * _FRAME_Y)]
    body.append('<text class="map-kicker" x="72" y="84">%s</text>' % _esc(lens["kicker"]))
    body.append('<text class="map-title" x="72" y="126">%s</text>' % _esc(lens["title"]))
    body.append('<text class="map-subtitle" x="72" y="156">%s</text>' % _esc(lens["subtitle"]))
    if lens.get("position"):
        body.append('<rect class="lens-pos-bg" x="68" y="180" width="1050" height="32" rx="9"/>')
        body.append('<text class="lens-pos" x="86" y="201">%s</text>' % _esc(lens["position"]))

    order = [t[0] for t in tiers]
    centers = {tk: band[tk][0] + band[tk][1] / 2 for tk in order}

    # ── 左序轴:一根竖轴 + 两极标签,显式说明本视角「按什么排序」(架构感来源①:排序原理可见) ──
    axis = lens.get("axis", ("上层 · 近用户", "底层 · 近硬件"))
    body.append('<g class="axis-rail">')
    body.append('<line class="axis-line" x1="{x}" y1="{y1}" x2="{x}" y2="{y2}"/>'.format(x=AXIS_X, y1=stack_top + 8, y2=stack_bot - 8))
    body.append('<text class="axis-pole" x="{x}" y="{y}">{t}</text>'.format(x=AXIS_X, y=stack_top - 6, t=_esc(axis[0])))
    body.append('<text class="axis-pole axis-pole-b" x="{x}" y="{y}">{t}</text>'.format(x=AXIS_X, y=stack_bot + 18, t=_esc(axis[1])))
    # 层间「下层支撑上层」依赖记号:紧贴边界上的小三角(honest 关系,非假数据流)
    body.append('<g class="dep-marks">')
    for a, b in zip(order, order[1:]):
        by = band[b][0]              # 相邻层边界 y
        body.append('<path class="dep-tri" d="M{x1},{y1} L{x2},{y1} L{xm},{y2} Z"/>'.format(
            x1=AXIS_X - 4, x2=AXIS_X + 4, xm=AXIS_X, y1=by - 5, y2=by + 1))
    body.append('</g></g>')

    # 固定卡宽:按 5 列基准算,任意层卡片同尺寸(栅格纪律)
    FIXED_CW = (LANE_W - 4 * NG) / 5
    BAND_X, BAND_W = LANE_X - 24, _FRAME_W - (LANE_X - 24) + _FRAME_X - 24

    # ── 逐层:整幅平台层(紧贴堆叠) · 层号名 · 组件卡 · 右侧留白填角色注 ──
    for i, (tk, ttitle, tsub, _keys, accent) in enumerate(tiers):
        yy, h, cols, mods = band[tk]
        cy = centers[tk]
        top = (i == 0)
        bot = (i == len(tiers) - 1)
        # 平台层:整幅宽,accent 微染,层间紧贴(圆角只在最顶/最底外角)
        body.append('<rect class="tier-band" x="{x}" y="{y:.1f}" width="{w}" height="{h:.1f}" rx="0" style="--accent:{c}"/>'.format(
            x=BAND_X, y=yy, w=BAND_W, h=h, c=accent))
        body.append('<rect class="tier-edge" x="{x}" y="{y:.1f}" width="4" height="{h:.1f}" style="--accent:{c}"/>'.format(
            x=BAND_X, y=yy, h=h, c=accent))
        if not bot:
            body.append('<line class="tier-div" x1="{x1}" y1="{y:.1f}" x2="{x2}" y2="{y:.1f}"/>'.format(
                x1=BAND_X, y=yy + h, x2=BAND_X + BAND_W))
        # 层号 + 层名 + 副标(左栏)
        body.append('<text class="layer-num" x="{x}" y="{y:.0f}">{n:02d}</text>'.format(x=GUT_X + 4, y=cy - 5, n=i + 1))
        body.append('<text class="layer-title" x="{x}" y="{y:.0f}">{t}</text>'.format(x=GUT_X + 4, y=cy + 13, t=_esc(_ellip(ttitle, 13))))
        body.append('<text class="layer-sub" x="{x}" y="{y:.0f}">{s}</text>'.format(x=GUT_X + 4, y=cy + 29, s=_esc(_ellip(tsub, 15))))
        # 组件卡:固定卡宽,左对齐栅格
        rows = max(1, -(-len(mods) // cols))
        grid_h = rows * (NODEH + ROWG) - ROWG
        gy0 = yy + (h - grid_h) / 2
        row_right = LANE_X
        for j, m in enumerate(mods):
            r, c = divmod(j, cols)
            nx = LANE_X + c * (FIXED_CW + NG)
            ny = gy0 + r * (NODEH + ROWG)
            row_right = max(row_right, nx + FIXED_CW)
            body.append(_node(m, nx, ny, FIXED_CW, accent, lens_id=lens["id"], lens_label=lens["label"]))
    return ('<svg class="atlas-lens" data-lens="{lid}" xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{lab} 架构视角 · 点击下钻">'
            '<defs>'
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.08"/></filter>'
            '<marker id="flow-hot-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-hot"/></marker>'
            '<marker id="flow-ctrl-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-ctrl"/></marker>'
            '<marker id="flow-state-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-state"/></marker>'
            '<marker id="flow-opt-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" class="arrow-opt"/></marker>'
            '</defs>{body}</svg>').format(lid=lens["id"], lab=_esc(lens["label"]), w=_CW, h=total_h, body="".join(body))


def build_all_lenses(projects):
    """渲染全部视角 SVG,包进可切换容器;首个默认显示。"""
    out = []
    for i, lens in enumerate(LENSES):
        svg = build_svg(projects) if lens["kind"] == "dual" else build_stack_svg(lens, projects)
        out.append('<div class="lens-view{act}" data-lens="{lid}">{svg}</div>'.format(
            act=" on" if i == 0 else "", lid=lens["id"], svg=svg))
    return "".join(out)


def build_lens_switch():
    """顶栏 segmented 视角切换器:四维各一张架构图,扁平 4 按钮(按钮 = 维名)。"""
    DIM_ORDER = ["计算理论与数学模型", "物理底座与体系结构", "系统抽象与工程实现", "工作负载与领域范式"]
    ordered = sorted(LENSES, key=lambda l: DIM_ORDER.index(l["group"]) if l.get("group") in DIM_ORDER else 99)
    segs = []
    for i, l in enumerate(ordered):
        segs.append('<button class="lens-seg{act}" data-lens="{lid}" role="tab">{lab}</button>'.format(
            act=" on" if i == 0 else "", lid=l["id"], lab=_esc(l["label"])))
    return '<div class="lens-switch" role="tablist" aria-label="架构视角">%s</div>' % "".join(segs)


def build_topics_switch():
    """专题视角切换器:6 大专题 seg,点击滚动/高亮对应主题卡。与项目视角并行。"""
    segs = []
    for i, t in enumerate(TOPICS):
        segs.append('<button class="topic-seg{act}" data-topic="{tid}" role="tab">{lab}</button>'.format(
            act=" on" if i == 0 else "", tid=t["id"], lab=_esc(t["title"])))
    return '<div class="topic-switch" role="tablist" aria-label="主题专题">%s</div>' % "".join(segs)


def _inline_hero_svg(svg_path):
    """把 design/ 下的预览图以【内联 <svg>】方式嵌入门户卡片(而非 base64 <img>)。
    内联后 SVG 元素进入主文档 DOM,才能被 :root[data-theme] 的主题 CSS 命中,
    从而让画布底色 / 主文字色跟随深浅主题切换(彩色语义保留)。不修改 SVG 源文件。"""
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return ""
    # 去掉 XML 声明 / DOCTYPE / 注释头,只保留 <svg> 起
    i = txt.find("<svg")
    if i < 0:
        return ""
    txt = txt[i:]
    # 给根 <svg> 打上 class,供门户 CSS 选择器命中;补 aria-hidden 降噪
    txt = re.sub(r'<svg\b', '<svg class="tc-hero-svg" aria-hidden="true" preserveAspectRatio="xMidYMid meet"', txt, count=1)
    # 把中性色值(画布底/白/主次文字/浅灰/中性线)就地替换为 CSS 变量,
    # 使其随深浅主题切换;彩色语义(绿蓝紫橙等)不在表内 → 原样保留。
    # 用变量而非 attribute selector,渲染 100% 可靠,不受色值大小写/变体影响。
    # 注意大小写不敏感匹配,兼容 #FBFBFD / #FFF 等写法。
    _neutral = [
        # (正则片段, 变量名) —— 底色类
        (r'#fbfbfd', 'var(--hero-bg)'),
        (r'#ffffff', 'var(--hero-bg)'),
        (r'#fff\b',  'var(--hero-bg)'),
        # 主文字 / 纯黑
        (r'#1d1d1f', 'var(--hero-ink)'),
        (r'#000000', 'var(--hero-ink)'),
        (r'#000\b',  'var(--hero-ink)'),
        # 次文字
        (r'#3a3a3c', 'var(--hero-ink2)'),
        (r'#6e6e73', 'var(--hero-ink2)'),
        # 浅灰弱文字
        (r'#a1a1a6', 'var(--hero-ink3)'),
        # 中性描边 / 分隔线
        (r'#d9dde4', 'var(--hero-line)'),
        (r'#eceef1', 'var(--hero-line)'),
        (r'#e4e7ec', 'var(--hero-line)'),
        (r'#e2e2e8', 'var(--hero-line)'),
        (r'#eef0f3', 'var(--hero-line)'),
        # 中性分区底(冷灰 panel)
        (r'#f6f7f9', 'var(--hero-panel)'),
        (r'#4a4a4f', 'var(--hero-ink2)'),
        (r'#8a8a8f', 'var(--hero-ink3)'),
        # 语义分区:蓝
        (r'#eaf1fb', 'var(--hero-blue-bg)'),
        (r'#c6d9f2', 'var(--hero-blue-line)'),
        (r'#20375e', 'var(--hero-blue-ink)'),
        # 语义分区:绿 / 青(浅绿系底与描边)
        (r'#eaf6f0', 'var(--hero-green-bg)'),
        (r'#e3f1ea', 'var(--hero-green-bg)'),
        (r'#dcede4', 'var(--hero-green-bg)'),
        (r'#f2f8f5', 'var(--hero-green-bg)'),
        (r'#eef7f2', 'var(--hero-green-bg)'),
        (r'#d7efe2', 'var(--hero-green-bg)'),
        (r'#e3f4f4', 'var(--hero-green-bg)'),
        (r'#bfe3d1', 'var(--hero-green-line)'),
        (r'#a9d6c0', 'var(--hero-green-line)'),
        (r'#9dceb4', 'var(--hero-green-line)'),
        (r'#c9e6d7', 'var(--hero-green-line)'),
        (r'#9ed3b8', 'var(--hero-green-line)'),
        (r'#bfe3e4', 'var(--hero-green-line)'),
        (r'#2f6b4e', 'var(--hero-green-ink)'),
        (r'#5a9078', 'var(--hero-green-ink2)'),
        (r'#8fb9a4', 'var(--hero-green-ink2)'),
        # 语义分区:紫
        (r'#f4eefb', 'var(--hero-purple-bg)'),
        (r'#dcc9ef', 'var(--hero-purple-line)'),
        (r'#6f3ea8', 'var(--hero-purple-ink)'),
        # 语义分区:橙
        (r'#fbf3e2', 'var(--hero-amber-bg)'),
        (r'#fdf6e8', 'var(--hero-amber-bg)'),
        (r'#ecd6a8', 'var(--hero-amber-line)'),
        (r'#e6ce9a', 'var(--hero-amber-line)'),
        (r'#8a6417', 'var(--hero-amber-ink)'),
        (r'#a98a3a', 'var(--hero-amber-ink2)'),
        # 语义分区:红
        (r'#fbeceb', 'var(--hero-red-bg)'),
        (r'#fbeee9', 'var(--hero-red-bg)'),
        (r'#fdecea', 'var(--hero-red-bg)'),
        (r'#e8b7b1', 'var(--hero-red-line)'),
        (r'#eccabb', 'var(--hero-red-line)'),
        (r'#f3c9c3', 'var(--hero-red-line)'),
        # ── 补:basic/principles 的 design 图用到的表外浅底/浅描边 ──
        # 之前遗漏导致这两视角导航卡缩略图在深色主题下露白(色不随主题)。
        # 按色相 + 亮度自动归类(仅浅色 L>=0.82 作为 bg/line;中深彩色前景保留原样)。
        (r'#fdf3e0', 'var(--hero-amber-bg)'),
        (r'#fbf1dc', 'var(--hero-amber-bg)'),
        (r'#fbeee2', 'var(--hero-amber-bg)'),
        (r'#fdf4e3', 'var(--hero-amber-bg)'),
        (r'#fff7e8', 'var(--hero-amber-bg)'),
        (r'#fdf6ea', 'var(--hero-amber-bg)'),
        (r'#fefaf0', 'var(--hero-amber-bg)'),
        (r'#e7f4ee', 'var(--hero-green-bg)'),
        (r'#e6f4ec', 'var(--hero-green-bg)'),
        (r'#e3f4ec', 'var(--hero-green-bg)'),
        (r'#e5f3ec', 'var(--hero-green-bg)'),
        (r'#e7f5ee', 'var(--hero-green-bg)'),
        (r'#eafaf2', 'var(--hero-green-bg)'),
        (r'#d7efe1', 'var(--hero-green-line)'),
        (r'#bfe6d3', 'var(--hero-green-line)'),
        (r'#f2f7ff', 'var(--hero-blue-bg)'),
        (r'#e4f4f4', 'var(--hero-blue-bg)'),
        (r'#f6f9fe', 'var(--hero-blue-bg)'),
        (r'#f2f0fa', 'var(--hero-blue-bg)'),
        (r'#dbe8fa', 'var(--hero-blue-line)'),
        (r'#dbe6f7', 'var(--hero-blue-line)'),
        (r'#fbe6e3', 'var(--hero-red-bg)'),
        (r'#fbecea', 'var(--hero-red-bg)'),
        (r'#f7ecea', 'var(--hero-red-bg)'),
        (r'#eec5c0', 'var(--hero-red-line)'),
        (r'#f0ebfb', 'var(--hero-purple-bg)'),
        (r'#d3c6ee', 'var(--hero-purple-line)'),
        (r'#f4f4f6', 'var(--hero-panel)'),
        (r'#d7d7dd', 'var(--hero-line)'),
    ]
    for pat, var in _neutral:
        txt = re.sub(pat, var, txt, flags=re.IGNORECASE)
    return '<span class="tc-hero">%s</span>' % txt


def _topic_hero(tid):
    """主题卡顶部预览图:取该主题 design/ 下的 *00生态架构.svg(核心代表图),内联 <svg>。
    找不到返回 ''(卡片降级为无图)。"""
    import glob as _glob
    hits = _glob.glob(os.path.join(ROOT, "topics", tid, "design", "*00生态架构*.svg"))
    if not hits:
        hits = _glob.glob(os.path.join(ROOT, "topics", tid, "design", "*.svg"))
    if not hits:
        return ""
    return _inline_hero_svg(sorted(hits)[0])


def build_topics_cards():
    """专题视角内容区:6 大专题卡网格,顶部核心生态图预览,点击下钻到 topics/<id>/index.html。"""
    cards = []
    for t in TOPICS:
        dots = "".join('<li class="tc-dot">{d}</li>'.format(d=_esc(d)) for d in t["dots"])
        chips = "".join('<span class="tc-chip">{n}</span>'.format(n=_esc(META.get(k, {}).get("name", k)))
                        for k in t["projects"])
        hero = _topic_hero(t["id"])
        cards.append(
            '<a class="topic-card" id="tc-{tid}" href="topics/{tid}/index.html" style="--accent:{c}">'
            '{hero}'
            '<span class="tc-body">'
            '<span class="tc-head"><span class="tc-title">{title}</span></span>'
            '<span class="tc-core">{core}</span>'
            '<ul class="tc-dots">{dots}</ul>'
            '<span class="tc-projs">{chips}</span>'
            '</span>'
            '</a>'.format(tid=t["id"], c=t["accent"], title=_esc(t["title"]),
                          core=_esc(t["core"]), dots=dots, chips=chips, hero=hero))
    note = ('<p class="topics-note">主题 = <b>跨项目专题深剖</b>(一个机制横穿多个项目,带图解点);'
            '区别于「技术项目视角」里按理论轴给项目归位的 lens。</p>')
    return note + '<div class="topics-grid">%s</div>' % "".join(cards)


# ── 基础原理视角(一级导航·技术剖面第 3 模式):数据结构与算法基本功。──
# 内容真源在 basic/(独立生成器 basic/gen.py),此处只做门户卡片 + 下钻跳转。
def _basic_hero(slug):
    """基础条目卡顶部预览图:取 basic/<slug>/design/ 下的 *00* 总览图,内联 <svg>。"""
    import glob as _glob
    hits = _glob.glob(os.path.join(ROOT, "basic", slug, "design", "*00*.svg"))
    if not hits:
        hits = _glob.glob(os.path.join(ROOT, "basic", slug, "design", "*.svg"))
    if not hits:
        return ""
    return _inline_hero_svg(sorted(hits)[0])


def build_basic_cards():
    """基础原理内容区:数据结构 6 + 算法 6,两段卡网格,下钻到 basic/<slug>/index.html。
    条目元数据从 basic/gen.py 的 ITEMS 动态读取,避免双真源。"""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("basic_gen", os.path.join(ROOT, "basic", "gen.py"))
    bg = _ilu.module_from_spec(spec)
    spec.loader.exec_module(bg)
    SECS = [("ds", "数据结构", "线性表 · 哈希 · 树 · 堆 · 图 —— 一切容器的地基"),
            ("algo", "算法", "搜索 · 排序 · 分治 · 回溯 · 动态规划 · 贪心 —— 解题范式")]
    blocks = []
    for cat, title, sub in SECS:
        cards = []
        for it in [x for x in bg.ITEMS if x["cat"] == cat]:
            hero = _basic_hero(it["slug"])
            cards.append(
                '<a class="topic-card" href="basic/{slug}/index.html" style="--accent:{c}">'
                '{hero}'
                '<span class="tc-body">'
                '<span class="tc-head"><span class="tc-title">{cn}</span></span>'
                '<span class="tc-core">{core}</span>'
                '</span>'
                '</a>'.format(slug=it["slug"], c=it.get("color", "#4a7fd0"),
                              cn=_esc(it["cn"]), hero=hero, core=_esc(it.get("core", ""))))
        blocks.append(
            '<h3 class="basic-subhead">{t}<span class="basic-subnote">{s}</span></h3>'
            '<div class="topics-grid">{g}</div>'.format(t=_esc(title), s=_esc(sub), g="".join(cards)))
    note = ('<p class="topics-note">基础原理 = <b>数据结构与算法基本功</b>(核心原理图 + 可运行 Go 实现,'
            '取材 hello-algo 并逐一源码核实);是读懂上层系统源码前的地基。</p>')
    return note + "".join(blocks)


# ── 架构原理视角(一级导航·技术剖面第 4 模式):系统设计模式为何选。──
# 内容真源在 principles/(独立生成器 principles/gen.py),此处只做门户卡片 + 下钻跳转。
def _principle_hero(slug):
    """架构原理卡片顶部预览图:取 principles/<slug>/design/ 下的 *00* 生态架构总图,内联 <svg>。"""
    import glob as _glob
    hits = _glob.glob(os.path.join(ROOT, "principles", slug, "design", "*00*.svg"))
    if not hits:
        hits = _glob.glob(os.path.join(ROOT, "principles", slug, "design", "*.svg"))
    if not hits:
        return ""
    return _inline_hero_svg(sorted(hits)[0])


def build_principles_cards():
    """架构原理内容区:7 张系统设计模式卡,下钻到 principles/<slug>/index.html。
    条目元数据从 principles/gen.py 的 PRINCIPLES 列表动态读取,避免双真源。"""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("principles_gen", os.path.join(ROOT, "principles", "gen.py"))
    pg = _ilu.module_from_spec(spec)
    spec.loader.exec_module(pg)
    cards = []
    for p in pg.PRINCIPLES:
        hero = _principle_hero(p["slug"])
        dots = "".join('<li class="tc-dot">{d}</li>'.format(d=_esc(g["algo"])) for g in p["groups"])
        cards.append(
            '<a class="topic-card" href="principles/{slug}/index.html" style="--accent:{c}">'
            '{hero}'
            '<span class="tc-body">'
            '<span class="tc-head"><span class="tc-title">{cn}</span></span>'
            '<span class="tc-core">{core}</span>'
            '<ul class="tc-dots">{dots}</ul>'
            '</span>'
            '</a>'.format(slug=p["slug"], c=p.get("color", "#4a7fd0"),
                          cn=_esc(p["cn"]), hero=hero, core=_esc(p.get("core", "")), dots=dots))
    note = ('<p class="topics-note">系统视角 = <b>系统设计模式为何选</b>(分片/缓存/限流背压/消息队列/'
            '服务发现/熔断幂等重试,每个模式下的变体都显式点名真实项目做对比);'
            '区别于「专题视角」纵向钻透单个机制在多项目中的实现。</p>')
    return note + '<div class="topics-grid">%s</div>' % "".join(cards)


# ── LLM & Agent 视角(一级导航·技术剖面第 5 模式):整体架构导航图,12 模块下钻。──
# 内容真源在 llm-agent/(独立生成器 llm-agent/gen.py),此处只做门户卡片 + 下钻跳转。
def _agent_hero(slug):
    """Agent 模块卡片顶部预览图:取 llm-agent/<slug>/design/ 下的 *00* 生态架构总图,base64 内联。"""
    import glob as _glob
    hits = _glob.glob(os.path.join(ROOT, "llm-agent", slug, "design", "*00*.svg"))
    if not hits:
        hits = _glob.glob(os.path.join(ROOT, "llm-agent", slug, "design", "*.svg"))
    if not hits:
        return ""
    try:
        with open(sorted(hits)[0], "rb") as f:
            b = base64.b64encode(f.read()).decode("ascii")
        return '<span class="tc-hero"><img src="data:image/svg+xml;base64,{b}" alt="" loading="lazy"/></span>'.format(b=b)
    except OSError:
        return ""


def build_agent_cards():
    """LLM & Agent:渲染一张手绘总架构图 SVG(仿 doris 项目架构导航)。
    图内每个模块框标注 data-tid(=slug)/data-lab;此处解析其坐标,
    在 base64 内联的 <img> 上叠加绝对定位的透明热区 <a>,点击下钻到
    llm-agent/<rel>/index.html。元数据(下钻路径/标题)从 llm-agent/gen.py 动态读取。"""
    import importlib.util as _ilu
    import xml.etree.ElementTree as _ET
    spec = _ilu.spec_from_file_location("llm_gen", os.path.join(ROOT, "llm-agent", "gen.py"))
    lg = _ilu.module_from_spec(spec)
    spec.loader.exec_module(lg)

    by_slug = {t["slug"]: t for t in lg.THEMES}

    svg_path = os.path.join(ROOT, "llm-agent", "design", "LLM_Agent_总架构图.svg")
    with open(svg_path, encoding="utf-8") as f:
        svg_text = f.read()
    # 内联 SVG 源码(非 base64 img),让底色/中性文字随主题变化;
    # 品牌语义色保留。给 <svg> 根标签加 class 以便 CSS 命中内部元素。
    svg_inline = re.sub(r'<svg\b', '<svg class="arch-svg"', svg_text, count=1)
    # ── 主题化:把中性/浅色 tint 填充统一归到语义 class,使深色主题可整体覆盖 ──
    # 1) 背景(全幅底色矩形;宽高随图版本变化,故用正则匹配而非写死尺寸)
    svg_inline = re.sub(
        r'<rect x="0" y="0" width="(\d+)" height="(\d+)" fill="#fbfbfd"\s*/>',
        r'<rect x="0" y="0" width="\1" height="\2" class="ag-bg"/>',
        svg_inline, count=1)
    # 2) 层容器渐变底(agentsBand/proxyBand/trainBand/serveBand/dataBand)→ ag-band
    svg_inline = re.sub(r'fill="url\(#\w+Band\)"', 'class="ag-band"', svg_inline)
    # 3) 纯白卡片框(可下钻/主体白框)→ ag-card(保留其 stroke 供浅色语义,深色由 CSS 覆盖)
    svg_inline = re.sub(r'fill="#ffffff"(\s+stroke="#[0-9a-fA-F]{3,6}")',
                        r'class="ag-card"\1', svg_inline)
    # 4) 其余浅色 tint 小框(标签/机理块,fill 为 #exxxxx/#fxxxxx/#dxxxxx 等浅色)→ ag-tint
    #    仅命中带 stroke 的 rect 填充,避免误伤纯色语义文字。
    _tint_fills = ['#dbe9ff', '#eef5ff', '#f6fbff', '#fff8f2', '#f2fbf6',
                   '#f3e8ff', '#eafcff', '#fff6ef', '#d6f3e5', '#eef6ff',
                   '#fff2e8', '#faf5ff', '#f3eefe', '#f5f0fb',
                   '#fff2f2', '#f2f7ff',
                   # 新版总架构图新增浅底(侧边栏冷灰底/引擎层/飞轮框)
                   '#f8fafc', '#f1f5f9', '#fcf4ff', '#fffcf0']
    for _tf in _tint_fills:
        svg_inline = svg_inline.replace('fill="{}"'.format(_tf), 'class="ag-tint"')
    # 4b) 横切治理带容器底(#f4f4f7 带 stroke)→ ag-band(层容器深色语义,与卡片区分层次)
    svg_inline = svg_inline.replace(
        'fill="#f4f4f7" stroke="#dcdce2"', 'class="ag-band" stroke="#dcdce2"')
    # 5) 中性文字色 → 语义 class(深色主题下变亮)
    svg_inline = svg_inline.replace('fill="#8a8a8e"', 'class="ag-sub"')
    svg_inline = svg_inline.replace('fill="#6e6e73"', 'class="ag-sub"')
    svg_inline = svg_inline.replace('fill="#1d1d1f"', 'class="ag-title"')
    svg_inline = svg_inline.replace('fill="#4b4b52"', 'class="ag-title"')

    # ── 解析热区:带 data-tid 的 <rect>,坐标累加 <g transform=translate> 偏移 ──
    vb = re.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg_text)
    vbw, vbh = float(vb.group(1)), float(vb.group(2))
    root = _ET.fromstring(svg_text)
    hots = []

    def _walk(el, dx, dy):
        m = re.search(r'translate\(\s*([-\d.]+)(?:[,\s]+([-\d.]+))?', el.get("transform") or "")
        if m:
            dx += float(m.group(1))
            if m.group(2):
                dy += float(m.group(2))
        if el.tag.rsplit("}", 1)[-1] == "rect" and el.get("data-tid"):
            hots.append((float(el.get("x", 0)) + dx, float(el.get("y", 0)) + dy,
                         float(el.get("width", 0)), float(el.get("height", 0)),
                         el.get("data-tid"), el.get("data-lab") or ""))
        for c in el:
            _walk(c, dx, dy)
    _walk(root, 0.0, 0.0)

    hot_html = []
    for (x, y, w, h, tid, lab) in hots:
        th = by_slug.get(tid)
        if not th:
            continue
        rel = lg._rel(th) if hasattr(lg, "_rel") else tid
        hot_html.append(
            '<a class="arch-hot" style="left:{lp:.3f}%;top:{tp:.3f}%;width:{wp:.3f}%;height:{hp:.3f}%;--accent:{c}" '
            'href="llm-agent/{rel}/index.html" title="{lab} → {cn}">'
            '<span class="arch-hot-lab">{cn}</span></a>'.format(
                lp=x / vbw * 100, tp=y / vbh * 100, wp=w / vbw * 100, hp=h / vbh * 100,
                c=th.get("color", "#a78bfa"), rel=rel, lab=_esc(lab), cn=_esc(th["cn"])))

    return ('<div class="arch-stage"><div class="arch-canvas">'
            '{svg}'
            '{hots}'
            '</div></div>').format(svg=svg_inline, hots="".join(hot_html))


# ===================================================================== #
#  业务场景下钻:10 类高频业务场景,每个场景一张「核心技术点」架构图子页
#  数据驱动:每个场景 = slug / 中英文名 / 主题色 / 一句定位 / 若干技术点
#  分组(每组 = 组名 + 若干节点,节点含标题+要点)。架构图 SVG 与子页面
#  均由 build_scenario_page 程序化生成,风格统一、自动主题化。
# ===================================================================== #
SCENARIOS = [
    {
        "slug": "ecommerce", "cn": "电商交易", "en": "E-Commerce Transaction",
        "layer": "交易支付层", "color": "#4a7fd0", "color2": "#3a4a63",
        "tagline": "淘宝 / 京东 / 拼多多 —— 从浏览搜索到履约售后的交易主链路,核心是「高并发不超卖、支付强一致、履约可追溯」。",
        "domain": {
            "title": "电商交易架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["浏览搜索", "加购收藏", "下单支付", "履约配送", "售后复购"],
            "mid": {"label": "🏗️ 核心业务域", "blocks": [
                {"t": "用户域", "s": "账户 / 会员 / 权益", "c": "blue"},
                {"t": "商品域", "s": "SPU / SKU / 类目", "c": "green"},
                {"t": "交易域", "s": "订单 / 库存 / 履约", "c": "purple"}]},
            "tech": [
                {"t": "秒杀引擎", "c": "green", "lines": ["多级限流削峰", "Redis 预扣减", "答题打散尖峰"]},
                {"t": "库存中心", "c": "blue", "lines": ["分段库存防热点", "Lua 原子扣减", "预占超时回滚"]},
                {"t": "搜索推荐", "c": "purple", "lines": ["ES 倒排检索", "召回 + 精排", "个性化排序"]},
                {"t": "分布式事务", "c": "pink", "lines": ["事务消息最终一致", "TCC / Saga 补偿", "本地消息表"]}],
            "store": ["MySQL 分库分表", "Redis Cluster", "Elasticsearch", "RocketMQ", "CDN + OSS"],
            "metrics": [
                "🔑 关键指标：峰值 QPS 10 万+ | 零超卖严格一致 | 支付成功率 99.999% | 秒杀扣减 <50ms",
                "核心模式：读多写少动静分离 | 强一致收敛到库存与资金,其余最终一致 + 对账"],
        },
    },
    {
        "slug": "social", "cn": "社交网络", "en": "Social Network",
        "layer": "社交互动层", "color": "#8a5cae", "color2": "#5a3a7a",
        "tagline": "微信 / 微博 / 小红书 —— 从关系链到内容分发的社交主链路,核心是「关系链海量存储、Feed 高效分发、消息必达」。",
        "domain": {
            "title": "社交网络架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["注册建号", "关系链", "内容发布", "Feed 分发", "互动社交", "社群运营", "商业变现"],
            "mid": {"label": "🏗️ 核心业务域", "blocks": [
                {"t": "关系链域", "s": "关注 / 好友 / 图谱", "c": "purple"},
                {"t": "内容域", "s": "图文 / 视频 / 话题", "c": "blue"},
                {"t": "分发域", "s": "Feed / 推荐 / 触达", "c": "green"}]},
            "tech": [
                {"t": "Feed 流架构", "c": "purple", "lines": ["推拉结合模式", "大 V 读扩散", "普通用户写扩散"]},
                {"t": "IM 即时通讯", "c": "blue", "lines": ["长连接网关", "消息必达 ACK", "多端同步"]},
                {"t": "推荐系统", "c": "green", "lines": ["多路召回", "精排 + 重排", "实时特征"]},
                {"t": "图数据库", "c": "pink", "lines": ["关系链存储", "多跳查询", "共同好友推荐"]}],
            "store": ["Neo4j 图谱", "HBase 消息", "Redis 计数", "Kafka 管道", "OSS + CDN"],
            "metrics": [
                "🔑 关键指标：DAU 亿级 | 关系链百亿边 | 消息到达 99.999% | Feed 拉取 <100ms",
                "核心模式：推拉结合 Feed | 大 V 写扩散优化 | 长连接海量维持"],
        },
    },

    {
        "slug": "video", "cn": "短视频 / 直播", "en": "Short Video & Live Streaming",
        "layer": "内容娱乐层", "color": "#8a5cae", "color2": "#5a3a7a",
        "tagline": "抖音 / 快手 / B站 —— 从创作上传到推荐播放的内容主链路,核心是「海量转码、毫秒推荐、低延迟直播」。",
        "domain": {
            "title": "短视频 / 直播架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["创作拍摄", "上传转码", "AI 审核", "推荐分发", "播放互动", "变现"],
            "mid": {"label": "🎬 直播核心链路", "blocks": [
                {"t": "推流 RTMP", "s": "主播端采集编码", "c": "pink"},
                {"t": "转码集群", "s": "多码率自适应", "c": "blue"},
                {"t": "CDN 边缘", "s": "就近分发", "c": "green"},
                {"t": "拉流 HLS", "s": "观众端播放", "c": "purple"}]},
            "tech": [
                {"t": "视频转码引擎", "c": "pink", "lines": ["FFmpeg + GPU", "多码率转码", "智能封面抽帧"]},
                {"t": "推荐引擎", "c": "blue", "lines": ["实时特征", "多路召回精排", "冷启动探索"]},
                {"t": "CDN 边缘", "c": "green", "lines": ["边缘缓存", "P2P 加速", "首屏秒开"]},
                {"t": "内容安全 AI", "c": "purple", "lines": ["图像识别", "语音转文字审核", "先审后发"]}],
            "store": ["OSS 视频", "Redis 计数器", "Kafka 管道", "Flink 实时", "GPU 转码集群"],
            "metrics":[
                "🔑 关键指标：日活 7 亿 | PB 级存储 | 直播延迟 <1s | 首屏秒开 99%",
                "核心模式：转码降本 + CDN 分发 | 推荐驱动流量 | 直播低延迟链路"],
        },
    },
    {
        "slug": "game", "cn": "在线游戏", "en": "Online Gaming",
        "layer": "实时交互层", "color": "#2f9e6e", "color2": "#2f6b4e",
        "tagline": "腾讯游戏 / 米哈游 —— 从登录匹配到实时对战的游戏主链路,核心是「帧同步低延迟、状态强一致、反外挂安全」。",
        "domain": {
            "title": "在线游戏架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["登录认证", "匹配", "实时对战", "结算排行", "社交组队", "商城付费", "运营活动"],
            "mid": {"label": "🎮 游戏服务器架构", "blocks": [
                {"t": "网关服务", "s": "长连接接入", "c": "blue"},
                {"t": "战斗逻辑服", "s": "帧同步 / 状态同步", "c": "pink"},
                {"t": "匹配服务", "s": "ELO 匹配算法", "c": "green"}]},
            "tech": [
                {"t": "帧同步引擎", "c": "pink", "lines": ["确定性逻辑", "帧广播回放", "断线重连"]},
                {"t": "匹配服务", "c": "green", "lines": ["ELO 分段", "延迟就近", "队列公平"]},
                {"t": "玩家数据服", "c": "blue", "lines": ["存档一致", "热更热备", "回档补偿"]},
               {"t": "反外挂系统", "c": "purple", "lines": ["行为检测", "服务端校验", "封禁风控"]}],
            "store": ["Redis 会话", "RocksDB 状态", "MongoDB 玩家", "MySQL 存档", "Kafka + K8s"],
            "metrics": [
                "🔑 关键指标：同时在线百万 | 60 FPS | 对战延迟 <50ms | 反外挂命中 99.9%",
                "核心模式：帧同步 / 状态同步 | 服务器权威校验 | 弹性扩缩容开服"],
        },
    },
    {
        "slug": "fintech", "cn": "金融科技", "en": "FinTech & Payment",
        "layer": "交易支付层", "color": "#4a7fd0", "color2": "#3a4a63",
        "tagline": "蚂蚁 / 微信支付 / 招行 —— 从开户认证到清算合规的金融主链路,核心是「资金零差错、风控毫秒级、容灾 RPO=0」。",
        "domain": {
            "title": "金融科技架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["KYC 开户", "认证鉴权", "交易支付", "实时风控", "清算结算", "理财信贷", "合规审计"],
            "mid": {"label": "🏦 金融级技术核心", "blocks": [
                {"t": "分布式事务", "s": "TCC / Saga 资金一致", "c": "green"},
                {"t": "实时风控引擎", "s": "Flink 毫秒决策", "c": "blue"},
                {"t": "资金安全", "s": "国密 SM 加密", "c": "purple"}]},
            "tech": [
                {"t": "分布式事务", "c": "green", "lines": ["TCC 强隔离", "Saga 长事务", "对账兜底"]},
                {"t": "实时风控", "c": "blue", "lines": ["Flink 流计算", "规则 + 模型", "毫秒拦截"]},
                {"t": "资金账务", "c": "purple", "lines": ["复式记账", "余额一致", "冷热分离"]},
                {"t": "高可用容灾", "c": "pink", "lines": ["三地五中心", "单元化", "RPO=0"]}],
            "store": ["OceanBase", "TiDB", "Redis", "RocketMQ", "HSM 加密机"],
            "metrics": [
                "🔑 关键指标：日交易数十亿 | 支付成功率 99.999% | 风控决策 <50ms | RPO=0",
                "核心模式：单元化容灾 | 强一致资金账务 | 实时风控 + 事后审计"],
        },
    },
    {
        "slug": "o2o", "cn": "O2O 本地生活", "en": "O2O Local Services",
        "layer": "调度履约层", "color": "#4a7fd0", "color2": "#3a4a63",
        "tagline": "美团 / 大众点评 / 饿了么 —— 从附近搜索到实时配送的本地生活主链路,核心是「LBS 空间索引、智能调度、实时轨迹」。",
        "domain": {
            "title": "O2O 本地生活架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["附近搜索", "商家浏览", "下单支付", "骑手接单", "实时配送", "确认收货"],
            "mid": {"label": "📌 核心业务域", "blocks": [
                {"t": "LBS 空间索引", "s": "GeoHash / S2 / H3", "c": "blue"},
                {"t": "智能调度系统", "s": "订单-骑手匹配", "c": "green"},
                {"t": "实时轨迹追踪", "s": "ETA 预估", "c": "purple"}]},
            "tech": [
                {"t": "智能调度引擎", "c": "green", "lines": ["OR-Tools 求解", "批量派单", "运力平衡"]},
                {"t": "高精地图服务", "c": "blue", "lines": ["路网建模", "路径规划", "围栏管理"]},
                {"t": "分布式事务", "c": "purple", "lines": ["下单履约一致", "补偿回滚", "对账"]},
                {"t": "风控反作弊", "c": "pink", "lines": ["刷单识别", "虚假定位", "骑手作弊"]}],
            "store": ["MySQL 分库", "Redis Geo", "Kafka 管道", "Elasticsearch", "对象存储"],
            "metrics": [
                "🔑 关键指标：日订单 5000 万 | 配送时长 30 分钟 | 调度成功率 99.5% | ETA 准确率高",
                "核心模式：LBS 空间索引 | 全局最优调度 | 实时轨迹 + 履约闭环"],
        },
    },
    {
        "slug": "mobility", "cn": "出行物流", "en": "Mobility & Logistics",
        "layer": "调度履约层", "color": "#c99a3a", "color2": "#8a6417",
        "tagline": "滴滴 / 顺丰 / 高德 —— 从地点输入到派单履约的时空调度主链路,核心是「LBS 空间索引、全局最优调度、实时轨迹履约闭环」。",
        "domain": {
            "title": "出行物流架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["地点输入", "路线规划", "司机匹配", "行程开始", "到达签收", "支付评价"],
            "mid": {"label": "🚦 核心能力", "blocks": [
                {"t": "路径规划引擎", "s": "A* / Dijkstra 最短路", "c": "blue"},
                {"t": "实时定位", "s": "卡尔曼滤波纠偏", "c": "green"},
                {"t": "ETA 预估", "s": "路况 + 时序模型", "c": "purple"}]},
            "tech": [
                {"t": "时空索引引擎", "c": "blue", "lines": ["H3 网格划分", "GeoHash 邻近", "热点区聚合"]},
                {"t": "实时数据管道", "c": "green", "lines": ["Flink 流处理", "轨迹实时清洗", "供需热力图"]},
                {"t": "分布式调度", "c": "purple", "lines": ["全局最优派单", "批量撮合", "预期收益最大化"]},
                {"t": "物流 IoT 平台", "c": "pink", "lines": ["车辆终端接入", "温控 / 定位上报", "异常轨迹告警"]}],
            "store": ["PostGIS", "Redis Geo", "Kafka + Flink", "HBase 轨迹", "InfluxDB"],
            "metrics": [
                "🔑 关键指标：日订单千万级 | ETA 准确率 95% | 派单撮合毫秒级 | 轨迹上报秒级",
                "核心模式：空间索引降维 | 全局批量最优调度 | 轨迹时序库分层存储"],
        },
    },
    {
        "slug": "edu", "cn": "在线教育", "en": "Online Education",
        "layer": "实时互动层", "color": "#2f9e6e", "color2": "#2f6b4e",
        "tagline": "腾讯课堂 / 猿辅导 / 好未来 —— 从试听到续费的教学主链路,核心是「大规模实时音视频、低延迟互动白板、AI 辅助教学」。",
        "domain": {
            "title": "在线教育架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["试听体验", "选课付费", "直播课堂", "课后作业", "考试测评", "续费转介绍"],
            "mid": {"label": "🧑‍🏫 核心教学能力", "blocks": [
                {"t": "RTC 实时音视频", "s": "百万并发低延迟", "c": "blue"},
                {"t": "互动白板", "s": "多端实时协作", "c": "green"},
                {"t": "AI 辅助教学", "s": "作业批改 / 答疑", "c": "purple"}]},
            "tech": [
                {"t": "实时音视频", "c": "blue", "lines": ["TRTC / WebRTC", "SFU 转发架构", "弱网抗丢包"]},
                {"t": "内容分发", "c": "green", "lines": ["CDN + P2P", "回放切片", "边缘就近拉流"]},
                {"t": "教育数据平台", "c": "purple", "lines": ["学情画像", "知识点掌握度", "个性化推题"]},
                {"t": "在线评测引擎", "c": "pink", "lines": ["OCR 手写识别", "NLP 主观题评分", "防作弊监考"]}],
            "store": ["MySQL + Redis", "OSS 课件", "CDN + P2P", "Kafka + Flink", "Neo4j 知识图谱"],
            "metrics": [
                "🔑 关键指标：百万级并发 | 音视频延迟 <200ms | 白板同步 99.99% | 弱网可用",
                "核心模式：SFU 音视频转发 | CDN + P2P 分发 | 学情数据驱动个性化"],
        },
    },
    {
        "slug": "health", "cn": "医疗健康", "en": "Digital Healthcare",
        "layer": "合规安全层", "color": "#2f9e6e", "color2": "#2f6b4e",
        "tagline": "平安好医生 / 微医 / 京东健康 —— 从分诊到慢病管理的诊疗主链路,核心是「电子病历 EMR、AI 辅助诊断、隐私合规医疗安全」。",
        "domain": {
            "title": "医疗健康架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["分诊预约", "在线问诊", "电子处方", "医药购药", "医保结算", "慢病管理"],
            "mid": {"label": "🏥 核心业务与医疗安全", "blocks": [
                {"t": "电子病历 EMR", "s": "HL7 / FHIR 标准", "c": "blue"},
                {"t": "AI 辅助诊断", "s": "影像识别 CDSS", "c": "green"},
                {"t": "隐私合规", "s": "国密 / HIPAA", "c": "purple"}]},
            "tech": [
                {"t": "RTC 远程问诊", "c": "blue", "lines": ["音视频问诊", "多方会诊", "弱网优化"]},
                {"t": "医学知识图谱", "c": "green", "lines": ["症状-疾病关联", "药品相互作用", "辅助决策"]},
                {"t": "DICOM 影像处理", "c": "purple", "lines": ["云端 PACS", "WebGL 渲染", "AI 病灶标注"]},
                {"t": "物联网 IoT 接入", "c": "pink", "lines": ["穿戴设备 MQTT", "体征实时监测", "异常预警"]}],
            "store": ["MySQL", "MongoDB 病历", "Neo4j 知识图谱", "OSS 医疗影像", "国密 SM4"],
            "metrics": [
                "🔑 关键指标：问诊响应 <30 秒 | 影像加载毫秒级 | 等保 4 级 | 100% 数据安全",
                "核心模式：FHIR 标准病历 | AI 辅助诊断 | 全链路国密加密合规"],
        },
    },
    {
        "slug": "saas", "cn": "企业服务 SaaS", "en": "Enterprise SaaS",
        "layer": "多租户平台层", "color": "#c99a3a", "color2": "#8a6417",
        "tagline": "钉钉 / 飞书 / Salesforce —— 从租户注册到续费升级的协同主链路,核心是「多租户隔离、细粒度权限、工作流引擎」。",
        "domain": {
            "title": "企业服务 SaaS 架构 · 业务×技术",
            "loopLabel": "📋 业务闭环",
            "loop": ["租户注册", "组织架构", "权限配置", "业务审批", "文档协作", "报表分析"],
            "mid": {"label": "🏢 SaaS 核心架构要素", "blocks": [
                {"t": "多租户隔离", "s": "Multi-Tenancy", "c": "blue"},
                {"t": "细粒度权限", "s": "RBAC / ABAC", "c": "green"},
                {"t": "工作流引擎", "s": "BPMN 2.0", "c": "purple"}]},
            "tech": [
                {"t": "实时协同引擎", "c": "blue", "lines": ["OT / CRDT", "WebSocket 长连", "冲突自动合并"]},
                {"t": "低代码引擎", "c": "green", "lines": ["JSON-Schema 驱动", "拖拽式表单", "动态数据模型"]},
                {"t": "开放平台", "c": "purple", "lines": ["微前端 qiankun", "API 网关", "应用市场"]},
                {"t": "企业级安全", "c": "pink", "lines": ["SSO / SAML", "审计日志", "DLP 数据防泄漏"]}],
            "store": ["MySQL / PostgreSQL", "Redis 集群", "Elasticsearch", "ClickHouse 报表", "RabbitMQ / Kafka"],
            "metrics": [
                "🔑 关键指标：99.99% 可用 | 毫秒级协同 | SOC2 合规 | 多租户强隔离",
                "核心模式：多租户隔离 | OT/CRDT 实时协同 | 低代码 + 开放平台生态"],
        },
    },
]


def build_scenarios_cards():
    """业务场景:内联「业务场景·分布式系统落地全景」导航图 SVG。
    自上而下三层——用户体验层 / 智能决策层 / 核心三流层,共 10 类高频
    业务场景。同 build_agent_cards 方式:把中性色(背景/白框/灰字/黑标题)
    挂 class 使深浅主题跟随;并解析带 data-tid 的卡片 <rect>,在其上叠加
    透明热区 <a>,点击下钻到 scenarios/<slug>/index.html(该场景核心技术
    点架构图子页)。"""
    import xml.etree.ElementTree as _ET
    svg_path = os.path.join(ROOT, "scenarios", "design", "业务场景_架构导航图.svg")
    try:
        with open(svg_path, encoding="utf-8") as f:
            svg_text = f.read()
    except OSError:
        return ""
    svg_inline = re.sub(r'<svg\b', '<svg class="arch-svg"', svg_text, count=1)
    # 浅底语义色卡风格(参考 LLM&Agent 总架构图 build_agent_cards):
    # 把中性色(背景/白卡/浅底 tint/层容器 band/黑标题/灰副标题/连线)统一挂 ag-* class
    # 并移除其 presentation hex,让 index.html 里的 ag-* 深浅主题 CSS 生效(暗色不露白)。
    # 场景卡的分类彩色描边(stroke=#0071e3/#7c3aed/#34c759/#ff9f0a)保留不动,作为四分类语义色。
    svg_inline = svg_inline.replace('fill="#fbfbfd" class="ag-bg"', 'class="ag-bg"')
    svg_inline = svg_inline.replace('stroke="#a1a1a6" class="ag-line"', 'class="ag-line"')
    # 层容器 band(浅灰底)
    svg_inline = svg_inline.replace('fill="#f4f4f6" stroke="#e4e7ec" class="ag-band"', 'class="ag-band"')
    # 上层四分类语义色分区 band(sf-band-pay/disc/social/growth):去 SVG 里的 fill=url(#xxxBand)+stroke，
    # 保留 sf-band-* class 由 index.html CSS 接管——亮色浅语义色、暗色各自深语义色(保分区色差,勿收敛成单色)。
    svg_inline = re.sub(
        r'fill="#[0-9a-fA-F]{6}" stroke="#[0-9a-fA-F]{6}" (class="sf-band-\w+")',
        r'\1', svg_inline)
    # 分类彩色标题(sf-cat-*):保留彩色 fill 作为四分类语义主色,不动。
    # 场景卡(白底 #ffffff + 柔和语义色描边 stroke-width 1.2 + sc-scene sc-<cat>):
    # 去白底 fill,保留彩色描边 + class,由 CSS 接管(亮色白底/暗色深底,不露白)。
    svg_inline = re.sub(
        r'fill="#ffffff" (stroke="#[0-9a-fA-F]{6}" stroke-width="1\.2" class="sc-scene sc-\w+")',
        r'\1', svg_inline)
    # 底层基础设施白卡
    svg_inline = svg_inline.replace(
        'fill="#ffffff" stroke="#e4e7ec" class="ag-card"', 'class="ag-card"')
    # 浅底 tint 小卡(中层 7 组件,统一中性浅底)
    svg_inline = svg_inline.replace(
        'fill="#f6f7f9" stroke="#d7d7dd" class="ag-tint"', 'class="ag-tint"')
    # 分类灰字标签
    svg_inline = svg_inline.replace('fill="#8a8a8e" class="ag-sub"', 'class="ag-sub"')
    # 组件/基础设施卡内灰副标题
    svg_inline = svg_inline.replace('fill="#6e6e73" class="ag-sub"', 'class="ag-sub"')
    svg_inline = svg_inline.replace('fill="#8a8a8e" class="ag-sub" text-anchor="middle"',
                                    'class="ag-sub" text-anchor="middle"')
    # 黑色主标题(顶部大标题 + 各卡标题)挂 ag-title
    svg_inline = svg_inline.replace('fill="#1d1d1f"', 'class="ag-title"')
    svg_inline = svg_inline.replace('fill="#8a8a8e">', 'class="ag-sub">')

    # ── 解析 data-tid 卡片热区,按 viewBox 百分比叠加透明下钻 <a> ──
    vb = re.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg_text)
    vbw, vbh = float(vb.group(1)), float(vb.group(2))
    root = _ET.fromstring(svg_text)
    by_slug = {s["slug"]: s for s in SCENARIOS}
    # 热区 hover 高亮的 --accent 必须与其所属分区语义色一致(否则悬停边框/淡底
    # 颜色与分区背景不契合)。四分类语义主色:交易蓝/内容紫/实时绿/服务橙。
    _SCEN_ACCENT = {
        "ecommerce": "#4a7fd0", "fintech": "#4a7fd0", "o2o": "#4a7fd0",
        "social": "#8a5cae", "video": "#8a5cae",
        "game": "#2f9e6e", "edu": "#2f9e6e", "health": "#2f9e6e",
        "mobility": "#c99a3a", "saas": "#c99a3a",
    }
    hot_html = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "rect" or not el.get("data-tid"):
            continue
        slug = el.get("data-tid")
        sc = by_slug.get(slug)
        if not sc:
            continue
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        hot_html.append(
            '<a id="{sid}" class="arch-hot" style="left:{lp:.3f}%;top:{tp:.3f}%;'
            'width:{wp:.3f}%;height:{hp:.3f}%;--accent:{c}" '
            'href="scenarios/{slug}/index.html" title="{lab} → {cn}">'
            '<span class="arch-hot-lab">{cn}</span></a>'.format(
                sid=_gid("scen_" + slug),
                lp=x / vbw * 100, tp=y / vbh * 100, wp=w / vbw * 100,
                hp=h / vbh * 100, c=_SCEN_ACCENT.get(slug, sc["color"]), slug=slug,
                lab=_esc(el.get("data-lab") or ""), cn=_esc(sc["cn"])))
    return ('<div class="arch-stage scen-hot"><div class="arch-canvas">'
        '{svg}{hots}'
            '</div></div>').format(svg=svg_inline, hots="".join(hot_html))


def _sv_wrap(text, per_line):
    """按全角字数机械折行,返回行列表(SVG 无自动折行)。"""
    lines, cur = [], ""
    for ch in text or "":
        cur += ch
        if len(cur) >= per_line:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def _scenario_master_svg(sc):
    """全景合成图:把【端到端数据流拓扑 + 关键技术矩阵 + 核心张力 +
    本质洞察 + 失败模式 + 设计心法】六部分绘制进同一张 SVG,一张图完整
    表达该场景的逻辑链条(是什么→怎么流转→矛盾在哪→本质→会怎么崩→该怎么做)。
    纵向分区,y 游标累加计算总高度 VBH。中性色挂 ag-* class 随主题变化。"""
    acc = sc["color"]
    VBW = 1080
    pad = 26
    body = []          # 区块正文(不含 <svg> 外壳)
    y = 92             # 顶部标题区之下起点

    # ============ 区一:端到端数据流拓扑 ============
    flow = sc.get("flow")
    if flow:
        lanes = flow["lanes"]
        edges = flow.get("edges", [])
        nl = len(lanes)
        lane_head = 30
        lane_gap = 16
        lane_w = (VBW - pad * 2 - lane_gap * (nl - 1)) / nl
        node_w = lane_w
        node_h = 66
        node_gap = 30
        sec_title_h = 34
        body.append(
            '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
            '① 端到端数据流 · 沿箭头为请求/数据流转,红虚线为回流/补偿</text>'.format(
                x=pad, y=y + 20, acc=acc))
        y += sec_title_h
        lane_top = y
        body_top = lane_top + lane_head + 14
        max_nodes = max(len(l["nodes"]) for l in lanes)
        body_h = max_nodes * node_h + (max_nodes - 1) * node_gap
        pos = {}
        for li, lane in enumerate(lanes):
            lx = pad + li * (lane_w + lane_gap)
            n = len(lane["nodes"])
            block_h = n * node_h + (n - 1) * node_gap
            y0 = body_top + (body_h - block_h) / 2
            for ni, nd in enumerate(lane["nodes"]):
                ny = y0 + ni * (node_h + node_gap)
                pos[nd["id"]] = (lx, ny, node_w, node_h)
        # ── 量级角标:funnel 与 lanes 均为有序流程阶段,按索引对齐挂 QPS ──
        funnel = sc.get("funnel", [])

        def _lane_qps(li):
            if li < len(funnel):
                return funnel[li].get("qps", "")
            return ""
        # lane 名称条
        for li, lane in enumerate(lanes):
            lx = pad + li * (lane_w + lane_gap)
            body.append(
                '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lh}" rx="9" '
                'fill="{acc}" opacity="0.12"/>'.format(
                    x=lx, y=lane_top, w=lane_w, lh=lane_head, acc=acc))
            _q = _lane_qps(li)
            if _q:
                # 有量级:名称左对齐,右侧挂 QPS 胶囊角标
                body.append(
                    '<text x="{x:.1f}" y="{y}" font-size="12" font-weight="700" '
                    'fill="{acc}" text-anchor="start">{g}</text>'.format(
                        x=lx + 12, y=lane_top + 20, acc=acc, g=_esc(lane["g"])))
                _qw = len(_q) * 6.4 + 14
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="17" rx="8.5" '
                    'fill="{acc}" opacity="0.9"/>'.format(
                        x=lx + lane_w - _qw - 10, y=lane_top + (lane_head - 17) / 2, w=_qw, acc=acc))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="9.5" font-weight="700" '
                    'fill="#ffffff" text-anchor="middle">{q}</text>'.format(
                        x=lx + lane_w - _qw / 2 - 10, y=lane_top + lane_head / 2 + 3.4, q=_esc(_q)))
            else:
                body.append(
                    '<text x="{x:.1f}" y="{y}" font-size="12" font-weight="700" '
                    'fill="{acc}" text-anchor="middle">{g}</text>'.format(
                        x=lx + lane_w / 2, y=lane_top + 20, acc=acc, g=_esc(lane["g"])))
        # 边(先画)
        for e in edges:
            if e["f"] not in pos or e["t"] not in pos:
                continue
            fx, fy, fw, fh = pos[e["f"]]
            tx, ty, tw, th = pos[e["t"]]
            back = e.get("d") == "back"
            if back:
                x1, y1 = fx, fy + fh / 2
                x2, y2 = tx + tw, ty + th / 2
                mx = (x1 + x2) / 2
                dd = "M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}".format(
                    x1=x1, y1=y1 + 14, mx=mx, x2=x2, y2=y2 + 14)
                body.append(
                    '<path d="{d}" fill="none" stroke="#c0392b" stroke-width="1.4" '
                    'stroke-dasharray="5 4" marker-end="url(#scArrB)" opacity="0.85"/>'.format(d=dd))
                lbx = mx
                lby = (y1 + y2) / 2 + 26
                _lbl = e.get("l", "")
                _lw = len(_lbl) * 10 * 0.95 + 8
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="15" rx="4" '
              'class="ag-bg" opacity="0.92"/>'.format(x=lbx - _lw / 2, y=lby - 11, w=_lw))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="10" fill="#c0392b" '
                    'text-anchor="middle">{l}</text>'.format(x=lbx, y=lby, l=_esc(_lbl)))
            else:
                x1, y1 = fx + fw, fy + fh / 2
                x2, y2 = tx, ty + th / 2
                mx = (x1 + x2) / 2
                dd = "M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}".format(
                    x1=x1, y1=y1, mx=mx, x2=x2, y2=y2)
                body.append(
                    '<path d="{d}" fill="none" stroke="{acc}" stroke-width="1.6" '
                    'marker-end="url(#scArr)" opacity="0.8"/>'.format(d=dd, acc=acc))
                if e.get("l"):
                    lbx = x1 + (mx - x1) * 0.62
                    lby = (y1 + y2) / 2 - 6
                    _lbl = e["l"]
                    _lw = len(_lbl) * 10 * 0.95 + 8
                    body.append(
                        '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="15" rx="4" '
                        'class="ag-bg" opacity="0.92"/>'.format(x=lbx - _lw / 2, y=lby - 11, w=_lw))
                    body.append(
                        '<text x="{x:.1f}" y="{y:.1f}" font-size="10" class="ag-sub" '
                        'text-anchor="middle">{l}</text>'.format(x=lbx, y=lby, l=_esc(_lbl)))
        # 节点(后画)
        for lane in lanes:
            for nd in lane["nodes"]:
                nx, ny, nw, nh = pos[nd["id"]]
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="11" '
                    'class="ag-card" stroke="{acc}" stroke-width="1.4" filter="url(#scSoft)"/>'.format(
                        x=nx, y=ny, w=nw, h=nh, acc=acc))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="12.5" font-weight="700" '
                    'class="ag-title" text-anchor="middle">{t}</text>'.format(
                        x=nx + nw / 2, y=ny + 24, t=_esc(nd["t"])))
                for i, ln in enumerate(_sv_wrap(nd.get("s", ""), max(6, int(nw / 11)))[:2]):
                    body.append(
                        '<text x="{x:.1f}" y="{y:.1f}" font-size="9.5" class="ag-sub" '
                        'text-anchor="middle">{ln}</text>'.format(
                            x=nx + nw / 2, y=ny + 42 + i * 13, ln=_esc(ln)))
        y = body_top + body_h + 30
        # ── 关键技术 / 机制 技术矩阵:按 groups 分组呈现,广度结构化可视化 ──
        groups2 = sc.get("groups", [])
        if groups2:
            body.append(
                '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
                '② 关键技术 · 机制矩阵(广度:按技术域分组)</text>'.format(
                    x=pad, y=y + 20, acc=acc))
            y += 36
            cy = y
            row_h = 28
            row_gap = 12
            gap_x = 9
            avail = VBW - pad * 2
            for grp in groups2:
                gname = grp.get("g", "").strip()
                cx = pad
                # 组名胶囊(实心 accent)
                gw = len(gname) * 13 + 26
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="7" '
                    'fill="{acc}" opacity="0.92"/>'.format(x=cx, y=cy, w=gw, h=row_h, acc=acc))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="12.5" font-weight="800" '
                    'fill="#ffffff" text-anchor="middle">{g}</text>'.format(
                        x=cx + gw / 2, y=cy + row_h / 2 + 4.4, g=_esc(gname)))
                cx += gw + gap_x + 4
                # 该组各技术点 chip(描边款)
                for nd2 in grp.get("nodes", []):
                    ct = nd2.get("t", "").strip()
                    if not ct:
                        continue
                    cw = len(ct) * 12.2 + 24
                    if cx > pad and cx + cw > pad + avail:
                        cy += row_h + row_gap
                        cx = pad + gw + gap_x + 4
                    body.append(
                        '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="14" '
                        'fill="{acc}" opacity="0.1" stroke="{acc}" stroke-width="1"/>'.format(
                            x=cx, y=cy, w=cw, h=row_h, acc=acc))
                    body.append(
                        '<text x="{x:.1f}" y="{y:.1f}" font-size="12" font-weight="600" '
                        'fill="{acc}" text-anchor="middle">{t}</text>'.format(
                            x=cx + cw / 2, y=cy + row_h / 2 + 4.2, acc=acc, t=_esc(ct)))
                    cx += cw + gap_x
                cy += row_h + row_gap
            y = cy + 12
        # ── 核心张力对撞图:left/right 两组图形化对峙,中间张力符号 ──
        tn = sc.get("tension")
        if tn and tn.get("left") and tn.get("right"):
            body.append(
                '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
                '③ 核心张力 · 本质矛盾(深度:一对相互拉扯的力)</text>'.format(
                    x=pad, y=y + 20, acc=acc))
            y += 34
            L = tn["left"]
            R = tn["right"]
            col_w = (VBW - pad * 2 - 90) / 2      # 中间留 90 给张力符号
            li = L.get("items", [])[:4]
            ri = R.get("items", [])[:4]
            rows = max(len(li), len(ri))
            head_h = 30
            item_h = 24
            item_gap = 8
            box_h = head_h + rows * (item_h + item_gap) + 10
            lx = pad
            rx = pad + col_w + 90
            cty = y
            # 左右外框
            for bx, side, col in ((lx, L, "#c0392b"), (rx, R, "#2d7d46")):
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" '
                    'fill="{c}" opacity="0.07" stroke="{c}" stroke-width="1.3"/>'.format(
                        x=bx, y=cty, w=col_w, h=box_h, c=col))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="13" font-weight="800" '
                    'fill="{c}" text-anchor="middle">{l}</text>'.format(
                        x=bx + col_w / 2, y=cty + 21, c=col, l=_esc(side.get("label", ""))))
                for i, it in enumerate(side.get("items", [])[:4]):
                    iy = cty + head_h + i * (item_h + item_gap)
                    body.append(
                        '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="7" '
                        'fill="{c}" opacity="0.11"/>'.format(
                            x=bx + 14, y=iy, w=col_w - 28, h=item_h, c=col))
                    body.append(
                        '<text x="{x:.1f}" y="{y:.1f}" font-size="11.5" class="ag-title" '
                        'text-anchor="middle">{t}</text>'.format(
                            x=bx + col_w / 2, y=iy + item_h / 2 + 4, t=_esc(it)))
            # 中间张力符号:双向箭头 + ⚡
            mcx = pad + col_w + 45
            mcy = cty + box_h / 2
            body.append(
                '<circle cx="{x:.1f}" cy="{y:.1f}" r="24" class="ag-bg" '
                'stroke="{acc}" stroke-width="1.6"/>'.format(x=mcx, y=mcy, acc=acc))
            body.append(
                '<text x="{x:.1f}" y="{y:.1f}" font-size="22" text-anchor="middle">⚡</text>'.format(
                    x=mcx, y=mcy + 8))
            body.append(
                '<path d="M{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f}" stroke="#c0392b" '
                'stroke-width="1.6" marker-end="url(#scArrB)"/>'.format(
                    x1=mcx - 26, y=mcy, x2=lx + col_w + 4))
            body.append(
                '<path d="M{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f}" stroke="#2d7d46" '
                'stroke-width="1.6" marker-end="url(#scArr2)"/>'.format(
                    x1=mcx + 26, y=mcy, x2=rx - 4))
            y = cty + box_h + 14
            core = tn.get("core", "")
            if core:
                # 均衡折行:按半长切两行,避免句末标点孤立成行
                import math as _m
                per = max(24, _m.ceil(len(core) / 2) + 1)
                lns = _sv_wrap(core, per)[:2]
                if len(lns) == 2 and len(lns[1].strip()) <= 1:
                    lns = [lns[0] + lns[1]]      # 孤立标点并回上一行
                for i, ln in enumerate(lns):
                    body.append(
                        '<text x="{x}" y="{y:.1f}" font-size="11.5" class="ag-sub">◆ {ln}</text>'.format(
                            x=pad, y=y + 4 + i * 17, ln=_esc(ln)))
                y += len(lns) * 17 + 16

        # ── 区四:本质洞察 insight(一段最凝练的场景本质判断) ──
        insight = sc.get("insight", "").strip()
        if insight:
            body.append(
                '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
                '④ 本质洞察 · 一句话看穿这个场景</text>'.format(
                    x=pad, y=y + 20, acc=acc))
            y += 32
            per = max(38, int((VBW - pad * 2 - 48) / 12.6))
            ins_lns = _sv_wrap(insight, per)
            box_h = 22 + len(ins_lns) * 20 + 16
            body.append(
                '<rect x="{x}" y="{y:.1f}" width="{w}" height="{h}" rx="12" '
                'class="ag-card" stroke="{acc}" stroke-width="1.4"/>'.format(
                    x=pad, y=y, w=VBW - pad * 2, h=box_h, acc=acc))
            body.append(
                '<rect x="{x}" y="{y:.1f}" width="4" height="{h}" rx="2" '
                'fill="{acc}"/>'.format(x=pad, y=y, h=box_h, acc=acc))
            for i, ln in enumerate(ins_lns):
                body.append(
                    '<text x="{x}" y="{ly:.1f}" font-size="13" class="ag-title">'
                    '{ln}</text>'.format(x=pad + 24, ly=y + 30 + i * 20, ln=_esc(ln)))
            y += box_h + 26

        # ── 区五:失败模式 pitfalls(踩坑铁律,红叉卡片双列网格) ──
        pits = sc.get("pitfalls", [])
        if pits:
            body.append(
                '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
                '⑤ 失败模式 · 真实踩过的坑(反例:这样做会崩)</text>'.format(
                    x=pad, y=y + 20, acc=acc))
            y += 34
            cols = 2
            col_gap = 16
            card_w = (VBW - pad * 2 - col_gap * (cols - 1)) / cols
            per = max(20, int((card_w - 46) / 12.6))
            row_y = [y, y]
            for idx, pit in enumerate(pits):
                ci = idx % cols
                cx = pad + ci * (card_w + col_gap)
                plns = _sv_wrap(pit, per)
                ch = 14 + len(plns) * 18 + 12
                cy = row_y[ci]
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="10" '
                    'class="ag-card" stroke="#e0562d" stroke-width="1" '
                    'stroke-opacity="0.5"/>'.format(x=cx, y=cy, w=card_w, h=ch))
                body.append(
                    '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="#e0562d" '
                    'opacity="0.14"/>'.format(cx=cx + 20, cy=cy + 20))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="11" font-weight="800" '
                    'fill="#e0562d" text-anchor="middle">✕</text>'.format(
                        x=cx + 20, y=cy + 23.5))
                for i, ln in enumerate(plns):
                    body.append(
                        '<text x="{x:.1f}" y="{ly:.1f}" font-size="11.5" class="ag-sub">'
                        '{ln}</text>'.format(x=cx + 36, ly=cy + 20 + i * 18, ln=_esc(ln)))
                row_y[ci] = cy + ch + 12
            y = max(row_y) + 16

        # ── 区六:设计心法 takeaways(经验结晶,绿勾卡片双列网格) ──
        tks = sc.get("takeaways", [])
        if tks:
            body.append(
                '<text x="{x}" y="{y}" font-size="15" font-weight="800" fill="{acc}">'
                '⑥ 设计心法 · 沉淀出的正解(正例:应该这样做)</text>'.format(
                    x=pad, y=y + 20, acc=acc))
            y += 34
            cols = 2
            col_gap = 16
            card_w = (VBW - pad * 2 - col_gap * (cols - 1)) / cols
            per = max(20, int((card_w - 46) / 12.6))
            row_y = [y, y]
            for idx, tk in enumerate(tks):
                ci = idx % cols
                cx = pad + ci * (card_w + col_gap)
                tlns = _sv_wrap(tk, per)
                ch = 14 + len(tlns) * 18 + 12
                cy = row_y[ci]
                body.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="10" '
                    'fill="#2ea043" fill-opacity="0.06" stroke="#2ea043" '
                    'stroke-width="1" stroke-opacity="0.45"/>'.format(
                        x=cx, y=cy, w=card_w, h=ch))
                body.append(
                    '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="#2ea043" '
                    'opacity="0.16"/>'.format(cx=cx + 20, cy=cy + 20))
                body.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="11" font-weight="800" '
                    'fill="#2ea043" text-anchor="middle">✓</text>'.format(
                        x=cx + 20, y=cy + 23.5))
                for i, ln in enumerate(tlns):
                    body.append(
                        '<text x="{x:.1f}" y="{ly:.1f}" font-size="11.5" class="ag-title">'
                        '{ln}</text>'.format(x=cx + 36, ly=cy + 20 + i * 18, ln=_esc(ln)))
                row_y[ci] = cy + ch + 12
            y = max(row_y) + 16

    return _scenario_master_svg_tail(sc, VBW, pad, acc, body, y)


def _scenario_master_svg_tail(sc, VBW, pad, acc, body, y):
    """承接 master 图:端到端数据流拓扑之后直接收尾。
    机制/深度细节回正文看,首图只保留数据流骨架,避免大段文本堆砌。"""
    return _scenario_master_svg_tail2(sc, VBW, pad, acc, body, y)


def _scenario_master_svg_tail2(sc, VBW, pad, acc, body, y):
    """承接 master 图:数据流拓扑之后直接组装 <svg> 外壳。
    首图只保留纯图形的端到端数据流拓扑,不再画核心张力/本质洞察文字卡
    (那些结论回正文「概念说明」看)。"""
    VBH = int(y + 20)
    head = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=VBH),
        '<defs><filter id="scSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.08"/></filter>'
        '<marker id="scArr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="{acc}"/></marker>'
        '<marker id="scArrB" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="#c0392b"/></marker>'
        '<marker id="scArr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="#2d7d46"/></marker></defs>'.format(acc=acc),
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(w=VBW, h=VBH),
        '<text x="{x}" y="42" font-size="20" font-weight="800" class="ag-title">'
        '{cn} · 全景</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">{t}</text>'.format(
            x=pad, t=_esc(sc["layer"] + " · " + sc["en"] + " · 数据流拓扑 + 技术矩阵 + 核心张力 + 洞察 + 踩坑 + 心法")),
    ]
    return "\n".join(head + body + ['</svg>'])


def _scenario_arch_svg(sc):
    """程序化生成某场景的「核心技术点」架构图 SVG。
    优先按 sc['flow'] 生成带箭头连线的分层数据流拓扑图(阶段泳道 + 节点 +
    有向边 + 流转语义标签),真实体现模块间关系与数据流向;无 flow 时回退
    到旧的分组卡片矩阵。中性色挂 ag-* class 随主题变化,accent 取场景色。"""
    if sc.get("flow"):
        return _scenario_flow_svg(sc)
    return _scenario_cards_svg(sc)


def _dom_label(raw):
    """去掉 domain 段标签里的 emoji / 装饰符号,只保留纯文字(Apple 工业风不用 emoji)。"""
    import re as _re
    txt = _re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF]", "", raw)
    return txt.strip(" ·").strip()


def _scenario_domain_svg(sc):
    """业务×技术架构图:Apple 工业风(淡雅浅底 + 柔投影 + 圆角 + 冷灰阶),620×480 分段式布局。
    数据取 sc['domain'],结构:
      title      标题
      loop       业务闭环块文本列表(5-8 块横向流程条)
      loopLabel  闭环段标签(默认 '业务闭环')
      mid        {label, blocks:[{t,s,c}]}  中间业务域段(2-3 块带 accent 描边)
      tech       [{t, lines:[..], c}]        技术核心(4 块 80px 卡片)
      store      存储块文本列表(5 块)
      metrics    [第一行, 第二行]            底部关键指标条
    中性色挂 ag-* class 随主题翻转,accent 取场景色用于描边 / 段标签强调。"""
    dom = sc["domain"]
    acc = sc["color"]
    out = [
        '<svg viewBox="0 0 620 480" class="arch-svg" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        'font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">",
        '<defs><filter id="scSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.08"/></filter></defs>',
        '<rect x="0" y="0" width="620" height="480" rx="14" class="ag-bg"/>',
    ]
    # ── 标题 + 右上角代表企业 ──
    out.append('<text x="20" y="30" font-size="16" font-weight="800" '
               'class="ag-title">%s</text>' % _esc(dom["title"]))
    tag = sc.get("tagline", "")
    firm = tag.split("——")[0].strip(" —")
    if firm:
        out.append('<text x="600" y="30" text-anchor="end" font-size="10.5" '
                   'class="ag-sub">%s</text>' % _esc(firm))

    # ── 业务闭环(横向流程条) ──
    loop = dom["loop"]
    out.append('<text x="20" y="60" font-size="11" font-weight="700" fill="%s">%s</text>'
               % (acc, _esc(_dom_label(dom.get("loopLabel", "业务闭环")))))
    out.append('<rect x="15" y="68" width="590" height="52" rx="12" class="ag-card" '
               'filter="url(#scSoft)"/>')
    n = len(loop)
    inner = 590 - 30
    gap = 10
    bw = (inner - gap * (n - 1)) / n
    out.append('<g transform="translate(30,77)">')
    x = 0.0
    for i, txt in enumerate(loop):
        out.append('<rect x="%.1f" y="0" width="%.1f" height="34" rx="8" fill="%s" '
                   'opacity="0.10"/>' % (x, bw, acc))
        out.append('<rect x="%.1f" y="0" width="%.1f" height="34" rx="8" fill="none" '
                   'stroke="%s" stroke-width="1" opacity="0.35"/>' % (x, bw, acc))
        out.append('<text x="%.1f" y="22" text-anchor="middle" class="ag-title" '
                   'font-size="10.5" font-weight="600">%s</text>' % (x + bw / 2, _esc(txt)))
        x += bw + gap
    out.append('</g>')

    # ── 中间业务域段(accent 描边,副标题)──
    mid = dom["mid"]
    out.append('<text x="20" y="148" font-size="11" font-weight="700" fill="%s">%s</text>'
               % (acc, _esc(_dom_label(mid["label"]))))
    out.append('<g transform="translate(15,156)">')
    mb = mid["blocks"]
    mn = len(mb)
    mgap = 10
    mbw = (590 - mgap * (mn - 1)) / mn
    mx = 0.0
    for blk in mb:
        out.append('<rect x="%.1f" y="0" width="%.1f" height="52" rx="11" class="ag-card" '
                   'stroke="%s" stroke-width="1.2" filter="url(#scSoft)"/>' % (mx, mbw, acc))
        out.append('<text x="%.1f" y="22" text-anchor="middle" class="ag-title" '
                   'font-size="12" font-weight="700">%s</text>' % (mx + mbw / 2, _esc(blk["t"])))
        out.append('<text x="%.1f" y="40" text-anchor="middle" class="ag-sub" '
                   'font-size="10">%s</text>' % (mx + mbw / 2, _esc(blk["s"])))
        mx += mbw + mgap
    out.append('</g>')

    # ── 技术核心(4 块 80px 卡片) ──
    tech = dom["tech"]
    out.append('<text x="20" y="231" font-size="11" font-weight="700" fill="%s">技术核心</text>' % acc)
    out.append('<g transform="translate(15,238)">')
    tn = len(tech)
    tgap = 10
    tbw = (590 - tgap * (tn - 1)) / tn
    tx = 0.0
    for blk in tech:
        cx = tx + tbw / 2
        out.append('<rect x="%.1f" y="0" width="%.1f" height="80" rx="11" class="ag-card" '
                   'stroke="%s" stroke-width="1.2" filter="url(#scSoft)"/>' % (tx, tbw, acc))
        out.append('<text x="%.1f" y="24" text-anchor="middle" class="ag-title" '
                   'font-size="11" font-weight="700">%s</text>' % (cx, _esc(blk["t"])))
        ly = 44
        for ln in blk.get("lines", [])[:3]:
            out.append('<text x="%.1f" y="%d" text-anchor="middle" class="ag-sub" '
                       'font-size="9">%s</text>' % (cx, ly, _esc(ln)))
            ly += 14
        tx += tbw + tgap
    out.append('</g>')

    # ── 存储与中间件(5 块) ──
    store = dom["store"]
    out.append('<text x="20" y="346" font-size="11" font-weight="700" fill="%s">存储与中间件</text>' % acc)
    out.append('<g transform="translate(15,354)">')
    sn = len(store)
    sgap = 10
    sbw = (590 - sgap * (sn - 1)) / sn
    sx = 0.0
    for txt in store:
        out.append('<rect x="%.1f" y="0" width="%.1f" height="40" rx="10" class="ag-card" '
                   'filter="url(#scSoft)"/>' % (sx, sbw))
        out.append('<text x="%.1f" y="25" text-anchor="middle" class="ag-title" '
                   'font-size="10">%s</text>' % (sx + sbw / 2, _esc(txt)))
        sx += sbw + sgap
    out.append('</g>')

    # ── 底部关键指标条 ──
    met = dom["metrics"]
    out.append('<g transform="translate(15,414)">')
    out.append('<rect x="0" y="0" width="590" height="50" rx="12" class="ag-band" '
               'filter="url(#scSoft)"/>')
    out.append('<text x="16" y="21" class="ag-title" font-size="10" font-weight="600">%s</text>'
               % _esc(_dom_label(met[0])))
    if len(met) > 1:
        out.append('<text x="16" y="39" class="ag-sub" font-size="9">%s</text>'
                   % _esc(_dom_label(met[1])))
    out.append('</g>')
    out.append('</svg>')
    return "".join(out)


def _scenario_flow_svg(sc):
    """分层数据流拓扑图:横向若干阶段(lane),每 lane 一列纵排节点,
    节点间按 edges 画有向连线并标注流转语义;back 边表示回流(虚线)。"""
    acc = sc["color"]
    flow = sc["flow"]
    lanes = flow["lanes"]
    edges = flow.get("edges", [])
    nl = len(lanes)
    VBW = 1080
    pad = 26
    top = 92                      # 标题区
    lane_head = 30                # lane 名称条高
    lane_gap = 16
    lane_w = (VBW - pad * 2 - lane_gap * (nl - 1)) / nl
    node_w = lane_w
    node_h = 66
    node_gap = 30                 # 纵向节点间距(留给边标签)
    body_top = top + lane_head + 14
    max_nodes = max(len(l["nodes"]) for l in lanes)
    body_h = max_nodes * node_h + (max_nodes - 1) * node_gap
    VBH = body_top + body_h + 44
    # ── 计算每个节点中心坐标 ──
    pos = {}
    for li, lane in enumerate(lanes):
        lx = pad + li * (lane_w + lane_gap)
        n = len(lane["nodes"])
        # 纵向居中分布
        block_h = n * node_h + (n - 1) * node_gap
        y0 = body_top + (body_h - block_h) / 2
        for ni, nd in enumerate(lane["nodes"]):
            ny = y0 + ni * (node_h + node_gap)
            pos[nd["id"]] = (lx, ny, node_w, node_h)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=int(VBH)),
        '<defs><filter id="scSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.08"/></filter>'
        '<marker id="scArr" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="{acc}"/></marker>'
        '<marker id="scArrB" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#c0392b"/></marker></defs>'.format(acc=acc),
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(
            w=VBW, h=int(VBH)),
        '<text x="{x}" y="42" font-size="20" font-weight="800" '
        'class="ag-title">{cn} · 端到端数据流</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">{t}</text>'.format(
            x=pad, t=_esc(sc["layer"] + " · " + sc["en"] + " · 沿箭头方向为请求 / 数据流转,红色虚线为回流 / 补偿")),
    ]
    # ── lane 名称条 ──
    for li, lane in enumerate(lanes):
        lx = pad + li * (lane_w + lane_gap)
        parts.append(
            '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lh}" rx="9" '
            'fill="{acc}" opacity="0.12"/>'.format(x=lx, y=top, w=lane_w, lh=lane_head, acc=acc))
        parts.append(
            '<text x="{x:.1f}" y="{y}" font-size="12" font-weight="700" '
            'fill="{acc}" text-anchor="middle">{g}</text>'.format(
                x=lx + lane_w / 2, y=top + 20, acc=acc, g=_esc(lane["g"])))
    # ── 边(先画,置于节点下层)──
    for e in edges:
        if e["f"] not in pos or e["t"] not in pos:
            continue
        fx, fy, fw, fh = pos[e["f"]]
        tx, ty, tw, th = pos[e["t"]]
        back = e.get("d") == "back"
        # 起终点:同向取右边->左边;回流取左->右上方偏移
        if back:
            x1, y1 = fx, fy + fh / 2
            x2, y2 = tx + tw, ty + th / 2
            mx = (x1 + x2) / 2
            d = "M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}".format(
                x1=x1, y1=y1 + 14, mx=mx, x2=x2, y2=y2 + 14)
            parts.append(
                '<path d="{d}" fill="none" stroke="#c0392b" stroke-width="1.4" '
                'stroke-dasharray="5 4" marker-end="url(#scArrB)" opacity="0.85"/>'.format(d=d))
            lx = mx
            ly = (y1 + y2) / 2 + 26
            _lbl = e.get("l", "")
            _lw = len(_lbl) * 10 * 0.95 + 8
            parts.append(
                '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="15" rx="4" '
                'class="ag-bg" opacity="0.92"/>'.format(x=lx - _lw / 2, y=ly - 11, w=_lw))
            parts.append(
                '<text x="{x:.1f}" y="{y:.1f}" font-size="10" fill="#c0392b" '
                'text-anchor="middle">{l}</text>'.format(x=lx, y=ly, l=_esc(_lbl)))
        else:
            x1, y1 = fx + fw, fy + fh / 2
            x2, y2 = tx, ty + th / 2
            mx = (x1 + x2) / 2
            d = "M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}".format(
                x1=x1, y1=y1, mx=mx, x2=x2, y2=y2)
            parts.append(
                '<path d="{d}" fill="none" stroke="{acc}" stroke-width="1.6" '
                'marker-end="url(#scArr)" opacity="0.8"/>'.format(d=d, acc=acc))
            if e.get("l"):
                # 标签落在 source 一侧的水平间隙区,避免压到目标节点小字
                lx = x1 + (mx - x1) * 0.62
                ly = (y1 + y2) / 2 - 6
                _lbl = e["l"]
                _lw = len(_lbl) * 10 * 0.95 + 8
                parts.append(
                    '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="15" rx="4" '
                    'class="ag-bg" opacity="0.92"/>'.format(x=lx - _lw / 2, y=ly - 11, w=_lw))
                parts.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="10" class="ag-sub" '
                    'text-anchor="middle">{l}</text>'.format(x=lx, y=ly, l=_esc(_lbl)))
    # ── 节点(后画,置于边上层)──
    for lane in lanes:
        for nd in lane["nodes"]:
            x, y, w, h = pos[nd["id"]]
            parts.append(
                '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="11" '
                'class="ag-card" stroke="{acc}" stroke-width="1.4" filter="url(#scSoft)"/>'.format(
                    x=x, y=y, w=w, h=h, acc=acc))
            parts.append(
                '<text x="{x:.1f}" y="{y:.1f}" font-size="12.5" font-weight="700" '
                'class="ag-title" text-anchor="middle">{t}</text>'.format(
                    x=x + w / 2, y=y + 24, t=_esc(nd["t"])))
            # 技术小字折行(最多 2 行)
            s = nd.get("s", "")
            line_max = max(6, int(w / 11))
            lines, cur = [], ""
            for ch in s:
                cur += ch
                if len(cur) >= line_max:
                    lines.append(cur); cur = ""
            if cur:
                lines.append(cur)
            for i, ln in enumerate(lines[:2]):
                parts.append(
                    '<text x="{x:.1f}" y="{y:.1f}" font-size="9.5" class="ag-sub" '
                    'text-anchor="middle">{ln}</text>'.format(
                        x=x + w / 2, y=y + 42 + i * 13, ln=_esc(ln)))
    parts.append('</svg>')
    return "\n".join(parts)


def _scenario_cards_svg(sc):
    """(回退)分组卡片矩阵:每个技术点分组一列,列内竖排若干节点。"""
    groups = sc["groups"]
    ng = len(groups)
    acc = sc["color"]
    VBW = 1080
    pad = 30
    gap = 20
    col_w = (VBW - pad * 2 - gap * (ng - 1)) / ng
    top = 96                 # 标题区高度
    ghead = 40               # 组标题条高
    node_h = 76
    node_gap = 12
    max_nodes = max(len(g["nodes"]) for g in groups)
    col_body = ghead + 14 + max_nodes * (node_h + node_gap)
    VBH = top + col_body + 40
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=int(VBH)),
        '<defs><filter id="scSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.08"/></filter></defs>',
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(
            w=VBW, h=int(VBH)),
        '<text x="{x}" y="42" font-size="20" font-weight="800" '
        'class="ag-title">{cn} · 核心技术点</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">{t}</text>'.format(
            x=pad, t=_esc(sc["layer"] + " · " + sc["en"])),
    ]
    for gi, g in enumerate(groups):
        cx = pad + gi * (col_w + gap)
        # 组标题条
        parts.append(
            '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{gh}" rx="12" '
            'fill="{acc}" opacity="0.12"/>'.format(x=cx, y=top, w=col_w, gh=ghead, acc=acc))
        parts.append(
            '<text x="{x:.1f}" y="{y}" font-size="13.5" font-weight="700" '
            'fill="{acc}" text-anchor="middle">{g}</text>'.format(
                x=cx + col_w / 2, y=top + 26, acc=acc, g=_esc(g["g"])))
        ny = top + ghead + 14
        for nd in g["nodes"]:
            parts.append(
                '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{nh}" rx="12" '
                'class="ag-card" stroke="#ececf1" filter="url(#scSoft)"/>'.format(
                    x=cx, y=ny, w=col_w, nh=node_h))
            parts.append(
                '<text x="{x:.1f}" y="{y}" font-size="12.5" font-weight="700" '
                'class="ag-title">{t}</text>'.format(
                    x=cx + 14, y=ny + 26, t=_esc(nd["t"])))
            # 要点自动折行(按字数)
            pts = nd["p"]
            line_max = int(col_w / 11)
            lines, cur = [], ""
            for ch in pts:
                cur += ch
                if len(cur) >= line_max:
                    lines.append(cur)
                    cur = ""
            if cur:
                lines.append(cur)
            for li, ln in enumerate(lines[:2]):
                parts.append(
                    '<text x="{x:.1f}" y="{y}" font-size="10.5" class="ag-sub">'
                    '{ln}</text>'.format(x=cx + 14, y=ny + 46 + li * 16, ln=_esc(ln)))
            ny += node_h + node_gap
    parts.append('</svg>')
    return "\n".join(parts)


def _dim_split(d):
    """把深度文字 d 按语义切分为(trade, scale, fail)三维句子列表,供 HTML/SVG 复用。
      - 失败模式/坑/风险 → fail(⚠ 失败模式)
      - 含数字 / 倍 / 级 / QPS / % → scale(◆ 关键量级)
      - 其余 → trade(⚖ 权衡取舍),兜底保证 trade 不空。
    切句以中文句号/分号为界。"""
    import re as _re
    raw = [s for s in _re.split(r"[。;;]", d or "") if s.strip()]
    fail, scale, trade = [], [], []
    for s in raw:
        s = s.strip()
        if _re.search(r"失败模式|坑|风险|否则|拖垮|打垮|打满|击穿|雪崩|超卖|少卖|脏数据|竞态", s):
            fail.append(s)
        elif _re.search(r"[0-9]|倍|数量级|QPS|万|亿|%|毫秒|ms|级", s):
            scale.append(s)
        else:
            trade.append(s)
    if not trade and raw:
        trade.append(raw[0].strip())
    return trade, scale, fail


def _dim_badges(d):
    """把一段深度文字 d 拆成「权衡 / 量级 / 失败模式」三维徽标 HTML(分组卡回退用)。"""
    if not d:
        return ""
    trade, scale, fail = _dim_split(d)
    dims = [
        ("trade", "⚖", "权衡取舍",trade),
        ("scale", "◆", "关键量级", scale),
        ("fail", "⚠", "失败模式", fail),
    ]
    cells = []
    for cls, ico, label, arr in dims:
        if not arr:
            continue
        txt = "。".join(arr)
        cells.append(
            '<div class="dm dm-{c}"><span class="dm-h">{i} {l}</span>'
            '<span class="dm-t">{t}。</span></div>'.format(
                c=cls, i=ico, l=label, t=_esc(txt)))
    if not cells:
        return ""
    return '<div class="dims">{c}</div>'.format(c="".join(cells))


def _scenario_tension_svg(sc):
    """核心张力对抗图:把场景的本质矛盾画成左右双力对抗 + 中间权衡点。
    读 sc["tension"] = {left:{label,items[]}, right:{label,items[]}, core}。复用 ag-* 主题 class。"""
    ts = sc.get("tension")
    if not ts:
        return ""
    acc = sc["color"]
    L = ts.get("left", {})
    R = ts.get("right", {})
    core = ts.get("core", "")
    li = L.get("items", []) or []
    ri = R.get("items", []) or []
    VBW = 1080
    rows = max(len(li), len(ri), 1)
    top = 118
    row_h = 40
    VBH = top + rows * row_h + (110 if core else 30)
    cx = VBW / 2
    colw = 400
    lx = 40
    rx = VBW - 40 - colw
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=int(VBH)),
        '<defs><filter id="tnSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.10"/></filter>'
        '<marker id="tnArr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" '
        'markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="{acc}"/>'
        '</marker></defs>'.format(acc=acc),
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(
            w=VBW, h=int(VBH)),
        '<text x="40" y="42" font-size="20" font-weight="800" class="ag-title">'
        '{cn} · 核心张力</text>'.format(cn=_esc(sc["cn"])),
        '<text x="40" y="70" font-size="12.5" class="ag-sub">'
        '本质是一对相互拉扯的力 · 架构决策即在两端之间取平衡点</text>',
        '<rect x="{x}" y="88" width="{cw}" height="30" rx="8" fill="{acc}" '
        'opacity="0.16"/>'.format(x=lx, cw=colw, acc=acc),
        '<text x="{tx:.1f}" y="108" font-size="14" font-weight="800" fill="{acc}" '
        'text-anchor="middle">{l}</text>'.format(
            tx=lx + colw / 2, acc=acc, l=_esc(L.get("label", "力 A"))),
        '<rect x="{x:.1f}" y="88" width="{cw}" height="30" rx="8" fill="{acc}" '
        'opacity="0.16"/>'.format(x=rx, cw=colw, acc=acc),
        '<text x="{tx:.1f}" y="108" font-size="14" font-weight="800" fill="{acc}" '
        'text-anchor="middle">{r}</text>'.format(
            tx=rx + colw / 2, acc=acc, r=_esc(R.get("label", "力 B"))),
    ]
    for i in range(rows):
        y = top + i * row_h
        if i < len(li):
            parts.append(
                '<rect x="{x}" y="{y}" width="{cw}" height="{rh}" rx="8" '
                'fill="{acc}" opacity="0.07" filter="url(#tnSoft)"/>'.format(
                    x=lx, y=y, cw=colw, rh=row_h - 8, acc=acc))
            parts.append(
                '<text x="{tx:.1f}" y="{ty}" font-size="12" class="ag-title" '
                'text-anchor="middle">{s}</text>'.format(
                    tx=lx + colw / 2, ty=y + 21, s=_esc(li[i])))
        if i < len(ri):
            parts.append(
                '<rect x="{x:.1f}" y="{y}" width="{cw}" height="{rh}" rx="8" '
                'fill="{acc}" opacity="0.07" filter="url(#tnSoft)"/>'.format(
                    x=rx, y=y, cw=colw, rh=row_h - 8, acc=acc))
            parts.append(
                '<text x="{tx:.1f}" y="{ty}" font-size="12" class="ag-title" '
                'text-anchor="middle">{s}</text>'.format(
                    tx=rx + colw / 2, ty=y + 21, s=_esc(ri[i])))
    my = top + rows * row_h / 2
    parts.append(
        '<path d="M{x1:.1f} {y:.1f} L{x2:.1f} {y:.1f}" stroke="{acc}" '
        'stroke-width="2" marker-end="url(#tnArr)"/>'.format(
            x1=lx + colw + 12, y=my, x2=cx - 14, acc=acc))
    parts.append(
        '<path d="M{x1:.1f} {y:.1f} L{x2:.1f} {y:.1f}" stroke="{acc}" '
        'stroke-width="2" marker-end="url(#tnArr)"/>'.format(
            x1=rx - 12, y=my, x2=cx + 14, acc=acc))
    parts.append(
        '<circle cx="{cx:.1f}" cy="{y:.1f}" r="7" fill="{acc}"/>'.format(
            cx=cx, y=my, acc=acc))
    parts.append(
        '<text x="{cx:.1f}" y="{y:.1f}" font-size="11" font-weight="800" '
        'fill="{acc}" text-anchor="middle">⚔ 权衡点</text>'.format(
            cx=cx, y=my - 16, acc=acc))
    if core:
        by = top + rows * row_h + 20
        parts.append(
            '<rect x="40" y="{y}" width="{w}" height="66" rx="12" fill="{acc}" '
            'opacity="0.10" stroke="{acc}" stroke-width="1.2"/>'.format(
                y=by, w=VBW - 80, acc=acc))
        cline = []
        cur = ""
        for ch in core:
            cur += ch
            if len(cur) >= 44:
                cline.append(cur)
                cur = ""
        if cur:
            cline.append(cur)
        parts.append(
            '<text x="60" y="{ty}" font-size="12.5" font-weight="700" '
            'fill="{acc}">◆ 本质矛盾</text>'.format(ty=by + 26, acc=acc))
        for ci, ln in enumerate(cline[:2]):
            parts.append(
                '<text x="150" y="{ty}" font-size="12.5" class="ag-title">'
                '{ln}</text>'.format(ty=by + 26 + ci * 20, ln=_esc(ln)))
    parts.append('</svg>')
    return "\n".join(parts)


def _scenario_funnel_svg(sc):
    """容量漏斗量级图:逐级收窄的横条,体现请求从入口到有效结果层层过滤的数量级坍缩。
    读 sc["funnel"] = [{stage, qps, note}, ...],复用 ag-* 主题 class。"""
    fn = sc.get("funnel") or []
    if not fn:
        return ""
    acc = sc["color"]
    VBW = 1080
    pad = 40
    top = 92
    row_h = 74
    row_gap = 16
    n = len(fn)
    VBH = top + n * (row_h + row_gap) + 30
    cx = VBW / 2
    w_max = VBW - pad * 2
    w_min = w_max * 0.30
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=int(VBH)),
        '<defs><filter id="fnSoft" x="-6%" y="-6%" width="112%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#0a0a0a" '
        'flood-opacity="0.10"/></filter></defs>',
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(
            w=VBW, h=int(VBH)),
        '<text x="{x}" y="42" font-size="20" font-weight="800" '
        'class="ag-title">{cn} · 容量漏斗</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">'
        '入口洪峰到有效结果的逐级过滤 · 每一层都在用最小代价挡掉注定失败的请求</text>'.format(x=pad),
    ]
    for i, st in enumerate(fn):
        # 逐级线性收窄
        frac = 1.0 if n == 1 else (n - 1 - i) / (n - 1)
        w = w_min + (w_max - w_min) * frac
        y = top + i * (row_h + row_gap)
        x = cx - w / 2
        # 透明度随深度略增,视觉上强调收敛
        op = 0.14 + 0.10 * (i / max(1, n - 1))
        parts.append(
            '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{rh}" rx="14" '
            'fill="{acc}" opacity="{op:.3f}" stroke="{acc}" stroke-width="1.2" '
            'filter="url(#fnSoft)"/>'.format(x=x, y=y, w=w, rh=row_h, acc=acc, op=op))
        parts.append(
            '<text x="{cx:.1f}" y="{y}" font-size="13.5" font-weight="700" '
            'class="ag-title" text-anchor="middle">{s}</text>'.format(
                cx=cx, y=y + 27, s=_esc(st["stage"])))
        parts.append(
            '<text x="{cx:.1f}" y="{y}" font-size="18" font-weight="800" '
            'fill="{acc}" text-anchor="middle">{q}</text>'.format(
                cx=cx, y=y + 52, acc=acc, q=_esc(st["qps"])))
        note = st.get("note", "")
        if note:
            parts.append(
                '<text x="{nx:.1f}" y="{y}" font-size="11" class="ag-sub" '
                'text-anchor="start">{nt}</text>'.format(
                    nx=x + w + 12, y=y + row_h / 2 + 4, nt=_esc(note)))
        # 收窄导引箭头(下一级)
        if i < n - 1:
            ay = y + row_h
            parts.append(
                '<path d="M{cx:.1f} {y1} L{cx:.1f} {y2}" stroke="{acc}" '
                'stroke-width="1.4" opacity="0.5" marker-end="url(#fnArr)"/>'.format(
                    cx=cx, y1=ay + 1, y2=ay + row_gap - 2, acc=acc))
    parts.insert(2,
        '<defs><marker id="fnArr" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" '
        'fill="{acc}" opacity="0.6"/></marker></defs>'.format(acc=acc))
    parts.append('</svg>')
    return "\n".join(parts)


def _scenario_sections(sc):
    """把场景的专业维度渲染成【图形】而非文本罗列。主全景图已含数据流拓扑 +
    技术矩阵 + 核心张力(推拉权衡),这里再补两张关键分图:分层存储架构图
    (datamodel)与演进时间轴阶梯图(roadmap)。文字仅作图注。字段缺失则跳过。"""
    out = []
    req = sc.get("req")
    if req:
        out.append(_render_req(req))
    dm = sc.get("datamodel")
    if dm:
        out.append(
            '<div class="arch-canvas">{}</div>'.format(_svg_storage_layers(sc)))
    rm = sc.get("roadmap")
    if rm:
        out.append(
            '<div class="arch-canvas">{}</div>'.format(_svg_roadmap_timeline(sc)))
    pf = sc.get("pitfalls")
    if pf:
        out.append(_render_pitfalls(pf))
    tk = sc.get("takeaways")
    if tk:
        out.append(_render_takeaways(tk))
    return "".join(out)


def _render_req(req):
    """需求根基:功能需求(func)+ 质量指标表(quality,带阈值+理由)+ 业务约束(cons)。
    这是整个论证链的地基——先讲清要解决什么、指标卡在哪、有哪些硬约束,
    后面的架构 / 踩坑 / 心法才有据可依。"""
    func = req.get("func", [])
    quality = req.get("quality", [])
    cons = req.get("cons", [])
    parts = ['<div class="sc-sec"><h2>需求根基</h2><div class="req-grid">']
    if func:
        lis = "".join('<li>{}</li>'.format(_esc(x)) for x in func)
        parts.append(
            '<div class="req-col"><h3>功能需求</h3><ul>{}</ul></div>'.format(lis))
    if cons:
        lis = "".join('<li>{}</li>'.format(_esc(x)) for x in cons)
        parts.append(
            '<div class="req-col"><h3>业务约束 / 难点</h3>'
            '<ul class="cons">{}</ul></div>'.format(lis))
    if quality:
        rows = "".join(
            '<tr><td class="qk">{k}</td><td class="qv">{v}</td><td>{n}</td></tr>'.format(
                k=_esc(q["k"]), v=_esc(q["v"]), n=_esc(q.get("n", "")))
            for q in quality)
        parts.append(
            '<div class="req-col req-wide"><h3>质量指标</h3>'
            '<table class="qtab"><thead><tr><th>维度</th><th>目标</th>'
            '<th>为什么是这个量级</th></tr></thead><tbody>{}</tbody></table></div>'.format(rows))
    parts.append('</div></div>')
    return "".join(parts)


def _render_pitfalls(pf):
    """典型反模式:把真实工程里踩过的坑列成红叉卡片,警示"看似合理实则致命"的做法。"""
    lis = "".join('<li>{}</li>'.format(_esc(x)) for x in pf)
    return (
        '<div class="sc-sec sc-pitfall"><h2>典型反模式</h2>'
        '<ul class="pit">{}</ul></div>'.format(lis))


def _render_takeaways(tk):
    """可迁移心法:从本场景提炼、可复用到其他系统的设计原则,绿勾卡片收尾。"""
    lis = "".join('<li>{}</li>'.format(_esc(x)) for x in tk)
    return (
        '<div class="sc-sec sc-takeaway"><h2>可迁移心法</h2>'
        '<ul class="tk">{}</ul></div>'.format(lis))


def _svg_storage_layers(sc):
    """分层存储架构图:一行一个数据实体,左=实体,中=存储选型胶囊,右=选型理由,
    按"离用户越近越靠上"从时间线到源站纵向堆叠,右侧标注读写热度。纯图形表达。"""
    acc = sc["color"]
    dm = sc["datamodel"]
    VBW = 1080
    pad = 26
    top = 92
    row_h = 62
    row_gap = 14
    n = len(dm)
    VBH = int(top + n * (row_h + row_gap) + 24)
    col_e = pad + 6                      # 实体列 x
    col_e_w = 190
    col_s = col_e + col_e_w + 20         # 存储胶囊列 x
    col_s_w = 240
    col_r = col_s + col_s_w + 20         # 理由列 x
    col_r_w = VBW - pad - col_r
    body = []
    for i, d in enumerate(dm):
        ry = top + i * (row_h + row_gap)
        cy = ry + row_h / 2
        # 行底卡
        body.append(
            '<rect x="{x}" y="{y:.1f}" width="{w}" height="{h}" rx="12" '
            'class="ag-card" filter="url(#stSoft)"/>'.format(
                x=pad, y=ry, w=VBW - pad * 2, h=row_h))
        # 序号圆点
        body.append(
            '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="13" fill="{acc}" opacity="0.14"/>'.format(
                cx=col_e + 4, cy=cy, acc=acc))
        body.append(
            '<text x="{cx:.1f}" y="{cy:.1f}" font-size="12" font-weight="800" '
            'fill="{acc}" text-anchor="middle">{i}</text>'.format(
                cx=col_e + 4, cy=cy + 4, acc=acc, i=i + 1))
        # 实体名
        body.append(
            '<text x="{x}" y="{cy:.1f}" font-size="14" font-weight="700" '
            'class="ag-title">{e}</text>'.format(x=col_e + 26, cy=cy + 5, e=_esc(d["e"])))
        # 存储选型胶囊
        body.append(
            '<rect x="{x}" y="{y:.1f}" width="{w}" height="30" rx="15" '
            'fill="{acc}" opacity="0.12"/>'.format(x=col_s, y=cy - 15, w=col_s_w, acc=acc))
        body.append(
            '<text x="{cx:.1f}" y="{cy:.1f}" font-size="13" font-weight="700" '
            'fill="{acc}" text-anchor="middle">{s}</text>'.format(
                cx=col_s + col_s_w / 2, cy=cy + 4, acc=acc, s=_esc(d["s"])))
        # 箭头 实体→存储
        body.append(
            '<path d="M{x1:.1f},{cy:.1f} L{x2:.1f},{cy:.1f}" stroke="{acc}" '
            'stroke-width="1.4" marker-end="url(#stArr)" opacity="0.7"/>'.format(
                x1=col_e + col_e_w - 6, cy=cy, x2=col_s - 4, acc=acc))
        # 理由(短语,一行)
        rl = _sv_wrap(d["r"], 16)[:1]
        for li, ln in enumerate(rl):
            body.append(
                '<text x="{x}" y="{y:.1f}" font-size="11.5" class="ag-sub">{ln}</text>'.format(
                    x=col_r, y=cy - 4 + li * 15 - (len(rl) - 1) * 7, ln=_esc(ln)))
    head = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=VBH),
        '<defs><filter id="stSoft" x="-4%" y="-30%" width="108%" height="160%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="5" flood-color="#0a0a0a" '
        'flood-opacity="0.07"/></filter>'
        '<marker id="stArr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" '
        'fill="{acc}"/></marker></defs>'.format(acc=acc),
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(w=VBW, h=VBH),
        '<text x="{x}" y="42" font-size="20" font-weight="800" class="ag-title">'
        '{cn} · 数据模型与存储选择</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">'
        '按访问模式选存储 · 左实体 → 中选型 → 右理由</text>'.format(x=pad),
    ]
    return "\n".join(head + body + ['</svg>'])


def _svg_roadmap_timeline(sc):
    """演进时间轴阶梯图:MVP→成长期→成熟期横向排列,阶段节点连成上升阶梯,
    每阶段下挂焦点标题 + 细节说明。用递增的柱高直观表达架构复杂度随阶段抬升。"""
    acc = sc["color"]
    rm = sc["roadmap"]
    VBW = 1080
    pad = 26
    top = 100
    n = len(rm)
    gap = 22
    col_w = (VBW - pad * 2 - gap * (n - 1)) / n
    base_y = top + 46                    # 阶梯基线
    step_h = 30                          # 每阶递增高度
    max_bar = (n - 1) * step_h + 40
    card_top = base_y + 20
    card_h = 96
    VBH = int(card_top + card_h + 24)
    body = []
    # 阶梯基线
    body.append(
        '<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{acc}" '
        'stroke-width="1.2" opacity="0.3"/>'.format(
            x1=pad, y=base_y, x2=VBW - pad, acc=acc))
    for i, r in enumerate(rm):
        cx = pad + i * (col_w + gap)
        bar_h = 40 + i * step_h
        # 递增阶梯柱(表达复杂度抬升)
        body.append(
            '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="8" '
            'fill="{acc}" opacity="{op:.2f}"/>'.format(
                x=cx,y=base_y - bar_h, w=col_w, h=bar_h, acc=acc,
                op=0.14 + i * 0.12))
        # 阶段徽标
        body.append(
            '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="26" rx="13" '
            'fill="{acc}"/>'.format(x=cx + col_w / 2 - 46, y=base_y - bar_h - 13, w=92, acc=acc))
        body.append(
            '<text x="{cx:.1f}" y="{y:.1f}" font-size="13" font-weight="800" '
            'fill="#ffffff" text-anchor="middle">{st}</text>'.format(
                cx=cx + col_w / 2, y=base_y - bar_h + 4, st=_esc(r["stage"])))
        # 阶段间连接箭头
        if i < n - 1:
            nx = pad + (i + 1) * (col_w + gap)
            body.append(
                '<path d="M{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f}" stroke="{acc}" '
                'stroke-width="1.6" marker-end="url(#rmArr)" opacity="0.8"/>'.format(
                    x1=cx + col_w + 2, y=base_y - 14, x2=nx - 4, acc=acc))
        # 焦点 + 细节卡
        body.append(
            '<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="12" '
            'class="ag-card" filter="url(#rmSoft)"/>'.format(
                x=cx, y=card_top, w=col_w, h=card_h))
        body.append(
            '<text x="{cx:.1f}" y="{y}" font-size="14.5" font-weight="800" '
            'fill="{acc}" text-anchor="middle">{f}</text>'.format(
                cx=cx + col_w / 2, y=card_top + 28, acc=acc, f=_esc(r["focus"])))
        body.append(
            '<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" '
            'class="ag-band" stroke-width="1"/>'.format(
                x1=cx + 16, y=card_top + 40, x2=cx + col_w - 16))
        dl = [s for s in r["detail"].split("、") if s][:3]
        for li, ln in enumerate(dl):
            body.append(
                '<text x="{cx:.1f}" y="{y}" font-size="11.5" class="ag-sub" '
                'text-anchor="middle">{ln}</text>'.format(
                    cx=cx + col_w / 2, y=card_top + 62 + li * 17, ln=_esc(ln)))
    head = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="arch-svg" '
        'viewBox="0 0 {w} {h}" font-family="-apple-system,BlinkMacSystemFont,'
        "'SF Pro Text','PingFang SC',sans-serif\">".format(w=VBW, h=VBH),
        '<defs><filter id="rmSoft" x="-4%" y="-6%" width="108%" height="112%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="5" flood-color="#0a0a0a" '
        'flood-opacity="0.07"/></filter>'
        '<marker id="rmArr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" '
        'fill="{acc}"/></marker></defs>'.format(acc=acc),
        '<rect x="0" y="0" width="{w}" height="{h}" class="ag-bg"/>'.format(w=VBW, h=VBH),
        '<text x="{x}" y="42" font-size="20" font-weight="800" class="ag-title">'
        '{cn} · 演进路线</text>'.format(x=pad, cn=_esc(sc["cn"])),
        '<text x="{x}" y="70" font-size="12.5" class="ag-sub">'
        '柱高递增 = 架构复杂度逐阶抬升</text>'.format(x=pad),
    ]
    return "\n".join(head + body + ['</svg>'])


def build_scenario_page(sc):
    """为单个业务场景生成自包含子页面 scenarios/<slug>/index.html。
    结构:头部(返回 + 主题切换) + 场景定位 tagline + 架构图 SVG + 核心技术点分组说明。
    复用根页面 ag-* 主题 class 与 atlas-nav-theme 主题持久化。"""
    accent = sc["color"]
    # 顶部唯一架构图 = 端到端数据流「泳道图」(_scenario_flow_svg),
    # 清爽的分层泳道 + 节点 + 有向箭头,对齐 Mermaid 全景图风格;
    # 无 flow 数据时回退到分组卡片矩阵。
    arch = _scenario_domain_svg(sc) if sc.get("domain") else (
        _scenario_flow_svg(sc) if sc.get("flow") else _scenario_cards_svg(sc))

    # ── 核心技术点分组:groups[{g, nodes[{t,p,d}]}] ──
    grp_html = ""
    if sc.get("groups"):
        cards = []
        for grp in sc["groups"]:
            lis = []
            for nd in grp["nodes"]:
                dp = ('<span class="dp">%s</span>' % _esc(nd["d"])) if nd.get("d") else ""
                lis.append('<li><b>%s</b><span>%s</span>%s</li>' % (
                    _esc(nd["t"]), _esc(nd["p"]), dp))
            cards.append('<div class="grp"><h3>%s</h3><ul>%s</ul></div>' % (
                _esc(grp["g"]), "".join(lis)))
        grp_html = ('<div class="sc-sec"><h2>核心技术点</h2>'
                    '<div class="grid">%s</div></div>') % "".join(cards)

    # ── 设计张力:tension{left{label,items},right{label,items},core} ──
    tn_html = ""
    if sc.get("tension"):
        tn = sc["tension"]
        def _tn_side(side, cls):
            its = "".join('<li>%s</li>' % _esc(i) for i in side["items"])
            return ('<div class="tn-side %s"><div class="tn-lbl">%s</div>'
                    '<ul>%s</ul></div>') % (cls, _esc(side["label"]), its)
        core = ('<div class="tn-core">%s</div>' % _esc(tn["core"])) if tn.get("core") else ""
        tn_html = ('<div class="sc-sec"><h2>设计张力</h2>'
                   '<div class="sc-tension"><div class="tn-wrap">%s'
                   '<div class="tn-vs">VS</div>%s</div>%s</div></div>') % (
            _tn_side(tn["left"], "tn-l"), _tn_side(tn["right"], "tn-r"), core)

    # ── 容量漏斗 / 数据流拓扑 / 设计张力等独立图表板块已并入顶部唯一泳道图,不再单独渲染 ──

    # ── 需求根基:req{func[], quality[{k,v,n}], cons[]} ──
    req_html = ""
    if sc.get("req"):
        rq = sc["req"]
        cols = []
        if rq.get("func"):
            fl = "".join('<li>%s</li>' % _esc(x) for x in rq["func"])
            cols.append('<div class="req-col"><h3>功能需求</h3><ul>%s</ul></div>' % fl)
        if rq.get("quality"):
            rows = "".join(
                '<tr><td class="qk">%s</td><td class="qv">%s</td><td>%s</td></tr>' % (
                    _esc(q["k"]), _esc(q["v"]), _esc(q.get("n", "")))
                for q in rq["quality"])
            cols.append('<div class="req-col req-wide"><h3>质量指标</h3>'
                        '<table class="qtab"><tr><th>维度</th><th>目标</th><th>说明</th></tr>'
                        '%s</table></div>' % rows)
        if rq.get("cons"):
            cl = "".join('<li>%s</li>' % _esc(x) for x in rq["cons"])
            cols.append('<div class="req-col req-wide"><h3>关键约束</h3>'
                        '<ul class="cons">%s</ul></div>' % cl)
        req_html = ('<div class="sc-sec"><h2>需求根基</h2>'
                    '<div class="req-grid">%s</div></div>') % "".join(cols)

    # ── 存储选型:datamodel[{e,s,r}] ──
    dm_html = ""
    if sc.get("datamodel"):
        rows = "".join(
            '<tr><td class="de">%s</td><td class="ds">%s</td><td>%s</td></tr>' % (
                _esc(d["e"]), _esc(d["s"]), _esc(d.get("r", "")))
            for d in sc["datamodel"])
        dm_html = ('<div class="sc-sec"><h2>存储选型</h2>'
                   '<table class="dtab"><tr><th>数据实体</th><th>存储方案</th>'
                   '<th>选型理由</th></tr>%s</table></div>') % rows

    # ── 演进路线:roadmap[{stage,focus,detail}] ──
    rm_html = ""
    if sc.get("roadmap"):
        steps = "".join(
            '<div class="rm-step"><span class="rm-stage">%s</span>'
            '<div class="rm-focus">%s</div><div class="rm-detail">%s</div></div>' % (
                _esc(r["stage"]), _esc(r["focus"]), _esc(r.get("detail", "")))
            for r in sc["roadmap"])
        rm_html = ('<div class="sc-sec"><h2>演进路线</h2>'
                   '<div class="rm-wrap">%s</div></div>') % steps

    # ── 常见踩坑:pitfalls[] ──
    pit_html = ""
    if sc.get("pitfalls"):
        lis = "".join('<li>%s</li>' % _esc(x) for x in sc["pitfalls"])
        pit_html = ('<div class="sc-sec sc-pitfall"><h2>常见踩坑</h2>'
                    '<ul class="pit">%s</ul></div>') % lis

    # ── 设计心法:takeaways[] ──
    tk_html = ""
    if sc.get("takeaways"):
        lis = "".join('<li>%s</li>' % _esc(x) for x in sc["takeaways"])
        tk_html = ('<div class="sc-sec sc-takeaway"><h2>设计心法</h2>'
                   '<ul class="tk">%s</ul></div>') % lis

    # ── 一句话洞察:insight ──
    insight_html = ""
    if sc.get("insight"):
        insight_html = ('<div class="sc-sec"><div class="insight">'
                        '<h2>本质洞察</h2><p>%s</p></div></div>') % _esc(sc["insight"])

    # ── 子页只保留顶部唯一一张「端到端数据流泳道图」(arch),
    #    所有文字板块(核心技术点 grp / 本质洞察 insight / 需求根基 req /
    #    常见踩坑 pit / 设计心法 tk)及其余图表板块一律不再渲染 ──
    body_html = ""
    css = """
/* ── Apple 工业风令牌:DEFAULT = 深色(石墨风,对齐 doris 项目页)── */
:root{--c-bg:#1c1c1e;--c-bg2:#161618;--c-panel:#242426;--c-panel2:#2c2c2e;
  --c-line:rgba(255,255,255,.11);--c-line2:rgba(255,255,255,.17);
  --c-ink:#f5f5f7;--c-sub:#c4c4c9;--c-ink3:#8e8e93;--c-soft:#2c2c2e;
  --c-glass:rgba(28,28,30,.82);
  --c-shadow-sm:0 1px 2px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.28)}
/* ── LIGHT:Apple Store 风(白/浅灰 + 柔投影)── */
:root[data-theme=light]{--c-bg:#f5f5f7;--c-bg2:#fbfbfd;--c-panel:#ffffff;--c-panel2:#f0f0f3;
  --c-line:rgba(0,0,0,.09);--c-line2:rgba(0,0,0,.14);
  --c-ink:#1d1d1f;--c-sub:#424245;--c-ink3:#86868b;--c-soft:#f0f0f3;
  --c-glass:rgba(255,255,255,.9);
  --c-shadow-sm:0 1px 2px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.05)}
*{box-sizing:border-box}
body{margin:0;background:var(--c-bg);color:var(--c-ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:-.01em;transition:background .25s,color .25s}
.wrap{max-width:1120px;margin:0 auto;padding:28px 24px 64px}
header.top{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:14px;
  padding:12px 24px;background:var(--c-glass);
  backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px);
  border-bottom:1px solid var(--c-line)}
header.top .logo{display:inline-flex;align-items:center;flex:none}
header.top .spacer{flex:1}
.brand-intro{display:flex;flex-direction:column;align-items:flex-start;margin-left:6px;min-width:0}
.brand-intro .bt{font-size:15px;font-weight:700;color:var(--c-ink);line-height:1.3}
.brand-intro .bs{margin-top:3px;font-size:11.5px;color:var(--c-sub);line-height:1.5}
.icobtn{width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-sub);cursor:pointer;display:inline-grid;
  place-items:center;font-size:16px;flex:none;text-decoration:none;transition:.15s}
.icobtn:hover{color:var(--c-ink);border-color:var(--accent)}
.tt-ico{font-size:16px;line-height:1}.tt-sun{display:none}
:root[data-theme=dark] .tt-moon{display:none}:root[data-theme=dark] .tt-sun{display:inline}
.hero{padding:18px 22px;border-radius:16px;background:var(--c-panel);border:1px solid var(--c-line);border-left:4px solid var(--accent);margin-bottom:26px}
.hero .lay{font-size:12px;color:var(--accent);font-weight:600;letter-spacing:.4px}
.hero h1{margin:6px 0 8px;font-size:24px;letter-spacing:-.3px}
.hero .en{color:var(--c-sub);font-size:13px}
.hero .tag{margin-top:10px;color:var(--c-ink);font-size:14.5px;line-height:1.7}
.arch-canvas{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;padding:18px;margin-bottom:30px;overflow:auto}
.arch-svg{width:100%;height:auto;display:block}
.arch-svg .ag-bg{fill:var(--c-panel)}
.arch-svg .ag-card{fill:var(--c-panel);stroke:var(--c-line);stroke-width:1.2}
.arch-svg .ag-band{fill:var(--c-soft)}
.arch-svg .ag-sub{fill:var(--c-sub)}
.arch-svg .ag-title{fill:var(--c-ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.grp{background:var(--c-panel);border:1px solid var(--c-line);border-radius:14px;padding:16px 18px}
.grp h3{margin:0 0 12px;font-size:15px;color:var(--accent);padding-bottom:8px;border-bottom:1px solid var(--c-line)}
.grp ul{list-style:none;margin:0;padding:0}
.grp li{padding:8px 0;border-bottom:1px dashed var(--c-line)}
.grp li:last-child{border-bottom:none}
.grp li b{display:block;font-size:13.5px;color:var(--c-ink);margin-bottom:2px}
.grp li span{font-size:12.5px;color:var(--c-sub);line-height:1.6}
.grp li .dp{display:block;margin-top:7px;padding:9px 11px;font-size:12px;line-height:1.7;
  color:var(--c-ink);background:var(--c-soft);border-left:2px solid var(--accent);border-radius:6px}
.dims{display:flex;flex-direction:column;gap:6px;margin-top:9px}
.dm{display:flex;flex-direction:column;gap:2px;padding:7px 11px;border-radius:8px;
  border-left:3px solid var(--c-line);background:var(--c-soft)}
.dm-h{font-size:11px;font-weight:800;letter-spacing:.02em;opacity:.92}
.dm-t{font-size:11.5px;line-height:1.65;color:var(--c-sub)}
.dm-trade{border-left-color:var(--accent)}
.dm-trade .dm-h{color:var(--accent)}
.dm-scale{border-left-color:#2ea043}
.dm-scale .dm-h{color:#2ea043}
.dm-fail{border-left-color:#e0562d}
.dm-fail .dm-h{color:#e0562d}
.insight{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;
  padding:20px 24px;margin-top:26px;border-top:3px solid var(--accent)}
.insight h2{margin:0 0 10px;font-size:16px;color:var(--c-ink)}
.insight p{margin:0;font-size:13.5px;line-height:1.85;color:var(--c-sub)}
.flow-desc{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;padding:18px 22px;margin-bottom:26px}
.flow-desc h2{margin:0 0 6px;font-size:16px;color:var(--c-ink)}
.fl-hint{margin:0 0 14px;font-size:12.5px;color:var(--c-sub)}
.flow-desc .fl-hint .fl-b{color:#c0392b;font-weight:600}
.sc-sec{margin-top:30px}
.sc-sec>h2{margin:0 0 14px;font-size:18px;color:var(--c-ink);padding-left:11px;border-left:4px solid var(--accent)}
.sc-essence{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;padding:20px 24px;border-top:3px solid var(--accent)}
.sc-essence p{margin:0;font-size:14px;line-height:1.9;color:var(--c-sub)}
.req-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.req-col{background:var(--c-panel);border:1px solid var(--c-line);border-radius:14px;padding:16px 18px}
.req-col.req-wide{grid-column:1/-1}
.req-col h3{margin:0 0 12px;font-size:14px;color:var(--accent)}
.req-col ul{list-style:none;margin:0;padding:0}
.req-col ul li{padding:6px 0 6px 18px;position:relative;font-size:13px;line-height:1.7;color:var(--c-sub);border-bottom:1px dashed var(--c-line)}
.req-col ul li:last-child{border-bottom:none}
.req-col ul li:before{content:"";position:absolute;left:2px;top:13px;width:6px;height:6px;border-radius:50%;background:var(--accent)}
.req-col ul.cons li:before{background:#e0562d}
.qtab,.dtab{width:100%;border-collapse:collapse;font-size:12.5px}
.qtab th,.dtab th{text-align:left;padding:9px 12px;color:var(--c-sub);font-weight:700;border-bottom:2px solid var(--c-line);font-size:12px}
.qtab td,.dtab td{padding:9px 12px;border-bottom:1px solid var(--c-line);line-height:1.65;color:var(--c-sub);vertical-align:top}
.qtab .qk{color:var(--c-ink);font-weight:700;white-space:nowrap}
.qtab .qv{color:var(--accent);font-weight:600;white-space:nowrap}
.dtab{background:var(--c-panel);border:1px solid var(--c-line);border-radius:14px;overflow:hidden}
.dtab .de{color:var(--c-ink);font-weight:700;white-space:nowrap}
.dtab .ds{color:var(--accent);font-weight:600;white-space:nowrap}
.sc-tension{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;padding:20px 24px}
.tn-wrap{display:flex;align-items:stretch;gap:0;position:relative}
.tn-side{flex:1;padding:14px 16px;border-radius:12px;background:var(--c-soft)}
.tn-side.tn-l{border:1px solid var(--accent)}
.tn-side.tn-r{border:1px solid #2ea043}
.tn-lbl{font-size:13.5px;font-weight:800;margin-bottom:10px}
.tn-l .tn-lbl{color:var(--accent)}.tn-r .tn-lbl{color:#2ea043}
.tn-side ul{list-style:none;margin:0;padding:0}
.tn-side li{padding:5px 0;font-size:12.5px;line-height:1.6;color:var(--c-sub);border-bottom:1px dashed var(--c-line)}
.tn-side li:last-child{border-bottom:none}
.tn-vs{align-self:center;margin:0 14px;font-size:12px;font-weight:800;color:var(--c-sub);background:var(--c-bg);border:1px solid var(--c-line);border-radius:50%;width:38px;height:38px;display:grid;place-items:center;flex:none}
.tn-core{margin-top:16px;padding:12px 16px;font-size:13px;line-height:1.75;color:var(--c-ink);background:var(--c-soft);border-left:3px solid var(--accent);border-radius:8px}
.sc-pitfall ul.pit{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px}
.sc-pitfall ul.pit li{padding:11px 14px 11px 34px;position:relative;font-size:12.5px;line-height:1.65;color:var(--c-sub);background:var(--c-panel);border:1px solid var(--c-line);border-left:3px solid #e0562d;border-radius:10px}
.sc-pitfall ul.pit li:before{content:"\\2715";position:absolute;left:13px;top:11px;color:#e0562d;font-weight:800;font-size:12px}
.rm-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.rm-step{background:var(--c-panel);border:1px solid var(--c-line);border-radius:14px;padding:16px 18px;border-top:3px solid var(--accent)}
.rm-stage{font-size:12px;font-weight:800;color:#fff;background:var(--accent);display:inline-block;padding:3px 12px;border-radius:20px;margin-bottom:10px}
.rm-focus{font-size:14px;font-weight:700;color:var(--c-ink);margin-bottom:7px}
.rm-detail{font-size:12.5px;line-height:1.7;color:var(--c-sub)}
.sc-takeaway ul.tk{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px}
.sc-takeaway ul.tk li{padding:11px 14px 11px 34px;position:relative;font-size:12.5px;line-height:1.65;color:var(--c-ink);background:var(--c-soft);border-radius:10px}
.sc-takeaway ul.tk li:before{content:"\\2713";position:absolute;left:13px;top:11px;color:#2ea043;font-weight:800;font-size:12px}
footer{margin-top:40px;text-align:center;color:var(--c-sub);font-size:12px}
"""
    js = (
        "(function(){var r=document.documentElement,KEY=\"atlas-nav-theme\";"
        "function ap(t){if(t===\"light\")r.setAttribute(\"data-theme\",\"light\");"
        "else r.removeAttribute(\"data-theme\");}"
        "var s=\"dark\";try{s=localStorage.getItem(KEY)||\"dark\";}catch(e){}ap(s);"
        "var tt=document.getElementById(\"tt\");"
        "if(tt)tt.onclick=function(){var n=r.getAttribute(\"data-theme\")===\"light\"?\"dark\":\"light\";"
        "ap(n);try{localStorage.setItem(KEY,n);}catch(e){}};})();")
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 40 40\'%3E%3Crect width=\'40\' height=\'40\' rx=\'9\' fill=\'%23bfe0f5\'/%3E%3Ccircle cx=\'12.5\' cy=\'11.5\' r=\'4\' fill=\'%23fff\'/%3E%3Ccircle cx=\'27.5\' cy=\'11.5\' r=\'4\' fill=\'%23fff\'/%3E%3Ccircle cx=\'12.5\' cy=\'11.5\' r=\'1.6\' fill=\'%23e2e2e6\'/%3E%3Ccircle cx=\'27.5\' cy=\'11.5\' r=\'1.6\' fill=\'%23e2e2e6\'/%3E%3Cpath d=\'M8 19 Q8 9 20 9 Q32 9 32 19 Q32 30 20 31 Q8 30 8 19 Z\' fill=\'%23fff\' stroke=\'%238a8a8f\' stroke-width=\'1.4\'/%3E%3Cellipse cx=\'20\' cy=\'24\' rx=\'5.5\' ry=\'4.2\' fill=\'%23eef1f4\' stroke=\'%238a8a8f\' stroke-width=\'1.2\'/%3E%3Ccircle cx=\'16.5\' cy=\'18\' r=\'1.7\' fill=\'%231d1d1f\'/%3E%3Ccircle cx=\'23.5\' cy=\'18\' r=\'1.7\' fill=\'%231d1d1f\'/%3E%3Cellipse cx=\'20\' cy=\'22.5\' rx=\'2.4\' ry=\'1.8\' fill=\'%231d1d1f\'/%3E%3C/svg%3E">'
        '<title>{cn} · 核心技术点</title>'
        '<script>(function(){{try{{var s=localStorage.getItem("atlas-nav-theme")||"dark";if(s==="light")document.documentElement.setAttribute("data-theme","light");}}catch(e){{}}}})();</script>'
        '<style>{css}</style></head>'
        '<body style="--accent:{accent}">'
        '<header class="top">'
        '<a class="logo" href="../../index.html#scenario" title="返回业务场景导航">'
        '<span class="icobtn"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>'
        '</svg></span></a>'
        '<div class="brand-intro"><div class="bt">业务场景</div>'
        '<div class="bs">分布式系统落地全景 · 核心技术点架构图</div></div>'
        '<div class="spacer"></div>'
        '<button id="tt" class="icobtn" title="切换深色 / 浅色主题" aria-label="切换主题">'
        '<span class="tt-ico tt-moon">&#9790;</span><span class="tt-ico tt-sun">&#9728;</span></button>'
        '</header>'
        '<div class="wrap">'
        '<div class="arch-canvas">{arch}</div>'
        '{body}'
        '<footer>业务场景 · 分布式系统落地全景 · 核心技术点架构图</footer>'
     '</div><script>{js}</script></body></html>'
    ).format(
        cn=_esc(sc["cn"]), css=css, accent=accent, layer=_esc(sc["layer"]),
        en=_esc(sc["en"]), tag=_esc(sc["tagline"]), arch=arch,
        body=body_html, js=js)
    return html


_REL_STYLE = {"own": "实线", "invest": "虚线", "host": "点线", "license": "橙线",
              "author": "实线", "compat": "虚线", "vote": "点线", "derive": "橙线",
              "mentor": "实线箭头", "colleague": "虚线", "lineage": "橙箭头"}


def build_relation_view(model):
    """关系视角内容区:核心/洞察 + 分组实体卡 + 关系图例。
    每个实体把相关项目渲染成可点 chip,点击进入 projects/<key>/index.html。"""
    accent = model["accent"]
    groups = []
    for g in model["groups"]:
        ents = []
        for e in g["entities"]:
            edge = _esc(e.get("edge", e.get("note", "")))
            kind = _esc(e.get("kind", ""))
            # 相关项目 chip(可点下钻);兼容旧单键 proj
            keys = list(e.get("projs", []))
            if e.get("proj") and e["proj"] not in keys:
                keys.insert(0, e["proj"])
            chips = "".join(
                '<a class="re-chip" href="projects/{k}/index.html">{n}</a>'.format(
                    k=k, n=_esc(META.get(k, {}).get("name", k)))
                for k in keys if k in META)
            chip_row = '<span class="re-chips">{c}</span>'.format(c=chips) if chips else ""
            ents.append(
                '<div class="re-ent">'
                '<span class="re-name">{n}</span>'
                '<span class="re-kind">{k}</span>'
                '<span class="re-edge">→ {edge}</span>'
                '{chips}</div>'.format(n=_esc(e["name"]), k=kind, edge=edge, chips=chip_row))
        groups.append(
            '<div class="re-group"><div class="re-glab">{lab}</div>'
            '<div class="re-ents">{ents}</div></div>'.format(
                lab=_esc(g["label"]), ents="".join(ents)))
    legend = "".join(
        '<span class="re-leg"><span class="re-leg-k">{s}</span>{lab}</span>'.format(
            s=_esc(_REL_STYLE.get(typ, "")), lab=_esc(lab))
        for lab, typ in model["relations"])
    return (
        '<div class="relation-view" style="--accent:{a}">'
        '<p class="re-core">{core}</p>'
        '<p class="re-insight">{insight}</p>'
        '<div class="re-legend"><span class="re-leg-lab">关系类型</span>{legend}</div>'
        '<div class="re-groups">{groups}</div>'
        '</div>').format(a=accent, core=_esc(model["core"]),
                         insight=_esc(model["insight"]), legend=legend,
                         groups="".join(groups))


def _search_index(projects):
    idx = []
    layer_title = {k: t for k, t, *_ in LAYERS}
    for p in projects:
        hay = " ".join([p["name"], p["key"], p["desc"],
                        layer_title.get(p["layer"], ""),
                        " ".join(p.get("modules") or [])]).lower()
        idx.append({"id": _gid(p["key"]), "name": p["name"],
                    "nav": p["status"] != "plan", "hay": hay})
    # 业务场景也纳入搜索:命中后高亮并滚动到主导航图上的对应热区。
    for s in SCENARIOS:
        hay = " ".join([s["cn"], s["en"], s["slug"], s.get("layer", ""),
                        s.get("tagline", "")]).lower()
        idx.append({"id": _gid("scen_" + s["slug"]), "name": s["cn"],
                    "nav": True, "hay": hay})
    # 一级导航入口(mode-seg)也纳入搜索:命中后高亮对应视角切换按钮。
    mode_entries = [
        ("project", "项目视角", "project 项目视角 项目 视角"),
        ("topic", "专题视角", "topic 专题视角 主题视角 专题 主题 视角 跨项目专题"),
        ("principles", "系统视角", "principles 系统视角 系统设计 分片 缓存 限流 消息队列"),
        ("basic", "基础原理", "basic 基础原理 原理视角 基础视角 数据结构 算法 基本功"),
        ("scenario", "业务场景", "scenario 业务场景 业务视角 分布式落地 高频场景"),
        ("agent", "AI视角", "agent ai视角 llm & agent llm agent 大模型 智能体 aigc mcp rag"),
        ("standards", "社区视角", "standards 社区视角 标准视角 标准 协议 规范 社区"),
        ("industry", "产业视角", "industry 产业视角 产业 生态"),
        ("people", "学派视角", "people 学派视角 学派 人物"),
    ]
    for m, name, hay in mode_entries:
        idx.append({"id": "m_mode_" + m, "name": name,
                    "nav": True, "hay": hay.lower()})
    return idx


def build_html(projects):
    agg = aggregate(projects)
    return (TEMPLATE
            .replace("__SVG__", build_all_lenses(projects))
            .replace("__LENSSWITCH__", build_lens_switch())
            .replace("__TOPICS__", build_topics_cards())
            .replace("__BASIC__", build_basic_cards())
            .replace("__PRINCIPLES__", build_principles_cards())
            .replace("__AGENT__", build_agent_cards())
            .replace("__SCENARIO__", build_scenarios_cards())
            .replace("__INDUSTRY__", build_relation_view(INDUSTRY))
            .replace("__STANDARDS__", build_relation_view(STANDARDS))
            .replace("__PEOPLE__", build_relation_view(PEOPLE))
            .replace("__INDEX__", json.dumps(_search_index(projects), ensure_ascii=False))
            .replace("__AGG__", json.dumps(agg, ensure_ascii=False))
            .replace("__UPDATED__", agg["updated"] or "—"))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='9' fill='%23bfe0f5'/%3E%3Ccircle cx='12.5' cy='11.5' r='4' fill='%23fff'/%3E%3Ccircle cx='27.5' cy='11.5' r='4' fill='%23fff'/%3E%3Ccircle cx='12.5' cy='11.5' r='1.6' fill='%23e2e2e6'/%3E%3Ccircle cx='27.5' cy='11.5' r='1.6' fill='%23e2e2e6'/%3E%3Cpath d='M8 19 Q8 9 20 9 Q32 9 32 19 Q32 30 20 31 Q8 30 8 19 Z' fill='%23fff' stroke='%238a8a8f' stroke-width='1.4'/%3E%3Cellipse cx='20' cy='24' rx='5.5' ry='4.2' fill='%23eef1f4' stroke='%238a8a8f' stroke-width='1.2'/%3E%3Ccircle cx='16.5' cy='18' r='1.7' fill='%231d1d1f'/%3E%3Ccircle cx='23.5' cy='18' r='1.7' fill='%231d1d1f'/%3E%3Cellipse cx='20' cy='22.5' rx='2.4' ry='1.8' fill='%231d1d1f'/%3E%3C/svg%3E"/>
<title>工程技术图谱 · 计算机体系架构导航</title>
<script>(function(){try{var s=localStorage.getItem("atlas-nav-theme")||"light";if(s==="dark")document.documentElement.setAttribute("data-theme","dark");}catch(e){}})();</script>
<style>
:root{color-scheme:light dark}
:root{
  --c-bg:#fbfbfd; --c-bg2:#f5f5f7; --c-panel:#ffffff; --c-panel2:#f5f5f7;
  --c-line:rgba(0,0,0,.09); --c-line2:rgba(0,0,0,.13);
  --c-ink:#1d1d1f; --c-ink2:#424245; --c-ink3:#86868b;
  --c-brand:#0071e3; --c-brand-ink:#0066cc; --c-hover:rgba(0,0,0,.04);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.10),0 24px 48px rgba(0,0,0,.10);
  --ok:#2f8f5e; --warn:#b8801f;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  --grid-tint:rgba(0,113,227,.07); --grid-tint2:rgba(124,95,230,.06);
}
:root[data-theme="dark"]{
  --c-bg:#0d0d0f; --c-bg2:#111114; --c-panel:#17171a; --c-panel2:#1e1e22;
  --c-line:rgba(255,255,255,.10); --c-line2:rgba(255,255,255,.16);
  --c-ink:#f2f2f5; --c-ink2:#c4c4c9; --c-ink3:#8a8a90;
  --c-brand:#0a84ff; --c-brand-ink:#409cff; --c-hover:rgba(255,255,255,.06);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.5),0 24px 48px rgba(0,0,0,.45);
  --ok:#2dd4a7; --warn:#fbbf24;
  --grid-tint:rgba(10,132,255,.10); --grid-tint2:rgba(139,108,255,.09);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
html{background:var(--c-bg);transition:background-color .3s}
body{font-family:var(--sans);color:var(--c-ink);min-height:100vh;-webkit-font-smoothing:antialiased;
  background:var(--c-bg);transition:background-color .3s,color .3s}
/* 顶栏:极简 · 毛玻璃 · 贴顶(对标 Doris —— logo + 搜索 + 主题钮,不喧宾夺主) */
.chrome{position:sticky;top:0;z-index:20;
  background:color-mix(in srgb,var(--c-bg) 82%,transparent);
  backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px);
  border-bottom:1px solid var(--c-line)}
.topbar{display:flex;align-items:center;gap:16px;padding:13px 30px 11px;position:relative}
.logo{flex:none;width:34px;height:34px;display:flex;align-items:center;justify-content:center}
.logo svg{display:block}
.pb-body{fill:#fff;stroke:#8a8a8f;stroke-width:1.4}
.pb-snout{fill:#eef1f4;stroke:#8a8a8f;stroke-width:1.2}
.pb-ear{fill:#e2e2e6}
.pb-eye{fill:#1d1d1f}
.pb-nose{fill:#1d1d1f}
.brand{font-size:15px;font-weight:700;letter-spacing:-.01em;white-space:nowrap;
  display:inline-flex;align-items:baseline;gap:11px}
.brand-dim{color:var(--c-ink3);font-weight:400;font-size:12.5px;
  padding-left:11px;border-left:1px solid var(--c-line)}
.search{margin-left:auto;width:min(340px,42vw);display:flex;align-items:center;gap:9px;
  background:var(--c-panel);border:1px solid var(--c-line);border-radius:10px;padding:8px 13px;
  transition:border-color .18s,box-shadow .18s}
.search:focus-within{border-color:var(--c-brand);box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand) 16%,transparent)}
.search svg{color:var(--c-ink3);flex:none}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--c-ink);font-size:13.5px;outline:none;font-family:var(--sans)}
.group-switch{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:inline-flex;align-items:center;gap:2px;padding:4px;border-radius:11px;background:var(--c-bg2);border:1px solid var(--c-line);z-index:1}
.group-seg{border:0;background:transparent;color:var(--c-ink3);cursor:pointer;font:700 13px var(--sans);padding:6px 20px;border-radius:8px;white-space:nowrap;transition:.15s}
.group-seg:hover{color:var(--c-ink)}
.group-seg.on{background:var(--c-brand);color:#fff;box-shadow:0 1px 4px color-mix(in srgb,var(--c-brand) 38%,transparent)}
.lensbar{padding:0}
.mode-switch{display:flex;flex-direction:column;align-items:stretch;gap:2px}
.mode-switch::-webkit-scrollbar{display:none}
.mode-group{display:none;flex-direction:column;gap:2px}
.mode-group.on{display:flex;position:relative;padding-left:14px}
/* 二级菜单树状引导线:mode-group 主干竖线 + 每个二级项横向分支 */
.mode-group.on::before{content:"";position:absolute;left:6px;top:12px;bottom:12px;width:1.5px;background:var(--c-line2);pointer-events:none}
.mode-seg{position:relative}
.mode-seg::before{content:"";position:absolute;left:-8px;top:50%;width:8px;height:1.5px;background:var(--c-line2);pointer-events:none}
/* 末项 └ 收尾:遮住其中点以下的主干竖线 */
.mode-group.on>.mode-seg:last-child::after{content:"";position:absolute;left:-8px;top:calc(50% + 1px);bottom:-14px;width:1.5px;background:var(--c-panel);pointer-events:none}
/* 业务视角无二级菜单:该组激活时整个左侧切换区隐藏,内容区占满 */
.side-nav:has(.mode-group.on[data-group="biz"]){display:none}
.mode-clab{font:700 9px var(--mono);color:var(--c-ink3);letter-spacing:.1em;text-transform:uppercase;padding:0 8px 0 4px;white-space:nowrap;opacity:.75}
.mode-div{width:1px;align-self:stretch;margin:4px 8px;background:var(--c-line2)}
.mode-seg{border:0;background:transparent;color:var(--c-ink3);cursor:pointer;font:700 12.5px var(--sans);padding:9px 16px;border-radius:9px;white-space:nowrap;transition:.15s;text-align:center}
.mode-seg:hover{color:var(--c-ink)}
.mode-seg.on{background:var(--accent,var(--c-brand));color:#fff;box-shadow:0 1px 4px color-mix(in srgb,var(--c-brand) 38%,transparent)}
.mode-seg.hit{color:var(--accent,var(--c-brand));box-shadow:0 0 0 2px color-mix(in srgb,var(--accent,var(--c-brand)) 45%,transparent) inset}
.mode-seg.dim{opacity:.4}
.mode-seg.flash{animation:hotflash 1.05s ease-out 2}
/* 统一左侧导航栏(二级 mode-switch + 三级 lens) + 右侧内容,合为一体不分割 */
.nav-shell{display:flex;align-items:stretch;gap:0;border:1px solid var(--c-line);border-radius:16px;background:var(--c-panel);overflow:hidden}
.side-nav{flex:0 0 auto;width:172px;padding:14px 12px;border-right:1px solid var(--c-line);display:flex;flex-direction:column;gap:12px}
.stage-main{flex:1;min-width:0;padding:16px 18px;background:var(--c-bg);overflow-x:auto}
.sub-region{display:block;margin:1px 0 4px}
.lens-switch{display:flex;flex-direction:column;gap:2px;position:relative;padding-left:15px}
.lens-switch::-webkit-scrollbar{display:none}
.lens-seg{position:relative}
.lens-seg::before{content:"";position:absolute;left:-8px;top:-2px;bottom:0;width:1.5px;background:var(--c-line2);pointer-events:none}
.lens-seg:last-child::before{bottom:auto;height:calc(50% + 2px)}
.lens-seg::after{content:"";position:absolute;left:-8px;top:50%;width:7px;height:1.5px;background:var(--c-line2);pointer-events:none}
.topic-switch{display:inline-flex;gap:2px;padding:5px 6px;border-radius:12px;background:var(--c-panel);border:1px solid var(--c-line);max-width:100%;overflow-x:auto;scrollbar-width:none}
.topic-switch::-webkit-scrollbar{display:none}
.topic-seg{border:0;background:transparent;color:var(--c-ink2);cursor:pointer;font:600 12px var(--sans);padding:5px 13px;border-radius:8px;white-space:nowrap;transition:.15s}
.topic-seg:hover{color:var(--c-ink)}
.topic-seg.on{background:var(--c-brand);color:#fff}
.lens-grp{display:inline-flex;flex-direction:column;gap:5px;padding:0 12px}
.lens-grp+.lens-grp{border-left:1px solid var(--c-line)}
.lens-grp-lab{font:600 9.5px var(--sans);color:var(--c-ink3);letter-spacing:.08em;white-space:nowrap;text-align:center;text-transform:uppercase}
.lens-grp-segs{display:flex;gap:2px;justify-content:center}
.lens-seg{border:0;background:transparent;color:var(--c-ink2);cursor:pointer;font:600 12px var(--sans);padding:7px 12px;border-radius:8px;white-space:nowrap;transition:.15s;text-align:center}
.lens-seg:hover{color:var(--c-ink);background:color-mix(in srgb,var(--c-ink) 5%,transparent)}
.lens-seg.on{background:var(--c-brand);color:#fff}
@media(max-width:720px){.nav-shell{flex-direction:column;gap:0}.side-nav{width:auto;border-right:0;border-bottom:1px solid var(--c-line);flex-direction:row;flex-wrap:wrap;align-items:flex-start}.mode-switch{flex-direction:row;flex-wrap:wrap}.mode-group.on{padding-left:0}.mode-group.on::before,.mode-seg::before{display:none}.sub-region{margin:0}.lens-switch{flex-direction:row;flex-wrap:wrap;padding-left:0}.lens-seg::before,.lens-seg::after{display:none}.mode-seg,.lens-seg{flex:0 0 auto;text-align:center}}
.mode-view{display:none}
.mode-view.on{display:block}
.lens-view{display:none}
.lens-view.on{display:block}
/* 主题卡网格 */
.topics-note{font:450 12px var(--sans);color:var(--c-ink3);line-height:1.5;margin:2px 4px 16px;max-width:820px}
.basic-subhead{font:800 15px var(--sans);color:var(--c-ink);margin:22px 4px 12px;display:flex;align-items:baseline;gap:12px}
.basic-subhead:first-of-type{margin-top:6px}
.basic-subnote{font:450 11.5px var(--sans);color:var(--c-ink3)}
.topics-note b{color:var(--c-ink2);font-weight:700}
.topics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:8px 4px 20px}
.topic-card{display:flex;flex-direction:column;position:relative;border-radius:16px;background:var(--c-panel);border:1px solid var(--c-line);text-decoration:none;overflow:hidden;transition:border-color .18s,box-shadow .18s,transform .18s}
.topic-card:hover{border-color:color-mix(in srgb,var(--accent) 55%,var(--c-line));box-shadow:0 8px 28px rgba(0,0,0,.10);transform:translateY(-2px)}
.tc-hero{display:block;height:132px;overflow:hidden;background:color-mix(in srgb,var(--accent) 6%,var(--c-bg2));border-bottom:1px solid var(--c-line);position:relative}
.tc-hero img{width:100%;height:auto;display:block;object-fit:cover;object-position:top center;opacity:.96}
.tc-hero svg.tc-hero-svg{width:100%;height:auto;display:block;opacity:.96}
.tc-hero::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,transparent 55%,var(--c-panel) 100%)}
.topic-card:hover .tc-hero img{opacity:1}
.topic-card:hover .tc-hero svg.tc-hero-svg{opacity:1}
/* 卡片预览图内联 SVG:中性色改用 CSS 变量随主题切换,彩色语义(绿蓝紫橙)保留。
   用变量而非属性选择器,渲染 100% 可靠,不受 SVG 色值大小写/变体影响。 */
:root .tc-hero-svg{
  --hero-bg:#fbfbfd;   /* 画布底 / 白 */
  --hero-ink:#1d1d1f;  /* 主文字 / 纯黑 */
  --hero-ink2:#6e6e73; /* 次文字 */
  --hero-ink3:#a1a1a6; /* 弱文字 */
  --hero-line:#e4e7ec; /* 中性描边 / 分隔线 */
  /* 语义分区底 + 描边 + 文字(浅色主题=原始浅色调) */
  --hero-blue-bg:#eaf1fb;   --hero-blue-line:#c6d9f2;  --hero-blue-ink:#20375e;  --hero-blue-ink2:#3a4a63;
  --hero-green-bg:#eaf6f0;  --hero-green-line:#bfe3d1; --hero-green-ink:#2f6b4e; --hero-green-ink2:#5a9078;
  --hero-purple-bg:#f4eefb; --hero-purple-line:#dcc9ef;--hero-purple-ink:#6f3ea8;--hero-purple-ink2:#8a5cae;
  --hero-amber-bg:#fbf3e2;  --hero-amber-line:#ecd6a8; --hero-amber-ink:#8a6417; --hero-amber-ink2:#a98a3a;
  --hero-red-bg:#fbeceb;    --hero-red-line:#e8b7b1;   --hero-red-ink:#8a3b34;   --hero-red-ink2:#b07068;
  --hero-panel:#f6f7f9;     /* 中性分区底(冷灰) */
}
:root[data-theme="dark"] .tc-hero-svg{
  --hero-bg:#1c1e24;
  --hero-ink:#e8e8ea;
  --hero-ink2:#c2c4cb;
  --hero-ink3:#8f9199;
  --hero-line:#3a3d46;
  /* 深色主题:压暗语义底(保留色相)、提亮语义文字 */
  --hero-blue-bg:#1a2740;   --hero-blue-line:#2f4568; --hero-blue-ink:#8fb0e0; --hero-blue-ink2:#6f90c4;
  --hero-green-bg:#152e26;  --hero-green-line:#2a5244; --hero-green-ink:#7fd0a8; --hero-green-ink2:#5fa585;
  --hero-purple-bg:#251a37; --hero-purple-line:#4a3568;--hero-purple-ink:#c39ae6;--hero-purple-ink2:#a07bc4;
  --hero-amber-bg:#332a15;  --hero-amber-line:#5c4a24; --hero-amber-ink:#d9b46a; --hero-amber-ink2:#b89552;
  --hero-red-bg:#3a1f1c;    --hero-red-line:#6b3c36;   --hero-red-ink:#e0938b;   --hero-red-ink2:#c07068;
  --hero-panel:#22242b;
}
.tc-body{display:flex;flex-direction:column;gap:10px;padding:18px 22px 20px}
.tc-title{font:700 16px var(--sans);color:var(--c-ink);letter-spacing:-.01em}
.tc-core{font:450 12.5px var(--sans);color:var(--c-ink2);line-height:1.5}
.tc-dots{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:5px}
.tc-dot{font:500 11px var(--sans);color:var(--c-ink3);padding-left:14px;position:relative;line-height:1.45}
.tc-dot::before{content:"";position:absolute;left:2px;top:7px;width:4px;height:4px;border-radius:50%;background:var(--accent);opacity:.7}
.tc-projs{display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}
.tc-chip{font:600 10px var(--mono);color:var(--c-ink3);background:var(--c-bg2);border:1px solid var(--c-line);border-radius:6px;padding:2px 7px}
.topic-card.tc-flash{animation:tcflash 1.15s ease-out}
@keyframes tcflash{0%,100%{box-shadow:0 0 0 0 transparent}30%{box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 45%,transparent)}}
/* LLM & Agent:手绘总架构图 + 热区下钻(仿 doris 架构导航) */
.arch-stage{max-width:1120px;margin:0 auto;padding:6px 4px 20px}
.arch-canvas{position:relative;width:100%;border-radius:20px;overflow:hidden;background:var(--c-panel);border:1px solid var(--c-line);box-shadow:0 8px 28px rgba(0,0,0,.08)}
.arch-img{display:block;width:100%;height:auto;user-select:none}
.arch-svg{display:block;width:100%;height:auto;user-select:none}
/* 内联总架构图:中性色随主题;品牌语义色保留 */
.arch-svg .ag-bg{fill:#fbfbfd}
.arch-svg .ag-card{fill:#ffffff;stroke:#c7c7cf !important;stroke-width:1.2}
.arch-svg .ag-band{fill:#f4f4f6;stroke:#e4e7ec !important;stroke-width:1.2}
.arch-svg .ag-tint{fill:#f6f7f9;stroke:#d7d7dd !important;stroke-width:1.1}
.arch-svg .ag-sub{fill:#8a8a8e}
.arch-svg .ag-title{fill:#1d1d1f}
.arch-svg .ag-line{stroke:#a1a1a6}
/* 业务场景四分类:对齐 Replication 柔和语义色 Apple 工业风——分区 band 用柔和语义浅底
   (蓝/紫/绿/金,克制不刺眼),场景卡纯白 + 柔和语义色描边,四分类色差靠彩标题+柔和浅底+卡描边点睛 */
.arch-svg .sf-band-pay{fill:#eaf1fb;stroke:#c6d9f2 !important}
.arch-svg .sf-band-disc{fill:#f4eefb;stroke:#dcc9ef !important}
.arch-svg .sf-band-social{fill:#eaf6f0;stroke:#bfe3d1 !important}
.arch-svg .sf-band-growth{fill:#fbf3e2;stroke:#ecd6a8 !important}
.arch-svg .sc-pay{fill:#ffffff}
.arch-svg .sc-disc{fill:#ffffff}
.arch-svg .sc-social{fill:#ffffff}
.arch-svg .sc-growth{fill:#ffffff}
/* 场景卡柔和语义色描边(1.2),配合纯白底克制点睛 */
.arch-svg .sc-scene{stroke-width:1.2}
/* 分类彩色标题(sf-cat-*):亮色柔和语义深字 / 暗色柔和语义亮字(!important 覆盖 SVG 硬编码 fill) */
.arch-svg .sf-cat-pay{fill:#20375e !important}
.arch-svg .sf-cat-disc{fill:#6f3ea8 !important}
.arch-svg .sf-cat-social{fill:#2f6b4e !important}
.arch-svg .sf-cat-growth{fill:#8a6417 !important}
:root[data-theme="dark"] .arch-svg .sf-cat-pay{fill:#7aa5e0 !important}
:root[data-theme="dark"] .arch-svg .sf-cat-disc{fill:#b58ed6 !important}
:root[data-theme="dark"] .arch-svg .sf-cat-social{fill:#6bc79a !important}
:root[data-theme="dark"] .arch-svg .sf-cat-growth{fill:#d6b463 !important}
:root[data-theme="dark"] .arch-svg .ag-bg{fill:#15161a}
:root[data-theme="dark"] .arch-svg .ag-card{fill:#22242b;stroke:#4a4d57 !important}
:root[data-theme="dark"] .arch-svg .ag-band{fill:#1b1d23;stroke:#33353d !important}
:root[data-theme="dark"] .arch-svg .ag-tint{fill:#2a2d36;stroke:#454955 !important}
:root[data-theme="dark"] .arch-svg .ag-sub{fill:#9ca0a8}
:root[data-theme="dark"] .arch-svg .ag-title{fill:#f2f3f5}
:root[data-theme="dark"] .arch-svg .ag-line{stroke:#565963}
:root[data-theme="dark"] .arch-svg .sf-band-pay{fill:#191b21;stroke:#2c2f38 !important}
:root[data-theme="dark"] .arch-svg .sf-band-disc{fill:#1a1a22;stroke:#2e2d38 !important}
:root[data-theme="dark"] .arch-svg .sf-band-social{fill:#181b1f;stroke:#2b2f36 !important}
:root[data-theme="dark"] .arch-svg .sf-band-growth{fill:#1b1a1d;stroke:#2f2d31 !important}
:root[data-theme="dark"] .arch-svg .sc-pay{fill:#22242b}
:root[data-theme="dark"] .arch-svg .sc-disc{fill:#22242b}
:root[data-theme="dark"] .arch-svg .sc-social{fill:#22242b}
:root[data-theme="dark"] .arch-svg .sc-growth{fill:#22242b}
:root[data-theme="dark"] .arch-canvas{background:#15161a}
.arch-hot{position:absolute;border:1.5px solid transparent;border-radius:14px;background:transparent;cursor:pointer;padding:0;text-decoration:none;display:grid;place-items:center;transition:border-color .18s,background .18s,box-shadow .18s}
.arch-hot:hover{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}
.arch-hot:focus-visible{outline:none;border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent)}
.arch-hot-lab{opacity:0;font:700 11px var(--sans);color:#fff;background:var(--accent);padding:3px 10px;border-radius:8px;transition:opacity .18s;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);white-space:nowrap}
.arch-hot:hover .arch-hot-lab{opacity:1}
/* 搜索命中场景热区:高亮边框+底色,dim 淡出其余,flash 脉冲一次 */
.arch-hot.hit{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 20%,transparent)}
.arch-hot.hit .arch-hot-lab{opacity:1}
.arch-hot.dim{opacity:.28}
@keyframes hotflash{0%,100%{box-shadow:0 0 0 0 transparent}35%{box-shadow:0 0 0 5px color-mix(in srgb,var(--accent) 55%,transparent)}}
.arch-hot.flash{animation:hotflash 1.05s ease-out 2}
/* 业务场景导航:保留 hover/命中的边框+底色+外发光高亮反馈,仅隐藏浮层标签(不要盖住卡片的文字块) */
.scen-hot .arch-hot-lab{display:none}
/* 业务场景热区圆角对齐场景卡 rx=12(全局 arch-hot 用 14px 贴 LLM 卡) */
.scen-hot .arch-hot{border-radius:12px}
/* 业务场景卡片 SVG 本身已有彩色描边;热区若再画 border 或 box-shadow 外环,会因热区 rect
   与可见卡 rect 尺寸(79 vs 77)不一致而错位,形成"边框重影"。故 scen-hot 热区高亮
   一律不画任何轮廓线/外发光,只用淡底填充(color-mix)做反馈,边框全部交给 SVG 卡描边。 */
.scen-hot .arch-hot:hover,.scen-hot .arch-hot:focus-visible{border-color:transparent!important;box-shadow:none!important;background:color-mix(in srgb,var(--accent) 16%,transparent)}
.scen-hot .arch-hot.hit{border-color:transparent!important;box-shadow:none!important;background:color-mix(in srgb,var(--accent) 20%,transparent)}
/* 命中脉冲也改成淡底闪烁,不画 box-shadow 环(否则与卡描边重影) */
.scen-hot .arch-hot.flash{animation:scenhotflash 1.05s ease-out 2}
@keyframes scenhotflash{0%,100%{background:color-mix(in srgb,var(--accent) 20%,transparent)}45%{background:color-mix(in srgb,var(--accent) 42%,transparent)}}
/* 关系视角:核心 + 洞察 + 关系图例 + 分组实体卡 */
.relation-view{padding:8px 4px 24px}
.re-core{font:700 20px var(--sans);color:var(--c-ink);letter-spacing:-.02em;margin:6px 0 6px}
.re-insight{font:450 13px var(--sans);color:var(--c-ink2);line-height:1.55;margin:0 0 18px;max-width:820px}
.re-legend{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:12px 16px;border-radius:12px;background:var(--c-bg2);border:1px solid var(--c-line);margin-bottom:22px}
.re-leg-lab{font:700 10px var(--mono);letter-spacing:.14em;color:var(--c-ink3);text-transform:uppercase}
.re-leg{font:500 11.5px var(--sans);color:var(--c-ink2);display:inline-flex;align-items:center;gap:6px}
.re-leg-k{font:600 10px var(--mono);color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent);border-radius:5px;padding:1px 6px}
.re-groups{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;align-items:start}
.re-group{display:flex;flex-direction:column;gap:10px}
.re-glab{font:700 12.5px var(--sans);color:var(--c-ink);padding-bottom:8px;border-bottom:2px solid color-mix(in srgb,var(--accent) 55%,var(--c-line))}
.re-ents{display:flex;flex-direction:column;gap:10px}
.re-ent{display:flex;flex-direction:column;gap:5px;padding:14px 16px;border-radius:12px;background:var(--c-panel);border:1px solid var(--c-line)}
.re-name{font:700 14px var(--sans);color:var(--c-ink)}
.re-kind{font:600 9.5px var(--mono);color:var(--accent);letter-spacing:.06em;text-transform:uppercase}
.re-edge{font:500 11.5px var(--sans);color:var(--c-ink2);line-height:1.45}
.re-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.re-chip{font:600 10.5px var(--sans);color:var(--accent);background:color-mix(in srgb,var(--accent) 9%,transparent);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);border-radius:7px;padding:3px 9px;text-decoration:none;transition:.15s;white-space:nowrap}
.re-chip:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.lens-pos-bg{fill:color-mix(in srgb,var(--c-brand) 7%,transparent);stroke:color-mix(in srgb,var(--c-brand) 22%,transparent);stroke-width:1}
.lens-pos{fill:var(--c-ink2);font:500 12px var(--sans)}
.axis-line{stroke:var(--c-line2);stroke-width:1.5}
.axis-pole{fill:var(--c-ink3);font:600 9px var(--mono);letter-spacing:.04em;text-anchor:middle}
.axis-pole-b{}
.dep-tri{fill:var(--c-ink3);opacity:.5}
.tier-band{fill:color-mix(in srgb,var(--accent) 5%,var(--c-panel));stroke:none}
:root[data-theme="dark"] .tier-band{fill:color-mix(in srgb,var(--accent) 9%,var(--c-panel))}
.tier-sheen{display:none}
.tier-div{stroke:var(--c-line);stroke-width:1}
.tier-edge{fill:var(--accent);opacity:.95}
.layer-num{fill:var(--c-ink3);font:700 19px var(--mono,monospace);opacity:.5}
.layer-title{fill:var(--c-ink);font:700 13px var(--sans)}
.layer-sub{fill:var(--c-ink3);font:500 9px var(--sans)}
.search kbd{font-family:var(--mono);font-size:11px;color:var(--c-ink3);border:1px solid var(--c-line2);
  border-radius:6px;padding:1px 6px;background:var(--c-panel2);flex:none}
.tt{flex:none;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:grid;place-items:center;transition:all .18s}
.tt:hover{border-color:var(--c-ink3);color:var(--c-ink);background:var(--c-hover)}
.tt-ico{font-size:16px;line-height:1} .tt-moon{display:none}
:root[data-theme="dark"] .tt-sun{display:none}
:root[data-theme="dark"] .tt-moon{display:inline}
/* 舞台:架构图是主角,居中留白,无额外装饰框 */
.stage{max-width:1300px;margin:0 auto;padding:34px 30px 56px}
.diagram{position:relative;overflow-x:auto}
.undernote{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;
  margin-top:22px;padding-top:16px;border-top:1px solid var(--c-line);
  color:var(--c-ink3);font-size:12px;font-family:var(--mono)}
.undernote .stats{color:var(--c-ink2)}

/* ── 架构图 SVG 主题化(不反相,图标保持真品牌色)── */
#atlas{display:block;width:100%;height:auto;min-width:1040px}
/* 单外框:系统母图是一张精密机器剖面,面板/路径/模块共享一张画布 */
.frame{fill:var(--c-panel);stroke:var(--c-line);stroke-width:1;filter:drop-shadow(0 1px 3px rgba(0,0,0,.05))}
:root[data-theme="dark"] .frame{fill:var(--c-panel);stroke:color-mix(in srgb,#fff 8%,transparent);filter:none}
.map-kicker{fill:var(--accent,var(--c-brand));font:700 10.5px var(--mono);letter-spacing:.24em;opacity:.9}
.map-title{fill:var(--c-ink);font:600 30px var(--sans);letter-spacing:-.032em}
.map-subtitle{fill:var(--c-ink3);font:450 13px var(--sans);letter-spacing:-.005em}
.plane-band rect{fill:transparent;stroke:var(--c-line);stroke-width:1;stroke-dasharray:2 8;opacity:.48}
.plane-band text{fill:var(--c-ink3);font:700 8.5px var(--mono);letter-spacing:.18em;opacity:.62}
.machine-rails path{fill:none}
.flow-hot{stroke:var(--p-hot,#0a84ff);stroke-width:2.4;filter:drop-shadow(0 0 5px color-mix(in srgb,var(--p-hot,#0a84ff) 48%,transparent))}
.flow-ctrl{stroke:var(--p-ctrl,#a78bfa);stroke-width:1.7;stroke-dasharray:7 5;opacity:.9}
.flow-state{stroke:var(--p-state,#2dd4bf);stroke-width:1.8;opacity:.9}
.flow-opt{stroke:var(--c-ink3);stroke-width:1.4;stroke-dasharray:2 5;opacity:.72}
.arrow-hot{fill:var(--p-hot,#0a84ff)}.arrow-ctrl{fill:var(--p-ctrl,#a78bfa)}.arrow-state{fill:var(--p-state,#2dd4bf)}.arrow-opt{fill:var(--c-ink3)}
.flow-label{fill:var(--c-ink3);font:600 10px var(--mono);letter-spacing:.08em}
.rail-label{fill:var(--c-ink3);font:600 11px var(--mono);letter-spacing:.04em}
.flow-hot-lab{fill:var(--p-hot,#0a84ff)}
.flow-ctrl-lab{fill:var(--p-ctrl,#a78bfa)}
.axis-cap{fill:var(--c-ink3);font:700 11px var(--mono);letter-spacing:.16em;opacity:.7}
.axis-cap-ctrl{fill:color-mix(in srgb,var(--p-ctrl,#a78bfa) 78%,var(--c-ink3))}
.sys-panel{isolation:isolate}
.panel-shell{fill:color-mix(in srgb,var(--c-panel) 90%,#fff 3%);stroke:var(--c-line2);stroke-width:1}
:root[data-theme="light"] .panel-shell{fill:color-mix(in srgb,var(--c-panel) 94%,#000 1%)}
.panel-rule{stroke:var(--c-line);stroke-width:1}
.panel-num{fill:var(--c-ink);font:200 42px var(--sans);letter-spacing:-.04em;opacity:.16}
.panel-title{fill:var(--c-ink);font:650 18px var(--sans);letter-spacing:-.025em}
.panel-sub{fill:var(--c-ink3);font:400 11.5px var(--sans)}
.panel-empty{fill:var(--c-ink3);font:500 11px var(--mono);opacity:.55}
.nd{cursor:pointer}
.nd-rect{fill:var(--c-panel);stroke:var(--c-line2);stroke-width:1;transition:stroke .18s,fill .18s}
:root[data-theme="dark"] .nd-rect{fill:color-mix(in srgb,#fff 6%,var(--c-panel));stroke:color-mix(in srgb,#fff 12%,transparent)}
.nd-sheen{display:none}
.nd-ic{transition:opacity .18s}
.nd:hover .nd-rect{stroke:var(--accent);stroke-width:1.5;fill:var(--c-hover)}
.nd:focus{outline:none}
.nd:focus-visible .nd-rect{stroke:var(--c-ink);stroke-width:2}
.nd-plan{cursor:default}
.nd-plan .nd-rect{stroke-dasharray:4 3;opacity:.55}
.nd-plan .nd-name,.nd-plan .tile,.nd-plan .nd-ic{opacity:.42}
.nd-name{fill:var(--c-ink2);font:590 11.5px var(--sans);letter-spacing:-.01em;transition:fill .18s}
.nd:hover .nd-name{fill:var(--c-ink)}
.nd-dot{stroke:var(--c-panel);stroke-width:1}
.tile{fill:var(--accent)}
.tile-t{fill:var(--c-panel);font:700 10px var(--sans);letter-spacing:-.02em}
.side-rail rect{fill:color-mix(in srgb,var(--c-panel) 88%,#fff 3%);stroke:var(--c-line);stroke-width:1}
.side-rail line{stroke:var(--c-line2);stroke-width:1}
.side-rail text{fill:var(--c-ink3);font:700 8.5px var(--mono);letter-spacing:.16em;writing-mode:vertical-rl}
.legend text{fill:var(--c-ink3);font:600 10px var(--mono);letter-spacing:.06em}
.legend path{fill:none}
/* 搜索态:命中 flash 高亮,其余淡出 */
.nd.dim{opacity:.2;transition:opacity .2s}
.nd.hit .nd-rect{stroke:var(--c-brand);stroke-width:2.4}
@keyframes flash{0%,100%{filter:none}35%{filter:drop-shadow(0 0 10px var(--c-brand))}}
.nd.flash .nd-rect{animation:flash 1.05s ease-out 2;stroke:var(--c-brand);stroke-width:2.6}

footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:26px;
  color:var(--c-ink3);font-size:12px;font-family:var(--mono)}
@media(max-width:720px){.wrap{padding:28px 16px 56px}h1{font-size:26px}.diagram{padding:10px;border-radius:16px}}
</style>
</head>
<body>
<div class="chrome">
<header class="topbar">
  <span class="logo" aria-hidden="true">
    <svg viewBox="0 0 40 40" width="34" height="34">
      <circle cx="12.5" cy="11.5" r="4" class="pb-body"/><circle cx="27.5" cy="11.5" r="4" class="pb-body"/>
      <circle cx="12.5" cy="11.5" r="1.6" class="pb-ear"/><circle cx="27.5" cy="11.5" r="1.6" class="pb-ear"/>
      <path d="M8 19 Q8 9 20 9 Q32 9 32 19 Q32 30 20 31 Q8 30 8 19 Z" class="pb-body"/>
      <ellipse cx="20" cy="24" rx="5.5" ry="4.2" class="pb-snout"/>
      <circle cx="16.5" cy="18" r="1.7" class="pb-eye"/><circle cx="23.5" cy="18" r="1.7" class="pb-eye"/>
      <ellipse cx="20" cy="22.5" rx="2.4" ry="1.8" class="pb-nose"/>
    </svg>
  </span>
  <span class="brand">工程技术图谱</span>
  <div class="group-switch" role="tablist" aria-label="导航分组">
    <button class="group-seg on" data-group="tech" role="tab" id="m_group_tech">技术视角</button>
    <button class="group-seg" data-group="biz" role="tab" id="m_group_biz">业务视角</button>
    <button class="group-seg" data-group="bg" role="tab" id="m_group_bg">三方视角</button>
  </div>
  <label class="search">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="text" placeholder="搜索图谱…" autocomplete="off" aria-label="搜索项目"/>
    <kbd>/</kbd>
  </label>
  <button class="tt" id="tt" aria-label="切换深浅主题" title="切换深浅主题">
    <span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span>
  </button>
</header>
<nav class="lensbar" aria-label="一级导航"></nav>
</div>

<main class="stage">
<div class="nav-shell">
<aside class="side-nav">
  <div class="mode-switch" role="tablist" aria-label="导航模式">
    <div class="mode-group on" data-group="tech">
      <button class="mode-seg on" data-mode="project" role="tab" id="m_mode_project">项目视角</button>
      <div class="sub-region on" data-mode="project">__LENSSWITCH__</div>
      <button class="mode-seg" data-mode="topic" role="tab" id="m_mode_topic">专题视角</button>
      <button class="mode-seg" data-mode="principles" role="tab" id="m_mode_principles">系统视角</button>
      <button class="mode-seg" data-mode="basic" role="tab" id="m_mode_basic">基础原理</button>
      <button class="mode-seg" data-mode="agent" role="tab" id="m_mode_agent">AI视角</button>
    </div>
    <div class="mode-group" data-group="biz" data-defaultmode="scenario"></div>
    <div class="mode-group" data-group="bg">
      <button class="mode-seg" data-mode="standards" role="tab" id="m_mode_standards">社区视角</button>
      <button class="mode-seg" data-mode="industry" role="tab" id="m_mode_industry">产业视角</button>
      <button class="mode-seg" data-mode="people" role="tab" id="m_mode_people">学派视角</button>
    </div>
  </div>
</aside>
<div class="stage-main">
  <div class="mode-view on" data-mode="project"><div class="diagram">__SVG__</div></div>
  <div class="mode-view" data-mode="topic">__TOPICS__</div>
  <div class="mode-view" data-mode="basic">__BASIC__</div>
  <div class="mode-view" data-mode="principles">__PRINCIPLES__</div>
  <div class="mode-view" data-mode="agent">__AGENT__</div>
  <div class="mode-view" data-mode="scenario">__SCENARIO__</div>
  <div class="mode-view" data-mode="standards">__STANDARDS__</div>
  <div class="mode-view" data-mode="industry">__INDUSTRY__</div>
  <div class="mode-view" data-mode="people">__PEOPLE__</div>
</div>
</div>
  <div class="undernote">
    <span class="stats" id="stats"></span>
    <span class="hint" id="count"></span>
  </div>
</main>

<script>
(function(){
  var AGG=__AGG__, IDX=__INDEX__;
  var r=document.documentElement, KEY="atlas-nav-theme";
  function ap(t){ if(t==="dark") r.setAttribute("data-theme","dark"); else r.removeAttribute("data-theme"); }
  var s="light"; try{ s=localStorage.getItem(KEY)||"light"; }catch(e){} ap(s);
  var tt=document.getElementById("tt");
  if(tt) tt.onclick=function(){ var n=r.getAttribute("data-theme")==="dark"?"light":"dark"; ap(n); try{localStorage.setItem(KEY,n);}catch(e){} };
  // 视角切换:segmented → 显示对应 lens-view,隐藏其余
  (function(){
    var segs=[].slice.call(document.querySelectorAll(".lens-seg"));
    var views=[].slice.call(document.querySelectorAll(".lens-view"));
    function show(lid){
      segs.forEach(function(b){ b.classList.toggle("on", b.dataset.lens===lid); });
      views.forEach(function(v){ v.classList.toggle("on", v.dataset.lens===lid); });
    }
    segs.forEach(function(b){ b.onclick=function(){ show(b.dataset.lens); }; });
  })();
  // 一级模式切换:项目视角 / 专题视角 —— 两套并行,切模式显隐对应切换区 + 内容区
  (function(){
    var ms=[].slice.call(document.querySelectorAll(".mode-seg"));
    var views=[].slice.call(document.querySelectorAll(".mode-view"));
    function mode(m){
      ms.forEach(function(b){ b.classList.toggle("on", b.dataset.mode===m); });
      views.forEach(function(v){ v.classList.toggle("on", v.dataset.mode===m); });
    }
    ms.forEach(function(b){ b.onclick=function(){ mode(b.dataset.mode); }; });
    // 顶部分组切换:技术视角 / 业务视角 / 三方视角 —— 切分组显隐对应 mode-group,并激活该组首个视角
    var gsegs=[].slice.call(document.querySelectorAll(".group-seg"));
    var mgroups=[].slice.call(document.querySelectorAll(".mode-group"));
    function group(g){
      gsegs.forEach(function(b){ b.classList.toggle("on", b.dataset.group===g); });
      mgroups.forEach(function(mg){ mg.classList.toggle("on", mg.dataset.group===g); });
      var mg=document.querySelector('.mode-group[data-group="'+g+'"]');
      var first=mg && mg.querySelector('.mode-seg');
      if(first) mode(first.dataset.mode);
      else if(mg && mg.dataset.defaultmode) mode(mg.dataset.defaultmode);
    }
    gsegs.forEach(function(b){ b.onclick=function(){ group(b.dataset.group); }; });
    // 深链接:子站「返回」带 #<mode> 进来时,直接激活对应一级模式(而非默认项目视角)
    var initMode=(location.hash||"").replace("#","");
    if(initMode && ms.some(function(b){ return b.dataset.mode===initMode; })){
      mode(initMode);
      // 同步激活该视角所在的顶部分组(否则 mode-group 仍停在默认 tech,seg 不可见)
      var owner=document.querySelector('.mode-group .mode-seg[data-mode="'+initMode+'"]');
      var og=owner && owner.closest(".mode-group");
      if(og && og.dataset.group){ gsegs.forEach(function(b){ b.classList.toggle("on", b.dataset.group===og.dataset.group); }); mgroups.forEach(function(mg){ mg.classList.toggle("on", mg.dataset.group===og.dataset.group); }); }
    }
    // 主题 seg → 滚动+高亮对应主题卡
    var tsegs=[].slice.call(document.querySelectorAll(".topic-seg"));
    tsegs.forEach(function(b){ b.onclick=function(){
      tsegs.forEach(function(x){ x.classList.toggle("on", x===b); });
      var c=document.getElementById("tc-"+b.dataset.topic);
      if(c){ c.scrollIntoView({behavior:"smooth", block:"center"}); c.classList.add("tc-flash"); setTimeout(function(){c.classList.remove("tc-flash");},1200); }
    }; });
  })();
  // 底部一行细描述(数值弱化,不与图争视觉)
  document.getElementById("stats").textContent=AGG.projects+" 项目 · "+AGG.accessible+" 可交互 · "+AGG.layers+" 机制节点 · "+AGG.svg+" 图 · "+AGG.md+" 篇 · 更新 __UPDATED__";
  // 搜索 → 图上 flash 高亮(非过滤成列表)
  var q=document.getElementById("q"), countEl=document.getElementById("count");
  // 同一项目 id 会在多个视角/模式视图里各渲染一份(id 全文档重复),
  // 故用 querySelectorAll 收集全部同 id 节点统一高亮,不能只取 getElementById 的第一份。
  function nodesOf(id){ return [].slice.call(document.querySelectorAll('[id="'+id+'"]')); }
  var els=IDX.map(function(it){ return {it:it, nodes:nodesOf(it.id)}; }).filter(function(x){return x.nodes.length;});
  function isVisible(el){ return !!(el.getClientRects().length); }
  function clearState(){ els.forEach(function(x){ x.nodes.forEach(function(n){ n.classList.remove("dim","hit","flash"); }); }); }
  function baseHint(){ countEl.textContent="/ 聚焦搜索 · ↑↓←→ 移动 · Enter 进入"; }
  function run(){
    var v=(q.value||"").trim().toLowerCase();
    if(!v){ clearState(); baseHint(); return; }
    var hits=[];
    els.forEach(function(x){
      var hit=x.it.hay.indexOf(v)>=0;
      x.nodes.forEach(function(n){
        n.classList.remove("flash");
        if(hit){ n.classList.add("hit"); n.classList.remove("dim"); }
        else{ n.classList.add("dim"); n.classList.remove("hit"); }
      });
      if(hit) hits.push(x);
    });
    countEl.textContent="命中 "+hits.length+" / "+IDX.length;
    if(hits.length){
      // 优先滚动到当前可见视图内的那份;找不到可见份则退回第一份。
      var target=null;
      for(var i=0;i<hits.length && !target;i++){
        for(var j=0;j<hits[i].nodes.length;j++){ if(isVisible(hits[i].nodes[j])){ target=hits[i].nodes[j]; break; } }
      }
      if(!target) target=hits[0].nodes[0];
      void target.getBoundingClientRect(); target.classList.add("flash");
      target.scrollIntoView({behavior:"smooth",block:"center"});
    }
  }
  q.addEventListener("input",run);
  baseHint();
  var navEls=els.filter(function(x){return x.it.nav;}).map(function(x){return x.nodes[0];});
  document.addEventListener("keydown",function(e){
    var typing=document.activeElement===q;
    if((e.key==="/"||((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k")) && !typing){ e.preventDefault(); q.focus(); q.select(); return; }
    if(e.key==="Escape"){ if(q.value){q.value="";run();} q.blur(); return; }
    if(typing) return;
    if(["ArrowDown","ArrowUp","ArrowLeft","ArrowRight"].indexOf(e.key)>=0){
      e.preventDefault();
      var cur=document.activeElement, i=navEls.indexOf(cur);
      if(i<0){ if(navEls[0]) navEls[0].focus(); return; }
      var d=(e.key==="ArrowDown"||e.key==="ArrowRight")?1:-1;
      var n=(i+d+navEls.length)%navEls.length; navEls[n].focus();
    }
  });
})();
</script>
</body>
</html>
"""



def main():
    projects = scan()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build_html(projects))
    # 业务场景下钻子页面:scenarios/<slug>/index.html(核心技术点架构图)
    for sc in SCENARIOS:
        sdir = os.path.join(ROOT, "scenarios", sc["slug"])
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(build_scenario_page(sc))
    print(f"  业务场景子页面 {len(SCENARIOS)} 页 → scenarios/<slug>/index.html")
    # 注:topics/<id>/index.html 的页面内容由专门流程维护(富主题图),本生成器不写、不覆盖。
    agg = aggregate(projects)
    print(f"✓ 扫描 {ROOT}")
    print(f"  项目 {agg['projects']} · 可交互 {agg['accessible']}(ready {agg['ready']}) · "
          f"体系层 {agg['layers']} · 图 {agg['svg']} · 篇 {agg['md']}")
    for k, title, *_ in LAYERS:
        items = [p for p in projects if p["layer"] == k]
        if not items:
            continue
        names = " ".join(f"{p['name']}[{p['status'][0]}]" for p in items)
        print(f"    {title}: {names}")
    print(f"→ 已写入 {OUT}")


if __name__ == "__main__":
    main()
