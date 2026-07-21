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
    {"id": "theory", "axis": ("强一致 · CP", "最终一致 · AP"), "label": "计算理论 · Theory", "group": "计算理论与数学模型", "kind": "stack",
     "kicker": "COMPUTATION THEORY · 正确性与一致性谱",
     "title": "线性一致/共识 → ACID 事务 → 快照隔离 → 顺序日志 → 最终一致 → 计算模型",
     "position": "回答「并发/分布式下,系统给多强的正确性保证」:轴 = 一致性强度谱(强一致 CP 递减到最终一致 AP),越往下可用性/吞吐越高。每个项目按其最强正确性保证归层。",
     "subtitle": "一致性强度 + 计算模型边界 · 从 CP 到 AP · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("th_lin", "线性一致 / 共识 · CP", "多数派 Raft/ZAB · 强一致元数据 · 选主", ["etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "kubernetes", "containerd"], "#a78bfa"),
         ("th_acid", "ACID 事务 · Serializable", "MVCC + WAL · 事务隔离级别 · 快照可见性", ["postgres", "mysql-server", "neo4j", "doris"], "#0a84ff"),
         ("th_snap", "快照隔离 / 时间旅行", "表级快照 + 乐观提交 · 多版本文件", ["iceberg", "hudi", "orc", "arrow"], "#2dd4bf"),
         ("th_log", "顺序日志 / 有序 · ISR", "分区内有序 + 副本同步 · exactly-once", ["kafka", "flink"], "#0a84ff"),
         ("th_eventual", "最终一致 / 弱序 · AP", "异步复制 · 读己所写 · 内存弱保证", ["redis", "rocksdb", "milvus"], "#8a8a90"),
         ("th_compute", "计算模型边界 · 有界↔无界", "批(全量重算)↔ 流(增量+状态)↔ 张量(计算图)", ["hadoop", "spark", "clickhouse", "starrocks", "trino", "duckdb", "pytorch", "tensorflow", "vllm", "ray", "go", "rust", "nginx", "grpc", "ffmpeg", "linux", "openjdk"], "#a78bfa"),
     ]},
    {"id": "hardware", "axis": ("热 · 快 · 近 CPU", "冷 · 慢 · 贴硬件"), "label": "物理底座 · Hardware", "group": "物理底座与体系结构", "kind": "stack",
     "kicker": "HARDWARE / STORAGE HIERARCHY · 物理距离与延迟",
     "title": "内存态 → 本地引擎 → 页+日志 → 表格式/文件 → 分布式/远端 → 内核/硬件",
     "position": "回答「数据与执行离 CPU 多远」:轴 = 物理距离/延迟梯度(热·快·近 CPU 递减到冷·慢·贴硬件)。每个项目按其数据/执行主要驻留的物理层归位。",
     "subtitle": "存储层级(register→RAM→disk→远端)+ 运行时/内核底座 · 同一物理轴 · 点击下钻",
     "flow": "state",
     "tiers": [
         ("hw_mem", "内存态 · In-Memory", "纯内存结构 · 微秒级 · 断电即失", ["redis", "milvus", "vllm"], "#2dd4bf"),
         ("hw_local", "本地引擎 · Local Engine", "内存+本地盘 · LSM/向量化 · 单机", ["rocksdb", "duckdb", "clickhouse"], "#0a84ff"),
         ("hw_page", "页 + 日志 · Page & WAL", "缓冲页 + 预写日志 · 持久单机", ["postgres", "mysql-server", "neo4j"], "#a78bfa"),
         ("hw_table", "表格式 / 列存文件", "不可变文件 + 元数据 · 对象存储之上", ["iceberg", "hudi", "orc", "arrow", "doris", "starrocks", "trino"], "#2dd4bf"),
         ("hw_dist", "分布式 / 远端", "多副本分布式文件 · 顺序日志 · 网络访问", ["hadoop", "kafka", "etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "spark", "flink"], "#8a8a90"),
         ("hw_kernel", "运行时 / 内核 / 硬件", "语言运行时 · GC · 系统调用 · cgroup 隔离 · GPU", ["go", "rust", "openjdk", "linux", "kubernetes", "containerd", "nginx", "grpc", "ffmpeg", "pytorch", "tensorflow", "ray"], "#8a8a90"),
     ]},
    {"id": "system", "axis": ("高层抽象 · 声明", "底层实现 · 机器"), "label": "系统抽象 · System", "group": "系统抽象与工程实现", "kind": "stack",
     "kicker": "SYSTEM ABSTRACTION · 抽象层级",
     "title": "接口/协议 → 计算/算子引擎 → 核心数据结构 → 存储/持久化 → 运行时/内核",
     "position": "回答「一个系统从声明式抽象到机器实现怎样分层」:轴 = 抽象度(高层声明递减到贴机器实现)。每个项目按其最能代表的抽象层归位——同一物理位置的项目抽象度可不同。",
     "subtitle": "从接口/协议到运行时的工程抽象栈 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("sy_api", "接口 / 协议 · Interface", "SQL/API · RPC · HTTP · 声明式编排契约", ["grpc", "nginx", "kubernetes", "trino"], "#0a84ff"),
         ("sy_engine", "计算 / 算子引擎 · Engine", "查询规划 · 向量化算子 · DAG · 训练/推理图", ["spark", "flink", "doris", "clickhouse", "starrocks", "duckdb", "pytorch", "tensorflow", "vllm", "ray"], "#a78bfa"),
         ("sy_ds", "核心数据结构 · Structure", "LSM / B树 / 列式 / 图 / 向量 / 跳表", ["rocksdb", "postgres", "mysql-server", "neo4j", "milvus", "redis", "orc", "arrow"], "#0a84ff"),
         ("sy_store", "存储 / 持久化 · Persistence", "日志段 · 表格式 · 分布式文件 · 副本", ["kafka", "iceberg", "hudi", "hadoop", "etcd", "zookeeper", "hashicorp-raft", "etcd-raft"], "#2dd4bf"),
         ("sy_rt", "运行时 / 内核 · Machine", "语言运行时 · GC · 调度 · 系统调用 · 容器", ["go", "rust", "openjdk", "linux", "containerd", "ffmpeg"], "#8a8a90"),
     ]},
    {"id": "workload", "axis": ("数据入口 · 上游", "结果产出 / 底座 · 下游"), "label": "工作负载 · Workload", "group": "工作负载与领域范式", "kind": "stack",
     "kicker": "WORKLOAD PIPELINE · 数据/负载处理流水",
     "title": "采集/接入 → 计算/训练 → 查询/推理 → 协调/编排 → 运行时底座",
     "position": "回答「一类负载(大数据/AI/在线服务)怎样从入口流到产出」:轴 = 处理流水位置(上游数据入口递进到下游产出/底座)。每个项目按其在负载流水中承担的环节归位。",
     "subtitle": "大数据 + AI + 云原生负载的统一处理流水 · 点击下钻",
     "flow": "hot",
     "tiers": [
         ("wl_ingest", "采集 / 接入 · Ingest", "日志总线 · 网关 · RPC · 编解码 · 向量库", ["kafka", "nginx", "grpc", "ffmpeg", "milvus"], "#0a84ff"),
         ("wl_compute", "计算 / 训练 · Compute", "批流计算 DAG · 分布式训练 · shuffle", ["spark", "flink", "hadoop", "pytorch", "tensorflow", "ray"], "#a78bfa"),
         ("wl_query", "查询 / 推理 · Serve", "MPP 查询 · 向量化 · 联邦 · 高吞吐推理", ["doris", "clickhouse", "starrocks", "trino", "duckdb", "vllm"], "#0a84ff"),
         ("wl_coord", "协调 / 编排 · Coordinate", "元数据 · 选主 · 容器编排 · 表格式治理", ["etcd", "zookeeper", "hashicorp-raft", "etcd-raft", "kubernetes", "containerd", "iceberg", "hudi", "orc", "arrow"], "#8a8a90"),
         ("wl_state", "状态 / 底座 · Substrate", "内存/持久状态后端 · 语言运行时 · 内核", ["redis", "rocksdb", "postgres", "mysql-server", "neo4j", "go", "rust", "openjdk", "linux"], "#2dd4bf"),
     ]},
]


# ── 主题视角(一级导航第二模式):6 大跨项目专题,与项目视角并行、不混。──
# 每主题:id / 标题 / 核心一句 / 3 图解点标题 / 相关项目 key(下钻目标,须 ∈ META)。
# 产物 = topics/<id>/index.html 轻量综合页。本 session 交付导航 + 跳转骨架。
TOPICS = [
    {"id": "consensus", "title": "Distributed Consensus & Replication", "accent": "#0a84ff",
     "core": "日志复制 + 多数派仲裁,实现多副本强一致。",
     "dots": ["日志连续性回溯匹配", "Multi-Raft 分片路由与 Leader 均衡", "Read Index / Lease 绕过日志的读一致性"],
     "projects": ["etcd", "etcd-raft", "hashicorp-raft", "zookeeper", "kafka"]},
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
            {"name": "数据库学派 (Berkeley/Wisconsin)", "kind": "学派", "edge": "关系/列存/分析引擎理念继承", "projs": ["mysql-server", "clickhouse", "doris", "starrocks", "trino", "duckdb", "orc", "arrow"]},
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


def _topic_hero(tid):
    """主题卡顶部预览图:取该主题 design/ 下的 *00生态架构.svg(核心代表图),base64 内联。
    找不到返回 ''(卡片降级为无图)。"""
    import glob as _glob
    hits = _glob.glob(os.path.join(ROOT, "topics", tid, "design", "*00生态架构*.svg"))
    if not hits:
        hits = _glob.glob(os.path.join(ROOT, "topics", tid, "design", "*.svg"))
    if not hits:
        return ""
    try:
        with open(sorted(hits)[0], "rb") as f:
            b = base64.b64encode(f.read()).decode("ascii")
        return '<span class="tc-hero"><img src="data:image/svg+xml;base64,{b}" alt="" loading="lazy"/></span>'.format(b=b)
    except OSError:
        return ""


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
    return idx


def build_html(projects):
    agg = aggregate(projects)
    return (TEMPLATE
            .replace("__SVG__", build_all_lenses(projects))
            .replace("__LENSSWITCH__", build_lens_switch())
            .replace("__TOPICS__", build_topics_cards())
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
.mode-seg.on{background:var(--c-panel);color:var(--c-ink);box-shadow:0 1px 3px rgba(0,0,0,.08)}
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
.topics-note b{color:var(--c-ink2);font-weight:700}
.topics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:8px 4px 20px}
.topic-card{display:flex;flex-direction:column;position:relative;border-radius:16px;background:var(--c-panel);border:1px solid var(--c-line);text-decoration:none;overflow:hidden;transition:border-color .18s,box-shadow .18s,transform .18s}
.topic-card:hover{border-color:color-mix(in srgb,var(--accent) 55%,var(--c-line));box-shadow:0 8px 28px rgba(0,0,0,.10);transform:translateY(-2px)}
.tc-hero{display:block;height:132px;overflow:hidden;background:color-mix(in srgb,var(--accent) 6%,var(--c-bg2));border-bottom:1px solid var(--c-line);position:relative}
.tc-hero img{width:100%;height:auto;display:block;object-fit:cover;object-position:top center;opacity:.96}
.tc-hero::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,transparent 55%,var(--c-panel) 100%)}
.topic-card:hover .tc-hero img{opacity:1}
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
    <button class="mode-seg on" data-mode="project" role="tab">项目视角</button>
    <button class="mode-seg" data-mode="topic" role="tab">主题视角</button>
    <span class="mode-div" aria-hidden="true"></span>
    <span class="mode-clab">项目背景</span>
    <button class="mode-seg" data-mode="standards" role="tab">标准视角</button>
    <button class="mode-seg" data-mode="industry" role="tab">产业视角</button>
    <button class="mode-seg" data-mode="people" role="tab">学派视角</button>
  </div>
  <div class="switch-region mode-switchbar on" data-mode="project">__LENSSWITCH__</div>
</nav>
</div>

<main class="stage">
  <div class="mode-view on" data-mode="project"><div class="diagram">__SVG__</div></div>
  <div class="mode-view" data-mode="topic">__TOPICS__</div>
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
