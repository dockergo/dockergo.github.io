#!/usr/bin/env python3
"""pytorch-design 交互式核心原理图谱生成器（自包含 · 离线 · 双主题）。

单向流水线：design/(md + 手绘 svg) → gen.py → index.html
- design/ 是内容真源；本脚本只编译不创作。
- 绝不手改 index.html；改渲染/导航改本脚本重跑。
- 零运行时依赖：所有 SVG 以 base64 内联，无网络、无 JS 库。
- 自包含：仅读同级 design/，默认写同级 index.html。

用法：
  cd pytorch-design && python3 gen.py
  python3 gen.py --design-dir <dir> --out <path>
"""
import os
import re
import html
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 PyTorch 交互式核心原理图谱（离线自包含 HTML）")
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
    os.environ.get("PYTORCH_DESIGN_DIR"),
    os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("PYTORCH_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ===================================================================== #
# 一、主线注册表 —— 唯一需随项目调整的数据块
#     新家族（ML 框架 · 张量计算 + 自动微分）：元模式 = 接口 × 能力域 × 时机。
#     全景 + 3 接口主线 + 8 支撑能力域。
#     每条主线声明：md 文件名、分组、图标、短标题、一句话副标。
# ===================================================================== #
MAINLINES = [
    ("PyTorch原理_全景主线框架", "pano", "◇", "全景主线框架",
     "新家族 ML 框架：双维模型 · 分层栈总架构 · define-by-run 动态图 · 依赖矩阵 · 三条贯穿声明"),

    ("PyTorch原理_接口_张量编程", "iface", "▦", "张量编程",
     "Tensor + 算子 API：元信息+共享存储 · 视图零拷贝 · 广播 · eager 即时执行"),
    ("PyTorch原理_接口_自动微分", "iface", "∂", "自动微分",
     "requires_grad → 前向建反向图 → backward → .grad · no_grad/detach"),
    ("PyTorch原理_接口_建模与训练", "iface", "◷", "建模与训练",
     "nn.Module 参数树 · optimizer/DataLoader · 五步训练循环"),

    ("PyTorch原理_支撑_张量与存储", "support", "▤", "张量与存储",
     "TensorImpl 元信息 + 共享 Storage · key_set · 引用计数"),
    ("PyTorch原理_支撑_Dispatcher分发", "support", "⚙", "Dispatcher 分发",
     "灵魂：按 DispatchKeySet 分层选 kernel · Autograd/Autocast/Backend · redispatch"),
    ("PyTorch原理_支撑_ATen算子库", "support", "✲", "ATen 算子库",
     "~2000 算子 schema · structured kernel · 复合算子降解"),
    ("PyTorch原理_支撑_自动微分引擎", "support", "∇", "自动微分引擎",
     "灵魂：反向图 Node/Edge · Engine 拓扑并行遍历 · AccumulateGrad"),
    ("PyTorch原理_支撑_设备后端与内存", "support", "▧", "设备后端与内存",
     "CPU/CUDA kernel · CUDACachingAllocator 显存池 · stream 异步"),
    ("PyTorch原理_支撑_编译栈", "support", "⚡", "编译栈 torch.compile",
     "Dynamo 抓图 → AOTAutograd → Inductor 融合 codegen · guards/重编译"),
    ("PyTorch原理_支撑_分布式训练", "support", "⬡", "分布式训练",
     "DDP 数据并行 all-reduce · FSDP 分片省显存 · ProcessGroup/collective"),
    ("PyTorch原理_支撑_数据加载", "support", "◐", "数据加载",
     "Dataset/Sampler · 多 worker 进程预取 · collate/pin_memory 喂满 GPU"),
]

CAT_ORDER = [
    ("pano", "全景框架 · 先读这一篇"),
    ("iface", "接口主线 · 用户如何编程（张量 / 自动微分 / 建模训练）"),
    ("support", "支撑主线 · 引擎内部（8 条能力域）"),
]

BRAND_TITLE = "一切知识皆索引"
BRAND_SUB = "PyTorch 核心原理 · 交互式图谱"
HOME_DESC = ("PyTorch 核心原理设计文档库的离线交互图谱——新家族（深度学习框架 · 张量计算 + 自动微分）。"
             "12 条主线、20 张手绘原理图，全部回官方源码核实。点任意主线进入逐图走查。")
ARCH_SVG_NAME = "PyTorch原理_全景_02总架构.svg"

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


def build_cards():
    parts = []
    for cat, label in CAT_ORDER:
        group = [m for m in MAINLINES if m[1] == cat]
        if not group:
            continue
        parts.append('<div class="cat-sec">%s</div>' % esc(label))
        cells = []
        for name, _cat, ico, ctitle, sub in group:
            n = len(DOCS[name]["walk"])
            cells.append(
                '<button class="tcard" data-mid="{mid}">'
                '<span class="tcard-ico">{ico}</span>'
                '<span class="tcard-body">'
                '<span class="tcard-title">{title}</span>'
                '<span class="tcard-desc">{sub}</span>'
                '<span class="tcard-meta">{n} 张原理图 →</span>'
                '</span></button>'.format(
                    mid=esc(name), ico=esc(ico), title=esc(ctitle),
                    sub=esc(sub), n=n))
        parts.append('<div class="tcards">' + "\n".join(cells) + "</div>")
    return "\n".join(parts)


def build_tree():
    parts = ['<div class="tree">']
    for cat, label in CAT_ORDER:
        group = [m for m in MAINLINES if m[1] == cat]
        if not group:
            continue
        parts.append('<div class="tree-cat">%s</div>' % esc(label))
        for name, _c, ico, ctitle, _sub in group:
            leaves = "".join(
                '<button class="tree-leaf" data-mid="{mid}" data-idx="{i}">{ico2} {sec}</button>'.format(
                    mid=esc(name), i=i, ico2="▸", sec=esc(sec))
                for i, (sec, _a, _s) in enumerate(DOCS[name]["walk"]))
            parts.append(
                '<div class="tree-node"><button class="tree-head" data-mid="{mid}">'
                '<span>{ico} {title}</span><span class="tree-n">{n}</span></button>'
                '<div class="tree-leaves">{leaves}</div></div>'.format(
                    mid=esc(name), ico=esc(ico), title=esc(ctitle),
                    n=len(DOCS[name]["walk"]), leaves=leaves))
    parts.append("</div>")
    return "\n".join(parts)


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
.logo{display:flex;align-items:center;gap:9px;cursor:pointer;font-weight:700;font-size:15px}
.logo{text-decoration:none;color:inherit}
.logo:hover .homeico{color:var(--c-brand)}
.homeico{display:inline-flex;color:var(--c-ink2);transition:color .15s}
.logo .dot{width:11px;height:11px;border-radius:3px;background:linear-gradient(135deg,var(--c-brand),var(--c-amber))}
.logo .sub{font-weight:500;color:var(--c-ink2);font-size:12px}
.spacer{flex:1}
.hbtn{border:1px solid var(--c-border);background:var(--c-card);color:var(--c-ink2);
  border-radius:9px;padding:6px 12px;cursor:pointer;font-size:12.5px;transition:.15s}
.hbtn:hover{color:var(--c-ink);border-color:var(--c-edge)}
.wrap{max-width:1180px;margin:0 auto;padding:30px 22px 80px}
.hero{padding:26px 0 10px}
.hero h1{font-size:30px;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(120deg,var(--c-ink),var(--c-ink2));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{margin-top:10px;color:var(--c-ink2);max-width:760px;font-size:13.5px}
.nav-seg{display:inline-flex;margin:22px 0 6px;background:var(--c-card2);border:1px solid var(--c-border);border-radius:11px;padding:3px}
.nav-seg button{border:0;background:transparent;color:var(--c-ink2);padding:7px 15px;border-radius:8px;cursor:pointer;font-size:12.5px;transition:.15s}
.nav-seg button.on{background:var(--c-card);color:var(--c-ink);box-shadow:0 1px 3px var(--c-shadow)}
.nav-mode{display:none;margin-top:16px}
.nav-mode.on{display:block}
.cat-sec{font-size:12px;font-weight:700;color:var(--c-ink3);text-transform:uppercase;letter-spacing:.6px;margin:26px 0 12px}
.tcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:13px}
.tcard{display:flex;gap:12px;text-align:left;cursor:pointer;padding:15px 16px;
  background:var(--c-card);border:1px solid var(--c-border);border-radius:14px;transition:.16s;color:inherit;align-items:flex-start}
.tcard:hover{border-color:var(--c-brand);transform:translateY(-2px);box-shadow:0 8px 24px var(--c-shadow)}
.tcard-ico{font-size:20px;line-height:1.2;width:26px;flex:none;text-align:center}
.tcard-body{display:flex;flex-direction:column;gap:4px;min-width:0}
.tcard-title{font-weight:700;font-size:14.5px}
.tcard-desc{color:var(--c-ink2);font-size:11.8px;line-height:1.5}
.tcard-meta{color:var(--c-brand);font-size:11px;font-weight:600;margin-top:2px}
.arch-wrap{position:relative;background:var(--c-card);border:1px solid var(--c-border);border-radius:16px;padding:14px;overflow:hidden}
.arch-wrap img{width:100%;display:block;border-radius:8px}
html:not([data-theme="light"]) .arch-wrap img{filter:invert(.92) hue-rotate(180deg) saturate(.85)}
.arch-chips{display:flex;flex-wrap:wrap;gap:9px;margin-top:14px}
.arch-chip{border:1px solid var(--c-border);background:var(--c-card2);border-radius:9px;padding:7px 12px;cursor:pointer;font-size:12px;transition:.15s}
.arch-chip:hover{border-color:var(--c-brand);color:var(--c-brand)}
.tree-cat{font-size:12px;font-weight:700;color:var(--c-ink3);text-transform:uppercase;letter-spacing:.6px;margin:20px 0 8px}
.tree-node{margin-bottom:6px}
.tree-head{width:100%;display:flex;justify-content:space-between;align-items:center;cursor:pointer;
  background:var(--c-card);border:1px solid var(--c-border);border-radius:10px;padding:11px 14px;color:inherit;font-size:13.5px;font-weight:600}
.tree-head:hover{border-color:var(--c-edge)}
.tree-n{color:var(--c-ink3);font-size:11px;font-weight:500}
.tree-leaves{display:none;padding:6px 0 6px 14px}
.tree-node.open .tree-leaves{display:block}
.tree-leaf{display:block;width:100%;text-align:left;cursor:pointer;background:transparent;border:0;
  color:var(--c-ink2);padding:6px 10px;border-radius:7px;font-size:12.5px}
.tree-leaf:hover{background:var(--c-card2);color:var(--c-ink)}
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
  var saved=localStorage.getItem('pytorch-atlas-theme');
  if(saved) root.setAttribute('data-theme',saved);
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='light'?'':'light';
    if(cur) root.setAttribute('data-theme',cur); else root.removeAttribute('data-theme');
    localStorage.setItem('pytorch-atlas-theme',cur);
    var b=document.getElementById('themeBtn'); if(b) b.textContent=cur==='light'?'☀ 浅色':'☾ 深色';
  }
  var tb=document.getElementById('themeBtn');
  if(tb){tb.onclick=toggleTheme; tb.textContent=root.getAttribute('data-theme')==='light'?'☀ 浅色':'☾ 深色';}

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
    var c=e.target.closest('.tcard'); if(c){openMain(c.dataset.mid,0);return;}
    var ac=e.target.closest('.arch-chip'); if(ac){openMain(ac.dataset.mid,0);return;}
    var wt=e.target.closest('.walk-tab'); if(wt){selFig(wt.dataset.mid,+wt.dataset.idx);return;}
    var tl=e.target.closest('.tree-leaf'); if(tl){openMain(tl.dataset.mid,+tl.dataset.idx);return;}
    var th=e.target.closest('.tree-head'); if(th){th.parentElement.classList.toggle('open');return;}
    // logo now portal link
    var bk=e.target.closest('#back'); if(bk){showHome();return;}
  });
  document.querySelectorAll('.nav-seg button').forEach(function(b){
    b.onclick=function(){
      document.querySelectorAll('.nav-seg button').forEach(function(x){x.classList.remove('on')});
      b.classList.add('on');
      document.querySelectorAll('.nav-mode').forEach(function(m){m.classList.toggle('on',m.dataset.mode===b.dataset.mode)});
    };
  });
  showHome();
  function done(){var lo=document.getElementById('lo');if(lo){lo.classList.add('hide');setTimeout(function(){if(lo&&lo.parentNode)lo.parentNode.removeChild(lo);},500);}}
  requestAnimationFrame(function(){requestAnimationFrame(function(){setTimeout(done,120);});});
  setTimeout(done,4000);
})();
"""


def build_html():
    if _ARCH_SVG:
        chips = "".join(
            '<button class="arch-chip" data-mid="{mid}">{ico} {title}</button>'.format(
                mid=esc(n), ico=esc(ico), title=esc(t))
            for (n, _c, ico, t, _s) in MAINLINES)
        arch_section = (
            '<div class="nav-mode" data-mode="arch">'
            '<div class="arch-wrap"><img alt="PyTorch 总架构图" '
            'src="data:image/svg+xml;base64,%s"/></div>'
            '<div class="arch-chips">%s</div></div>' % (_ARCH_SVG, chips))
    else:
        arch_section = '<div class="nav-mode" data-mode="arch"><p>（缺总架构图）</p></div>'

    total_svg = len(_on_disk)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{brand} · PyTorch 核心原理图谱</title>
<style>{css}</style>
</head>
<body>
<div id="lo" role="status" aria-live="polite">
  <div class="lo-logo"></div>
  <div class="lo-t">{brand}</div>
  <div class="lo-s">{sub} · 正在装载 {n} 张原理图</div>
  <div class="lo-bar"><i></i></div>
  <div class="lo-s" style="font-size:11px;opacity:.7">短暂空白属正常装载，非内容缺失</div>
</div>
<header>
  <a class="logo" id="logo" href="../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span><span>{brand}</span><span class="sub">{sub}</span></a>
  <div class="spacer"></div>
  <button class="hbtn" id="back">← 返回首页</button>
  <button class="hbtn" id="themeBtn">☾ 深色</button>
</header>
<div class="wrap">
  <div id="home">
    <div class="hero">
      <h1>{brand}</h1>
      <p>{home_desc}</p>
    </div>
    <div class="nav-seg">
      <button data-mode="cards" class="on">主题卡片</button>
      <button data-mode="arch">架构导航</button>
      <button data-mode="tree">目录树</button>
    </div>
    <div class="nav-mode on" data-mode="cards">{cards}</div>
    {arch}
    <div class="nav-mode" data-mode="tree">{tree}</div>
  </div>
  <div id="panes" style="display:none">
    <button class="hbtn back on" id="back2" onclick="document.getElementById('back').click()">← 返回全部主线</button>
    {panes}
  </div>
</div>
<script>{js}</script>
</body>
</html>""".format(
        brand=esc(BRAND_TITLE), sub=esc(BRAND_SUB), home_desc=esc(HOME_DESC), n=total_svg,
        css=CSS, cards=build_cards(), arch=arch_section, tree=build_tree(),
        panes=build_panes(), js=APP_JS)


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
