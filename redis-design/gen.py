#!/usr/bin/env python3
"""<项目级 gen.py 骨架> —— 把 <xxx>-design/design/ 编译成自包含双主题 index.html。

这是 design-skills 的**可复制起点**:全新引擎在没有现成生成器可移植时,从本骨架起步
(而非从零手写)。把 <XXX>/<xxx> 换成引擎名,按该引擎 design/ 的真实主题填 THEMES 即可。
完整方法论见 references/atlas-builder.md;双主题工程见 references/dual-theme-and-interactive.md。

铁律(勿违背):
  · 自包含:仅标准库,SVG/文档全部 base64 内联进单个 HTML,零网络/服务器依赖,双击即用。
  · 只读同级 design/,产物恒名 index.html(可随时重生成,绝不手改)。
  · 缺文件容错:_b64() 对不存在的文件返回 ""(未挂载主题的占位常量不炸全局)。
  · 落盘校验:写完打印字节数与主题清单,确认真的落盘(防"幽灵生成")。
"""
import argparse
import base64
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ── CLI:--design-dir / --out;等价 env,无硬编码绝对路径(CLI → env → 回退链) ──
_ap = argparse.ArgumentParser(description="生成 <XXX> 引擎交互式核心原理图谱(离线自包含 HTML)")
_ap.add_argument("--design-dir", default=None, help="手绘 SVG + prose 文档目录")
_ap.add_argument("--out", default=None, help="输出 HTML 路径")
_args, _ = _ap.parse_known_args()


def _first_existing(*cands):
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


DESIGN_DIR = _first_existing(
    _args.design_dir, os.environ.get("XXX_MAP_DESIGN_DIR"), os.path.join(HERE, "design"),
)
OUT = _args.out or os.environ.get("XXX_MAP_OUT") or os.path.join(HERE, "index.html")


# ── 素材内联:base64,缺文件容错(不抛,返回空串) ──
def _b64(name):
    path = os.path.join(DESIGN_DIR, name)
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _svg_img(name):
    """把一张 design/ 下的 .svg 内联为 <img>(base64)。缺文件 → 占位提示。"""
    b = _b64(name)
    if not b:
        return f'<div class="missing">缺图:{name}</div>'
    return f'<img alt="{name}" src="data:image/svg+xml;base64,{b}"/>'


# ── 主题清单:按本引擎 design/ 真实产出填写(库里没有的主题就不做,勿编造对等) ──
# 每个 theme:key(锚点) / label(导航显示) / cat(分组) / prose(.md,图从 md 的 ![](x.svg) 自动内联)
# cat: pano=全景 / iface=数据类型命令族 / support=引擎内部
THEMES = [
    {"key": "pano", "label": "全景主线框架", "cat": "pano",
     "prose": "Redis原理_全景主线框架.md"},

    # ── 接触面主线 · 数据类型命令族 ──
    {"key": "string", "label": "String 字符串", "cat": "iface", "prose": "Redis原理_String字符串.md"},
    {"key": "hash", "label": "Hash 哈希", "cat": "iface", "prose": "Redis原理_Hash哈希.md"},
    {"key": "list", "label": "List 列表", "cat": "iface", "prose": "Redis原理_List列表.md"},
    {"key": "setzset", "label": "Set / ZSet 集合", "cat": "iface", "prose": "Redis原理_SetZSet集合.md"},
    {"key": "stream", "label": "Stream 流", "cat": "iface", "prose": "Redis原理_Stream流.md"},

    # ── 支撑能力域 · 引擎内部 ──
    {"key": "object", "label": "对象与编码", "cat": "support", "prose": "Redis原理_支撑_对象与编码.md"},
    {"key": "net", "label": "网络与执行模型", "cat": "support", "prose": "Redis原理_支撑_网络与执行.md"},
    {"key": "mem", "label": "内存 · 过期与淘汰", "cat": "support", "prose": "Redis原理_支撑_内存过期淘汰.md"},
    {"key": "rdb", "label": "持久化 · RDB", "cat": "support", "prose": "Redis原理_支撑_持久化RDB.md"},
    {"key": "aof", "label": "持久化 · AOF", "cat": "support", "prose": "Redis原理_支撑_持久化AOF.md"},
    {"key": "repl", "label": "复制", "cat": "support", "prose": "Redis原理_支撑_复制.md"},
    {"key": "cluster", "label": "集群与高可用", "cat": "support", "prose": "Redis原理_支撑_集群与高可用.md"},
    {"key": "txn", "label": "事务 · 脚本 · 发布订阅", "cat": "support", "prose": "Redis原理_支撑_事务脚本发布订阅.md"},
]
CAT_ORDER = [("pano", "全景"), ("iface", "接触面主线 · 数据类型命令族"), ("support", "支撑能力域 · 引擎内部")]

# ── 架构图导航(产品规则:唯一首页导航 = 总架构图下钻)──
# 落地页 = design/Redis原理_全景_02总架构.svg(base64 内联),其上覆盖透明 .arch-hot 按钮;
# 点某模块 → 复用 sel(key) 打开对应主题面板。未在图上直接标注的主题走 .arch-chip 兜底。
_ARCH_SVG = "Redis原理_全景_02总架构.svg"
_ARCH_VBW, _ARCH_VBH = 1080, 640  # 总架构 SVG viewBox(无 <g transform>,坐标→百分比直接换算,无偏移)

# (x, y, w, h, key):矩形坐标取自该 SVG 的模块 <rect>,key = 该模块所属主题
_ARCH_HOTSPOTS = [
    (30, 146, 1020, 90, "net"),      # 接入层整条 · 单线程事件循环(ae/RESP/命令表/call/IO 线程)
    (46, 284, 300, 76, "object"),    # 键空间 dict:key → redisObject(对象与编码)
    (374, 312, 100, 38, "string"),   # String
    (484, 312, 100, 38, "hash"),     # Hash/Set 编码
    (594, 312, 100, 38, "list"),     # List
    (704, 312, 110, 38, "setzset"),  # ZSet
    (824, 312, 100, 38, "setzset"),  # Set(int) —— 同属 Set/ZSet 集合主题
    (934, 312, 90, 38, "stream"),    # Stream
    (46, 420, 230, 70, "mem"),       # 内存管理 · 过期与淘汰
    (286, 420, 230, 38, "rdb"),      # 持久化(上半)· RDB
    (286, 458, 230, 32, "aof"),      # 持久化(下半)· AOF
    (526, 420, 230, 70, "repl"),     # 复制
    (766, 420, 270, 70, "cluster"),  # 集群与高可用
]


def _build_arch_nav():
    """返回 (hotspots_html, chips_html):热点覆盖的主题 + 未覆盖主题的 chip 兜底(全 14 主题必可达)。"""
    if not _b64(_ARCH_SVG):
        return (f'<div class="missing">缺架构图:{_ARCH_SVG}</div>', "")
    label = {t["key"]: t["label"] for t in THEMES}
    hs = []
    for (x, y, w, h, key) in _ARCH_HOTSPOTS:
        lab = _html_escape(label.get(key, key))
        hs.append(
            '<button class="arch-hot" style="left:{lp:.4f}%;top:{tp:.4f}%;width:{wp:.4f}%;height:{hp:.4f}%" '
            'data-k="{k}" title="{lab}"><span class="arch-hot-lab">{lab}</span></button>'.format(
                lp=x / _ARCH_VBW * 100, tp=y / _ARCH_VBH * 100,
                wp=w / _ARCH_VBW * 100, hp=h / _ARCH_VBH * 100, k=key, lab=lab))
    depicted = {key for (_, _, _, _, key) in _ARCH_HOTSPOTS}
    chips = [
        '<button class="arch-chip" data-k="{k}">{lab}</button>'.format(k=t["key"], lab=_html_escape(t["label"]))
        for t in THEMES if t["key"] not in depicted
    ]
    return ("\n".join(hs), "\n".join(chips))


def discover_themes_if_empty():
    """THEMES 为空时,从 design/ 文件名 <XXX>原理_<模块>_<序号> 自动兜底发现主题。

    正式使用应手工填 THEMES(可控顺序/命名);此兜底仅让骨架"开箱能跑"。
    """
    if THEMES:
        return THEMES
    if not os.path.isdir(DESIGN_DIR):
        return []
    groups = {}
    for f in sorted(os.listdir(DESIGN_DIR)):
        if not f.lower().endswith(".svg"):
            continue
        m = re.match(r"^.+?原理[_]([^_]+)[_]", f)
        key = m.group(1) if m else "misc"
        groups.setdefault(key, []).append(f)
    return [{"key": k, "label": k, "svgs": v, "prose": None} for k, v in groups.items()]


def _md_inline(s):
    """行内 markdown:**bold** / `code`。先 bold 后 code(避免 code 内的 * 破坏 bold)。"""
    s = _html_escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r'<code>\1</code>', s)
    return s


def _html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _svg_data_uri(name):
    b = _b64(name)
    if not b:
        return None
    return f"data:image/svg+xml;base64,{b}"


def render_prose(name):
    """把一篇 .md 渲成结构化 HTML:# 标题 / ## 章节 / GFM 表格 / ![](x.svg) 内联 / > 引用 / 列表。"""
    if not name:
        return ""
    path = os.path.join(DESIGN_DIR, name)
    if not os.path.isfile(path):
        return f'<div class="missing">缺文档:{name}</div>'
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    out = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        # 图片 ![alt](file.svg)
        m = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", ln)
        if m:
            uri = _svg_data_uri(m.group(2))
            if uri:
                out.append(f'<figure><img alt="{_html_escape(m.group(1))}" src="{uri}"/></figure>')
            else:
                out.append(f'<div class="missing">缺图:{_html_escape(m.group(2))}</div>')
            i += 1
            continue
        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{_md_inline(m.group(2))}</h{lvl}>')
            i += 1
            continue
        # 引用块(可多行)
        if ln.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(_md_inline(lines[i].lstrip(">").strip()))
                i += 1
            out.append(f'<blockquote>{"<br/>".join(buf)}</blockquote>')
            continue
        # GFM 表格:连续以 | 开头的行,第二行是分隔
        if ln.strip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{_md_inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
            continue
        # 无序列表
        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(f"<li>{_md_inline(re.sub(r'^\s*[-*]\s+', '', lines[i]))}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue
        # 有序列表
        if re.match(r"^\s*\d+\.\s+", ln):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(f"<li>{_md_inline(re.sub(r'^\s*\d+\.\s+', '', lines[i]))}</li>")
                i += 1
            out.append(f"<ol>{''.join(items)}</ol>")
            continue
        # 空行 / 水平分隔线
        if not ln.strip() or re.match(r"^\s*-{3,}\s*$", ln):
            i += 1
            continue
        # 普通段落
        out.append(f"<p>{_md_inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def build_html(themes):
    # 面板机制保留:每主题一个 .panel(data-k=主题 key),由 sel(k) 切换显示
    panels = ""
    for t in themes:
        body = render_prose(t.get("prose")) if t.get("prose") else ""
        figs = "".join(f'<figure>{_svg_img(s)}</figure>' for s in t.get("svgs", []))
        panels += f'<section class="panel" data-k="{t["key"]}"><div class="prose">{figs}{body}</div></section>'
    # 唯一首页导航 = 总架构图下钻(替代原按 CAT_ORDER 分组的 .tabs 列表导航)
    arch_hot, arch_chips = _build_arch_nav()
    labels = {t["key"]: t["label"] for t in themes}
    return (TEMPLATE
            .replace("__ARCH_SVG_B64__", _b64(_ARCH_SVG))
            .replace("__ARCH_HOTSPOTS__", arch_hot)
            .replace("__ARCH_CHIPS__", arch_chips)
            .replace("__THEME_LABELS__", json.dumps(labels, ensure_ascii=False))
            .replace("__PANELS__", panels))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Redis 原理 · 交互式核心原理图谱</title>
<style>
:root{ --c-bg:#1c1c1e; --c-bg2:#161618; --c-panel:#242426; --c-panel2:#2c2c2e;
  --c-line:rgba(255,255,255,.11); --c-line2:rgba(255,255,255,.17);
  --c-ink:#f5f5f7; --c-ink2:#c4c4c9; --c-ink3:#8e8e93; --c-brand:#0a84ff; --c-brand-ink:#409cff;
  --c-code-bg:rgba(255,255,255,.06);
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace; }
:root[data-theme="light"]{ --c-bg:#f5f5f7; --c-bg2:#fbfbfd; --c-panel:#fff; --c-panel2:#f0f0f3;
  --c-line:rgba(0,0,0,.09); --c-line2:rgba(0,0,0,.14);
  --c-ink:#1d1d1f; --c-ink2:#424245; --c-ink3:#86868b; --c-brand:#0071e3; --c-brand-ink:#0066cc;
  --c-code-bg:rgba(0,0,0,.05); }
*{box-sizing:border-box} html{background:var(--c-bg2)}
body{margin:0;font-family:var(--sans);background:var(--c-bg);color:var(--c-ink);-webkit-font-smoothing:antialiased}
header{display:flex;justify-content:space-between;align-items:center;padding:16px 28px;border-bottom:1px solid var(--c-line);position:sticky;top:0;background:var(--c-bg);z-index:10}
.brand{font-size:15px;font-weight:700;letter-spacing:-.01em}
.brand .dim{color:var(--c-ink3);font-weight:400;font-size:13px;margin-left:8px}
.panel{display:none} .panel.on{display:block}
/* ── 首页唯一导航:总架构图下钻 ── */
.home{display:none;max-width:1180px;margin:0 auto;padding:30px 28px 80px}
.home.on{display:block}
.home-hero{text-align:center;max-width:860px;margin:0 auto 26px}
.home-title{font-size:24px;font-weight:700;letter-spacing:-.02em}
.home-desc{font-size:14px;line-height:1.7;color:var(--c-ink2);margin-top:10px}
.arch-canvas{position:relative;width:100%;max-width:1080px;margin:0 auto;line-height:0}
.arch-img{width:100%;height:auto;display:block;border:1px solid var(--c-line);border-radius:16px;background:#fbfbfd}
html:not([data-theme="light"]) .arch-img{filter:invert(.9) hue-rotate(180deg) saturate(1.05) brightness(.97)}
.arch-hot{position:absolute;border:1.5px solid transparent;border-radius:10px;background:transparent;
  cursor:pointer;padding:0;transition:all .18s;display:grid;place-items:center}
.arch-hot:hover{border-color:var(--c-brand);background:color-mix(in srgb,var(--c-brand) 12%,transparent);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand) 16%,transparent)}
.arch-hot:focus-visible{outline:none;border-color:var(--c-brand);background:color-mix(in srgb,var(--c-brand) 10%,transparent)}
.arch-hot-lab{opacity:0;font-size:11px;font-weight:700;color:#fff;background:var(--c-brand);
  padding:3px 9px;border-radius:7px;transition:opacity .18s;pointer-events:none;white-space:nowrap}
.arch-hot:hover .arch-hot-lab{opacity:1}
.arch-extra{max-width:1080px;margin:22px auto 0;text-align:center}
.arch-extra-h{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--c-ink3);font-weight:600;margin-bottom:12px}
.arch-chips{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}
.arch-chip{font:inherit;font-size:13px;font-weight:600;color:var(--c-ink2);padding:8px 16px;border-radius:11px;cursor:pointer;
  background:var(--c-panel);border:1px solid var(--c-line);transition:all .2s}
.arch-chip:hover{color:var(--c-brand);border-color:var(--c-brand);transform:translateY(-2px)}
/* 面板内返回架构图 */
.crumb{display:none;align-items:center;gap:10px;padding:14px 28px;border-bottom:1px solid var(--c-line)}
.crumb.on{display:flex}
.crumb-home{font:inherit;font-size:13px;cursor:pointer;background:var(--c-panel);border:1px solid var(--c-line);
  color:var(--c-ink2);border-radius:999px;padding:6px 14px;transition:all .15s}
.crumb-home:hover{border-color:var(--c-brand);color:var(--c-brand)}
.crumb-sep{color:var(--c-ink3);font-size:13px}
.crumb-cur{font-size:14px;font-weight:640;color:var(--c-ink)}
.panel{display:none} .panel.on{display:block}
.prose{max-width:1000px;margin:0 auto;padding:28px 28px 80px}
.prose h1{font-size:26px;font-weight:700;letter-spacing:-.02em;margin:8px 0 18px}
.prose h2{font-size:19px;font-weight:640;margin:34px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--c-line)}
.prose h3{font-size:15px;font-weight:600;margin:24px 0 10px;color:var(--c-brand-ink)}
.prose p{font-size:14px;line-height:1.7;color:var(--c-ink2);margin:10px 0}
.prose b{color:var(--c-ink);font-weight:640}
.prose code{font-family:var(--mono);font-size:12.5px;background:var(--c-code-bg);padding:1.5px 6px;border-radius:5px;color:var(--c-brand-ink)}
.prose blockquote{margin:16px 0;padding:12px 18px;background:var(--c-panel);border-left:3px solid var(--c-brand);border-radius:0 10px 10px 0;font-size:13.5px;line-height:1.65;color:var(--c-ink2)}
.prose ul,.prose ol{font-size:14px;line-height:1.7;color:var(--c-ink2);padding-left:24px}
.prose li{margin:5px 0}
.prose figure{margin:20px 0}
.prose figure img{max-width:100%;border:1px solid var(--c-line);border-radius:12px;background:#fbfbfd;display:block}
.prose table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13px}
.prose th,.prose td{border:1px solid var(--c-line);padding:8px 12px;text-align:left;vertical-align:top}
.prose th{background:var(--c-panel2);font-weight:600;color:var(--c-ink)}
.prose td{color:var(--c-ink2)}
.prose tbody tr:nth-child(even){background:var(--c-panel)}
.missing{color:#f43f5e;font-size:13px;padding:10px 0}
.theme-toggle{width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);cursor:pointer;font-size:16px;flex:none}
.theme-toggle:hover{color:var(--c-ink)}
.hgroup{display:inline-flex;align-items:center;gap:12px}
.homelink{display:inline-flex;align-items:center;margin-right:10px;text-decoration:none;color:var(--c-ink2)}
.homelink:hover{color:var(--c-brand)}
.homeico{display:inline-flex}
.back-portal{display:inline-flex;align-items:center;padding:7px 14px;border-radius:9px;border:1px solid var(--c-line);background:var(--c-panel);color:var(--c-ink2);font-size:12.5px;font-weight:500;text-decoration:none;flex:none}
.back-portal:hover{border-color:var(--c-brand);color:var(--c-brand)}
</style></head><body>
<header>
  <a class="homelink" href="../index.html" title="返回导航主页"><span class="homeico" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg></span></a><span class="brand">Redis 原理<span class="dim">内存数据结构存储图谱</span></span>
  <span class="hgroup">
  <button class="theme-toggle" id="tt" aria-label="切换主题">☾</button></span>
</header>
<nav class="crumb" id="crumb">
  <button class="crumb-home" id="crumbHome">← 总架构图</button>
  <span class="crumb-sep">/</span>
  <span class="crumb-cur" id="crumbCur"></span>
</nav>
<section class="home on" id="home">
  <div class="arch-canvas">
    <img class="arch-img" src="data:image/svg+xml;base64,__ARCH_SVG_B64__" alt="Redis 总架构图" draggable="false"/>
    __ARCH_HOTSPOTS__
  </div>
  <div class="arch-extra">
    <div class="arch-extra-h">架构图未直接标注 · 点此进入</div>
    <div class="arch-chips">__ARCH_CHIPS__</div>
  </div>
</section>
<main id="main">__PANELS__</main>
<script>
(function(){ var KEY="redis-atlas-theme", r=document.documentElement;
  function apply(t){ if(t==="light") r.setAttribute("data-theme","light"); else r.removeAttribute("data-theme"); }
  var s="dark"; try{ s=localStorage.getItem(KEY)||"dark"; }catch(e){} apply(s);
  document.getElementById("tt").onclick=function(){
    var n=r.getAttribute("data-theme")==="light"?"dark":"light"; apply(n);
    try{ localStorage.setItem(KEY,n); }catch(e){}
  };
})();
(function(){
  var LABELS=__THEME_LABELS__;
  var panels=[].slice.call(document.querySelectorAll(".panel"));
  var home=document.getElementById("home"), crumb=document.getElementById("crumb"), crumbCur=document.getElementById("crumbCur");
  // sel(k):打开主题 k 的面板(唯一面板切换函数,架构图热点/兜底 chip 复用它)
  function sel(k){
    var found=panels.some(function(p){return p.dataset.k===k;});
    if(!k||!found){ showHome(); return; }
    home.classList.remove("on");
    panels.forEach(function(p){p.classList.toggle("on",p.dataset.k===k);});
    crumb.classList.add("on"); crumbCur.textContent=LABELS[k]||k;
    if(history.replaceState) history.replaceState(null,"","#"+k);
    window.scrollTo(0,0);
  }
  function showHome(){
    panels.forEach(function(p){p.classList.remove("on");});
    crumb.classList.remove("on"); home.classList.add("on");
    if(history.replaceState) history.replaceState(null,"","#");
    window.scrollTo(0,0);
  }
  // 唯一入口:架构图热点 + 兜底 chip → sel(主题 key)
  document.querySelectorAll(".arch-hot,.arch-chip").forEach(function(b){ b.onclick=function(){sel(b.dataset.k);}; });
  document.getElementById("crumbHome").onclick=showHome;
  var h=location.hash.replace("#","");
  if(h && panels.some(function(p){return p.dataset.k===h;})) sel(h); else showHome();
})();
</script></body></html>
"""


def main():
    themes = discover_themes_if_empty()
    html = build_html(themes)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    size = os.path.getsize(OUT)
    missing = [t["prose"] for t in themes if t.get("prose") and not os.path.isfile(os.path.join(DESIGN_DIR, t["prose"]))]
    print(f"Wrote {OUT} ({size // 1024} KB)")
    print(f"themes ({len(themes)}): {', '.join(t['key'] for t in themes)}")
    if missing:
        print(f"缺 prose ({len(missing)}): {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()

