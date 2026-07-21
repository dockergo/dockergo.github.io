#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""go-design 项目级 gen.py —— 把 design/ 编译成自包含双主题 index.html。

铁律（勿违背）：
· 自包含：仅标准库；SVG/文档全部 base64 内联进单个 HTML，零网络/服务器依赖，双击即用。
· 只读同级 design/，产物恒名 index.html（可随时重生成，绝不手改）。
· design/ 是内容真源：图清单从每篇 .md 的 `](Go原理_*.svg)` 引用**按文档顺序解析**得来，
  不硬编码——新增/删图改 md 即自动同步，从根上消除「漏登记→静默不显示」陷阱。
· 深色默认 + 浅色可切；手绘浅色 SVG 以 base64 <img> 内联，深色用 CSS filter 反相（穿不进独立文档）。
· 落盘校验：写完打印字节数与主线清单，确认真的落盘（防"幽灵生成"）。
· 导航返回：头部「← 返回导航主页」按钮 href=../index.html，链回门户（supports/index.html）。
"""
import os
import re
import sys
import html
import base64
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(description="生成 Go 语言交互式核心原理图谱（离线自包含）")
_ap.add_argument("--design-dir", default=None, help="design 素材目录（默认：<here>/design）")
_ap.add_argument("--out", default=None, help="输出 HTML 路径（默认：<here>/index.html）")
_args, _ = _ap.parse_known_args()

DESIGN_DIR = _args.design_dir or os.environ.get("GO_DESIGN_DIR") or os.path.join(HERE, "design")
OUT = _args.out or os.environ.get("GO_DESIGN_OUT") or os.path.join(HERE, "index.html")

# ---- 主线定义：三组家族 × 各主线文档 --------------------------------------
# (tid, 文档文件名, tab 标签, 家族分类)
MAINLINES = [
    # 全景
    ("panorama", "Go原理_全景主线框架.md", "全景 · 主线框架", "全景"),
    # 运行期 · runtime
    ("gmp",      "Go原理_GMP调度.md",         "GMP 调度",        "运行期"),
    ("lifecycle","Go原理_goroutine生命周期.md","goroutine 生命周期","运行期"),
    ("stack",    "Go原理_栈管理.md",           "栈管理",          "运行期"),
    ("alloc",    "Go原理_内存分配器.md",       "内存分配器",      "运行期"),
    ("gc",       "Go原理_垃圾回收.md",         "垃圾回收",        "运行期"),
    ("concur",   "Go原理_并发原语.md",         "并发原语",        "运行期"),
    ("defer",    "Go原理_defer_panic_recover.md","defer/panic/recover","运行期"),
    ("iface",    "Go原理_接口与反射.md",       "接口与反射",      "运行期"),
    # 编译期 · 工具链
    ("frontend", "Go原理_编译前端.md",         "编译前端",        "编译期"),
    ("ssa",      "Go原理_SSA后端.md",          "SSA 后端",        "编译期"),
    ("escape",   "Go原理_逃逸分析与内联.md",   "逃逸分析与内联",  "编译期"),
    ("generics", "Go原理_泛型实现.md",         "泛型实现",        "编译期"),
    ("gocmd",    "Go原理_go命令与链接.md",     "go 命令与链接",   "编译期"),
]

CAT_ORDER = ["全景", "运行期", "编译期"]
CAT_DESC = {
    "全景": "双维模型 · 总架构 · 依赖矩阵 · 三条贯穿声明",
    "运行期": "GMP 调度 · 栈 · 分配器 · GC · 并发 · defer · 接口——编译进每个二进制的那套 runtime",
    "编译期": "gc 前端 · SSA 后端 · 逃逸内联 · 泛型 · go 命令与链接——把源程序静态编译成单一二进制",
}

# ---- 总架构导航：架构图热区 ------------------------------------------------
# 唯一导航主页 = 总架构 SVG（design/Go原理_全景_02总架构.svg）＋透明热区叠加。
# 热区从 SVG 派生（唯一真源）：遍历带 data-tid 的 <rect>，累加 <g transform=translate>
# 偏移得根坐标；除数用 viewBox 实际宽高。消除「SVG 与硬编码坐标双真源」漂移。
# stack/defer/iface/generics 是横切语言特性、图上无对应方块，走 chip 兜底不画框。
ARCH_SVG = "Go原理_全景_02总架构.svg"

import re as _re_hot
import xml.etree.ElementTree as _ET_hot


def _parse_arch_hotspots(svg_text):
    vb = _re_hot.search(
        r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg_text)
    vbw, vbh = float(vb.group(1)), float(vb.group(2))
    root = _ET_hot.fromstring(svg_text)
    hots = []

    def walk(el, dx, dy):
        m = _re_hot.search(
            r'translate\(\s*([-\d.]+)(?:[,\s]+([-\d.]+))?',
            el.get("transform") or "")
        if m:
            dx += float(m.group(1))
            if m.group(2):
                dy += float(m.group(2))
        if el.tag.rsplit("}", 1)[-1] == "rect" and el.get("data-tid"):
            hots.append((
                float(el.get("x", 0)) + dx, float(el.get("y", 0)) + dy,
                float(el.get("width", 0)), float(el.get("height", 0)),
                el.get("data-tid"), el.get("data-lab") or ""))
        for c in el:
            walk(c, dx, dy)

    walk(root, 0.0, 0.0)
    return hots, vbw, vbh


with open(os.path.join(DESIGN_DIR, ARCH_SVG), encoding="utf-8") as _f_arch:
    _ARCH_SVG_TEXT = _f_arch.read()
_ARCH_HOTSPOTS_FULL, ARCH_VIEW_W, ARCH_VIEW_H = _parse_arch_hotspots(
    _ARCH_SVG_TEXT)
# 消费端沿用 5 元 (x, y, w, h, tid)；标签由 MAINLINES 提供
ARCH_HOTSPOTS = [(x, y, w, h, tid)
                 for (x, y, w, h, tid, _lab) in _ARCH_HOTSPOTS_FULL]


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _b64_svg(fname):
    """读 design/<fname> 编成 base64 data-uri；缺文件返回 ""（不炸全局）。"""
    path = os.path.join(DESIGN_DIR, fname)
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# ---- 从 md 解析：图引用（按文档顺序）+ prose 五层深化 --------------------
_IMG_RE = re.compile(r"!\[([^\]]*)\]\((Go原理_[^)]+\.svg)\)")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)


def parse_doc(fname):
    """返回 dict：title, figs=[(alt, svgfile)...按序], tips={定位/总纲/调优/误区/深化}。"""
    md = _read(os.path.join(DESIGN_DIR, fname))
    if not md:
        return {"title": fname, "figs": [], "tips": {}}
    m = _H1_RE.search(md)
    title = m.group(1).strip() if m else fname
    # 去掉 SVG <text> 里可能干扰的行内代码，仅取图引用
    figs = [(alt.strip(), svg.strip()) for alt, svg in _IMG_RE.findall(md)]
    tips = _parse_tips(md)
    return {"title": title, "figs": figs, "tips": tips}


def _parse_tips(md):
    """抽五层深化：定位、一句话总纲、调优要点、常见误区、深化清单。"""
    tips = {}
    # 定位：> **定位**：...
    m = re.search(r">\s*\*\*定位\*\*[：:]\s*(.+?)(?:\n\n|\n>|\Z)", md, re.S)
    if m:
        tips["定位"] = _clean(m.group(1))
    # 一句话总纲：## 一句话总纲 后到下一个标题
    m = re.search(r"##\s*一句话总纲\s*\n+(.+?)(?:\n##|\Z)", md, re.S)
    if m:
        tips["总纲"] = _clean(m.group(1))
    # 调优要点
    m = re.search(r"##\s*调优要点[^\n]*\n+(.+?)(?:\n##|\Z)", md, re.S)
    if m:
        tips["调优"] = _clean(m.group(1), keep_list=True)
    # 常见误区
    m = re.search(r"##\s*常见误区[^\n]*\n+(.+?)(?:\n##|\Z)", md, re.S)
    if m:
        tips["误区"] = _clean(m.group(1), keep_list=True)
    return tips


def _clean(s, keep_list=False):
    s = s.strip()
    # 去 markdown 强调符
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    if not keep_list:
        s = re.sub(r"\s*\n\s*", " ", s)
    return s


# ---- HTML 片段构建 --------------------------------------------------------
def esc(s):
    return html.escape(s, quote=True)


def build_panel(tid, doc):
    """一条主线的内容面板：doris 式垂直 tab —— 左 nav 列（每图一节 + 末尾要点），
    右内容区，点 tab 只显当前一节。避免大端平铺、一屏聚焦一个要点。"""
    navs = []      # 左侧垂直 tab 按钮
    secs = []      # 右侧内容节（同序，只有 active 显示）
    idx = 0

    for (alt, svg) in doc["figs"]:
        b64 = _b64_svg(svg)
        cap = esc(alt or svg)
        active = " active" if idx == 0 else ""
        navs.append(
            f'<button class="vt-nav{active}" data-sec="{tid}-{idx}">'
            f'<span class="vt-n">{idx+1}</span><span class="vt-t">{cap}</span></button>'
        )
        if b64:
            body = (f'<figure class="fig"><img class="fig-img" loading="lazy" alt="{cap}" '
                    f'src="data:image/svg+xml;base64,{b64}"/>'
                    f'<figcaption>{cap}</figcaption></figure>')
        else:
            body = f'<div class="fig missing">缺图：{esc(svg)}</div>'
        secs.append(f'<section class="vt-sec{active}" id="{tid}-{idx}">{body}</section>')
        idx += 1

    # 要点小节（并成最后一个垂直 tab）
    tips = doc["tips"]
    tip_parts = []
    if tips.get("定位"):
        tip_parts.append(f'<div class="tip"><h4>定位</h4><p>{esc(tips["定位"])}</p></div>')
    if tips.get("总纲"):
        tip_parts.append(f'<div class="tip tip-key"><h4>一句话总纲</h4><p>{esc(tips["总纲"])}</p></div>')
    if tips.get("调优"):
        tip_parts.append(f'<div class="tip"><h4>调优要点</h4>{_list_html(tips["调优"])}</div>')
    if tips.get("误区"):
        tip_parts.append(f'<div class="tip"><h4>常见误区与工程要点</h4>{_list_html(tips["误区"])}</div>')
    if tip_parts:
        active = " active" if idx == 0 else ""
        navs.append(
            f'<button class="vt-nav{active}" data-sec="{tid}-{idx}">'
            f'<span class="vt-n">·</span><span class="vt-t">要点 · 定位与调优</span></button>'
        )
        secs.append(
            f'<section class="vt-sec{active}" id="{tid}-{idx}">'
            f'<div class="tips">{"".join(tip_parts)}</div></section>'
        )
        idx += 1

    if not navs:  # 空主线兜底
        secs = ['<section class="vt-sec active"><div class="fig missing">（本主线暂无内容）</div></section>']
        navs = ['<button class="vt-nav active" data-sec="none"><span class="vt-n">·</span><span class="vt-t">概览</span></button>']

    return (
        f'<section class="panel" data-tid="{tid}">'
        f'<div class="panel-head"><h2>{esc(doc["title"])}</h2>'
        f'<span class="fig-count">{len(doc["figs"])} 图</span></div>'
        f'<div class="vt-wrap"><nav class="vt-navcol">{"".join(navs)}</nav>'
        f'<div class="vt-stage">{"".join(secs)}</div></div></section>'
    )


def _list_html(raw):
    """把 markdown 列表/段落转成 <ul>/<p>。"""
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    items = []
    paras = []
    for ln in lines:
        m = re.match(r"^[-*]\s+(.+)$", ln)
        if m:
            items.append(f"<li>{esc(_clean(m.group(1)))}</li>")
        else:
            paras.append(f"<p>{esc(_clean(ln))}</p>")
    out = ""
    if items:
        out += "<ul>" + "".join(items) + "</ul>"
    out += "".join(paras)
    return out


def build_arch_home(docs_by_tid):
    """唯一导航主页：总架构 SVG + 透明热区叠加 + 未上图主线的 chip 兜底。
    返回 (home_html, tabs_html)。所有主线（热区 ∪ chip）必可达。"""
    label_by_tid = {tid: label for tid, _f, label, _c in MAINLINES}
    b64 = _b64_svg(ARCH_SVG)

    # 热区：坐标 ÷ viewBox → 百分比（SVG 无 <g transform>，直接映射到图片框）
    hot_html = []
    hot_tids = set()
    for x, y, w, h, tid in ARCH_HOTSPOTS:
        hot_tids.add(tid)
        left = x / ARCH_VIEW_W * 100
        top = y / ARCH_VIEW_H * 100
        wpc = w / ARCH_VIEW_W * 100
        hpc = h / ARCH_VIEW_H * 100
        lab = label_by_tid.get(tid, tid)
        hot_html.append(
            f'<button class="arch-hot" data-tid="{tid}" '
            f'title="{esc(lab)}" aria-label="进入主线：{esc(lab)}" '
            f'style="left:{left:.3f}%;top:{top:.3f}%;'
            f'width:{wpc:.3f}%;height:{hpc:.3f}%">'
            f'<span class="arch-hot-label">{esc(lab)}</span></button>'
        )

    # chip 兜底：MAINLINES 中未在总图出现的主线（按序），保证全部可达
    chips = []
    for tid, _f, label, _c in MAINLINES:
        if tid in hot_tids:
            continue
        chips.append(f'<button class="arch-chip" data-tid="{tid}">{esc(label)}</button>')
    chips_html = "".join(chips)
    # 全部主线均有热区时,chip 兜底整块隐藏(不再残留空「其余主线」标题)
    chips_wrap = (
        '<div class="arch-chips-wrap"><span class="arch-chips-hd">其余主线</span>'
        f'<div class="arch-chips">{chips_html}</div></div>'
    ) if chips else ""

    if b64:
        img = ('<img class="arch-img" '
               'alt="Go 总架构：从 .go 源到一个 goroutine 在跑" '
               f'src="data:image/svg+xml;base64,{b64}"/>')
    else:
        img = f'<div class="fig missing">缺图：{esc(ARCH_SVG)}</div>'

    home = (
        '<section class="panel arch-panel active" data-tid="home">'
        f'<div class="arch-wrap"><div class="arch-stage">{img}'
        f'{"".join(hot_html)}</div></div>'
        f'{chips_wrap}'
        '</section>'
    )

    # 导航即架构图本身：不再平铺全主线横条。仅保留一个「← 返回架构图」，
    # 仅在下钻到某主线面板时出现（home 主页隐藏），回到唯一导航底图。
    tabs = '<button class="tab-back" data-tid="home">← 返回架构图</button>'
    return home, tabs


def build_html():
    docs_by_tid = {}
    for tid, fname, label, cat in MAINLINES:
        docs_by_tid[tid] = parse_doc(fname)

    home_html, tabs_html = build_arch_home(docs_by_tid)
    panels = home_html + "\n" + "\n".join(
        build_panel(tid, docs_by_tid[tid]) for tid, *_ in MAINLINES
    )

    total_figs = sum(len(d["figs"]) for d in docs_by_tid.values())
    total_docs = len(MAINLINES)

    first_tid = "home"

    return (
        TEMPLATE
        .replace("__TABS__", tabs_html)
        .replace("__PANELS__", panels)
        .replace("__TOTAL_DOCS__", str(total_docs))
        .replace("__TOTAL_FIGS__", str(total_figs))
        .replace("__FIRST_TID__", first_tid)
        # 热区匹配根治：渲染盒宽高比从 SVG viewBox 派生，永不与 data-tid 派生坐标漂移
        .replace("__ARCH_ASPECT__", f"{ARCH_VIEW_W:g}/{ARCH_VIEW_H:g}")
    )


# ---- 单文件 HTML 模板（双主题 · 深色默认 · 零依赖）------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Go 语言 · 交互式核心原理图谱</title>
<style>
:root{
  --c-bg:#1c1c1e; --c-bg2:#161618; --c-panel:#242426; --c-panel2:#2a2a2e;
  --c-ink:#f2f2f5; --c-ink2:#c7c7cd; --c-ink3:#8e8e96;
  --c-line:#3a3a40; --c-brand:#5aa7f0; --c-brand-ink:#7db8f5;
  --c-hover:#2f2f34; --c-shadow-sm:0 1px 3px rgba(0,0,0,.4);
  --c-accent-run:#5fd08a; --c-accent-comp:#c9a15f; --c-accent-pan:#7db8f5;
  --cv-filter:invert(.9) hue-rotate(180deg) saturate(1.05) brightness(.97);
}
:root[data-theme="light"]{
  --c-bg:#f5f5f7; --c-bg2:#ececee; --c-panel:#ffffff; --c-panel2:#f6f6f8;
  --c-ink:#1d1d1f; --c-ink2:#3a3a3c; --c-ink3:#86868b;
  --c-line:#e2e2e7; --c-brand:#0071e3; --c-brand-ink:#0a6fd0;
  --c-hover:#f0f0f3; --c-shadow-sm:0 1px 3px rgba(0,0,0,.08);
  --c-accent-run:#2f8f5e; --c-accent-comp:#a9822f; --c-accent-pan:#0a6fd0;
  --cv-filter:none;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--c-bg2);color:var(--c-ink);
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;
  transition:background-color .3s ease,color .3s ease}
a{color:var(--c-brand);text-decoration:none}
/* 首帧加载覆盖层 */
#boot{position:fixed;inset:0;background:var(--c-bg2);z-index:9999;display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:16px;
  transition:opacity .4s ease}
#boot.hide{opacity:0;pointer-events:none}
#boot .logo{width:52px;height:52px;border-radius:14px;
  background:linear-gradient(135deg,#5fd08a,#5aa7f0);display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:24px;color:#fff}
#boot .txt{color:var(--c-ink3);font-size:13px}
#boot .bar{width:180px;height:3px;border-radius:2px;background:var(--c-line);overflow:hidden}
#boot .bar i{display:block;height:100%;width:40%;border-radius:2px;
  background:var(--c-brand);animation:boot 1.1s ease-in-out infinite}
@keyframes boot{0%{margin-left:-40%}100%{margin-left:100%}}

header{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:14px;
  padding:12px 22px;background:var(--c-bg);border-bottom:1px solid var(--c-line)}
.brand{display:flex;align-items:center;gap:11px}
.brand .mark{width:38px;height:38px;border-radius:50%;
  background:linear-gradient(135deg,#5fd08a,#5aa7f0);display:flex;align-items:center;
  justify-content:center;color:#fff;font-weight:700;font-size:17px}
.brand .tt{font-size:15px;font-weight:600}
.brand .sub{font-size:11.5px;color:var(--c-ink3);margin-left:2px}
.spacer{flex:1}
.back-home{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:9px;
  border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);
  font-size:12.5px;font-weight:500;cursor:pointer;transition:all .15s}
.homelink{display:inline-flex;align-items:center;margin-right:10px;text-decoration:none;color:var(--c-ink2)}
.homelink:hover{color:var(--c-brand)}
.homeico{display:inline-grid;place-items:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);transition:color .15s}.msearch{position:relative;display:flex;align-items:center;gap:8px;width:min(280px,32vw);padding:0 12px;height:38px;border-radius:19px;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);margin-right:12px}.msearch svg{flex:none;opacity:.7}.msearch input{flex:1;border:0;background:transparent;color:var(--c-ink);outline:0;font-size:13px}.msearch kbd{flex:none;font:600 11px monospace;color:var(--c-ink3);border:1px solid var(--c-line);border-radius:5px;padding:1px 6px}.mq-list{position:absolute;top:44px;right:0;width:min(320px,80vw);z-index:60;background:var(--c-panel);border:1px solid var(--c-line);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.28);overflow:hidden;display:none}.mq-list.on{display:block}.mq-item{display:block;width:100%;text-align:left;border:0;background:transparent;cursor:pointer;padding:9px 14px;color:var(--c-ink);font-size:13px;border-bottom:1px solid var(--c-line)}.mq-item:last-child{border-bottom:0}.mq-item:hover,.mq-item.sel{background:var(--c-hover,rgba(120,120,140,.14))} a:hover .homeico,.logo:hover .homeico,.homelink:hover .homeico{color:var(--c-brand);border-color:var(--c-brand)}
.nn-n{fill:var(--c-ink2)}.nn-h{fill:var(--c-brand)}.nn-e{stroke:var(--c-line);stroke-width:1.4}

.back-home:hover{border-color:var(--c-brand);color:var(--c-brand);background:var(--c-hover)}
.theme-toggle{width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);cursor:pointer;font-size:15px;
  display:flex;align-items:center;justify-content:center;transition:all .15s}
.theme-toggle:hover{border-color:var(--c-ink3);color:var(--c-ink);background:var(--c-hover)}
:root[data-theme="light"] .tt-moon{display:none}
:root:not([data-theme="light"]) .tt-sun{display:none}

.stats{display:flex;gap:8px;align-items:center;padding:0 22px;height:44px;
  background:var(--c-bg);border-bottom:1px solid var(--c-line);font-size:12px;color:var(--c-ink3)}
.stats b{color:var(--c-ink);font-weight:600}
.stat-pill{padding:3px 11px;border-radius:999px;background:var(--c-panel2);
  border:1px solid var(--c-line)}

.layout{display:flex;min-height:calc(100vh - 100px)}
.nav-group{margin-bottom:18px}
.ng-head{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  color:var(--c-ink3);padding:4px 10px 8px;display:flex;flex-direction:column;gap:3px}
.ng-desc{font-size:10px;font-weight:400;text-transform:none;letter-spacing:0;
  color:var(--c-ink3);opacity:.85;line-height:1.4}

/* ── 唯一导航主页：总架构图 + 透明热区 ── */
.arch-panel{display:none}
.arch-panel.active{display:block}
.arch-intro{margin-bottom:16px}
.arch-intro h2{margin:0 0 6px;font-size:20px;font-weight:600}
.arch-intro p{margin:0;font-size:13px;line-height:1.7;color:var(--c-ink2);max-width:900px}
.arch-wrap{background:var(--c-panel);border:1px solid var(--c-line);border-radius:16px;
  padding:0;box-shadow:var(--c-shadow-sm);overflow:hidden}
.arch-stage{position:relative;width:100%;max-width:1080px;margin:0 auto;
  aspect-ratio:__ARCH_ASPECT__}
.arch-img{display:block;width:100%;height:auto;border-radius:10px;filter:var(--cv-filter)}
.arch-hot{position:absolute;border:0;margin:0;padding:0;cursor:pointer;
  background:transparent;border-radius:9px;transition:background .15s,box-shadow .15s;
  display:flex;align-items:flex-end;justify-content:center}
.arch-hot:hover,.arch-hot:focus-visible{background:rgba(90,167,240,.16);
  box-shadow:inset 0 0 0 2px var(--c-brand);outline:none}
.arch-hot-label{opacity:0;transform:translateY(4px);transition:opacity .15s,transform .15s;
  margin-bottom:4px;padding:2px 8px;border-radius:999px;background:var(--c-brand);color:#fff;
  font-size:11px;font-weight:600;pointer-events:none;white-space:nowrap;
  box-shadow:0 2px 8px rgba(0,0,0,.25)}
.arch-hot:hover .arch-hot-label,.arch-hot:focus-visible .arch-hot-label{opacity:1;transform:none}
.arch-chips-wrap{margin-top:20px;display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.arch-chips-hd{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  color:var(--c-ink3)}
.arch-chips{display:flex;flex-wrap:wrap;gap:8px}
.arch-chip{padding:7px 14px;border-radius:999px;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);font-size:12.5px;cursor:pointer;transition:all .13s}
.arch-chip:hover{border-color:var(--c-brand);color:var(--c-brand);background:var(--c-hover)}

.main{flex:1;min-width:0;padding:22px 30px 60px}
.tabs{display:flex;margin-bottom:20px}
.tab-back{display:none;padding:7px 15px;border-radius:999px;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);font-size:13px;cursor:pointer;transition:all .13s}
.tab-back.show{display:inline-flex;align-items:center;gap:6px}
.tab-back:hover{border-color:var(--c-brand);color:var(--c-brand)}

.panel{display:none;animation:fade .3s ease}
.panel.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.panel-head{display:flex;align-items:baseline;gap:12px;margin-bottom:18px;
  padding-bottom:12px;border-bottom:1px solid var(--c-line)}
.panel-head h2{margin:0;font-size:20px;font-weight:600}
.fig-count{font-size:12px;color:var(--c-ink3);padding:2px 10px;border-radius:999px;
  background:var(--c-panel2);border:1px solid var(--c-line)}

/* ===== 垂直 tab（doris 式：左 nav 列 + 右内容，点切只显一节） ===== */
.vt-wrap{display:flex;align-items:flex-start;gap:22px;min-width:0}
.vt-navcol{flex:0 0 236px;position:sticky;top:16px;display:flex;flex-direction:column;gap:4px}
.vt-nav{display:flex;align-items:flex-start;gap:10px;width:100%;text-align:left;
  padding:11px 13px;border:1px solid transparent;border-radius:11px;background:transparent;
  color:var(--c-ink2);font-size:12.5px;line-height:1.45;cursor:pointer;transition:all .13s}
.vt-nav:hover{background:var(--c-panel2)}
.vt-nav.active{background:var(--c-panel);border-color:var(--c-line);color:var(--c-ink);
  box-shadow:var(--c-shadow-sm)}
.vt-n{flex:none;width:20px;height:20px;border-radius:6px;display:grid;place-items:center;
  font-size:11px;font-weight:700;background:var(--c-panel2);color:var(--c-ink3)}
.vt-nav.active .vt-n{background:var(--c-brand);color:#fff}
.vt-t{flex:1;min-width:0}
.vt-stage{flex:1;min-width:0}
.vt-sec{display:none;animation:fade .25s ease}
.vt-sec.active{display:block}
@media(max-width:820px){.vt-wrap{flex-direction:column}.vt-navcol{position:static;flex:none;width:100%;
  flex-direction:row;flex-wrap:wrap}.vt-nav{width:auto}}

.figs{display:flex;flex-direction:column;gap:22px}
.fig{margin:0;background:var(--c-panel);border:1px solid var(--c-line);border-radius:14px;
  padding:18px;box-shadow:var(--c-shadow-sm)}
.fig-img{display:block;max-width:100%;height:auto;margin:0 auto;border-radius:8px;
  filter:var(--cv-filter)}
.fig figcaption{margin-top:12px;font-size:12px;color:var(--c-ink3);text-align:center}
.fig.missing{color:#c0417a;font-size:13px;padding:26px;text-align:center;
  border-style:dashed}

.tips{margin-top:26px;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.tip{background:var(--c-panel);border:1px solid var(--c-line);border-radius:12px;padding:15px 17px}
.tip h4{margin:0 0 9px;font-size:13px;font-weight:600;color:var(--c-brand-ink)}
.tip p{margin:0;font-size:12.5px;line-height:1.65;color:var(--c-ink2)}
.tip ul{margin:0;padding-left:18px}
.tip li{font-size:12px;line-height:1.6;color:var(--c-ink2);margin:4px 0}
.tip-key{grid-column:1/-1;background:linear-gradient(135deg,var(--c-panel),var(--c-panel2));
  border-color:var(--c-brand)}
.tip-key p{color:var(--c-ink);font-size:13px}

footer{padding:22px 30px;color:var(--c-ink3);font-size:11.5px;border-top:1px solid var(--c-line);
  text-align:center}
@media(max-width:820px){.main{padding:16px}.arch-hot-label{display:none}}
</style>
</head>
<body>
<div id="boot"><div class="logo">Go</div>
  <div class="txt">正在装载核心原理图谱…</div><div class="bar"><i></i></div></div>

<header>
  <a class="homelink" href="../../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true" style="width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);display:inline-grid;place-items:center;text-decoration:none"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a>
  <div class="brand">
    <div><div class="tt">Go 语言 · 核心原理图谱</div>
    <span class="sub">运行时底座:GMP 调度器把 goroutine 复用到 OS 线程,并发三色标记 GC,netpoll 非阻塞 IO,channel 做 CSP 通信 —— 运行时纪律而非语言语法。</span></div>
  </div>
  <div class="spacer"></div>
  <a href="https://github.com/golang/go" target="_blank" rel="noopener" title="GitHub 源码仓库" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg></a><a href="https://go.dev" target="_blank" rel="noopener" title="项目官网" style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);color:var(--c-ink2);text-decoration:none;margin-right:8px"><img src="data:image/svg+xml;base64,PHN2ZyBmaWxsPSIjMDBBREQ4IiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU+R288L3RpdGxlPjxwYXRoIGQ9Ik0xLjgxMSAxMC4yMzFjLS4wNDcgMC0uMDU4LS4wMjMtLjAzNS0uMDU5bC4yNDYtLjMxNWMuMDIzLS4wMzUuMDgxLS4wNTguMTI4LS4wNThoNC4xNzJjLjA0NiAwIC4wNTguMDM1LjAzNS4wN2wtLjE5OS4zMDNjLS4wMjMuMDM2LS4wODIuMDctLjExNy4wN3pNLjA0NyAxMS4zMDZjLS4wNDcgMC0uMDU5LS4wMjMtLjAzNS0uMDU4bC4yNDUtLjMxNmMuMDIzLS4wMzUuMDgyLS4wNTguMTI5LS4wNThoNS4zMjhjLjA0NyAwIC4wNy4wMzUuMDU4LjA3bC0uMDkzLjI4Yy0uMDEyLjA0Ny0uMDU4LjA3LS4xMDUuMDd6bTIuODI4IDEuMDc1Yy0uMDQ3IDAtLjA1OS0uMDM1LS4wMzUtLjA3bC4xNjMtLjI5MmMuMDIzLS4wMzUuMDctLjA3LjExNy0uMDdoMi4zMzdjLjA0NyAwIC4wNy4wMzUuMDcuMDgybC0uMDIzLjI4YzAgLjA0Ny0uMDQ3LjA4Mi0uMDgyLjA4MnptMTIuMTI5LTIuMzZjLS43MzYuMTg3LTEuMjM5LjMyNy0xLjk2My41MTQtLjE3Ni4wNDYtLjE4Ny4wNTgtLjM0LS4xMTctLjE3NC0uMTk5LS4zMDMtLjMyNy0uNTQ4LS40NDQtLjczNy0uMzYyLTEuNDUtLjI1Ny0yLjExNS4xNzUtLjc5NS41MTQtMS4yMDQgMS4yNzQtMS4xOTIgMi4yMi4wMTEuOTM1LjY1NCAxLjcwNiAxLjU3NyAxLjgzNS43OTUuMTA1IDEuNDYtLjE3NSAxLjk4Ny0uNzcuMTA1LS4xMy4xOTgtLjI3LjMxNS0uNDM0SDEwLjQ3Yy0uMjQ1IDAtLjMwNC0uMTUyLS4yMjItLjM1LjE1Mi0uMzYyLjQzMi0uOTcuNTk2LTEuMjc0YS4zMTUuMzE1IDAgMDEuMjkyLS4xODdoNC4yNTNjLS4wMjMuMzE2LS4wMjMuNjMxLS4wNy45NDdhNC45ODMgNC45ODMgMCAwMS0uOTU4IDIuMjljLS44NDEgMS4xMS0xLjk0IDEuOC0zLjMzIDEuOTg2LTEuMTQ1LjE1Mi0yLjIwOS0uMDctMy4xNDMtLjc3LS44NjUtLjY1NS0xLjM1Ni0xLjUyLTEuNDg0LTIuNTk1LS4xNTItMS4yNzQuMjIyLTIuNDE5Ljk5My0zLjQyNC44My0xLjA4NiAxLjkyOC0xLjc3NiAzLjI3Mi0yLjAyIDEuMDk4LS4yIDIuMTUtLjA3IDMuMDk2LjU3MS42Mi40MSAxLjA2My45NyAxLjM1NiAxLjY0OC4wNy4xMDUuMDIzLjE2NC0uMTE3LjJtMy44NjggNi40NjFjLTEuMDY0LS4wMjQtMi4wMzQtLjMyOC0yLjg1Mi0xLjAyOWEzLjY2NSAzLjY2NSAwIDAxLTEuMjYyLTIuMjU1Yy0uMjEtMS4zMi4xNTItMi40ODkuOTQ3LTMuNTI5Ljg1My0xLjEyMiAxLjg4MS0xLjcwNiAzLjI3Mi0xLjk1IDEuMTkyLS4yMSAyLjMxNC0uMDk1IDMuMzMuNTk1LjkyMy42MyAxLjQ5NiAxLjQ4NCAxLjY0OCAyLjYwNS4xOTggMS41NzgtLjI1NyAyLjg2My0xLjM0NCAzLjk2Mi0uNzcxLjc4My0xLjcxOCAxLjI3My0yLjgwNSAxLjQ5NS0uMzE1LjA2LS42My4wNy0uOTM0LjEwNnptMi43OC00LjcyYy0uMDExLS4xNTMtLjAxMS0uMjctLjAzNC0uMzg3LS4yMS0xLjE1Ny0xLjI3NC0xLjgxLTIuMzg0LTEuNTU0LTEuMDg3LjI0NS0xLjc4OC45MzUtMi4wNDUgMi4wMzMtLjIxLjkxMi4yMzQgMS44MzUgMS4wNzUgMi4yMS42NDMuMjggMS4yODUuMjQ0IDEuOTA1LS4wNy45MjMtLjQ4IDEuNDI1LTEuMjI4IDEuNDg0LTIuMjMzeiIvPjwvc3ZnPg==" width="18" height="18" alt="官网" style="display:block"/></a><label class="msearch"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><input id="mq" type="text" placeholder="搜索模块 / 主线…" autocomplete="off" aria-label="搜索模块"/><kbd>/</kbd><div id="mqlist" class="mq-list"></div></label><button class="theme-toggle" id="themeToggle" title="切换深色 / 浅色" aria-label="切换主题">
    <span class="tt-moon">☾</span><span class="tt-sun">☀</span>
  </button>
</header>

<div class="layout">
  <main class="main">
    <nav class="tabs">__TABS__</nav>
    __PANELS__
  </main>
</div>

<footer>Go 语言核心原理图谱 · 由 design/ 经 gen.py 编译 · 单文件离线自包含 · 深色默认可切浅色</footer>

<script>
(function(){
  var FIRST="__FIRST_TID__";
  // 主题：localStorage 记忆，深色默认
  var saved=null;
  try{saved=localStorage.getItem("atlas-nav-theme");}catch(e){}
  if(saved==="light")document.documentElement.setAttribute("data-theme","light");
  var tt=document.getElementById("themeToggle");
  tt.onclick=function(){
    var light=document.documentElement.getAttribute("data-theme")==="light";
    if(light){document.documentElement.removeAttribute("data-theme");}
    else{document.documentElement.setAttribute("data-theme","light");}
    try{localStorage.setItem("atlas-nav-theme",light?"dark":"light");}catch(e){}
  };
  // 选中某主线（home = 架构总览主页）
  function select(tid){
    var panels=document.querySelectorAll(".panel");
    for(var i=0;i<panels.length;i++)
      panels[i].classList.toggle("active",panels[i].dataset.tid===tid);
    // 「← 返回架构图」仅在下钻到主线面板时出现，home 主页隐藏
    var back=document.querySelector(".tab-back");
    if(back)back.classList.toggle("show",tid!=="home");
    try{history.replaceState(null,"","#"+tid);}catch(e){}
    document.querySelector(".main").scrollTop=0;
    window.scrollTo(0,0);
  }
  function bind(sel){
    var els=document.querySelectorAll(sel);
    for(var i=0;i<els.length;i++){
      els[i].onclick=function(){select(this.dataset.tid);};
    }
  }
  // 架构图热区 / 返回按钮 共用同一开面板路径
  bind(".arch-hot");bind(".tab-back");
  // 垂直 tab：点左侧 nav 只显对应节（限本 .vt-wrap 组内）
  (function(){
    var navs=document.querySelectorAll(".vt-nav");
    for(var i=0;i<navs.length;i++){
      navs[i].onclick=function(){
        var wrap=this.closest(".vt-wrap");if(!wrap)return;
        var ns=wrap.querySelectorAll(".vt-nav"),ss=wrap.querySelectorAll(".vt-sec");
        for(var j=0;j<ns.length;j++)ns[j].classList.remove("active");
        for(var k=0;k<ss.length;k++)ss[k].classList.remove("active");
        this.classList.add("active");
        var sec=document.getElementById(this.dataset.sec);
        if(sec)sec.classList.add("active");
        wrap.scrollIntoView({block:"nearest"});
      };
    }
  })();
  // 主线 tid 序（去重，按热区在图上的 DOM 顺序）——键盘/URL 导航依据
  function tidOrder(){
    var seen={},ids=[],hs=document.querySelectorAll(".arch-hot");
    for(var i=0;i<hs.length;i++){var t=hs[i].dataset.tid;if(t&&!seen[t]){seen[t]=1;ids.push(t);}}
    return ids;
  }
  // 初始：URL hash 命中某主线则下钻，否则架构总览主页
  var hash=(location.hash||"").replace("#","");
  var order=tidOrder();
  select(order.indexOf(hash)>=0?hash:"home");
  // 键盘：左右在各主线间切换（沿热区顺序）
  document.addEventListener("keydown",function(e){
    if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA")return;
    if(e.key!=="ArrowLeft"&&e.key!=="ArrowRight")return;
    var ids=tidOrder();
    var cur=(location.hash||"").replace("#","");
    var idx=ids.indexOf(cur);if(idx<0)idx=0;
    idx+=(e.key==="ArrowRight"?1:-1);
    if(idx<0)idx=ids.length-1;if(idx>=ids.length)idx=0;
    select(ids[idx]);e.preventDefault();
  });
  // 收起首帧覆盖层
  var boot=document.getElementById("boot");
  setTimeout(function(){boot.classList.add("hide");
    setTimeout(function(){boot.style.display="none";},450);},260);
})();

/* 模块搜索(DOM-scrape 通用法:读现有 nav 项,过滤后 dispatch click) */
(function(){
  var mq=document.getElementById('mq'), list=document.getElementById('mqlist');
  if(!mq||!list) return;
  function items(){
    return [].slice.call(document.querySelectorAll('[data-tid]')).map(function(el){
      var lab=(el.getAttribute('title')||el.textContent||'').trim().replace(/\s+/g,' ');
      return {el:el, lab:lab};
    }).filter(function(x){return x.lab && x.lab.length<40;});
  }
  var sel=-1, cur=[];
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function render(){
    var q=mq.value.trim().toLowerCase();
    var seen={};
    cur = !q ? [] : items().filter(function(x){
      if(seen[x.lab])return false; if(x.lab.toLowerCase().indexOf(q)<0)return false; seen[x.lab]=1; return true;
    }).slice(0,8);
    if(!cur.length){ list.className='mq-list'; list.innerHTML=''; return; }
    sel=0;
    list.innerHTML=cur.map(function(x,i){return '<button class="mq-item'+(i===0?' sel':'')+'" data-i="'+i+'">'+esc(x.lab)+'</button>';}).join('');
    list.className='mq-list on';
  }
  function go(i){ mq.value=''; list.className='mq-list'; list.innerHTML=''; if(cur[i]) cur[i].el.click(); window.scrollTo(0,0); }
  mq.addEventListener('input',render);
  mq.addEventListener('keydown',function(e){
    if(!cur.length){ if(e.key==='Escape') mq.blur(); return; }
    if(e.key==='ArrowDown'){e.preventDefault();sel=(sel+1)%cur.length;}
    else if(e.key==='ArrowUp'){e.preventDefault();sel=(sel-1+cur.length)%cur.length;}
    else if(e.key==='Enter'){e.preventDefault();go(sel);return;}
    else if(e.key==='Escape'){list.className='mq-list';mq.blur();return;}
    else return;
    [].forEach.call(list.children,function(el,i){el.className='mq-item'+(i===sel?' sel':'');});
  });
  list.addEventListener('click',function(e){var b=e.target.closest('.mq-item'); if(b) go(+b.dataset.i);});
  document.addEventListener('keydown',function(e){ if(e.key==='/'&&document.activeElement!==mq){e.preventDefault();mq.focus();} });
  document.addEventListener('click',function(e){ if(!e.target.closest('.msearch')){list.className='mq-list';} });
})();

</script>
</body>
</html>
"""


def main():
    if not os.path.isdir(DESIGN_DIR):
        print(f"错误：design 目录不存在：{DESIGN_DIR}", file=sys.stderr)
        sys.exit(1)
    html_out = build_html()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    size = os.path.getsize(OUT)
    n_docs = len(MAINLINES)
    n_figs = sum(len(parse_doc(fn)["figs"]) for _, fn, *_ in MAINLINES)
    print(f"✓ 已生成 {OUT}")
    print(f"  字节数：{size:,}（{size/1024:.0f} KB）")
    print(f"  主线：{n_docs} 条 · 图引用：{n_figs} 张")
    print(f"  家族：{' / '.join(CAT_ORDER)}")


if __name__ == "__main__":
    main()
