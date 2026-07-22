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
    "trino": "execute", "duckdb": "execute",
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
    "go": {"name": "Go 语言", "init": "GO", "desc": "语言核心原理 · 编译期 + 运行期",
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


def aggregate(projects):
    by_layer = {k: 0 for k in LAYER_ORDER}
    for p in projects:
        by_layer[p["layer"]] = by_layer.get(p["layer"], 0) + 1
    latest = ""
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
         ("th_acid", "ACID 事务 · Serializable", "MVCC + WAL · 事务隔离级别 · 快照可见性", ["postgres", "mysql-server", "neo4j", "doris"], "#0a84ff"),
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
         ("hw_table", "表格式 / 列存文件", "不可变文件 + 元数据 · 对象存储之上", ["iceberg", "hudi", "orc", "parquet", "arrow", "doris", "starrocks", "trino"], "#2dd4bf"),
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
         ("sy_engine", "计算 / 算子引擎 · Engine", "查询规划 · 向量化算子 · DAG · 训练/推理图", ["spark", "flink", "doris", "clickhouse", "starrocks", "duckdb", "pytorch", "tensorflow", "vllm", "ray"], "#a78bfa"),
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
         ("wl_query", "查询 / 推理 · Serve", "MPP 查询 · 向量化 · 联邦 · 高吞吐推理", ["doris", "clickhouse", "starrocks", "trino", "duckdb", "vllm"], "#0a84ff"),
         ("wl_coord", "协调 / 编排 · Coordinate", "元数据 · 选主 · 容器编排 · 表格式治理", ["etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "kubernetes", "containerd", "iceberg", "hudi", "orc", "arrow", "parquet"], "#8a8a90"),
         ("wl_state", "状态 / 底座 · Substrate", "内存/持久状态后端 · 语言运行时 · 内核", ["redis", "rocksdb", "postgres", "mysql-server", "neo4j", "go", "rust", "openjdk", "linux"], "#2dd4bf"),
     ]},
]


# ── 主题视角(一级导航第二模式):6 大跨项目专题,与项目视角并行、不混。──
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
    """主题视角切换器:6 大专题 seg,点击滚动/高亮对应主题卡。与项目视角并行。"""
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
    """主题视角内容区:6 大专题卡网格,顶部核心生态图预览,点击下钻到 topics/<id>/index.html。"""
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
            '区别于「主题视角」纵向钻透单个机制在多项目中的实现。</p>')
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
        "slug": "seckill", "cn": "瞬时高并发交易", "en": "Flash Sale / High-Concurrency",
        "layer": "交易支付层", "color": "#1a7f52",
        "tagline": "秒杀 / 抢票 / 大促 —— 在极短时间窗口内承接百万级瞬时请求,核心是「层层过滤、把请求挡在数据库之外」。",
        "groups": [
            {"g": "流量入口 · 削峰", "nodes": [
                 {"t": "多级限流", "p": "网关层令牌桶 / 漏桶,单机 + 集群限流;超额直接拒绝返回兜底页",
                 "d": "阈值 = 库存量 ×(2~5)倍即可,放太多反而击穿下游。失败模式:限流阈值拍脑袋定,大促实测才发现网关先于库存被打满。"},
                {"t": "答题 / 验证码", "p": "打散请求到达时刻,过滤脚本刷单,拉平瞬时尖峰",
                 "d": "答题增加 1~3s 随机延迟,峰值 QPS 可降一个数量级,同时挡住 80%+ 脚本党。代价:真实用户体验下降,需与业务权衡。"},
                {"t": "CDN 静态化", "p": "商品详情页静态化 + 边缘缓存,动静分离,读请求不回源",
                 "d": "详情页 99% 是读,静态化后回源率可压到 1% 以下,动态数据用单独轻接口异步拉取。关键:静态页与库存状态解耦,售罄靠前端轮询/长连接更新,不刷新整页。"},
            ]},
            {"g": "库存扣减 · 防超卖", "nodes": [
                {"t": "Redis 预扣减", "p": "库存预热到 Redis,Lua 脚本原子扣减,天然防超卖",
                 "d": "为何不用数据库行锁?DB 单行更新 QPS 仅数千,Redis 可达十万级。失败模式:Redis 宕机需有本地兜底计数 + 数据库对账,否则超卖或少卖。"},
                {"t": "分段库存", "p": "热点库存拆成 N 段分散写压力,避免单 key 热点",
                 "d": "1000 库存拆成 10 段各 100,单 key 写压力降为 1/N。难点:某段售罄需跨段借调,否则出现「总量有货但分段无货」的少卖。适合超大热点 SKU,普通场景单 key 足够。"},
                {"t": "异步落库", "p": "扣减成功后消息队列异步创建订单,数据库削峰填谷",
                 "d": "将瞬时百万写压力摊平到数分钟。关键:扣减与发消息要保证一致(本地消息表/事务消息),否则扣了库存却没订单 = 少卖。"},
            ]},
            {"g": "订单 · 最终一致", "nodes": [
                {"t": "MQ 异步下单", "p": "预扣减→发消息→消费端幂等创单;失败回补库存",
                 "d": "消费端必须幂等(同一消息重复投递只建一单)。失败链路:建单失败→重试 N 次→仍失败则回补 Redis 库存并告警,形成闭环补偿。"},
                {"t": "幂等去重", "p": "唯一索引 / token 防重复下单,消息幂等消费",
                 "d": "三道防线:前端置灰按钮(防手抖)、下单 token(防重放)、DB 唯一索引(userId+activityId 兜底)。为何都要?任一层都可能被绕过,唯一索引是最后底线。"},
                {"t": "超时释放", "p": "延迟队列监控未支付订单,超时自动回滚库存",
                 "d": "下单后 15min 未支付触发回滚,库存归还 Redis 供他人再抢。难点:回滚与用户「刚好支付」的竞态,需乐观锁 + 状态机(待支付→已支付不可回滚)。"},
            ]},
        ],
        "insight": "秒杀的本质不是「扛住百万请求」,而是「用最小代价把注定失败的请求尽早挡掉」——真正能抢中的只有库存数量个,其余 99.99% 请求的价值是「快速失败」而非「排队等待」。因此架构呈漏斗形:每一层过滤掉一批,越往后单请求成本越高(CDN 边缘 < 网关内存 < Redis 网络 < DB 磁盘),核心是让昂贵的资源只服务于极少数有效请求。最大的坑不是并发,而是一致性:预扣减/落库/超时释放三处只要有一处不幂等或不闭环,就会超卖或少卖。",
        "tension": {
            "left": {"label": "尽早挡掉无效请求", "items": [
                "真正抢中 = 库存数量个", "99.99% 价值是快速失败", "CDN 边缘 < 网关内存", "越往后单请求越贵"]},
            "right": {"label": "保住有效请求正确性", "items": [
                "昂贵资源只服务少数", "Redis 网络 < DB 磁盘", "预扣减 / 落库 / 超时释放", "任一处不幂等即超卖少卖"]},
            "core": "本质不是「扛住百万请求」,而是「用最小代价把注定失败的请求尽早挡掉」;最大的坑不是并发而是一致性。",
        },
        "funnel": [
            {"stage": "瞬时请求", "qps": "1,000,000", "note": "百万用户同时点击"},
            {"stage": "CDN / 静态化", "qps": "100,000", "note": "读请求边缘拦截 ~90%"},
            {"stage": "答题 / 限流", "qps": "20,000", "note": "打散尖峰 + 过滤脚本"},
            {"stage": "Redis 预扣减", "qps": "5,000", "note": "放行库存 2~5 倍流量"},
            {"stage": "MQ 异步下单", "qps": "1,000", "note": "削峰后平稳落库"},
            {"stage": "有效订单", "qps": "1,000", "note": "= 库存量,其余快速失败"},
        ],
        "flow": {
            "lanes": [
                {"g": "客户端 / 边缘", "nodes": [
                    {"id": "cdn", "t": "CDN 静态化", "s": "详情页静态化，动静分离"},
                    {"id": "quiz", "t": "答题 / 验证码", "s": "打散尖峰，过滤脚本"}]},
                {"g": "网关削峰", "nodes": [
                    {"id": "gw", "t": "限流网关", "s": "令牌桶+集群限流，超额兜底页"}]},
                {"g": "库存扣减", "nodes": [
                    {"id": "redis", "t": "Redis 分段库存", "s": "Lua 原子扣减，防超卖"}]},
                {"g": "异步下单", "nodes": [
                    {"id": "mq", "t": "消息队列", "s": "削峰填谷，可靠投递"},
                    {"id": "order", "t": "订单服务", "s": "幂等创单+延迟队列超时释放"}]},
                {"g": "落库", "nodes": [
                    {"id": "db", "t": "订单库 (分库分表)", "s": "最终一致，失败回补库存"}]},
            ],
            "edges": [
                {"f": "cdn", "t": "gw", "l": "动态请求"},
                {"f": "quiz", "t": "gw", "l": "通过令牌"},
                {"f": "gw", "t": "redis", "l": "放行流量"},
                {"f": "redis", "t": "mq", "l": "扣减成功→发消息"},
                {"f": "redis", "t": "gw", "l": "售罄拒绝", "d": "back"},
                {"f": "mq", "t": "order", "l": "异步消费"},
                {"f": "order", "t": "db", "l": "幂等落库"},
                {"f": "order", "t": "redis", "l": "超时回补库存", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "秒杀商品上下架与库存预热(活动前把库存 / 详情推到缓存)",
                "抢购下单:校验资格 → 扣库存 → 生成订单,全链路防超卖",
                "限流与排队:令牌桶 + 答题 / 验证码打散尖峰、过滤脚本",
                "幂等下单:同一用户重复点击 / 重放只产生一单",
                "超时未支付自动释放库存,回补给后续用户",
            ],
            "quality": [
                {"k": "峰值承压", "v": "入口百万 QPS、有效写千级", "n": "读写比悬殊,靠层层漏斗收敛到库存量级"},
                {"k": "扣减延迟", "v": "P99 < 50ms", "n": "抢购体验是秒级博弈,慢一步就抢不到"},
                {"k": "超卖", "v": "零容忍,严格 = 库存", "n": "超卖=资损+客诉,是绝对红线不可妥协"},
                {"k": "可用性", "v": "99.95%,售罄快速失败", "n": "宁可明确告知售罄,也不能让请求悬挂雪崩"},
                {"k": "一致性", "v": "缓存与库最终一致 + 对账", "n": "预扣在缓存、落库异步,允许短暂不同步但须可对账追平"},
            ],
            "cons": [
                "极端热点:全站流量集中打一个商品的一个库存 key,天然单点热",
                "尖峰持续短:活动就几秒到几分钟,系统必须为瞬时峰值而非均值设计",
                "黑产脚本:机器人抢购远快于真人,须在入口就识别拦截",
            ],
        },
        "datamodel": [
            {"e": "库存", "s": "Redis(Lua 原子扣)", "r": "十万级写、防超卖"},
            {"e": "分段库存", "s": "Redis 多 key 分片", "r": "打散单 key 热点"},
            {"e": "订单", "s": "分库分表 DB", "r": "海量写、按用户分片"},
            {"e": "去重令牌", "s": "Redis + DB 唯一索引", "r": "防重放、兜底防重"},
            {"e": "下单消息", "s": "消息队列", "r": "削峰、可靠投递"},
            {"e": "商品详情", "s": "CDN 静态化", "r": "读不回源、动静分离"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "DB 直扣", "detail": "行锁扣减、同步下单、量小够用"},
            {"stage": "成长期", "focus": "Redis 预扣 + MQ", "detail": "缓存扣减、异步落库、削峰填谷"},
            {"stage": "成熟期", "focus": "全链路削峰", "detail": "分段库存、多级限流、幂等闭环补偿"},
        ],
        "pitfalls": [
            "DB 行锁扛抢购:高并发下行锁排队,连接池瞬间打满、库被拖垮",
            "先扣库存后下单不幂等:网络重试 / 用户狂点造成一人多单、库存虚减",
            "缓存与库双写不对账:预扣成功但落库失败,库存漏了却无人追平",
            "单 key 库存不分段:全站流量压一个热 key,Redis 分片形同虚设",
            "同步下单不削峰:抢购请求直连订单库,峰值瞬间打垮下游",
            "超时不回补库存:未支付订单占着库存,后面的人抢不到、转化率崩",
            "限流只在应用层:入口没拦住脚本,无效流量已经穿透到扣减逻辑",
        ],
        "takeaways": [
            "层层漏斗收敛:CDN→限流→答题→预扣→异步,每层砍一个数量级,别让全部流量到底",
            "热点必分段:单点热 key 是万恶之源,分段库存 / 多副本把热度摊开",
            "扣减要原子:库存判断 + 扣减必须一个原子操作(Lua / CAS),杜绝检查-执行竞态",
            "写路径异步化:同步只做最轻的预扣,重活(落库)扔给 MQ 削峰慢慢消化",
            "幂等 + 补偿兜底:下单幂等、超时回补,用最终一致 + 对账守住不超卖不漏单",
        ],
    },
    {
        "slug": "ecommerce", "cn": "电商交易与订单", "en": "E-Commerce Transaction",
        "layer": "交易支付层", "color": "#1a7f52",
        "tagline": "下单 / 支付 / 履约 —— 从加购到成交的交易主链路,核心是「库存不超卖、订单不丢失、状态强一致」。",
        "groups": [
            {"g": "商品 · 建模", "nodes": [
                {"t": "SPU / SKU 建模", "p": "SPU 聚合标品、SKU 落到可售单元(颜色 / 尺码),库存挂在 SKU",
                "d": "SPU=一件商品,SKU=具体规格的最小库存单位。价格 / 库存 / 图片挂 SKU,搜索 / 详情聚合到 SPU。失败模式:库存挂错粒度(挂 SPU)会导致规格间串货超卖。"},
                {"t": "雪花 ID / 分库分表", "p": "订单 / 商品全局唯一 ID,按 userId 或 orderId 分片",
                 "d": "雪花算法生成趋势递增有序 ID,避免自增主键单点。订单按买家 userId 分片(便于查我的订单),商家维度用异构索引。难点:分片键选错后期迁移代价极大。"},
            ]},
            {"g": "下单 · 防超卖", "nodes": [
                {"t": "库存扣减防超卖", "p": "预占 / 扣减 / 释放三态,乐观锁或 Redis 原子扣,严格不超卖",
                 "d": "下单预占、支付扣减、超时释放。DB 用 update...where stock>=n 乐观锁,高并发切 Redis 原子扣 + 异步对账。失败模式:预占不释放导致库存虚减(有货却下不了单)。"},
                {"t": "幂等下单", "p": "下单 token + 唯一索引,重复提交 / 网络重试只产生一单",
                 "d": "前端置灰 + 下单 token(防重放)+ DB 唯一索引(userId+商品+幂等号兜底)。任一层可能被绕过,唯一索引是最后底线。失败模式:不幂等则一人多单、库存虚减。"},
                {"t": "购物车 / 优惠", "p": "加购、券 / 满减 / 拆单价格试算,下单前锁价",
                 "d": "结算时重算价格与库存(不能信前端传的价)。优惠叠加顺序、拆单分摊是复杂点。锁价:下单瞬间快照价格,避免结算与支付间价格漂移引发客诉。"},
            ]},
            {"g": "交易 · 一致性", "nodes": [
                {"t": "分布式事务 TCC / Saga", "p": "跨库存 / 订单 / 账户,Try-Confirm-Cancel 或状态机补偿",
                 "d": "扣库存、建订单、扣余额跨多服务无法用本地事务。TCC 预留资源后确认/取消,Saga 长事务用补偿回滚。核心是最终一致 + 幂等补偿,别追求强一致拖垮性能。"},
                {"t": "本地消息表", "p": "扣库存与发下单消息在同一本地事务,保证不丢不重",
                 "d": "业务操作与消息写入同库本地事务,再异步投递,保证「操作成功消息必达」。失败模式:先操作后发消息,中间宕机则消息丢失、下游状态错乱。"},
                {"t": "订单状态机", "p": "待支付 / 已支付 / 已发货 / 已完成 / 已取消,迁移受控",
                 "d": "状态迁移只允许合法路径(待支付→已支付,不可逆回),配乐观锁防并发跳变。难点:超时取消与用户刚好支付的竞态,须状态机 + 版本号守住。"},
            ]},
        ],
        "insight": "电商交易系统的核心矛盾是「性能」与「一致性」的拉锯——下单主链路要扛住大促洪峰(高性能),又不能超卖、不能丢单、不能乱扣钱(强一致)。工程答案是分层妥协:读多的商品 / 详情用缓存 + 静态化换性能,写关键的库存 / 订单 / 资金用分布式事务 + 幂等 + 状态机守一致。最大的坑不是并发而是一致性链路:库存扣减、分布式事务、消息投递三处只要有一处不幂等或不闭环,就会超卖、少卖或资损。真正的高手把「强一致」收敛到最小范围(库存 + 资金),其余全走最终一致 + 对账兜底。",
        "tension": {
            "left": {"label": "追求性能 / 吞吐", "items": [
                "商品 / 详情缓存 + 静态化", "库存切 Redis 原子扣", "下单异步化削峰", "读路径极致优化"]},
            "right": {"label": "保住一致 / 不资损", "items": [
                "库存严格不超卖", "分布式事务 TCC / Saga", "幂等 + 唯一索引兜底", "状态机 + 对账追平"]},
            "core": "核心是性能与一致性的拉锯;把强一致收敛到库存+资金最小范围,其余走最终一致+对账。",
        },
        "funnel": [
            {"stage": "浏览 / 加购", "qps": "500,000", "note": "商品详情读,缓存+静态化扛住"},
            {"stage": "下单请求", "qps": "50,000", "note": "校验资格+锁价+幂等"},
            {"stage": "库存扣减", "qps": "20,000", "note": "原子扣减,防超卖"},
            {"stage": "创建订单", "qps": "20,000", "note": "分布式事务+状态机"},
            {"stage": "支付成交", "qps": "10,000", "note": "跳转支付,超时释放库存"},
        ],
        "flow": {
            "lanes": [
                {"g": "商品 / 加购", "nodes": [
                    {"id": "cart", "t": "购物车服务", "s": "选品，KV 存储"},
                    {"id": "price", "t": "价格 / 优惠", "s": "结算重算，下单锁价"}]},
                {"g": "下单", "nodes": [
                    {"id": "order", "t": "订单服务", "s": "幂等校验+建单+状态机"}]},
                {"g": "库存", "nodes": [
                    {"id": "stock", "t": "库存服务", "s": "预占/扣减/释放，防超卖"}]},
                {"g": "交易一致", "nodes": [
                    {"id": "txn", "t": "分布式事务", "s": "TCC/Saga 补偿"},
                    {"id": "mq", "t": "本地消息表 / MQ", "s": "可靠投递，不丢不重"}]},
                {"g": "落库", "nodes": [
                    {"id": "db", "t": "订单库 (分库分表)", "s": "雪花 ID，按 userId 分片"}]},
            ],
            "edges": [
                {"f": "cart", "t": "price", "l": "结算试算"},
                {"f": "price", "t": "order", "l": "锁价下单"},
                {"f": "order", "t": "stock", "l": "预占库存"},
                {"f": "stock", "t": "order", "l": "扣减成功", "d": "back"},
                {"f": "order", "t": "txn", "l": "分布式事务"},
                {"f": "txn", "t": "mq", "l": "发下单消息"},
                {"f": "order", "t": "db", "l": "幂等落库"},
                {"f": "txn", "t": "stock", "l": "失败补偿回滚", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "商品 SPU / SKU 建模、上下架与库存管理",
                "购物车加购、优惠 / 券试算与下单锁价",
                "下单主链路:校验→扣库存→建订单,全链路防超卖防重",
                "跨库存 / 订单 / 资金的分布式事务与补偿",
                "订单状态机流转、超时未支付自动释放库存",
            ],
            "quality": [
                {"k": "下单延迟", "v": "P99 < 200ms", "n": "成交转化对延迟敏感,慢一步就流失"},
                {"k": "峰值承压", "v": "大促下单 5 万+ QPS", "n": "洪峰远高于均值,须为峰值设计"},
                {"k": "超卖", "v": "零容忍,严格 = 库存", "n": "超卖=资损+客诉,绝对红线"},
                {"k": "资金一致", "v": "不多扣 / 不少扣 + 对账", "n": "涉钱强一致,须可对账追平"},
                {"k": "可用性", "v": "99.95%,核心链路优先", "n": "下单支付是命脉,可降级非核心"},
            ],
            "cons": [
                "读写比悬殊:浏览远多于下单,读靠缓存写靠一致性保障",
                "资金 / 库存零容忍:超卖少扣钱都是硬故障,不可妥协",
                "长事务跨多服务:库存 / 订单 / 资金 / 履约分布在不同域,天然分布式",
            ],
        },
        "datamodel": [
            {"e": "商品 (SPU/SKU)", "s": "关系型 DB + 缓存", "r": "详情读多,缓存扛读"},
            {"e": "库存", "s": "Redis 原子扣 + DB", "r": "高并发写、严格防超卖"},
            {"e": "订单", "s": "分库分表 DB", "r": "海量写、按 userId 分片"},
            {"e": "购物车", "s": "Redis KV", "r": "高频读写、临时态"},
            {"e": "去重 / 幂等", "s": "Redis + DB 唯一索引", "r": "防重放、兜底防重"},
            {"e": "交易消息", "s": "本地消息表 + MQ", "r": "可靠投递、不丢不重"},
        ],
        "pitfalls": [
            "库存挂错粒度:挂在 SPU 而非 SKU,规格间串货导致超卖",
            "下单不幂等:网络重试 / 用户狂点造成一人多单、库存虚减",
            "DB 行锁扛下单:大促高并发下行锁排队,连接池打满拖垮库",
            "预占库存不释放:超时订单占着库存,有货却下不了单、转化崩",
            "分布式事务追求强一致:全链路 2PC 锁资源,性能塌陷且易死锁",
            "先操作后发消息:业务成功但消息丢失,下游状态不一致无人追平",
            "价格信前端:结算不重算价,被篡改价格下单造成资损",
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "单库单表", "detail": "本地事务下单、DB 行锁扣库存、量小够用"},
            {"stage": "成长期", "focus": "缓存 + 异步", "detail": "商品缓存、Redis 扣库存、MQ 异步落库"},
            {"stage": "成熟期", "focus": "分布式事务 + 分库分表", "detail": "TCC/Saga、幂等闭环、对账兜底"},
        ],
        "takeaways": [
            "强一致收敛到最小范围:只有库存 + 资金要强保障,其余走最终一致 + 对账",
            "扣减要原子:库存判断 + 扣减一个原子操作,杜绝检查-执行竞态",
            "幂等 + 唯一索引兜底:下单 token 防重放,DB 唯一索引是最后底线",
            "写路径异步化:同步只做最轻的核心操作,重活扔给 MQ 削峰",
            "对账兜底一切:凡涉钱涉库存,都要有 T+1 对账追平不一致",
        ],
    },
    {
        "slug": "im", "cn": "即时通讯 IM", "en": "Instant Messaging",
        "layer": "社交互动层", "color": "#0a84ff",
        "tagline": "私聊 / 群聊 / 已读回执 —— 亿级长连接下的实时消息投递,核心是「长连接管理 + 可靠投递 + 读写扩散」。",
        "groups": [
            {"g": "长连接 · 接入", "nodes": [
                {"t": "WebSocket 长连接", "p": "客户端与接入网关维持长连,双向实时推送,替代轮询",
                 "d": "长连接省去反复握手、支持服务端主动推。海量连接的核心挑战是单机连接数(靠 epoll / 多路复用扛百万连)与心跳保活(检测死连接、及时清理)。失败模式:心跳间隔不合理,要么误杀活连接要么留大量死连接耗资源。"},
                {"t": "接入层路由", "p": "用户→接入网关的映射存 Redis,消息按路由找到目标长连",
                 "d": "谁连在哪台网关须实时可查(uid→gateway 映射)。下行消息先查路由再投递到对应网关。难点:网关扩缩容 / 宕机时路由需快速更新,否则消息投到已断开的网关丢失。"},
                {"t": "心跳与重连", "p": "客户端定时心跳,断线指数退避重连,离线转推送",
                 "d": "心跳检活 + 断线重连保证连接可用性。移动端弱网频繁断连,重连要指数退避避免风暴。彻底离线则转 APNs / FCM 系统推送,保证消息不漏。"},
            ]},
            {"g": "可靠投递 · 一致", "nodes": [
                {"t": "ACK 确认机制", "p": "消息投递需应用层 ACK,未确认则重投,保证不丢",
                 "d": "TCP 可靠不等于应用可靠(收到未必处理成功)。须应用层 ACK:发送→存储→投递→客户端 ACK→标记已达。失败模式:只依赖 TCP 不做应用 ACK,客户端崩溃时消息「已发未达」丢失。"},
                {"t": "消息去重 / 有序", "p": "客户端生成 msgId 幂等去重,序列号保证会话内有序",
                 "d": "重投会导致重复,靠客户端 msgId + 服务端去重。会话内有序靠单调递增 seq(而非依赖到达顺序)。难点:多端登录时各端 seq 同步,避免消息乱序或丢失。"},
                {"t": "离线消息", "p": "离线期间消息暂存,上线后按 seq 增量拉取补齐",
                 "d": "用户离线时消息存离线库,上线后带最后已读 seq 拉增量。难点:海量离线消息的存储与拉取分页,群消息离线不能给每人存一份(存储爆炸),须存引用 + 拉时聚合。"},
            ]},
            {"g": "群聊 · 扩散", "nodes": [
                {"t": "写扩散 vs 读扩散", "p": "小群写扩散(each 收件箱)、大群读扩散(共享消息表)",
                 "d": "与 Feed 同理:小群成员少,写扩散每人存一份读快;万人大群写扩散爆炸,改读扩散存一份共享消息表、读时拉取。分界靠群成员数阈值。"},
                {"t": "群消息同步", "p": "群内共享 seq,成员按各自已读位点拉增量",
                 "d": "大群共享一条消息序列,每个成员维护自己的已读 seq,拉取时按位点增量同步。好处:消息只存一份,成员各自推进进度。难点:超大群在线成员同时拉取的读放大。"},
                {"t": "已读回执 / 未读数", "p": "已读位点上报,未读数增量计算,高频写合并",
                 "d": "已读回执 = 上报已读 seq;未读数 = 最新 seq − 已读 seq。高频写(每条已读都上报)须合并批量。大群已读回执若给每条消息记录每人状态会存储爆炸,通常只维护位点。"},
            ]},
        ],
        "insight": "IM 的本质是「在海量长连接上做可靠、有序、实时的消息投递」——两大命门是长连接管理(百万级连接的接入、路由、保活)和消息可靠性(不丢、不重、有序)。最反直觉的一点:TCP 可靠不等于应用可靠,客户端收到 TCP 包不代表处理成功,必须做应用层 ACK,否则「已发未达」照样丢消息。群聊放大了一切难题:万人大群若沿用单聊的写扩散(每人存一份),存储和写入直接爆炸,必须切读扩散(共享消息表 + 各自已读位点)。已读回执 / 未读数看似小功能,却是高频写的重灾区,必须靠位点合并而非逐条记录。真正的护城河在长连接的稳定性与消息投递的一致性保证。",
        "tension": {
            "left": {"label": "实时 · 低延迟推送", "items": [
                "WebSocket 长连主动推", "接入路由查目标连", "心跳保活 + 弱网重连", "离线转系统推送兜底"]},
            "right": {"label": "可靠 · 不丢不重有序", "items": [
                "应用层 ACK 保不丢", "msgId 去重 / seq 有序", "离线消息增量补齐", "大群读扩散省存储"]},
            "core": "本质是在海量长连接上兼顾实时与可靠;TCP 可靠不等于应用可靠,群聊放大存储与扩散难题,只能按规模取舍。",
        },
        "funnel": [
            {"stage": "在线长连接数", "qps": "1000万", "note": "单机百万连,靠多路复用扛"},
            {"stage": "消息上行", "qps": "50万/s", "note": "发送峰值,先落存储再投递"},
            {"stage": "写/读扩散", "qps": "500万/s", "note": "群聊放大,大群走读扩散"},
            {"stage": "下行投递", "qps": "300万/s", "note": "查路由投目标网关长连"},
            {"stage": "ACK 确认", "qps": "290万/s", "note": "未确认重投,保证不丢"},
        ],
        "flow": {
            "lanes": [
                {"g": "发送端", "nodes": [
                    {"id": "sender", "t": "发送方客户端", "s": "生成 msgId,长连上行"}]},
                {"g": "接入", "nodes": [
                    {"id": "gw", "t": "接入网关", "s": "维持长连,uid→网关路由"}]},
                {"g": "逻辑 / 存储", "nodes": [
                    {"id": "logic", "t": "消息逻辑层", "s": "去重、定 seq、扩散"},
                    {"id": "store", "t": "消息存储", "s": "先落库,离线暂存"}]},
                {"g": "路由 / 下行", "nodes": [
                    {"id": "route", "t": "在线路由", "s": "查收方连在哪台网关"},
                    {"id": "push", "t": "系统推送", "s": "离线转 APNs / FCM"}]},
                {"g": "接收端", "nodes": [
                    {"id": "recv", "t": "接收方客户端", "s": "回 ACK,拉离线增量"}]},
            ],
            "edges": [
                {"f": "sender", "t": "gw", "l": "长连上行"},
                {"f": "gw", "t": "logic", "l": "投递"},
                {"f": "logic", "t": "store", "l": "先落库"},
                {"f": "logic", "t": "route", "l": "查在线路由"},
                {"f": "route", "t": "recv", "l": "在线直投"},
                {"f": "route", "t": "push", "l": "离线转推送"},
                {"f": "recv", "t": "logic", "l": "ACK 确认", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "单聊 / 群聊 / 系统通知的实时消息收发,支持文本、图片、语音等多媒体",
                "长连接接入:WebSocket 长连、心跳保活、断线重连、多端登录同步",
                "可靠投递:应用层 ACK、消息去重(msgId)、会话内有序(seq)、失败重投",
                "离线消息:离线暂存、上线按已读位点增量拉取、离线转系统推送",
                "群聊扩散:小群写扩散、大群读扩散、已读回执与未读数",
            ],
            "quality": [
                {"k": "消息可达率", "v": "> 99.99%", "n": "IM 生命线,靠应用层 ACK + 重投 + 离线补齐,不能丢"},
                {"k": "端到端延迟", "v": "< 200ms", "n": "在线消息秒达才有实时感,靠长连主动推而非轮询"},
                {"k": "单机连接数", "v": "百万级", "n": "海量长连的核心指标,靠 epoll / 多路复用扛"},
                {"k": "消息有序", "v": "会话内严格有序", "n": "靠单调递增 seq,乱序会让对话逻辑错乱"},
                {"k": "多端一致", "v": "各端进度同步", "n": "多端登录各端 seq 同步,消息不重不漏"},
            ],
            "cons": [
                "TCP 可靠 ≠ 应用可靠:客户端崩溃时消息「已发未达」,必须应用层 ACK 兜底",
                "群聊放大存储与扩散:万人大群写扩散爆炸,须按群规模切读扩散",
                "移动端弱网频繁断连:重连要指数退避避免风暴,离线要转系统推送",
            ],
        },
        "datamodel": [
            {"e": "消息内容", "s": "分布式存储(HBase 类)", "r": "海量、按会话+seq 范围读"},
            {"e": "会话 / 收件箱", "s": "KV + seq 索引", "r": "写扩散每人一份,按 seq 拉增量"},
            {"e": "在线路由(uid→网关)", "s": "Redis KV", "r": "高频读写,实时可查"},
            {"e": "离线消息", "s": "离线库 + 引用", "r": "群消息存引用,拉时聚合"},
            {"e": "已读位点 / 未读数", "s": "KV(位点)", "r": "高频写合并,只存位点"},
            {"e": "群成员关系", "s": "关系存储", "r": "扩散时查成员,大群缓存"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "单聊长连", "detail": "WebSocket + ACK + 单机路由,写扩散"},
            {"stage": "成长期", "focus": "群聊 + 离线", "detail": "读写扩散分流、离线消息、系统推送兜底"},
            {"stage": "成熟期", "focus": "海量 + 多端", "detail": "百万长连、多端同步、大群读扩散优化"},
        ],
        "pitfalls": [
            "只依赖 TCP 不做应用 ACK:客户端崩溃时消息「已发未达」,可达率直接崩",
            "群聊全用写扩散:万人大群每人存一份,存储和写入瞬间爆炸",
            "离线群消息给每人存一份:大群离线存储爆炸,应存引用 + 拉时聚合",
            "已读回执逐条记录每人状态:高频写 + 存储放大,应只维护已读位点",
            "心跳间隔不合理:太长留大量死连接耗资源,太短误杀活连接又费电费流量",
            "网关扩缩容不更新路由:消息投到已断开的网关直接丢失",
            "seq 不做单调保证:多端 / 重投导致乱序,对话逻辑错乱",
        ],
        "takeaways": [
            "应用层 ACK 是底线:TCP 可靠只到网络层,消息可达必须靠应用确认 + 重投兜底",
            "按群规模切扩散:小群写扩散读得快,大群读扩散省存储,阈值分流别一刀切",
            "位点思维治高频:已读 / 未读 / 增量拉取都用 seq 位点,避免逐条记录的写放大",
            "长连接稳定性是命门:心跳、重连、路由更新一环出错就大面积掉线丢消息",
            "为弱网和多端设计:移动端断连是常态,多端登录是刚需,同步与兜底不能省",
        ],
    },
    {
        "slug": "live", "cn": "直播与互动娱乐", "en": "Live Streaming",
        "layer": "社交互动层", "color": "#0a84ff",
        "tagline": "秀场 / 电商 / 赛事直播 —— 一对多低延迟推拉流,核心是「采编转码 + CDN 分发 + 互动与审核」。",
        "groups": [
            {"g": "采集 · 转码", "nodes": [
                {"t": "推流采集", "p": "主播端采集编码,RTMP / SRT 推流到接入网关",
                 "d": "主播端采集音视频→编码→推流。推流协议:RTMP 兼容好但基于 TCP 延迟高,SRT / 私有 UDP 抗弱网低延迟。难点:主播端网络参差,推流侧也要做码率自适应,否则源头就卡。"},
                {"t": "实时转码", "p": "转多码率(1080p/720p/480p)供不同网络自适应",
                 "d": "一路源流转码成多档清晰度(转码集群 GPU 加速),端侧按网络自适应切换(ABR)。代价:转码耗 CPU/GPU 且引入延迟。难点:海量并发直播间的转码成本,冷门直播间可懒转码(有人看才转)。"},
                {"t": "协议选型", "p": "延迟档次:RTMP/HLS 秒级、LL-HLS 亚秒、WebRTC 毫秒",
                 "d": "按延迟诉求分档:普通直播 HLS / FLV(3~10s,兼容成本低)、低延迟 LL-HLS(1~2s)、连麦互动 WebRTC(<500ms)。本质是「延迟 vs 兼容性 vs 成本」权衡,秀场连麦须 WebRTC,赛事分发可 HLS。"},
            ]},
            {"g": "分发 · 加速", "nodes": [
                {"t":"CDN 分发", "p": "边缘节点就近拉流,回源分层缓存扛百万观众",
                 "d": "一对多分发的核心:观众就近从 CDN 边缘拉流,边缘未命中回源到中心。分层缓存 + 回源收敛避免源站被打穿。难点:热点直播间瞬时百万涌入,边缘节点与回源带宽的弹性扩容。"},
                {"t": "首帧优化", "p": "GOP 缓存 / 快速起播,秒开决定留存",
                 "d": "进直播间到看到画面的等待直接决定跳出。优化:边缘缓存最近一个 GOP(关键帧起播)、预连接、降低起播缓冲。首帧每多 1 秒跳出率显著上升,是直播体验第一指标。"},
                {"t": "边缘调度", "p": "按地域 / 负载调度观众到最优边缘节点",
                 "d": "DNS / HTTPDNS 按用户地域、节点负载、链路质量调度到最优边缘。难点:热点直播间的流量倾斜,须动态扩容边缘并做负载均衡,避免单节点被打挂。"},
            ]},
            {"g": "互动 · 审核", "nodes": [
                {"t": "弹幕 / 礼物", "p": "海量弹幕靠长连广播,高频写合并 + 限流削峰",
                 "d": "弹幕 / 点赞 / 礼物是高频写广播:百万观众同时发,须合并批量 + 采样下发(不是每条都推给每个人)。礼物涉及资金须可靠(不能丢),弹幕可采样丢弃。用长连接广播,分区扩散降压。"},
                {"t": "连麦 / 互动", "p": "主播连麦 / 观众上麦走 WebRTC,与直播流混流",
                 "d": "连麦是实时互动(WebRTC 低延迟),连麦画面再与主播流混流后走 CDN 分发给普通观众。难点:互动流(毫秒)与分发流(秒级)两套体系的衔接与混流延迟控制。"},
                {"t": "内容审核", "p": "画面 / 语音 / 弹幕实时机审 + 人审,违规即断流",
                 "d": "直播内容强监管:视频抽帧 + 语音转写 + 弹幕文本实时送审(AI 机审兜底 + 人工复审)。违规即时断流 / 打码 / 禁言。难点:实时性(违规几秒内处置)与误伤率的平衡,漏审是合规红线。"},
            ]},
        ],
        "insight": "直播的本质是「一对多的低延迟内容分发 + 实时互动」——它把 CDN 分发的规模挑战和音视频的延迟挑战叠加在一起。最反直觉的一点:直播不是一套延迟标准,而是按场景分档——赛事 / 秀场普通观看容忍秒级(HLS + CDN 扛规模),连麦 / 电商互动要毫秒级(WebRTC),两套体系还要衔接混流。首帧秒开看似小事,却是留存第一杀手,靠边缘 GOP 缓存和预连接抢那几百毫秒。互动侧的弹幕 / 礼物是典型高频写广播,百万人同时刷,靠合并 + 采样下发而非逐条推。内容审核则是不可省的合规红线,违规须秒级处置。真正的护城河在 CDN 分发的弹性扩容能力与「延迟 - 规模 - 成本」的动态平衡。",
        "tension": {
            "left": {"label": "低延迟 · 强互动", "items": [
                "连麦 / 电商要毫秒级", "WebRTC 抗弱网低延迟", "首帧秒开决定留存", "互动流与分发流衔接"]},
            "right": {"label": "大规模 · 省成本", "items": [
                "百万观众靠 CDN 分发", "HLS / FLV 兼容成本低", "多码率转码耗算力", "边缘弹性扛热点倾斜"]},
            "core": "本质是一对多分发规模与音视频延迟的叠加;按场景分档(秒级观看 vs 毫秒互动),在延迟-规模-成本间动态平衡。",
        },
        "funnel": [
            {"stage": "推流采集", "qps": "1 路源流", "note": "主播端编码推流"},
            {"stage": "多码率转码", "qps": "3~4 档", "note": "1080p/720p/480p 供自适应"},
            {"stage": "CDN 边缘分发", "qps": "百万观众", "note": "就近拉流,回源收敛"},
            {"stage": "弹幕 / 礼物", "qps": "50万/s", "note": "高频写广播,合并采样"},
            {"stage": "内容审核", "qps": "全量抽帧", "note": "机审兜底,违规秒级断流"},
        ],
        "flow": {
            "lanes": [
                {"g": "推流端", "nodes": [
                    {"id": "streamer", "t": "主播端推流", "s": "采集编码,RTMP/SRT"}]},
                {"g": "接入 / 转码", "nodes": [
                    {"id": "ingest", "t": "推流接入网关", "s": "鉴权,回源中心"},
                    {"id": "transcode", "t": "实时转码", "s": "转多码率 ABR"}]},
                {"g": "分发", "nodes": [
                    {"id": "origin", "t": "源站 / 中心", "s": "分层缓存,回源收敛"},
                    {"id": "cdn", "t": "CDN 边缘", "s": "就近拉流,GOP 秒开"}]},
                {"g": "互动", "nodes": [
                    {"id": "danmu", "t": "弹幕 / 礼物", "s": "长连广播,合并采样"},
                    {"id": "audit", "t": "内容审核", "s": "抽帧机审,违规断流"}]},
                {"g": "观众端", "nodes": [
                    {"id": "viewer", "t": "观众端播放", "s": "自适应拉流,发弹幕"}]},
            ],
            "edges": [
                {"f": "streamer", "t": "ingest", "l": "推流"},
                {"f": "ingest", "t": "transcode", "l": "转码"},
                {"f": "transcode", "t": "origin", "l": "多码率入源"},
                {"f": "origin", "t": "cdn", "l": "边缘拉流"},
                {"f": "cdn", "t": "viewer", "l": "就近下发"},
                {"f": "ingest", "t": "audit", "l": "抽帧送审"},
                {"f": "viewer", "t": "danmu", "l": "发弹幕/礼物"},
                {"f": "danmu", "t": "viewer", "l": "广播下发", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "推流采集编码:主播端采集音视频,H.264/H.265 编码,RTMP/SRT 推流",
                "实时转码多档:一路源流转多码率(ABR),适配不同网络与终端",
                "CDN 边缘分发:源站分层缓存 + 就近拉流,GOP 对齐做秒开",
                "弹幕礼物广播:长连接下发互动消息,高并发下合并采样限速",
                "内容审核断流:抽帧机审 + 人工复核,违规实时断流合规",
            ],
            "quality": [
                {"k": "首帧秒开", "v": "P99 < 1s", "n": "首帧耗时直接决定进房留存,GOP 缓存 + 边缘预热是关键"},
                {"k": "卡顿率", "v": "< 1%", "n": "卡顿是直播体验杀手,ABR 自适应 + 边缘调度压降卡顿"},
                {"k": "并发观众", "v": "百万级/场", "n": "头部直播瞬时涌入,靠 CDN 边缘水平扩容承接"},
                {"k": "端到端延迟", "v": "按档 3s~200ms", "n": "普通直播 HLS 3~6s,连麦互动 WebRTC 降到百毫秒级"},
                {"k": "审核时效", "v": "秒级", "n": "违规内容须秒级发现断流,合规红线不可逾越"},
            ],
            "cons": [
                "一对多海量分发:一路源流放大到百万观众,规模全靠 CDN 边缘承接",
                "延迟与流畅权衡:低延迟(WebRTC)牺牲缓冲抗抖,高流畅(HLS)牺牲实时性",
                "审核合规红线:直播实时性强,违规须秒级断流,漏审是平台生死线",
            ],
        },
        "datamodel": [
            {"e": "直播流元数据", "s": "关系型 DB + 缓存", "r": "开播状态、推拉流地址"},
            {"e": "转码档位", "s": "配置 + 任务队列", "r": "多码率规格、转码调度"},
            {"e": "CDN 边缘缓存", "s": "边缘节点 + 源站", "r": "GOP 缓存、就近下发"},
            {"e": "弹幕 / 礼物", "s": "长连接 + MQ", "r": "高并发广播、合并采样"},
            {"e": "礼物流水", "s": "关系型 DB(分片)", "r": "事务、对账结算"},
            {"e": "审核记录", "s": "对象存储 + 日志", "r": "抽帧留证、合规追溯"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "单区 HLS", "detail": "RTMP 推流、单档转码、HLS 拉流,延迟高但简单"},
            {"stage": "成长期", "focus": "多码率 + CDN", "detail": "ABR 多档转码、CDN 边缘分发、GOP 秒开优化"},
            {"stage": "成熟期", "focus": "低延迟连麦", "detail": "WebRTC 连麦互动、边缘调度、弹幕采样、实时审核"},
        ],
        "pitfalls": [
            "首帧不优化:不做 GOP 缓存 / 边缘预热,进房转圈几秒,用户直接跳出",
            "弹幕全量广播:百万观众每条弹幕全量下发,长连接瞬间被打挂",
            "转码不分档:只出一路高码率,弱网观众持续卡顿,ABR 形同虚设",
            "审核走离线:直播实时性强却用离线审核,违规内容已传播才发现",
            "回源不收敛:边缘未命中全部回源站,热点直播瞬间打爆源站带宽",
            "热点不弹性:头部主播瞬时百万涌入,CDN 不能秒级扩容就大面积卡顿",
            "延迟档位混用:所有场景都追极低延迟,牺牲流畅度得不偿失",
        ],
        "takeaways": [
            "按场景分延迟档:普通直播用 HLS 求流畅,连麦互动用 WebRTC 求实时,不要一刀切",
            "首帧是留存命门:GOP 缓存 + 边缘预热 + 快速起播,秒开直接决定进房转化",
            "弹幕要合并采样:高并发下按窗口聚合 + 降采样广播,别让互动流打垮长连接",
            "分发全靠 CDN:一对多规模只能靠边缘水平扩容,源站只做回源收敛",
            "审核不可省不可缓:抽帧机审 + 秒级断流是合规底线,离线审核在直播场景失效",
        ],
    },
    {
        "slug": "risk", "cn": "实时风控与反欺诈决策", "en": "Real-Time Risk Control",
        "layer": "增长风控层", "color": "#7c3aed",
        "tagline": "信贷审批 / 营销防刷 —— 毫秒级识别欺诈与风险,核心是实时特征 + 规则引擎 + 图计算。",
        "groups": [
            {"g": "决策引擎", "nodes": [
                {"t": "规则引擎", "p": "可配置规则集(Drools / 自研 DSL),命中即拦截或加验",
                   "d": "规则可业务热更新(改阈值不发版)。优势:可解释(监管要求)、响应快(毫秒)。缺陷:规则爆炸后维护难、易被黑产试探绕过。故与模型互补:规则守可解释底线,模型抓未知模式。"},
                {"t": "模型评分", "p": "GBDT / 深度模型输出风险分,与规则组合决策",
                 "d": "GBDT 处理表格特征稳健、可解释性尚可,是风控主力;深度模型抓复杂交互但黑盒。与规则组合(如分>0.8 拒、0.5~0.8 加验)。核心难点:样本极不均衡(欺诈占比 <1%)、标签滞后(欺诈数月后才确认),需特殊采样与延迟反馈训练。"},
                {"t": "决策流编排", "p": "多策略串并联编排,灰度 / AB 实验对比效果",
                 "d": "串联(逐层过滤)省算力、并联(同时评估)降延迟。新策略必须灰度/AB 上线——风控改动直接影响交易通过率,激进上线可能误杀大量正常用户或放过欺诈,损失都是真金白银。"},
            ]},
            {"g": "实时特征", "nodes": [
                {"t": "实时特征计算", "p": "Flink 流式计算滑动窗口特征(近 N 次频次 / 金额)",
                 "d": "风控最强特征是行为序列:近 1 分钟登录几次、近 1 小时交易金额、设备近 24h 关联账号数,Flink 滑动窗口毫秒级可查。难点:窗口状态大(千万用户×多窗口)、要求 exactly-once(算错频次=误判)、乱序事件需 watermark 处理。"},
                {"t": "特征存储", "p": "在线特征库(Redis / HBase)低延迟读取,离线在线一致",
                 "d": "Redis(热)/HBase(全量)在线特征库支撑毫秒读。最大的坑是「训练-服务偏斜」:离线训练用的特征口径与在线计算不一致,模型线上失效。需特征平台统一定义,离线在线共用一套计算逻辑。"},
            ]},
            {"g": "关系挖掘", "nodes": [
                {"t": "图计算团伙识别", "p": "设备 / 账号 / IP 构图,社区发现挖掘欺诈团伙",
                 "d": "单点看正常的账号,放到设备/IP/WiFi/资金关系图里,团伙特征暴露无遗(百账号共用一设备)。用社区发现/标签传播/GNN 挖掘团伙。价值:抓「协同作案」这类单点规则抓不到的模式。难点:图规模亿级、实时更新与实时查询的性能。"},
                {"t": "名单体系", "p": "黑白灰名单实时命中,联合建模跨域风险",
                 "d": "命中是毫秒级 KV 查。关键:名单要有时效(误伤需申诉解禁)、要联合(设备黑则关联账号灰)、要反哺(决策结果动态回写),形成闭环。"},
            ]},
        ],
        "insight": "实时风控的本质是「在毫秒内、用不完整信息、做一个会直接损失真金白银的二元决策」——它的核心矛盾不是技术而是两类错误的权衡:漏放欺诈(漏杀)直接资损,误伤好人(误杀)损失体验与 GMV,而两者此消彼长,阈值调松调紧都是在两种亏损间选择。因此风控不是追求「零欺诈」,而是把损失控制在可接受成本内。技术上规则(可解释、抗监管)与模型(抓未知模式)、单点特征与图关系(抓团伙)必须互补,单靠任何一路都会被黑产针对性绕过。最隐蔽的坑是训练-服务特征偏斜:离线效果很好、上线全线失效。",
        "tension": {
            "left": {"label": "漏放欺诈(漏杀)", "items": [
                "直接资损真金白银", "阈值调松则漏杀增", "规则可解释抗监管", "图关系抓团伙"]},
            "right": {"label": "误伤好人(误杀)", "items": [
                "损失体验与 GMV", "阈值调紧则误杀增", "模型抓未知模式", "毫秒内用不完整信息判"]},
            "core": "核心矛盾不是技术而是两类错误的权衡,两者此消彼长;不追求零欺诈,而是把损失控制在可接受成本内。",
        },
        "funnel": [
           {"stage": "全量请求", "qps": "50,000", "note": "交易/登录/申贷事件"},
            {"stage": "名单命中", "qps": "48,000", "note": "黑名单直拒~4%"},
            {"stage": "规则过滤", "qps": "5,000", "note": "命中规则进入加验/评估"},
            {"stage": "模型评分", "qps": "1,500", "note": "高风险分需进一步决策"},
            {"stage": "人工/加验拦截", "qps": "300", "note": "最终拦截,其余放行"},
        ],
        "flow": {
            "lanes": [
                {"g": "事件接入", "nodes": [
                    {"id": "evt", "t": "业务事件", "s": "交易/登录/申贷请求"}]},
                {"g": "实时特征", "nodes": [
                    {"id": "flink", "t": "Flink 流式计算", "s": "滑动窗口频次/金额"},
                    {"id": "fstore", "t": "在线特征库", "s": "Redis/HBase 低延迟读"}]},
                {"g": "关系挖掘", "nodes": [
                    {"id": "graph", "t": "图计算团伙识别", "s": "设备/账号构图，社区发现"},
                    {"id": "list", "t": "名单体系", "s": "黑白灰名单实时命中"}]},
                {"g": "决策", "nodes": [
                    {"id": "rule", "t": "规则引擎", "s": "DSL 规则集，命中拦截"},
                    {"id": "model", "t": "模型评分", "s": "GBDT/深度模型风险分"}]},
                {"g": "处置", "nodes": [
                    {"id": "act", "t": "决策流编排", "s": "放行/加验/拒绝，AB 实验"}]},
            ],
            "edges": [
                {"f": "evt", "t": "flink", "l": "事件流"},
                {"f": "flink", "t": "fstore", "l": "特征写入"},
                {"f": "fstore", "t": "rule", "l": "读特征"},
                {"f": "fstore", "t": "model", "l": "读特征"},
                {"f": "graph", "t": "rule", "l": "团伙标签"},
                {"f": "list", "t": "rule", "l": "名单命中"},
                {"f": "rule", "t": "act", "l": "规则结果"},
                {"f": "model", "t": "act", "l": "评分结果"},
                {"f": "act", "t": "list", "l": "反哺名单", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "交易 / 登录 / 营销事件的毫秒级实时风险决策(放行 / 加验 / 拒绝)",
                "规则引擎:可热更新的 DSL 规则集,命中即拦截或加验",
                "实时特征计算:Flink 滑窗统计近 N 次频次 / 金额等行为特征",
                "模型评分:GBDT / 深度模型输出风险分,与规则组合决策",
                "关系图谱团伙识别 + 黑白名单动态回写闭环",
            ],
            "quality": [
                {"k": "决策延迟", "v": "P99 < 100ms", "n": "卡在交易主链路,慢一点就拖累支付成功率"},
                {"k": "可解释性", "v": "每次拒绝可回溯命中规则", "n": "监管要求 + 客诉申诉,黑盒模型不能单独拍板"},
                {"k": "召回 / 误杀", "v": "欺诈召回高、误杀率 < 0.1%", "n": "误杀正常用户直接流失,漏过欺诈直接资损,双约束"},
                {"k": "特征时效", "v": "行为到特征 < 1s", "n": "欺诈是瞬时爆发,特征滞后就等于没拦"},
                {"k": "规则时效", "v": "改阈值秒级生效不发版", "n": "黑产变招极快,规则须能热更新快速对抗"},
            ],
            "cons": [
                "样本极不均衡:欺诈占比常 < 1%,且标签滞后数月才确认,训练难",
                "对抗性:黑产会主动试探绕过,策略必须持续演进而非一劳永逸",
                "误杀与漏过双向代价:两类错误都是真金白银,阈值是艰难的经营权衡",
            ],
        },
        "datamodel": [
            {"e": "实时特征", "s": "Redis/HBase 特征库", "r": "毫秒读、离线在线一致"},
            {"e": "滑窗状态", "s": "Flink 状态后端", "r": "exactly-once、防误判"},
            {"e": "关系图谱", "s": "图数据库", "r": "亿级点边、社区发现"},
            {"e": "名单库", "s": "Redis KV", "r": "毫秒命中、动态回写"},
            {"e": "决策流水", "s": "分库分表", "r": "可追溯、抗监管"},
            {"e": "模型样本", "s": "数仓+对象存储", "r": "延迟标签、离线训练"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "规则引擎", "detail": "DSL 规则、名单命中、可解释拦截"},
            {"stage": "成长期", "focus": "实时特征+模型", "detail": "Flink 滑窗、GBDT 评分、规则模型组合"},
            {"stage": "成熟期", "focus": "图计算+闭环", "detail": "团伙识别、决策灰度、反哺名单闭环"},
        ],
        "pitfalls": [
            "纯模型不留规则:全黑盒决策无法解释,监管过不了、申诉说不清",
            "特征离线在线不一致:训练用离线特征、线上用另一套,模型效果直接失真",
            "规则改动不灰度:风控直连交易通过率,激进上线可能瞬间误杀大批正常用户",
            "只看单点特征:不做滑窗 / 图关联,识别不出批量注册、团伙套现等群体欺诈",
            "标签滞后当无标签:忽略欺诈数月后才确认,训练样本用错标签越训越偏",
            "名单不闭环:识别出的坏账号不回写名单,同一黑产换个入口又能进来",
            "同步串联所有策略:决策链路全串行,规则一多延迟叠加拖垮交易主链路",
        ],
        "takeaways": [
            "规则守底线、模型抓未知:规则保可解释与快速对抗,模型补未知模式,两者互补",
            "在线离线特征同源:用同一套特征定义 / 计算逻辑,杜绝训练-服务偏差",
            "任何策略先灰度:风控改动都可能造成资损,AB / 灰度是上线的强制前置",
            "从点到图看关系:欺诈往往成团,图计算 + 社区发现能抓单点特征看不到的团伙",
            "决策要闭环反哺:识别结果回写名单 / 样本,让系统在对抗中持续进化",
        ],
    },
    {
        "slug": "search", "cn": "搜索引擎与检索", "en": "Search Engine",
        "layer": "内容发现层", "color": "#0369a1",
        "tagline": "全网搜 / 电商搜 / 站内搜 —— 从海量文档中检索最相关结果,核心是倒排索引 + 分词 + 向量召回 + 相关性排序。",
        "groups": [
            {"g": "检索基础", "nodes": [
                {"t": "倒排索引", "p": "分词建倒排,ES / Lucene,布尔检索 + 相关性打分(BM25)",
                 "d": "BM25 综合词频、逆文档频率、文档长度打分。局限:只能字面匹配,「番茄」搜不到「西红柿」——语义鸿沟需向量检索补。分词质量直接决定召回率,中文尤甚。"},
                {"t": "中文分词", "p": "IK / 自研分词器,词典 + 新词发现,同义词 / 纠错扩展",
                 "d": "中文无天然空格,分词是检索质量的第一道关:切错词直接召不回。难点:歧义切分(「南京市长江大桥」)、新词发现(网络热词/品牌名)、专有名词保护。配合同义词库、拼音纠错、query 改写把用户真实意图对齐到索引词。"},
                {"t": "索引更新", "p": "近实时索引(NRT),增量 + 全量重建,冷热分层",
                 "d": "NRT 索引让新文档秒级可搜:增量写入内存段+定期合并、全量定期重建纠偏。难点:写入与查询争资源、段合并引发查询抖动、删除是标记而非物理删(需定期 compact)。冷热分层控成本。"},
            ]},
            {"g": "语义与排序", "nodes": [
                {"t": "向量检索", "p": "Embedding + ANN(HNSW / IVF),语义召回补关键词召回",
                 "d": "精确 KNN 太慢,用 ANN(HNSW 图索引查询快、IVF 倒排聚类省内存)近似。权衡:召回率 vs 延迟 vs 内存。向量召回补关键词的语义盲区,但可能召回「相关但不精确」的结果,需排序把关。2025 新增变量:大模型入场做 query 理解与改写(纠错/扩展/意图补全),再用改写后的 query 向量化,让语义召回更贴真实意图。"},
                {"t": "相关性排序", "p": "BM25 + LTR(Learning to Rank),多特征融合排序",
                 "d": "字面 BM25 只是基线,真实相关性还看点击反馈、文档质量、时效、权威度等。LTR 用机器学习模型(GBDT/深度)融合数十维特征学排序,把「相关」量化。难点:训练样本靠点击日志(有位置偏差需纠偏)、离线 NDCG 与线上体验可能背离。"},
                {"t": "Query 理解", "p": "分词 + 纠错 + 意图识别 + 改写扩展",
                 "d": "搜索有明确 query(意图强),理解质量决定检索天花板:错字纠正(「iphont」→「iphone」)、意图识别(导航/信息/交易)、同义扩展、大模型改写。理解偏差会让后续召回排序全盘皆错——query 是搜索的入口也是命门。"},
            ]},
            {"g": "性能与运维", "nodes": [
                {"t": "分片与副本", "p": "索引分片水平扩容 + 副本高可用,聚合归并",
                 "d": "单机装不下全量索引,按 shard 水平切分并行检索、再归并打分。副本既做高可用又分摊查询压力。难点:分片数一旦定难改、聚合(如全局 Top-K)需跨分片归并、深分页代价大。"},
                {"t": "缓存与降级", "p": "热门 query 缓存 + 慢查询兜底 + 熔断降级",
                 "d": "头部 query 高度集中,结果缓存挡掉大部分重复检索。慢查询(通配/深分页)要限流兜底,避免拖垮集群。极端下降级为简化召回保可用,是搜索稳定性的最后防线。"},
            ]},
        ],
        "insight": "搜索的本质是「用毫秒把用户的一句话对齐到海量文档里最相关的那几条」。它由两条链路支撑:一条是字面链路(分词 → 倒排 → BM25),快而精确但有语义鸿沟;一条是语义链路(Embedding → ANN),补字面盲区但引入近似噪声。两条召回汇合后靠相关性排序(BM25→LTR)做精细打分,最终十几条呈现。最深的认知是:query 理解是天花板(理解偏了后面全错)、召回决定能不能搜到(没召回的永远排不出)、排序决定好不好(相关性量化)。搜索与推荐同源异形——搜索有明确 query(意图强、需理解),推荐无 query(需猜意图),但倒排/向量/排序的技术底座高度共用。",
        "tension": {
            "left": {"label": "召回(能搜到)", "items": [
                "分词/query 理解定上限","倒排求精确、向量补语义", "没召回的永远排不出", "全库千万文档"]},
            "right": {"label": "排序(搜得好)", "items": [
                "BM25 基线 + LTR 精排", "相关性靠多特征量化", "毫秒延迟内算完", "最终只呈现十几条"]},
            "core": "字面链路快而有语义鸿沟,语义链路补盲区但有噪声;两路汇合后排序把关,query 理解是全链路天花板。",
        },
        "funnel": [
            {"stage": "全库文档", "qps": "10,000,000", "note": "倒排+向量索引全量"},
            {"stage": "召回候选", "qps": "10,000", "note": "倒排+向量融合去重"},
            {"stage": "BM25 粗排", "qps": "500", "note": "字面相关性初筛"},
            {"stage": "LTR 精排", "qps": "50", "note": "多特征模型精细打分"},
            {"stage": "结果呈现", "qps": "10", "note": "去重+业务规则,最终展现"},
        ],
        "flow": {
            "lanes": [
                {"g": "查询接入", "nodes": [
                    {"id": "q", "t": "Query 理解", "s": "分词/纠错/意图识别/改写"}]},
                {"g": "召回", "nodes": [
                    {"id": "inv", "t": "倒排召回", "s": "BM25 关键词检索"},
                    {"id": "ann", "t": "向量召回", "s": "HNSW/IVF 语义召回"}]},
                {"g": "融合", "nodes": [
                    {"id": "merge", "t": "融合去重", "s": "两路合并候选集"}]},
                {"g": "排序", "nodes": [
                    {"id": "bm25", "t": "BM25 粗排", "s": "字面相关性初筛"},
                    {"id": "ltr", "t": "LTR 精排", "s": "多特征模型打分"}]},
                {"g": "呈现", "nodes": [
                    {"id": "out", "t": "结果呈现", "s": "去重+业务规则"}]},
            ],
            "edges": [
                {"f": "q", "t": "inv", "l": "关键词"},
                {"f": "q", "t": "ann", "l": "Embedding"},
                {"f": "inv", "t": "merge", "l": "候选"},
                {"f": "ann", "t": "merge", "l": "候选"},
                {"f": "merge", "t": "bm25", "l": "粗筛"},
                {"f": "bm25", "t": "ltr", "l": "Top-K"},
                {"f": "ltr", "t": "out", "l": "精排结果"},
            ],
        },
        "req": {
            "func": [
                "Query 理解:分词 → 纠错 → 意图识别 → 同义/大模型改写",
                "关键词检索:倒排召回 + BM25 字面相关性打分",
                "语义召回:向量化 + ANN 近似检索补字面不匹配的结果",
                "相关性排序:BM25 粗排 + LTR 多特征模型精排",
                "结果呈现:去重 + 业务规则 + 高亮/摘要,支持筛选与分页",
            ],
            "quality": [
                {"k": "检索延迟", "v": "P99 < 200ms", "n": "搜索是即时交互,慢半秒用户就流失"},
                {"k": "召回率", "v": "倒排+向量互补 > 95% 相关", "n": "漏召回的结果排序再强也救不回来"},
                {"k": "相关性", "v": "以 NDCG / 点击为核心", "n": "搜索价值由结果相关性而非纯延迟定义"},
                {"k": "索引时效", "v": "近实时(秒~分钟)可见", "n": "新内容 / 下架须快速反映,否则搜陈或搜死链"},
                {"k": "分词质量", "v": "切词准确率高", "n": "中文切错词直接召不回,分词是检索第一道关"},
            ],
            "cons": [
                "语义鸿沟:倒排只能字面匹配,「番茄」搜不到「西红柿」,需向量补",
                "召回-排序漏斗:召回漏了排序无法弥补,倒排+向量须互补",
                "相关性主观:不同用户对「相关」预期不同,需靠点击反馈持续校准",
            ],
        },
        "datamodel": [
            {"e": "倒排索引", "s": "ES/Lucene", "r": "关键词检索、BM25"},
            {"e": "向量索引", "s": "HNSW/IVF 向量库", "r": "语义召回、ANN 近似"},
            {"e": "分词词典", "s": "词典+同义词库", "r": "分词、纠错、扩展"},
            {"e": "排序特征", "s": "特征库", "r": "LTR 多特征、点击反馈"},
            {"e": "query 日志", "s": "数仓+日志", "r": "点击回收、纠偏训练"},
            {"e": "热门缓存", "s": "Redis", "r": "头部 query 结果缓存"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "倒排检索", "detail": "分词建索、BM25 打分、单路召回"},
            {"stage": "成长期", "focus": "向量+LTR", "detail": "向量召回、融合去重、LTR 精排"},
            {"stage": "成熟期", "focus": "理解+运维", "detail": "大模型改写、分片扩容、缓存降级"},
        ],
        "pitfalls": [
            "分词切错不治理:歧义切分/新词漏识别,query 从入口就召不回相关文档",
            "只用倒排不做向量:字面不匹配的语义相关内容全漏,召回天花板很低",
            "排序只靠 BM25:不引入点击/质量特征,头部结果长期不精准",
            "深分页硬翻:翻到第 N 页全量拉取归并,单查询就能拖垮集群",
            "索引更新滞后:下架内容还在搜、新品迟迟不出,搜死链或错失热点",
            "热门 query 不缓存:头部重复检索全打到底层,集群被少数 query 打满",
            "慢查询不兜底:通配/超长 query 不限流,一条烂查询拖垮整个搜索",
        ],
        "takeaways": [
            "query 理解是天花板:分词/纠错/意图理解偏了,后面召回排序全盘皆错",
            "倒排+向量互补:字面链路求精确、语义链路补盲区,两路融合才够覆盖",
            "排序要量化相关性:从 BM25 基线到 LTR 多特征,把「相关」交给模型学",
            "近实时索引要治理:增量+合并+定期重建,兼顾可搜时效与查询稳定",
            "缓存与降级是底线:热门 query 缓存 + 慢查询兜底,是搜索高可用的地基",
        ],
    },
    {
        "slug": "recommend", "cn": "个性化推荐系统", "en": "Recommendation System",
        "layer": "内容发现层", "color": "#0369a1",
        "tagline": "电商推荐 / 信息流 / 短视频 —— 无明确 query 下猜用户意图,核心是多路召回 + 粗排精排重排漏斗 + 特征平台 + AB 实验。",
        "groups": [
            {"g": "召回层", "nodes": [
                {"t": "多路召回", "p": "协同 / 内容 / 热门 / 向量多路并行,各取 Top-N 融合去重",
                 "d": "单路召回覆盖不全:协同过滤(ItemCF/UserCF)抓行为相似、内容召回抓属性相关、热门兜底冷启动、向量召回抓语义相似。多路并行各取 Top-N 再融合去重,提升召回覆盖率。核心权衡:路数越多覆盖越广但延迟越高、融合越复杂,需按业务价值分配每路配额。召回决定天花板——没召回的永远排不出来。"},
                {"t": "双塔向量召回", "p": "用户塔 + 物品塔独立编码,ANN 近邻检索",
                 "d": "双塔模型把用户和物品分别编码成向量,物品向量离线预计算入 ANN 索引,线上只算用户塔再做近邻检索,毫秒级召回海量候选。优点:解耦、可预计算、易扩展;局限:用户-物品交互在塔顶才融合,表达力弱于精排的交叉模型,故只用于召回不用于精排。"},
                {"t": "冷启动兜底", "p": "新用户 / 新物品无历史,靠热门 / 属性 / 探索兜底",
                 "d": "新用户无行为历史、新物品无曝光数据,纯个性化会推空或推歪。解法:新用户用热门/地域/人群包兜底并快速试探收集反馈,新物品用内容属性召回 + 强制曝光探索(EE 权衡)积累数据。冷启动做不好首屏体验极差,是留存的第一道坎。"},
            ]},
            {"g": "排序漏斗", "nodes": [
                {"t": "粗排", "p": "轻量模型(双塔 / LR)把万级候选砍到几百",
                 "d": "召回可能上万,精排模型贵(每条几十特征+深度网络),全量精排扛不住延迟。粗排用轻量模型快速打分砍量到几百,是「算力 vs 效果」的缓冲层。难点:粗排与精排目标要一致(否则粗排砍掉了精排想要的),常用蒸馏让粗排逼近精排。"},
                {"t": "精排", "p": "DIN / DeepFM 等交叉模型,建模用户-物品精细交互",
                 "d": "精排用复杂模型(DIN 注意力捕捉兴趣、DeepFM 显式特征交叉)对几百候选精细打分预估 CTR/CVR。这是效果的核心:数十上百维特征 + 深度网络建模交互。难点:模型越复杂延迟越高、特征越多训练-服务一致性越难保、离线 AUC 与线上转化常背离。"},
                {"t": "重排 / 打散", "p": "多样性打散 + 多目标 + 业务规则,兼顾体验与生态",
                 "d": "精排只看单点点击率,会导致结果同质化、头部垄断。重排引入多样性(打散同类)、新鲜度、业务规则(扶持新品/生态)、多目标(点击+时长+转化)。难点:多目标本质冲突需帕累托权衡,且要防「过度干预」伤害体验。2025 前沿:生成式推荐(LLM4Rec)直接生成候选,但离线指标与线上背离、AB 实验是唯一裁判这条铁律不变。"},
            ]},
            {"g": "特征与实验", "nodes": [
                {"t": "特征平台", "p": "用户 / 物品 / 上下文特征,实时 + 离线统一管理",
                 "d": "特征决定模型上限:用户画像(离线)、实时行为(近 N 次点击)、物品属性、上下文(时间/场景)。Feature Store 统一管理:离线批量 + 实时流式,在线拼接供打分,核心是解决训练-服务一致性(离线训练与线上服务同源同口径,否则模型上线即掉点)。避免各团队重复造轮子与口径漂移。"},
                {"t": "AB 实验平台", "p": "分流实验对比指标,支撑策略快速迭代",
                 "d": "推荐效果无法离线完全评估(离线 AUC 高≠线上转化高),必须 AB 实验看真实指标。关键:分流正交(多实验互不干扰)、样本充分(避免辛普森悖论)、长短期指标兼顾(点击涨但留存跌是陷阱)。实验平台是推荐策略迭代的基础设施——一切改动靠实验裁判。"},
            ]},
        ],
        "insight": "推荐系统的本质是「在没有 query 的情况下猜用户想要什么」,靠一个「逐级收窄的漏斗」实现:从千万级物品,经多路召回(覆盖)→粗排(算力妥协)→精排(精准)→重排(体验与生态),最终呈现十几条。每一级都在同一约束下权衡——用有限算力和毫秒延迟,从海量中挑出最相关的少数。最深的认知是:召回决定天花板(没召回的永远排不出来)、精排决定下限、重排决定体验与生态健康。而离线指标与线上效果常年背离(离线 AUC 高≠线上转化高),所以 AB 实验不是可选项而是唯一裁判。支撑整个漏斗高效运转的两块地基:特征平台(解决训练-服务一致性)和 AB 实验平台(裁判一切改动)。推荐与搜索同源异形——推荐无 query 需猜意图、搜索有 query 需理解,但召回-排序的技术底座高度共用。",
        "tension": {
            "left": {"label": "覆盖(召回)", "items": [
                "召回决定天花板", "多路召回求全", "没召回的永远排不出", "候选千万级"]},
            "right": {"label": "精准(排序算力)", "items": [
                "精排决定下限", "重排决定体验与生态", "毫秒延迟内算完", "最终只呈现十几条"]},
            "core": "同一约束下用有限算力从海量挑少数;离线指标与线上常年背离,AB 实验是唯一裁判。",
        },
        "funnel": [
            {"stage": "全库物品", "qps": "10,000,000", "note": "协同+向量+内容索引全量"},
            {"stage": "多路召回", "qps": "10,000", "note": "各路 Top-N 融合去重"},
            {"stage": "粗排", "qps": "500", "note": "轻量模型砍量"},
            {"stage": "精排", "qps": "50", "note": "DIN/DeepFM 精细打分"},
            {"stage": "重排呈现", "qps": "10", "note": "多样性+业务规则,最终曝光"},
        ],
        "flow": {
            "lanes": [
                {"g": "请求接入", "nodes": [
                    {"id": "req", "t": "推荐请求", "s": "用户+场景+上下文"}]},
                {"g": "召回层", "nodes": [
                    {"id": "cf", "t": "协同/内容召回", "s": "行为+属性相似"},
                    {"id": "vec", "t": "双塔向量召回", "s": "用户塔+ANN"},
                    {"id": "hot", "t": "热门/冷启召回", "s": "兜底探索"}]},
                {"g": "融合", "nodes": [
                    {"id": "merge", "t": "融合去重", "s": "多路合并候选集"}]},
                {"g": "排序漏斗", "nodes": [
                    {"id": "rough", "t": "粗排", "s": "轻量模型砍量"},
                    {"id": "fine", "t": "精排", "s": "DIN/DeepFM 打分"}]},
                {"g": "重排出", "nodes": [
                    {"id": "rerank", "t": "重排/打散", "s": "多样性+多目标"}]},
            ],
            "edges": [
                {"f": "req", "t": "cf", "l": "触发"},
                {"f": "req", "t": "vec", "l": "触发"},
                {"f": "req", "t": "hot", "l": "触发"},
                {"f": "cf", "t": "merge", "l": "候选"},
                {"f": "vec", "t": "merge", "l": "候选"},
                {"f": "hot", "t": "merge", "l": "候选"},
                {"f": "merge", "t": "rough", "l": "粗筛"},
                {"f": "rough", "t": "fine", "l": "Top-K"},
                {"f": "fine", "t": "rerank", "l": "精排结果"},
            ],
        },
        "req": {
            "func": [
                "多路召回:协同 / 内容 / 热门 / 双塔向量并行,各取 Top-N 融合去重",
                "粗排:轻量模型把万级候选砍到几百,平衡算力与效果",
                "精排:DIN / DeepFM 融合用户画像 + 实时行为 + 物品特征预估 CTR/CVR",
                "重排:多样性打散 + 多目标(点击 / 时长 / 转化)+ 业务规则",
                "冷启动兜底 + AB 实验分流迭代,一切改动靠实验裁判",
            ],
            "quality": [
                {"k": "推荐延迟", "v": "P99 < 200ms", "n": "信息流即时刷新,慢半秒用户就划走"},
                {"k": "召回率", "v": "多路互补覆盖 > 95% 相关", "n": "漏召回的物品精排再强也救不回来"},
                {"k": "点击 / 转化", "v": "以 CTR/CVR 为核心", "n": "推荐价值由业务指标而非离线 AUC 定义"},
                {"k": "特征时效", "v": "实时行为秒级入特征", "n": "刚点过的马上影响推荐,时效差就不「懂」用户"},
                {"k": "多样性", "v": "打散避免同质化", "n": "全推一类会审美疲劳,伤长期时长与留存"},
            ],
            "cons": [
                "召回-排序漏斗:每层砍量级,前面漏召回后面无法弥补,须多路互补",
                "冷启动:新用户 / 新物品无历史,纯个性化会推不准甚至推空",
                "指标多目标冲突:点击、时长、多样性、生态相互拉扯,无单一最优",
            ],
        },
        "datamodel": [
            {"e": "用户画像", "s": "KV+特征库", "r": "离线在线拼接"},
            {"e": "实时行为", "s": "Flink+Redis", "r": "近 N 次点击、低延迟"},
            {"e": "物品向量", "s": "HNSW/IVF 向量库", "r": "双塔召回、ANN 近似"},
            {"e": "协同矩阵", "s": "离线计算+KV", "r": "ItemCF/UserCF 召回"},
            {"e": "特征平台", "s": "Feature Store", "r": "统一口径、训练服务一致"},
            {"e": "实验数据", "s": "数仓+日志", "r": "AB 分流、指标回收"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "热门+协同", "detail": "热门榜兜底、ItemCF 召回、单路排序"},
            {"stage": "成长期", "focus": "多路+精排", "detail": "双塔向量召回、融合去重、DIN 精排"},
            {"stage": "成熟期", "focus": "重排+平台", "detail": "多样性多目标、特征平台、AB 实验迭代"},
        ],
        "pitfalls": [
            "召回单路走天下:只用协同或只用热门,覆盖面窄,召回天花板极低",
            "精排前不做粗排裁剪:把海量候选全喂精排,算力爆炸且延迟不可控",
            "特征在线离线不一致:训练用离线特征、线上另一套,模型上线即掉点",
            "无 AB 直接全量:凭感觉调策略,没实验对照根本分不清是涨是跌",
            "冷启动不兜底:新用户直接跑个性化,推空 / 推歪,首屏体验极差",
            "只优化单目标:一味追 CTR 导致标题党泛滥,长期伤害时长与生态",
            "推荐不打散:精排全推一类,结果同质化、头部垄断、用户审美疲劳",
        ],
        "takeaways": [
            "召回要广、排序要准:召回追全(多路互补),排序追准(粗排精排重排),分工别混",
            "多路互补而非单路:协同 / 向量 / 内容 / 热门各补一块,合并去重扩大覆盖面",
            "一切改动靠实验:推荐效果反直觉,AB 分流 + 指标回收是唯一可信的评判标准",
            "特征平台统一口径:在线离线同源、防漂移,是模型效果可复现的地基",
            "多目标而非单指标:点击 / 时长 / 多样性 / 生态联合优化,别为短期指标透支长期",
        ],
    },
    {
        "slug": "payment", "cn": "金融级支付与清结算", "en": "Payment & Settlement",
        "layer": "交易支付层", "color": "#1a7f52",
        "tagline": "钱包 / 收单 / 跨境汇兑 —— 资金零差错、可追溯,核心是分布式事务 + 幂等 + 对账。",
        "groups": [
            {"g": "分布式事务", "nodes": [
                {"t": "TCC / Saga", "p": "Try-Confirm-Cancel 或 Saga 补偿,保证跨服务资金一致",
                 "d": "跨服务转账无法用本地事务。TCC 两阶段(Try 冻结→Confirm 扣/Cancel 解)强隔离但侵入业务重;Saga 顺序执行+反向补偿,轻量但无隔离(中间态可见)。资金强场景多用 TCC。核心难点:空回滚、悬挂、幂等三大异常必须全部处理,否则资金错乱。"},
                {"t": "本地消息表", "p": "业务与消息同库事务,最终一致,可靠投递下游",
                 "d": "业务操作与「待发消息」写同一本地事务(解决双写不一致),再由投递器轮询发 MQ、下游幂等消费。牺牲实时一致换最终一致,比分布式事务轻,是支付异步链路主力。代价:有秒级延迟、需清理已投递消息。"},
                {"t": "对账兜底", "p": "日终批量对账 + 差错处理,兜住极端不一致",
                 "d": "无论前面多可靠,分布式系统总有极端不一致(网络分区、宕机丢消息)。日终把本方账务与渠道/银行流水逐笔比对,差错进差错池人工/自动冲正。这是资金安全的最后防线——前面所有机制都是「尽量不出错」,对账是「出错了也能发现并修复」。"},
            ]},
            {"g": "资金安全", "nodes": [
                {"t": "幂等控制", "p": "全链路幂等键,防重复扣款 / 多次入账",
                 "d": "网络重试、消息重投、用户重复点击都会导致重复请求,支付重复=资损。全链路幂等键(交易流水号)+唯一索引/状态机保证「同一笔只处理一次」。难点:幂等要贯穿受理→事务→账务→渠道全链路,任一环漏了都可能重复扣款。"},
                {"t": "账务复式记账", "p": "借贷记账、试算平衡,每笔资金可追溯审计",
                 "d": "借贷恒等(试算平衡)让资金守恒可校验、可追溯、可审计——金融账务的铁律,非普通 CRUD。任何时点可验证账平不平,错账立即暴露。监管强制要求,不可用「余额直接加减」替代。"},
                {"t": "冷热资金隔离", "p": "核心账务库高可靠强一致,与流水日志分离",
                 "d": "核心账户余额(强一致、高可靠、必须准)与海量流水日志(可最终一致、可分库)分离。核心库轻量保稳,流水库承载查询压力。避免流水查询/统计拖垮核心记账。这是支付系统在「一致性」与「性能」间的关键切分。"},
            ]},
            {"g": "高可用", "nodes": [
                {"t": "单元化 / 多活", "p": "异地多活单元化部署,故障切换资金不丢",
                 "d": "按用户维度切分单元(uid 路由),每单元自包含完整链路,单元内闭环、跨单元少交互。异地多活容灾:一地故障切另一地,资金零丢失(依赖同步复制/对账)。难点:单元切分需避免热点、跨单元交易(转账)需特殊处理、数据同步与一致性。"},
                {"t": "限流降级", "p": "核心链路保护,非核心降级,守住资金主流程",
                 "d": "大促洪峰时,营销/积分/通知等非核心可降级,但支付/记账主流程必须活。核心链路预留容量、非核心随时可断。原则:宁可少赚(降级营销)不可错账(牺牲资金一致)。降级预案需演练,真出事时按预案执行而非临场决策。"},
            ]},
        ],
        "insight": "金融级支付的第一性原理是「资金零差错」——它与互联网大多数场景的价值观相反:别处追求可用性和性能、允许最终一致甚至少量丢数据,支付则是「宁可慢、宁可拒绝服务,绝不能算错一分钱」。这个约束层层传导:分布式事务(TCC/Saga)保证跨服务一致、幂等防重复扣款、复式记账让每笔可校验可追溯、对账作为最后防线兜住极端不一致。最深刻的认知是没有任何单一机制能保证 100% 正确,所以是「多层防御 + 对账兜底」:前面所有机制降低出错概率,对账保证「即使出错也能发现和修复」。而资金一致永远优先于性能和体验——这是支付架构一切取舍的原点。",
        "tension": {
            "left": {"label": "资金零差错(第一性)", "items": [
                "宁可慢、宁可拒服务", "分布式事务 TCC/Saga", "幂等防重复扣款", "复式记账 + 对账兜底"]},
            "right": {"label": "可用性与性能诉求", "items": [
                "别处允许最终一致", "别处追求高吞吐低延迟", "支付则牺牲之以求正确", "资金一致永远优先"]},
            "core": "价值观与多数互联网场景相反:绝不能算错一分钱;没有单一机制保证 100% 正确,故多层防御 + 对账兜底。",
        },
        "funnel": [
            {"stage": "支付请求", "qps": "10,000", "note": "幂等键去重+限流"},
            {"stage": "事务协调", "qps": "9,800", "note": "TCC Try 冻结/Saga 启动"},
            {"stage": "复式记账", "qps": "9,700", "note": "借贷平衡写核心账务"},
            {"stage": "渠道投递", "qps": "9,600", "note": "可靠投递银行/渠道"},
            {"stage": "日终对账", "qps": "≈100%", "note": "逐笔比对,差错冲正兜底"},
        ],
        "flow": {
            "lanes": [
                {"g": "受理", "nodes": [
                    {"id": "gw", "t": "支付受理", "s": "幂等键+限流降级"}]},
                {"g": "事务协调", "nodes": [
                    {"id": "tcc", "t": "TCC / Saga 协调", "s": "跨服务资金一致"},
                    {"id": "msg", "t": "本地消息表", "s": "业务+消息同库事务"}]},
                {"g": "账务", "nodes": [
                    {"id": "acct", "t": "复式记账", "s": "借贷平衡，可追溯"},
                    {"id": "core", "t": "核心账务库", "s": "强一致，冷热隔离"}]},
                {"g": "下游", "nodes": [
                    {"id": "channel", "t": "渠道/银行", "s": "收单/汇兑"}]},
                {"g": "兜底", "nodes": [
                    {"id": "recon", "t": "日终对账", "s": "差错处理兜底"}]},
            ],
            "edges": [
                {"f": "gw", "t": "tcc", "l": "发起交易"},
                {"f": "tcc", "t": "acct", "l": "Try 冻结"},
                {"f": "acct", "t": "core", "l": "记账"},
                {"f": "tcc", "t": "msg", "l": "投递下游"},
                {"f": "msg", "t": "channel", "l": "可靠投递"},
                {"f": "channel", "t": "recon", "l": "对账文件"},
                {"f": "core", "t": "recon", "l": "账务流水"},
                {"f": "recon", "t": "acct", "l": "差错冲正", "d": "back"},
            ],
        },
        "req": {
            "func": [
                "下单支付:预下单、渠道路由、异步回调、状态同步",
                "记账清分:复式记账、多方分账、商户结算",
            "退款与冲正:原路退回、部分退、超时冲正",
                "对账:与渠道逐笔勾兑、差错自动挂账人工兜底",
                "资金安全:幂等防重、限额风控、敏感操作二次校验",
            ],
            "quality": [
                {"k": "资金准确性", "v": "零差错", "n": "任何一笔钱都必须记得清、对得上,差一分都要人工核查"},
                {"k": "核心链路可用性", "v": "99.99%", "n": "支付是交易最后一环,不可用直接等于收入损失"},
                {"k": "支付成功回调", "v": "P99 < 3s", "n": "用户付完款要尽快看到成功,否则重复支付投诉激增"},
                {"k": "对账时效", "v": "日终 T+1 全量", "n": "当天资金当天对平,差错越早发现处理成本越低"},
                {"k": "幂等保证", "v": "100%", "n": "网络重试/回调重发不能造成重复扣款或重复入账"},
            ],
            "cons": [
                "外部渠道不可控:银行/三方通道会超时、乱序、回调丢失,须以对账为最终真相",
                "强合规:资金流水不可篡改、可审计、留存年限受监管约束",
                "分布式事务无强一致银弹:跨服务扣款+记账须用 TCC/本地消息补偿而非 2PC",
            ],
        },
        "datamodel": [
            {"e": "核心账户", "s": "强一致关系库", "r": "冷热隔离、必须准"},
            {"e": "账务分录", "s": "复式记账库", "r": "借贷平衡、可审计"},
            {"e": "流水日志", "s": "分库分表", "r": "海量写、承载查询"},
            {"e": "幂等键", "s": "Redis+唯一索引", "r": "防重复扣款"},
            {"e": "本地消息", "s": "消息表+MQ", "r": "同库事务、可靠投递"},
            {"e": "对账文件", "s": "对象存储", "r": "逐笔比对、差错兜底"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "幂等+记账", "detail": "幂等键、复式记账、日终对账"},
            {"stage": "成长期", "focus": "分布式事务", "detail": "TCC 冻结、本地消息、可靠投递"},
            {"stage": "成熟期", "focus": "单元化多活", "detail": "异地多活、限流降级、资金零丢"},
        ],
        "pitfalls": [
            "用单库单表金额字段直接加减代替复式记账——对不出账、查不清资金去向,一旦差错无法定位",
            "跨服务扣款用分布式 2PC 追求强一致——同步阻塞、协调者单点,支付高并发下直接雪崩",
            "回调接口不做幂等——渠道回调重发导致同一笔重复入账/重复发货,资金凭空多出",
            "对账只对总额不逐笔——总额偶然对平掩盖了两笔方向相反的错账,差错被埋",
            "退款走独立链路不回冲原分录——账面退了但记账没冲,借贷失衡审计失败",
            "把三方渠道超时当失败直接置终态——渠道实际扣款成功造成掉单,须以对账为准而非猜测",
            "本地消息表不与业务同事务提交——消息发出了业务回滚了,或反之,产生幽灵订单",
        ],
        "takeaways": [
            "资金系统的第一性原理是可审计:复式记账让每一分钱都有借必有贷、恒等可查,这是差错兜底的地基",
            "外部渠道天然不可靠,对账是资金系统的最后一道防线——设计时就要假设回调会丢、会乱序、会重复",
            "分布式事务优先选补偿式(TCC/Saga/本地消息),用最终一致换可用性,强一致的 2PC 不适合高并发资金",
            "幂等不是可选项而是资金系统的生命线,以业务唯一键(而非请求 ID)作幂等边界才能真正防重",
            "状态机建模支付生命周期,只允许合法迁移,把超时/悬挂/空回滚等异常显式建模而非隐式兜底",
        ],
    },
    {
        "slug": "ad", "cn": "在线广告与实时竞价", "en": "Online Advertising & RTB",
        "layer": "增长风控层", "color": "#7c3aed",
        "tagline": "广告召回 / CTR-CVR 预估 / RTB 竞价 —— 用户体验、广告主 ROI、平台收入三方博弈,eCPM 统一度量。",
        "groups": [
            {"g": "竞价机制", "nodes": [
                {"t": "RTB 实时竞价", "p": "毫秒级实时竞价,ADX 发单、DSP 出价、赢家曝光",
                 "d": "一次广告请求触发实时竞价:ADX(交易平台)把流量拆成竞价请求发给各 DSP,DSP 在预算和定向约束下出价,最高者赢得曝光——全程须在 100ms 内闭环,超时即丢弃该 DSP 出价。关键是超低延迟下的高并发撮合。失败模式:某 DSP 超时拖慢整场竞价,须设硬超时+异步并发询价,慢的直接放弃而非阻塞全局。"},
                {"t": "eCPM 排序", "p": "eCPM = 出价 × 预估CTR × 预估CVR × 1000,统一度量收益",
                 "d": "不同计费模式(CPM/CPC/CPA)无法直接比价,统一折算成 eCPM(每千次展示期望收益)排序,让平台在同一把尺子下取收益最大者。核心是 eCPM 依赖预估的准确性——CTR/CVR 预估偏高会让低质广告挤掉优质广告。失败模式:预估系统性高估导致劣质广告长期占位,须校准(calibration)让预估值贴近真实点击率。"},
                {"t": "GSP 次价拍卖", "p": "广义次价拍卖,赢家按第二名出价计费,激励真实出价",
                 "d": "若按自己出价计费(首价),广告主会反复试探压低出价,市场不稳。GSP 让赢家只需支付「刚好超过第二名」的价格,理论上激励广告主按真实价值出价、简化博弈。权衡:GSP 非严格激励相容但工程简单被广泛采用,VCG 更优却复杂难解释。失败模式:首价拍卖下的出价博弈使收入与稳定性双输。"},
            ]},
            {"g": "预估模型", "nodes": [
                {"t": "CTR 预估", "p": "预估点击率,LR→GBDT→深度模型(Wide&Deep/DIN)演进",
                 "d": "eCPM 的核心因子,预估用户点击某广告的概率。特征含用户画像、广告创意、上下文、交叉特征,模型从 LR 到 Wide&Deep、DIN 演进以捕捉高阶交叉与兴趣。关键是特征时效——实时特征(近几分钟行为)比静态画像信息量大得多。失败模式:训练/服务特征不一致(线上线下特征口径漂移)导致预估失准,须特征平台统一。"},
                {"t": "CVR 预估", "p": "预估转化率,解决延迟转化与样本稀疏难题",
                 "d": "面向 CPA/oCPX 计费,预估点击后的转化概率。难点是转化延迟——用户可能点击数天后才下单,回流样本天然滞后,直接训练会把「还没转化」误标为负样本。须用延迟反馈建模(delayed feedback)或转化窗口修正。失败模式:样本稀疏(转化远少于点击)+延迟叠加使 CVR 模型方差大,须联合建模或迁移学习。"},
                {"t": "出价策略 oCPX", "p": "从人工 CPC 到智能出价,按转化目标自动调价",
                 "d": "oCPX(优化成本)让广告主设定目标成本,系统按实时预估 CVR 自动换算并动态调整出价,把「为点击出价」升级为「为转化出价」。核心是预算平滑与成本控制的博弈——既要花完预算又不能超成本。失败模式:出价策略与预估耦合,预估抖动引发出价震荡,须 PID/强化学习平滑控制。"},
            ]},
            {"g": "反作弊结算", "nodes": [
                {"t": "流量反作弊", "p": "识别机器刷量、无效点击,过滤虚假流量",
                 "d": "广告按曝光/点击计费,黑产用机器人、点击农场刷量骗取广告费。须多维识别:设备指纹、行为序列异常、IP 聚集、点击时间分布异常等,实时+离线双层拦截。关键是对抗性——规则一公开即被绕过,须持续迭代+模型化。失败模式:反作弊过严误杀真实用户,广告主投诉填充率骤降,须精细化平衡召回与精度。"},
                {"t": "计费与归因", "p": "曝光/点击/转化计费,多触点归因分配转化功劳",
                 "d": "计费须防重复计费(同一点击多次上报)与防刷,归因解决「这次转化该归功于哪次广告触达」——末次归因简单但低估前链路,多触点归因(线性/时间衰减/数据驱动)更公平但复杂。关键是计费流水的准确与可对账,涉及真金白银不能错。失败模式:归因口径与广告主统计不一致引发结算纠纷,须口径对齐+明细可查。"},
            ]},
        ],
        "insight": "在线广告是典型的三方博弈系统:用户要体验、广告主要 ROI、平台要收入,三者天然冲突,而 eCPM 是把它们统一到同一把尺子上的关键——它让「出高价的劣质广告」与「出低价的优质广告」可以公平比较,因为 eCPM = 出价 × 预估CTR × 预估CVR 同时编码了广告主意愿与用户偏好。最反直觉的认知是:广告系统的收入天花板不在竞价机制本身,而在预估的准确性——CTR/CVR 预估准一个百分点,收入与体验同时上涨;预估失准则要么劣质广告挤占流量伤体验,要么优质广告卖不上价伤收入。因此这类系统的工程重心是三件事:极低延迟下完成一场竞价(100ms 硬约束)、预估模型的准确与校准(训练服务一致、延迟反馈修正)、以及反作弊守住计费真实性(黑产刷量直接偷钱)。真正的难点不是排序算法,而是在对抗环境下让每一次曝光的计费都真实可对账。",
        "tension": {
            "left": {"label": "多方博弈诉求", "items": [
                "用户:体验不被打扰", "广告主:ROI/转化", "平台:收入最大化", "决策窗口:100ms 内"]},
            "right": {"label": "统一度量与对抗", "items": [
                "eCPM 统一比价", "预估准确性定收益", "GSP 激励真实出价", "反作弊守住计费真实"]},
        "core": "三方冲突靠 eCPM 统一度量,收入天花板取决于预估准确性,而非竞价机制本身;对抗环境下计费真实是底线。",
        },
        "funnel": [
            {"stage": "广告请求", "qps": "100%", "note": "一次曝光机会触发一次广告请求,峰值百万级 QPS"},
            {"stage": "召回定向", "qps": "×数百", "note": "按定向条件+预算从广告库召回候选广告"},
            {"stage": "CTR/CVR 预估", "qps": "候选级", "note": "逐候选打分,须在毫秒内完成批量预估"},
            {"stage": "eCPM 排序竞价", "qps": "取 Top", "note": "统一折算 eCPM 排序,GSP 定价出赢家"},
            {"stage": "曝光计费归因", "qps": "反作弊后", "note": "过滤无效流量后计费,多触点归因转化"},
        ],
        "flow": {
            "lanes": [
                {"g": "请求", "nodes": [
                    {"id": "req", "t": "广告请求", "s": "一次曝光机会"}]},
                {"g": "召回", "nodes": [
                    {"id": "recall", "t": "召回定向", "s": "预算+定向筛选"}]},
                {"g": "预估", "nodes": [
                    {"id": "ctr", "t": "CTR 预估", "s": "点击率"},
                    {"id": "cvr", "t": "CVR 预估", "s": "转化率"}]},
                {"g": "竞价", "nodes": [
                    {"id": "ecpm", "t": "eCPM 排序", "s": "统一折算"},
                    {"id": "gsp", "t": "GSP 定价", "s": "次价拍卖"}]},
                {"g": "结算", "nodes": [
                 {"id": "af", "t": "反作弊", "s": "过滤无效流量"},
                    {"id": "bill", "t": "计费归因", "s": "多触点分配"}]},
            ],
            "edges": [
                {"f": "req", "t": "recall", "l": "召回候选"},
                {"f": "recall", "t": "ctr", "l": "逐候选打分"},
                {"f": "ctr", "t": "cvr", "l": "转化预估"},
                {"f": "cvr", "t": "ecpm", "l": "折算收益"},
                {"f": "ecpm", "t": "gsp", "l": "取赢家"},
                {"f": "gsp", "t": "af", "l": "曝光校验"},
                {"f": "af", "t": "bill", "l": "有效计费"},
            ],
        },
        "req": {
            "func": [
                "广告召回定向:按人群/兴趣/地域/时段等条件从广告库召回候选",
                "预估打分:CTR/CVR 实时预估,毫秒内完成候选批量打分",
                "竞价排序:eCPM 统一折算排序,GSP 次价拍卖定价",
                "曝光计费:CPM/CPC/CPA 多计费模式,防重复防作弊计费",
                "归因结算:多触点归因分配转化功劳,明细可对账",
            ],
            "quality": [
                {"k": "竞价延迟", "v": "P99 < 100ms", "n": "一次竞价含召回+预估+排序,超时则丢弃该候选,延迟直接决定填充"},
                {"k": "预估准确性", "v": "AUC / 校准", "n": "CTR/CVR 预估既要区分度(AUC)又要校准(预估值贴近真实率)"},
                {"k": "填充率", "v": "尽量高", "n": "有广告请求却无广告返回是收入漏损,须平衡反作弊误杀与填充"},
                {"k": "反作弊准确", "v": "低漏低误", "n": "漏判被黑产偷钱,误判误杀真实流量,须精细平衡召回精度"},
                {"k": "计费准确", "v": "可对账", "n": "涉及真金白银,计费流水须与广告主统计口径一致、明细可查"},
            ],
            "cons": [
                "极低延迟:整场竞价 100ms 内闭环,预估必须在毫秒内完成批量打分",
                "对抗环境:黑产持续刷量骗费,反作弊规则一公开即被绕过,须持续对抗",
                "延迟反馈:转化可能滞后数天回流,CVR 训练样本天然不完整,须延迟建模",
            ],
        },
        "datamodel": [
            {"e": "广告库", "s": "创意+定向+预算", "r": "召回候选、预算约束"},
            {"e": "定向标签", "s": "人群/兴趣画像", "r": "定向匹配、召回过滤"},
            {"e": "预估特征", "s": "特征平台统一", "r": "训练服务一致、实时特征"},
            {"e": "竞价日志", "s": "流式落库", "r": "eCPM/出价/赢家留痕"},
            {"e": "计费流水", "s": "防重+对账库", "r": "准确计费、可对账"},
            {"e": "归因数据", "s": "多触点链路", "r": "转化功劳分配"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "CPC 合约", "detail": "固定定向、CPC 计费、简单排序"},
            {"stage": "成长期", "focus": "RTB 竞价", "detail": "实时竞价、CTR 预估、eCPM 排序、GSP 定价"},
            {"stage": "成熟期", "focus": "智能出价", "detail": "CVR 预估、oCPX 智能出价、反作弊、多触点归因"},
        ],
        "pitfalls": [
            "排序只看预估 CTR 不乘出价——高点击低价值广告挤占优质广告,平台收入受损",
            "用首价拍卖计费——广告主反复试探压价,市场博弈不稳、出价不真实",
            "预估只追 AUC 不做校准——eCPM 系统性偏高/偏低,竞价与计费全盘失真",
            "训练与线上服务特征口径不一致——离线效果好上线拉胯,是预估翻车的头号原因",
            "CVR 直接把未回流样本当负例——转化延迟被误标,模型低估转化、出价保守",
            "不做流量反作弊——机器刷量点击直接计费,广告费被黑产偷走且填充虚高",
            "归因口径与广告主自有统计不对齐——结算时数据对不上,引发信任与合同纠纷",
        ],
        "takeaways": [
            "eCPM 是广告系统的统一语言:出价 × 预估CTR × 预估CVR 让不同计费模式、不同质量的广告在同一把尺子下公平竞价",
            "收入天花板取决于预估准确性而非竞价机制——CTR/CVR 预估准一点,收入与体验同时抬升,校准比 AUC 更影响真实收益",
            "GSP 次价拍卖用「付第二名价格」激励广告主按真实价值出价,牺牲严格最优换工程可解释,是行业主流选择",
            "反作弊是广告的生死线:不是锦上添花而是守住计费真实性,黑产刷量等于直接偷钱,须实时+离线持续对抗",
            "特征平台统一训练与服务口径,是预估工程的地基——线上线下特征漂移是模型翻车最常见也最隐蔽的坑",
        ],
    },
    {
        "slug": "feed", "cn": "信息流与时间线", "en": "Feed & Timeline",
        "layer": "内容发现层", "color": "#0369a1",
        "tagline": "朋友圈 / 微博 / 关注流 —— 关注关系下的内容分发,核心是推拉结合的写扩散 / 读扩散权衡。",
        "groups": [
            {"g": "分发模式", "nodes": [
                {"t": "写扩散(推)", "p": "发布时写入所有粉丝的收件箱,读时直接取,读快写重",
                 "d": "发布一条内容即遍历粉丝列表,把该条 ID 推进每个粉丝的 Timeline(收件箱)。读极快——直接取自己的收件箱即可。代价是写放大:一个百万粉丝大 V 发一条,瞬间产生百万次写。失败模式:大 V 发布引发写风暴打垮存储,须对大 V 单独处理,不能一视同仁全推。"},
                {"t": "读扩散(拉)", "p": "发布只写自己的发件箱,读时拉取所有关注人再聚合,写轻读重",
                 "d": "发布只写自己一份(发件箱),读时现拉所有关注对象的最新内容再归并排序。写极轻,但读放大:关注 2000 人就要拉 2000 个发件箱聚合。失败模式:关注数多的用户刷新一次要聚合海量来源,读延迟高,须缓存热门发件箱+分页游标。"},
                {"t": "推拉结合", "p": "普通用户写扩散、大 V 读扩散,按粉丝量与活跃度动态选择",
                 "d": "工业界的实际答案:普通用户走推(粉丝少,写放大可控),大 V 走拉(粉丝多,避免写风暴),读时把「推来的收件箱」与「大 V 发件箱现拉」两部分归并。核心是阈值划分与活跃度感知——只给活跃粉丝推,沉默粉丝按需拉。失败模式:推拉边界拍脑袋定死,须按粉丝量/活跃度动态调整。"},
            ]},
            {"g": "时间线组织", "nodes": [
                {"t": "Timeline 存储", "p": "收件箱/发件箱用有序结构存储,支持游标翻页",
                 "d": "Timeline 本质是一个按时间/权重排序的 ID 列表,须支持高效追加与范围读。用 Redis ZSet 或专用宽表存储,翻页用游标(上次末尾时间戳/ID)而非 offset,避免深翻页性能塌陷与新内容插入导致的错位重复。失败模式:用 offset 分页,发布高峰下翻页错位、重复或漏内容。"},
                {"t": "Feed 排序", "p": "从纯时间序到兴趣加权排序,平衡时效与相关性",
                 "d": "早期 Feed 是纯时间倒序,简单但信息过载、错过重要内容。演进为加权排序——结合互动预估、亲密度、时效衰减打分重排。权衡:时间序可预期但低效,算法序高效但打破「按时间」的用户心智。失败模式:过度算法化让用户找不到刚发的内容,须保留一定时序可解释性。"},
            ]},
            {"g": "一致性与体验", "nodes": [
                {"t": "读己之所写", "p": "发布后自己立即可见,保证会话内一致",
                 "d": "Feed 是最终一致系统,但用户对「自己刚发的内容」有强一致预期——发完刷新必须看到。须做读己之所写(read-your-writes):把自己的新内容在客户端或读路径上就近合并,不依赖扩散完成。失败模式:扩散有延迟,用户发完刷新看不到自己的内容,误以为发布失败重复提交。"},
                {"t": "缓存与降级", "p": "热门 Timeline 多级缓存,降级返回时间序兜底",
                 "d": "Feed 读多写少且热点集中(活跃用户 Timeline 反复被读),须多级缓存收敛。极端流量下排序服务过载时,降级为纯时间序或返回缓存旧数据,保证可用而非全挂。失败模式:排序服务是关键路径无降级,一挂整个 Feed 不可用,须排序旁路化+时序兜底。"},
            ]},
        ],
        "insight": "Feed 系统的本质,是在写扩散与读扩散这对相反成本模型之间做全局权衡:推(写扩散)让读极快但一个大 V 发帖能瞬间产生百万次写,拉(读扩散)让写极轻但关注两千人的用户刷新一次要聚合两千个来源。没有银弹——工业界的答案永远是推拉结合:普通用户推、大 V 拉,再在读时归并两部分。最反直觉的认知是:Feed 的难点不在排序算法,而在扩散模型的选择与切换阈值,因为它直接决定了系统在「大 V 发帖」和「海量关注用户刷新」这两个极端下会不会被压垮。此外 Feed 虽是最终一致系统,却必须对「自己刚发的内容」保证读己之所写——用户对别人的内容能容忍延迟,对自己的不能。因此工程重心是三件事:按粉丝量与活跃度动态选推拉、用游标而非 offset 组织可靠翻页、以及排序服务旁路化让极端流量下能降级到时序兜底。",
        "tension": {
            "left": {"label": "写扩散(推)", "items": [
                "发布时推进所有粉丝收件箱", "读极快 · 直接取收件箱", "大 V 发帖写放大百万级", "适合粉丝少的普通用户"]},
            "right": {"label": "读扩散(拉)", "items": [
                "发布只写自己发件箱", "写极轻 · 读时聚合", "关注多则读放大严重", "适合粉丝多的大 V"]},
            "core": "推读快写重、拉写轻读重,没有银弹;工业界答案是推拉结合——普通用户推、大 V 拉,按粉丝量与活跃度动态切换。",
        },
        "funnel": [
            {"stage": "内容发布", "qps": "100%", "note": "用户发布一条内容,进入分发流程"},
            {"stage": "扩散分发", "qps": "推 ×粉丝数", "note": "普通用户写扩散推收件箱,大 V 只写发件箱"},
            {"stage": "Timeline 读取", "qps": "读放大", "note": "读时合并收件箱+大 V 发件箱现拉,游标翻页"},
            {"stage": "排序重排", "qps": "加权打分", "note": "时效衰减+互动预估+亲密度重排,时序兜底"},
            {"stage": "呈现", "qps": "读己所写", "note": "自己新内容就近合并,保证发完即见"},
        ],
        "flow": {
            "lanes": [
                {"g": "发布", "nodes": [
                    {"id": "pub", "t": "发布服务", "s": "内容落库"}]},
                {"g": "扩散", "nodes": [
                    {"id": "push", "t": "写扩散", "s": "推普通用户粉丝"},
                    {"id": "pull", "t": "读扩散", "s": "大 V 只写发件箱"}]},
                {"g": "时间线", "nodes": [
                    {"id": "inbox", "t": "收件箱 Timeline", "s": "ZSet 游标翻页"},
                    {"id": "merge", "t": "读时归并", "s": "收件箱+大V发件箱"}]},
                {"g": "排序", "nodes": [
                    {"id": "rank", "t": "Feed 排序", "s": "加权重排/时序兜底"}]},
                {"g": "呈现", "nodes": [
                    {"id": "view", "t": "客户端呈现", "s": "读己之所写"}]},
            ],
            "edges": [
                {"f": "pub", "t": "push", "l": "普通用户"},
                {"f": "pub", "t": "pull", "l": "大 V"},
                {"f": "push", "t": "inbox", "l": "写收件箱"},
                {"f": "inbox", "t": "merge", "l": "读收件箱"},
                {"f": "pull", "t": "merge", "l": "现拉大V"},
                {"f": "merge", "t": "rank", "l": "重排"},
                {"f": "rank", "t": "view", "l": "下发"},
            ],
        },
        "req": {
            "func": [
                "发布分发:内容落库并按推拉策略扩散到粉丝时间线",
                "推拉选择:按粉丝量/活跃度动态选写扩散或读扩散",
                "时间线读取:收件箱与大 V 发件箱归并,游标分页",
                "Feed 排序:时间序/兴趣加权重排,可降级时序兜底",
                "一致性:读己之所写,自己新内容发布即可见",
            ],
            "quality": [
                {"k": "Feed 拉取延迟", "v": "P99 < 200ms", "n": "刷新首屏慢直接掉活跃度,热门 Timeline 须缓存命中"},
                {"k": "写扩散吞吐", "v": "峰值抗大 V", "n": "大 V 发帖写放大百万级,须异步扩散+削峰不阻塞发布"},
                {"k": "读己之所写", "v": "强一致", "n": "用户发完刷新必须看到自己内容,否则误判失败重复发"},
                {"k": "最终一致时延", "v": "秒级收敛", "n": "他人内容可容忍秒级延迟到达,但不能长期缺失"},
                {"k": "排序可降级", "v": "时序兜底", "n": "排序服务过载时降级纯时间序,保证 Feed 可用不全挂"},
            ],
            "cons": [
                "扩散成本相反:推读快写重、拉写轻读重,单一模式在极端场景必被压垮",
                "关系不均衡:大 V 粉丝数与普通用户差几个数量级,不能用统一策略",
                "最终一致:扩散有延迟,须专门处理读己之所写与翻页一致性",
            ],
        },
        "datamodel": [
            {"e": "关注关系", "s": "图/KV 存储", "r": "扩散目标、推拉判定"},
            {"e": "收件箱", "s": "Redis ZSet", "r": "写扩散、游标翻页"},
            {"e": "发件箱", "s": "有序列表", "r": "读扩散、大 V 现拉"},
            {"e": "内容元数据", "s": "KV+对象存储", "r": "正文/媒体、引用计数"},
            {"e": "排序特征", "s": "特征缓存", "r": "互动/亲密度/时效"},
            {"e": "热点缓存", "s": "多级缓存", "r": "热门 Timeline 收敛读"},
        ],
        "roadmap": [
            {"stage": "MVP", "focus": "读扩散", "detail": "只写发件箱、读时聚合、纯时间序"},
            {"stage": "成长期", "focus": "推拉结合", "detail": "普通用户写扩散、大 V 拉、读时归并"},
            {"stage": "成熟期", "focus": "排序+一致", "detail": "加权重排、读己之所写、缓存降级"},
        ],
        "pitfalls": [
            "所有用户一律写扩散——大 V 发一条产生百万次写,发布高峰直接打垮存储",
            "所有用户一律读扩散——关注多的用户刷新要聚合海量发件箱,读延迟高到不可用",
            "Timeline 翻页用 offset——发布高峰下新内容插入导致翻页错位、重复或漏内容",
            "忽略读己之所写——扩散延迟下用户发完看不到自己内容,误判失败重复提交",
            "排序服务放在关键路径且无降级——排序一挂整个 Feed 不可用,须旁路+时序兜底",
            "推拉阈值拍脑袋定死——不随粉丝量/活跃度调整,边界场景成本失控",
            "给沉默粉丝也全量推——大量收件箱写入从不被读,浪费存储与写放大",
        ],
        "takeaways": [
            "Feed 的核心决策是推拉之争:推读快写重、拉写轻读重,没有银弹,工业界一律推拉结合按角色分治",
            "大 V 与普通用户必须区别对待——普通用户推、大 V 拉,再在读时归并,这是抗住写风暴与读放大的关键",
            "Timeline 用游标而非 offset 翻页,才能在发布高峰下保证不重不漏,这是 Feed 一致性的工程细节命门",
            "Feed 是最终一致系统,但读己之所写是不可让步的底线——用户对自己内容有强一致预期",
            "排序服务要旁路化、可降级到纯时间序,让极端流量下 Feed 退化但不崩溃,可用性优先于最优排序",
        ],
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
    svg_inline = svg_inline.replace('stroke="#8a8f98" class="ag-line"', 'class="ag-line"')
    # 层容器 band(浅灰底)
    svg_inline = svg_inline.replace('fill="#f4f4f7" stroke="#dcdce2" class="ag-band"', 'class="ag-band"')
    # 上层四分类语义色分区 band(sf-band-pay/disc/social/growth):去 SVG 里的 fill=url(#xxxBand)+stroke，
    # 保留 sf-band-* class 由 index.html CSS 接管——亮色浅语义色、暗色各自深语义色(保分区色差,勿收敛成单色)。
    svg_inline = re.sub(
        r'fill="url\(#sf\w+Band\)" stroke="#[0-9a-fA-F]{6}" (class="sf-band-\w+")',
        r'\1', svg_inline)
    # 分类彩色标题(sf-cat-*):保留彩色 fill 作为四分类语义主色,不动。
    # 旧结构白卡场景卡(stroke-width 1.6):去白 fill 挂 ag-card,保留彩色描边。
    for _sk in ("#0071e3", "#7c3aed", "#34c759", "#ff9f0a"):
        svg_inline = svg_inline.replace(
            'fill="#ffffff" stroke="%s" stroke-width="1.6" class="sc-scene"' % _sk,
            'stroke="%s" stroke-width="1.6" class="ag-card sc-scene"' % _sk)
    # 新结构分类浅底场景卡(stroke-width 1.4 + sc-<cat>):去浅底 fill,保留 sc-scene sc-<cat> class
    # 由 CSS 接管(亮色浅语义色/暗色深语义色),彩色描边保留。
    svg_inline = re.sub(
        r'fill="#[0-9a-fA-F]{6}" (stroke="#[0-9a-fA-F]{6}" stroke-width="1\.4" class="sc-scene sc-\w+")',
        r'\1', svg_inline)
    # 底层基础设施白卡
    svg_inline = svg_inline.replace(
        'fill="#ffffff" stroke="#e4e4ec" class="ag-card"', 'class="ag-card"')
    # 浅底 tint 小卡(4 种浅色,同 _tint_fills 语义)
    for _tk in ("#f8fafc", "#f1f5f9", "#fcf4ff", "#fffcf0"):
        svg_inline = svg_inline.replace(
            'fill="%s" class="ag-tint"' % _tk, 'class="ag-tint"')
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
    # 颜色与分区背景不契合)。四分类语义主色:支付蓝/发现紫/社交绿/增长橙。
    _SCEN_ACCENT = {
        "ecommerce": "#0071e3", "seckill": "#0071e3", "payment": "#0071e3",
        "search": "#7c3aed", "recommend": "#7c3aed", "feed": "#7c3aed",
        "im": "#34c759", "live": "#34c759",
        "ad": "#ff9f0a", "risk": "#ff9f0a",
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
    arch = _scenario_master_svg(sc)
    flow_svg = _scenario_flow_svg(sc) if sc.get("flow") else ""
    funnel_svg = _scenario_funnel_svg(sc) if sc.get("funnel") else ""

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

    # ── 容量漏斗:funnel SVG ──
    funnel_html = ""
    if funnel_svg:
        funnel_html = ('<div class="sc-sec"><h2>容量漏斗</h2>'
                       '<div class="arch-canvas">%s</div></div>') % funnel_svg

    # ── 数据流拓扑:flow SVG ──
    flow_html = ""
    if flow_svg:
        flow_html = ('<div class="sc-sec"><h2>核心数据流</h2>'
                     '<div class="arch-canvas">%s</div></div>') % flow_svg

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

    body_html = (grp_html + insight_html + tn_html + funnel_html + flow_html
                 + req_html + dm_html + rm_html + pit_html + tk_html)
    css = """
:root{--c-bg:#f5f6f8;--c-panel:#ffffff;--c-line:#e2e5ea;--c-ink:#1b1c20;--c-sub:#5c5f68;--c-soft:#eef0f4}
:root[data-theme=dark]{--c-bg:#0f1013;--c-panel:#1a1c22;--c-line:#31343d;--c-ink:#e8e8ea;--c-sub:#9a9aa2;--c-soft:#20222a}
*{box-sizing:border-box}
body{margin:0;background:var(--c-bg);color:var(--c-ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;transition:background .25s,color .25s}
.wrap{max-width:1120px;margin:0 auto;padding:28px 24px 64px}
header.top{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:14px;
  padding:12px 24px;background:color-mix(in srgb,var(--c-bg) 86%,transparent);
  backdrop-filter:saturate(1.4) blur(14px);-webkit-backdrop-filter:saturate(1.4) blur(14px);
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
        "function ap(t){if(t===\"dark\")r.setAttribute(\"data-theme\",\"dark\");"
        "else r.removeAttribute(\"data-theme\");}"
        "var s=\"light\";try{s=localStorage.getItem(KEY)||\"light\";}catch(e){}ap(s);"
        "var tt=document.getElementById(\"tt\");"
        "if(tt)tt.onclick=function(){var n=r.getAttribute(\"data-theme\")===\"dark\"?\"light\":\"dark\";"
        "ap(n);try{localStorage.setItem(KEY,n);}catch(e){}};})();")
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>{cn} · 核心技术点</title><style>{css}</style></head>'
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
        '<div class="hero"><div class="lay">{layer}</div><h1>{cn}</h1>'
        '<div class="en">{en}</div><div class="tag">{tag}</div></div>'
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
        ("topic", "主题视角", "topic 主题视角 主题 视角 跨项目专题"),
        ("principles", "系统视角", "principles 系统视角 系统设计 分片 缓存 限流 消息队列"),
        ("basic", "基础原理", "basic 基础原理 数据结构 算法 基本功"),
        ("scenario", "业务场景", "scenario 业务场景 分布式落地 高频场景"),
        ("agent", "LLM & Agent", "agent llm & agent llm agent 大模型 智能体 aigc mcp rag"),
        ("standards", "标准视角", "standards 标准视角 标准 协议 规范"),
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
<title>技术图谱 · 计算机体系架构导航</title>
<style>
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
.topbar{display:flex;align-items:center;gap:16px;padding:13px 30px 11px}
.logo{flex:none;width:34px;height:34px;display:flex;align-items:center;justify-content:center}
.logo svg{display:block}
.nn-n{fill:var(--c-ink2)}
.nn-h{fill:var(--c-brand)}
.nn-e{stroke:var(--c-line2,var(--c-line));stroke-width:1.4}
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
.lensbar{display:flex;flex-direction:column;align-items:center;gap:10px;padding:0 30px 11px}
.mode-switch{display:inline-flex;align-items:center;gap:2px;padding:4px 8px;border-radius:11px;background:var(--c-bg2);border:1px solid var(--c-line);max-width:100%;overflow-x:auto;scrollbar-width:none}
.mode-switch::-webkit-scrollbar{display:none}
.mode-clab{font:700 9px var(--mono);color:var(--c-ink3);letter-spacing:.1em;text-transform:uppercase;padding:0 8px 0 4px;white-space:nowrap;opacity:.75}
.mode-div{width:1px;align-self:stretch;margin:4px 8px;background:var(--c-line2)}
.mode-seg{border:0;background:transparent;color:var(--c-ink3);cursor:pointer;font:700 12.5px var(--sans);padding:6px 18px;border-radius:8px;white-space:nowrap;transition:.15s}
.mode-seg:hover{color:var(--c-ink)}
.mode-seg.on{background:var(--accent,var(--c-brand));color:#fff;box-shadow:0 1px 4px color-mix(in srgb,var(--c-brand) 38%,transparent)}
.mode-seg.hit{color:var(--accent,var(--c-brand));box-shadow:0 0 0 2px color-mix(in srgb,var(--accent,var(--c-brand)) 45%,transparent) inset}
.mode-seg.dim{opacity:.4}
.mode-seg.flash{animation:hotflash 1.05s ease-out 2}
.switch-region{display:none}
.switch-region.on{display:flex;justify-content:center}
.lens-switch{display:inline-flex;gap:0;padding:5px 6px;border-radius:12px;background:var(--c-panel);border:1px solid var(--c-line);max-width:100%;overflow-x:auto;scrollbar-width:none}
.lens-switch::-webkit-scrollbar{display:none}
.topic-switch{display:inline-flex;gap:2px;padding:5px 6px;border-radius:12px;background:var(--c-panel);border:1px solid var(--c-line);max-width:100%;overflow-x:auto;scrollbar-width:none}
.topic-switch::-webkit-scrollbar{display:none}
.topic-seg{border:0;background:transparent;color:var(--c-ink2);cursor:pointer;font:600 12px var(--sans);padding:5px 13px;border-radius:8px;white-space:nowrap;transition:.15s}
.topic-seg:hover{color:var(--c-ink)}
.topic-seg.on{background:var(--c-brand);color:#fff}
.lens-grp{display:inline-flex;flex-direction:column;gap:5px;padding:0 12px}
.lens-grp+.lens-grp{border-left:1px solid var(--c-line)}
.lens-grp-lab{font:600 9.5px var(--sans);color:var(--c-ink3);letter-spacing:.08em;white-space:nowrap;text-align:center;text-transform:uppercase}
.lens-grp-segs{display:flex;gap:2px;justify-content:center}
.lens-seg{border:0;background:transparent;color:var(--c-ink2);cursor:pointer;font:600 12px var(--sans);padding:5px 12px;border-radius:8px;white-space:nowrap;transition:.15s}
.lens-seg:hover{color:var(--c-ink)}
.lens-seg.on{background:var(--c-brand);color:#fff}
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
.arch-svg .ag-band{fill:#f4f4f7;stroke:#e2e2e8 !important;stroke-width:1.2}
.arch-svg .ag-tint{fill:#f0f0f4;stroke:#d6d6de !important;stroke-width:1.1}
.arch-svg .ag-sub{fill:#8a8a8e}
.arch-svg .ag-title{fill:#1d1d1f}
.arch-svg .ag-line{stroke:#c2c4cc}
/* 业务场景四分类语义色分区 band + 场景卡浅底:亮色浅语义色,暗色各自深语义色(保分区色差) */
.arch-svg .sf-band-pay{fill:#eef5ff;stroke:#d7e4fb !important}
.arch-svg .sf-band-disc{fill:#f5f0ff;stroke:#e2d6f7 !important}
.arch-svg .sf-band-social{fill:#eafaf3;stroke:#c9ecd7 !important}
.arch-svg .sf-band-growth{fill:#fff4ec;stroke:#f7dcc0 !important}
.arch-svg .sc-pay{fill:#f4f8ff}
.arch-svg .sc-disc{fill:#faf6ff}
.arch-svg .sc-social{fill:#f1faf4}
.arch-svg .sc-growth{fill:#fff7ef}
:root[data-theme="dark"] .arch-svg .ag-bg{fill:#15161a}
:root[data-theme="dark"] .arch-svg .ag-card{fill:#22242b;stroke:#4a4d57 !important}
:root[data-theme="dark"] .arch-svg .ag-band{fill:#1b1d23;stroke:#33353d !important}
:root[data-theme="dark"] .arch-svg .ag-tint{fill:#2a2d36;stroke:#454955 !important}
:root[data-theme="dark"] .arch-svg .ag-sub{fill:#9ca0a8}
:root[data-theme="dark"] .arch-svg .ag-title{fill:#f2f3f5}
:root[data-theme="dark"] .arch-svg .ag-line{stroke:#565963}
:root[data-theme="dark"] .arch-svg .sf-band-pay{fill:#16253d;stroke:#2b3f5c !important}
:root[data-theme="dark"] .arch-svg .sf-band-disc{fill:#241d3a;stroke:#3b3357 !important}
:root[data-theme="dark"] .arch-svg .sf-band-social{fill:#0f3330;stroke:#1e4a45 !important}
:root[data-theme="dark"] .arch-svg .sf-band-growth{fill:#382214;stroke:#573c26 !important}
:root[data-theme="dark"] .arch-svg .sc-pay{fill:#1c2e49}
:root[data-theme="dark"] .arch-svg .sc-disc{fill:#2c2447}
:root[data-theme="dark"] .arch-svg .sc-social{fill:#164039}
:root[data-theme="dark"] .arch-svg .sc-growth{fill:#452b18}
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
    <svg viewBox="0 0 40 40" width="34" height="34" fill="none">
      <line x1="9" y1="12" x2="20" y2="8" class="nn-e"/><line x1="9" y1="12" x2="20" y2="20" class="nn-e"/>
      <line x1="9" y1="28" x2="20" y2="20" class="nn-e"/><line x1="9" y1="28" x2="20" y2="32" class="nn-e"/>
      <line x1="20" y1="8" x2="31" y2="14" class="nn-e"/><line x1="20" y1="20" x2="31" y2="14" class="nn-e"/>
      <line x1="20" y1="20" x2="31" y2="26" class="nn-e"/><line x1="20" y1="32" x2="31" y2="26" class="nn-e"/>
      <circle cx="9" cy="12" r="3" class="nn-n"/><circle cx="9" cy="28" r="3" class="nn-n"/>
      <circle cx="20" cy="8" r="3" class="nn-n nn-h"/><circle cx="20" cy="20" r="3" class="nn-n nn-h"/><circle cx="20" cy="32" r="3" class="nn-n nn-h"/>
      <circle cx="31" cy="14" r="3" class="nn-n"/><circle cx="31" cy="26" r="3" class="nn-n"/>
    </svg>
  </span>
  <span class="brand">技术图谱</span>
  <label class="search">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="text" placeholder="搜索项目 / 关键词…" autocomplete="off" aria-label="搜索项目"/>
    <kbd>/</kbd>
  </label>
  <button class="tt" id="tt" aria-label="切换深浅主题" title="切换深浅主题">
    <span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span>
  </button>
</header>
<nav class="lensbar" aria-label="一级导航">
  <div class="mode-switch" role="tablist" aria-label="导航模式">
    <span class="mode-clab">技术剖面</span>
    <button class="mode-seg on" data-mode="project" role="tab" id="m_mode_project">项目视角</button>
    <button class="mode-seg" data-mode="topic" role="tab" id="m_mode_topic">主题视角</button>
    <button class="mode-seg" data-mode="principles" role="tab" id="m_mode_principles">系统视角</button>
    <button class="mode-seg" data-mode="basic" role="tab" id="m_mode_basic">基础原理</button>
    <button class="mode-seg" data-mode="scenario" role="tab" id="m_mode_scenario">业务场景</button>
    <button class="mode-seg" data-mode="agent" role="tab" id="m_mode_agent">LLM &amp; Agent</button>
    <span class="mode-div" aria-hidden="true"></span>
    <span class="mode-clab">项目背景</span>
    <button class="mode-seg" data-mode="standards" role="tab" id="m_mode_standards">标准视角</button>
    <button class="mode-seg" data-mode="industry" role="tab" id="m_mode_industry">产业视角</button>
    <button class="mode-seg" data-mode="people" role="tab" id="m_mode_people">学派视角</button>
  </div>
  <div class="switch-region mode-switchbar on" data-mode="project">__LENSSWITCH__</div>
</nav>
</div>

<main class="stage">
  <div class="mode-view on" data-mode="project"><div class="diagram">__SVG__</div></div>
  <div class="mode-view" data-mode="topic">__TOPICS__</div>
  <div class="mode-view" data-mode="basic">__BASIC__</div>
  <div class="mode-view" data-mode="principles">__PRINCIPLES__</div>
  <div class="mode-view" data-mode="agent">__AGENT__</div>
  <div class="mode-view" data-mode="scenario">__SCENARIO__</div>
  <div class="mode-view" data-mode="standards">__STANDARDS__</div>
  <div class="mode-view" data-mode="industry">__INDUSTRY__</div>
  <div class="mode-view" data-mode="people">__PEOPLE__</div>
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
  // 一级模式切换:项目视角 / 主题视角 —— 两套并行,切模式显隐对应切换区 + 内容区
  (function(){
    var ms=[].slice.call(document.querySelectorAll(".mode-seg"));
    var regions=[].slice.call(document.querySelectorAll(".mode-switchbar"));
    var views=[].slice.call(document.querySelectorAll(".mode-view"));
    function mode(m){
      ms.forEach(function(b){ b.classList.toggle("on", b.dataset.mode===m); });
      regions.forEach(function(r){ r.classList.toggle("on", r.dataset.mode===m); });
      views.forEach(function(v){ v.classList.toggle("on", v.dataset.mode===m); });
    }
    ms.forEach(function(b){ b.onclick=function(){ mode(b.dataset.mode); }; });
    // 深链接:子站「返回」带 #<mode> 进来时,直接激活对应一级模式(而非默认项目视角)
    var initMode=(location.hash||"").replace("#","");
    if(initMode && ms.some(function(b){ return b.dataset.mode===initMode; })) mode(initMode);
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
