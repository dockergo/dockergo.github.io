#!/usr/bin/env python3
"""zookeeper-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd zookeeper-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import json
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 ZooKeeper 交互式核心原理图谱（离线自包含 HTML）")
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
    os.environ.get("ZOOKEEPER_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("ZOOKEEPER_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     家族 6 分布式协调/共识 KV 存储（模板 etcd；ZK 用 ZAB + znode 树）。
#     元模式 = 接触面 × 能力域 × 时机。全景 + 1 接触面 + 8 支撑能力域。
# ===================================================================== #
MAINLINES = [
    ("ZooKeeper原理_全景主线框架", "pano", "◇", "全景主线框架",
     "家族6分布式协调：双维模型 · 总架构 · 依赖矩阵 · 运行形态 · 三条贯穿声明"),

    ("ZooKeeper原理_接口_客户端API与znode", "iface", "⚙", "客户端 API 与 znode",
     "create/getData/setData/getChildren/exists/delete/multi + watch + session · 层级 znode 树"),

    ("ZooKeeper原理_支撑_ZAB原子广播", "support", "★", "ZAB 原子广播",
     "灵魂：Proposal→Ack→Commit 广播 + FastLeaderElection 选举/恢复 · zxid 全序"),
    ("ZooKeeper原理_支撑_数据树DataTree", "support", "▤", "数据树 DataTree",
     "全量内存 znode 树 · nodes 映射 + DataNode + ephemerals 索引 · 读直查"),
    ("ZooKeeper原理_支撑_会话与临时节点", "support", "⏱", "会话与临时节点",
     "session 心跳 + 分桶过期（ExpiryQueue）· ephemeralOwner 绑节点生命周期"),
    ("ZooKeeper原理_支撑_Watch机制", "support", "◉", "Watch 机制",
     "WatchManager path↔watchers · 一次性触发即移除 · 3.6+ 持久/递归 watch"),
    ("ZooKeeper原理_支撑_事务日志与快照", "support", "▦", "事务日志与快照",
     "WAL（FileTxnLog fsync）+ 模糊快照（FileSnap）· 恢复=快照+回放日志"),
    ("ZooKeeper原理_支撑_请求处理链", "support", "⇄", "请求处理链",
     "RequestProcessor 责任链 · 单机/Leader/Follower/Observer 四种拼法"),
    ("ZooKeeper原理_支撑_集群与Quorum", "support", "◫", "集群与 Quorum",
     "QuorumPeer 状态机 + QuorumCnxManager 选举连接 + 过半判定 + reconfig"),
    ("ZooKeeper原理_支撑_ACL权限", "support", "⛨", "ACL 权限",
     "每 znode 独立 scheme:id:perm（不继承）· world/auth/digest/ip/x509/sasl"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接触面主线 · 客户端如何用（API + znode + session + watch）"),
    ("support", "支撑主线 · 协调服务内部（8 条能力域）"),
]

# ===================================================================== #
# 一·b、项目总架构图 = 唯一导航底图 —— 热区注册表（决定"点击下钻"）
#   坐标系 = 该总架构 SVG 的 viewBox（ARCH_W×ARCH_H），生成期换算成百分比定位。
#   两条覆盖铁律：① 图上每个模块都有热区 ② 每条主线都被某热区覆盖（未覆盖者兜底成 chip）。
# ===================================================================== #
PANO_NAME = "ZooKeeper原理_全景主线框架"
# (x, y, w, h, 主线name) —— 一个模块可拆多行热区，一条主线可被多个区域指向
# 没有独立架构区域、需底部 chip 兜底的主线（本项目 10 主线全部落在图上 → 空）
ARCH_ALWAYS_CHIP = []

BRAND_TITLE = "一切知识皆索引"
BRAND_SUB = "Apache ZooKeeper"
HOME_DESC = ("Apache ZooKeeper 核心原理设计文档库的离线交互图谱——家族 6 分布式协调 / 共识 KV 存储（模板 etcd，"
             "但 ZK 用 ZAB 协议、层级 znode 树、一次性 watch、临时节点绑 session、Java 实现）。"
             "10 条主线、17 张手绘原理图，全部回本地源码核实。点击项目总架构图任意模块即可下钻到对应主线。")
ARCH_SVG_NAME = "ZooKeeper原理_全景_02总架构.svg"
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
_on_disk = {f for f in os.listdir(_DESIGN_DIR) if f.endswith(".svg")}
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
        '<img alt="Apache ZooKeeper 项目总架构图" src="data:image/svg+xml;base64,%s"/>'
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
  <a class="logo" id="logo" href="../../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a><div class="brand-intro" style="display:flex;flex-direction:column;align-items:flex-start;margin-left:12px;min-width:0;max-width:min(60vw,760px)"><div style="font-size:15px;font-weight:600;color:var(--c-ink);line-height:1.3">ZooKeeper · 核心原理图谱</div><span style="margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5;text-align:left">分布式协调服务:ZAB 原子广播保证顺序一致,znode 树形命名空间 + watch 通知,选主/配置/锁的协调原语。</span></div>
  <div class="spacer"></div>
  <label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label>
  <a href="https://github.com/apache/zookeeper" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://zookeeper.apache.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iNDUuMDIgMjIuMzIgNTMuMTE1IDU3Ljc3NCI+PHN0eWxlPjwhW0NEQVRBWy5Je3N0cm9rZS13aWR0aDouNX0uSntzdHJva2UtbWl0ZXJsaW1pdDoxMH0uS3tzdHJva2U6IzAwMH0uTHtmaWxsOm5vbmV9Lk17ZmlsbDojZjljODlhfS5Oe2ZpbGw6IzRmMmUwZX0uT3tmaWxsOiM2ZDk3NTh9LlB7c3Ryb2tlLXdpZHRoOi4xfV1dPjwvc3R5bGU+PGcgdHJhbnNmb3JtPSJtYXRyaXgoLjE1OTg4NCAwIDAgLjE1OTg4NCAzNC4yMDYzMSAxNy4yODM5MikiPjxnIGNsYXNzPSJLIEkiPjxlbGxpcHNlIGN4PSIyOTkuNzMiIGN5PSIzMzkuODEzIiByeD0iMTAuOTU3IiByeT0iNS4xNCIgZmlsbD0iIzMzMWUwOSIvPjxnIHN0cm9rZS1taXRlcmxpbWl0PSIxMCI+PHBhdGggZD0iTTIxNy43MDYgMzE5LjQ1M3M0LjM2MyAxOC42MTQgNC45NDQgMjQuMTQyIDExLjYzNSA4LjE0NSAxMi43OTggMS43NDUgNS4yMzYtMjIuMTA1IDUuMjM2LTIyLjEwNXptNjkuNTE4IDQuMDcyczUuODE2IDEzLjk2MiA1LjgxNiAyMS44MTQgMTMuOTYgOS4wMTcgMTUuMTI1IDMuNzggMi45MDgtMjUuODg3IDIuOTA4LTI1Ljg4N3oiIGNsYXNzPSJNIi8+PHBhdGggZD0iTTIzNC43NyAzMzYuMDNjLTIuMzI3Ljk3LTguOTIgMS43NDYtMTEuNDQuNzc3cy4xOTUgOS4xMTMuOTcgMTIuMjE3IDguOTIgMi41MiA4LjkyIDIuNTJ6IiBmaWxsPSIjYTE1ODEzIi8+PC9nPjxnIGNsYXNzPSJOIj48ZWxsaXBzZSBjeD0iMjIwLjk3OSIgY3k9IjM0NC4wMyIgcng9IjQuODcyIiByeT0iMTEuNjM2Ii8+PGVsbGlwc2UgY3g9IjIzNi4yNDkiIGN5PSIzNDUuMjY4IiByeD0iNS4wMTgiIHJ5PSIxMS40MTYiLz48L2c+PGcgc3Ryb2tlLW1pdGVybGltaXQ9IjEwIj48cGF0aCBkPSJNMjAyLjE0NSAzNzcuNzdMMjAyIDM2NC4xYy0uMTQ1LTcuNTYyIDcuODU0LTE3LjE2IDI0LjE0Mi0xNi43MjVzMjMuODUgOS40NTMgMjMuODUgMTguMTgtLjcyOCAxNS43MDctMS42IDE3LjQ1Mi00Mi42IDIuMzI3LTQ0LjIuNzI4LTIuMDM2LTUuOTY0LTIuMDM2LTUuOTY0eiIgZmlsbD0iIzllNTYxMyIvPjxwYXRoIGQ9Ik0yMDIuMTQ1IDM4OS41NWMtMi43NjMtLjcyNy0zLjc4LTMuNjM2LTMuOTI3LTYuMzk4czIuMTgyLTUuMSAzLjkyNy01LjM4MmMxLjMwOCAxLjc0NiAzLjkyNiAyLjQ3NCA2LjI1MyAyLjlzMzIuMTQuNzI3IDM1LjYzLjQzNiA0LjM2My0yLjMyNiA0Ljk0Ni0zLjE5N2MyLjQ3My44NyAzLjUgMy40ODggMy42MzUgNS45NnMtMS4wMTggNC44LTMuNSA1LjY3My0xNS41NjIgMi45LTI0LjU3OCAyLjc2My0yMi4zOTYtMi43NjQtMjIuMzk2LTIuNzY0eiIgY2xhc3M9Ik4iLz48cGF0aCBkPSJNMzEwLjYzOCAzNDIuNDNzLTcuODU0IDQuNjUzLTE3LjkgMS4xNjRjLTYuNTQ0LS44NzMtOC4zLS44NzMtOC4xNDUgMi4zMjdzMS4wMiAxMS45MjYtMi4wMzUgMTUuNTYtNi4yNTUgMTMuMS0xLjYgMTcuNDUyIDcxLjk4OCAzLjkyNyA3NC42MDcgMy4yIDQuMjE4LTUuMzgyIDQuMjE4LTUuMzgyLjg3LTkuOS41OC0xNS4xMjQtNy41NjItMTQuODM0LTE5LjkyNS0xNC4zOTctMTcuNDUgOS4xNjItMjIuOTc4IDEwLjMyNWMtNC42NTQtNC4zNjItNi40LTkuNDUyLTYuNC0xMC40NzJzLS40MzQtNC42NTMtLjQzNC00LjY1M3oiIGZpbGw9IiM5ZTU2MTMiLz48cGF0aCBkPSJNMjk1LjU4NSAzNTguMzU1YzQuMzYzIDAgNy41LTEuOTYzIDcuODU0LTYuNDcycy0uNzI3LTYuOTgtMy45MjgtNy4xOTgtNy4xMjYtLjg3My05LjAxNi0yLjEwOC0yLjEtMy41LTEuMy00LjQzNyAyLjE4LTEuODE3IDIuMTgtMS44MTdsLS41LTEuMzhzLTcuMiAyLjc2My02LjU0NCAxMC40NyA0LjUwOCAxMi45NDMgMTEuMjcgMTIuOTQzem03LjkyNy0xMy42N2MyLjM5OC45NDUgMi45MDcgMi43NjQgMi41NDUgNC43MjdzLTEuMTY0IDcuNjM2IDIuOTggNy40MTcgNS4yMzYtOC4zIDQuODczLTExLjk5OC0yLjc2NC03LjI3Mi0zLjg1NC04LjE0NWwtLjIxOCAxLjFzLjgyNC41OC44NSAyLjAzNi0yLjQ1IDQuMjE2LTcuMTc1IDQuODcyeiIgY2xhc3M9Ik4iLz48cGF0aCBkPSJNMzE3LjQ3MyAzNTcuNTU2Yy0yLjIzIDQuODUtNC4zNjMgMjAuMzYzLTIuNDI0IDI0LjYyNiIgY2xhc3M9IkwiLz48cGF0aCBkPSJNMjgwLjk3IDM3OC45MzVzLTMuMzQ2IDIuMDM2LTMuMDU0IDUuMjM0IDIuNzYzIDMuOTI4IDYuNCA0LjggMzguMTAzIDEuOSA0NC4zNTYgMi4xOCAyNy42MzItMS4zIDMxLjI2OC0yLjc2MyA2LjgzNi03Ljg1NC0uMTQ1LTExLjYzNmMtMi43NjUgMy4wNTUtNC45NDUgMy42MzctOS40NTQgNC4yMnMtMjUuNTk3LjcyNy0zNC4zMjIuNDM2bC0zMS45OTUtLjcyN2MtMi4xOC0uMTQ2LTMuMDUzLTEuNzQ1LTMuMDUzLTEuNzQ1eiIgY2xhc3M9Ik4iLz48L2c+PGcgc3Ryb2tlLW1pdGVybGltaXQ9IjEwIiBjbGFzcz0iTSI+PHBhdGggZD0iTTI2NS41NTQgMTE1LjQxMmMtMS4wMiAxLjE2My01LjgxNyA2LjctMy41IDExLjM0M3MxNS41NiAyNS4wMTUgMTUuNTYgMjUuMDE1IDI5LjIzMi0xNC44MzQgMjguMzYtMjEuODE1LTYuODM2LTE1LjI3LTYuODM2LTE1LjI3em03MS45IDEwNS42M2MuOTctLjk3IDMuMS01LjcyLTIuNjE4LTcuNDY2LTQuNTU2LS41ODItNy44NTMgMS41NTItOC44MjIgMi42MnMyLjAzNSA2Ljc4NyAzLjg3NyA2Ljk4IDcuNTYzLTIuMTMzIDcuNTYzLTIuMTMzeiIvPjxwYXRoIGQ9Ik0zNDEuNDIgMjI2LjI4Yy44NzMtMS4yNiAyLjcxNS00LjQ2LTEuNTUtNi41OTNzLTkuOTg4LjA5OC0xMS40NDIgMi4zMjcgMi40MjQgNy4xNzUgMy4yIDcuMTc1IDkuNzkyLTIuOSA5Ljc5Mi0yLjl6Ii8+PHBhdGggZD0iTTMzMS44NyAyMDIuODE2bC01LjM4IDkuNDU0czMuMDA1IDMuOTI3IDQuMTY4IDguODctLjc3NiA2LjcuODcyIDYuNCAxMS4yNDgtMi45MDggMTMuMS0xLjc0NiA0LjM2MyA1LjkxNSAyLjYxOCA5LjExNC02Ljc4NyA5Ljc5Mi0xMy44NjUgMTEuNTM4LTE1LjYwOC0xLjQ1NS0xOC44LTUuOTE1LTguMjQtMTguOC04LjQzNi0yMS4zMyAzLjItMTAuMTggMy4yLTEwLjE4bDEzLjE4Ni01LjkxNHoiLz48cGF0aCBkPSJNMzI1LjAzNSAyMTEuNTQyYzIuNDIzIDEuMzU3IDYuMzAzIDQuMzYzIDcuMjcgOS41MDJzLTEuMDY2IDExLjYzNS00LjM2MiAxNC4zNSIvPjxwYXRoIGQ9Ik0zNDEuNyAyMzQuNDIzcy0yLjMyOCAzLjI5OC03Ljc1OCAyLjUyLTUuMDQtNy41NjItMi40MjQtOS40MDQgNi43ODYtMy4yOTYgOS42LTIuODEyIDQuMTY3IDEuNzQ1IDQuMTY3IDEuNzQ1Ii8+PHBhdGggZD0iTTMzNC4zNDMgMjI4Ljg5N2wyLjYxNyA0Ljg0OHMtMS42NSAxLjM1Ny0zLjU4OC40ODQtMS45NC0yLjMyNy0xLjQ1NS0zLjU4NyAyLjQyNi0xLjc0NSAyLjQyNi0xLjc0NXoiLz48L2c+PGcgc3Ryb2tlLW1pdGVybGltaXQ9IjEwIiBjbGFzcz0iTyI+PHBhdGggZD0iTTMxNC40NjYgMTIzLjk5MnMxMC43NjQgNS42NzIgMTIuNSAxMi42NTNjNS4yMzUgMS43NDUgMTEuMzkyIDkuNDI4IDEwLjggMTUuMDUyIDUuNjIzIDIuMzI3IDguMTIgNS41ODcgOC4xMiA5LjI3IDMuMTA0IDIuNzE1IDcuNzQ0IDkuNjc4IDIuMTIgMTkuNzZzLTguOTI3IDE3LjA1NS04LjkyNyAxNy4wNTVsLTIyLjQ5NS0xLjk0NC0xLjk0LTYuOCAxMC40Ny0xOS4zOTJzLTQuNjU0LTcuNTYyLTEwLjA4NS03Ljc1N2MtMS4zNTYgNS44MTctMi43MTQgMTQuMTU1LTIuNzE0IDE0LjE1NWwuNTggMzEuOTk1LTIuOTA4IDEuNzQ1LS41ODIgNy4xNzUgNy4xNzUgMTQuOTMgMi41MiAyLjMyNy02LjU5NCAxMC4yNzggMS41NTMgMi45IDguOTIgMjEuOTEyLS4xOTQgMi43MTUgNS4yMzcgNi43ODYtLjE5NSAyLjkwOCAyLjkgNy4xNzUtNS42MjQgMTIuNzk4LTMuNSA2Ljk4IDMuMjk3IDEwLjA4M3MtOS4xMTMgOC4zNC0yNC4yNCA4LjE0NS0yNS40LTcuOTUtMjUuNC03Ljk1bC0yLjkwOC0xLjc0NHMzLjI5Ny0xOS4wMDIgMi41Mi0yOS42NjgtMy4xMDQtMjYuNzYtMy4xMDQtMzAuNDQ0LS45Ny0xNC4xNTUtLjk3LTE0LjE1NWwtMS41NTMgMzMuNTQ2Yy0uMTkzIDExLjI0Ny0xLjc0NSAyNi41NjUtMy42ODMgMjkuNjY3cy00LjA3MiA0LjA3Mi00LjA3MiA0LjA3MmwyLjEzMiAzLjY4Ni41ODIgNC40NTgtMi4zMjcgMi45LTQuMjY3LTEuMTY1cy04LjMzNyA5LjY5Ny0yMy40NjIgNy45NTMtMjQuNDMyLTkuMzA4LTI1LjQwMi0xNS41MTRjLTMuNS0yLjUyLTMuODc4LTQuMjY2LTMuODc4LTQuMjY2bDkuOS0xMS40NC01LjYyNC0zLjI5NiA0LjY1NC04LjM0czMuMjk3LTguMTQ1IDMuODc4LTEwLjg2IDIuMzI3LTkuMzA3IDIuMzI3LTkuMzA3bC00Ljg0OC4xOTMgNy45NS0xMi40LS41OC04LjUzMyAxNC41NDItMzAuODMtLjU4Mi01LjA0Mi0xLjk1LTIuNzE1LTEuNTg3LTEwLjc2MiAxLjAyLTUuODE4czUuMDMtNi4xMDcgNS42LTExLjE1LTIuNDE3LTEwLjA4My0yLjQxNy0xMC4wODNsLTMzLjk4IDIyLjMtNC44Ny4zODgtMTMuOTczIDYuMjA1LTMuMzAzLTEuMzU4cy0xLjE2Ni0xLjkzOC0xLjU1NC01LjA0LS4wMDEtMTcuMDY0IDEuMTYyLTE5LjAwMyAzLjg3Ny0xLjk0IDMuODc3LTEuOTQgNC40Ni0uNzc1IDcuOTUtMy4xMDMgMjUuMDE0LTE4LjIyOCAzMC4yNS0yMi4zIDIzLjQ2My0xOS43NzggMjMuNDYzLTE5Ljc3OCA2LjIwNS00Ljg0OCA5LjY5NS02IDUuODE1LS45NyA1LjgxNS0uOTdsLjE5NSAxNi42NzcgMTUuNzA2IDE3LjggMTcuMDY1LTEwLjIzIDEzLjU3NC0xMi42MDR6Ii8+PHBhdGggZD0iTTI2Mi45MzYgMTE1Ljk5M2wtMi4zMjcgMS40NTUtMTAuMDM2IDE2LjcyNCAxMC45IDEuMDItMy45MjcgNy41NjIgMjAuNjUgMTAuOTA3IDEuNzQ0LTIuMDM2LTE0Ljk4LTE4LjQ3Yy0zLjUtNC4zNjMtNC41LTE0LjEwNy0uNTgyLTE2LjcyNXMtMS40NTMtLjQzNy0xLjQ1My0uNDM3Ii8+PHBhdGggZD0iTTI3Mi4yNDIgMTU1LjkxNWwzMS4xOTYtNS4yLTMuNjczLTEzLjMgMTMuMzQ0IDEuNyAxLjE2NC0xNS40MTctMTMuODE2LTguODctMS4zLS4xNDVzMy4zNDYgNC4zNjMgMy41IDkuNzQ0LTQuNzk4IDkuNDUzLTguODcgMTIuOTQzbC0yMS41MjUgMTguNTQzem0yMS42NjggMTAuNjg4bDIwLjY1Mi02LjgzNCAyLjE4MiAxMS4wNTItMTkuMzQzIDEyLjM2MnptLTIyLjI5Ny0xMC4zMjVsLjc3NiA0NS4xOC0zLjQ5MyAxMi43OTgtLjIgMTIuNC0uNTgyIDEyLjIxNiAyLjcxNSA0LjA3MiA3LjM2OC0xLjc0Nm0xMy41NzMtMjguNjk2bC0xMS40NC0uOTcuNzc0IDUuNDMgMTEuNDQzIDIuMTMyeiIvPjxwYXRoIGQ9Ik0zMTAuMDA4IDIwOS43OTdsLTEwLjA4NCAyLjUyIDEuMzU3IDYuNzg2IDguMTQ1LTIuMTMybS01MS4zODYtNi43ODZsOC43MjYuNzc1LjM4NiA2Ljk4LTEwLjI3Ni0uOTd6bS0yMS41MjUtMS43NDVsMTIuNjA0LjM4OC0uNTgyIDcuMTc0LTExLjQ0LTEuNzQ1bTQuODQ4LTU1LjA3bC00Ljg0OCA4LjcyNiAyMS4xMzUgMTYuNDgyIDYuNC0xNS43MDd6bTk3LjM0MiA0My40ODNzMC02LjI1NCAxLjktOC43MjZjLTQuNjU0LTIuMDM3LTE1Ljg1Mi02LjU0NC0yMS45Ni01LjgxNy0yLjkgMy41LTguMDk0IDEzLjY3LTYuMzAyIDE5LjkyNCA2LjczNy0yLjMyNyAyNi4zNy01LjM4IDI2LjM3LTUuMzh6bS0xNDcuMDMyLTM3LjA4NWw2LjcgOS43NDQgNC4yMTggMTAuOTA4cy0yLjYxOCAzLjYzNS01LjUyNiA0Ljk0NC0xMy4yODMgNS42MjQtMTMuMjgzIDUuNjI0bC0zLjI5Ni0xLjM1OHMzLjA1NC0xLjkzOCAzLjUtMTMtMi4zMjYtMTIuNTA3LTIuMzI2LTEyLjUwN2w2LjU0NC0yLjQ3M3ptOTguNzUgMTAyLjUzczQuMjE3IDE0LjY4OCAxMC4zMjYgMjQuMTQzYzMuMDUzLTIuMDM1IDI0LjI4Ny0zLjUgMjkuNDI2LTMuMzQ1Ii8+PC9nPjxnIHN0cm9rZS1taXRlcmxpbWl0PSIxMCI+PHBhdGggZD0iTTIwOS4xNzQgMjkzLjU2NmMzLjg3OCAxLjAxOCAyMC4zMTIgMy4zNDQgMjAuMzEyIDMuMzQ0czguODcyIDIuMTgyIDEzLjY3LjE0NmMyLjQ3Mi01LjUyNyA5LjktMzEuMTIzIDkuOS0zMS4xMjNzLTcuMTI2LTguMy0xMy41MjUtOS41OTgtMTYuNDMzLTQuOC0xNi40MzMtNC44IiBjbGFzcz0iTCIvPjxwYXRoIGQ9Ik0yMjAuMDMzIDI2NS4wNjJjMy41LS40MzcgMjAuNzk2IDAgMzAuNjg2IDcuMTI1IiBjbGFzcz0iTyIvPjxwYXRoIGQ9Ik0yMTQuNzk3IDI5Ni44NjJsMi43NjQgOS42NDciIGNsYXNzPSJMIi8+PHBhdGggZD0iTTIwOS40MTYgMzEyLjQ3MmM2LjU0NCA0LjY1MyAyMy43MDYgMTMuOTYzIDQ2LjgzIDMuNjM3IiBjbGFzcz0iTyIvPjxwYXRoIGQ9Ik0yNzYuMDI1IDMxOS4zMDhjNy45OTcgMy4xOTggMjcuNzc1IDQuMDcgMzguMTAzLTEuNzQ1IiBjbGFzcz0iTCIvPjwvZz48ZyBzdHJva2UtbWl0ZXJsaW1pdD0iMTAiIGNsYXNzPSJPIj48cGF0aCBkPSJNMzEwLjA1NiAzMTUuOTYzYzEwLjMyNCAzLjM0NSAyNS4zMDYgMy45MjcgMjcuMDUuM1MzMjEuNjQgMzA4LjcgMzIxLjY0IDMwOC43Ii8+PHBhdGggZD0iTTMwMi4yMDIgMzA5LjQxOGMxMi42NSAxLjkgMjYuOTA1LS41ODIgMjYuOTA1LTQuOTQ1cy0xOS40ODgtMy43OC0xOS40ODgtMy43OG0zLjkyNi01My42NjZjNC4yMiA1LjEgNy40MTggOS45IDExLjA1NCAxMS4wNTQtOC43MjYgMS40NTQtMjkuNjY4IDUuODE3LTMyLjg2OCA5LjQ1LTEuNDUzLTMuMzQ0LTIuNjE3LTUuMS00LjUwNy02LjM5OCAzLjc4LTUuMSAyNi4zMi0xNC4xMDcgMjYuMzItMTQuMTA3eiIvPjwvZz48cGF0aCBkPSJNMTgzLjA5MyAxNzIuN2MtNS4yMzYtLjU4Mi0xNS45OTgtMi43NjMtMTkuOTI0LTEyLjk0My0yLjQ3Mi01LjEtNi41NDQtNS45NjItOC40MzUtNy4yNzItMi40NzMtMi4xOC01Ljk2My0zLjc4LTEwLjkwOC0zLjA1NHMtMTIuNzk4LS40MzctMTcuNzQzLTMuMzQ1LTEwLjE4LTEuMDE4LTExLjkyNSAxLjQ1NS0xLjkgNS45NjItLjE0NiA3Ljg1M2wyLjkgMy4wNTVzLTYuODM1IDEuMDE4LTcuNDE3IDYuMTA4IDMuMDU0IDcuNTYyIDUuMzggOC41OCA0LjM2MyAxLjE2NCA0LjM2MyAxLjE2NC0yLjYxNyAzLjUtLjcyNyA2LjgzNCA2LjU0NSA0LjggNi41NDUgNC44IDIuMTggMy4wNTQgNC41MDggMy41IDE2LjQzNCAxLjE2NCAxNi40MzQgMS4xNjQgNS44MTYtMi4xOCA5LjE2Mi0yLjQ3MiAxMS4xOTgtLjQzNyAxMy44MTYuNzI3IDE0LjEwNyAxLjQ1NCAxNC4xMDcgMS40NTQgMS40NTQtNi4yNTQgMS4zLTkuNi0xLjMwOC04LTEuMzA4LTh6IiBjbGFzcz0iSiBNIi8+PC9nPjxsaW5lYXJHcmFkaWVudCBpZD0iQSIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIHgxPSIxMDMuMyIgeTE9IjM1Ny4zNiIgeDI9IjE3OS41MjQiIHkyPSIzNTcuMzYiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzQ0MmIxZiIvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzQ0MmIxZiIvPjwvbGluZWFyR3JhZGllbnQ+PHBhdGggZD0iTTE2Mi4wNTUgMzI3LjVjLTcuOTUuNzc1LTUwLjIyMi0uNTgyLTU4Ljc1NC01LjYyNC41ODIgMjkuMDg3IDguNzI2IDU0Ljg3NiAxMy45NiA2MC41czIxLjUyNCAxMC40NyAzOC4zOTUgMTAuNDcgMjcuMjEyLTUuMDY3IDIyLjg4LTExLjgyOGMtMTIuOC0xOS45NzMtMTYuNDgzLTUzLjUyLTE2LjQ4My01My41MnoiIGZpbGw9InVybCgjQSkiLz48bGluZWFyR3JhZGllbnQgaWQ9IkIiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiB4MT0iMTMxLjAyOSIgeTE9IjIzMy45MzYiIHgyPSIxNDMuNSIgeTI9IjIzMy45MzYiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2M4YjA5MSIvPjxzdG9wIG9mZnNldD0iLjE5OSIgc3RvcC1jb2xvcj0iI2M1YTc4OCIvPjxzdG9wIG9mZnNldD0iLjUyOSIgc3RvcC1jb2xvcj0iI2JjOGU2ZSIvPjxzdG9wIG9mZnNldD0iLjk0OCIgc3RvcC1jb2xvcj0iI2FkNjc0NSIvPjxzdG9wIG9mZnNldD0iLjk5NCIgc3RvcC1jb2xvcj0iI2FiNjI0MCIvPjwvbGluZWFyR3JhZGllbnQ+PHBhdGggZD0iTTE0My41IDM2My4zNzNWMTA0LjVoLTEyLjQ3bC4zMTMgMjIyLjUxNGMwIDExLjA1My4zMTQgMTkuMTk2IDEuNTcgMjMuODUyczUuMjkzIDEwLjc2MiA3LjE3NyAxMS42MzQgMy40MTIuODczIDMuNDEyLjg3M3oiIGZpbGw9InVybCgjQikiIGNsYXNzPSJKIEsiLz48bGluZWFyR3JhZGllbnQgaWQ9IkMiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiB4MT0iMTMxLjk5OCIgeTE9IjM0MS4yMzEiIHgyPSIxNDIuNzYiIHkyPSIzNDEuMjMxIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM4ODc4NmYiLz48c3RvcCBvZmZzZXQ9Ii4xMDUiIHN0b3AtY29sb3I9IiM4MDZmNjYiLz48c3RvcCBvZmZzZXQ9Ii4yODEiIHN0b3AtY29sb3I9IiM2YjU3NGMiLz48c3RvcCBvZmZzZXQ9Ii41MDMiIHN0b3AtY29sb3I9IiM0OTMwMjMiLz48c3RvcCBvZmZzZXQ9Ii42MjIiIHN0b3AtY29sb3I9IiMzNDE4MGEiLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMzZTIzMTYiLz48L2xpbmVhckdyYWRpZW50PjxwYXRoIGQ9Ik0xNDIuNjYzIDMzMmgtMTAuNjY1czAgMTUuODggMS4zNTcgMTguMjA3bDkuNDA1LjI1M3oiIGZpbGw9InVybCgjQykiLz48ZyBzdHJva2UtbWl0ZXJsaW1pdD0iMTAiIGNsYXNzPSJJIEsgTSI+PHBhdGggZD0iTTEyNy4zNDUgMTYzLjkzOHMtMy4yIDUuNTI2LTMuMDA2IDcuMjcgNi4yMDYuNDg2IDYuNTkzLTEuNzQ1LTMuNTg3LTUuNTI2LTMuNTg3LTUuNTI2em0zLjEgMjUuOGMyLjYyLjE0NSA3LjQxNy40MzcgOS4xNjMtMS44OTJzNS45NjItNC41MDggNS45NjItNy4xMjUtLjcyNy00LjA3Mi0zLjM0NC02LjEwOC0xNS40MTYgMi45LTE2LjE0NCA0LjIxNy0xLjc0NSA0Ljk0NS0xLjMwOCA1Ljk2MyAxLjMwOCAyLjkgMi42MTcgMy43OCAzLjA1NCAxLjE2NCAzLjA1NCAxLjE2NHoiLz48cGF0aCBkPSJNMTM4IDE3OC45NjVsMy41IDIuNDcyczMuNS0yLjc2My4yOTItNC44LTQuMDcyIDEuMDE4LTQuMDcyIDEuMDE4eiIvPjxwYXRoIGQ9Ik0xMjMuMDc4IDE4NS4yNjdjMS43NDUuNDg1IDEuNTUzIDEuNjUgNi4wMTIuNDg1czkuNS01LjA0MiAxMC45NTYtOC41MzItNi43LTkuMi0xMC4wODMtOC40MzUtOS4yIDMuNTg3LTEwLjcxNCA1LjUyNi0xLjc5MyA1LjcyLS44MjQgNy4xNzQgNC42NTMgMy43ODIgNC42NTMgMy43ODJ6bTE1LjgwMi0yNy4wNWMtMS4wNjYtMS41NS0yLjEzMi00LjY1NC0zLjUtNS41MjdzLTUuODE2LTQuMzYzLTcuMTc0LTUuMjM1LTUuNTI3LTQuMDcyLTkuMTE0LTMuMTAzLTYuODgzIDMuMDA2LTYuNCA3Ljg1MyAzLjU4NyA1LjMzMyA1LjIzNSA2Ljk4IDMuOTc2IDMuOTc2IDUuMzMzIDQuNzUgNS4yMzUgMi42MTggOC4xNDQgMi45IDUuNzItMS41NTIgNi43ODctMy4zOTQuNjc4LTUuMjM1LjY3OC01LjIzNXoiLz48cGF0aCBkPSJNMTMzLjE2MiAxNTUuM2wtNC45NDQgOC4xNDRzNS4zOTYgMiA3LjM2OC0uOTdjMi43MTQtNC4wNzItMi40MjQtNy4xNzQtMi40MjQtNy4xNzR6Ii8+PHBhdGggZD0iTTE0Ni4wMDggMTUwLjg5N2MtNC4zNjQgMS4zLTE1LjI3IDExLjM0My0xNy40NTIgMTYuNzI1cy0xLjQ1NCAxMC4wMzUgMi45IDExLjc4IDEwLjc2Mi0yLjE4IDEyLjUwNy01LjM4IDQuNTA4LTEzLjUyNSA0LjUwOC0xMy41MjVtLTE3LjA1NCA4LjNsOS43OTIgNC45NDRzLTEuNDU1IDIuNzE0LTQuNDYgMy4xMDMtNi4zOTgtMi4wMzYtNi40OTYtNC4wNzIgMS4xNjMtMy45NzUgMS4xNjMtMy45NzV6bTE0LjkzLS44NzNjLjk3IDEuNzQ1IDYuMzAyIDYuNzg3IDkuMiA3LjA3OG0tLjg2MiAxMy4xODVjMi4wMzYtLjQ4NCAzLjM5NC0xLjY0OCA0LjY1NC0yLjYxOCIvPjwvZz48bGluZWFyR3JhZGllbnQgaWQ9IkQiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiB4MT0iMjc3LjE4OCIgeTE9IjE2MS40NDEiIHgyPSIyODQuNjA0IiB5Mj0iMTYxLjQ0MSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjZjhmYjliIi8+PHN0b3Agb2Zmc2V0PSIuMTI2IiBzdG9wLWNvbG9yPSIjZjVmODkyIi8+PHN0b3Agb2Zmc2V0PSIuMzM0IiBzdG9wLWNvbG9yPSIjZWZlZjc4Ii8+PHN0b3Agb2Zmc2V0PSIuNjAxIiBzdG9wLWNvbG9yPSIjZTNlMTRmIi8+PHN0b3Agb2Zmc2V0PSIuOTExIiBzdG9wLWNvbG9yPSIjZDRjZTE2Ii8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjY2ZjODA0Ii8+PC9saW5lYXJHcmFkaWVudD48ZyBjbGFzcz0iSyI+PGNpcmNsZSBjeD0iMjgwLjg5NiIgY3k9IjE2MS40NDEiIHI9IjMuNzA4IiBmaWxsPSJ1cmwoI0QpIiBjbGFzcz0iSSIvPjxjaXJjbGUgY3g9IjI4MC44NzEiIGN5PSIxNjEuNDE3IiByPSIyLjkwOCIgY2xhc3M9IkwgUCIvPjwvZz48bGluZWFyR3JhZGllbnQgaWQ9IkUiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiB4MT0iMjc2LjAyNSIgeTE9IjE4Mi4zODMiIHgyPSIyODMuNDQiIHkyPSIxODIuMzgzIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNmOGZiOWIiLz48c3RvcCBvZmZzZXQ9Ii4xMjYiIHN0b3AtY29sb3I9IiNmNWY4OTIiLz48c3RvcCBvZmZzZXQ9Ii4zMzQiIHN0b3AtY29sb3I9IiNlZmVmNzgiLz48c3RvcCBvZmZzZXQ9Ii42MDEiIHN0b3AtY29sb3I9IiNlM2UxNGYiLz48c3RvcCBvZmZzZXQ9Ii45MTEiIHN0b3AtY29sb3I9IiNkNGNlMTYiLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiNjZmM4MDQiLz48L2xpbmVhckdyYWRpZW50PjxnIGNsYXNzPSJLIj48Y2lyY2xlIGN4PSIyNzkuNzMzIiBjeT0iMTgyLjM4MyIgcj0iMy43MDgiIGZpbGw9InVybCgjRSkiIGNsYXNzPSJJIi8+PGNpcmNsZSBjeD0iMjc5LjcwOCIgY3k9IjE4Mi4zNTgiIHI9IjIuOTA5IiBjbGFzcz0iTCBQIi8+PC9nPjxsaW5lYXJHcmFkaWVudCBpZD0iRiIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIHgxPSIyNzQuODYiIHkxPSIyMDMuMzI1IiB4Mj0iMjgyLjI3OCIgeTI9IjIwMy4zMjUiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2Y4ZmI5YiIvPjxzdG9wIG9mZnNldD0iLjEyNiIgc3RvcC1jb2xvcj0iI2Y1Zjg5MiIvPjxzdG9wIG9mZnNldD0iLjMzNCIgc3RvcC1jb2xvcj0iI2VmZWY3OCIvPjxzdG9wIG9mZnNldD0iLjYwMSIgc3RvcC1jb2xvcj0iI2UzZTE0ZiIvPjxzdG9wIG9mZnNldD0iLjkxMSIgc3RvcC1jb2xvcj0iI2Q0Y2UxNiIvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2NmYzgwNCIvPjwvbGluZWFyR3JhZGllbnQ+PGcgY2xhc3M9IksiPjxjaXJjbGUgY3g9IjI3OC41NjkiIGN5PSIyMDMuMzI1IiByPSIzLjcwOSIgZmlsbD0idXJsKCNGKSIgY2xhc3M9IkkiLz48Y2lyY2xlIGN4PSIyNzguNTQ1IiBjeT0iMjAzLjMwMSIgcj0iMi45MDkiIGNsYXNzPSJMIFAiLz48cGF0aCBkPSJNMjUxLjU0MiA3Ny40NTRsLTMuMi0uODczcy0xLjc0NS4zODgtMS41NTIgMS4yNjIgMS40NTUgMS45NCAxLjM1NyAzLjUtLjMgNC41NTYuODc1IDYuNDk2IDMuOTc1IDQuODQ4IDUuNDMgNS42MjMgMS44NDItLjM4OCAxLjg0Mi0uMzg4IDEuMzU2IDEzLjk2IDEuNzQ2IDE1LjQxNiAyLjQyNCA1LjA0MiA1LjcyIDcuODU0IDguOTIgOS4yIDExLjUzOCAxMS4xNSAxMS4yNDYgMy41ODggMTQuOTMtLjE5NCAxMS42MzUtMTIuNTA3IDEyLjUwNy0xMy43NjggMy4zOTMtNC4yNjYgMy4yOTctNS40My0uNDg0LTEzLjU3NC0uNDg0LTE0LjA2Yy41OC4xOTQgMS44NC0uNDg0IDIuNTItMS4wNjZzNC45NDUtNS4yMzYgNC44NS03LjI3Mi0xLjM1OC03LjY2LS44NzItOC4wNDcgMS4xNjItMS45NC4zLTIuMzI3LTYuMDEyIDMuMzkzLTYuMDEyIDMuMzkzLTEuMDQyLTEzLjI1OC01LjgxNS0xNi42NzYtNDMuNDM4LTUuODE3LTQ1Ljc2NC0yLjcxNS0zLjIwNCAxOC4xMzItMy4yMDQgMTguMTMyeiIgY2xhc3M9IkkgSiBNIi8+PC9nPjxwYXRoIGQ9Ik0yNTggODguNzk3bC40NTcgNC43NS0xLjEzMi0yLjQ3Mi0xLjY4LTYuNjY2LTUuMDUzLTcuMzU2TDI1MCA2Ni40di0yLjAzNmwxNC4wMDYtNC41NTctNC4wNSA2LjEtMy4wOTIgOS41OTgtLjE1OCA0LjQ2TDI1OCA4Mi4zMDJ6Ii8+PHBhdGggZD0iTTMwOS4zMjggNzEuNWMxMC4wMzUgNi41NDQtMy4wNTQgNC42NTQtMTMuODE1IDEuMDE4cy0zMi4yODYtOS45LTM3LjIzMi0xMC4wMzUgMzIuNzI0LTMuMDU1IDM4LjU0LTEuMTY0IDEyLjUwNyAxMC4xOCAxMi41MDcgMTAuMTh6IiBmaWxsPSIjMTYxNjE2IiBjbGFzcz0iSSBKIEsiLz48bGluZWFyR3JhZGllbnQgaWQ9IkciIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiB4MT0iMjgwLjk2IiB5MT0iNjkuMDIiIHgyPSIyODAuOTYiIHkyPSIzMS43NDgiPjxzdG9wIG9mZnNldD0iLjM3MiIgc3RvcC1jb2xvcj0iIzFkMjczOSIvPjxzdG9wIG9mZnNldD0iLjk5NCIgc3RvcC1jb2xvcj0iIzFkMjczOSIvPjwvbGluZWFyR3JhZGllbnQ+PGcgc3Ryb2tlLW1pdGVybGltaXQ9IjEwIiBjbGFzcz0iSSBLIj48cGF0aCBkPSJNMjQ3LjU2OCA2MS4yNjNjLTEyLjQtNi0xMi40LTEzLjc2Ny43NzYtMjIuMTA1czM3LjIzLTguNzI2IDQ4LjQ3Ni01LjYyNCAyOC42OTggMTQuMTU1IDI2LjU2NiAyNS4wMTVjLTIuMTMyIDguMzM3LTExLjgzIDEwLjQ3LTExLjgzIDEwLjQ3eiIgZmlsbD0idXJsKCNHKSIvPjxwYXRoIGQ9Ik0yNDguNjg0IDY1LjM4M2wtMS40NTYtNi41NDRjMTcuOS0xMC42MTcgNTAuOS0xMC45MDggNjUuNzM1IDcuMTI2LS40MzcgMS4zMDgtMi4zMjYgNC41MDgtMy42MzYgNS41MjYtMjUuNDUtMTguOTA2LTYwLjY0My02LjEwOC02MC42NDMtNi4xMDh6IiBmaWxsPSIjMDM0NjhiIi8+PC9nPjxwYXRoIGQ9Ik0yNzUuMDA3IDU2LjY1N2w2LjY4OC44NzMtLjMgMS43NDQtMTEuOTI1LTEuMDE3IDguNzI3LTcuODU0LTUuOTY0LS4zLjE0Ny0xLjkgMTAuOTA2IDEuM3ptMTcuNTIzLTUuNmMzLjI3MiAxLjkgNC4zNjQgNC45NDQgMy4yIDcuNTYycy01LjM4MiAyLjgzNS03LjE5OCAyLjI1NC02LjAzNy0zLjM0NS00LjA3Mi03LjcwOGMxLjMwOC0yLjU0NCA0Ljc5OC00IDguMDctMi4xMDh6bS01Ljk0IDMuMjg4Yy0xLjIwNSAyLjY3NyAxLjM4MyA0LjM3MiAyLjUgNC43M3MzLjcwMi4yMjIgNC40MTYtMS4zODIuMDQ2LTMuNDgtMS45NjQtNC42NC00LjE1LS4yNjgtNC45NSAxLjI5NHptMTYuOTgyLS4wMDdjMy4wMTIgMS42MDMgNC40NTQgNC43NjQgMy45NzcgNy43NnMtMy44OCAzLjgwNC01LjQ3MiAzLjQyLTUuNTMtMi44MDQtNC43MTQtNy43OThjLjYtMi45MzYgMy4xOTYtNC45ODcgNi4yLTMuMzgyem0tNC4yNTYgNC4zN2MtLjUwNCAzLjA2NSAxLjkxOCA0LjU1IDIuOSA0Ljc4NnMzLjA2My0uMjYyIDMuMzU3LTIuMDk4LS42LTMuNzc3LTIuNDQtNC43NjMtMy40MzUuMjczLTMuODA4IDIuMDc1eiIgZmlsbD0iI2ZmZiIvPjxwYXRoIGQ9Ik0zMDMuMTg3IDczLjQ4bDEuMjc3IDYuNzg3LTEuOCA0Ljk0NS4zMzYgNS40M3YyLjhsMS42LTIuMzI3LjY2My04LjE0NCAzLjA0NS01LjUyNi4yNjItMy4yeiIvPjxnIHN0cm9rZS1taXRlcmxpbWl0PSIxMCIgY2xhc3M9IksgTCI+PHBhdGggZD0iTTMwMC43IDgxLjYyNGMtLjk3LS41ODMtMy4zOTQtMi45LTQuNTU3LTIuOXMtNC4zNjQuOTctNS44MTcgMS4wNjYtNS45MTQgMS44NC02LjMwMyAyLjIzbS05Ljk4Ni4xOTVjLS45NyAwLTMuODc4LS45Ny00LjQ2LTEuMjZzLTMuNS0uMTk0LTMuNS0uMTk0bC0yLjIzLTEuNDU1LTMuMDA2IDIuODEyIi8+PHBhdGggZD0iTTI3NS43ODIgODUuMDE2Yy42OC4zODggMi4yMyAyLjUyIDIuMTM1IDMuNjg0cy0xLjc0NyAxMi4zMTMtMS41NTMgMTIuNjA0IDMuNzguODcyIDQuMjY3LjQ4NW0yLjYxNy0xLjE2M2MuNjgtLjA5NyAxLjU1Mi0uMyAyLjIzLjU4Mk0yNzMuNjUgODYuNzZjLTEuNjQ3LTMuNS04LjM0LTMuNS0xMC44Ni4wOThtMjMuMzY3LjE5NGMuNzc0LTQuMjY1IDEwLjU2Ny01LjEzOCAxMi43LS44NzIiIGNsYXNzPSJJIi8+PC9nPjxlbGxpcHNlIGN4PSIyNjguNDE0IiBjeT0iODYuNzEzIiByeD0iMy4wMDYiIHJ5PSIyLjM3NSIvPjxlbGxpcHNlIGN4PSIyOTIuMTE5IiBjeT0iODUuNzQ0IiByeD0iMy4xNTEiIHJ5PSIyLjQ3MiIvPjxnIHN0cm9rZS1taXRlcmxpbWl0PSIxMCIgY2xhc3M9IkkgSyI+PHBhdGggZD0iTTI2OS44NjcgMTA3Ljk5NWM0LjY1NSA1LjkxNCAxOC41MiA1LjcyIDIxLjY5NS0uOTctMS4wNjcuMy0yLjc1Mi45Mi0yLjc1Mi45MnMtNS43NTguMjQzLTcuMDE4LjkyMmMtLjg3IDAtMi4wMzUuMTkzLTIuMDM1LjE5M3MtNS43Mi0uNzc2LTYuNTk0LS4xOTMtMy4yOTYtLjg3My0zLjI5Ni0uODczeiIgZmlsbD0iI2Q4ZDhkOCIvPjxwYXRoIGQ9Ik0yODguMyAxMTIuNjQ4Yy0zLjEwNCAzLjY4NC0xMS4wNTQgMy41ODctMTQuMjUzLjc3NSIgY2xhc3M9IkwiLz48L2c+PHBhdGggZD0iTTI4OS4wMTcgODUuMzU1bDMuNTg2LjQzNy0zLjA1NCAxLjM1N2MtLjU4LS41OC0uNTMyLTEuNzk0LS41MzItMS43OTR6bS0yMy4yNyAxLjE2NWwzLjU4Ni40MzctMy4wNTMgMS4zNThjLS41ODItLjU4My0uNTMzLTEuNzk1LS41MzMtMS43OTV6IiBmaWxsPSIjZmNmY2ZjIi8+PHBhdGggZD0iTTMwOS45IDc5LjJjLS42NTMgMS4xNjMtMi41NDQgMy41NjMtMi43IDQuNzI2cy44IDQuMTQ1LjcyOCA0LjcyN20xLjE2Mi0yLjE4M2MtLjE0Ni0uOC0uNjU1LTIuOTgtMS40NTUtMy40MThtLTU4LjA4LTMuOTI2Yy43MjggMS4wMiA0LjQzNiA0LjA3MiA0LjU4IDUuM3MtLjggMy4xMjctLjUgNC4yMTcgMS4wMiAyLjc2MyAxLjAyIDIuNzYzbS0yLjQtMy44NTRjLS4yMi0xLjE2My4wNzItMy43IDEuMTYyLTQiIGNsYXNzPSJJIEogSyBMIi8+PC9nPjwvc3ZnPg==" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换深色 / 浅色主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none"><span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span></button>
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
