#!/usr/bin/env python3
"""fluss-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd fluss-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 Fluss 交互式核心原理图谱（离线自包含 HTML）")
_ap.add_argument("--design-dir", default=None, help="手绘 SVG + prose 文档目录（默认：脚本同级 ./design）")
_ap.add_argument("--out", default=None, help="输出 HTML 路径（默认：脚本同级 index.html）")
_args, _ = _ap.parse_known_args()


def _first_dir(*cands):
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


_DESIGN_DIR = _first_dir(
    _args.design_dir,
    os.environ.get("FLUSS_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("FLUSS_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     Apache Fluss（面向 Flink 的流式存储，介于消息/事件流平台与分布式存储之间）：
#     元模式 = 接触面 × 支撑能力域 × 时机。全景 + 3 接触面 + 8 支撑能力域 = 12 主线。
# ===================================================================== #
MAINLINES = [
    ("Fluss原理_全景主线框架", "pano", "◇", "全景主线框架",
     "流式湖仓存储：双维模型 · 总架构 · 依赖矩阵 · 部署形态 · 三条贯穿声明"),

    ("Fluss原理_接触面_表模型与写入", "iface", "✎", "表模型与写入",
     "日志表 Append 直接追加 / 主键表 Upsert 经 KvTablet 物化产 changelog · 幂等分桶"),
    ("Fluss原理_接触面_读取Lookup与Scan", "iface", "⌕", "读取 Lookup 与 Scan",
     "LogScanner 流式 / Lookuper 点查前缀 / BatchScanner 快照批读 · 投影下推"),
    ("Fluss原理_接触面_Flink与Lakehouse集成", "iface", "⇄", "Flink 与 Lakehouse 集成",
     "connector source/sink · lookup join 维表 · union read 历史+实时联合读"),

    ("Fluss原理_支撑_Log追加存储引擎", "support", "▤", "Log 追加存储引擎",
     "LogTablet→LogSegment 追加日志 · .log+稀疏索引 · 幂等 WriterState · 零拷贝"),
    ("Fluss原理_支撑_KV主键表与changelog", "support", "◈", "KV 主键表与 changelog",
     "RocksDB 物化 · WAL 先行 + preWriteBuffer · rowMerger 合并 · CDC changelog"),
    ("Fluss原理_支撑_Arrow列存与投影下推", "support", "▦", "Arrow 列存与投影下推",
     "MemoryLogRecordsArrowBuilder 攒 Arrow batch · FileLogProjection 服务端裁列"),
    ("Fluss原理_支撑_副本复制与ISR", "support", "⬡", "副本复制与 ISR",
     "Leader/Follower pull 复制 · ISR 收缩扩张 · HW = ISR 最小 LEO · AdjustIsr"),
    ("Fluss原理_支撑_协调器元数据与调度", "support", "⚙", "协调器元数据与调度",
     "单线程事件循环 · 状态机 + Leader 选举 · ZooKeeper 元数据 · 建表副本放置"),
    ("Fluss原理_支撑_分层存储与Lakehouse", "support", "◫", "分层存储与 Lakehouse",
     "远程日志 tiering → DFS · 独立 Flink 作业写 Paimon/Iceberg · 按 offset 联合读"),
    ("Fluss原理_支撑_KV快照与恢复", "support", "◉", "KV 快照与恢复",
     "RocksDB 增量快照 → DFS · 下载快照 + 从 offset 两阶段回放 changelog"),
    ("Fluss原理_支撑_网络RPC与安全", "support", "◱", "网络 RPC 与安全",
     "Netty Reactor · RequestChannel 队列削峰 · ApiKeys 分派 · ACL/SASL 鉴权"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接触面主线 · 应用如何用（写入 / 读取 / Flink 集成）"),
    ("support", "支撑主线 · 存储内部（8 条能力域）"),
]

# ===================================================================== #
# 一·b、项目总架构图 = 唯一导航底图 —— 热区注册表（决定"点击下钻"）
#   坐标系 = 该总架构 SVG 的 viewBox（ARCH_W×ARCH_H），生成期换算成百分比定位。
#   两条覆盖铁律：① 图上每个模块都有热区 ② 每条主线都被某热区覆盖。
# ===================================================================== #
PANO_NAME = "Fluss原理_全景主线框架"
ARCH_W, ARCH_H = 1040, 750  # 必须与 ARCH_SVG_NAME 的 viewBox 一致
# (x, y, w, h, 主线name) —— 一个模块可拆多行热区，一条主线可被多个区域指向
ARCH_HOTSPOTS = [
    # 顶部标题条 → 全景总览
    (30, 16, 980, 30, "Fluss原理_全景主线框架"),
    # ① 客户端 / 引擎接触面
    (48, 90, 300, 52, "Fluss原理_接触面_表模型与写入"),
    (364, 90, 300, 52, "Fluss原理_接触面_读取Lookup与Scan"),
    (680, 90, 312, 52, "Fluss原理_接触面_Flink与Lakehouse集成"),
    # ② RPC 网络层
    (30, 160, 980, 34, "Fluss原理_支撑_网络RPC与安全"),
    # ③ CoordinatorServer（标题条 + 三格）
    (30, 212, 980, 26, "Fluss原理_支撑_协调器元数据与调度"),
    (48, 240, 300, 34, "Fluss原理_支撑_协调器元数据与调度"),
    (364, 240, 300, 34, "Fluss原理_支撑_副本复制与ISR"),
    (680, 240, 312, 34, "Fluss原理_支撑_分层存储与Lakehouse"),
    # ④ TabletServer（header + Replica 内 log/KV/Arrow 列 + ISR 条）
    (30, 298, 980, 26, "Fluss原理_支撑_副本复制与ISR"),
    (72, 386, 424, 62, "Fluss原理_支撑_Log追加存储引擎"),
    (524, 386, 452, 62, "Fluss原理_支撑_KV主键表与changelog"),
    (72, 456, 424, 44, "Fluss原理_支撑_Arrow列存与投影下推"),
    (72, 512, 904, 60, "Fluss原理_支撑_副本复制与ISR"),
    # ⑤ 分层存储（标题条 + 三格）
    (30, 616, 980, 26, "Fluss原理_支撑_分层存储与Lakehouse"),
    (48, 648, 300, 66, "Fluss原理_支撑_分层存储与Lakehouse"),
    (364, 648, 300, 66, "Fluss原理_支撑_KV快照与恢复"),
    (680, 648, 312, 66, "Fluss原理_支撑_分层存储与Lakehouse"),
]
# 没有独立架构区域、需底部 chip 兜底的主线（本项目 12 主线全部落在图上 → 空）
ARCH_ALWAYS_CHIP = []

BRAND_SUB = "Apache Fluss"
HOME_DESC = ("Apache Fluss 核心原理设计文档库的离线交互图谱——面向 Flink 的流式湖仓存储"
             "（介于消息/事件流平台与分布式存储之间：Table API 接触面、桶副本上的追加日志 + KV 物化、副本 ISR 容错、ZooKeeper 协调、本地到湖仓的分层存储）。"
             "12 条主线、33 张手绘原理图，全部回本地源码核实。点击项目总架构图任意模块即可下钻到对应主线。")
ARCH_SVG_NAME = "Fluss原理_全景_02总架构.svg"

# 非"逐图走查"图（项目图标等），不计入孤儿/缺失统计
_NON_WALK_SVG = {"icon.svg"}

# ===================================================================== #
# 二、md 解析 —— 从每篇 design 文档抽取结构化内容
# ===================================================================== #
def _read(fname):
    p = os.path.join(_DESIGN_DIR, fname)
    if not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def _b64_svg(fname):
    p = os.path.join(_DESIGN_DIR, fname)
    if not os.path.isfile(p):
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _md_inline(s):
    """行内 markdown → HTML：先 bold 再 code（否则 code 里的 * 破坏 bold）。"""
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _parse_md_table(body):
    """markdown 表 → (headers, rows)。识别 | a | b | 形式，跳过 |---| 分隔行。"""
    lines = [l.strip() for l in body.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return None

    def cells(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]
    headers = cells(lines[0])
    rows = []
    for l in lines[1:]:
        if re.match(r"^\|?[\s:\-|]+\|?$", l):  # 分隔行
            continue
        rows.append(cells(l))
    return (headers, rows) if rows else None


def parse_doc(fname):
    """把一篇 design md 解析成图谱所需结构。"""
    t = _read(fname)
    h1 = re.search(r"^#\s+(.+)$", t, re.M)
    title = h1.group(1).strip() if h1 else fname

    # 定位 blockquote
    loc = re.search(r">\s*\*\*定位\*\*[：:]\s*(.+)", t)
    position = loc.group(1).strip() if loc else ""

    # 章节 → 紧跟其后的 SVG（逐图走查序）
    walk = []
    for m in re.finditer(r"##\s*([^\n]+?)\s*\n+!\[([^\]]*)\]\(([^)]+\.svg)\)", t):
        sec, alt, svg = m.group(1).strip(), m.group(2).strip(), os.path.basename(m.group(3))
        walk.append((sec, alt, svg))
    # 兜底：把所有引用到但未被 ## 捕获的 svg 也补进来（保证 0 缺图）
    seen = {w[2] for w in walk}
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+\.svg)\)", t):
        svg = os.path.basename(m.group(2))
        if svg not in seen:
            walk.append((m.group(1).strip() or svg, m.group(1).strip(), svg))
            seen.add(svg)

    # 调优要点 / 常见误区 bullets
    def bullets(header):
        m = re.search(r"##\s*" + header + r"[^\n]*\n(.*?)(?=\n##|\Z)", t, re.S)
        if not m:
            return []
        return [_md_inline(x.group(1).strip())
                for x in re.finditer(r"^-\s+(.+)$", m.group(1), re.M)]
    tuning = bullets("调优要点")
    pitfalls = bullets("常见误区")

    # 深化/拓展/补充 章节里的对比表
    tables = []
    for m in re.finditer(r"##\s*((?:深化|拓展|补充)[^\n]*)\n(.*?)(?=\n##|\Z)", t, re.S):
        cap = re.sub(r"^[·\s]*(深化|拓展|补充)\s*·?\s*", "", m.group(1)).strip()
        parsed = _parse_md_table(m.group(2))
        if parsed:
            tables.append((cap, parsed[0], parsed[1]))

    # 一句话总纲
    one = re.search(r"一句话总纲.*?\n+\*\*(.+?)\*\*", t, re.S)
    summary = one.group(1).strip() if one else ""

    return dict(title=title, position=position, walk=walk,
                tuning=tuning, pitfalls=pitfalls, tables=tables, summary=summary)


DOCS = {name: parse_doc(name + ".md") for (name, *_rest) in MAINLINES}

# 引用闭环校验（0 缺失 / 0 孤儿）——生成期打印，异常早暴露
_all_refs = set()
for d in DOCS.values():
    for _, _, svg in d["walk"]:
        _all_refs.add(svg)
_on_disk = {f for f in os.listdir(_DESIGN_DIR)
            if f.endswith(".svg") and f not in _NON_WALK_SVG}
_missing = _all_refs - _on_disk
_orphan = _on_disk - _all_refs

# ===================================================================== #
# 三、HTML 片段构建
# ===================================================================== #
def esc(s):
    return html.escape(s or "")


def build_archnav():
    """首页唯一导航：项目总架构图 (ARCH_SVG_NAME) 底图 + 透明热区叠加。
    每个语义模块 = 一个 .arch-hot 区域，点击下钻对应主线；未覆盖主线兜底成 chip。"""
    meta = {name: (ico, ctitle, sub) for name, _c, ico, ctitle, sub in MAINLINES}
    if not _ARCH_SVG:
        return '<p style="color:var(--c-ink2)">（缺项目总架构图 %s）</p>' % esc(ARCH_SVG_NAME)
    hots = []
    for (x, y, w, h, mid) in ARCH_HOTSPOTS:
        if mid not in meta:
            print("  ⚠ 热区指向不存在的主线:", mid)
            continue
        _ico, title, _s = meta[mid]
        hots.append(
            '<button class="arch-hot" data-mid="{mid}" aria-label="{title}"'
            ' style="left:{l:.3f}%;top:{t:.3f}%;width:{w:.3f}%;height:{ht:.3f}%">'
            '<span class="ah-tag">{ico} {title}</span></button>'.format(
                mid=esc(mid), title=esc(title), ico=esc(_ico),
                l=x / ARCH_W * 100, t=y / ARCH_H * 100,
                w=w / ARCH_W * 100, ht=h / ARCH_H * 100))
    covered = {mid for (*_r, mid) in ARCH_HOTSPOTS}
    chip_names = [n for (n, *_r) in MAINLINES if n not in covered] + \
                 [n for n in ARCH_ALWAYS_CHIP if n not in covered]
    chips = ""
    if chip_names:
        seen, items = set(), []
        for n in chip_names:
            if n in seen or n not in meta:
                continue
            seen.add(n)
            ico, title, _s = meta[n]
            items.append('<button class="arch-chip" data-mid="{mid}">{ico} {title}</button>'
                         .format(mid=esc(n), ico=esc(ico), title=esc(title)))
        chips = ('<div class="arch-chips" aria-label="未在架构图上单独描绘的主线">%s</div>'
                 % "".join(items))
    return (
        '<div class="arch-wrap">'
        '<img alt="Apache Fluss 项目总架构图" src="data:image/svg+xml;base64,%s"/>'
        '%s</div>%s' % (_ARCH_SVG, "".join(hots), chips))



def build_panes():
    """每条主线一个 pane：左垂直图索引 + 右主内容（SVG 逐图 + 定位/总纲/调优/误区/表）。"""
    panes = []
    for name, _cat, _ico, ctitle, _sub in MAINLINES:
        d = DOCS[name]
        idx = "".join(
            '<button class="walk-tab" data-mid="{mid}" data-idx="{i}">'
            '<span class="wt-n">{n2}</span><span class="wt-t">{sec}</span></button>'.format(
                mid=esc(name), i=i, n2=i + 1, sec=esc(sec))
            for i, (sec, _a, _s) in enumerate(d["walk"]))
        figs = []
        for i, (sec, alt, svg) in enumerate(d["walk"]):
            b64 = _b64_svg(svg)
            figs.append(
                '<figure class="walk-fig" data-mid="{mid}" data-idx="{i}">'
                '<figcaption class="walk-cap"><span class="wc-n">{n2}</span>{sec}</figcaption>'
                '<img class="walk-img" loading="lazy" alt="{alt}" '
                'src="data:image/svg+xml;base64,{b64}"/>'
                '</figure>'.format(mid=esc(name), i=i, n2=i + 1,
                                   sec=esc(sec), alt=esc(alt or sec), b64=b64))
        tips = []
        if d["position"]:
            tips.append('<div class="tip-pos"><span class="tip-k">定位</span>%s</div>'
                        % _md_inline(d["position"]))
        if d["summary"]:
            tips.append('<div class="tip-sum"><span class="tip-k">一句话总纲</span>%s</div>'
                        % _md_inline(d["summary"]))
        cols = []
        if d["tuning"]:
            cols.append('<div class="tip-col"><div class="tip-h">调优要点</div><ul>%s</ul></div>'
                        % "".join("<li>%s</li>" % b for b in d["tuning"]))
        if d["pitfalls"]:
            cols.append('<div class="tip-col"><div class="tip-h">常见误区</div><ul>%s</ul></div>'
                        % "".join("<li>%s</li>" % b for b in d["pitfalls"]))
        if cols:
            tips.append('<div class="tip-cols">%s</div>' % "".join(cols))
        for cap, headers, rows in d["tables"]:
            thead = "".join("<th>%s</th>" % _md_inline(h) for h in headers)
            tbody = "".join(
                "<tr>" + "".join("<td>%s</td>" % _md_inline(c) for c in r) + "</tr>"
                for r in rows)
            tips.append('<div class="tip-tbl"><div class="tip-h">%s</div>'
                        '<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                        % (esc(cap), thead, tbody))
        panes.append(
            '<section class="pane" data-mid="{mid}">'
            '<div class="pane-head"><h2>{title}</h2></div>'
            '<div class="pane-body">'
            '<nav class="walk-idx">{idx}</nav>'
            '<div class="walk-main">{figs}<div class="walk-tips">{tips}</div></div>'
            '</div></section>'.format(
                mid=esc(name), title=esc(d["title"]), idx=idx,
                figs="".join(figs), tips="".join(tips)))
    return "\n".join(panes)


_ARCH_SVG = _b64_svg(ARCH_SVG_NAME)

# ===================================================================== #
# 四、页面模板（CSS + JS 内联，双主题 graphite/light）
# ===================================================================== #
CSS = r"""
:root{
  --c-bg:#0d0d0f; --c-card:#17171a; --c-card2:#1e1e22; --c-ink:#f2f2f5;
  --c-ink2:#a1a1a6; --c-ink3:#6e6e73; --c-border:#2a2a30; --c-edge:#33333a;
  --c-brand:#f5b301; --c-brand2:#ffcf33; --c-amber:#ff9f0a; --c-green:#30d158;
  --c-red:#ff453a; --c-purple:#bf5af2; --c-shadow:rgba(0,0,0,.5);
}
html[data-theme="light"]{
  --c-bg:#fbfbfd; --c-card:#ffffff; --c-card2:#f5f5f7; --c-ink:#1d1d1f;
  --c-ink2:#6e6e73; --c-ink3:#a1a1a6; --c-border:#e6e6ea; --c-edge:#d2d2d7;
  --c-brand:#b26a00; --c-brand2:#d98a00; --c-amber:#b25e00; --c-green:#1d8f3f;
  --c-red:#c4341c; --c-purple:#8944ab; --c-shadow:rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--c-bg);color:var(--c-ink);
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;
  font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
header{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:14px;
  padding:12px 22px;background:color-mix(in srgb,var(--c-bg) 82%,transparent);
  backdrop-filter:saturate(160%) blur(14px);border-bottom:1px solid var(--c-border)}
.logo{display:flex;align-items:center;gap:9px;cursor:pointer;font-weight:700;font-size:15px;text-decoration:none;color:inherit}
.logo:hover .homeico{color:var(--c-brand)}
.homeico{display:inline-flex;color:var(--c-ink2);transition:color .15s}
.logo .dot{width:11px;height:11px;border-radius:3px;background:linear-gradient(135deg,var(--c-brand),var(--c-amber))}
.logo .sub{font-weight:500;color:var(--c-ink2);font-size:12px}
.spacer{flex:1}
.hbtn{border:1px solid var(--c-border);background:var(--c-card);color:var(--c-ink2);
  border-radius:9px;padding:6px 12px;cursor:pointer;font-size:12.5px;transition:.15s}
.hbtn:hover{color:var(--c-ink);border-color:var(--c-edge)}
.wrap{max-width:1180px;margin:0 auto;padding:30px 22px 80px}
.navmap-hint{color:var(--c-ink3);font-size:12px;margin:18px 2px 0;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.navmap-hint b{color:var(--c-brand);font-weight:700}
.arch-wrap{position:relative;margin-top:12px;background:var(--c-card);border:1px solid var(--c-border);border-radius:16px;padding:14px;overflow:hidden}
.arch-wrap img{width:100%;display:block;border-radius:8px}
html:not([data-theme="light"]) .arch-wrap img{filter:invert(.92) hue-rotate(180deg) saturate(.85)}
.arch-hot{position:absolute;border:0;background:transparent;cursor:pointer;padding:0;border-radius:6px;transition:.12s;z-index:2}
.arch-hot:hover,.arch-hot:focus-visible{background:color-mix(in srgb,var(--c-brand) 14%,transparent);outline:2px solid var(--c-brand);outline-offset:-1px}
.arch-hot:focus{outline:2px solid var(--c-brand)}
.ah-tag{display:none;position:absolute;left:3px;top:3px;white-space:nowrap;background:var(--c-brand);color:#fff;font-size:11px;font-weight:600;padding:3px 8px;border-radius:6px;box-shadow:0 3px 10px var(--c-shadow);pointer-events:none;z-index:3}
.arch-hot:hover .ah-tag,.arch-hot:focus-visible .ah-tag{display:block}
.arch-chips{display:flex;flex-wrap:wrap;gap:9px;margin-top:14px}
.arch-chip{border:1px solid var(--c-border);background:var(--c-card2);border-radius:9px;padding:7px 12px;cursor:pointer;font-size:12px;transition:.15s;color:inherit}
.arch-chip:hover{border-color:var(--c-brand);color:var(--c-brand)}
.pane{display:none}
.pane.on{display:block}
.pane-head{display:flex;align-items:center;gap:12px;margin:6px 0 16px}
.pane-head h2{font-size:20px;font-weight:800;letter-spacing:-.3px}
.pane-body{display:grid;grid-template-columns:230px 1fr;gap:22px;align-items:start}
.walk-idx{position:sticky;top:78px;display:flex;flex-direction:column;gap:4px;max-height:calc(100vh - 100px);overflow:auto;padding-right:4px}
.walk-tab{display:flex;gap:9px;align-items:flex-start;text-align:left;cursor:pointer;
  background:transparent;border:1px solid transparent;border-radius:9px;padding:8px 10px;color:var(--c-ink2);font-size:12.3px;transition:.14s;line-height:1.45}
.walk-tab:hover{background:var(--c-card2);color:var(--c-ink)}
.walk-tab.on{background:var(--c-card);border-color:var(--c-brand);color:var(--c-ink)}
.wt-n{flex:none;width:19px;height:19px;border-radius:6px;background:var(--c-card2);color:var(--c-ink3);
  font-size:10.5px;font-weight:700;display:flex;align-items:center;justify-content:center}
.walk-tab.on .wt-n{background:var(--c-brand);color:#fff}
.walk-main{min-width:0}
.walk-fig{display:none;background:var(--c-card);border:1px solid var(--c-border);border-radius:16px;padding:14px 14px 16px;margin-bottom:18px}
.walk-fig.on{display:block}
.walk-cap{display:flex;align-items:center;gap:9px;font-weight:700;font-size:13.5px;margin-bottom:12px}
.wc-n{width:22px;height:22px;border-radius:7px;background:var(--c-brand);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
.walk-img{width:100%;display:block;border-radius:9px;background:#fbfbfd}
html:not([data-theme="light"]) .walk-img{filter:invert(.92) hue-rotate(180deg) saturate(.85)}
.walk-tips{margin-top:6px}
.tip-pos{border:1px dashed var(--c-edge);border-radius:12px;padding:12px 15px;color:var(--c-ink2);font-size:12.8px;margin-bottom:12px}
.tip-sum{border:1px solid var(--c-brand);background:color-mix(in srgb,var(--c-brand) 8%,transparent);
  border-radius:12px;padding:13px 15px;font-size:13px;margin-bottom:14px;line-height:1.65}
.tip-k{display:inline-block;font-weight:700;color:var(--c-brand);margin-right:8px;font-size:11.5px;
  text-transform:uppercase;letter-spacing:.5px}
.tip-cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:820px){.tip-cols{grid-template-columns:1fr}.pane-body{grid-template-columns:1fr}.walk-idx{position:static;flex-direction:row;flex-wrap:wrap;max-height:none}}
.tip-col{background:var(--c-card);border:1px solid var(--c-border);border-radius:12px;padding:13px 15px}
.tip-h{font-weight:700;font-size:12.5px;margin-bottom:8px;color:var(--c-ink)}
.tip-col ul,.tip-tbl+.tip-tbl{margin:0}
.tip-col li{list-style:none;padding:5px 0 5px 15px;position:relative;color:var(--c-ink2);font-size:12.3px;line-height:1.55;border-top:1px solid var(--c-border)}
.tip-col li:first-child{border-top:0}
.tip-col li:before{content:"";position:absolute;left:2px;top:12px;width:5px;height:5px;border-radius:50%;background:var(--c-brand)}
.tip-tbl{background:var(--c-card);border:1px solid var(--c-border);border-radius:12px;padding:13px 15px;margin-bottom:14px;overflow:auto}
.tip-tbl table{width:100%;border-collapse:collapse;font-size:12px}
.tip-tbl th{text-align:left;font-weight:700;color:var(--c-ink);padding:7px 9px;border-bottom:1.5px solid var(--c-edge);background:var(--c-card2)}
.tip-tbl td{padding:7px 9px;border-bottom:1px solid var(--c-border);color:var(--c-ink2);vertical-align:top}
.tip-tbl td:first-child{font-weight:600;color:var(--c-ink)}
.tip-tbl tr:nth-child(even) td{background:color-mix(in srgb,var(--c-card2) 50%,transparent)}
code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:.9em;background:var(--c-card2);
  border:1px solid var(--c-border);border-radius:5px;padding:1px 5px;color:var(--c-brand)}
b{color:var(--c-ink);font-weight:700}
.back{display:none;margin-bottom:12px}
.back.on{display:inline-flex}
#lo{position:fixed;inset:0;z-index:100;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:16px;background:var(--c-bg);transition:opacity .4s}
#lo.hide{opacity:0;visibility:hidden}
#lo .lo-logo{width:46px;height:46px;border-radius:13px;background:linear-gradient(135deg,var(--c-brand),var(--c-amber));animation:pulse 1.4s ease-in-out infinite}
#lo .lo-t{font-weight:800;font-size:17px}
#lo .lo-s{color:var(--c-ink2);font-size:12.5px}
#lo .lo-bar{width:180px;height:3px;border-radius:2px;background:var(--c-card2);overflow:hidden}
#lo .lo-bar i{display:block;width:40%;height:100%;background:var(--c-brand);animation:slide 1.1s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media(prefers-reduced-motion:reduce){#lo .lo-logo,#lo .lo-bar i{animation:none}}
"""

APP_JS = r"""
(function(){
  var root=document.documentElement;
  var saved=localStorage.getItem('fluss-atlas-theme');
  if(saved) root.setAttribute('data-theme',saved);
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='light'?'':'light';
    if(cur) root.setAttribute('data-theme',cur); else root.removeAttribute('data-theme');
    localStorage.setItem('fluss-atlas-theme',cur);
    var b=document.getElementById('themeBtn'); if(b) b.textContent=cur==='light'?'☀':'☾';
  }
  var tb=document.getElementById('themeBtn');
  if(tb){tb.onclick=toggleTheme; tb.textContent=root.getAttribute('data-theme')==='light'?'☀':'☾';}

  var home=document.getElementById('home'), panes=document.getElementById('panes');
  function showHome(){home.style.display='block';panes.style.display='none';
    document.querySelectorAll('.pane').forEach(function(p){p.classList.remove('on')});
    window.scrollTo(0,0);}
  function openMain(mid,idx){
    home.style.display='none';panes.style.display='block';
    document.querySelectorAll('.pane').forEach(function(p){p.classList.toggle('on',p.dataset.mid===mid)});
    selFig(mid, idx||0);
    window.scrollTo(0,0);
  }
  function selFig(mid,idx){
    document.querySelectorAll('.walk-fig[data-mid="'+mid+'"]').forEach(function(f){
      f.classList.toggle('on', +f.dataset.idx===idx);});
    document.querySelectorAll('.walk-tab[data-mid="'+mid+'"]').forEach(function(t){
      t.classList.toggle('on', +t.dataset.idx===idx);});
  }
  document.addEventListener('click',function(e){
    var ah=e.target.closest('.arch-hot'); if(ah){openMain(ah.dataset.mid,0);return;}
    var ac=e.target.closest('.arch-chip'); if(ac){openMain(ac.dataset.mid,0);return;}
    var wt=e.target.closest('.walk-tab'); if(wt){selFig(wt.dataset.mid,+wt.dataset.idx);return;}
    // logo is now a link to portal (../index.html); no JS intercept
    var bk=e.target.closest('#back2'); if(bk){showHome();return;}
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ')return;
    var ah=e.target.closest('.arch-hot,.arch-chip'); if(ah){e.preventDefault();openMain(ah.dataset.mid,0);}
  });
  showHome();
  function done(){var lo=document.getElementById('lo');if(lo){lo.classList.add('hide');setTimeout(function(){if(lo&&lo.parentNode)lo.parentNode.removeChild(lo);},500);}}
  requestAnimationFrame(function(){requestAnimationFrame(function(){setTimeout(done,120);});});
  setTimeout(done,4000);
})();
"""


def build_html():
    archnav = build_archnav()
    # 导航一致性校验：每条主线要么被某热区覆盖、要么进兜底 chip，否则在架构图入口失联
    covered = {mid for (*_r, mid) in ARCH_HOTSPOTS} | set(ARCH_ALWAYS_CHIP)
    unmapped = [n for (n, *_r) in MAINLINES if n not in covered]
    if unmapped:
        print("  ⚠ 架构图上失联的主线(既无热区又无 chip):", unmapped)

    total_svg = len(_on_disk)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{sub} · 原理图谱</title>
<style>{css}</style>
</head>
<body>
<div id="lo" role="status" aria-live="polite">
  <div class="lo-logo"></div>
  <div class="lo-t">{sub}</div>
  <div class="lo-s">正在装载 {n} 张原理图</div>
  <div class="lo-bar"><i></i></div>
  <div class="lo-s" style="font-size:11px;opacity:.7">短暂空白属正常装载，非内容缺失</div>
</div>
<header>
  <a class="logo" id="logo" href="../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a>
  <div class="spacer"></div>
  <a href="https://github.com/apache/fluss" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://fluss.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjRTY1MjZGIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+QXBhY2hlIEZsaW5rPC90aXRsZT48cGF0aCBkPSJNMy4xOTIgMTMuMjM2Yy4wMjguMDM1LjA2NC4wNjkuMDk4LjEwMWwuMDI0LjAyMi4wMDguMDA0YS43MzYuNzM2IDAgMCAwIC4xNzkuMDY1IDguMTE3IDguMTE3IDAgMCAxLS4xMzgtMS43NThjLjAyNy0uNzk3LjE3OC0xLjQ3LjQ2Mi0yLjA1OWE4LjAyIDguMDIgMCAwIDEgLjMxNS0uNTE5cy0uMTc2IDEuMjAyLS4yMDIgMS42NzNhNy4xMDQgNy4xMDQgMCAwIDAgLjE2IDEuODY4bC4wNzItLjA1Yy0uMDQzLS4zODktLjA0Mi0uOC4wMDQtMS4yMmE2Ljk4NyA2Ljk4NyAwIDAgMSAuNDE5LTEuNzIxIDkuMjY2IDkuMjY2IDAgMCAxIC45NzMtMS44OTJjLTEuOTg1LjIwOS0yLjQxOCAyLjEtMi40MTggMi4xcy4wMTctLjM0Ny4wMjQtLjQzNGMuMDU3LS42NDkuMTIzLS45NjEuMjA1LTEuMjg3LS4xMy4yMzgtLjIxMi40ODgtLjI3MS42ODgtLjEzOS40Ny0uMjE2Ljk0OS0uMjczIDEuMzU2YTkuMDIyIDkuMDIyIDAgMCAwLS4wOTYgMS4yODljLjAwMi4zOC4wMjQuODI4LjE3NiAxLjI2My4wNzMuMjA1LjE2NC4zNzMuMjc5LjUxMXptMS40NC0uNzM3Yy4xNzktLjExMy4zODUtLjIuNjI2LS4yNjguNDI1LS4xMTkuODg5LS4yMzkgMS40NjEtLjM3OWwuMTktLjA0NmMuNDc4LS4xMTYuOTc0LS4yMzcgMS40MzktLjQxNS4yODMtLjEwOC41NTItLjI1LjgyNC0uNDM2LjM4LS4yNi43MjEtLjU3OSAxLjAxMi0uOTUxLjE1NC0uMTk2LjIzMi0uMzQ5LjMwOS0uNjA1bC4xMTQtLjM3OHMuNDY0LjUxOS0uMDA0IDEuNDM2Yy4yOTctLjEwNy41ODItLjQxMy43OTgtLjc4OC4xODEtLjMxNS40OTEtMS40NTEuNDkxLTEuNDUxcy41NjkuODc1LS4xMDUgMi4wMTFhMS41OSAxLjU5IDAgMCAwIC4zNTYtLjIyN2MyLjUwNy0yLjQ5LjM0OS0zLjg5OS0uMTAzLTQuMjM2YTQuMTQxIDQuMTQxIDAgMCAwLS45ODItLjUyNUwxMSA1LjIxOGMtLjAzLS4wMTMtLjA0Ny0uMDMzLS4wNTUtLjA0MmwtLjMyMS0uMzUuNTYzLjE1NWMuMDc5LjAyMS4xNTQuMDQyLjIyOC4wNjQuNjE0LjE4MiAxLjA4Mi40IDEuNDcyLjY4Ni40NDUuMzI1IDIuMTQyIDEuNzUxLjM0OCAzLjgzNy41NTYtLjE5MSAxLjYwNi0uNzcyIDEuOTYyLTEuMjcyIDEuNzEzLTIuNDA1LS4yNTQtMy44MDgtLjE3LTMuODA4LjAxOSAwIC4wNDQuMDAyLjA5OS4wMWEuNDQuNDQgMCAwIDAgLjA2OS4wMDZjLjAzNiAwIC4wOTctLjAwNi4xMDktLjA0MS4wMTUtLjA0Mi0uMDE0LS4xMjItLjA3My0uMTY4LS4xNTQtLjExNy0uMzIxLS4yMDItLjUzMy0uMTY5QzEyLjkyNiA0LjQgMTIuMyAzLjg1IDEyLjMgMy44NXMyLjQ4Mi4xMjkgMi41NjItLjI4YTQuOTIgNC45MiAwIDAgMC0xLjIyNS0uOTEyIDYuNjk3IDYuNjk3IDAgMCAwLTIuMjI4LS43NDNjLTEuMjA3LS4xNzktMi4xMy4wNTMtMi4xMy4wNTMuMDk2LS4xMjEuNTc0LS42NjcgMi41NTYtLjUxMS44MDIuMDYzIDEuNTY0LjMxNiAyLjI3LjY2OS4xODIuMDkxLjI5LS4xMjUuMjkzLS4yMjMuMDA0LS4xMTQuMjAxLjM3OS4yMDMuNDA1LjAxOS0uMDQ5LjA5Ni0uMzA4LjExMi0uMzA4LjA0NyAwIC4yNC42MDMuMjQuNjAzLjAwMi0uMDI0LjI1Ny0uMjg2LjI1Ny0uMjg2LjA3Ni4zNDMuMDY2LjUxNC4wNDcuNTYyLjAwMi0uMDA5LjI2Ny0uMTcyLjI2Ny0uMTcycy4xNTIuNjM4LjQxMi44OTFjLjA4NC4wODIuMjM4LjI5Ni4zMjguNTI3LjE5LS4xMzMuNDIxLS43OTkuNDIxLS43OTlzLjExOS4zNTMuMDE5Ljk4OGMuMDA3LS4wMDguMzAxLS4yMTkuMzAxLS4yMTlzLjA0Mi40NDktLjE1IDEuMDA4YS41NzIuNTcyIDAgMCAwLS4wMjIuMDk1Yy4xNjItLjA5MS40MDQtLjM4OC40MDQtLjM4OGwtLjA0Mi4xODhjLS4wNDguMjE0LS4xMzcuNjI5LS4zMjcuOTUzYTIuNTQ5IDIuNTQ5IDAgMCAwLS4yOS42ODZjLjA0OS0uMDQ1LjA5OS0uMDg1LjE1Mi0uMTIuMS0uMDY1LjE5OS0uMTE3LjI5My0uMTUxbC4yMzItLjA4NWMuMzkyLS4xNDIuNzg4LS4zMDkgMS4xNzMtLjQ3OS44MTItLjM1OS42MzEtLjg2LjYzMS0uODYtLjIwOS40MDgtLjk2Ni44MTYtLjk2Ni44MTZzLjk4LS44NzguNTYyLTEuOTA1Yy0uMTE1LjI3LS4yMjQuNTM4LS4zMjcuNzkyLS4xNDQuMzUzLS4zMTQuNzI2LS41OSAxLjA1NS0uMTQxLjE2OC0uMjg2LjI5LS40NDYuMzczYS42ODYuNjg2IDAgMCAxLS4xMTUuMDQ4bC0uMDQzLjAxNnMuMTcyLS4yODMuMTg0LTEuMDYzYy4wMDQtLjI4Mi4wMTItLjU3MS4wMTItLjgyNnYtLjA1NGMwLS4xMzItLjAwMy0uMjYzLS4wMDItLjM5NS4wMDUtLjU1OC4wMTUtLjk4Mi4xMzItMS4zNzMtLjAxMi0uMDIyLS4wMDUtLjA0NS0uMDE4LS4wNjgtLjAyNy0uMDQ2LS4wNDctLjA5OS0uMDcxLS4xNTctLjAzNi0uMDg5LS4wNjYtLjE3OC0uMTAxLS4yNzUtLjEyNy0uMzYtLjMwOC0uNTM4LS4zNjUtLjU4OC0uMDM4LjExNS0uMjcxLjU5MS0uMjcxLjU5MXMuMDAxLS4zNjUtLjAwMS0uMzkzYy0uMDY3LS41MTEtMS4zMy0uOTcyLTEuMzU2LS45ODhsLjA2Ny40MDFzLS4zODItLjAyOC0uNTQ1LS4yODRjLS4wMzQtLjA1Mi0uMDg0LS4wOS0uMTMtLjEyNWwuMDkuMzA2LjA5My4yMTRzLS4yOTYtLjAyNC0uNDM1LS4yNjljLS4wMzMtLjA1Ny0uMDc1LS4xMjEtLjExMi0uMTg5YS43NDYuNzQ2IDAgMCAwLS41NzQtLjM5NiA4LjM5MyA4LjM5MyAwIDAgMC0uNjAxLS4wNjIgMS4zMDEgMS4zMDEgMCAwIDEtLjQ3OS0uMTFMMTIuNTczIDBsLjA0Ni4wODdjLjAxNS4wMjkuMDI1LjA1OC4wNC4wOTVsLjAwOC4wMjIuMDMyLjA3OC4wNDguMTcycy0uMzUzLS4wMTQtLjc2NS0uMjk5Yy0uMDg5LS4wNjItLjIwMS0uMDYyLS4zMjUtLjA3MkwxMS42MjIuMDhhNC4xOTIgNC4xOTIgMCAwIDAtLjMzMi0uMDE0IDMuMDk3IDMuMDk3IDAgMCAwLS45NzQuMTQ5Yy4wMzUtLjAwMi4wNzEtLjAwMy4xMDYtLjAwM2wuMDY3LjAwMWMuNjc3LjAxMi44ODcuNDEzLjg4Ny40MTNzLS42MDYgMC0uNzg1LjAyM2MtLjIwOS4wMjctLjQyLjA1Mi0uNjE2LjEwNmE1LjEwMiA1LjEwMiAwIDAgMC0xLjYyMi43OTZjLS4xMjQuMDg4LS4yNTMuMTctLjM4OS4yNTYtLjIzLjE0Ny0uNDI0LjM0MS0uNTc2LjU3N2EuMzU3LjM1NyAwIDAgMC0uMDM0LjA2OGMtLjAxNC4wMzYtLjAwOC4wMzkuMDE1LjA1MWEuNzguNzggMCAwIDAgLjE2OC4wNjEgMi4zNTMgMi4zNTMgMCAwIDEgMS43ODYgMi4wMDVsLjAxNS4xMjNjLjAzNS4zMDcuMDcyLjYyMy4wNTYuOTQ0YTMuNDEzIDMuNDEzIDAgMCAxLS45MDEgMi4xOTFjLS41OS42NDYtMS4zMjMuNjktMS4zMTYuNjg1LjQzNS0uNDA2LjcyMi0uOTUuODc2LTEuNjZhMS4zOTUgMS4zOTUgMCAwIDAtLjA4NC0uODI4Ljg2OC44NjggMCAwIDAtLjAxNi4wNDdjLS4wOTcuMjc2LS4yMi41OTQtLjQ0Ny44NTctLjEzMi4xNS0uMzEyLjMyMi0uNTIxLjUyMS0uOTExLjg2Ny0yLjQzNSAyLjMxNy0yLjQwOSA0LjYyMyAwIC4xMzUuMDI3LjMuMDU2LjQyN3ptMTMuOTY3LTUuODM2Yy0uMTEzLjA5OC0uMjI2LjE5Ni0uMzQxLjI5Mi0uMjA1LjE3MS0uMzUxLjI4LS42NjYuMzk0LS4yNzYuMDk5LS40ODgtLjEyNC0uNDg4LS4xMjRhMS4zIDEuMyAwIDAgMCAuNDQ3LS4zODkgNy45NjggNy45NjggMCAwIDAtMS4xNTQuNzEgMi40MSAyLjQxIDAgMCAwLS4zODkuMzUzYy0uMTI0LjE1Ni0uMjA1LjMxOC0uMjA1LjQ4NHYuMDAyYzAtLjAwMy4wNDQtLjAwNS4wNTMtLjAwN2E2LjEyMiA2LjEyMiAwIDAgMCAxLjIyNi0uNDkgMTYuMDA2IDE2LjAwNiAwIDAgMCAxLjc1Ny0xLjA3NC4zMzQuMzM0IDAgMCAxIC4wOTUtLjA0OGwuMzcxLS4xMDYtLjIyOC4zMTRhLjI4OC4yODggMCAwIDEtLjAyNy4wMzRjLS43NDUuNzQxLTEuNTE3IDEuMjcyLTIuMzYgMS42MjJhNC43MzQgNC43MzQgMCAwIDEtLjQ5Mi4xNzQgOS4yMDEgOS4yMDEgMCAwIDAgMS41MTMtLjUyNWMuNTM3LS4yNDQuOTEzLS40ODMgMS4yMi0uNzcyLjQ3NS0uNDUuODE0LS45ODEgMS4wMDktMS41NzZhLjczMi43MzIgMCAwIDAgLjAyNC0uMWwtLjExMS4wMzNjLS4xMjcuMDM3LS4yNTguMDc0LS4zNzMuMTNhMi4zNjcgMi4zNjcgMCAwIDAtLjQyNy4yODZjLS4xNTguMTI3LS4zMjEuMjY5LS40NTQuMzgzek0xLjU3OCAxNC45ODdjLjEyOC4yMDUuMjY4LjQwNy40MDMuNjAybC4wMjEuMDMxYy0uMzUxLTEuMjM2LjIyMy0xLjk4Mi4yMjMtMS45ODJsLjE0Mi4zOTFjLjAzNi4xMDEuMDkxLjE5OS4xNjcuMzAyLjE0Ny0uMjc1LjMyNi0uNTM4LjUzNC0uNzg0YTEuNDM4IDEuNDM4IDAgMCAxLS40NzItLjQxNWMtLjItLjI2NC0uMzMyLS41ODEtLjQxNS0uOTk2YTUuNTA3IDUuNTA3IDAgMCAxLS4wNjktMS41NjJjLjAxNS0uMTc0LjAzNi0uMzQ4LjA1OS0uNTI1YTguMzc3IDguMzc3IDAgMCAwLTEuNjI2IDIuNzE2LjA0Ni4wNDYgMCAwIDAgLjAwMy4wMjEgOS40MzggOS40MzggMCAwIDAgMS4wMyAyLjIwMXpNMTguMjIxIDMuMzUzYTUuMDQ1IDUuMDQ1IDAgMCAxIC4zNjYtMS45MzNsLjAxOC0uMDQxYS45NC45NCAwIDAgMC0uMjQ2LjI1MmMtLjE2OC4yNDItLjI5MS41My0uMzk3LjkzMi0uMTgyLjY4Ny0uMjkgMS40MjctLjMzNyAyLjMwOC4xOTItLjIwNS41MDctLjY1Ny41NzItMS4yMTUuMDExLS4wOTQuMDI0LS4xOTkuMDI0LS4zMDN6bTMuMzY4IDE5LjAxMmMtLjM5Ni0uMDY1LTEuMjM0LS4zNi0xLjQ2OC0uOTQ1LS4yODguNzA3LjMwNiAxLjIyMS43NSAxLjQ1MS4wNzcuMDQuMS4wNS4xODEuMDgyLjA4NC4wMzctLjE2NS40OTQuMDQ1LjcwNC4yMS4yMS40MDkuMTQ4LjQ4Ny4xNDggMCAwIC4zNjEuMzM1LjU2Ny4xMTEuMDUzLS4wNTguMDk4LS4yNjIuMDI5LS4zODUtLjA4Ni0uMTUyLS4yOTUtLjEyNC0uMzE1LS4xMjQtLjQxLjAwNS0uMzczLS4xODgtLjMxMS0uMjcuMDQ1LS4wNTkuMTMyLS4wNTUuMjA1LS4wNTUuMDE3IDAgLjAzNC4wMDEuMDUzLjAwNC4wOTQuMDExLjE4NC4wMTYuMjY4LjAxNi4zMzUgMCAuNzI2LS4wMzUuOTg1LS4xNzkuMTg2LS4xMDQuNDkxLS40NTYuNDc1LS42OTItLjAxNy4wMDYtLjgyNS4zMTktMS45NTEuMTM0em0yLjMyNC03Ljc4NWMtLjAzOC0uMDk3LS4wODUtLjE5Ni0uMTI2LS4yODNsLS4wNi0uMTI2Yy0uMDIxLS4wNDctLjA0NC0uMDkzLS4wNjYtLjEzOS0uMDU1LS4xMTEtLjExMi0uMjI2LS4xNTEtLjM1LS4wMzQtLjEwNi0uMDQzLS4yMTYtLjA1Mi0uMzJhMy4zMTIgMy4zMTIgMCAwIDAtMS44ODYtMi43MTYgMS4yNSAxLjI1IDAgMCAxLS4yMTUuNDE3Yy0uMDkuMTItLjE0NC4xMzgtLjI2Mi4xMzgtLjE1NyAwLS4xOC0uMTgtLjEzMy0uMjY1YTEuNDUgMS40NSAwIDAgMCAuMTk2LS41NDNjLjAzMy0uMzc3LS4xNzctLjc4Ni0uNDM1LTEuMDY4LS4yMzktLjI2MS0uNjQ5LS41NjQtLjk3OS0uNjYzLS4wNzkuMzA3LjAxNy44MTIuMTI0IDEuMTA5LjEzMi4zNi41NDQgMS4wNjkuNDQ1IDEuNDk5IDAgMC0uMDI5LjI3NS0uMzA0LjQ0OC0uMTUzLjA5Ni0uMjE1LjA1My0uMjE1LjA1My4yOTQtLjYyNy4yOTctLjg5MS0uMDI4LTEuNDg1LS4yNDUtLjQ0Ny0uMzU4LS44OTktLjI3LTEuMzk4LjAwMy0uMDIuMDEtLjA0LjAxNC0uMDZhMi4yMjIgMi4yMjIgMCAwIDEtLjA4OC4xOTljLS4yNS40MzktLjQ4Ni42NjctLjYyOCAxLjEyMS0uMTQ5LjUwOC4wMSAxLjA1OS4zMjUgMS41OThhMS4yMzcgMS4yMzcgMCAwIDEtLjU1My0uODA0IDQuMzIzIDQuMzIzIDAgMCAwLTEuMzM0IDEuMTY2Yy0uMDguMTA0LS4xNzUuMTkxLS4yNTkuMjY4YTQuOTIgNC45MiAwIDAgMS0xLjk3OCAxLjA5OWMtLjQ5My4xNDUtMS4wMDEuMjY3LTEuNTAyLjM4OGwtLjEzMS4wMzFjLS42ODMuMTY1LTEuNDA5LjM1MS0yLjA5Ny42NTctLjc5Mi4zNTItMS40Mi43NTctMS45MTggMS4yMzlhNC40MTIgNC40MTIgMCAwIDAtMS4zMjYgMi41OTNjLS4xMTQuNzgxLS4wNTUgMS41OTUuMTggMi40OS4wMDguMDMyLTEuMDMtLjk0MS0uNDk0LTMuNzQxYTYuMzIyIDYuMzIyIDAgMCAwLS4yMzYtLjAwN2wtLjA2Ny4wMDFjLTEuOTMzLjA1OC0yLjczNyAxLjEyMy0yLjczNyAxLjEyM3MuMTI2LTEuMTgyIDEuOTg3LTEuNTc5Yy4xNC0uMDMgMS4zMTItLjI5MyAxLjM1Mi0uMzA2LjE1NC0uMzE0LjM0MS0uNjEyLjU1Ny0uODg5bC0uMTY2LjAyNmMtLjMxOS4wNS0uNjQ4LjEtLjk3NS4xNDNsLS4yNTIuMDNjLS41NzcuMDc0LTEuMTc0LjE0OS0xLjc0LjMxNi0uNTk0LjE3NC0xLjA1OS40MjYtMS40MjIuNzY4LS4zODkuMzY2LS42NjguODM5LS44NTIgMS40NDJsLS4wMjMuMDg2Yy0uMDEzLjA1LS4wMjYuMTAxLS4wNDUuMTUxLS4wMi4wNTItLjAyNC4xMS4wMTguMjIuMzQ4LjkyMy45NDUgMS43MjMgMS43NzQgMi4zNzZhNy41ODcgNy41ODcgMCAwIDAgMi4xNDYgMS4xOGMuMDI2LjAwOS4wNy4wMjQuMTA5LjA2NGwuMzQ4LjMzNy0uNTQ0LS4xM2MtLjA2NC0uMDE1LS4xMjctLjAyOS0uMTkxLS4wNDctMS4xMTQtLjMwNi0yLjA4NS0uODIxLTIuODg1LTEuNTMyLS4yNzMtLjA5OS0xLjY2OC0uNzk0LTIuMjYtMS45MzZsLS4wOTktLjE5cy43NTcuNzQ2IDEuMjg4Ljg1NWE1LjU5IDUuNTkgMCAwIDEtLjU2NC0xLjIyLjI4My4yODMgMCAwIDAtLjA0OS0uMDg3QzEuMjczIDE3LjE5Ni42MjQgMTYuMDU0LjE5NiAxNC44MzRhNC43MDggNC43MDggMCAwIDEtLjA4NS0uMjYyYy0uMDQzLjM1NS0uMDY0LjcxLS4wNjQgMS4wNTcgMCAuMTEuOTU1IDIuNjQ3Ljk1NSAyLjY0N3MtLjQyLS40NjctLjc2OC0xLjA1OWMwIDAtLjA2MS0uMTk5LS4wNjktLjIxMi4xNDkuODk3LjQzOSAxLjc0Ljg2MyAyLjUyMSAxLjE2NyAyLjE0NyAyLjk1NiAzLjU1NCA1LjQ3IDQuMjEyYTcuNzMgNy43MyAwIDAgMCAxLjk1NS4yNTVsNy44NTUuMDA3Yy4zNjkgMCAuNjUyLS4wMjIuOTE1LS4wN2wuMDQxLS4wMDdhMS40NyAxLjQ3IDAgMCAxIC4yODEtLjAzNGMuMTA2LjAwMS4yMTkuMDE0LjM0NS4wNDRsLjA2Mi4wMTVjLjExNi4wMjYuMjI0LjA1Mi4zMzEuMDUyIDEuMzIuMDEgMS4xMzctLjc4NSAxLjEzNy0uNzg1LS4wNTUtLjIwNy0uMjk1LS4zNTEtLjU1Ny0uNDEzYTEuMjA0IDEuMjA0IDAgMCAwLS4yOC0uMDMzYy0uMTc5IDAtLjM2Ny4wNDEtLjU1OS4xMmwtLjI4OC4xMjMtLjE3Mi4wNzVhMS4zMTcgMS4zMTcgMCAwIDEtLjA5OC4wMzguNTQuNTQgMCAwIDEtLjE3LjAzNmMtLjE5OSAwLS4yMDgtLjE5NS0uMjEzLS4zMTJhLjQ2LjQ2IDAgMCAxIC4xNjktLjM3M2MuMDkzLS4wNzkuMTk0LS4xNTYuMzAyLS4yMjguMTk1LS4xMzIuMzk2LS4yNjguNTUxLS40NDZhMS40OSAxLjQ5IDAgMCAwIC4zNjEtLjY5OS44MjUuODI1IDAgMCAwLS4wNDQtLjQ2OWMtLjAxNC0uMDM1LS4wMjctLjA0Mi0uMDQtLjA0NmE5LjAzNyA5LjAzNyAwIDAgMC0uMzY4LS4xMTJjLS40ODgtLjEzNy0uODQ3LS4zNDItMS4xMjctLjY0M2EyLjgwMyAyLjgwMyAwIDAgMS0uNDM5LS42NzEgNS43ODMgNS43ODMgMCAwIDEtLjQxNi0xLjA5NmMtLjE1OS0uNjAxLS41MzYtMS4wODMtMS4xNS0xLjQ3MmEzLjUzNiAzLjUzNiAwIDAgMC0xLjU1Ny0uNTI0Yy0uMTM3LS4wMTUtLjI3Ni0uMDIxLS40MjMtLjAyOC0uMDM3LS4wMDItLjEyMi0uMDEzLS4yMDgtLjAyNC0uMDc3LS4wMS0uMTUzLS4wMjEtLjE4OC0uMDIybC0uMjEtLjAxM3MuMDU0LS4wNzYuNDg5LS4yNDJjLjA4Mi0uMDMxLjE2Ny0uMDM5LjI1LS4wNTQuMjAxLS4wMzUuNC0uMDUzLjU5LS4wNTMuNDU4IDAgLjg5MS4xMDYgMS4yODguMzE0LjQ5NC4yNi44ODguNjU2IDEuMjA2IDEuMjExLjE3My4zMDIuMzA5LjYyNi40MTYuOTkyLjAyMS4wNy4wMzguMTQuMDU4LjIxNi4wMzUuMTM0LjA3MS4yNzEuMTIyLjM5Ni4zMDcuNzU2Ljg3NiAxLjE5OCAxLjY5IDEuMzE1LjIxNi4wMzEuNDI2LjA0Ni42MjYuMDQ2YTMuNDggMy40OCAwIDAgMCAxLjA3Ny0uMTY1Yy40NTUtLjE0OS44MDMtLjM4MiAxLjA2Mi0uNzEyYTEuNDIgMS40MiAwIDAgMCAuMjU1LS40OTRsLjAzNS0uMTIxLjIwMy4wNDhjLjA0My4wMTEuMDg2LjAyMS4xMy4wM2EuNDgzLjQ4MyAwIDAgMCAuMDk0LjAwOWMuMDkyIDAgLjE4Ni0uMDIyLjI4OC0uMDQ0bC4wMTctLjAwNGMuMDc2LS4wMTcuMTUtLjAyLjIyMi0uMDIzbC4wNjEtLjAwM2MuMDcyIDAgLjEzMi4wNDguMTU5LjA5My4wMzEuMDUzLjA4MS4wODMuMTc1LjEwNGEuMzY3LjM2NyAwIDAgMCAuMDc1LjAwN2MuMjI5IDAgLjQ3LS4yMS40NzYtLjQxNi4wMDMtLjA3OS0uMDE4LS4xMjctLjA3LS4xNjMtLjA0MS0uMDI4LS4wODMtLjA1NC0uMTMxLS4wODRsLS4yMjgtLjE0My4xNTItLjExNmEuMjQ1LjI0NSAwIDAgMSAuMTQ3LS4wNTFjLjA0NSAwIC4wODUuMDEzLjEyLjAyOCAwIDAtLjE5MS0xLjAxLTEuNTI3LS43MTYgMCAwLS4yMTcuMDg5LS4zMjguMTMxbC0uMDUyLjAyYS4yNy4yNyAwIDAgMS0uMTAxLjAxOS4zNTguMzU4IDAgMCAxLS4xNjYtLjA0N2MtLjQ2OC0uMjM1LS45MjYtLjEzMS0xLjAwMi0uMTMxYTIuMjggMi4yOCAwIDAgMS0uNTM4LS4wNTkuMjIyLjIyMiAwIDAgMS0uMTE2LS4wNjdsLS4wODYtLjA5N2EyLjYzNCAyLjYzNCAwIDAgMS0xLjE4My0uMTk3Yy0uNDM2LS4xODYtLjc4NC0uNDctLjk5NS0uOTAzYTEuNDg3IDEuNDg3IDAgMCAxLS4xNS0uNjg1bC4wMjYuMDY3Yy4wODQuMjQ4LjIwOC40NzQuMzc0LjY3OC4zMDYuMzc5LjcwMS42MzQgMS4xNS44MTMuMjQzLjA5Ny40OTUuMTY1Ljc2NC4yMSAwIDAgLjk1NS4wMzYgMS4zOC0uMzE3LjMyMy0uMTguNjE0LS4yNjQuOTE3LS4yNjRoLjA2M2MxLjAyNy0uMDAxIDEuMTE4LS40OTggMS4xMTgtLjQ5OHMuMTE3LjA3Ni4yODEuMDUxYS42NjYuNjY2IDAgMCAwIC42MDQtLjYzbC0uMzQtLjMwNi0uMDcyLS4wNjMtLjEzNC0uMTA2LjA5Mi0uMTA1YS4yNzQuMjc0IDAgMCAxIC4yMDctLjA5OWMuMDQ2IDAgLjA5MS4wMTIuMTM0LjAzNS4wNjEuMDM0LjExNS4wNzcuMTY0LjExN2wuMDUxLjA0LjA2NC4wNWEuNTU5LjU1OSAwIDAgMC0uMDM2LS4yNjV6bS0xLjI2Ny0uMjczYy0uMDM4LjEwNi0uMDg4LjEyMy0uMTk5LjA5OWEuNjg4LjY4OCAwIDAgMC0uMTgxLS4wMTRjLS4xMTEuMDA1LS4yMjEuMDI0LS4zMzIuMDI2LS4yNzcuMDA1LS41NDMtLjA0NS0uNzYzLS4yMjUtLjMxMi0uMjU2LS4zNzItLjU1OS0uMTc3LS45NDNsLjAwNC4wMzdhLjc0NS43NDUgMCAwIDAgLjM0NS42MTFjLjE4LjEyMS4zODUuMTcuNTk1LjE5Ni4xNy4wMjEuMzM4LjA1LjQ4Ny4xNDJsLjA0MS4wMjFhLjA0My4wNDMgMCAwIDEgLjAwNi0uMDA3Yy0uMDI5LS4wNDEtLjAzOS0uMTgzLS4wMjQtLjI0MmEuNTY1LjU2NSAwIDAgMCAuMDAyLS4yOTcuNjIyLjYyMiAwIDAgMS0uMjUuMzA0LjA3Ni4wNzYgMCAwIDEtLjA1My4wMiAyLjUzIDIuNTMgMCAwIDEtLjY1NC0uMjMzYy0uMTg2LS4xMDItLjI4My0uMjYxLS4yMzQtLjQ4NGEuMTk4LjE5OCAwIDAgMC0uMDU2LS4xODljLS4wMjMtLjAyMy0uMDQzLS4wNS0uMDY3LS4wNzguMDU1LS4wNTEuMTAyLS4xLjE1NS0uMTQzLjA1LS4wNC4xMDItLjA3OC4xNTgtLjEwOS40MzItLjI0NSAxLjAxNi0uMDYxIDEuMjA4LjM4OS4wNDkuMTE0LjA3NS4yNC4wODkuMzYzLjAyOC4yNTktLjAxMy41MTEtLjEuNzU2em0tMjAuNjcgMi45MjZjLS4wMi0uMjM3LS4wMzMtLjQ3NC0uMDQ2LS43NTZhLjEwMi4xMDIgMCAwIDAtLjAyMS0uMDY0Yy0uNjMtLjkwOS0xLjA4OS0xLjY5Ni0xLjQ0Ni0yLjQ3NmE3LjI5MiA3LjI5MiAwIDAgMS0uMTY5LS4zOTQgNy43NDggNy43NDggMCAwIDAgMS42ODIgMy42OTR2LS4wMDR6bTE4Ljk5MSA0LjEwM2MuMTc2LjExNy4zOTUuMjAzLjczMi4yODcuMzQuMDg1LjY1My4xMjUuOTY2LjEyNS4xODUgMCAuMzM0LS4wMTkuNDctLjA1OWEuODEuODEgMCAwIDAgLjU5LS42MzkgNi4wMyA2LjAzIDAgMCAwIC4xMjgtLjcxMyAxLjc5OCAxLjc5OCAwIDAgMC0uMzcyLTEuMzIzYy0uMDM1LjAzMS0uMDcuMDYxLS4xMDYuMDg5YTEuMTA0IDEuMTA0IDAgMCAxLS4xOTguMTIxLjY1OC42NTggMCAwIDEtLjI5MS4wNzIuNTkzLjU5MyAwIDAgMS0uMjgxLS4wNzIuOTYuOTYgMCAwIDAtLjQ2MS0uMTA0Yy0uMDYzIDAtLjEzMS4wMDUtLjIwOC4wMTMtLjAyNy4wMDMtLjAzOS4wMDktLjA1NC4wNC0uMjU4LjUzMS0uNjgzLjkwOC0xLjI5OCAxLjE1NGwtLjAxNy4wMDctLjAwMy4wMTNhMS4xNSAxLjE1IDAgMCAwLS4wMDEuNDU0Yy4wNTQuMjE2LjE4NS4zOTEuNDA0LjUzNXpNMTQuOTkgOS41MTJjLS41MTYuNTI1LTEuMTQxLjk1OC0xLjk2NCAxLjM2NC0uNTIuMjU2LTEuMS40NDEtMS44MjYuNTgyLS40MTUuMDgxLS44MjkuMTU5LTEuMjQzLjIzN2wtLjA4Ni4wMTUtMS4wNTYuMmMtLjkyOS4xNzgtMS45Mi4zODktMi44NzIuNzEtLjY5MS4yMzQtMS4yMjQuNDgxLTEuNjc3Ljc3OS0uNDQ0LjI5MS0uNzUuNTkxLS45NjUuOTQzYTIuNjM3IDIuNjM3IDAgMCAwLS4xNDYuMjkxIDUuNjk2IDUuNjk2IDAgMCAxLS4wNzUuMTU5LjQyLjQyIDAgMCAxLS4wNzYuMTE0Yy0uNDg0LjQ3My0uNjkgMS4wNjQtLjYxMyAxLjc1Ni4wNDYuNDE2LjE3Ni44MjEuMzk1IDEuMjM2LjEyNy0uODQ2LjU3NC0xLjQ5MiAxLjMyOC0xLjkyLjQxLS4yMzMuODYzLS40MDMgMS4zODMtLjUxNy41MjYtLjExNyAxLjA2LS4yMTQgMS41NjEtLjMwNGwuMzA3LS4wNTRjLjUxNi0uMDkxIDEuMDUxLS4xODQgMS41NTgtLjM0NS4xMi0uMDM4LjIzOC0uMDguMzQ4LS4xMjEuMTQ3LS4wNTUuMjc1LS4xMi4zOTEtLjIwNi4xNDEtLjEwNS4yODktLjIuNDQ0LS4yOTEtLjY1My0uMDE1LTEuNzYtLjAxNy0yLjEwNC0uMDE5LS43Ny0uMDA0LTEuMy4wNi0xLjk2NC4zMTItLjY5NC4yNjQtMi42NzYgMS4yNzEtMi42NzYgMS4yNzFzLjk4NS0xLjA1NCAyLjgzNy0xLjg0NGE3Ljg1OCA3Ljg1OCAwIDAgMSAyLjkyOC0uNTNjLjI3NSAwIC41NjEuMDExLjg3Mi4wMzMuNTEyLjAzOCAxLjAyNC4wNzUgMS41MzUuMTFsLjAxNC4wMDFjLjAyNCAwIC4wNS0uMDA0LjA3NS0uMDExYTEwLjYzIDEwLjYzIDAgMCAxIDEuNTcyLS4zMjVjLjE3NS0uMDI1LjM1My0uMDYxLjUyOC0uMDk3LS4wMzQtLjAxMS0uMDY5LS4wMi0uMTAzLS4wM2ExLjEzIDEuMTMgMCAwIDEtLjExOC0uMDQ0bC0uMDg4LS4wMzUtLjM0NS0uMjMzIDEuMjk2LjAyOGMuMjc5IDAgMy4wMzItLjQ0MyA0LjIxLTMuNzIzLjA3OC0uMjE5LjE2LS40MzcuMjIzLS42NzZhNy42MTEgNy42MTEgMCAwIDEtMi42NjkgMS4wNjMgNy4xNTUgNy4xNTUgMCAwIDEtMS4xMzkuMTIxem00Ljc4NC0xLjg3MXptMS43MDEgNS42MjJhLjI3LjI3IDAgMSAwIC41NCAwIC4yNy4yNyAwIDAgMC0uNTQgMHoiLz48L3N2Zz4=" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none">☾</button>
</header>
<div class="wrap">
  <div id="home">
    {archnav}
  </div>
  <div id="panes" style="display:none">
    <button class="hbtn back on" id="back2" onclick="showHome()">← 返回全部主线</button>
    {panes}
  </div>
</div>
<script>{js}</script>
</body>
</html>""".format(
        sub=esc(BRAND_SUB), n=total_svg,
        css=CSS, archnav=archnav, panes=build_panes(), js=APP_JS)


if __name__ == "__main__":
    html_out = build_html()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    kb = len(html_out.encode("utf-8")) / 1024
    print("Wrote %s  (%.0f KB)" % (os.path.abspath(OUT), kb))
    print("主线 %d 条 · 图引用 %d 张 · 磁盘 %d 张 · 缺失 %d · 孤儿 %d"
          % (len(MAINLINES), len(_all_refs), len(_on_disk), len(_missing), len(_orphan)))
    if _missing:
        print("  ⚠ 缺失:", sorted(_missing))
    if _orphan:
        print("  ⚠ 孤儿(design 里有但未被任何主线引用):", sorted(_orphan))
