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


# ── 架构图几何常量(单位 px,viewBox 内)──
_CANVAS_W = 1180
_PAD = 26
_LW = 176          # 左侧层标题栏宽
_MW, _MH = 184, 66   # 模块宽 / 高
_MG, _RG = 14, 14    # 模块列间距 / 行间距
_AC = 34           # 层间箭头连接区高
_BPAD = 22         # 层带内上下留白


def _module_svg(p, x, y, accent):
    """单个项目模块:可点(<a>)或规划占位(<g>)。图标优先,回退首字母 tile。"""
    nav = p["status"] != "plan"
    gid = _gid(p["key"])
    dot = {"ready": "var(--ok)", "assets": "var(--warn)"}.get(p["status"], "var(--c-ink3)")
    cls = "mod" if nav else "mod mod-plan"
    if nav:
        head = ('<a href="{h}" class="{c}" id="{i}" tabindex="0" '
                'aria-label="{n}:{d}">').format(h=_esc(p["href"]), c=cls, i=gid,
                                                n=_esc(p["name"]), d=_esc(p["desc"]))
        tail = "</a>"
    else:
        head = '<g class="{c}" id="{i}" aria-label="{n}(规划中)">'.format(
            c=cls, i=gid, n=_esc(p["name"]))
        tail = "</g>"
    out = [head]
    out.append('<rect class="mod-rect" x="{x}" y="{y}" width="{w}" height="{h}" rx="13" '
               'style="--accent:{a}"/>'.format(x=x, y=y, w=_MW, h=_MH, a=accent))
    ix, iy, isz = x + 13, y + 16, 34
    if p.get("icon"):
        out.append('<image x="{ix}" y="{iy}" width="{s}" height="{s}" href="{u}" '
                   'preserveAspectRatio="xMidYMid meet"/>'.format(
                       ix=ix, iy=iy, s=isz, u=_esc(p["icon"])))
    else:
        out.append('<rect class="tile" x="{ix}" y="{iy}" width="{s}" height="{s}" rx="9" '
                   'style="--accent:{a}"/>'.format(ix=ix, iy=iy, s=isz, a=accent))
        out.append('<text class="tile-t" x="{tx}" y="{ty}" text-anchor="middle">{t}</text>'
                   .format(tx=ix + isz / 2, ty=iy + isz / 2 + 5, t=_esc(p["init"])))
    tx = x + 58
    name = p["name"] if len(p["name"]) <= 15 else p["name"][:14] + "…"
    out.append('<text class="mod-name" x="{tx}" y="{ty}">{n}</text>'.format(
        tx=tx, ty=y + 27, n=_esc(name)))
    if nav and (p["svg"] or p["md"]):
        meta = "{s} 图 · {m} 篇".format(s=p["svg"], m=p["md"])
    elif nav:
        meta = "待编译"
    else:
        meta = "规划中"
    out.append('<text class="mod-meta" x="{tx}" y="{ty}">{m}</text>'.format(
        tx=tx, ty=y + 46, m=_esc(meta)))
    out.append('<circle class="mod-dot" cx="{cx}" cy="{cy}" r="4" style="fill:{d}"/>'.format(
        cx=x + _MW - 15, cy=y + 18, d=dot))
    out.append(tail)
    return "".join(out)


def build_svg(projects):
    """把分层后的项目程序化排布成一张 Apple 工业风"计算机体系架构图"SVG。"""
    bands = []
    for k, title, sub, color in LAYERS:
        items = [p for p in projects if p["layer"] == k]
        if items:
            bands.append((k, title, sub, color, items))
    x0 = _PAD + _LW
    area = _CANVAS_W - _PAD - x0
    per_row = max(1, (area + _MG) // (_MW + _MG))
    y = _PAD
    body = []
    for bi, (k, title, sub, color, items) in enumerate(bands):
        rows = (len(items) + per_row - 1) // per_row
        bh = rows * _MH + (rows - 1) * _RG + 2 * _BPAD
        bx, bw = _PAD, _CANVAS_W - 2 * _PAD
        body.append('<rect class="band" x="{x}" y="{y}" width="{w}" height="{h}" rx="18" '
                    'style="--accent:{a}"/>'.format(x=bx, y=y, w=bw, h=bh, a=color))
        body.append('<rect class="band-tab" x="{x}" y="{y}" width="6" height="{h}" rx="3" '
                    'style="fill:{a}"/>'.format(x=bx, y=y + 16, h=bh - 32, a=color))
        body.append('<text class="lyr-title" x="{tx}" y="{ty}">{t}</text>'.format(
            tx=bx + 24, ty=y + _BPAD + 14, t=_esc(title)))
        body.append('<text class="lyr-sub" x="{tx}" y="{ty}">{s}</text>'.format(
            tx=bx + 24, ty=y + _BPAD + 33, s=_esc(sub)))
        body.append('<text class="lyr-cnt" x="{tx}" y="{ty}">{n} 个项目</text>'.format(
            tx=bx + 24, ty=y + bh - _BPAD + 2, n=len(items)))
        for i, p in enumerate(items):
            r, c = divmod(i, per_row)
            mx = x0 + c * (_MW + _MG)
            my = y + _BPAD + r * (_MH + _RG)
            body.append(_module_svg(p, mx, my, color))
        y += bh
        if bi < len(bands) - 1:
            cx = _CANVAS_W // 2
            body.append('<line class="flow" x1="{cx}" y1="{y1}" x2="{cx}" y2="{y2}" '
                        'marker-end="url(#ar)"/>'.format(cx=cx, y1=y + 9, y2=y + _AC - 7))
            y += _AC
    total_h = y + _PAD
    return ('<svg id="atlas" xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 {w} {h}" width="100%" role="img" '
            'aria-label="计算机体系架构导航图 · 点击任意项目下钻">'
            '<defs>'
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#000" flood-opacity="0.14"/>'
            '</filter>'
            '<marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
            'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L9,5 L0,10 z" class="ar"/>'
            '</marker></defs>{body}</svg>').format(w=_CANVAS_W, h=total_h, body="".join(body))


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
html{background:var(--c-bg2);transition:background-color .3s}
html,body{margin:0;padding:0}
body{font-family:var(--sans);color:var(--c-ink);min-height:100vh;-webkit-font-smoothing:antialiased;
  background:radial-gradient(1100px 560px at 88% -12%,var(--grid-tint),transparent 60%),
             radial-gradient(900px 520px at 2% 110%,var(--grid-tint2),transparent 58%),
             linear-gradient(180deg,var(--c-bg),var(--c-bg2));
  transition:background-color .3s,color .3s}
.wrap{max-width:1240px;margin:0 auto;padding:40px 28px 72px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--c-brand-ink);margin:0 0 12px;display:flex;align-items:center;gap:8px}
.eyebrow::before{content:"";width:24px;height:1px;background:var(--c-brand-ink);opacity:.7}
h1{font-size:34px;line-height:1.12;margin:0 0 12px;font-weight:700;letter-spacing:-.02em}
.sub{color:var(--c-ink2);font-size:15px;max-width:700px;line-height:1.6;margin:0}
.tt{flex:none;width:44px;height:44px;border-radius:12px;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink);cursor:pointer;display:grid;place-items:center;
  box-shadow:var(--c-shadow-lg);transition:transform .15s,background .2s}
.tt:hover{transform:translateY(-1px)}
.tt-ico{font-size:18px;line-height:1} .tt-sun{display:none}
:root[data-theme="light"] .tt-moon{display:none}
:root[data-theme="light"] .tt-sun{display:inline}
.statbar{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0 18px}
.stat{background:var(--c-panel);border:1px solid var(--c-line);border-radius:13px;padding:12px 18px;
  box-shadow:var(--c-shadow-lg)}
.stat b{display:block;font-size:22px;font-weight:700;letter-spacing:-.02em;font-family:var(--mono)}
.stat span{font-size:11.5px;color:var(--c-ink3);text-transform:uppercase;letter-spacing:.06em}
.toolbar{display:flex;align-items:center;gap:16px;margin:12px 0 8px;flex-wrap:wrap}
.search{flex:1;min-width:260px;display:flex;align-items:center;gap:9px;background:var(--c-panel);
  border:1px solid var(--c-line);border-radius:12px;padding:11px 14px;box-shadow:var(--c-shadow-lg);
  transition:border-color .18s,box-shadow .18s}
.search:focus-within{border-color:var(--c-brand);box-shadow:0 0 0 4px color-mix(in srgb,var(--c-brand) 18%,transparent)}
.search svg{color:var(--c-ink3);flex:none}
.search input{flex:1;border:0;background:transparent;color:var(--c-ink);font-size:14.5px;outline:none;font-family:var(--sans)}
.search kbd{font-family:var(--mono);font-size:11px;color:var(--c-ink3);border:1px solid var(--c-line2);
  border-radius:6px;padding:2px 7px;background:var(--c-panel2)}
.count{font-size:12.5px;color:var(--c-ink3);font-family:var(--mono);white-space:nowrap}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 20px;font-size:12.5px;color:var(--c-ink2)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:9px;height:9px;border-radius:50%;display:inline-block}
.diagram{position:relative;background:var(--c-panel);border:1px solid var(--c-line);border-radius:22px;
  padding:16px;box-shadow:var(--c-shadow-lg);overflow-x:auto}

/* ── 架构图 SVG 主题化(不反相,图标保持真品牌色)── */
#atlas{display:block;width:100%;height:auto;min-width:960px}
.band{fill:color-mix(in srgb,var(--accent) 6%,var(--c-panel));
  stroke:color-mix(in srgb,var(--accent) 20%,var(--c-line));stroke-width:1;filter:url(#soft)}
.lyr-title{fill:var(--c-ink);font:600 15px var(--sans)}
.lyr-sub{fill:var(--c-ink3);font:400 11px var(--sans)}
.lyr-cnt{fill:var(--c-ink3);font:600 11px var(--mono)}
.mod{cursor:pointer}
.mod-rect{fill:color-mix(in srgb,var(--accent) 13%,var(--c-panel));
  stroke:color-mix(in srgb,var(--accent) 36%,var(--c-line2));stroke-width:1.2;transition:stroke .16s,filter .16s}
.mod:hover .mod-rect{stroke:var(--accent);stroke-width:2;
  filter:drop-shadow(0 3px 10px color-mix(in srgb,var(--accent) 42%,transparent))}
.mod:focus{outline:none}
.mod:focus-visible .mod-rect{stroke:var(--c-brand);stroke-width:2.6}
.mod-plan{cursor:default}
.mod-plan .mod-rect{fill:var(--c-panel);stroke-dasharray:5 4;opacity:.7}
.mod-plan .mod-name,.mod-plan .mod-meta,.mod-plan .tile,.mod-plan image{opacity:.5}
.mod-name{fill:var(--c-ink);font:600 13px var(--sans)}
.mod-meta{fill:var(--c-ink3);font:500 10.5px var(--mono)}
.tile{fill:var(--accent)}
.tile-t{fill:#fff;font:700 14px var(--sans);letter-spacing:-.02em}
.flow{stroke:var(--c-ink3);stroke-width:1.5;opacity:.5}
.ar{fill:var(--c-ink3)}
/* 搜索态:命中在图上 flash 高亮,其余淡出 */
.mod.dim{opacity:.24;transition:opacity .2s}
.mod.hit .mod-rect{stroke:var(--c-brand);stroke-width:2.6}
@keyframes flash{0%,100%{filter:none}35%{filter:drop-shadow(0 0 11px var(--c-brand))}}
.mod.flash .mod-rect{animation:flash 1.05s ease-out 2;stroke:var(--c-brand);stroke-width:2.8}

footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:26px;
  color:var(--c-ink3);font-size:12px;font-family:var(--mono)}
@media(max-width:720px){.wrap{padding:28px 16px 56px}h1{font-size:26px}.diagram{padding:10px;border-radius:16px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <p class="eyebrow">Core Principles Atlas</p>
      <h1>核心原理图谱 · 计算机体系架构</h1>
      <p class="sub">这套图谱本身是一张<b>计算机系统架构图</b>:自上而下按体系层次(接口 → 计算 → 存储 → 协调 → 编排 → 网络 → 内核 → 运行时)排布,<b>每个项目是所属层里的一个可点模块</b>,点击即下钻到该项目的交互式原理图谱。</p>
    </div>
    <button class="tt" id="tt" aria-label="切换深浅主题" title="切换深浅主题">
      <span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span>
    </button>
  </div>

  <div class="statbar" id="statbar"></div>

  <div class="toolbar">
    <label class="search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <input id="q" type="text" placeholder="搜索项目 / 关键词 → 在体系图上定位并高亮…" autocomplete="off" aria-label="搜索项目"/>
      <kbd>/</kbd>
    </label>
    <span class="count" id="count"></span>
  </div>
  <div class="legend">
    <span><i style="background:var(--ok)"></i>就绪 · 可交互</span>
    <span><i style="background:var(--warn)"></i>资源 · 待编译</span>
    <span><i style="background:var(--c-ink3)"></i>规划中</span>
    <span style="color:var(--c-ink3)">/ 或 ⌘K 聚焦搜索 · ↑↓←→ 移动 · Enter 进入 · Esc 清空</span>
  </div>

  <div class="diagram">__SVG__</div>

  <footer>
    <span id="foot"></span>
    <span>static · 无需服务器 · 由 gen.py 按体系架构自动生成 · 最近更新 __UPDATED__</span>
  </footer>
</div>

<script>
(function(){
  var AGG=__AGG__, IDX=__INDEX__;
  var r=document.documentElement, KEY="atlas-nav-theme";
  // ── 主题 ──
  function ap(t){ if(t==="light") r.setAttribute("data-theme","light"); else r.removeAttribute("data-theme"); }
  var s="dark"; try{ s=localStorage.getItem(KEY)||"dark"; }catch(e){} ap(s);
  var tt=document.getElementById("tt");
  if(tt) tt.onclick=function(){ var n=r.getAttribute("data-theme")==="light"?"dark":"light"; ap(n); try{localStorage.setItem(KEY,n);}catch(e){} };
  // ── 总览 stat 条 ──
  var stats=[["项目",AGG.projects],["可交互",AGG.accessible],["就绪",AGG.ready],["体系层",AGG.layers],["图谱",AGG.svg],["文档",AGG.md]];
  document.getElementById("statbar").innerHTML=stats.map(function(x){return '<div class="stat"><b>'+x[1]+'</b><span>'+x[0]+'</span></div>';}).join("");
  document.getElementById("foot").textContent=AGG.projects+" 项目 · "+AGG.accessible+" 可交互 · "+AGG.layers+" 体系层 · "+AGG.svg+" 图 · "+AGG.md+" 篇";
  // ── 搜索 → 图上 flash 高亮(非过滤成列表)──
  var q=document.getElementById("q"), countEl=document.getElementById("count");
  var els=IDX.map(function(it){ return {it:it, el:document.getElementById(it.id)}; }).filter(function(x){return x.el;});
  function clearState(){ els.forEach(function(x){ x.el.classList.remove("dim","hit","flash"); }); }
  function baseCount(){ countEl.textContent="共 "+IDX.length+" 个 · "+AGG.accessible+" 可交互"; }
  function run(){
    var v=(q.value||"").trim().toLowerCase();
    if(!v){ clearState(); baseCount(); return; }
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
  baseCount();
  // ── 键盘驱动 ──
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
