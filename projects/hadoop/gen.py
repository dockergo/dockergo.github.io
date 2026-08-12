#!/usr/bin/env python3
"""hadoop-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd hadoop-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import json
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 hadoop 交互式核心原理图谱（离线自包含 HTML）")
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
    os.environ.get("HADOOP_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("HADOOP_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     家族 4 分布式存储/文件系统（HDFS + YARN + MapReduce）：元模式 = 接触面 × 能力域 × 时机。
#     全景 + 3 接口主线 + 8 支撑能力域。
# ===================================================================== #
MAINLINES = [
    ("Hadoop原理_全景主线框架", "pano", "◇", "全景主线框架",
     "家族 4 分布式存储/文件系统：双维模型 · 总架构 · 读写数据流 · 依赖矩阵 · 三条贯穿声明"),

    ("Hadoop原理_接口_FileSystem与Shell", "iface", "⚙", "FileSystem API 与 fs shell",
     "FileSystem 可插拔门面 · DistributedFileSystem 委托 DFSClient · fs shell 同路"),
    ("Hadoop原理_接口_YARN应用提交", "iface", "⇄", "YARN 应用提交",
     "YarnClient 提交 → RM 启动 AM 容器 → AM 自申请 Container · 资源仲裁与应用调度解耦"),

    ("Hadoop原理_支撑_NameNode命名空间与元数据", "support", "◆", "NameNode 命名空间与元数据",
     "灵魂：全内存 INode 树 · FsImage 快照 + EditLog 预写日志 · 检查点合并 · 先日志后内存"),
    ("Hadoop原理_支撑_DataNode块存储", "support", "▤", "DataNode 块存储",
     "只认块不认文件 · block + .meta 双文件 · FsDatasetImpl 多卷 volumeMap · 校验和自愈"),
    ("Hadoop原理_支撑_块放置与复制策略", "support", "▦", "块放置与复制策略",
     "一近两远跨两机架 · BlockPlacementPolicyDefault · RedundancyMonitor 期望态对账"),
    ("Hadoop原理_支撑_Pipeline写数据流", "support", "◉", "Pipeline 写数据流",
     "client→DN1→DN2→DN3 流水复制 · packet/ack 队列 · genStamp 故障重建管道"),
    ("Hadoop原理_支撑_心跳与块汇报对账", "support", "⚡", "心跳与块汇报对账",
     "灵魂：心跳 3s 保活+搭车回令 · 块汇报全量 6h+增量即时 · blocksMap 内存重建"),
    ("Hadoop原理_支撑_HA高可用", "support", "⛨", "HA 高可用",
     "Active/Standby + JournalNode 多数派 EditLog + ZKFC 选主切换 · epoch/fencing 防脑裂"),
    ("Hadoop原理_支撑_YARN资源调度", "support", "◫", "YARN 资源调度",
     "RM 仲裁/AM 调度/NM 执行三权分立 · Capacity/Fair 队列 · 数据本地性"),
    ("Hadoop原理_支撑_MapReduce执行", "support", "✲", "MapReduce 执行",
     "就近读块的 Map → 拉取归并的 Shuffle → 汇聚输出的 Reduce · MRAppMaster 是一种 AM"),
    ("Hadoop原理_支撑_Balancer与Federation", "support", "◐", "Balancer 与 Federation",
     "Balancer 均衡磁盘利用率(不改副本) · Federation/RBF 多 NameNode 拆命名空间"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接触面主线 · 外部如何用（FileSystem API/Shell / YARN 提交）"),
    ("support", "支撑主线 · 存储与计算内部（8 条能力域）"),
]

# ===================================================================== #
# 一·b、项目总架构图 = 唯一导航底图 —— 热区注册表（决定"点击下钻"）
#   产出准则（用户明确要求）：项目页统一用【项目总架构图】(ARCH_SVG_NAME) 做导航，
#   在图上叠透明热区，每个语义模块 = 一个可点区域 → 下钻对应主线。
#   坐标系 = 该总架构 SVG 的 viewBox（ARCH_W×ARCH_H），生成期换算成百分比定位。
#   两条覆盖铁律：① 图上每个模块都有热区 ② 每条主线都被某热区覆盖（未覆盖者自动兜底成 chip）。
# ===================================================================== #
PANO_NAME = "Hadoop原理_全景主线框架"
# (x, y, w, h, 主线name) —— 一个模块可拆多行热区，一条主线可被多个区域指向
# 没有独立架构区域、需底部 chip 兜底的主线（本项目 12 主线全部落在图上 → 空）
ARCH_ALWAYS_CHIP = []

BRAND_TITLE = "一切知识皆索引"
BRAND_SUB = "Apache Hadoop"
HOME_DESC = ("Apache Hadoop（HDFS + YARN + MapReduce）核心原理设计文档库的离线交互图谱——家族 4 分布式存储/文件系统。"
             "12 条主线、25 张手绘原理图，全部回本地源码核实（commit 6f5d1374）。点击项目总架构图任意模块即可下钻到对应主线。")
ARCH_SVG_NAME = "Hadoop原理_全景_02总架构.svg"
_ARCH_SVG_TEXT = open(os.path.join(_DESIGN_DIR, ARCH_SVG_NAME), encoding="utf-8").read()
def _parse_arch_hotspots(svg_text):
    """从架构 SVG 的 data-tid rect 派生热区 5 元组 + viewBox 宽高(除数恒用本图 viewBox)。"""
    import xml.etree.ElementTree as _ET
    vb = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg_text)
    vbw, vbh = float(vb.group(1)), float(vb.group(2))
    root = _ET.fromstring(svg_text); hots = []
    def walk(el, dx, dy):
        m = re.search(r'translate\(\s*([-\d.]+)(?:[,\s]+([-\d.]+))?', el.get("transform") or "")
        if m:
            dx += float(m.group(1))
            if m.group(2): dy += float(m.group(2))
        if el.tag.rsplit("}", 1)[-1] == "rect" and el.get("data-tid"):
            hots.append((float(el.get("x", 0)) + dx, float(el.get("y", 0)) + dy,
                         float(el.get("width", 0)), float(el.get("height", 0)),
                         el.get("data-tid")))
        for c in el:
            walk(c, dx, dy)
    walk(root, 0.0, 0.0)
    return hots, vbw, vbh
ARCH_HOTSPOTS, ARCH_W, ARCH_H = _parse_arch_hotspots(_ARCH_SVG_TEXT)

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
            if f.endswith(".svg") and f != "icon.svg"}  # icon.svg 是站点图标，非原理图
_missing = _all_refs - _on_disk
_orphan = {f for f in (_on_disk - _all_refs)
           if f not in ("icon.svg", "logo.svg", "favicon.svg")}  # 图标非主线图,豁免孤儿告警

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
        '<img alt="Apache Hadoop 项目总架构图" src="data:image/svg+xml;base64,%s"/>'
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
.logo:hover .homeico{display:inline-grid;place-items:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);transition:color .15s} a:hover .homeico,.logo:hover .homeico,.homelink:hover .homeico{color:var(--c-brand);border-color:var(--c-brand)}
.nn-n{fill:var(--c-ink2)}.nn-h{fill:var(--c-brand)}.nn-e{stroke:var(--c-line);stroke-width:1.4}
.tt-ico{font-size:16px;line-height:1}.tt-sun{display:none}:root[data-theme="light"] .tt-moon{display:none}:root[data-theme="light"] .tt-sun{display:inline}
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
.arch-wrap{position:relative;margin-top:12px;background:var(--c-card);border:1px solid var(--c-border);border-radius:16px;padding:0;overflow:hidden}.msearch{position:relative;display:flex;align-items:center;gap:8px;width:min(300px,38vw);padding:0 12px;height:38px;border-radius:19px;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);margin-right:12px}.msearch svg{flex:none;opacity:.7}.msearch input{flex:1;border:0;background:transparent;color:var(--c-ink);outline:0;font-size:13px}.msearch kbd{flex:none;font:600 11px monospace;color:var(--c-ink3);border:1px solid var(--c-line);border-radius:5px;padding:1px 6px}.mq-list{position:absolute;top:44px;left:0;right:0;z-index:60;background:var(--c-card);border:1px solid var(--c-line);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;display:none}.mq-list.on{display:block}.mq-item{display:block;width:100%;text-align:left;border:0;background:transparent;cursor:pointer;padding:9px 14px;color:var(--c-ink);font-size:13px;border-bottom:1px solid var(--c-line)}.mq-item:last-child{border-bottom:0}.mq-item:hover,.mq-item.sel{background:color-mix(in srgb,var(--c-brand) 12%,transparent)}.mq-item .s{display:block;color:var(--c-ink3);font-size:11px;margin-top:2px}
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
  var saved=localStorage.getItem('atlas-nav-theme');
  if(saved) root.setAttribute('data-theme',saved); else root.setAttribute('data-theme','light');
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='light'?'dark':'light';
    root.setAttribute('data-theme',cur);
    localStorage.setItem('atlas-nav-theme',cur);
    
  }
  var tb=document.getElementById('themeBtn');
  if(tb){tb.onclick=toggleTheme;}

  var home=document.getElementById('home'), panes=document.getElementById('panes');
  function showHome(){home.style.display='block';panes.style.display='none';
    document.querySelectorAll('.pane').forEach(function(p){p.classList.remove('on')});
    window.scrollTo(0,0);}
  window.openMain=function(mid,idx){return openMain(mid,idx);};
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

/* 模块搜索:过滤本项目主线,回车/点击下钻 */
(function(){
  var MS=window.__MAINS__||[], mq=document.getElementById('mq'), list=document.getElementById('mqlist');
  if(!mq||!list) return;
  var sel=-1, cur=[];
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function render(){
    var q=mq.value.trim().toLowerCase();
    cur = !q ? [] : MS.filter(function(m){return (m.t+' '+m.s+' '+m.mid).toLowerCase().indexOf(q)>=0;}).slice(0,8);
    if(!cur.length){ list.className='mq-list'; list.innerHTML=''; return; }
    sel=0;
    list.innerHTML=cur.map(function(m,i){return '<button class="mq-item'+(i===0?' sel':'')+'" data-mid="'+esc(m.mid)+'"><b>'+esc(m.t)+'</b><span class="s">'+esc(m.s)+'</span></button>';}).join('');
    list.className='mq-list on';
  }
  function go(mid){ mq.value=''; list.className='mq-list'; list.innerHTML=''; if(typeof window.openMain==='function') window.openMain(mid,0); }
  mq.addEventListener('input',render);
  mq.addEventListener('keydown',function(e){
    if(!cur.length){ if(e.key==='Escape') mq.blur(); return; }
    if(e.key==='ArrowDown'){e.preventDefault();sel=(sel+1)%cur.length;}
    else if(e.key==='ArrowUp'){e.preventDefault();sel=(sel-1+cur.length)%cur.length;}
    else if(e.key==='Enter'){e.preventDefault();go(cur[sel].mid);return;}
    else if(e.key==='Escape'){list.className='mq-list';mq.blur();return;}
    else return;
    [].forEach.call(list.children,function(el,i){el.className='mq-item'+(i===sel?' sel':'');});
  });
  list.addEventListener('click',function(e){var b=e.target.closest('.mq-item'); if(b) go(b.dataset.mid);});
  document.addEventListener('keydown',function(e){ if(e.key==='/'&&document.activeElement!==mq){e.preventDefault();mq.focus();} });
  document.addEventListener('click',function(e){ if(!e.target.closest('.msearch')){list.className='mq-list';} });
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
  <a class="logo" id="logo" href="../../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a><div class="brand-intro" style="display:flex;flex-direction:column;align-items:flex-start;margin-left:12px;min-width:0;max-width:min(60vw,760px)"><div style="font-size:15px;font-weight:600;color:var(--c-ink);line-height:1.3">Hadoop HDFS · 核心原理图谱</div><span style="margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5;text-align:left">分布式文件系统 HDFS:NameNode 管元数据 + DataNode 存块副本,大文件切块 + 多副本容错,一次写多次读。</span></div>
  <div class="spacer"></div>
  <label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label>
  <a href="https://github.com/apache/hadoop" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://hadoop.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCI+PHBhdGggZD0iTTcuNDAzIDM4LjEyNGwtLjMxNi44Ni0uNjA2LS4yMjIuMzE2LS44NnptLS4zMTYuODZsLS40NyAxLjI4LS42MTctLjIyLjQ3LTEuMjh6bS0uNDcgMS4yOGwtLjA3Ni4xMTctLjIyNy0uMjI4em0tLjA3Ni4xMTdsLTEuMDMzIDEuMDIzLS40NTQtLjQ1NyAxLjAzMy0xLjAyM3ptLTEuMDMzIDEuMDIzbC0uOTE2LjkwNy0uNDU0LS40NTcuOTE2LS45MDd6bS0uOTE2LjkwN2wtLjIzLjIyNC0uNDQ3LS40NjcuMjItLjIxNHptLS4yMy4yMjRjLS40MTMuMzk4LS40OTUuNDc3LS4zNzYgMS4xODhsLS42MzYuMTA2Yy0uMTc1LTEuMDQ4LS4wNTMtMS4xNjYuNTY2LTEuNzZ6bS0uMzc2IDEuMTg4YTUuNzQgNS43NCAwIDAgMCAuNTg1IDEuNzI1bC0uNTczLjNhNi40IDYuNCAwIDAgMS0uNjQ4LTEuOTJ6bS41ODUgMS43MjVjLjI3Ny41MjguNjQ3IDEuMDQgMS4xMTggMS41MTJsLS40NTcuNDU0YTYuOTIgNi45MiAwIDAgMS0xLjIzNC0xLjY2NnpNNS43IDQ2Ljk2Yy42MDMuNjA1IDEuNTg3IDEuMzU0IDIuNjEyIDEuNzQzbC0uMjI3LjYwNGMtMS4xMi0uNDI1LTIuMi0xLjIzOC0yLjg0Mi0xLjg5MnptMi42IDEuNzQzYy43MTMuMjcgMS40NC4zNjQgMi4wNDYuMDk1bC4yNi42Yy0uNzgzLjM0Ny0xLjY3Ni4yNDMtMi41MzMtLjA4M3ptMi4wNDYuMDk1bC42MjQtLjI3Ni0uMTgyLjY1Ny0uMzEyLS4wODZ6bS40NDIuMzhsLS4yODUuODk1LS42LS4yMi4yNy0uODQ3em0tLjI4NS44OTVsLS4zNDcuODUtLjU4OC0uMjY4LjMyNi0uODAyem0tLjM0Ny44NWMtLjU0NiAxLjE5Ny4wMjYgMS44MjguOTEzIDIuMjMybC0uMjY4LjU4OGMtMS4yLS41NDctMi0xLjQxNy0xLjIzLTMuMDgzem0uOTEzIDIuMjMyYy41NjcuMjU4IDEuMjUzLjQzNyAxLjkuNjAzbC0uMTYyLjYyNGMtLjY3LS4xNzQtMS40LS4zNjItMS45OTYtLjYzOHptMS45LjYwM2wuNDUuMTE4LS4xNjQuNjI0LS40NDYtLjExOHptLjQ1LjExOGMuNzcuMjA4IDIuMDk3LjYgMy4yOTIuNjY1bC0uMDQuNjQ2Yy0xLjI1Mi0uMDgtMi42MjItLjQ3My0zLjQxNi0uNjg3em0zLjI5Mi42NjVjMS4wOC4wNjggMi4wNDItLjExMyAyLjI2NS0uOTRsLjYyNC4xNjRjLS4zMyAxLjIyNy0xLjU2MyAxLjUtMi45MyAxLjQyMnptMi4yNjUtLjk0YTYuMzYgNi4zNiAwIDAgMCAuMjE1LTEuMWwuNjQ2LjA1M2MtLjAzLjM2NC0uMTA2LjczNy0uMjM3IDEuMjIzem0uMjE1LTEuMWMuMDMtLjMzNy4wMTctLjY2NC0uMDI1LTEuMDhsLjY0LS4wNmE2LjM3IDYuMzcgMCAwIDEgLjAzIDEuMTkzem0tLjAyNS0xLjA4bC4wMjUtLjE2Mi4yOTUuMTN6bS4wMjUtLjE2MmMuNDM1LS45Ny42MTQtMS4yMzMuOTMtMS42OTZsLjUzMy4zNjRjLS4yOTMuNDI4LS40NTguNjctLjg3MiAxLjU5NXptLjkzLTEuNjk2bC4xNC0uMjA4LjUzNS4zNi0uMTQ0LjJ6bS4xNC0uMjA4Yy4yNDctLjM2Ni4zNi0uNi4zOTctLjg2M2wuNjQuMDg4Yy0uMDUyLjM2Mi0uMTk1LjY4My0uNSAxLjEzNnptLjM5Ny0uODYzYy4wMzgtLjI2NiAwLS41ODItLjA1OC0xLjA2N2wuNjQtLjA3M2MuMDYzLjUzMi4xMDUuODguMDU1IDEuMjN6bS0uMDU4LTEuMDY3bC0uMDM4LS4zMDUuNjQtLjA4LjA0LjMxM3ptLS4wMzgtLjMwNWwtLjA0Ni0uMzIuNjQtLjA5My4wNDYuMzN6bS0uMDQ2LS4zMmwtLjA2My0uNDMuNDMuMDY1LS4wNDguMzJ6bS4zNjctLjM2NmExOC45NSAxOC45NSAwIDAgMCAyLjcwNC4yMTFsLS4wMDMuNjQ2YTE5LjU4IDE5LjU4IDAgMCAxLTIuNzk3LS4yMTl6bTIuNzA0LjJhMjAuNDkgMjAuNDkgMCAwIDAgMi42ODMtLjE2MmwuMDc2LjY0Yy0uOTI1LjExNS0xLjg0Mi4xNzMtMi43NjIuMTY3em0yLjY4My0uMTYybC4yLjYtLjE2Mi0uMjh6bS4yLjZsLTEuNzA3LjkxMy0uMjk1LS41NzYgMS42OC0uODk4em0tMS43MDcuOTEzbC0uMTQ4LjA3Ni0uMjk1LS41NzYuMTQ4LS4wNzZ6bS0uMTQ4LjA3NmMtLjY4My4zNS0uNyAxLjA4OC0uNDQ4IDEuODZsLS42MTYuMTkyYy0uMzMtMS4wNTctLjI4Ni0yLjA4NS43NjgtMi42Mjh6bS0uNDQ4IDEuODZjLjI3NC44NzYuODU1IDEuNzk4IDEuMjIgMi4zNmwtLjU0LjM1Yy0uMzg0LS41OTItLjk5Ny0xLjU2NS0xLjI5NS0yLjUyem0xLjIyIDIuMzZjLjc2MyAxLjE3NiAxLjQ4MyAyLjE2NyAyLjMgMi42NzRsLS4zMzYuNTVjLS45MzUtLjU3My0xLjcwNi0xLjYyNy0yLjUxNS0yLjg3M3ptMi4zIDIuNjc0Yy43OC40OCAxLjY5NC41MjMgMi45MDQtLjEzbC4zMDYuNTdjLTEuNDQ2Ljc4Mi0yLjU2NS43MTItMy41NDUuMXptMi45MDQtLjEzYy41NzItLjMuNzY0LS42NDUgMS4wMjItMS4wOThsLjU2My4zMThjLS4zMTIuNTQ3LS41NDQuOTUzLTEuMjggMS4zNXptMS4wMjItMS4wOThsLjM4LS42MjQuNTM1LjM1OC0uMzUzLjU4NHptLjM4LS42MjRsLjExMi0uMTA1LjE1NS4yODR6bS4xMTItLjEwNWMuMi0uMTA0Ljk5NS0uNzcgMS43OC0xLjQxN2wuNDEyLjQ5Ny0xLjg4IDEuNDg4em0xLjc4LTEuNDE3bDEuMDA4LS44My40MDYuNTA1LTEuMDAzLjgyMnptMS4wMDgtLjgzbC4yNDgtLjIuMjA0LjI0NS0uMjUuMjA3em0uNDUyLjA0NWMuMTMuMTU1LjMzMy4yNS42LjMxN2wtLjE1LjYzYy0uNDEzLS4xLS43My0uMjU4LS45NTgtLjUzem0uNi4zMTdjLjMxOC4wNzYuNzM2LjExMyAxLjI0Mi4xNWwtLjA0Ni42NDZjLS41My0uMDM4LS45NzQtLjA3OC0xLjM0Ni0uMTY3em0xLjI0Mi4xNWMuMzk3LjAzIDEuNjY1LjAyOCAyLjQ4NC4wMjh2LjY0NmMtLjgzNyAwLTIuMTMyLjAwMS0yLjUzLS4wMjh6bTIuNDg0LjAyOGwuNjA1LjAwMS0uMDAzLjY0NmgtLjYwMnYtLjY0NnptLjYwNS4wMDFjLjc2My4wMDUgMS4zNjgtLjAzIDEuNzY4LS4yNTZsLjMxOC41NjNjLS41MjcuMy0xLjIyNS4zNDQtMi4wODguMzRsLjAwMy0uNjQ2em0xLjc2OC0uMjU2Yy4zNjUtLjIwNy41ODQtLjYxNC42NC0xLjM3NmwuNjQ2LjA0NmMtLjA3MiAxLS40MDUgMS41NzUtLjk2NyAxLjg5NHptLjY0LTEuMzc2Yy4wMjgtLjQuMDM1LS42MjUtLjAxLS44MjVsLjYzLS4xNGMuMDYyLjI4My4wNTcuNTYuMDI1IDF6bS0uMDEtLjgyNWMtLjA0NC0uMi0uMTQ4LS40MDgtLjM0LS43NWwuNTY2LS4zMTZjLjIyLjM5NC4zNDMuNjQzLjQwNS45MjZ6bS0uMzQtLjc1bC0uMDQtLjE1LjMyMy0uMDA4em0tLjA0LS4xNWwtLjAzNy0xLjM5Mi42NDYtLjAxNS4wMzcgMS4zOTJ6bS0uMDM3LTEuMzkybC0uMDM3LTEuNC42NDYtLjAxNS4wMzcgMS40em0tLjAzNy0xLjRhNS42NCA1LjY0IDAgMCAwLS4xNjYtMS4yODZsLjYyNi0uMTU3YTYuMzIgNi4zMiAwIDAgMSAuMTg2IDEuNDI4em0tLjE2Ni0xLjI4NmMtLjEtLjQtLjI0Ny0uNzgzLS40NDctMS4yNmwuNTk2LS4yNS40NzcgMS4zNTJ6bS0uNDQ3LTEuMjZsLS4zOC0uOTgzLjYwNi0uMjIyLjM3Ljk1NnptLjIyNS0xLjIwN2wtLjMwMy4xem0tLjYwNi4yMjVsLS42MjctMS41LjU3OC0uM2MuMjc2LjU0NS40NjMgMS4wNDguNjU1IDEuNTY2em0tLjYyNy0xLjVsLS4wMy0uMi4zMTguMDU2em0tLjAzLS4ybC4wOC0uNS42NC4wOC0uMDguNTN6bS4wOC0uNWwuMDU2LS41Mi42NDYuMDUzLS4wNjMuNTQ4em0uMDU2LS41MmwuMDYtLjY3Ni40ODcuNDctLjIyNC4yMzR6bS41NDYtLjIwN2wuOTUuOTE1LS40NDcuNDY3LS45NS0uOTE1em0uOTUuOTE1bC43LjY4NC0uNDQ3LjQ2Ny0uNy0uNjg0em0uNy42ODRjLjUxMi40OTQuOTguOTQyIDEuNSAxLjI1bC0uMzI4LjU1OGMtLjU4Mi0uMzQzLTEuMDc3LS44MTgtMS42Mi0xLjM0em0xLjUgMS4yNWEzLjA4IDMuMDggMCAwIDAgMS43OTUuNDNsLjAzLjY0NmEzLjcxIDMuNzEgMCAwIDEtMi4xNTQtLjUxOXptMS43OTUuNDNjLjgtLjAzNyAxLjY0My0uMzc2IDIuMzUzLS45bC4zODQuNTJjLS44MDguNTk2LTEuOC45ODMtMi43MDYgMS4wMjZ6bTIuMzUzLS45Yy42NzctLjUgMS4yMTctMS4xNjIgMS40MzYtMS44ODNsLjYyLjE4N2MtLjI2Mi44Ni0uOSAxLjY0LTEuNjcgMi4yMTZ6bTEuNDM2LTEuODgzbC4yMjctLjc0Ny42Mi4xODctLjIyNy43NDd6bS4yMjctLjc0N2wuMjY0LS44Ny42Mi4xODctLjI2NC44N3ptLjI2NC0uODdsLjA4NC0uMjc3LjI4NC4wNTQtLjA2LjMxN3ptLjM3LS4yMjNjMS4zLjI0NyAyLjczNC4zMzQgNC4xMDMuMmwuMDYzLjY0Yy0xLjQzMi4xNS0yLjkyLjA2LTQuMjg1LS4xOTh6bTQuMTAzLjJjMS4yMDMtLjEyNiAyLjM2NC0uNDMyIDMuMzYtLjk2NGwuMzAzLjU3Yy0xLjA3Mi41NzItMi4zMTUuOS0zLjYgMS4wMzV6bTMuMzYtLjk2NGMxLjQ2LS43OCAyLjU2LTEuOTMyIDMuMzUtMy4zbC41Ni4zMmMtLjg1IDEuNDctMi4wMyAyLjctMy42MDYgMy41NXptMy4zNS0zLjNsLjI4LjE2LS4yOC0uMTZ6bTAtLjAwMWMuOTAzLTEuNTY0IDEuNC0zLjQgMS42LTUuM2wuNjQuMDZjLS4yMDIgMS45OTMtLjczMyAzLjkzLTEuNjgyIDUuNTczem0xLjYtNS4zYy4xNTctMS41NS4wNy0zLjY2Mi0uMjU0LTUuNzA1bC42MzYtLjFjLjMzMyAyLjA5NS40MiA0LjI2OC4yNiA1Ljg2N3ptLS4yNTQtNS43MDVjLS4yODYtMS44MDItLjc1Ni0zLjU0NS0xLjQwNi00Ljc4OGwuNTczLS4yOThjLjY4IDEuMzA0IDEuMTcyIDMuMTE3IDEuNDcgNC45ODV6TTYxLjYgMTcuNDk2YTEuMjcgMS4yNyAwIDAgMC0uMjQ0LS4zMWwuNDUyLS40NjJhMS45NyAxLjk3IDAgMCAxIC4zNjUuNDc1em0tLjI0NC0uM2EzLjA5IDMuMDkgMCAwIDAtMS4xMTUtLjY3OWwuMi0uNmEzLjc2IDMuNzYgMCAwIDEgMS4zNTcuODI4em0tMS4xMTUtLjY4Yy0uMzk2LS4xMzYtLjc5NC0uMTc0LTEuMDgtLjAyNWwtLjI5OC0uNTczYy40Ni0uMjQgMS4wMzgtLjIwMiAxLjU4Ni0uMDEzem0tMS4wOC0uMDI1YS42NC42NCAwIDAgMC0uMTY1LjEyMmwtLjQ2Mi0uNDUyYy4xLS4xLjItLjE4LjMzLS4yNDN6bS0uMTY1LjEyMmMtLjI2NC4yNjgtLjQ5Ni42MDctLjczLjk0NmwtLjUzMy0uMzY0Yy4yNS0uMzY3LjUwMi0uNzMzLjgtMS4wMzR6bS0uNzMuOTQ2Yy0uMzA2LjQ0Ny0uNjEzLjg5NS0xIDEuMjM1bC0uNDItLjQ5MmMuMzM2LS4yODcuNjE3LS42OTguODk3LTEuMTA2em0tMSAxLjIzNWMtLjQ4Ny40MTYtMS4wNS42NDItMS41NzUuODUybC0uMjQtLjZjLjQ3Ny0uMiAxLS4zOTcgMS4zOTYtLjc0NHptLTEuNTc1Ljg1MmwtLjIzOC4wOTYtLjI0NS0uNTk4LjI0My0uMDk4em0tLjIzOC4wOTZsLS4zLjEyNy0uMTE3LS4zMTUuMzAzLS4xem0tLjQyNS0uMTg4YTguMzIgOC4zMiAwIDAgMC0uNzYyLTEuNTQybC41NDgtLjM0M2E4Ljk2IDguOTYgMCAwIDEgLjgyIDEuNjYzem0tLjc2Mi0xLjU0MmExMi4yMyAxMi4yMyAwIDAgMC0xLjAxMy0xLjM3bC40OTUtLjQxNGExMi44OSAxMi44OSAwIDAgMSAxLjA2NiAxLjQ0MXptLTEuMDEzLTEuMzdhNS4yNCA1LjI0IDAgMCAwLS44Ny0uODNsLjQtLjUxM2MuMzQuMjU4LjY1Mi41NDYuOTc0Ljkzem0tLjg3LS44M2MtLjMwMi0uMjMtLjY0NC0uNDQ1LTEuMDQ0LS42OTZsLjM0My0uNTQ4IDEuMDkyLjczem0tMS4wNDQtLjY5NmMtMS4xMjctLjcwNi0yLjA3LTEuNTM0LTMuMDM1LTIuMzhsLjQyNC0uNDg3Yy45NDMuODI4IDEuODY4IDEuNjQgMi45NTQgMi4zMnptLTMuMDM1LTIuMzhsLTEuMjczLTEuMDkyLjQxMi0uNSAxLjI4NSAxLjEwNXptLTEuMjczLTEuMDkyYy0yLjEzNC0xLjc2LTQuMS0yLjYxMy02LjItMi43NDVsLjA0LS42NDZjMi4yNC4xNCA0LjMzNiAxLjA0IDYuNTgyIDIuOXpNNDAuODMgOC45Yy0yLjExNS0uMTMzLTQuMzc2LjQ2LTcuMDYgMS42bC0uMjUtLjU5NmMyLjc3NC0xLjE2OCA1LjEyNS0xLjc4IDcuMzUtMS42NHptLTcuMDYgMS42Yy0xLjI2NS41MzItMi4yIDEuMTU4LTMuMDEzIDEuOWwtLjQzNy0uNDc1Yy44NjYtLjggMS44Ni0xLjQ2NyAzLjItMi4wM3ptLTMuMDEzIDEuOWMtLjgxOC43NTctMS41MjIgMS42NS0yLjMgMi43MDZsLS41MTgtLjM4NmMuODA4LTEuMDggMS41MzItMiAyLjQtMi43OTV6bS0yLjMgMi43MDZsLS4xLjEyMi0uMTUuMDA4LS4wMTYtLjMyM3ptLS4yNDIuMTNjLS40NS4wMjMtLjgyNi4wNzgtMS4yLjIyN2wtLjI0LS42Yy40NTMtLjE4LjktLjI0NiAxLjQwNy0uMjczem0tMS4yLjIyN2MtLjM4LjE1Mi0uNzcyLjQwNi0xLjI1LjgzbC0uNDI3LS40ODVjLjU0LS40NzcgMS0uNzY3IDEuNDM4LS45NDZ6bS0xLjI1LjgzbC0xLjA2Ni45ODgtLjQ1LS40NjUgMS4xMDYtMS4wMjJ6bS0xLjA2Ni45ODhsLS4yMjUtLjIzNC4yMjUuMjMyem0tLjAwMS4wMDFsLTEuMDI4IDEuMDM1LS40NjctLjQ0NyAxLjA1LTEuMDU1em0tMS4wMjggMS4wMzVsLS4xODMuMDk1LS4wNS0uMzE4em0tLjE4My4wOTVjLTIuNTI2LjQwMy00LjU3My44NDQtNi40MDIgMS41NTNsLS4yMzItLjYwNGMxLjg3LS43MjQgMy45NTgtMS4xNzUgNi41MzMtMS41ODZ6bS02LjQwMiAxLjU1M2MtMS44MTMuNzAyLTMuNDEzIDEuNjctNS4wNTggMy4xM0wxMS42IDIyLjZjMS43MDctMS41MTMgMy4zNjgtMi41MTggNS4yNTMtMy4yNDh6TTEyIDIzLjA4YTEzLjE4IDEzLjE4IDAgMCAwLTEuNzQzIDEuODdsLS41MTMtLjRhMTMuODIgMTMuODIgMCAwIDEgMS44MjktMS45NjN6bS0xLjc0MyAxLjg3Yy0uNTAyLjY1Ny0uOTMzIDEuMzUzLTEuMzEyIDIuMWwtLjU3Ni0uMjkzYTE1LjA3IDE1LjA3IDAgMCAxIDEuMzc1LTIuMnptLTEuMzEyIDIuMWwtLjA0OC4wNy0uMjQtLjIxNnptLS4wNDguMDdMNy43NyAyOC4yOTJsLS40MzItLjQ4MmMuMzgtLjM0Mi43My0uNzM0IDEuMDgtMS4xMnpNNy43NyAyOC4yOTJjLS40MTIuMzctLjg2LjY4Ny0xLjM3Ni44ODZsLS4yMzItLjYwNGMuNDMtLjE2Ni44MTYtLjQ0IDEuMTc3LS43NjV6bS0xLjM3Ni44ODZINi40bC0uMTE1LS4zMDJ6bS0uMDAxIDBjLS40MTUuMTYtLjYxNy4yNC0uODQ3LjE0MmwuMjUtLjU5NmMuMDEuMDA0LjExNS0uMDUzLjM2Ny0uMTV6bS0uODQ3LjE0MmgtLjAwMWwuMTI2LS4yOTctLjEyNS4yOTh6bS0uMDAxLS4wMDFjLS4yNDItLjEwMy0uMy0uMzAyLS40Ni0uNzAybC42MDYtLjIyNWMuMDg1LjIyNy4wODMuMzI0LjEwNi4zMzN6bS0uNDYtLjcwMkw1IDI4LjM5MmwuMTk0LS4xNDYuMTkzLjI2em0uMS0uMzdjLjU5NC0uNDQ2LjY1LTEuMzM1LjcwNC0yLjJsLjY0Ni4wNGMtLjA2MyAxLS4xMyAyLjA0LS45NjQgMi42Njh6bS43MDQtMi4ybC4wMi0uMzA4LjY0Ni4wNDYtLjAyLjMwM3ptLjAyLS4zMDhsLjAyMy0uMzE1LjMxNS4wMTUtLjAxNS4zMjN6bS4zMzgtLjNjLjUzMy4wMjUuNzc2LjQgMS4wMzguODA3bC0uNTQzLjM1Yy0uMTY3LS4yNi0uMzIzLS41LS41MjUtLjV6bTEuMDM4LjgwN2wuMjI4LjMzLS41MDUuNGE0Ljc3IDQuNzcgMCAwIDEtLjI2Ni0uMzgzem0uMy42bC0uMTQ4LjY2LS40Mi0uNTMuMjUyLS4yem0tLjYzLS4xNGMuMS0uNDg4LjE5My0xLjEyOC4wNzUtMS42NTJsLjYzLS4xNGMuMTQ0LjY0LjA1MiAxLjM3OC0uMDcyIDEuOTMyem0uMDc1LTEuNjUyYy0uMDc1LS4zMzMtLjIzNi0uNjItLjUzNS0uNzc0bC4yOTUtLjU3NmMuNDk0LjI1Ni43NTQuNy44NjggMS4yem0tLjUzNS0uNzc0bC0uMjU2LS4xMzIuMS0uMjY4LjMwMy4xMTJ6bS0uMTU1LS40bC4yLS40ODcuNi4yMzUtLjE4My40Nzd6bS4yLS40ODdsLjI5Ni0uNzg1LjYuMjEyLS4zMDYuODA4em0uNTQ3LS45OTdsLjU0Mi0uMDk0LS4xODIuNTE4LS4zMDYtLjEwNnptLjEuNjM2Yy0uNjI2LjEtMi4wMDQuODgyLTMuMDA0IDEuOTJsLS40NjctLjQ0N2MxLjEtMS4xMzMgMi42NDItMS45ODUgMy4zNjMtMi4xem0tMy4wMDQgMS45MmMtLjM2My4zNzYtLjY3Ljc4My0uODY0IDEuMTk3bC0uNTg2LS4yN2MuMjMtLjQ4OC41NzctLjk1My45ODMtMS4zNzR6TTMuMzIgMjYuMTVjLS4xODUuMzk1LS4yNy44LS4yMDIgMS4xOTJsLS42MzYuMWMtLjA5Mi0uNTMyLjAxNC0xLjA2My4yNTItMS41N3ptLS4yMDIgMS4xOTJjLjA2Mi4zNTcuMjUzLjcxNS42MTQgMS4wNjNsLS40NDcuNDY3Yy0uNDY4LS40NS0uNzE4LS45My0uODAzLTEuNDJ6bS42MTQgMS4wNjNsLjEuMTU2LS4zMTMuMDc3em0uMS4xNTZsLjIzNi44Ny0uNjE2LjE5Mi0uMjQ2LS45em0uMjM2Ljg3YTQuOTkgNC45OSAwIDAgMCAuMjY1LjY4MWwtLjU4My4yNzhhNS42MyA1LjYzIDAgMCAxLS4yOTgtLjc2N3ptLjI2NS42OGMuMjMyLjQ4My42Ljc3OCAxLjAyNC45MTRsLS4xOTcuNjE2Yy0uNTg2LS4xODgtMS4wOTMtLjU5Mi0xLjQtMS4yNTJ6bTEuMDI0LjkxNGMuNDk0LjE2IDEuMDcuMSAxLjYwNy0uMWwuMjM1LjZjLS42NzIuMjYyLTEuNC4zMi0yLjA0LjExNXptMS42MDctLjFsLjU2LS4yMi0uMTI4LjU4Ny0uMzE2LS4wNjh6bS40MzMuMzdjLS4xNTIuNjk4LS4yNDQgMS40My0uMjc1IDIuMjU3bC0uNjQ2LS4wMjNhMTMuMzEgMTMuMzEgMCAwIDEgLjI5LTIuMzcxek03LjEgMzMuNTZjLS4wMy44MjcuMDAxIDEuNzU1LjA5NCAyLjg0NWwtLjY0Ni4wNTNjLS4wOTUtMS4xMDUtLjEyNi0yLjA1Ny0uMDk0LTIuOTJ6bS4wOTQgMi44NDVsLjA4NS43NjctLjY0LjA4Ni0uMDkzLS44em0uMDg1Ljc2N2wuMTMyLjgtLjYzNC4xMi0uMTM3LS44MjR6bS4xMzIuOGwtLjAxNC4xNzItLjMwMy0uMSIvPjxnIGZpbGwtcnVsZT0iZXZlbm9kZCI+PHBhdGggZD0iTTIzLjU4NiAxOC41OTRsLTQuMjU1LjctMy44ODMgMS43MDItMy4yOTggMi4wNzQtMy4xMzggMy44My0xLjc3MyAxLjg3OC0xLjcxNC42MzItLjQ1My0xLjEwOC43OTMtMS4xNDQuMTc4LTEuNjE0LjUzLjAyLjU4LjUzLS4xNTYtMS42NDQtLjY0My0uNDMuMDItLjYyNi0xLjUyMy44NjItMS4zOCAxLjYyOC0uMjg4IDEuNDU1LjYgMS4xNjUuNTUgMS45OCAxLjEyLjUzIDEuMTc3LS4wNTggMS4xMTYtLjY1TDcgMzQuMDcybC43NDUgNC4yMDItLjgyIDEuOTQtMi42ODUgMi44OTIuNDc3IDEuNzI4TDYgNDYuODM3bDIuMzk4IDEuNjg4IDEuMjcyLjE3NCAxLjQxNC4wNDgtLjg4MiAzLjYyMiAzLjI0NCAxLjMzIDQuMDQyLjUzMiAxLjM4My0uOTA0LjEwNi0yLjQ0NyAxLjU0My0yLjU1My4xMDYtMi4wMiAzLjcyMy4yNjYgMy40NTctLjMyLTMuNDU3IDIuMDc0LjU4NSAyLjUgMi4xOCAzLjQwNCAyLjEyOC45MDQgMS43MDItLjcuNy0xLjM4MyAzLjU2NC0yLjcxMy43LjU4NSA1LjU4NS4yMTMgMS4xMTctLjkwNC4xMDYtMS41OTYtLjM3Mi0uNy0uMjY2LTQuMzA4LTEuODYyLTMuNzIzLjMyLTEuNjUgMS4xMTcuNTg1IDMuMTM4IDIuOTI1IDEuNTQyLjEwNiAxLjcwMi0uNyAxLjcwMi0xLjI3Ni44NS0yLjc2NiA1IC4zMiAzLjAzMi0xLjE3IDIuNDQ3LTIuMjg3IDEuNzU1LTMuMjk4LjQyNi0zLjg4My0uMzcyLTQuNTItLjk1Ny00LjA0Mi0uOTU3LTEuMjc3LTEuMzMtLjQyNi0yLjM0IDIuNTUzLTIuMTI3Ljc0NS0xLjg2Mi0zLjA4NS0xLjg2Mi0xLjcwMi0xLS42MzgtNC4wNDItMy4zNS0zLjI0NC0xLjc1NS0zLjI0NC0uMjY2LTMuNzc2LjYzOC0zLjI5OCAxLjIyMy0yLjI4NyAxLjg2Mi0xLjgwOCAyLjE4LTEuODYyLjUzMnoiIHN0cm9rZS1taXRlcmxpbWl0PSIxMCIgZmlsbD0iI2ZlZWI1MCIgc3Ryb2tlPSIjMWYxOTE3IiBzdHJva2Utd2lkdGg9Ii4wOTUiLz48ZyBmaWxsPSIjZmRmN2JhIj48cGF0aCBkPSJNMTEuMjQ1IDI4LjE5NkM3LjYgMzIuNDQ3IDguNCAzNy42MDMgOS40MiA0Mi42NTVMNy44MDMgMzguNTdsLS41OTYtMy43NDYuMTctMy44MyAxLjUzMi0zLjY2IDIuMy0zLjQwNSAzLjU3NS0yLjk4TDE4LjcgMTkuMzNsNC41OTctLjU5Ni00LjI1NiA0Ljg1MmMtMy40MTcgMS4xMDgtNS40MzMgMS44NTUtNy43OTQgNC42Ii8+PHBhdGggZD0iTTI4LjQwMiAxNS4yNDNjLTIuNTM0IDIuNDcyLTMuOTE4IDQuMzM3LTUuNTMgNy4yM2wtMy42NiA2LjEwNmMtLjYxMyAxLjAzMy0uNjcgMS45LS44NTUgMy4wOTJsLTEuNzg4LTIuMTI4Ljg1LTIuNTU0IDIuODk0LTUuMTkzIDYuMTMtNi4wNDQgMS45NTgtLjVtMTIuNTE1LTYuMTNjLTIuMDMuNzYtNS40IDEuMDEyLTUuNjM0IDMuMzQtLjE2NyAxLjY1NC4xMjUgMi40ODUgMS4xMjIgNC4yMzUtMi40NjMtMi41NDgtMy4wNzItMi4xNTQtNy44My0xLjM2MmwyLjA0My0yLjg5NCAzLjU3NS0yLjIxMyA0LjU5Ny0xLjAyMiAyLjEyOC0uMDg1Ii8+PC9nPjxnIGZpbGw9IiNlZGQ3NDkiPjxwYXRoIGQ9Ik00Ni41MTUgNDAuNjJjLjY3Ni40MTcuNjYuNzIuNTQ4IDEuMDA1bDEuNi0uNjQgMS4wMzYtMS40Ljc3LTEuOTgyLS45ODItLjc0LTQuMjk0LjU0OC0uMzIuODY4LjEgMS4yMzMuNC43My42NC4zMi41MDMuMDQ2bS0uNC03LjM0Yy0yLjE1Mi42Mi0yLjEzNi43OTItMi43NyAyLjkyOC44NC0xLjM0NiAxLjQ2LTIuMDI2IDIuNzctMi45MjhNNjAuNDMgMTcuM2MtLjM4My4xNzctLjc1NS4yNjItLjk5NC42MTItLjUxNS43NTMtLjk1NiAxLjM4Ny0xLjgwOCAxLjkxNi0uNDMuMjY2LS44NzIuNDQtMS4zMjcuNTgtLjM3Ny4xMTctLjYwNC4wMTMtLjkyNS4yNDNsLjU3LjFoMS4yNmwxLjU1My0uOTYuOTE0LS45Ni43NTYtMS41MzNtLTM0LjI4NiA0Ljc3N2MtLjg0NyAyLjMxNy0xLjU4NyA0LjMwMy0yLjg3IDYuNGExOS4xNyAxOS4xNyAwIDAgMCAzLjU4Mi01LjI4Yy4zNjYtLjc3OC40MzUtMS43IDEuNDUzLTEuMzUuMDQ2Ljc3Ny4yIDEuNTUzLjI1NiAyLjMzLjU1LTMuOTQ1IDIuMTAyLTUuNTk1IDUuNy03LjEyNmwtMy4wNi4zNjUtMi44NzguNjRMMjYuOSAyMC4xbC0uNzc3IDEuOTY0bTctLjA4Yy43NzggMy42NjIgMS44OTggNy4xNzYgMi4zODUgMTAuODk2LjMxNiAyLjQxNy4zNSAzLjU3OC0uODY2IDUuNjY0LTEuMzMtLjA4Ni0yLjE1NC4wNjQtMy40NC40ODUtNS4xMTggMS42NzgtOC4wNTMgNC4xNDUtMTEuNTAyLS44MjZsMy4zMDMgMS41NTYgMi4zNTQtLjQ2MyA0LjE1Ny0yLjQyIDMuMjQzLS42NCAxLjA1LTQuMzg1LS43NzctNS44MDItLjEtMi43NC4xODMtMS4zMjVtOC44MTMgMjIuNjU3Yy0uNDMgMi45NzUgMSA0LjU3NC40MDIgNS4zOTYtLjE2Ny4yMzMtLjM5Mi42MzgtLjY0NC43NS0uOS4zOTctMi4xMzYtLjA3NC0yLjIyNS4xNThIMzYuNWwtMS4xODgtLjUwMyAxLjgyNy0yLjE0NyAxLjc4Mi0zLjg4MyAxLjE0Mi0zLjkyOGguNTk0bDEuMjggNC4xNTciLz48cGF0aCBkPSJNMzYuOTU2IDM1Ljk5M2MuMjQgMS4zNS42NiAxLjY3MiAxLjI5NSAyLjk4LS40MjMgMi4xMzMtMS4xMDIgNC42Ny0xLjkyIDYuNTUyLS4zNDUuNzk0LS42MjMgMS4yMy0xLjIzIDEuODQ1LTEuMDI2IDEuMDM2LTIuMDY0IDEuOTQtMy4yMjggMi44MzgtLjgzOC42NDYtMS40MjMuMzIyLTIuNDU2LjE3Ni0uNDQuNzk3LS41NiAxLjI0LTEuMzcgMS42NDQtMS4yNDQuNjIyLTIuMzU4LS43Mi0zLjMzNS0xLjUwN2wyLjExNSAzLjMwNCAxLjQ2MiAxLjM3IDEuMjMzLjE4MyAxLjY0NC0xLjAwNS44NjgtMS42NDQgMS44MjctMS4zNyAyLjIzOC0xLjkyIDEuNDE2LTIgMS4yOC0yLjM3NSAxLjY0NS00LjkzMy4xMzctMS44NzMtMi4wNTYtLjkxNC0xLjU2NS0xLjM0TTIwLjU3IDQ1LjUwOGMyLjMwNiAwIDQuNzQtLjEyOCA2Ljg1Mi0xLjA5Ni41OTgtLjg5NyAxLjE4Ny0xLjYzIDEuOTItMi40Mi0uNjY1IDEuMjU3LS44NzQgMS45NjctMS4wNSAzLjM4bC0uNjg1IDEuMDA1LTUuMjA3LjEzNy0xLjctLjE4My0uMTgzLS4xODMuMDQ2LS42NE0yMC4yNSA0My45bC0uMTgtMS42MjJjLS4zOTQgMi4zNy0uMyAzLjk2LTEuNCA2LjA4NC0uODE1Ljk0NC0xLjgyIDEuODA0LTIuOTY4IDIuMjY0LjA5Ny41ODIuMTI2Ljk0Ni4wNyAxLjM3My0uMjAyIDEuNTM2LTMuMjc1Ljg1Ny00LjUzOC43OTZsNi4wODIgMS41NjYgMS4zNy0uNTQ4LjQ1Ny0yLjY1IDEuMjgtMi4zNzUuMjI4LTEuNDYyLS40LTMuNDI2bS0zLjQxNy0xMy4zNzVjLS4wNjQgMS4xNTMtLjEzOCAxLjYzMy4zNyAyLjY1Mi42NDYgMS4yOTQgMS40NCAyLjUgMi4xNDIgMy44bC4yMjgtMi41NTgtMi43NC0zLjg4M20tOS4zODcgOC42OThsLS41OTMgMS4yNjNjLjU0NCAxLjgzMyAxLjAyOCAyLjk5NSAyLjA2NCA0LjU5Ni0uMTguNjUtLjMxNi45MzMtLjczIDEuNDYyLS45MTItLjE0LTEuNzIyLS4xOC0yLjY0Ni0uMTc4bDMuMDYgMi4zNzUgMS41MDctLjI3NCAxLjUwNy0xLjUwNy0yLjE0Ny0zLjMzNS0yLjAyMy00LjQwMk02MC40MzMgMTYuN2MuNjIgMi43OTYgMS40MjMgNS4zNzUgMS4zNDggOC4yMzgtLjEgMy41MTItLjc3NiA3Ljk1LTQuMDMgMTAuMDY4LTMuNjQ1IDIuMzcyLTcuOTIzIDEuMjUtMTEuOTIyLjIzNGw0Ljg4OCAyIDQuNTY4LjIyOCAzLjEwNi0uOTE0IDIuNDItMiAxLjgyNy0zLjgzNy42ODUtNC40My0uNTQ4LTQuMzQtMS4wMDUtNC4yOTQtMS4zNC0uOTUyTTYuMDQ1IDI1LjAyQzQuNCAyNi4xIDMuNzQgMjYuNTcgMy45MjIgMjguNTY3bC40OTUgMS43OTMuNy40NzQuODY2LjI4OCAxLjU2Ny0uMzcuODA0LTIuNDk0LTIuMjI2IDEuMDkzaC0uNTE1bC0uNTc3LS44ODYuNy0xLjAzLjM3LTEuOTU4LjQ3NC4xNDQuNTc3LjQ1NC0uMDgzLTEuMDMtLjM5Mi0uNjYtLjM5Mi0uMzMtLjI0Ny45N000My4xNjUgOS4yOThjMS40NjggMS4zNjQgMy4yNyAyLjU1IDQuNDQ1IDQuMjE1LjQ1NS42NDUuOTYuOTc1LS4wMDggMS44ODYgMS4wMjItLjI5MiAxLjQwMi0uMjYgMi4yMi0uMTYgMS40ODguMTggMi44ODMgMi4yOTYgMi45NzIgMy44MTItLjAxOC4xNDItLjQxMy40NjQtMS41NjQuNzgtLjAyMy4wNDQtLjY1LS4wODYtLjYzNC0uMDQzLjEyLjMyNy4yOC4zNzcuNTIzLjUzLjA1My4zNjQuMDg3LjkyNS4zMzUgMS4zMjNhOS45OCA5Ljk4IDAgMCAxIDIuMTQuMjA3Yy4yNC4zOTYuMjAzLjc5Mi4xODMgMS4xODhsLjgyMi0uMTM3LS4yMjgtMS44NzMuNzMtMS4yMzMtMS4wNS0yLjM3NS0yLTEuOTItLjE5NC0uMDEtMi4yNi0xLjM4Ny0zLjY4Ny0zLjAxNi0yLjczNy0xLjc4N20yLjQ2NSAxMS4yNTJjLS4wNzcuMTM1LS4xOTQuMzUyLS4zNDQuNTAyLjYxMi41OC45MTMuOTY2IDEuMTMgMS43ODRsLTIuMDc0IDEuMDMtMS43NTUgMS42ODNjLS43Ny0uNDE1LS45NjItLjczMy0xLjMzNS0xLjUyMy0uNDM0LjExNS0uODQ1LjIyNS0xLjIwMy4wOTQuMjI3LjAwMi4zNjctLjA1NS41OTQtLjE5NmwxLjExNy0xLjE2IDEuOTczLTEuNDk0IDEuMy0uNDJjLjE2NC0uMDY4LjQ0LS4yMy42MDUtLjMiLz48cGF0aCBkPSJNNDcuNTUgMjIuNjE0QzQ1LjM1IDIzLjggNDMuMjQ0IDI1IDQyLjEyIDI3LjI0YzAtMi44NTUgMi44NjctNC4xMTIgNS40MzItNC42MjVtLTUuODcyLTUuNjE4Yy0xLjYzMyAxLjExNC0yLjc4OCAzLjM2LTIuNjQzIDUuNTUyLS41MzItMS44OTctLjM0NC0zLjcgMS4zLTVsLjgyNy0uNDAyLjUyNi0uMTUiLz48L2c+PHBhdGggZD0iTTQ0LjggMzMuOTA1bDEuMjg4LS42Mi0xLjMxNy4yNDVjLS45MjguMTU3LTEuMDM3LjM4LTEuMTggMS4yOTNsLS4yMyAxLjM5NC42MTMtMS41MTZjLjIyNC0uNS4zNS0uNTM3LjgyNi0uNzk2em0tMTcuMi0yMy41MmMuNzMtMS4wOTMgMS4xNS0xLjQ1IDIuMjctMi4xNDItMS41MjMuMzY3LTEuODE0LjY1LTIuMjcgMi4xNDJ6bS0uMjQgMi40YzEuMjc2LTIuNTY0IDIuMjQyLTMuNSA0LjkxMi00Ljc2OC0zLjAyLjc0LTMuOSAxLjI2Ny00LjkxMiA0Ljc2OHpNLjAzMiAyNi4xNGMuMjgtMS4yODQuNTQtMS43NyAxLjMzMy0yLjgyM0MuMDggMjQuMjE1LS4wODcgMjQuNTg0LjAzMiAyNi4xNHptMjguNTkzIDIxLjQ5MmwtLjExNi0uOTM1Yy0uMDctLjU2NS0uMDY3LTEuMDIzLS4wMjItMS41OTJsLjEzLTEuNjVjLS4xNi41Ni0uNDggMS4xMTgtLjY0IDEuNjc3bC0uMTQ3LjU3MmMtMi40LjQ4OC00Ljc2My41Mi03LjE1NC4wOTJsLS40OTQtMi40N2MtLjA0Ny43NC0uMDE3IDIuNzg4LS4wMiAzLjkzNC0uMDAzLjg4OC0uMDQgMS4xOTItLjQ5OCAxLjk0OC0uNDMuNzA3LS42Ljg2OC0xLjIgMi4wNjMuMDUuNzU0LjA1IDEuMjUzLS4xNSAxLjk2OC0uMzMzIDEuMi0zLjY5NC4yNjgtNC41OC4wMjUtMS4wOTItLjMtMy4zNS0uNzQzLTIuNzgyLTIuMi41LTEuMjguODE2LTIuNjMyIDEuMDYtNC40MjQtMi0yLjg4Mi0zLjg2LTYuODMtNC4yMTgtMTAuMzMtLjI3Ny0yLjcxNy0uMS00LjQuNDc3LTYuMDUuOTMyLTIuNjMzIDIuMjM1LTQuOTEyIDQuMzI2LTYuNzQ4IDIuODItMi40NzUgNS40NTgtMy40NyA5LjU4Ni00LjA5OC0uOTkzIDEuMS0xLjk3NSAyLjI4Ny0zLjA0NiAzLjU0Ny0xLjA4NCAxLjI3Ni0xLjcyOCAyLjU2NC0yLjQxNiAzLjk2LS45NSAxLjkyNy0uOTMgMi42Ni4zMyA0LjM1MyAxLjA4NiAxLjQ1OCAxLjY3MiAyLjExNSAyLjE0NyAzLjU0LS4zOTIuODA3LS41MzQgMS41LS42NjYgMi41OTIgMS4zMyAxLjQ1MyAyLjMxOCAyLjQ1IDMuNiAyLjc1NyAxLjI2Ni4zIDIuMzI0LjI0MyAzLjQ1Ny0uMzM2IDIuNTE3LTEuMjg3IDQuODQ1LTIuOTQ4IDcuNjg0LTMuMDE3IDEuMzEzLTMuMjMgMS4xOC01LjkyNy41NS05LjA1LS40My0yLjEzMy0uNjAzLTQuMTUzLS43MzctNi4zMy0uNTMyIDIuMjQtLjYzMiA0LjItLjIzNyA2LjQ0LjQ3NiAyLjcuODQ2IDUuNjYtLjQ3OCA4LjAyMy0yLjU2Ny4xOTctNC43NjcgMS43NTgtNy4wOCAyLjk1Ni0uOTMuNDgyLTEuODk4LjUzLTIuOTI3LjI0Ni0uOTU1LS4yNjItMS42LS44OTQtMi42My0yLjA4Mi0uMDE2LTEuMTkyLjI1My0xLjc0Mi44LTIuODIuODgtMS43MzMgMS44NS0zLjM0NyAyLjkxNS01LjA1My0xLjMwNCAxLjU3NC0yLjU0IDIuOS0zLjU2NyA0LjQ3My0uMzkyLTEuMTE4LS45NTMtMS42ODYtMS44ODMtMi45NDQtLjkwOC0xLjIzLTEuMDAzLTEuNzY4LS4zMjQtMy4yczEuMjYtMi42ODcgMi40MjMtMy45NGMyLjAwNy0yLjE2OCAzLjg0Ni00LjU4IDYuMDQtNi43MTUgMS4xOTItMS4xNiAxLjY3Ni0xLjEyIDMuMjU3LTEuMzYgMS40My0uMjE3IDIuODI0LS41IDQuMjgtLjgzLTEuNC4xMy0yLjc3Mi4xOC00LjE0NC4yMTRsLS4wNDMuMDAxYzEuMzUtMS43MjQgMi4xMzMtMi42ODUgNC4zMjYtMy42MzcgNS4zOTgtMi4zNDQgOC44MjgtMi41OTggMTMuMDY4Ljk2NiAxLjEuOTI0IDIuMDYgMS44MiAzLjE3MyAyLjYxOGE0LjAzIDQuMDMgMCAwIDAtMS4yMTMuMjg4Yy41Ni0uMTA3IDEuMjA4LS4wMDEgMS44LjEwNWExMy45NCAxMy45NCAwIDAgMCAuNTAzLjMxMWMuNzg2LjQ2MyAxLjIzMy43MiAxLjc2NSAxLjQ2LjU2Mi43ODMgMS4wMyAxLjU2NiAxLjQ0NCAyLjQzbC0uNy0uMjRhMS41IDEuNSAwIDAgMC0xLjQyLjA4OGwtLjAzMy4wMTVjLS40MzUuMjEyLTEuMS40NTMtMS41Ni41MjcuMjMuMDguNzQuMS45OC4wMTRhLjcyLjcyIDAgMCAxIC4wOTgtLjAzMSAxLjUgMS41IDAgMCAwLS4wNDEgMS40NTZsLjAwMS4wMDNjLjA0LjA5Ni4wOTcuMTg0LjE2LjI0OGExMi40MyAxMi40MyAwIDAgMC0uNjM0LjI1N2MxLjAwNi0uMTUzIDEuOTEzLS4xOCAyLjg5NS0uMDVsLjIuOTctLjM2NS4wMjgtLjAzLjAwM2MtLjQ2NC0uMzctLjk4Mi0uMy0xLjctLjE0OC0yLjE1LjUtMS42NDUgMS42OTctMi42MzQgMy41MTUgMS4wMjctMS4yNTYuOTUtMi41NyAyLjYyNS0yLjk2NS40LS4wOTIuNjU2LS4yMDguOTItLjE2OC0uNDc1LjI0LS44ODYuNjM1LTEuMDUgMS4wOTUtLjQ2IDEuMjk3LS4xNzQgMi40LS42OCAzLjYwMi42MjUtMS4wODMuNjYzLTIuMTQgMS4yMjItMy4yOC4yLS40Ljk0Ni0xLjA2NSAxLjQwMy0xLjA3NWwuMzc2LS4wMDhjLjEuNzIuMTc3IDEuNDM3LjEzNCAyLjAzLS4wNzggMS4wODQtLjM2IDIuNjkyLS41MjggMy4zMDcuNTY2LS43MjguODI0LTIuMjcgMS4wNzMtMy4zNTUuMjYtMS4xMy4xOTQtMi40ODYtLjAzMy0zLjctLjMtMS42NjYgMS40MDQtMS4zOTUgMi40LTIuMTguNzMyLS41NzcgMS4yMzYtMS41IDEuOTA3LTIuMTUyLjY2Ni0uNjQ3IDEuNzE0LjMwNCAxLjk3Ni45MzcgMS4xMzYgMi43NDcgMS42NTMgNy4wNyAxLjM1MyA5Ljg0LS4zMzcgMy4xMDgtMS44MzggNi41LTQuNTggOC4wMy0zLjQ5NCAxLjk1LTcuNjE0Ljc2LTExLjA4NS0uNC0uNzQtLjI1LTEuMjU2LS42MTMtMS45MDctMS4wMjQuMTc3Ljc5OC4yNTggMS42NDQuMDIyIDIuNDQtLjM3NSAxLjI2NS0uOTggMy4zMzUuNzQgMy43MTcuNjU0LjE0NS45NS4xMjQgMS44NzMtLjM1MmEzLjQ0IDMuNDQgMCAwIDEtMS42MzcuMDMzYy0uNDY1LS4wODYtLjcxMi0uMzgtLjg0Mi0uNzMuMTYzLjExNy40MjguMTguODguMyAxLjI3NC4zMDcgMi40ODctLjMwNiAyLjcyNC0xLjIuMTM4LS41MTYuMTE1LS43ODcuNDA4LTEuNS4yNjMuMDguNTM2LjE1NS44MTUuMjIzbC0uNDczIDEuNTQzYy0uNCAxLjMzNS0yLjAwNCAyLjQxMi0zLjQxMiAyLjM4Ny0xLjMwMi0uMDIzLTIuMTI3LS44MzgtMy4wMjUtMS42MzhsLTEuODA1LTEuNmExMy42OSAxMy42OSAwIDAgMS00LjQyMi0yLjIyMmMxLjA3IDEuMjU3IDEuNzk2IDEuOTU0IDMuMjg4IDIuNTgtLjIxNyAyLjIxNC0uOTg2IDMuODI4LTEuNjQyIDUuOTQ2LS4yOTcuOTU4LTIuNjQgNC43OTYtMy4zIDUuMTctLjQ2My4yNjctMy4zNjQgMi43LTMuOSAzLjAzMi0uNDA2LjU0LS43NjMgMS4yODUtMS4zNzQgMS42MDgtMS44NjIuOTg0LTMuMDU4LS45LTQuMDYtMi40OTMtLjQ1Ni0uNzI1LTEuNzIzLTIuODE0LS42Mi0zLjQgMS4wNDQtLjU1MyAxLjYzLS45NDggMi42OTQtMS42NDcuMTU2LjI4NS40MjUuNTYuNi44NDV6bTYuNDcyIDMuMzc1Yy0uOTQzLjc2LTIuNTI4IDIuMS0yLjgzNSAyLjI3OC0uNTU3LjgzLS42MjYgMS4zNDUtMS41MTggMS44MjgtMi42NTYgMS40MzctNC4wNjUtLjIzLTUuNjM3LTIuNjUyLS43NS0xLjE1NC0yLjM4Ny0zLjgtLjY1LTQuNjgzLjczMi0uMzc2IDEuMjg3LS42NiAxLjg0LS45OC0xLjgyMy4yMjYtMy42MTMuMjMtNS40NzMtLjA1bC4wODUuNjM0Yy4xMiAxLjAxNy4xNiAxLjMyOC0uMzkyIDIuMTQ3LS40MDMuNTk3LS41NTguNzctMS4wNDQgMS44NTZhNS40MSA1LjQxIDAgMCAxLS4xOTkgMi4zMDNjLS41NTMgMi4wNTMtNC4zODguOTI4LTUuOTUuNTA1LTEuODgtLjUwOC00LjU2Ni0uOTgyLTMuNDY0LTMuNC4yNTgtLjU2Ni40Ni0xLjE0Ni42MTQtMS42OTgtMS42NDQuNzI4LTMuOTI4LS44MTYtNS4wMTctMS45MDctMS4wMzUtMS4wMzgtMS41OTctMi4yNDMtMS43OTMtMy40MTItLjE2Ny0uOTk1LS4wMTQtMSAuNjk2LTEuNjk0bDEuOTUtMS45My43ODctMi4xNGMtLjEwMi0uNTMzLS4xNzgtMS4wNjUtLjIyMy0xLjYtLjItMi4xOTUtLjEyNS0zLjc1OC4xODgtNS4xOTYtMS4xNDQuNDQ2LTIuNDU2LjIzNy0zLjA0LS45NzctLjIyMi0uNDYyLS4zNTQtLjkzMi0uNTIyLTEuNjE0LTIuNTUyLTIuNDYgMi4yMy01LjY4IDMuNjI1LTUuOTI0LS4xNi40NTMtLjMzNC44NjgtLjQ4OCAxLjI4Ljk0Ni41LjgzIDEuODg1LjYzIDIuNzg0LS4zNC0uNDMtLjUyOC0xLTEuMDMtMS4wMTUtLjA3MyAxLjAxNi0uMDYgMi4xNC0uODU0IDIuNzM1LjIzNS42MjguMjIzLjYyOC45LjM3Mi45NDgtLjM2NSAxLjY2Mi0xLjE3OCAyLjM4LTEuOTcyLjc3My0xLjUwNyAxLjc2NS0yLjg0NyAzLjEzLTQuMDU2IDMuMzUyLTIuOTcyIDYuNTItMy45NDQgMTEuNjIyLTQuNzU3YTM1LjI5IDM1LjI5IDAgMCAxIDIuMTM0LTIuMDU3YzEuMDItLjkgMS42ODMtMS4wODcgMi42NDgtMS4xMzggMS41OTctMi4xMzYgMi44NTQtMy42MjQgNS40NTctNC43MiA1LjQ1OC0yLjI5NyA5LjIyLTIuNDA4IDEzLjYgMS4yMDQgMS40NDggMS4xOTMgMi42ODIgMi40NSA0LjI3MyAzLjQ0OC44MDUuNTA0IDEuMzguODY3IDIgMS41OTQuNzY4LjkxNSAxLjM5NSAxLjgzIDEuODMgMy4wMDcuNTY0LS4yMzIgMS4yMDctLjQ1IDEuNzI2LS44OTQuNjctLjU3MyAxLjA5Ny0xLjUzIDEuNzE4LTIuMTYuODI0LS44MzUgMi43MDQuMTczIDMuMTIuOTcgMS40MTYgMi43IDEuOTk1IDcuNzAzIDEuNjk0IDEwLjY3Mi0uMzcyIDMuNjctMS44ODUgNy4xNC01LjEyIDguODY3LTIuMiAxLjE3My01LjE1IDEuMjgyLTcuNjc2LjgwNWwtLjUgMS42MTZjLS41IDEuNjE0LTIuNDA4IDIuOTMzLTQuMDgzIDMuMDEyLTEuNjA4LjA3Ni0yLjQ4LS43NTQtMy41MzQtMS43N2wtMS42Ni0xLjZhMTIuMSAxMi4xIDAgMCAxLS4xMzkgMS4wNDhjLjQzNi44Ni42NDUgMS42MTYgMS4wMTggMi41MDMuNC45NzYuNiAxLjYxNy42MzggMi42NjJsLjA3NCAyLjc4M2MuNDE0LjczNS40NS45MTQuNCAxLjc1NS0uMTI3IDEuNzczLTEuMTA0IDEuOTQyLTIuNzMgMS45MzItLjU0Mi0uMDA0LTIuNi4wMS0zLjEtLjAyOC0xLjAzNy0uMDc1LTEuNzItLjE1NC0yLjA3OC0uNTgyem01LjQ4Ny05LjY3MmMtLjMyNyAxLjE3LS43NjcgMi4yNzMtMS4xNyAzLjUzOC0uMzggMS4xOTctMi4zMyA0LjY3NS0zLjQ3NyA1LjUxNy4yMjMuMTY2LjYzMy4yMyAxLjM2NC4yOTQuNTE3LjA0NSAyLjU1NC4wNTQgMy4wNjUuMDYzIDEuMTI2LjAyIDEuNTUzLS4wNjUgMS42NjctMS4zNDcuMDU2LS42MjguMDA3LS43NDUtLjMwNy0xLjI5NWwtLjA4My0yLjk0NWMtLjAyNi0uOTMtLjIwNS0xLjQ2Ni0uNTctMi4zMzQtLjIyLS41Mi0uMzM4LTEuMDAzLS40ODgtMS40OTJ6bS0zNC4zLTE2LjA2Yy4yNTMtLjAzLjQuMTA0LjYwNS4zLS4wMzYtLjQ2Ny0uMTIyLS44MTMtLjQ1LTEuMDA0YTUuNTUgNS41NSAwIDAgMC0uMDY1LjIzIDUuOTggNS45OCAwIDAgMC0uMS40NzZ6bTEuNTg4IDMuMzczYTI0Ljk2IDI0Ljk2IDAgMCAwLS41MSAxLjQ1N2wtLjA3Ni4yNWMtLjk2Mi40MDgtMi4yMjYuNjY3LTIuNy0uMzQ0LS4yMzUtLjUtLjM2OC0uOTcyLS41NC0xLjU5Mi0xLjU4NC0xLjY0Ljc4NC0zLjgwNiAyLjA3My00LjU4My0uMTg3LjQtLjMyLjcwNS0uNCAxLjAxNy0uMzkyIDEuMzU1LjE3NyAyLjU2NC0xLjA1MiAzLjU0Ni41NzggMS4xNjYuNTUgMS42MyAxLjg5NiAxLjA5Mi41Mi0uMjA4Ljk0Ni0uNSAxLjMyOC0uODQ0em0tLjM3IDExLjA0Yy43MyAyLjUyIDEuOTcgNC45OTcgMy4zNDYgNy4wOHYuMDM2Yy0uMDg2LjM1OC0uMTg2LjcwNy0uMzk1Ljk4Ny0uOTg0IDEuMzE2LTMuNDg1LS42MTYtNC4yLTEuMzU1LS43OTItLjgwOC0xLjMyMi0xLjc2Ni0xLjQ0OC0yLjY2My0uMDkyLS42NTUtLjAwMy0uNjcuNDU0LTEuMTM0bDEuODQ4LTEuODcuNDA1LTEuMDh6bTQ2LjU3Ni0yMC4yMzJhMS41MyAxLjUzIDAgMCAxIC4zMzIuNDg3IDEuMjEgMS4yMSAwIDAgMSAuMTM2LS4xMWwtLjE3Ni0uMzg0LS4zLjAwOHpNNDIuMDMgMjRjLS4xMjgtLjI3LS4yLS41NTMtLjE5Mi0uODMzLS40NzIuMzc3LS45ODUuNzM1LTEuNTE4Ljk0LjczNS0uNjU3IDEuNzM0LTIuMjA1IDIuNDU4LTIuNjk0LjgyLS41NTUgMS45MzYtLjQ0NyAyLjg5NC0uOS0uMzI3LjI5Ny0uNzQ2LjUzNi0xLjE3My43NjQuNDcuMTcyLjg3Ni41MiAxLjEwOCAxLjAwNmExLjk3IDEuOTcgMCAwIDEgLjE4LjYzM2MuNjQzLS4yIDEuMjc1LS4zIDEuOC0uMzA0LTEuOS41MzYtMy45NCAxLjgtNS4zNCAzLjQ0OGE0LjQzIDQuNDMgMCAwIDEgLjY0Mi0xLjE3MiAxLjk3IDEuOTcgMCAwIDEtLjg2OC0uOXptLTguODUyLTYuOTA1YTI0LjkyIDI0LjkyIDAgMCAxLTMuMDQzLjk3OGMtLjkzOCAxLjIzMi0xLjUgMS44Ny0xLjcyNCAzLjUyMi0uMjU0LTEuNjI1LS4zMDctMS45MjYuNDE3LTMuMTQtLjIuMTA2LS40MDQuMjUzLS42ODQuNDkyLTEgLjg2NC0yLjMyNyA0LjI2LTIuODU0IDUuNDcyLjMzNC0xLjQ2IDEuMzgtNS4xMTIgMi40NTYtNi4xNzcuNzA4LS43Ljg3LS42ODQgMS44NjctLjc3OGwzLjU2NS0uMzd6bTIyIDMuNTQyYy44NTUuMDggMS4zNDQuMjEzIDIuMS0uMTY2IDEuNDI3LS43MDYgMi40NzctMS44NiAzLjE1OC0zLjIzOC0uNDE3IDEuNjQ1LTEuMjU1IDMuMDQzLTIuOTk0IDMuNjYzLS44NTQuMzA0LTEuNDA1LS4wMS0yLjI3NC0uMjZ6bS0xNi40LjE2Yy4zMjItMS40MjcuODk0LTIuOCAzLjEtMy44NjUtMi45MzcuNzM1LTMuNDg3IDEuOTctMy4xIDMuODY1ek0uNyAyOC40N2MuMjUyLTIuODUzLjgwNy00LjA4NSAyLjgzNC02LjIzMkMuOTggMjQuMDMuMzQ2IDI0Ljg0NS43IDI4LjQ3Ii8+PHBhdGggZD0iTTQyLjQgMjQuNDUyYS44My44MyAwIDAgMSAuMzktMS4xLjgzLjgzIDAgMCAxIDEuMTAzLjM5LjgyLjgyIDAgMCAxIC4wNDYuMTE5Yy0uMzkzLjMtLjc1My42MzUtMS4wNTUgMS4wMzNhLjkuOSAwIDAgMS0uNDg0LS40NDFtOS4xOTYtMy41NTdhLjYxLjYxIDAgMCAxIC42NjMtLjU1OC42Mi42MiAwIDAgMSAuNTU4LjY3Ny42My42MyAwIDAgMS0uMDU2LjIwMyA1LjM2IDUuMzYgMCAwIDAtLjk0My4yNjIuODMuODMgMCAwIDEtLjIyMi0uNTg0IiBmaWxsPSIjZWRkNzQ5Ii8+PC9nPjwvc3ZnPg==" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换深色 / 浅色主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none"><span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span></button>
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
<script>window.__MAINS__={mains};</script>
<script>{js}</script>
</body>
</html>""".format(
        sub=esc(BRAND_SUB), n=total_svg,
        css=CSS, archnav=archnav, mains=json.dumps([{"mid":n,"t":ct,"s":sub} for n,_c,_ic,ct,sub in MAINLINES],ensure_ascii=False), panes=build_panes(), js=APP_JS)


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
