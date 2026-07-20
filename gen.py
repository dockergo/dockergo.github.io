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
    "nginx": "ingress", "ffmpeg": "ingress",
    # Schedule:编排/调度/资源
    "kubernetes": "schedule", "ray": "schedule", "spark": "schedule", "flink": "schedule",
    # Execute:查询执行/向量化/训练推理
    "doris": "execute", "clickhouse": "execute", "starrocks": "execute",
    "trino": "execute", "duckdb": "execute",
    "pytorch": "execute", "tensorflow": "execute", "vllm": "execute", "milvus": "execute",
    # State:内存/索引/事务/状态后端/图
    "redis": "state", "rocksdb": "state", "postgres": "state", "neo4j": "state",
    # Persist:日志/表格式/列存/分布式文件
    "kafka": "persist", "hudi": "persist",
    "iceberg": "persist", "orc": "persist", "hadoop": "persist",
    # Coordinate:共识/选主/控制面状态
    "etcd": "coord", "zookeeper": "coord", "raft": "coord",
    # Runtime:语言运行时/执行模型/内存纪律
    "go": "runtime", "rust": "runtime", "linux": "runtime",
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
    """项目 key → SVG 元素 id;Python 与 JS 必须一致。"""
    return "m_" + re.sub(r"[^a-zA-Z0-9]+", "_", key.lower())


def _esc(s):
    return html.escape(str(s), quote=True)


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


def _node(p, x, y, w, accent):
    """项目节点:工业铭牌式模块。点击进入项目架构图。"""
    nav = p["status"] != "plan"
    gid = _gid(p["key"])
    dot = {"ready": "var(--ok)", "assets": "var(--warn)"}.get(p["status"], "var(--c-ink3)")
    cls = "nd" if nav else "nd nd-plan"
    meta = ("{s} 图 · {m} 篇".format(s=p["svg"], m=p["md"]) if (p["svg"] or p["md"])
            else ("规划中" if not nav else "待编译"))
    tip = "{n} · {d} · {m}".format(n=p["name"], d=p["desc"], m=meta)
    if nav:
        head = ('<a href="{h}" class="{c}" id="{i}" tabindex="0">'
                '<title>{t}</title>').format(h=_esc(p["href"]), c=cls, i=gid, t=_esc(tip))
        tail = "</a>"
    else:
        head = '<g class="{c}" id="{i}"><title>{t}</title>'.format(c=cls, i=gid, t=_esc(tip))
        tail = "</g>"
    out = [head,
           '<rect class="nd-rect" x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
           'style="--accent:{a}"/>'.format(x=x, y=y, w=w, h=_NODEH, a=accent)]
    isz = 22
    ix, iy = x + 10, y + (_NODEH - isz) / 2
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
    {"id": "vonneumann", "label": "冯诺依曼", "group": "理论视角", "kind": "stack",
     "kicker": "VON NEUMANN ARCHITECTURE · 计算机体系结构",
     "title": "I/O → 控制器 → 运算器 → 主存 → 外存 → 运行时",
     "position": "回答「一个计算系统怎样把请求变成结果」:请求从 I/O 进入,控制器决定做什么,运算器执行,主存/外存承载状态,运行时是底座。",
     "subtitle": "冯诺依曼体系结构(1945)自上而下的数据通路 · 各层项目实现该层机制 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("vn_io", "I/O · 输入输出", "北向接入 · 网关 · TLS · 编解码 · 传输", ["nginx", "ffmpeg"], "#0a84ff"),
         ("vn_ctrl", "控制器 · Control Unit", "调度 / 编排 / 共识 —— 决定「做什么、在哪做」", ["kubernetes", "ray", "spark", "flink", "etcd", "zookeeper", "raft"], "#a78bfa"),
         ("vn_alu", "运算器 · ALU", "查询/向量化 · 训练推理 · 算子流水 —— 实际计算", ["doris", "clickhouse", "starrocks", "trino", "duckdb", "pytorch", "tensorflow", "vllm", "milvus"], "#0a84ff"),
         ("vn_mem", "主存 · Memory", "内存结构 · 索引 · 事务 · 状态后端", ["redis", "rocksdb", "postgres", "neo4j"], "#2dd4bf"),
         ("vn_store", "外存 · Storage", "日志 · 表格式 · 列存文件 · 分布式文件系统", ["kafka", "hudi", "iceberg", "orc", "hadoop"], "#2dd4bf"),
         ("vn_rt", "运行时 · Substrate", "语言运行时 · GC · 调度纪律 · 内核", ["go", "rust", "linux"], "#8a8a90"),
     ]},
    {"id": "tcpip", "label": "TCP/IP 网络栈", "group": "理论视角", "kind": "stack",
     "kicker": "TCP/IP PROTOCOL STACK · 网络协议分层",
     "title": "应用层 L7 → 传输层 L4 → 网络/链路 · OS",
     "position": "回答「一个字节怎样在网络上可靠送达」:严格按 TCP/IP 四层模型归位,只收真正实现协议栈层次的项目(共识/存储类不属于本视角)。",
     "subtitle": "TCP/IP 分层模型 · 请求自上而下穿栈 · 仅含协议栈成员 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("net_app", "应用层 · L7 Application", "HTTP/1·2·3 · 反向代理 · 消息协议端点", ["nginx", "kafka"], "#0a84ff"),
         ("net_os", "网络/链路 · L3-L2 · OS", "内核协议栈 · 路由 · netpoll/epoll · 零拷贝", ["linux", "go"], "#8a8a90"),
     ]},
    {"id": "aiml", "label": "AI / ML", "group": "领域视角", "kind": "stack",
     "kicker": "AI / ML PIPELINE · 机器学习系统",
     "title": "数据/检索 → 训练 → 推理服务 → 分布式调度 → 底座",
     "position": "回答「一个模型怎样从数据训练出来、再高吞吐地对外服务」:数据流自上而下贯穿训练与推理两段。",
     "subtitle": "机器学习系统剖面 · 从张量到 token · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("ai_data", "数据 / 向量检索", "向量库 · ANN 检索 · 特征/嵌入存储", ["milvus"], "#2dd4bf"),
         ("ai_train", "训练框架 · Training", "自动微分 · 计算图 · 算子分发到设备", ["pytorch", "tensorflow"], "#0a84ff"),
         ("ai_infer", "推理服务 · Serving", "KV 缓存分块 · 连续批处理 · 高吞吐 token", ["vllm"], "#0a84ff"),
         ("ai_dist", "分布式调度 · Scale", "task/actor · 参数分片 · 集群资源调度", ["ray"], "#a78bfa"),
         ("ai_rt", "运行时底座 · Substrate", "语言运行时 · 内存/并发/GPU 边界", ["rust", "go", "linux"], "#8a8a90"),
     ]},
    {"id": "bigdata", "label": "大数据", "group": "领域视角", "kind": "stack",
     "kicker": "BIG DATA STACK · 数据密集系统",
     "title": "采集 → 存储/表格式 → 计算 → 查询 → 协调",
     "position": "回答「海量数据怎样从进入到被分析」:数据自上而下流经采集、落盘、批流计算、查询,协调层横向保障一致性。",
     "subtitle": "数据密集系统剖面 · 从日志到分析 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("bd_ingest", "采集 / 日志总线", "顺序日志 · 流式接入 · CDC", ["kafka"], "#0a84ff"),
         ("bd_store", "存储 / 表格式 / 文件", "表格式 · 列存文件 · 分布式文件系统", ["iceberg", "hudi", "orc", "hadoop"], "#2dd4bf"),
         ("bd_compute", "计算引擎 · Compute", "DAG · shuffle · 有状态流 · 容错重算", ["spark", "flink"], "#a78bfa"),
         ("bd_query", "查询引擎 · Query", "MPP · 向量化 · CBO · 联邦 · 嵌入式", ["doris", "clickhouse", "starrocks", "trino", "duckdb"], "#0a84ff"),
         ("bd_coord", "协调 · Coordination", "元数据 · 选主 · 集群成员一致性", ["zookeeper", "etcd", "raft"], "#8a8a90"),
     ]},
    {"id": "memhier", "label": "存储层级", "group": "理论视角", "kind": "stack",
     "kicker": "MEMORY / STORAGE HIERARCHY · 存储层级",
     "title": "内存态 → 本地引擎 → 页+日志 → 表格式/文件 → 分布式/远端",
     "position": "回答「数据放在离 CPU 多远、如何在层级间搬运」:越往下容量越大、延迟越高,是所有数据系统的物理约束轴。",
     "subtitle": "经典存储层级(register→cache→RAM→disk→远端)投影到数据系统 · 点击下钻",
     "flow": "state",
     "tiers": [
         ("mh_mem", "内存态 · In-Memory", "纯内存结构 · 微秒级 · 断电即失", ["redis", "milvus"], "#2dd4bf"),
         ("mh_local", "本地引擎 · Local Engine", "内存+本地盘 LSM/向量化 · 单机", ["rocksdb", "duckdb"], "#0a84ff"),
         ("mh_page", "页 + 日志 · Page & WAL", "缓冲页 + 预写日志 · 持久单机存储", ["postgres", "neo4j"], "#a78bfa"),
         ("mh_file", "表格式 / 列存文件", "不可变文件 + 元数据 · 对象存储之上", ["iceberg", "hudi", "orc"], "#2dd4bf"),
         ("mh_dist", "分布式 / 远端", "多副本分布式文件 · 顺序日志 · 网络访问", ["hadoop", "kafka"], "#8a8a90"),
     ]},
    {"id": "consistency", "label": "一致性模型", "group": "理论视角", "kind": "stack",
     "kicker": "CONSISTENCY MODELS · 一致性谱系",
     "title": "线性一致/共识 → ACID 事务 → 快照隔离 → 顺序日志 → 最终一致",
     "position": "回答「并发下系统给多强的正确性保证」:自上而下一致性递减、可用性/吞吐递增,是分布式设计的核心权衡轴。",
     "subtitle": "从线性一致(CP)到最终一致(AP)的一致性谱系 · 点击下钻",
     "flow": "ctrl",
     "tiers": [
         ("cs_lin", "线性一致 / 共识 · CP", "Raft/ZAB 多数派 · 强一致元数据存储", ["etcd", "zookeeper", "raft"], "#a78bfa"),
         ("cs_acid", "ACID 事务 · Serializable", "MVCC + WAL · 事务隔离级别", ["postgres", "doris"], "#0a84ff"),
         ("cs_snap", "快照隔离 · Snapshot", "表级快照 + 乐观提交 · 时间旅行", ["iceberg", "hudi"], "#2dd4bf"),
         ("cs_log", "顺序日志 / ISR", "分区内有序 + 副本同步 · at-least/exactly-once", ["kafka", "flink"], "#0a84ff"),
         ("cs_evt", "最终一致 / 副本 · AP", "异步复制 · 读己所写弱保证", ["redis", "rocksdb"], "#8a8a90"),
     ]},
    {"id": "cloudnative", "label": "云原生", "group": "领域视角", "kind": "stack",
     "kicker": "CLOUD NATIVE STACK · 云原生",
     "title": "编排/控制平面 → 入口/网关 → 协调/共识 → 容器运行时底座",
     "position": "回答「服务怎样被编排、路由、协调地跑在集群上」:声明式控制平面驱动,入口接流量,协调层保状态一致。",
     "subtitle": "云原生控制/数据面剖面 · CNCF 分层视角 · 点击下钻",
     "flow": "ctrl",
     "tiers": [
         ("cn_ctrl", "编排 / 控制平面", "声明式 reconcile · 资源调度 · 分布式执行", ["kubernetes", "ray", "spark"], "#a78bfa"),
         ("cn_ingress", "入口 / 网关 / 边缘", "反向代理 · 动态路由 · TLS · 服务发现", ["nginx"], "#0a84ff"),
         ("cn_coord", "协调 / 共识 · 状态存储", "集群状态真相 · 选主 · 配置中心", ["etcd", "zookeeper", "raft"], "#2dd4bf"),
         ("cn_rt", "容器运行时 · 底座", "语言运行时 · 内核 cgroup/namespace", ["go", "rust", "linux"], "#8a8a90"),
     ]},
    {"id": "dbkernel", "label": "数据库内核", "group": "领域视角", "kind": "stack",
     "kicker": "DATABASE KERNEL · 数据库内核",
     "title": "查询前端 → MPP 执行 → 事务存储引擎 → 图/向量特化",
     "position": "回答「一条查询在数据库内核里流经哪些部件」:按各库最具代表性的内核层归位(解析规划 / 执行 / 存储 / 特化)。",
     "subtitle": "关系/分析/图/向量数据库内核部件剖面 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("db_front", "查询前端 · 解析/规划/优化", "SQL 解析 · CBO · 联邦下推 · 嵌入式", ["trino", "duckdb"], "#0a84ff"),
         ("db_exec", "执行引擎 · MPP/向量化", "向量化算子 · pipeline · shuffle · MPP", ["doris", "clickhouse", "starrocks"], "#0a84ff"),
         ("db_store", "事务存储引擎 · Page/LSM", "MVCC + WAL · LSM · 缓冲池 · Compaction", ["postgres", "rocksdb"], "#a78bfa"),
         ("db_spec", "特化模型 · 图/向量", "图遍历免索引邻接 · ANN 向量检索", ["neo4j", "milvus"], "#2dd4bf"),
     ]},
]


def build_stack_svg(lens, projects):
    """总线脊接线图:左侧层号栅栏 + 中央竖向总线脊,每层模块经端口接入总线,
    信号沿脊自上而下逐层步进。类 OSI/系统总线工程图——有接线、有端口、有方向。"""
    global LAYER_ITEMS, LAYER_COLOR
    tiers = lens["tiers"]
    by_key = {p["key"]: p for p in projects}
    LAYER_ITEMS = {tk: [by_key[k] for k in keys if k in by_key] for tk, _t, _s, keys, _c in tiers}
    LAYER_COLOR = {tk: c for tk, _t, _s, _keys, c in tiers}

    GUT_X = 44                        # 左号栏起点
    SPINE_X = 250                     # 总线脊 x(号栏与模块道之间)
    LANE_X, LANE_W = 296, 826         # 模块道
    Y1, VGAP, PAD = 208, 30, 20
    NODEH, ROWG, NG = _NODEH, _ROWG, _NG

    band = {}
    y = Y1
    for tk, _t, _s, keys, _c in tiers:
        mods = [by_key[k] for k in keys if k in by_key]
        n = len(mods)
        cols = min(5, max(1, n))
        rows = max(1, -(-n // cols))
        grid_h = rows * (NODEH + ROWG) - ROWG
        h = max(70, grid_h) + PAD * 2
        band[tk] = (y, h, cols, mods)
        y += h + VGAP
    last_bottom = y - VGAP
    total_h = last_bottom + 96

    body = ['<rect class="frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="28"/>'.format(
        x=_FRAME_X, y=_FRAME_Y, w=_FRAME_W, h=total_h - 2 * _FRAME_Y)]
    body.append('<text class="map-kicker" x="70" y="72">%s</text>' % _esc(lens["kicker"]))
    body.append('<text class="map-title" x="70" y="106">%s</text>' % _esc(lens["title"]))
    body.append('<text class="map-subtitle" x="70" y="130">%s</text>' % _esc(lens["subtitle"]))
    if lens.get("position"):
        body.append('<rect class="lens-pos-bg" x="66" y="150" width="1054" height="30" rx="8"/>')
        body.append('<text class="lens-pos" x="82" y="170">%s</text>' % _esc(lens["position"]))

    order = [t[0] for t in tiers]
    centers = {tk: band[tk][0] + band[tk][1] / 2 for tk in order}
    flow = "flow-" + lens.get("flow", "hot")

    # ── OSI 分层栅:每层间一条发丝分隔线(号栏..模块道右缘) ──
    body.append('<g class="osi-grid">')
    for i in range(1, len(order)):
        gy = (band[order[i - 1]][0] + band[order[i - 1]][1] + band[order[i]][0]) / 2
        body.append('<line class="osi-line" x1="{x1}" y1="{y}" x2="{x2}" y2="{y}"/>'.format(
            x1=GUT_X, y=gy, x2=LANE_X + LANE_W))
    # 号栏与模块道的竖向分界(总线所在通道)
    body.append('<line class="osi-vline" x1="{x}" y1="{y1}" x2="{x}" y2="{y2}"/>'.format(
        x=SPINE_X + 22, y1=band[order[0]][0] - 6, y2=last_bottom + 6))
    body.append('</g>')

    # ── 总线脊:自顶层端口到底层端口,分段下行箭头(信号步进) ──
    body.append('<g class="machine-rails">')
    for a, b in zip(order, order[1:]):
        body.append(_flow_path(flow, [(SPINE_X, centers[a]), (SPINE_X, centers[b])]))
    body.append('</g>')

    # ── 逐层:号栏(层号+名+副) · 端口 · 接入线 · 模块道 ──
    for i, (tk, ttitle, tsub, _keys, accent) in enumerate(tiers):
        yy, h, cols, mods = band[tk]
        cy = centers[tk]
        # 层号栏
        body.append('<text class="layer-num" x="{x}" y="{y:.0f}">{n:02d}</text>'.format(x=GUT_X + 8, y=cy - 6, n=i + 1))
        body.append('<text class="layer-title" x="{x}" y="{y:.0f}">{t}</text>'.format(x=GUT_X + 8, y=cy + 14, t=_esc(ttitle)))
        body.append('<text class="layer-sub" x="{x}" y="{y:.0f}">{s}</text>'.format(x=GUT_X + 8, y=cy + 30, s=_esc(tsub[:34])))
        # 端口(脊上的接入点)+ 接入线(脊 → 模块道)
        body.append('<circle class="bus-port" cx="{x}" cy="{y:.1f}" r="5" style="--accent:{c}"/>'.format(x=SPINE_X, y=cy, c=accent))
        body.append('<line class="bus-stub" x1="{x1}" y1="{y:.1f}" x2="{x2}" y2="{y:.1f}" style="--accent:{c}"/>'.format(
            x1=SPINE_X + 5, y=cy, x2=LANE_X - 4, c=accent))
        # 模块道:网格居中
        card_w = (LANE_W - (cols - 1) * NG) / cols
        rows = max(1, -(-len(mods) // cols))
        grid_h = rows * (NODEH + ROWG) - ROWG
        gy0 = yy + (h - grid_h) / 2
        for j, m in enumerate(mods):
            r, c = divmod(j, cols)
            nx = LANE_X + c * (card_w + NG)
            ny = gy0 + r * (NODEH + ROWG)
            body.append(_node(m, nx, ny, card_w, accent))
    return ('<svg class="atlas-lens" data-lens="{lid}" xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{lab} 架构视角 · 点击下钻">'
            '<defs>'
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="10" stdDeviation="18" flood-color="#000" flood-opacity="0.18"/></filter>'
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
    """顶栏 segmented 视角切换器,按 理论框架视角 / 领域视角 两类分组。"""
    groups = []
    seen = []
    for l in LENSES:
        g = l.get("group", "")
        if g not in seen:
            seen.append(g)
    idx = 0
    parts = []
    for g in seen:
        segs = []
        for l in LENSES:
            if l.get("group", "") != g:
                continue
            segs.append('<button class="lens-seg{act}" data-lens="{lid}" role="tab">{lab}</button>'.format(
                act=" on" if idx == 0 else "", lid=l["id"], lab=_esc(l["label"])))
            idx += 1
        parts.append('<span class="lens-grp"><span class="lens-grp-lab">{g}</span><span class="lens-grp-segs">{segs}</span></span>'.format(
            g=_esc(g), segs="".join(segs)))
    return '<div class="lens-switch" role="tablist" aria-label="架构视角">%s</div>' % "".join(parts)


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
            .replace("__SVG__", build_all_lenses(projects))
            .replace("__LENSSWITCH__", build_lens_switch())
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
  --c-bg:#0d0d0f; --c-bg2:#111114; --c-panel:#17171a; --c-panel2:#1e1e22;
  --c-line:rgba(255,255,255,.10); --c-line2:rgba(255,255,255,.16);
  --c-ink:#f2f2f5; --c-ink2:#c4c4c9; --c-ink3:#8a8a90;
  --c-brand:#0a84ff; --c-brand-ink:#409cff; --c-hover:rgba(255,255,255,.06);
  --c-shadow-lg:0 8px 28px rgba(0,0,0,.5),0 24px 48px rgba(0,0,0,.45);
  --ok:#2dd4a7; --warn:#fbbf24;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  --grid-tint:rgba(10,132,255,.10); --grid-tint2:rgba(139,108,255,.09);
}
:root[data-theme="light"]{
  --c-bg:#fbfbfd; --c-bg2:#f5f5f7; --c-panel:#ffffff; --c-panel2:#f5f5f7;
  --c-line:rgba(0,0,0,.09); --c-line2:rgba(0,0,0,.13);
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
.lens-switch{position:absolute;left:50%;transform:translateX(-50%);display:inline-flex;gap:14px;padding:6px 8px;border-radius:12px;background:var(--c-panel);border:1px solid var(--c-line)}
.lens-grp{display:inline-flex;flex-direction:column;gap:4px}
.lens-grp+.lens-grp{padding-left:14px;border-left:1px solid var(--c-line)}
.lens-grp-lab{font:600 10px var(--sans);color:var(--c-ink3);letter-spacing:.06em;white-space:nowrap;text-align:center}
.lens-grp-segs{display:flex;gap:2px;justify-content:center}
.lens-seg{border:0;background:transparent;color:var(--c-ink2);cursor:pointer;font:600 12px var(--sans);padding:5px 12px;border-radius:8px;white-space:nowrap;transition:.15s}
.lens-seg:hover{color:var(--c-ink)}
.lens-seg.on{background:var(--c-brand);color:#fff}
.lens-view{display:none}
.lens-view.on{display:block}
.lens-pos-bg{fill:color-mix(in srgb,var(--c-brand) 7%,transparent);stroke:color-mix(in srgb,var(--c-brand) 22%,transparent);stroke-width:1}
.lens-pos{fill:var(--c-ink2);font:500 12px var(--sans)}
.osi-line{stroke:var(--c-line);stroke-width:1;opacity:.6}
.osi-vline{stroke:var(--c-line);stroke-width:1;stroke-dasharray:2 4;opacity:.5}
.layer-num{fill:var(--c-ink3);font:700 20px var(--mono,monospace);opacity:.55}
.layer-title{fill:var(--c-ink);font:700 13px var(--sans)}
.layer-sub{fill:var(--c-ink3);font:500 10px var(--sans)}
.bus-port{fill:var(--c-bg);stroke:var(--accent,#0a84ff);stroke-width:2.5}
.bus-stub{stroke:var(--accent,#0a84ff);stroke-width:1.5;opacity:.7}
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
/* 单外框:系统母图是一张精密机器剖面,面板/路径/模块共享一张画布 */
.frame{fill:var(--c-panel);stroke:var(--c-line);stroke-width:1;filter:url(#soft)}
:root:not([data-theme="light"]) .frame{fill:color-mix(in srgb,#fff 2%,var(--c-bg))}
.map-kicker{fill:var(--c-ink3);font:700 10px var(--mono);letter-spacing:.18em}
.map-title{fill:var(--c-ink);font:600 19px var(--sans);letter-spacing:-.025em}
.map-subtitle{fill:var(--c-ink3);font:500 12px var(--sans);letter-spacing:-.01em}
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
.nd-rect{fill:color-mix(in srgb,var(--c-panel) 84%,#fff 4%);stroke:var(--c-line2);stroke-width:1;transition:stroke .18s,fill .18s,filter .18s}
.nd-ic{transition:opacity .18s}
.nd:hover .nd-rect{stroke:var(--c-ink);stroke-width:1.35;fill:var(--c-hover);filter:drop-shadow(0 0 7px color-mix(in srgb,var(--accent) 22%,transparent))}
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
  <span class="brand">核心原理图谱</span>
  __LENSSWITCH__
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
  // 底部一行细描述(数值弱化,不与图争视觉)
  document.getElementById("stats").textContent=AGG.projects+" 项目 · "+AGG.accessible+" 可交互 · "+AGG.layers+" 机制节点 · "+AGG.svg+" 图 · "+AGG.md+" 篇 · 更新 __UPDATED__";
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
