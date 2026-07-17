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
LAYERS = [
    ("app",      "接口 / 应用框架层",   "用户接触面:Web 框架 · ORM · 语言",      "#7c5fe6"),
    ("compute",  "计算 / 查询引擎层",   "SQL 存算 · 联邦查询 · 分布式计算 · 流",   "#a78bfa"),
    ("ai",       "AI / ML 层",          "训练 · 推理 · 向量检索",                 "#f472b6"),
    ("lakehouse","数据湖 / 表格式层",   "表格式 · 列存文件 · 湖仓",               "#38bdf8"),
    ("storage",  "存储引擎层",          "KV / LSM · 关系 · 图 · 内存",            "#f59e0b"),
    ("mq",       "消息 / 流层",         "消息队列 · 事件流",                     "#fbbf24"),
    ("coord",    "分布式协调 / 共识层", "元数据 · 共识 · 服务发现",               "#0a84ff"),
    ("orch",     "编排 / 服务网格层",   "容器编排 · 反向代理 · 网关",             "#2dd4a7"),
    ("net",      "网络 / 传输层",       "协议栈 · QUIC · 多媒体",                 "#4ade80"),
    ("os",       "操作系统内核层",      "进程 · 内存 · 文件 · 调度",              "#8e8e93"),
    ("runtime",  "语言 / 运行时层",     "语言运行时 · GC · 并发",                 "#00add8"),
    ("misc",     "其他 / 待归类",       "尚未归入体系层的项目",                   "#6b7280"),
]
LAYER_ORDER = [k for k, *_ in LAYERS]

# ── 项目 → 体系层 映射(新增项目补一条即在图上落位) ──
LAYER_MAP = {
    # 接口 / 应用框架
    "react": "app", "gin": "app", "gorm": "app", "spring-boot": "app",
    # 计算 / 查询引擎
    "doris": "compute", "clickhouse": "compute", "starrocks": "compute",
    "trino": "compute", "spark": "compute", "flink": "compute", "duckdb": "compute",
    # AI / ML
    "pytorch": "ai", "tensorflow": "ai", "ray": "ai", "vllm": "ai", "milvus": "ai",
    # 数据湖 / 表格式
    "iceberg": "lakehouse", "hudi": "lakehouse", "orc": "lakehouse", "fluss": "lakehouse",
    # 存储引擎
    "rocksdb": "storage", "redis": "storage", "postgres": "storage", "neo4j": "storage",
    "hadoop": "storage",
    # 消息 / 流
    "kafka": "mq",
    # 分布式协调 / 共识
    "etcd": "coord", "zookeeper": "coord", "raft": "coord",
    # 编排 / 服务网格
    "kubernetes": "orch", "nginx": "orch", "traefik": "orch",
    # 网络 / 传输
    "quic-go": "net", "quiche": "net", "ffmpeg": "net",
    # 操作系统内核
    "linux": "os",
    # 语言 / 运行时
    "go": "runtime", "rust": "runtime",
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
    "raft": {"name": "Raft", "init": "RF", "desc": "共识算法",
             "lc": "linear-gradient(135deg,#0a84ff,#5b8cff)"},
    "kafka": {"name": "Apache Kafka", "init": "KF", "desc": "分布式事件流平台",
              "lc": "linear-gradient(135deg,#8e8e93,#4a4a4f)"},
    "kubernetes": {"name": "Kubernetes", "init": "K8", "desc": "容器编排系统",
                   "lc": "linear-gradient(135deg,#326ce5,#5b8cff)"},
    "nginx": {"name": "Nginx", "init": "NG", "desc": "Web 服务器 / 反向代理",
              "lc": "linear-gradient(135deg,#2f8f5e,#4ade80)"},
    "traefik": {"name": "Traefik", "init": "TK", "desc": "云原生反向代理 / 网关",
                "lc": "linear-gradient(135deg,#2dd4a7,#38bdf8)"},
    "linux": {"name": "Linux Kernel", "init": "LX", "desc": "操作系统内核",
              "lc": "linear-gradient(135deg,#5a5a64,#7a8494)"},
    "go": {"name": "Go 语言", "init": "GO", "desc": "语言核心原理 · 编译期 + 运行期",
           "lc": "linear-gradient(135deg,#00add8,#5dc9e2)"},
    "rust": {"name": "Rust", "init": "RS", "desc": "系统级语言 · 所有权",
             "lc": "linear-gradient(135deg,#dea584,#b7410e)"},
    "react": {"name": "React", "init": "RC", "desc": "前端 UI 框架",
              "lc": "linear-gradient(135deg,#38bdf8,#61dafb)"},
    "gin": {"name": "Gin", "init": "GI", "desc": "Go Web 框架",
            "lc": "linear-gradient(135deg,#00add8,#5dc9e2)"},
    "gorm": {"name": "GORM", "init": "GM", "desc": "Go ORM",
             "lc": "linear-gradient(135deg,#e25a1c,#f6832b)"},
    "spring-boot": {"name": "Spring Boot", "init": "SB", "desc": "Java 应用框架",
                    "lc": "linear-gradient(135deg,#6db33f,#8bc34a)"},
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
    "fluss": {"name": "Fluss", "init": "FS", "desc": "流式存储",
              "lc": "linear-gradient(135deg,#38bdf8,#4dd0e1)"},
    "quic-go": {"name": "quic-go", "init": "QG", "desc": "Go QUIC 实现",
                "lc": "linear-gradient(135deg,#4ade80,#2dd4a7)"},
    "quiche": {"name": "quiche", "init": "QC", "desc": "Rust QUIC/HTTP3 实现",
               "lc": "linear-gradient(135deg,#4ade80,#38bdf8)"},
    "ffmpeg": {"name": "FFmpeg", "init": "FF", "desc": "多媒体编解码",
               "lc": "linear-gradient(135deg,#4ade80,#5dc9e2)"},
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
    for entry in sorted(os.listdir(ROOT)):
        full = os.path.join(ROOT, entry)
        if not os.path.isdir(full) or not entry.endswith(SUFFIX):
            continue
        key = entry[: -len(SUFFIX)].strip()
        # 归一化查表键:去空格 + 小写,兼容 "FFmpeg" / " spring-boot" 等目录名瑕疵
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
    """项目 key → SVG 元素 id;Python 与 JS 必须一致(此处规则简单可在 JS 复刻)。"""
    return "m_" + re.sub(r"[^a-zA-Z0-9]+", "_", key.lower())


def _esc(s):
    return html.escape(str(s), quote=True)


# 层元数据快查(build_svg 用)
LAYER_TITLE = {k: t for k, t, s, c in LAYERS}
LAYER_SUB = {k: s for k, t, s, c in LAYERS}
LAYER_COLOR = {k: c for k, t, s, c in LAYERS}

# ── 架构图几何(px)—— 计算机系统架构的真实 2D 拓扑,而非平铺色带 ──
_CW = 1200            # 画布宽
_PAD = 28
_COLGAP = 18          # 区域内子列间距
_RAILW = 158          # 横切侧栏宽
_RAILGAP = 20         # 侧栏 ↔ 中央区间距
_MW, _MH = 176, 62    # 标准模块(全宽区 / 中央区)
_CMW, _CMH = 130, 50  # 紧凑模块(侧栏)
_MG, _RG = 13, 12     # 模块列间距 / 行间距
_ARROW = 42           # 层间箭头区高
_REGHEAD = 52         # 区域标题带高
_SUBHEAD = 32         # 子列标题高
_REGPAD = 18          # 区域内边距

# 每渲染一次填充:layer key → 该层项目列表
LAYER_ITEMS = {}


def _module_svg(p, x, y, w, accent, compact=False):
    """单个项目模块:可点(<a>)或规划占位(<g>)。图标优先,回退语义色首字母 tile。"""
    h = _CMH if compact else _MH
    nav = p["status"] != "plan"
    gid = _gid(p["key"])
    dot = {"ready": "var(--ok)", "assets": "var(--warn)"}.get(p["status"], "var(--c-ink3)")
    cls = "mod" if nav else "mod mod-plan"
    if nav:
        head = ('<a href="{h}" class="{c}" id="{i}" tabindex="0" aria-label="{n}:{d}">'
                .format(h=_esc(p["href"]), c=cls, i=gid, n=_esc(p["name"]), d=_esc(p["desc"])))
        tail = "</a>"
    else:
        head = '<g class="{c}" id="{i}" aria-label="{n}(规划中)">'.format(
            c=cls, i=gid, n=_esc(p["name"]))
        tail = "</g>"
    out = [head]
    out.append('<rect class="mod-rect" x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
               'style="--accent:{a}"/>'.format(x=x, y=y, w=w, h=h, a=accent))
    isz = 30 if compact else 32
    ix, iy = x + 11, y + (h - isz) / 2
    if p.get("icon"):
        out.append('<image x="{ix}" y="{iy:.1f}" width="{s}" height="{s}" href="{u}" '
                   'preserveAspectRatio="xMidYMid meet"/>'.format(ix=ix, iy=iy, s=isz, u=_esc(p["icon"])))
    else:
        out.append('<rect class="tile" x="{ix}" y="{iy:.1f}" width="{s}" height="{s}" rx="8" '
                   'style="--accent:{a}"/>'.format(ix=ix, iy=iy, s=isz, a=accent))
        out.append('<text class="tile-t" x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle">{t}</text>'
                   .format(tx=ix + isz / 2, ty=iy + isz / 2 + 4, t=_esc(p["init"])))
    tx = x + isz + 20
    maxname = 11 if compact else 15
    name = p["name"] if len(p["name"]) <= maxname else p["name"][:maxname - 1] + "…"
    if compact:
        out.append('<text class="mod-name" x="{tx}" y="{ty:.1f}">{n}</text>'.format(
            tx=tx, ty=y + h / 2 + 4, n=_esc(name)))
    else:
        out.append('<text class="mod-name" x="{tx}" y="{ty}">{n}</text>'.format(
            tx=tx, ty=y + 25, n=_esc(name)))
        meta = ("{s} 图 · {m} 篇".format(s=p["svg"], m=p["md"]) if nav and (p["svg"] or p["md"])
                else ("待编译" if nav else "规划中"))
        out.append('<text class="mod-meta" x="{tx}" y="{ty}">{m}</text>'.format(
            tx=tx, ty=y + 43, m=_esc(meta)))
    out.append('<circle class="mod-dot" cx="{cx}" cy="{cy}" r="3.5" style="fill:{d}"/>'.format(
        cx=x + w - 13, cy=y + 12, d=dot))
    out.append(tail)
    return "".join(out)


def _place_grid(items, x, y, colw, accent, compact=False):
    """把项目在 colw 宽的列里网格排布,水平居中;返回 (svg, 占用高度)。"""
    mw = _CMW if compact else _MW
    mh = _CMH if compact else _MH
    per_row = max(1, int((colw + _MG) // (mw + _MG)))
    used_w = per_row * mw + (per_row - 1) * _MG
    offx = x + max(0, (colw - used_w) / 2)
    out = []
    for i, p in enumerate(items):
        r, c = divmod(i, per_row)
        out.append(_module_svg(p, offx + c * (mw + _MG), y + r * (mh + _RG), mw, accent, compact))
    rows = (len(items) + per_row - 1) // per_row
    return "".join(out), rows * mh + max(0, rows - 1) * _RG


def _subcol(layer_key, x, y, colw, show_head=True):
    """区域内的一个子列 = 一个体系层:可选标题 + 项目网格。返回 (svg, 高度)。
    show_head=False 时(区域仅含此一层),省略子列标题以免与区域标题重复。"""
    items = LAYER_ITEMS.get(layer_key, [])
    accent = LAYER_COLOR[layer_key]
    out = []
    top = y
    if show_head:
        out.append('<text class="sub-title" x="{x}" y="{y}">{t}</text>'.format(
            x=x, y=y + 13, t=_esc(LAYER_TITLE[layer_key])))
        out.append('<text class="sub-sub" x="{x}" y="{y}">{s} · {n}</text>'.format(
            x=x, y=y + 28, s=_esc(LAYER_SUB[layer_key]), n=str(len(items)) + " 项"))
        top = y + _SUBHEAD
    g, gh = _place_grid(items, x, top, colw, accent)
    out.append(g)
    return "".join(out), (top - y) + gh


def _region(title, sub, layer_keys, x, y, w, accent):
    """一个宏区域(白卡容器)内并列若干体系层子列。返回 (svg, 区域高度)。
    单层区域:省略子列标题(区域标题已表达),模块直接紧贴区域标题下。"""
    inner_x = x + _REGPAD
    ncol = max(1, len(layer_keys))
    single = ncol == 1
    colw = (w - 2 * _REGPAD - (ncol - 1) * _COLGAP) / ncol
    cy = y + _REGHEAD
    cols = []
    maxh = 0
    for i, lk in enumerate(layer_keys):
        cxp = inner_x + i * (colw + _COLGAP)
        g, h = _subcol(lk, cxp, cy, colw, show_head=not single)
        cols.append((cxp, g))
        maxh = max(maxh, h)
    region_h = _REGHEAD + maxh + _REGPAD
    parts = ['<rect class="region" x="{x}" y="{y}" width="{w}" height="{h}" rx="18" '
             'style="--accent:{a}"/>'.format(x=x, y=y, w=w, h=region_h, a=accent),
             '<rect class="region-bar" x="{x}" y="{y}" width="5" height="{h}" rx="2.5" '
             'style="fill:{a}"/>'.format(x=x, y=y + 16, h=region_h - 32, a=accent),
             '<text class="region-title" x="{tx}" y="{ty}">{t}</text>'.format(
                 tx=x + _REGPAD + 6, ty=y + 27, t=_esc(title)),
             '<text class="region-sub" x="{tx}" y="{ty}">{s}</text>'.format(
                 tx=x + _REGPAD + 6, ty=y + 44, s=_esc(sub))]
    for i, (cxp, g) in enumerate(cols):
        if i > 0:
            parts.append('<line class="col-div" x1="{vx:.1f}" y1="{y1}" x2="{vx:.1f}" y2="{y2}"/>'.format(
                vx=cxp - _COLGAP / 2, y1=cy - 8, y2=y + region_h - _REGPAD))
        parts.append(g)
    return "".join(parts), region_h


def _rail(layer_key, x, y, w, h):
    """横切侧栏(如 Doris 的保障域 / 后台任务):跨中央区高度,项目自顶紧凑堆叠、垂直居中。"""
    items = LAYER_ITEMS.get(layer_key, [])
    accent = LAYER_COLOR[layer_key]
    out = ['<rect class="rail" x="{x}" y="{y}" width="{w}" height="{h}" rx="16" '
           'style="--accent:{a}"/>'.format(x=x, y=y, w=w, h=h, a=accent),
           '<rect class="rail-bar" x="{x}" y="{y}" width="5" height="{bh}" rx="2.5" '
           'style="fill:{a}"/>'.format(x=x, y=y + 16, bh=h - 32, a=accent),
           '<text class="rail-title" x="{tx}" y="{ty}">{t}</text>'.format(
               tx=x + 16, ty=y + 27, t=_esc(LAYER_TITLE[layer_key])),
           '<text class="rail-sub" x="{tx}" y="{ty}">{s} · {n} 项</text>'.format(
               tx=x + 16, ty=y + 44, s=_esc(LAYER_SUB[layer_key]), n=len(items))]
    n = len(items)
    if n:
        gap = 12
        block = n * _CMH + (n - 1) * gap
        top = y + 58
        avail = (y + h - 16) - top
        start = top + max(0, (avail - block) / 2)   # 紧凑堆叠 + 垂直居中
        for i, p in enumerate(items):
            out.append(_module_svg(p, x + 12, start + i * (_CMH + gap), w - 24, accent, compact=True))
    return "".join(out)


def _flow(cx, y, label):
    return ('<line class="flow" x1="{cx}" y1="{y1}" x2="{cx}" y2="{y2}" marker-end="url(#ar)"/>'
            '<text class="flow-label" x="{lx}" y="{ly:.0f}">{t}</text>').format(
        cx=cx, y1=y + 6, y2=y + _ARROW - 9, lx=cx + 14, ly=y + _ARROW / 2 + 3, t=_esc(label))


def build_svg(projects):
    """程序化生成一张 Apple 工业风"计算机系统架构图":app 接入 → 计算/数据中央区
    (两侧为协调/编排横切栏)→ 系统基础设施,层间有向标注箭头。项目自动落位其体系层。"""
    global LAYER_ITEMS
    LAYER_ITEMS = {k: [p for p in projects if p["layer"] == k] for k, *_ in LAYERS}
    innerw = _CW - 2 * _PAD
    body = []
    y = _PAD

    # 1) 接入层(全宽)
    if LAYER_ITEMS["app"]:
        g, h = _region("接口 / 应用接入", "用户与服务的接触面 · Web 框架 · ORM · 语言",
                       ["app"], _PAD, y, innerw, LAYER_COLOR["app"])
        body.append(g); y += h
        body.append(_flow(_CW // 2, y, "请求 / 调用")); y += _ARROW

    # 2) 中央区(计算 / 数据)+ 两侧横切栏(协调 / 编排)
    cx = _PAD + _RAILW + _RAILGAP
    cw = _CW - 2 * _PAD - 2 * (_RAILW + _RAILGAP)
    center_top = y
    center_parts = []
    cy = y
    comp_layers = [k for k in ("compute", "ai") if LAYER_ITEMS[k]]
    if comp_layers:
        g, h = _region("计算与智能", "查询引擎 · 训练推理 · 流处理", comp_layers,
                       cx, cy, cw, LAYER_COLOR["compute"])
        center_parts.append(g); cy += h + 20
    data_layers = [k for k in ("storage", "lakehouse", "mq") if LAYER_ITEMS[k]]
    if data_layers:
        g, h = _region("数据与存储", "存储引擎 · 表格式 · 消息流", data_layers,
                       cx, cy, cw, LAYER_COLOR["storage"])
        center_parts.append(g); cy += h
    center_h = cy - center_top
    if center_h > 0:
        if LAYER_ITEMS["coord"]:
            body.append(_rail("coord", _PAD, center_top, _RAILW, center_h))
        if LAYER_ITEMS["orch"]:
            body.append(_rail("orch", _CW - _PAD - _RAILW, center_top, _RAILW, center_h))
    body.extend(center_parts)
    y = center_top + center_h
    if center_h > 0:
        body.append(_flow(_CW // 2, y, "运行 / 依赖")); y += _ARROW

    # 3) 系统基础设施(全宽)
    found_layers = [k for k in ("net", "os", "runtime") if LAYER_ITEMS[k]]
    if found_layers:
        g, h = _region("系统基础设施", "网络传输 · 操作系统内核 · 语言运行时", found_layers,
                       _PAD, y, innerw, LAYER_COLOR["os"])
        body.append(g); y += h

    # 4) 其他 / 待归类(全宽,降权)
    if LAYER_ITEMS["misc"]:
        y += 14
        g, h = _region("其他 / 待归类", "尚未归入体系层的项目", ["misc"],
                       _PAD, y, innerw, LAYER_COLOR["misc"])
        body.append(g); y += h

    total_h = y + _PAD
    return ('<svg id="atlas" xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 {w} {h}" width="100%" role="img" '
            'aria-label="计算机系统架构导航图 · 点击任意项目下钻">'
            '<defs>'
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="2" stdDeviation="7" flood-color="#000" flood-opacity="0.12"/>'
            '</filter>'
            '<marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
            'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L9,5 L0,10 z" class="ar"/>'
            '</marker></defs>{body}</svg>').format(w=_CW, h=total_h, body="".join(body))


def _search_index(projects):
    idx = []
    layer_title = {k: t for k, t, *_ in LAYERS}
    for p in projects:
        hay = " ".join([p["name"], p["key"], p["desc"],
                        layer_title.get(p["layer"], ""),
                        " ".join(p.get("modules") or [])]).lower()
        idx.append({"id": _gid(p["key"]), "name": p["name"],
                    "nav": p["status"] != "plan", "hay": hay})
    return idx


def build_html(projects):
    agg = aggregate(projects)
    return (TEMPLATE
            .replace("__SVG__", build_svg(projects))
            .replace("__INDEX__", json.dumps(_search_index(projects), ensure_ascii=False))
            .replace("__AGG__", json.dumps(agg, ensure_ascii=False))
            .replace("__UPDATED__", agg["updated"] or "—"))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>核心原理图谱 · 计算机体系架构导航</title>
<style>
:root{
  --c-bg:#1c1c1e; --c-bg2:#161618; --c-panel:#242426; --c-panel2:#2c2c2e;
  --c-line:rgba(255,255,255,.12); --c-line2:rgba(255,255,255,.18);
  --c-ink:#f5f5f7; --c-ink2:#c4c4c9; --c-ink3:#8e8e93;
  --c-brand:#0a84ff; --c-brand-ink:#409cff; --c-hover:rgba(255,255,255,.07);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.5),0 24px 48px rgba(0,0,0,.45);
  --ok:#2dd4a7; --warn:#fbbf24;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  --grid-tint:rgba(10,132,255,.10); --grid-tint2:rgba(139,108,255,.09);
}
:root[data-theme="light"]{
  --c-bg:#f5f5f7; --c-bg2:#fbfbfd; --c-panel:#ffffff; --c-panel2:#f0f0f3;
  --c-line:rgba(0,0,0,.09); --c-line2:rgba(0,0,0,.14);
  --c-ink:#1d1d1f; --c-ink2:#424245; --c-ink3:#86868b;
  --c-brand:#0071e3; --c-brand-ink:#0066cc; --c-hover:rgba(0,0,0,.04);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.10),0 24px 48px rgba(0,0,0,.10);
  --ok:#2f8f5e; --warn:#b8801f;
  --grid-tint:rgba(0,113,227,.07); --grid-tint2:rgba(124,95,230,.06);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
html{background:var(--c-bg);transition:background-color .3s}
body{font-family:var(--sans);color:var(--c-ink);min-height:100vh;-webkit-font-smoothing:antialiased;
  background:var(--c-bg);transition:background-color .3s,color .3s}
/* 顶栏:极简 · 毛玻璃 · 贴顶(对标 Doris —— logo + 搜索 + 主题钮,不喧宾夺主) */
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;
  padding:14px 30px;border-bottom:1px solid var(--c-line);
  background:color-mix(in srgb,var(--c-bg) 82%,transparent);
  backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px)}
.logo{flex:none;width:34px;height:34px;border-radius:9px;position:relative;
  background:conic-gradient(from 210deg,var(--c-brand),#8b6cff,#38bdf8,var(--c-brand))}
.logo::after{content:"";position:absolute;inset:5px;border-radius:5px;background:var(--c-bg);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--c-ink) 8%,transparent)}
.brand{font-size:15px;font-weight:700;letter-spacing:-.01em;white-space:nowrap}
.brand-dim{color:var(--c-ink3);font-weight:400;font-size:12.5px;margin-left:10px}
.search{margin-left:auto;width:min(340px,42vw);display:flex;align-items:center;gap:9px;
  background:var(--c-panel);border:1px solid var(--c-line);border-radius:10px;padding:8px 13px;
  transition:border-color .18s,box-shadow .18s}
.search:focus-within{border-color:var(--c-brand);box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand) 16%,transparent)}
.search svg{color:var(--c-ink3);flex:none}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--c-ink);font-size:13.5px;outline:none;font-family:var(--sans)}
.search kbd{font-family:var(--mono);font-size:11px;color:var(--c-ink3);border:1px solid var(--c-line2);
  border-radius:6px;padding:1px 6px;background:var(--c-panel2);flex:none}
.tt{flex:none;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:grid;place-items:center;transition:all .18s}
.tt:hover{border-color:var(--c-ink3);color:var(--c-ink);background:var(--c-hover)}
.tt-ico{font-size:16px;line-height:1} .tt-sun{display:none}
:root[data-theme="light"] .tt-moon{display:none}
:root[data-theme="light"] .tt-sun{display:inline}
/* 舞台:架构图是主角,居中留白,无额外装饰框 */
.stage{max-width:1300px;margin:0 auto;padding:34px 30px 56px}
.diagram{position:relative;overflow-x:auto}
.undernote{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;
  margin-top:22px;padding-top:16px;border-top:1px solid var(--c-line);
  color:var(--c-ink3);font-size:12px;font-family:var(--mono)}
.undernote .stats{color:var(--c-ink2)}

/* ── 架构图 SVG 主题化(不反相,图标保持真品牌色)── */
#atlas{display:block;width:100%;height:auto;min-width:1040px}
/* 宏区域:白卡容器(Apple 工业风,细边 + 柔投影),内嵌语义色微 tint */
.region{fill:var(--c-panel);stroke:var(--c-line);stroke-width:1;filter:url(#soft)}
:root:not([data-theme="light"]) .region{fill:color-mix(in srgb,var(--accent) 5%,var(--c-panel))}
.region-bar{opacity:.9}
.region-title{fill:var(--c-ink);font:650 16px var(--sans);letter-spacing:-.01em}
.region-sub{fill:var(--c-ink3);font:400 11.5px var(--sans)}
.col-div{stroke:var(--c-line);stroke-width:1;stroke-dasharray:2 4;opacity:.7}
/* 子列(体系层)标题 */
.sub-title{fill:var(--c-ink2);font:600 12.5px var(--sans);text-transform:none}
.sub-sub{fill:var(--c-ink3);font:400 10px var(--mono)}
/* 横切侧栏(协调 / 编排)—— 类比 Doris 保障域 / 后台任务 */
.rail{fill:color-mix(in srgb,var(--accent) 7%,var(--c-panel));
  stroke:color-mix(in srgb,var(--accent) 22%,var(--c-line));stroke-width:1;filter:url(#soft)}
.rail-bar{opacity:.9}
.rail-title{fill:var(--c-ink);font:600 13px var(--sans)}
.rail-sub{fill:var(--c-ink3);font:400 10px var(--sans)}
/* 项目模块 */
.mod{cursor:pointer}
.mod-rect{fill:color-mix(in srgb,var(--accent) 11%,var(--c-panel));
  stroke:color-mix(in srgb,var(--accent) 34%,var(--c-line2));stroke-width:1.2;transition:stroke .16s,filter .16s}
.mod:hover .mod-rect{stroke:var(--accent);stroke-width:2;
  filter:drop-shadow(0 3px 10px color-mix(in srgb,var(--accent) 42%,transparent))}
.mod:focus{outline:none}
.mod:focus-visible .mod-rect{stroke:var(--c-brand);stroke-width:2.6}
.mod-plan{cursor:default}
.mod-plan .mod-rect{fill:var(--c-panel);stroke-dasharray:5 4;opacity:.72}
.mod-plan .mod-name,.mod-plan .mod-meta,.mod-plan .tile,.mod-plan image{opacity:.5}
.mod-name{fill:var(--c-ink);font:600 12.5px var(--sans)}
.mod-meta{fill:var(--c-ink3);font:500 10px var(--mono)}
.tile{fill:var(--accent)}
.tile-t{fill:#fff;font:700 13px var(--sans);letter-spacing:-.02em}
.flow{stroke:var(--c-ink3);stroke-width:1.6;opacity:.55}
.flow-label{fill:var(--c-ink3);font:500 10px var(--mono)}
.ar{fill:var(--c-ink3)}
/* 搜索态:命中在图上 flash 高亮,其余淡出 */
.mod.dim{opacity:.22;transition:opacity .2s}
.mod.hit .mod-rect{stroke:var(--c-brand);stroke-width:2.6}
@keyframes flash{0%,100%{filter:none}35%{filter:drop-shadow(0 0 11px var(--c-brand))}}
.mod.flash .mod-rect{animation:flash 1.05s ease-out 2;stroke:var(--c-brand);stroke-width:2.8}

footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:26px;
  color:var(--c-ink3);font-size:12px;font-family:var(--mono)}
@media(max-width:720px){.wrap{padding:28px 16px 56px}h1{font-size:26px}.diagram{padding:10px;border-radius:16px}}
</style>
</head>
<body>
<header class="topbar">
  <span class="logo" aria-hidden="true"></span>
  <span class="brand">核心原理图谱<span class="brand-dim">计算机系统架构导航</span></span>
  <label class="search">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="text" placeholder="搜索项目 / 关键词…" autocomplete="off" aria-label="搜索项目"/>
    <kbd>/</kbd>
  </label>
  <button class="tt" id="tt" aria-label="切换深浅主题" title="切换深浅主题">
    <span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span>
  </button>
</header>

<main class="stage">
  <div class="diagram">__SVG__</div>
  <div class="undernote">
    <span class="stats" id="stats"></span>
    <span class="hint" id="count"></span>
  </div>
</main>

<script>
(function(){
  var AGG=__AGG__, IDX=__INDEX__;
  var r=document.documentElement, KEY="atlas-nav-theme";
  function ap(t){ if(t==="light") r.setAttribute("data-theme","light"); else r.removeAttribute("data-theme"); }
  var s="dark"; try{ s=localStorage.getItem(KEY)||"dark"; }catch(e){} ap(s);
  var tt=document.getElementById("tt");
  if(tt) tt.onclick=function(){ var n=r.getAttribute("data-theme")==="light"?"dark":"light"; ap(n); try{localStorage.setItem(KEY,n);}catch(e){} };
  // 底部一行细描述(数值弱化,不与图争视觉)
  document.getElementById("stats").textContent=AGG.projects+" 项目 · "+AGG.accessible+" 可交互 · "+AGG.layers+" 体系层 · "+AGG.svg+" 图 · "+AGG.md+" 篇 · 更新 __UPDATED__";
  // 搜索 → 图上 flash 高亮(非过滤成列表)
  var q=document.getElementById("q"), countEl=document.getElementById("count");
  var els=IDX.map(function(it){ return {it:it, el:document.getElementById(it.id)}; }).filter(function(x){return x.el;});
  function clearState(){ els.forEach(function(x){ x.el.classList.remove("dim","hit","flash"); }); }
  function baseHint(){ countEl.textContent="/ 聚焦搜索 · ↑↓←→ 移动 · Enter 进入"; }
  function run(){
    var v=(q.value||"").trim().toLowerCase();
    if(!v){ clearState(); baseHint(); return; }
    var hits=[];
    els.forEach(function(x){
      x.el.classList.remove("flash");
      if(x.it.hay.indexOf(v)>=0){ x.el.classList.add("hit"); x.el.classList.remove("dim"); hits.push(x); }
      else{ x.el.classList.add("dim"); x.el.classList.remove("hit"); }
    });
    countEl.textContent="命中 "+hits.length+" / "+IDX.length;
    if(hits.length){
      void hits[0].el.getBoundingClientRect(); hits[0].el.classList.add("flash");
      hits[0].el.scrollIntoView({behavior:"smooth",block:"center"});
    }
  }
  q.addEventListener("input",run);
  baseHint();
  var navEls=els.filter(function(x){return x.it.nav;}).map(function(x){return x.el;});
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
