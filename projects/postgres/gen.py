#!/usr/bin/env python3
"""postgres-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd postgres-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import json
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 PostgreSQL 交互式核心原理图谱（离线自包含 HTML）")
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
    os.environ.get("POSTGRES_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("POSTGRES_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     新家族（PostgreSQL）：元模式 = 接口 × 能力域 × 时机。
#     全景 + 4 接触面主线（SQL 四类：DDL/DML/DQL/DCL）+ 8 支撑能力域。
# ===================================================================== #
MAINLINES = [
    ("Postgres原理_全景主线框架", "pano", "◇", "全景主线框架",
     "postmaster + per-connection backend 进程 + 共享内存 + 自管存储：双维模型 · 总架构 · 三条贯穿声明"),

    ("Postgres原理_DDL数据定义", "iface", "⚙", "DDL 数据定义",
     "CREATE/ALTER/DROP · 写系统目录 pg_catalog · 事务性 DDL(可回滚)"),
    ("Postgres原理_DML数据写入", "iface", "✎", "DML 数据写入",
     "INSERT/UPDATE/DELETE · heap 追加 + 旧版本标记 · 走 WAL 先写日志"),
    ("Postgres原理_DQL数据查询", "iface", "▦", "DQL 数据查询",
     "SELECT · Parser→Analyzer→Planner→Executor 流水线 · 快照可见性判定"),
    ("Postgres原理_DCL数据控制", "iface", "◐", "DCL 数据控制",
     "GRANT/REVOKE · 角色与权限 · row-level security"),

    ("Postgres原理_支撑_进程与内存架构", "support", "▤", "进程与内存架构",
     "核心：postmaster 每连接 fork 一 backend + 辅助进程 · shared_buffers/WAL buffers/锁表 共享内存"),
    ("Postgres原理_支撑_存储引擎", "support", "◫", "存储引擎",
     "heap 行存 + 8KB page · TOAST 大字段 · shared_buffers 缓冲池 · 自管 PGDATA"),
    ("Postgres原理_支撑_索引方法", "support", "▦", "索引方法",
     "B-tree/Hash/GiST/GIN/BRIN · 可扩展 access method · 索引扫描 vs 顺序扫描"),
    ("Postgres原理_支撑_查询优化器", "support", "◐", "查询优化器",
     "灵魂：基于代价的 Planner · 统计信息 + 选择率 · Join 顺序/方法枚举 · 生成计划树"),
    ("Postgres原理_支撑_执行引擎", "support", "⚙", "执行引擎",
     "火山模型 Portal · 计划节点树逐行拉取 · 各种扫描/连接/聚合算子"),
    ("Postgres原理_支撑_事务与MVCC", "support", "⛨", "事务与 MVCC",
     "每行 xmin/xmax 多版本 · 快照隔离 · CLOG 事务状态 · VACUUM 回收死元组"),
    ("Postgres原理_支撑_并发控制与锁", "support", "◉", "并发控制与锁",
     "表/行/咨询锁 · ProcArray 快照 · 死锁检测 · 轻量锁 LWLock 保护共享内存"),
    ("Postgres原理_支撑_WAL与恢复复制", "support", "⛨", "WAL 与恢复/复制",
     "预写日志 WAL · checkpoint · crash recovery 重放 · 流复制/物理逻辑复制"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接触面主线 · SQL 四类"),
    ("support", "支撑主线 · 引擎内部（8 条能力域）"),
]

# ===================================================================== #
# 一·b、项目总架构图 = 唯一导航底图 —— 热区注册表（决定"点击下钻"）
#   产出准则（用户明确要求）：项目页统一用【项目总架构图】(ARCH_SVG_NAME) 做导航，
#   在图上叠透明热区，每个语义模块 = 一个可点区域 → 下钻对应主线。
#   坐标系 = 该总架构 SVG 的 viewBox（ARCH_W×ARCH_H），生成期换算成百分比定位。
#   两条覆盖铁律：① 图上每个模块都有热区 ② 每条主线都被某热区覆盖（未覆盖者自动兜底成 chip）。
# ===================================================================== #
PANO_NAME = "Postgres原理_全景主线框架"
# (x, y, w, h, 主线name) —— 坐标取自总架构 SVG 的真实 rect（viewBox 1020×680）
# 未被上面热区覆盖的主线（DDL/DML 是 SQL 写动作、事务与MVCC 贯穿多处，图上无独立区域）
# 由 build_archnav 自动兜底成底部 chip —— 故此处显式清单留空。
ARCH_ALWAYS_CHIP = [
    "Postgres原理_DDL数据定义",
    "Postgres原理_DML数据写入",
    "Postgres原理_支撑_事务与MVCC",
]

BRAND_TITLE = "一切知识皆索引"
BRAND_SUB = "PostgreSQL"
HOME_DESC = ("PostgreSQL 核心原理设计文档库的离线交互图谱——经典关系型数据库："
             "postmaster 每连接 fork 一 backend 进程 + 共享内存 + 自管 PGDATA 存储 + WAL + MVCC。"
             "13 条主线、手绘原理图，全部回 postgres 源码核实。点击项目总架构图任意模块即可下钻到对应主线。")
ARCH_SVG_NAME = "Postgres原理_全景_02总架构.svg"
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
        '<img alt="PostgreSQL 项目总架构图" src="data:image/svg+xml;base64,%s"/>'
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
  <a class="logo" id="logo" href="../../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a><div class="brand-intro" style="display:flex;flex-direction:column;align-items:flex-start;margin-left:12px;min-width:0;max-width:min(60vw,760px)"><div style="font-size:15px;font-weight:600;color:var(--c-ink);line-height:1.3">PostgreSQL · 核心原理图谱</div><span style="margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5;text-align:left">进程级关系数据库内核:postmaster 每连接 fork 一 backend,共享内存协调,MVCC 多版本 + WAL 先写日志,代价优化 + 火山执行。</span></div>
  <div class="spacer"></div>
  <label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label>
  <a href="https://github.com/postgres/postgres" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://www.postgresql.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjNDE2OUUxIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+UG9zdGdyZVNRTDwvdGl0bGU+PHBhdGggZD0iTTIzLjU1OTQgMTQuNzIyOGEuNTI2OS41MjY5IDAgMCAwLS4wNTYzLS4xMTkxYy0uMTM5LS4yNjMyLS40NzY4LS4zNDE4LTEuMDA3NC0uMjMyMS0xLjY1MzMuMzQxMS0yLjI5MzUuMTMxMi0yLjUyNTYtLjAxOTEgMS4zNDItMi4wNDgyIDIuNDQ1LTQuNTIyIDMuMDQxMS02LjgyOTcuMjcxNC0xLjA1MDcuNzk4Mi0zLjUyMzcuMTIyMi00LjczMTZhMS41NjQxIDEuNTY0MSAwIDAgMC0uMTUwOS0uMjM1QzIxLjY5MzEuOTA4NiAxOS44MDA3LjAyNDggMTcuNTA5OS4wMDA1Yy0xLjQ5NDctLjAxNTgtMi43NzA1LjM0NjEtMy4xMTYxLjQ3OTRhOS40NDkgOS40NDkgMCAwIDAtLjUxNTktLjA4MTYgOC4wNDQgOC4wNDQgMCAwIDAtMS4zMTE0LS4xMjc4Yy0xLjE4MjItLjAxODQtMi4yMDM4LjI2NDItMy4wNDk4Ljg0MDYtLjg1NzMtLjMyMTEtNC43ODg4LTEuNjQ1LTcuMjIxOS4wNzg4Qy45MzU5IDIuMTUyNi4zMDg2IDMuODczMy40MzAyIDYuMzA0M2MuMDQwOS44MTguNTA2OSAzLjMzNCAxLjI0MjMgNS43NDM2LjQ1OTggMS41MDY1LjkzODcgMi43MDE5IDEuNDMzNCAzLjU4Mi41NTMuOTk0MiAxLjEyNTkgMS41OTMzIDEuNzE0MyAxLjc4OTUuNDQ3NC4xNDkxIDEuMTMyNy4xNDQxIDEuODU4MS0uNzI3OS44MDEyLS45NjM1IDEuNTkwMy0xLjgyNTggMS45NDQ2LTIuMjA2OS40MzUxLjIzNTUuOTA2NC4zNjI1IDEuMzkuMzc3MmEuMDU2OS4wNTY5IDAgMCAwIC4wMDA0LjAwNDEgMTEuMDMxMiAxMS4wMzEyIDAgMCAwLS4yNDcyLjMwNTRjLS4zMzg5LjQzMDItLjQwOTQuNTE5Ny0xLjUwMDIuNzQ0My0uMzEwMi4wNjQtMS4xMzQ0LjIzMzktMS4xNDY0LjgxMTUtLjAwMjUuMTIyNC4wMzI5LjIzMDkuMDkxOS4zMjY4LjIyNjkuNDIzMS45MjE2LjYwOTcgMS4wMTUuNjMzMSAxLjMzNDUuMzMzNSAyLjUwNDQuMDkyIDMuMzcxNC0uNjc4Ny0uMDE3IDIuMjMxLjA3NzUgNC40MTc0LjM0NTQgNS4wODc0LjIyMTIuNTUyOS43NjE4IDEuOTA0NSAyLjQ2OTIgMS45MDQzLjI1MDUgMCAuNTI2My0uMDI5MS44Mjk2LS4wOTQxIDEuNzgxOS0uMzgyMSAyLjU1NTctMS4xNjk2IDIuODU1LTIuOTA1OS4xNTAzLS44NzA3LjQwMTYtMi44NzUzLjUzODgtNC4xMDEyLjAxNjktLjA3MDMuMDM1Ny0uMTIwNy4wNTctLjEzNjIuMDAwNy0uMDAwNS4wNjk3LS4wNDcxLjQyNzIuMDMwN2EuMzY3My4zNjczIDAgMCAwIC4wNDQzLjAwNjhsLjI1MzkuMDIyMy4wMTQ5LjAwMWMuODQ2OC4wMzg0IDEuOTExNC0uMTQyNiAyLjUzMTItLjQzMDguNjQzOC0uMjk4OCAxLjgwNTctMS4wMzIzIDEuNTk1MS0xLjY2OTh6TTIuMzcxIDExLjg3NjVjLS43NDM1LTIuNDM1OC0xLjE3NzktNC44ODUxLTEuMjEyMy01LjU3MTktLjEwODYtMi4xNzE0LjQxNzEtMy42ODI5IDEuNTYyMy00LjQ5MjcgMS44MzY3LTEuMjk4NiA0LjgzOTgtLjU0MDggNi4xMDgtLjEzLS4wMDMyLjAwMzItLjAwNjYuMDA2MS0uMDA5OC4wMDk0LTIuMDIzOCAyLjA0NC0xLjk3NTggNS41MzYtMS45NzA4IDUuNzQ5NS0uMDAwMi4wODIzLjAwNjYuMTk4OS4wMTYyLjM1OTMuMDM0OC41ODczLjA5OTYgMS42ODA0LS4wNzM1IDIuOTE4NC0uMTYwOSAxLjE1MDQuMTkzNyAyLjI3NjQuOTcyOCAzLjA4OTIuMDgwNi4wODQxLjE2NDguMTYzMS4yNTE4LjIzNzQtLjM0NjguMzcxNC0xLjEwMDQgMS4xOTI2LTEuOTAyNSAyLjE1NzYtLjU2NzcuNjgyNS0uOTU5Ny41NTE3LTEuMDg4Ni41MDg3LS4zOTE5LS4xMzA3LS44MTMtLjU4NzEtMS4yMzgxLTEuMzIyMy0uNDc5Ni0uODM5LS45NjM1LTIuMDMxNy0xLjQxNTUtMy41MTI2em02LjAwNzIgNS4wODcxYy0uMTcxMS0uMDQyOC0uMzI3MS0uMTEzMi0uNDMyMi0uMTc3Mi4wODg5LS4wMzk0LjIzNzQtLjA5MDIuNDgzMy0uMTQwOSAxLjI4MzMtLjI2NDEgMS40ODE1LS40NTA2IDEuOTE0My0xLjAwMDIuMDk5Mi0uMTI2LjIxMTYtLjI2ODcuMzY3My0uNDQyNmEuMzU0OS4zNTQ5IDAgMCAwIC4wNzM3LS4xMjk4Yy4xNzA4LS4xNTEzLjI3MjQtLjEwOTkuNDM2OS0uMDQxNy4xNTYuMDY0Ni4zMDc4LjI2LjM2OTUuNDc1Mi4wMjkxLjEwMTYuMDYxOS4yOTQ1LS4wNDUyLjQ0NDQtLjkwNDMgMS4yNjU4LTIuMjIxNiAxLjI0OTQtMy4xNjc2IDEuMDEyOHptMi4wOTQtMy45ODgtLjA1MjUuMTQxYy0uMTMzLjM1NjYtLjI1NjcuNjg4MS0uMzMzNCAxLjAwMy0uNjY3NC0uMDAyMS0xLjMxNjgtLjI4NzItMS44MTA1LS44MDI0LS42Mjc5LS42NTUxLS45MTMxLTEuNTY2NC0uNzgyNS0yLjUwMDQuMTgyOC0xLjMwNzkuMTE1My0yLjQ0NjguMDc5LTMuMDU4Ni0uMDA1LS4wODU3LS4wMDk1LS4xNjA3LS4wMTIyLS4yMTk5LjI5NTctLjI2MjEgMS42NjU5LS45OTYyIDIuNjQyOS0uNzcyNC40NDU5LjEwMjIuNzE3Ni40MDU3LjgzMDUuOTI4LjU4NDYgMi43MDM4LjA3NzQgMy44MzA3LS4zMzAyIDQuNzM2My0uMDg0LjE4NjYtLjE2MzMuMzYyOS0uMjMxMS41NDU0em03LjM2MzcgNC41NzI1Yy0uMDE2OS4xNzY4LS4wMzU4LjM3Ni0uMDYxOC41OTU5bC0uMTQ2LjQzODNhLjM1NDcuMzU0NyAwIDAgMC0uMDE4Mi4xMDc3Yy0uMDA1OS40NzQ3LS4wNTQuNjQ4OS0uMTE1Ljg2OTMtLjA2MzQuMjI5Mi0uMTM1My40ODkxLS4xNzk0IDEuMDU3NS0uMTEgMS40MTQzLS44NzgyIDIuMjI2Ny0yLjQxNzIgMi41NTY1LTEuNTE1NS4zMjUxLTEuNzg0My0uNDk2OC0yLjAyMTItMS4yMjE3YTYuNTgyNCA2LjU4MjQgMCAwIDAtLjA3NjktLjIyNjZjLS4yMTU0LS41ODU4LS4xOTExLTEuNDExOS0uMTU3NC0yLjU1NTEuMDE2NS0uNTYxMi0uMDI0OS0xLjkwMTMtLjMzMDItMi42NDYyLjAwNDQtLjI5MzIuMDEwNi0uNTkwOS4wMTktLjg5MThhLjM1MjkuMzUyOSAwIDAgMC0uMDE1My0uMTEyNiAxLjQ5MjcgMS40OTI3IDAgMCAwLS4wNDM5LS4yMDhjLS4xMjI2LS40MjgzLS40MjEzLS43ODY2LS43Nzk3LS45MzUxLS4xNDI0LS4wNTktLjQwMzgtLjE2NzItLjcxNzgtLjA4NjkuMDY3LS4yNzYuMTgzMS0uNTg3NS4zMDktLjkyNDlsLjA1MjktLjE0MmMuMDU5NS0uMTYuMTM0LS4zMjU3LjIxMy0uNTAxMi40MjY1LS45NDc2IDEuMDEwNi0yLjI0NTMuMzc2Ni01LjE3NzItLjIzNzQtMS4wOTgxLTEuMDMwNC0xLjYzNDMtMi4yMzI0LTEuNTA5OC0uNzIwNy4wNzQ2LTEuMzc5OS4zNjU0LTEuNzA4OC41MzIxYTUuNjcxNiA1LjY3MTYgMCAwIDAtLjE5NTguMTA0MWMuMDkxOC0xLjEwNjQuNDM4Ni0zLjE3NDEgMS43MzU3LTQuNDgyM2E0LjAzMDYgNC4wMzA2IDAgMCAxIC4zMDMzLS4yNzYuMzUzMi4zNTMyIDAgMCAwIC4xNDQ3LS4wNjQ0Yy43NTI0LS41NzA2IDEuNjk0NS0uODUwNiAyLjgwMi0uODMyNS40MDkxLjAwNjcuODAxNy4wMzM5IDEuMTc0Mi4wODEgMS45MzkuMzU0NCAzLjI0MzkgMS40NDY4IDQuMDM1OSAyLjM4MjcuODE0My45NjIzIDEuMjU1MiAxLjkzMTUgMS40MzEyIDIuNDU0My0xLjMyMzItLjEzNDYtMi4yMjM0LjEyNjgtMi42Nzk3Ljc3OS0uOTkyNiAxLjQxODkuNTQzIDQuMTcyOSAxLjI4MTEgNS40OTY0LjEzNTMuMjQyNi4yNTIyLjQ1MjIuMjg4OS41NDEzLjI0MDMuNTgyNS41NTE1Ljk3MTMuNzc4NyAxLjI1NTIuMDY5Ni4wODcuMTM3Mi4xNzE0LjE4ODUuMjQ1LS40MDA4LjExNTUtMS4xMjA4LjM4MjUtMS4wNTUyIDEuNzE3LS4wMTIzLjE1NjMtLjA0MjMuNDQ2OS0uMDgzNC44MTQ4LS4wNDYxLjIwNzctLjA3MDIuNDYwMy0uMDk5NC43NjYyem0uODkwNS0xLjYyMTFjLS4wNDA1LS44MzE2LjI2OTEtLjkxODUuNTk2Ny0xLjAxMDVhMi44NTY2IDIuODU2NiAwIDAgMCAuMTM1LS4wNDA2IDEuMjAyIDEuMjAyIDAgMCAwIC4xMzQyLjEwM2MuNTcwMy4zNzY1IDEuNTgyMy40MjEzIDMuMDA2OC4xMzQ0LS4yMDE2LjE3NjktLjUxODkuMzk5NC0uOTUzMy42MDExLS40MDk4LjE5MDMtMS4wOTU3LjMzMy0xLjc0NzMuMzYzNi0uNzE5Ny4wMzM2LTEuMDg1OS0uMDgwNy0xLjE3MjEtLjE1MXptLjU2OTUtOS4yNzEyYy0uMDA1OS4zNTA4LS4wNTQyLjY2OTItLjEwNTQgMS4wMDE3LS4wNTUuMzU3Ni0uMTEyLjcyNzQtLjEyNjQgMS4xNzYyLS4wMTQyLjQzNjguMDQwNC44OTA5LjA5MzIgMS4zMzAxLjEwNjYuODg3LjIxNiAxLjgwMDMtLjIwNzUgMi43MDE0YTMuNTI3MiAzLjUyNzIgMCAwIDEtLjE4NzYtLjM4NTZjLS4wNTI3LS4xMjc2LS4xNjY5LS4zMzI2LS4zMjUxLS42MTYyLS42MTU2LTEuMTA0MS0yLjA1NzQtMy42ODk2LTEuMzE5My00Ljc0NDYuMzc5NS0uNTQyNyAxLjM0MDgtLjU2NjEgMi4xNzgxLS40NjN6bS4yMjg0IDcuMDEzN2ExMi4zNzYyIDEyLjM3NjIgMCAwIDAtLjA4NTMtLjEwNzRsLS4wMzU1LS4wNDQ0Yy43MjYyLTEuMTk5NS41ODQyLTIuMzg2Mi40NTc4LTMuNDM4NS0uMDUxOS0uNDMxOC0uMTAwOS0uODM5Ni0uMDg4NS0xLjIyMjYuMDEyOS0uNDA2MS4wNjY2LS43NTQzLjExODUtMS4wOTExLjA2MzktLjQxNS4xMjg4LS44NDQzLjExMDktMS4zNTA1LjAxMzQtLjA1MzEuMDE4OC0uMTE1OC4wMTE4LS4xOTAyLS4wNDU3LS40ODU1LS41OTk5LTEuOTM4LTEuNzI5NC0zLjI1My0uNjA3Ni0uNzA3My0xLjQ4OTYtMS40OTcyLTIuNjg4OS0yLjAzOTUuNTI1MS0uMTA2NiAxLjIzMjgtLjIwMzUgMi4wMjQ0LS4xODU5IDIuMDUxNS4wNDU2IDMuNjc0Ni44MTM1IDQuODI0MiAyLjI4MjRhLjkwOC45MDggMCAwIDEgLjA2NjcuMTAwMmMuNzIzMSAxLjM1NTYtLjI3NjIgNi4yNzUxLTIuOTg2NyAxMC41NDA1em0tOC44MTY2LTYuMTE2MmMtLjAyNS4xNzk0LS4zMDg5LjQyMjUtLjYyMTEuNDIyNWEuNTgyMS41ODIxIDAgMCAxLS4wODA5LS4wMDU2Yy0uMTg3My0uMDI2LS4zNzY1LS4xNDQtLjUwNTktLjMxNTYtLjA0NTgtLjA2MDUtLjEyMDMtLjE3OC0uMTA1NS0uMjg0NC4wMDU1LS4wNDAxLjAyNjEtLjA5ODUuMDkyNS0uMTQ4OC4xMTgyLS4wODk0LjM1MTgtLjEyMjYuNjA5Ni0uMDg2Ny4zMTYzLjA0NDEuNjQyNi4xOTM4LjYxMTMuNDE4NnptNy45MzA1LS40MTE0Yy4wMTExLjA3OTItLjA0OS4yMDEtLjE1MzEuMzEwMi0uMDY4My4wNzE3LS4yMTIuMTk2MS0uNDA3OS4yMjMyYS41NDU2LjU0NTYgMCAwIDEtLjA3NS4wMDUyYy0uMjkzNSAwLS41NDE0LS4yMzQ0LS41NjA3LS4zNzE3LS4wMjQtLjE3NjUuMjY0MS0uMzEwNi41NjExLS4zNTIuMjk3LS4wNDE0LjYxMTEuMDA4OC42MzU2LjE4NTF6Ii8+PC9zdmc+" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换深色 / 浅色主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none"><span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span></button>
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
