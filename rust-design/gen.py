#!/usr/bin/env python3
"""rust-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd rust-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 Rust 交互式核心原理图谱（离线自包含 HTML）")
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
    os.environ.get("RUST_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("RUST_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     新家族（湖仓表格式 · 开放表格式 · Apache Iceberg）：元模式 = 接口 × 能力域 × 时机。
#     全景 + 1 接触面主线 + 8 支撑能力域。
# ===================================================================== #
MAINLINES = [
    ("Rust原理_全景主线框架", "pano", "◇", "全景主线框架",
     "新家族语言运行时/编译器：双维模型 · 总架构 · 依赖矩阵 · 依赖关系图 · 三条贯穿声明"),

    ("Rust原理_接触面_语法与所有权", "iface", "⚙", "接触面 · 语法与所有权规则",
     "开发者心智模型：所有权(每值一主+move)· 借用(&T 多/&mut T 唯一)· 生命周期(防悬垂)"),

    ("Rust原理_支撑_编译管线", "support", "▤", "编译管线",
     "AST→HIR→THIR→MIR→codegen(LLVM)· query 系统 + 增量编译 · MIR 是中心舞台"),
    ("Rust原理_支撑_借用检查器", "support", "✦", "借用检查器(灵魂)",
     "灵魂：MIR 上验所有权/借用/生命周期 · NLL 非词法 + Polonius 区域推断 · 过不了不编译"),
    ("Rust原理_支撑_特质与单态化", "support", "◈", "特质与单态化",
     "trait 求解 + 泛型→具体单态化(零成本抽象)· 静态分发默认 · dyn 才虚表"),
    ("Rust原理_支撑_类型推断", "support", "◫", "类型推断",
     "合一(union-find)少标注推类型 · 体内推断签名必标 · 与区域推断两套"),
    ("Rust原理_支撑_内存与Drop", "support", "◧", "内存与 Drop",
     "无 GC：RAII/Drop 出作用域自动析构 · move 语义 · 编译器插 Drop glue 零开销"),
    ("Rust原理_支撑_并发SendSync", "support", "◐", "并发 Send/Sync",
     "无畏并发：marker trait 编译期保无数据竞争 · thread::spawn Send 边界 · Arc/Mutex"),
    ("Rust原理_支撑_智能指针与内部可变", "support", "▩", "智能指针与内部可变",
     "Box/Rc/Arc + UnsafeCell/Cell/RefCell · 所有权太死时的受控逃生舱"),
    ("Rust原理_支撑_panic与展开", "support", "◉", "panic 与展开",
     "不可恢复错误：展开(逐层析构可 catch)vs abort(直接终止)· catch_unwind 边界捕获"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接触面主线 · 开发者如何用(语法 + 所有权)"),
    ("support", "支撑主线 · 编译器与运行时内部(8 条能力域)"),
]

PANO_NAME = "Rust原理_全景主线框架"
ARCH_W, ARCH_H = 1080, 820
ARCH_HOTSPOTS = [
    (0, 0, 1080, 58, "Rust原理_全景主线框架"),
    (30, 64, 1020, 46, "Rust原理_接触面_语法与所有权"),
    (30, 124, 1020, 180, "Rust原理_支撑_编译管线"),
    (30, 316, 330, 78, "Rust原理_支撑_借用检查器"),
    (375, 316, 330, 78, "Rust原理_支撑_特质与单态化"),
    (720, 316, 330, 78, "Rust原理_支撑_类型推断"),
    (30, 408, 330, 78, "Rust原理_支撑_内存与Drop"),
    (375, 408, 330, 78, "Rust原理_支撑_并发SendSync"),
    (720, 408, 330, 78, "Rust原理_支撑_智能指针与内部可变"),
]
ARCH_ALWAYS_CHIP = ["Rust原理_支撑_panic与展开"]

BRAND_TITLE = "一切知识皆索引"
BRAND_SUB = "Rust"
HOME_DESC = ("Rust 核心原理设计文档库的离线交互图谱——新家族(语言运行时/编译器：所有权+借用检查编译期杜绝内存错误/数据竞争，无 GC 零成本抽象)。"
             "11 条主线、手绘原理图，全部回 rust-lang/rust 源码核实。点击项目总架构图任意模块即可下钻到对应主线。")
ARCH_SVG_NAME = "Rust原理_总架构图.svg"

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
        '<img alt="Rust 项目总架构图" src="data:image/svg+xml;base64,%s"/>'
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
  var saved=localStorage.getItem('rust-atlas-theme');
  if(saved) root.setAttribute('data-theme',saved);
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='light'?'':'light';
    if(cur) root.setAttribute('data-theme',cur); else root.removeAttribute('data-theme');
    localStorage.setItem('rust-atlas-theme',cur);
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
  <a href="https://github.com/rust-lang/rust" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://www.rust-lang.org" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjMDAwMDAwIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+UnVzdDwvdGl0bGU+PHBhdGggZD0iTTIzLjgzNDYgMTEuNzAzM2wtMS4wMDczLS42MjM2YTEzLjcyNjggMTMuNzI2OCAwIDAwLS4wMjgzLS4yOTM2bC44NjU2LS44MDY5YS4zNDgzLjM0ODMgMCAwMC0uMTE1NC0uNTc4bC0xLjEwNjYtLjQxNGE4LjQ5NTggOC40OTU4IDAgMDAtLjA4Ny0uMjg1NmwuNjkwNC0uOTU4N2EuMzQ2Mi4zNDYyIDAgMDAtLjIyNTctLjU0NDZsLTEuMTY2My0uMTg5NGE5LjM1NzQgOS4zNTc0IDAgMDAtLjE0MDctLjI2MjJsLjQ5LTEuMDc2MWEuMzQzNy4zNDM3IDAgMDAtLjAyNzQtLjMzNjEuMzQ4Ni4zNDg2IDAgMDAtLjMwMDYtLjE1NGwtMS4xODQ1LjA0MTZhNi43NDQ0IDYuNzQ0NCAwIDAwLS4xODczLS4yMjY4bC4yNzIzLTEuMTUzYS4zNDcyLjM0NzIgMCAwMC0uNDE3LS40MTcybC0xLjE1MzIuMjcyNGExNC4wMTgzIDE0LjAxODMgMCAwMC0uMjI3OC0uMTg3M2wuMDQxNS0xLjE4NDVhLjM0NDIuMzQ0MiAwIDAwLS40OS0uMzI4bC0xLjA3Ni40OTFjLS4wODcyLS4wNDc2LS4xNzQyLS4wOTUyLS4yNjIzLS4xNDA3bC0uMTkwMy0xLjE2NzNBLjM0ODMuMzQ4MyAwIDAwMTYuMjU2Ljk1NWwtLjk1OTcuNjkwNWE4LjQ4NjcgOC40ODY3IDAgMDAtLjI4NTUtLjA4NmwtLjQxNC0xLjEwNjZhLjM0ODMuMzQ4MyAwIDAwLS41NzgxLS4xMTU0bC0uODA2OS44NjY2YTkuMjkzNiA5LjI5MzYgMCAwMC0uMjkzNi0uMDI4NEwxMi4yOTQ2LjE2ODNhLjM0NjIuMzQ2MiAwIDAwLS41ODkyIDBsLS42MjM2IDEuMDA3M2ExMy43MzgzIDEzLjczODMgMCAwMC0uMjkzNi4wMjg0TDkuOTgwMy4zMzc0YS4zNDYyLjM0NjIgMCAwMC0uNTc4LjExNTRsLS40MTQxIDEuMTA2NWMtLjA5NjIuMDI3NC0uMTkwMy4wNTY3LS4yODU1LjA4Nkw3Ljc0NC45NTVhLjM0ODMuMzQ4MyAwIDAwLS41NDQ3LjIyNThMNy4wMDkgMi4zNDhhOS4zNTc0IDkuMzU3NCAwIDAwLS4yNjIyLjE0MDdsLTEuMDc2Mi0uNDkxYS4zNDYyLjM0NjIgMCAwMC0uNDkuMzI4bC4wNDE2IDEuMTg0NWE3Ljk4MjYgNy45ODI2IDAgMDAtLjIyNzguMTg3M0wzLjg0MTMgMy40MjVhLjM0NzIuMzQ3MiAwIDAwLS40MTcxLjQxNzFsLjI3MTMgMS4xNTMxYy0uMDYyOC4wNzUtLjEyNTUuMTUwOS0uMTg2My4yMjY4bC0xLjE4NDUtLjA0MTVhLjM0NjIuMzQ2MiAwIDAwLS4zMjguNDlsLjQ5MSAxLjA3NjFhOS4xNjcgOS4xNjcgMCAwMC0uMTQwNy4yNjIybC0xLjE2NjIuMTg5NGEuMzQ4My4zNDgzIDAgMDAtLjIyNTguNTQ0NmwuNjkwNC45NTg3YTEzLjMwMyAxMy4zMDMgMCAwMC0uMDg3LjI4NTVsLTEuMTA2NS40MTRhLjM0ODMuMzQ4MyAwIDAwLS4xMTU1LjU3ODFsLjg2NTYuODA3YTkuMjkzNiA5LjI5MzYgMCAwMC0uMDI4My4yOTM1bC0xLjAwNzMuNjIzNmEuMzQ0Mi4zNDQyIDAgMDAwIC41ODkybDEuMDA3My42MjM2Yy4wMDguMDk4Mi4wMTgyLjE5NjQuMDI4My4yOTM2bC0uODY1Ni44MDc5YS4zNDYyLjM0NjIgMCAwMC4xMTU1LjU3OGwxLjEwNjUuNDE0MWMuMDI3My4wOTYyLjA1NjcuMTkxNC4wODcuMjg1NWwtLjY5MDQuOTU4N2EuMzQ1Mi4zNDUyIDAgMDAuMjI2OC41NDQ3bDEuMTY2Mi4xODkzYy4wNDU2LjA4OC4wOTIyLjE3NTEuMTQwOC4yNjIybC0uNDkxIDEuMDc2MmEuMzQ2Mi4zNDYyIDAgMDAuMzI4LjQ5bDEuMTgzNC0uMDQxNWMuMDYxOC4wNzY5LjEyMzUuMTUyOC4xODczLjIyNzdsLS4yNzEzIDEuMTU0MWEuMzQ2Mi4zNDYyIDAgMDAuNDE3MS40MTYxbDEuMTUzLS4yNzEzYy4wNzUuMDYzOC4xNTEuMTI1NS4yMjc5LjE4NjNsLS4wNDE1IDEuMTg0NWEuMzQ0Mi4zNDQyIDAgMDAuNDkuMzI3bDEuMDc2MS0uNDljLjA4Ny4wNDg2LjE3NDEuMDk1MS4yNjIyLjE0MDdsLjE5MDMgMS4xNjYyYS4zNDgzLjM0ODMgMCAwMC41NDQ3LjIyNjhsLjk1ODctLjY5MDRhOS4yOTkgOS4yOTkgMCAwMC4yODU1LjA4N2wuNDE0IDEuMTA2NmEuMzQ1Mi4zNDUyIDAgMDAuNTc4MS4xMTU0bC44MDc5LS44NjU2Yy4wOTcyLjAxMTEuMTk1NC4wMjAzLjI5MzYuMDI5NGwuNjIzNiAxLjAwNzNhLjM0NzIuMzQ3MiAwIDAwLjU4OTIgMGwuNjIzNi0xLjAwNzNjLjA5ODItLjAwOTEuMTk2NC0uMDE4My4yOTM2LS4wMjk0bC44MDY5Ljg2NTZhLjM0ODMuMzQ4MyAwIDAwLjU3OC0uMTE1NGwuNDE0MS0xLjEwNjZhOC40NjI2IDguNDYyNiAwIDAwLjI4NTUtLjA4N2wuOTU4Ny42OTA0YS4zNDUyLjM0NTIgMCAwMC41NDQ3LS4yMjY4bC4xOTAzLTEuMTY2MmMuMDg4LS4wNDU2LjE3NTEtLjA5MzEuMjYyMi0uMTQwN2wxLjA3NjIuNDlhLjM0NzIuMzQ3MiAwIDAwLjQ5LS4zMjdsLS4wNDE1LTEuMTg0NWE2LjcyNjcgNi43MjY3IDAgMDAuMjI2Ny0uMTg2M2wxLjE1MzEuMjcxM2EuMzQ3Mi4zNDcyIDAgMDAuNDE3MS0uNDE2bC0uMjcxMy0xLjE1NDJjLjA2MjgtLjA3NDkuMTI1NS0uMTUwOC4xODYzLS4yMjc4bDEuMTg0NS4wNDE1YS4zNDQyLjM0NDIgMCAwMC4zMjgtLjQ5bC0uNDktMS4wNzZjLjA0NzUtLjA4NzIuMDk1MS0uMTc0Mi4xNDA3LS4yNjIzbDEuMTY2Mi0uMTg5M2EuMzQ4My4zNDgzIDAgMDAuMjI1OC0uNTQ0N2wtLjY5MDQtLjk1ODcuMDg3LS4yODU1IDEuMTA2Ni0uNDE0YS4zNDYyLjM0NjIgMCAwMC4xMTU0LS41NzgxbC0uODY1Ni0uODA3OWMuMDEwMS0uMDk3Mi4wMjAyLS4xOTU0LjAyODMtLjI5MzZsMS4wMDczLS42MjM2YS4zNDQyLjM0NDIgMCAwMDAtLjU4OTJ6bS02Ljc0MTMgOC4zNTUxYS43MTM4LjcxMzggMCAwMS4yOTg2LTEuMzk2LjcxNC43MTQgMCAxMS0uMjk5NyAxLjM5NnptLS4zNDIyLTIuMzE0MmEuNjQ5LjY0OSAwIDAwLS43NzE1LjVsLS4zNTczIDEuNjY4NWMtMS4xMDM1LjUwMS0yLjMyODUuNzc5NS0zLjYxOTMuNzc5NWE4LjczNjggOC43MzY4IDAgMDEtMy42OTUxLS44MTRsLS4zNTc0LTEuNjY4NGEuNjQ4LjY0OCAwIDAwLS43NzE0LS40OTlsLTEuNDczLjMxNThhOC43MjE2IDguNzIxNiAwIDAxLS43NjEzLS44OThoNy4xNjc2Yy4wODEgMCAuMTM1Ni0uMDE0MS4xMzU2LS4wODh2LTIuNTM2YzAtLjA3NC0uMDUzNi0uMDg4MS0uMTM1Ni0uMDg4MWgtMi4wOTY2di0xLjYwNzdoMi4yNjc3Yy4yMDY1IDAgMS4xMDY1LjA1ODcgMS4zOTQgMS4yMDg4LjA5MDEuMzUzMy4yODc1IDEuNTA0NC40MjMyIDEuODcyOS4xMzQ2LjQxMy42ODMzIDEuMjM4MSAxLjI2ODUgMS4yMzgxaDMuNTcxNmEuNzQ5Mi43NDkyIDAgMDAuMTI5Ni0uMDEzMSA4Ljc4NzQgOC43ODc0IDAgMDEtLjgxMTkuOTUyNnpNNi44MzY5IDIwLjAyNGEuNzE0LjcxNCAwIDExLS4yOTk3LTEuMzk2LjcxNC43MTQgMCAwMS4yOTk3IDEuMzk2ek00LjExNzcgOC45OTcyYS43MTM3LjcxMzcgMCAxMS0xLjMwNC41NzkxLjcxMzcuNzEzNyAwIDAxMS4zMDQtLjU3OXptLS44MzUyIDEuOTgxM2wxLjUzNDctLjY4MjRhLjY1LjY1IDAgMDAuMzMtLjg1ODVsLS4zMTU4LS43MTQ3aDEuMjQzMnY1LjYwMjVIMy41NjY5YTguNzc1MyA4Ljc3NTMgMCAwMS0uMjgzNC0zLjM0OHptNi43MzQzLS41NDM3VjguNzgzNmgyLjk2MDFjLjE1MyAwIDEuMDc5Mi4xNzcyIDEuMDc5Mi44Njk3IDAgLjU3NS0uNzEwNy43ODE1LTEuMjk0OC43ODE1em0xMC43NTc0IDEuNDg2MmMwIC4yMTg3LS4wMDguNDM2My0uMDI0My42NTFoLS45Yy0uMDkgMC0uMTI2NS4wNTg2LS4xMjY1LjE0Nzd2LjQxM2MwIC45NzMtLjU0ODcgMS4xODQ2LTEuMDI5NiAxLjIzODItLjQ1NzYuMDUxNy0uOTY0OC0uMTkxMy0xLjAyNzUtLjQ3MTctLjI3MDQtMS41MTg2LS43MTk4LTEuODQzNi0xLjQzMDUtMi40MDM0Ljg4MTctLjU1OTkgMS43OTktMS4zODYgMS43OTktMi40OTE1IDAtMS4xOTM2LS44MTktMS45NDU4LTEuMzc2OS0yLjMxNTMtLjc4MjUtLjUxNjMtMS42NDkxLS42MTk1LTEuODgzLS42MTk1SDUuNDY4MmE4Ljc2NTEgOC43NjUxIDAgMDE0LjkwNy0yLjc2OTlsMS4wOTc0IDEuMTUxYS42NDguNjQ4IDAgMDAuOTE4Mi4wMjEzbDEuMjI3LTEuMTc0M2E4Ljc3NTMgOC43NzUzIDAgMDE2LjAwNDQgNC4yNzYybC0uODQwMyAxLjg5ODJhLjY1Mi42NTIgMCAwMC4zMy44NTg1bDEuNjE3OC43MTg4Yy4wMjgzLjI4NzUuMDQyNS41NzcuMDQyNS44NzE3em0tOS4zMDA2LTkuNTk5M2EuNzEyOC43MTI4IDAgMTEuOTg0IDEuMDMxNi43MTM3LjcxMzcgMCAwMS0uOTg0LTEuMDMxNnptOC4zMzg5IDYuNzFhLjcxMDcuNzEwNyAwIDAxLjkzOTUtLjM2MjUuNzEzNy43MTM3IDAgMTEtLjk0MDUuMzYzNXoiLz48L3N2Zz4=" width="18" height="18" alt="官网" style="display:block"/></a><button id="themeBtn" title="切换主题" aria-label="切换主题" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;place-items:center;font-size:16px;flex:none">☾</button>
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
