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
  <a href="https://github.com/apache/hadoop" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://hadoop.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjNjZDQ0ZGIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+QXBhY2hlIEhhZG9vcDwvdGl0bGU+PHBhdGggZD0iTTEyLjA5OCAzLjAxYy0xLjEzMy4yNzctMS40NjYuNDc0LTEuODQyIDEuNzg3LjQ3OC0uOTYyLjg0LTEuMzE1IDEuODQyLTEuNzg3em0zLjIyOC4wNzZjLS44MzQtLjA1My0xLjcxNS4xNzctMi43NTYuNjE1YTMuOTcgMy45NyAwIDAwLTEuMTk5Ljc2Yy0uMzEuMjg3LS41NzYuNjItLjg2NiAxLjAwNmExLjMxMiAxLjMxMiAwIDAwLS40NjguMDk1IDEuODY4IDEuODY4IDAgMDAtLjUzOS4zNTZjLS4xNDEuMTI0LS4yOC4yNTItLjQxNi4zODN2LjAwMmMtLjEyMy4xMi0uMjQ0LjI0MS0uMzYzLjM2NS0uOTQ1LjE1Mi0xLjcyLjMyLTIuNDEuNTg4YTYuMzE0IDYuMzE0IDAgMDAtMS45NyAxLjIxN2MtLjI1Mi4yMjItLjQ4Mi40NjktLjY4Ny43MzZhNS40MzUgNS40MzUgMCAwMC0uNTAzLjgwM2MtLjEzLjE0Mi0uMjYuMjg4LS4zOTkuNDE0YTEuNDUgMS40NSAwIDAxLS40NDEuMjg1Yy0uMDkzLjAzNS0uMTMzLjA1OC0uMTM3LjA1Ni0uMDA0LS4wMDEtLjAwOC0uMDMzLS4wMTItLjA0Ny4yMzUtLjIxLjI2Ny0uNTUuMjg5LS44Ni4wMy4wMzQuMDUzLjA2OC4wODIuMTEzLjAzMS4wNDcuMDYyLjA5NS4xLjE0MmwuMTU4LjIuMDU1LS4yNDljLjA0Ni0uMjA4LjA4MS0uNDg0LjAyNy0uNzI0LS4wMzQtLjE1My0uMTE3LS4zMTUtLjIzNS0uMzkzbC4wMzYtLjA5Yy4wNC0uMS4wOC0uMjA0LjExNS0uMzAzbC4wNjktLjE5My0uMjA0LjAzNWMtLjI3LjA0Ny0uODUyLjM2Ni0xLjI2MS43OTEtLjE1Mi4xNTgtLjI4NC4zMy0uMzcuNTE0YS45ODQuOTg0IDAgMDAtLjA5My41OS45MS45MSAwIDAwLjI3Mi40OThjLjAzLjEyLjA1OC4yMjMuMDg3LjMxNi4wMzMuMTA0LjA2OC4xOTguMTEyLjI5LjExOS4yNDcuMzEuMzk4LjUyOS40NjguMTgyLjA1OS4zNjkuMDY2LjU2Ni4wMmEzLjgzIDMuODMgMCAwMC0uMDcyLjY5IDguOTExIDguOTExIDAgMDAuMDcgMS4zOTRjLjAxMy4wOTMuMDI4LjE4NC4wNDUuMjc1bC0uMTA3LjI5MS0uMTY2LjQ1NS0uMzcuMzY1LS4zNDMuMzRhOS4yMiA5LjIyIDAgMDEtLjA4Mi4wOGMtLjIzMi4yMjQtLjI3OS4yNy0uMjEzLjY2Mi4wNC4yNDEuMTE5LjQ4NC4yNDIuNzIuMTE0LjIxNi4yNjcuNDI3LjQ2My42MjQuMjQ1LjI0NS42NDcuNTUgMS4wNjYuNzEuMjQ1LjA5Mi40ODguMTM4LjcyMy4wOTdsLS4wMzkuMTFhNC4wNDYgNC4wNDYgMCAwMS0uMTIzLjNjLS4yODUuNjI0LjAwOC45NS40NjMgMS4xNTguMjI3LjEwNC40OTcuMTczLjc0OC4yMzhsLjE2OC4wNDVjLjI5OC4wOC44MTIuMjI4IDEuMjgxLjI1OC41MTMuMDMzLjk3NC0uMDczIDEuMDk4LS41MzMuMDQ5LS4xODIuMDc4LS4zMjIuMDktLjQ1OWEyLjMzIDIuMzMgMCAwMC0uMDEtLjQwNmMuMTQ0LS4zMi4yMS0uNDIzLjMxNi0uNTc4bC4wNTMtLjA4Yy4xMTUtLjE3LjE2OC0uMjkuMTg4LS40MjYuMDE4LS4xMzEuMDA0LS4yNjItLjAyLS40NjFsLS4wMTEtLjA4NGE2LjgyMiA2LjgyMiAwIDAwMS4zMzguMDVsLS4xMTguMDYxLS4wNTUuMDNjLS4zOTUuMjAzLS40MTMuNTg3LS4yODkuOTg0LjExMi4zNTcuMzQzLjcyMy40ODcuOTQ1LjMwMy40NjcuNTkyLjg2MS45NDMgMS4wNzYuMzY4LjIyNi43ODYuMjUzIDEuMzI4LS4wNC4yNzYtLjE1LjM2My0uMzAyLjQ4LS41MDcuMDM4LS4wNjYuMDgtLjEzMy4xMjYtLjIwNC4xMDEtLjA1LjM4Mi0uMjk2LjY3LS41MzRsLjI5Ni0uMjQyYy4wNzMuMDUzLjE2NC4wOS4yNy4xMTUuMTQuMDM0LjMwNS4wNS41MDQuMDY1LjE0OS4wMS42MzUuMDEuOTQ5LjAxaC4yMjdjLjMyNC4wMDEuNTg1LS4wMTYuNzgzLS4xMjguMjEtLjExOS4zMzQtLjMzMS4zNjEtLjcxYTEuMjggMS4yOCAwIDAwLS4wMDgtLjM3OC45NDYuOTQ2IDAgMDAtLjEzNi0uMzEybC0uMDE0LS41MDItLjAxNi0uNTIxYTIuMzcyIDIuMzcyIDAgMDAtLjA2OC0uNTM2IDMuNTU4IDMuNTU4IDAgMDAtLjE4LS41MDVjLS4wNTMtLjEyNy0uMDk2LS4yNDUtLjEzOC0uMzZhNS43NTYgNS43NTYgMCAwMC0uMjI5LS41NDdsLjAxOC0uMTIzLjE4MS4xNzQuMjY2LjI1OGMuMjAzLjE5Ni4zOS4zNzMuNjA3LjUwMi4yMjYuMTMzLjQ3OS4yMS44MDcuMTk1YTEuOTI1IDEuOTI1IDAgMDAxLjAxNi0uMzg1Yy4yOTMtLjIxNi41MjgtLjUwOS42MjctLjgzMmwuMDg0LS4yNzkuMDctLjIyNWMuNDgyLjA4Mi45OTguMTEgMS40OTguMDU3YTMuNyAzLjcgMCAwMDEuMzUxLS4zODkgMy40MDYgMy40MDYgMCAwMDEuMzUtMS4zM2guMDAydi0uMDAyYy4zNTUtLjYxNi41NTUtMS4zNC42My0yLjA4OC4wNjItLjU5OS4wMjgtMS40MTUtLjA5Ny0yLjItLjExLS43MDEtLjI5NS0xLjM4LS41NS0xLjg3YS43MzYuNzM2IDAgMDAtLjEzNy0uMTc4IDEuNDEzIDEuNDEzIDAgMDAtLjUxLS4zMWMtLjIwNi0uMDctLjQyMi0uMDg0LS41OTQuMDA2YS40ODUuNDg1IDAgMDAtLjEyMy4wOSAyLjc5MyAyLjc5MyAwIDAwLS4zLjM4OGMtLjEwNi4xNTMtLjIxLjMwNy0uMzM3LjQxNC0uMTQ5LjEyOC0uMzI3LjIwMi0uNTAyLjI3MmEzLjQ1NCAzLjQ1NCAwIDAwLS4yNjEtLjUwOCA0LjgxIDQuODEgMCAwMC0uMzk5LS41NCAyLjIxIDIuMjEgMCAwMC0uMzY1LS4zNDkgNS4zNTcgNS4zNTcgMCAwMC0uNDEtLjI3NWMtLjQwNy0uMjU1LS43NTQtLjU1OS0xLjEwOC0uODctLjE2LS4xNC0uMzIzLS4yODItLjQ4Mi0uNDEzLS44NDItLjY5NS0xLjYyOC0xLjAzMS0yLjQ2OS0xLjA4NHptLTQuMTI5LjAwNGMtLjU3LjEzNy0uNjguMjQ1LS44NTEuODA0LjI3My0uNDEuNDMtLjU0NS44NTEtLjgwNHptMy45NTIuNDY1Yy44MjktLjAwMSAxLjU4Ny4zMDMgMi40MzEgMS4wMTMuNDEyLjM0Ny43NzQuNjg0IDEuMTkyLjk4My0uMTUyLjAxMy0uMjgzLjA0LS40NTUuMTA3LjIxLS4wNC40NTEgMCAuNjcuMDQuMDYuMDM5LjEyNC4wNzguMTg5LjExNi4yOTUuMTc0LjQ2My4yNy42NjIuNTQ3LjIxLjI5NC4zODYuNTg5LjU0MS45MTItLjEwMS0uMDM2LS4xODYtLjA2Ny0uMjYyLS4wOWEuNTY2LjU2NiAwIDAwLS41MzMuMDM0bC0uMDEyLjAwNmMtLjE2My4wNzktLjQxNi4xNy0uNTg2LjE5N2EuNy43IDAgMDAuNDA1LS4wMDYuNTY1LjU2NSAwIDAwLS4wMTguNTM5LjI2OS4yNjkgMCAwMS0uMDItLjEyLjIyOC4yMjggMCAwMS4yNDktLjIwOC4yMzMuMjMzIDAgMDEuMTg3LjMzYy0uMTE3LjAyLS4yMzMuMDU1LS4zNTMuMWE0LjQxIDQuNDEgMCAwMC0uMjM3LjA5NSAzLjcyMiAzLjcyMiAwIDAxMS4wODQtLjAyYy4wMjUuMTE3LjA1LjI0LjA3My4zNjZsLS4xMzcuMDEtLjAxMi4wMDJjLS4xNzQtLjE0LS4zNjctLjExNy0uNjMzLS4wNTctLjgwNi4xODQtLjYxNy42MzctLjk4OCAxLjMxOC4zODUtLjQ3LjM1Ny0uOTYyLjk4NC0xLjExLjE0Ny0uMDM2LjI0Ny0uMDc4LjM0Ni0uMDYzLS4xNzguMDktLjMzMy4yMzctLjM5NC40MS0uMTczLjQ4Ni0uMDY1Ljg5NS0uMjU0IDEuMzUuMjM0LS40MDcuMjQ5LS44MDIuNDU5LTEuMjMuMDc1LS4xNTMuMzU0LS40LjUyNS0uNDAzbC4xNC0uMDAyYy4wNDIuMjcuMDY4LjUzOS4wNTIuNzYxYTguNTM1IDguNTM1IDAgMDEtLjE5OCAxLjI0Yy4yMTMtLjI3Mi4zMS0uODUuNDAzLTEuMjU3LjA5Ny0uNDI0LjA3LS45MzQtLjAxNC0xLjM4OS0uMTE3LS42MjUuNTI3LS41MjIuOS0uODE2LjI3NS0uMjE3LjQ2My0uNTY0LjcxNS0uODA5LjI1LS4yNDMuNjQ0LjExNC43NDIuMzUyLjQyNiAxLjAzLjYyIDIuNjUuNTA4IDMuNjktLjEyNiAxLjE2NC0uNjkgMi40MzctMS43MTkgMy4wMS0xLjMxLjczMi0yLjg1NC4yODUtNC4xNTYtLjE1NC0uMjc4LS4wOTMtLjQ3LS4yMjktLjcxNS0uMzgyLjA2Ny4zLjA5Ny42MTUuMDA4LjkxNC0uMTQuNDc0LS4zNjcgMS4yNTEuMjc3IDEuMzk0LjI0Ni4wNTUuMzU3LjA0OC43MDQtLjEzYTEuMyAxLjMgMCAwMS0uNjE2LjAxMS4zOTcuMzk3IDAgMDEtLjMxNC0uMjczYy4wNi4wNDQuMTYuMDY2LjMzLjEwNy40NzguMTE1LjkzMi0uMTE0IDEuMDIxLS40NDUuMDUyLS4xOTQuMDQzLS4yOTUuMTUzLS41NTkuMDk5LjAzLjIwMi4wNTkuMzA2LjA4NGwtLjE3Ny41NzhjLS4xNTQuNTAxLS43NTIuOTA0LTEuMjguODk1LS40ODgtLjAwOS0uNzk3LS4zMTQtMS4xMzQtLjYxM2wtLjY3OC0uNmE1LjIyOCA1LjIyOCAwIDAxLTEuNjU4LS44MzRjLjQuNDcyLjY3My43MzIgMS4yMzIuOTY3LS4wODEuODMtLjM3IDEuNDM2LS42MTUgMi4yMy0uMTExLjM2LS45OTEgMS44LTEuMjM0IDEuOTQtLjE3NC4xLTEuMjYgMS4wMTYtMS40NjUgMS4xMzYtLjE1My4yMDMtLjI4Ny40ODMtLjUxNi42MDQtLjY5OC4zNy0xLjE0OC0uMzM5LTEuNTIzLS45MzYtLjE3MS0uMjcyLS42NDUtMS4wNTQtLjIzLTEuMjczLjM5LS4yMDguNjEtLjM1NyAxLjAwOS0uNjIuMDU5LjEwOC4xNTkuMjEyLjIyNS4zMmwtLjA0My0uMzUyYTIuNzUyIDIuNzUyIDAgMDEtLjAwOC0uNTk2Yy4wMTYtLjIwNi4wMy0uNDEzLjA0Ny0uNjItLjA2LjIxLS4xNzkuNDItLjIzOS42My0uMDI0LjA4NC0uMDQ1LjE1Mi0uMDU2LjIxNGE3LjA1IDcuMDUgMCAwMS0yLjY4Mi4wMzQgMTYuNzYgMTYuNzYgMCAwMC0uMTg1LS45MjZjLS4wMTguMjc4LS4wMDcgMS4wNDctLjAwOCAxLjQ3Ni0uMDAxLjMzMy0uMDE2LjQ0OC0uMTg4LjczMS0uMTYuMjY1LS4yMjguMzI1LS40NTMuNzczLjAxOS4yODMuMDE5LjQ3LS4wNTcuNzM5LS4xMjUuNDQ2LTEuMzg2LjA5OC0xLjcxOC4wMDctLjQxLS4xMTItMS4yNTYtLjI3OC0xLjA0My0uODI0LjE4Ny0uNDguMzA3LS45ODYuMzk4LTEuNjU4LS43NS0xLjA4LTEuNDQ4LTIuNTYtMS41ODItMy44NzMtLjEwNC0xLjAxOS0uMDQtMS42NDYuMTgtMi4yNy4zNS0uOTg3LjgzNy0xLjg0MyAxLjYyLTIuNTNDNS43NzggNy44OSA2Ljc2NyA3LjUxNiA4LjMxNiA3LjI4Yy0uMzczLjQxNy0uNzQxLjg1OC0xLjE0MyAxLjMzLS40MDYuNDc5LS42NDguOTYzLS45MDYgMS40ODctLjM1Ny43MjItLjM0OC45OTYuMTI1IDEuNjMuNDA3LjU0Ny42MjcuNzk0LjgwNCAxLjMyOC0uMTQ2LjMwMy0uMi41Ni0uMjUuOTczLjUuNTQ1Ljg3LjkxOCAxLjM1NCAxLjAzMy40NzUuMTEzLjg3Mi4wOTMgMS4yOTctLjEyNS45NDQtLjQ4MiAxLjgxNi0xLjEwNyAyLjg4LTEuMTMyLjQ5My0xLjIxMS40NDQtMi4yMjIuMjA4LTMuMzkzLS4xNjItLjgtLjIyNy0xLjU1Ny0uMjc4LTIuMzczLS4yLjg0LS4yMzYgMS41NzctLjA4OCAyLjQxNC4xOCAxLjAwOC4zMTggMi4xMjQtLjE4IDMuMDEtLjk2Mi4wNzMtMS43ODguNjU4LTIuNjU1IDEuMTA3LS4zNS4xOC0uNzEyLjE5OC0xLjA5OC4wOTItLjM1OC0uMDk4LS42LS4zMzQtLjk4Ni0uNzgtLjAwNi0uNDQ2LjA5NS0uNjUzLjMtMS4wNTguMzMtLjY1LjY5NS0xLjI1NSAxLjA5NC0xLjg5NC0uNDkuNTktLjk1MyAxLjA4NC0xLjMzOCAxLjY3Ny0uMTQ3LS40MTktLjM1OC0uNjMzLS43MDctMS4xMDUtLjM0LS40NjEtLjM3NS0uNjYyLS4xMi0xLjE5Ni4yNTUtLjUzNi40NzItMS4wMDguOTA3LTEuNDc4Ljc1My0uODEzIDEuNDQzLTEuNzE3IDIuMjY2LTIuNTE4LjQ0Ny0uNDM0LjYyOC0uNDIgMS4yMi0uNTFhMjAuNzY4IDIwLjc2OCAwIDAwMS42MDYtLjMxIDIyLjUgMjIuNSAwIDAxLTEuNTUzLjA4aC0uMDE1Yy41MDYtLjY0Ni43OTktMS4wMDYgMS42Mi0xLjM2My45NS0uNDEyIDEuNzM4LS42NTIgMi40Ny0uNjUyem0uNTU2IDIuNzljLTEuMTAxLjI3Ni0xLjMwNy43MzktMS4xNjYgMS40NS4xMjEtLjUzNS4zMzUtMS4wNSAxLjE2Ni0xLjQ1em0tMy4yNjMuMDYxYy0uNDQ2LjA1LS44OS4wOTYtMS4zMzYuMTM5LS4zNzUuMDM1LS40MzYuMDMtLjcwMi4yOTMtLjQwMy4zOTktLjc5NCAxLjc2OC0uOTIgMi4zMTYuMTk4LS40NTUuNjktMS43MjkgMS4wNjktMi4wNTMuMTA1LS4wOS4xOC0uMTQzLjI1OC0uMTgzLS4yNzEuNDU1LS4yNTIuNTY2LS4xNTcgMS4xNzYuMDgxLS42Mi4yOTUtLjg1OS42NDctMS4zMmE5LjI4NyA5LjI4NyAwIDAwMS4xNC0uMzY4em0xMC4yMjYuMDUzYy0uMjU1LjUxNy0uNjUuOTUtMS4xODUgMS4yMTUtLjI4OC4xNDItLjQ3LjA5My0uNzkxLjA2Mi4zMjYuMDk0LjUzMy4yMS44NTMuMDk2LjY1Mi0uMjMzLjk2Ny0uNzU2IDEuMTIzLTEuMzczem0tMi4yOC44MzRjLjAyMy4wNDcuMDQ2LjA5Ni4wNjcuMTQ0YS42MDIuNjAyIDAgMDAtLjA1LjA0MS41NzIuNTcyIDAgMDAtLjEyNi0uMTgxbC4xMS0uMDA0em0tMy4yNi40Yy0uMzYuMTY2LS43NzkuMTI2LTEuMDg3LjMzNC0uMjcxLjE4NC0uNjQ2Ljc2NC0uOTIyIDEuMDEuMi0uMDc4LjM5NC0uMjEyLjU3LS4zNTQuMDAyLjIyLjEwMS40MjYuMjcuNTY1YS4zMS4zMSAwIDAxLjA5Mi0uNDkyLjMxMi4zMTIgMCAwMS40MzIuMTkxYy0uMTQ4LjExLS4yODQuMjM4LS4zOTcuMzg3YTEuNjY2IDEuNjY2IDAgMDAtLjI0LjQ0IDQuMjIyIDQuMjIyIDAgMDEyLjAwMi0xLjI5NGMtLjItLjAwMy0uNDM3LjAzNC0uNjc4LjExNGEuNzMyLjczMiAwIDAwLS40ODItLjYxNGMuMTYtLjA4NS4zMTYtLjE3NS40NC0uMjg3em0tMS4wNDIgMS42NGEuNzM1LjczNSAwIDAxLS4xMjUtLjA4My4zNS4zNSAwIDAwLjEyNS4wODR6TTEuMzIgOC4zNGMtLjk1My42NzItMS4xOS45NzgtMS4wNjIgMi4zMzhDLjM1MiA5LjYwOC41NiA5LjE0NSAxLjMyIDguMzR6bS0uODA4LjQwNGMtLjQ4Mi4zMzYtLjU0NS40NzUtLjUgMS4wNTkuMTA1LS40ODIuMjAzLS42NjQuNS0xLjA1OXptMS43NzkuMTk1Yy0uMDcuMTUtLjExOC4yNjQtLjE1Mi4zODEtLjE0Ny41MDguMDY2Ljk2Mi0uMzk1IDEuMzMuMjE3LjQzOC4yMDcuNjEyLjcxMS40MS4xOTUtLjA3OC4zNTUtLjE4Ny40OTgtLjMxNi0uMDcuMTgtLjEzMy4zNjEtLjE5MS41NDVsLS4wMy4wOTRjLS4zNi4xNTMtLjgzNC4yNS0xLjAxNS0uMTNhMy40NTggMy40NTggMCAwMS0uMjAzLS41OTVjLS41OTQtLjYxNS4yOTQtMS40MjcuNzc3LTEuNzE5em0uMTIzLjI3NmMuMTIzLjA3MS4xNTYuMi4xNy4zNzUtLjA3My0uMDc0LS4xMzItLjEyMi0uMjI3LS4xMTIuMDA4LS4wNi4wMTktLjExOS4wMzQtLjE3Ny4wMDctLjAzLjAxNC0uMDU4LjAyMy0uMDg2em0xNC44NyAzLjI2N2MtLjEzMS4wMjItLjM2NS4wNy0uNDk1LjA5Mi0uMzQ4LjA1OS0uMzg3LjE0Mi0uNDQxLjQ4NGwtLjA4Ni41MjRhOS4xNiA5LjE2IDAgMDEuMjI4LS41NjhjLjA4NC0uMTg0LjEzMi0uMjAyLjMxLS4zLjEyNy0uMDY4LjM1Ny0uMTYzLjQ4My0uMjMyem0tMTQuNDcgMi40Yy4yNzQuOTQ2LjczOCAxLjg3NiAxLjI1NSAyLjY1N3YuMDE0YS45OTMuOTkzIDAgMDEtLjE0OS4zNjljLS4zNjkuNDkzLTEuMzA2LS4yMy0xLjU3OC0uNTA4LS4yOTctLjMwMy0uNDk2LS42NjItLjU0My0uOTk4LS4wMzQtLjI0Ni0uMDAxLS4yNTIuMTctLjQyNmwuNjkzLS43MDEuMTUzLS40MDZ6bTEyLjQwNS42MmMuMDU2LjE4My4xMDEuMzY0LjE4My41NTguMTM4LjMyNi4yMDUuNTI2LjIxNS44NzVsLjAzMiAxLjEwNmMuMTE3LjIwNi4xMzYuMjQ5LjExNS40ODQtLjA0My40ODEtLjIwMy41MTMtLjYyNS41MDYtLjE5Mi0uMDAzLS45NTctLjAwNy0xLjE1LS4wMjMtLjI3NC0uMDI0LS40MjktLjA1LS41MTItLjExMi40My0uMzE2IDEuMTYyLTEuNjE5IDEuMzA0LTIuMDY4LjE1MS0uNDc0LjMxNS0uODg4LjQzOC0xLjMyNnoiLz48L3N2Zz4=" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换深色 / 浅色主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none"><span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span></button>
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
