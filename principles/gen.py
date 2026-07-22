#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""架构原理层生成器（principles/gen.py）—— 系统设计模式详情页。

与主题图谱（topics/，讲某个具体算法怎么运作，不点名项目）不同：这里对标
system-design-primer 一类经典，讲**为何选这类架构模式**——CAP/一致性谱、
复制策略、分片、缓存、限流背压、消息队列、服务发现、熔断幂等重试，
每个模式下的变体都显式点名真实项目，做「项目实现对比」。

产物（全部自包含、仅标准库、离线、SVG 全部 base64 内联、双主题 + 记忆切换）：
  principles/<slug>/index.html     —— 模式页：判型标题带 → 生态架构总图 → 变体分组（点名项目）→ 对比图 → 参考文献
入口卡片在主站 ../gen.py 的「架构原理」一级模式内（build_principles_cards，直连各模式页，无独立门户）；
模式页「返回架构原理」链接指向 ../../index.html#principles，由主站 JS 深链接激活对应一级模式。

设计文件命名（各模式 design/ 目录内）：
  生态架构  <模式中文>_00生态架构.svg
  变体机制  <模式中文>_<ID>xxx.svg   （ID 见 PRINCIPLES 里 groups[].mechs[].n）
  对比图    <模式中文>_CMP对比.svg
  注解散文  <模式中文>.md   （用 @eco / @<id小写> / @cmp / @refs 分节）

用法：  cd principles && python3 gen.py
"""
import base64
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# ===================================================================== #
# 一、架构原理内容契约（PRINCIPLES）—— 8 个系统设计模式，变体=真实项目落点
# ===================================================================== #
PRINCIPLES = [
    {
        "slug": "partitioning", "cn": "分片与哈希",
        "en": "Partitioning & Consistent Hashing",
        "title": "Partitioning & Consistent Hashing · 分片与一致性哈希",
        "core": "分片把「一张表」拆成「可独立搬动的单元」，取舍轴是加减节点时要不要搬动全量数据——固定哈希槽最简单也最刚性，一致性哈希环最柔性。",
        "color": "#2f9e6e", "eco": "分片与哈希_00生态架构.svg",
        "groups": [
            {"algo": "固定哈希槽 Fixed Hash Slots", "mechs": [
                {"n": "P1", "title": "Redis Cluster 16384 槽", "svg": "分片与哈希_P1哈希槽.svg"},
            ]},
            {"algo": "一致性哈希环 Consistent Hash Ring", "mechs": [
                {"n": "P2", "title": "Hudi 一致性哈希 split / merge", "svg": "分片与哈希_P2一致性哈希环.svg"},
            ]},
            {"algo": "范围+哈希两级 Range + Hash", "mechs": [
                {"n": "P3", "title": "Doris Range/List 分区 + Hash 分桶", "svg": "分片与哈希_P3两级分片.svg"},
            ]},
        ],
        "compare": {"svg": "分片与哈希_CMP对比.svg"},
    },
    {
        "slug": "replication", "cn": "复制策略",
        "en": "Replication",
        "title": "Replication · 复制策略与故障切换",
        "core": "复制把「一份数据」变成「多份副本」以换容错，主从/多主/无主三种拓扑在「写去哪」「读多新」「丢多少」三轴上各有取舍。",
        "color": "#2f6df0", "eco": "复制策略_00生态架构.svg",
        "groups": [
            {"algo": "主从 Primary-Standby", "mechs": [
                {"n": "R1", "title": "Postgres WAL 流复制", "svg": "复制策略_R1主从流复制.svg"},
            ]},
            {"algo": "多主 Multi-Master", "mechs": [
                {"n": "R2", "title": "ClickHouse 多主异步复制", "svg": "复制策略_R2多主复制.svg"},
            ]},
            {"algo": "无主 Leaderless（概念参考）", "mechs": [
                {"n": "R3", "title": "Dynamo / Cassandra Quorum N/R/W", "svg": "复制策略_R3无主Quorum.svg"},
            ]},
        ],
        "compare": {"svg": "复制策略_CMP对比.svg"},
    },
    {
        "slug": "caching", "cn": "缓存模式",
        "en": "Caching Patterns",
        "title": "Caching Patterns · 缓存模式与失效策略",
        "core": "缓存拿命中率换延迟，核心矛盾在「命中前谁去源站取」与「写后何时让缓存看见新值」——两条路径分别决定了读穿透与写回的形状。",
        "color": "#d98a00", "eco": "缓存模式_00生态架构.svg",
        "groups": [
            {"algo": "读穿透+回填 Read Path", "mechs": [
                {"n": "H1", "title": "nginx proxy_cache 未命中回填", "svg": "缓存模式_H1读穿透回填.svg"},
            ]},
            {"algo": "写回 Write-Back", "mechs": [
                {"n": "H2", "title": "InnoDB Buffer Pool 写回", "svg": "缓存模式_H2写回.svg"},
            ]},
        ],
        "compare": {"svg": "缓存模式_CMP对比.svg"},
    },
    {
        "slug": "flow-control", "cn": "限流与背压",
        "en": "Rate Limiting & Backpressure",
        "title": "Rate Limiting & Backpressure · 限流与背压",
        "core": "系统扛不住流量有两种姿势：在门外拒绝（限流）或在内部把压力向上游传导（背压）——前者保护自己、后者保护全链路。",
        "color": "#2aa0a4", "eco": "限流与背压_00生态架构.svg",
        "groups": [
            {"algo": "边缘拒绝 Rate Limiting", "mechs": [
                {"n": "F1", "title": "nginx limit_req 漏桶", "svg": "限流与背压_F1漏桶限流.svg"},
                {"n": "F2", "title": "k8s client-go 令牌桶 + 指数退避", "svg": "限流与背压_F2令牌桶.svg"},
            ]},
            {"algo": "内部传导减速 Backpressure", "mechs": [
                {"n": "F3", "title": "Flink credit-based 反压", "svg": "限流与背压_F3反压.svg"},
            ]},
        ],
        "compare": {"svg": "限流与背压_CMP对比.svg"},
    },
    {
        "slug": "messaging", "cn": "消息队列模式",
        "en": "Messaging Patterns",
        "title": "Messaging Patterns · 消息队列模式",
        "core": "消息队列把「谁发」与「谁收」解耦，发布订阅/竞争消费者/投递语义三个维度分别回答「广播给谁」「谁分摊」「丢不丢/重不重」。",
        "color": "#8a5cae", "eco": "消息队列模式_00生态架构.svg",
        "groups": [
            {"algo": "发布订阅 Publish-Subscribe", "mechs": [
                {"n": "M1", "title": "Kafka Topic / Partition 广播", "svg": "消息队列模式_M1发布订阅.svg"},
            ]},
            {"algo": "竞争消费者 Consumer Group", "mechs": [
                {"n": "M2", "title": "Kafka Consumer Group Rebalance", "svg": "消息队列模式_M2消费者组.svg"},
            ]},
            {"algo": "投递语义 Delivery Semantics", "mechs": [
                {"n": "M3", "title": "Kafka 幂等生产者 + 事务", "svg": "消息队列模式_M3投递语义.svg"},
            ]},
        ],
        "compare": {"svg": "消息队列模式_CMP对比.svg"},
    },
    {
        "slug": "service-discovery", "cn": "服务发现",
        "en": "Service Discovery",
        "title": "Service Discovery · 服务发现与存活检测",
        "core": "服务发现的核心是「怎么知道一个节点还活着」——租约心跳与会话临时节点是同一个 TTL 思想的两种实现外壳。",
        "color": "#c4562f", "eco": "服务发现_00生态架构.svg",
        "groups": [
            {"algo": "租约心跳 Lease", "mechs": [
                {"n": "D1", "title": "etcd Lease TTL", "svg": "服务发现_D1租约心跳.svg"},
            ]},
            {"algo": "会话临时节点 Ephemeral Session", "mechs": [
                {"n": "D2", "title": "ZooKeeper Session 分桶过期", "svg": "服务发现_D2会话临时节点.svg"},
            ]},
        ],
        "compare": {"svg": "服务发现_CMP对比.svg"},
    },
    {
        "slug": "resilience", "cn": "熔断幂等重试",
        "en": "Circuit Breaking, Idempotency & Retry",
        "title": "Circuit Breaking, Idempotency & Retry · 熔断幂等与重试",
        "core": "故障是常态不是异常：熔断阻止故障扩散、幂等让重试安全、重试让瞬时故障自愈——三者环环相扣，少一个都不完整。",
        "color": "#6a5fc4", "eco": "熔断幂等重试_00生态架构.svg",
        "groups": [
            {"algo": "熔断状态机 Circuit Breaking", "mechs": [
                {"n": "B1", "title": "nginx 被动健康检查", "svg": "熔断幂等重试_B1被动健康检查.svg"},
                {"n": "B2", "title": "gRPC outlier_detection", "svg": "熔断幂等重试_B2outlier检测.svg"},
                {"n": "B3", "title": "StarRocks 大查询资源熔断", "svg": "熔断幂等重试_B3资源熔断.svg"},
            ]},
            {"algo": "幂等键去重 Idempotency", "mechs": [
                {"n": "B4", "title": "Kafka 幂等生产者去重", "svg": "熔断幂等重试_B4幂等去重.svg"},
            ]},
            {"algo": "安全重试 Safe Retry", "mechs": [
                {"n": "B5", "title": "nginx proxy_next_upstream", "svg": "熔断幂等重试_B5安全重试.svg"},
            ]},
        ],
        "compare": {"svg": "熔断幂等重试_CMP对比.svg"},
    },
]

# ===================================================================== #
# 二、文件读取 / base64 内联 / markdown 行内（与 topics/gen.py 同构，自包含不共享）
# ===================================================================== #
_missing = []


def _design_dir(slug):
    return os.path.join(HERE, slug, "design")


def _read(slug, fname):
    p = os.path.join(_design_dir(slug), fname)
    if not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def _b64_svg(slug, fname):
    p = os.path.join(_design_dir(slug), fname)
    if not os.path.isfile(p):
        _missing.append("%s/%s" % (slug, fname))
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _md_inline(s):
    """行内 markdown → HTML：链接 → bold → code。escape 后再匹配（url 里无 * `，安全）。"""
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener" class="ref">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _md_para(body):
    """把一段散文（可能多行）转成若干 <p>。空行分段。"""
    body = (body or "").strip()
    if not body:
        return ""
    chunks = re.split(r"\n\s*\n", body)
    return "".join("<p>%s</p>" % _md_inline(c.strip().replace("\n", " "))
                   for c in chunks if c.strip())


def parse_prose(slug, cn):
    """读取 <cn>.md，按任意 @marker 分节（@eco / @c1 / @cmp / @refs …），返回 dict。
    键即 marker 小写；缺失键 .get() 兜底空串。"""
    txt = _read(slug, cn + ".md")
    buf = {}
    cur = None
    for line in txt.splitlines():
        m = re.match(r"^@(\w+)\s*$", line.strip())
        if m:
            cur = m.group(1).lower()
            buf.setdefault(cur, [])
            continue
        if cur is not None:
            buf[cur].append(line)
    return {k: _md_para("\n".join(v)) for k, v in buf.items()}


def esc(s):
    return html.escape(str(s), quote=True)


# ===================================================================== #
# 三、页面模板：CSS（双主题 graphite / light）+ JS（记忆切换）—— 与 topics/gen.py 同构
# ===================================================================== #
CSS = r"""
:root{
  --c-bg:#0d0d0f; --c-card:#17171a; --c-card2:#1e1e22; --c-ink:#f2f2f5;
  --c-ink2:#a1a1a6; --c-ink3:#6e6e73; --c-line:#2a2a30; --c-edge:#33333a;
  --c-panel:#161619; --c-shadow:rgba(0,0,0,.5);
}
html[data-theme="light"]{
  --c-bg:#fbfbfd; --c-card:#ffffff; --c-card2:#f5f5f7; --c-ink:#1d1d1f;
  --c-ink2:#6e6e73; --c-ink3:#a1a1a6; --c-line:#e6e6ea; --c-edge:#d2d2d7;
  --c-panel:#ffffff; --c-shadow:rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--c-bg);color:var(--c-ink);
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;
  font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
header{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:14px;
  padding:12px 24px;background:color-mix(in srgb,var(--c-bg) 86%,transparent);
  backdrop-filter:saturate(1.4) blur(14px);border-bottom:1px solid var(--c-line)}
header .logo{display:inline-flex;align-items:center;flex:none}
header .spacer{flex:1}
.brand-intro{display:flex;flex-direction:column;align-items:flex-start;margin-left:6px;min-width:0}
.brand-intro .bt{font-size:15px;font-weight:700;color:var(--c-ink);line-height:1.3}
.brand-intro .bs{margin-top:3px;font-size:11.5px;color:var(--c-ink3);line-height:1.5}
.icobtn{width:38px;height:38px;border-radius:50%;border:1px solid var(--c-line);
  background:var(--c-panel);color:var(--c-ink2);cursor:pointer;display:inline-grid;
  place-items:center;font-size:16px;flex:none;text-decoration:none}
.tt-ico{font-size:16px;line-height:1}.tt-sun{display:none}
html[data-theme="light"] .tt-moon{display:none}html[data-theme="light"] .tt-sun{display:inline}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 80px}

/* ---- 模式页 ---- */
.judge{background:var(--c-card);border:1px solid var(--c-line);border-left:4px solid var(--acc);
  border-radius:14px;padding:18px 22px;margin-bottom:26px}
.judge .k{font-size:11px;font-weight:700;letter-spacing:.6px;color:var(--acc);text-transform:uppercase}
.judge h1{font-size:22px;font-weight:800;line-height:1.34;margin-top:7px}
.judge .core{margin-top:11px;font-size:13.5px;color:var(--c-ink2);line-height:1.7;max-width:900px}
.secttl{display:flex;align-items:center;gap:11px;margin:34px 0 14px}
.secttl .badge{flex:none;min-width:30px;height:30px;padding:0 9px;border-radius:9px;background:var(--acc);
  color:#fff;font-weight:800;font-size:15px;display:inline-grid;place-items:center}
.secttl .t{font-size:17px;font-weight:750}
.secttl.eco .badge{background:var(--c-ink);color:var(--c-bg)}
/* ── 垂直 TAB 布局 ── */
.vt-wrap{display:flex;gap:22px;margin-top:26px;align-items:flex-start}
.vt-nav{flex:none;width:236px;position:sticky;top:20px;display:flex;flex-direction:column;gap:8px}
.vt-grp{font-size:11px;font-weight:800;letter-spacing:.04em;color:var(--c-ink3);
  text-transform:none;margin:14px 4px 2px;padding-top:8px;border-top:1px solid var(--c-line)}
.vt-grp:first-child{margin-top:0;padding-top:0;border-top:none}
.vt-tab{display:flex;align-items:center;gap:10px;text-align:left;cursor:pointer;
  background:var(--c-card);border:1px solid var(--c-line);border-radius:12px;
  padding:12px 13px;color:var(--c-ink2);font:inherit;transition:.15s}
.vt-tab:hover{border-color:var(--acc);color:var(--c-ink)}
.vt-tab.active{background:var(--acc);border-color:var(--acc);color:#fff;box-shadow:0 4px 14px -6px var(--acc)}
.vt-tab .vt-b{flex:none;min-width:26px;height:26px;padding:0 7px;border-radius:8px;
  background:var(--c-card2);color:var(--acc);font-weight:800;font-size:13px;
  display:inline-grid;place-items:center}
.vt-tab.active .vt-b{background:rgba(255,255,255,.24);color:#fff}
.vt-tab .vt-l{font-size:12.5px;font-weight:650;line-height:1.35}
.vt-stage{flex:1;min-width:0}
.vt-sec{display:none}
.vt-sec.active{display:block;animation:vtfade .22s ease}
.vt-sec .secttl{margin-top:0}
@keyframes vtfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(max-width:820px){.vt-wrap{flex-direction:column}.vt-nav{position:static;width:100%;flex-direction:row;flex-wrap:wrap}.vt-tab{flex:1 1 44%}}
.fig{background:var(--c-card);border:1px solid var(--c-line);border-radius:16px;
  padding:16px;overflow:hidden}
.fig img{display:block;width:100%;height:auto;border-radius:8px}
html:not([data-theme="light"]) .fig img{filter:invert(.925) hue-rotate(180deg) saturate(.86)}
.blurb{margin-top:14px;background:var(--c-card);border:1px solid var(--c-line);
  border-radius:14px;padding:15px 19px}
.blurb p{font-size:13px;color:var(--c-ink2);line-height:1.75}
.blurb p+p{margin-top:9px}
.blurb b{color:var(--c-ink);font-weight:700}
.blurb code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:.88em;
  background:var(--c-card2);border:1px solid var(--c-line);border-radius:5px;padding:1px 5px;color:var(--acc)}
.blurb a{color:var(--acc);text-decoration:none;
  border-bottom:1px solid color-mix(in srgb,var(--acc) 40%,transparent);transition:border-color .15s}
.blurb a:hover{border-bottom-color:var(--acc)}
.refs{margin-top:30px;padding-top:18px;border-top:2px solid var(--c-line)}
.reflist{margin-top:12px}
.reflist p{margin:5px 0;font-size:12.5px;color:var(--c-ink2);line-height:1.7}
.reflist a{color:var(--acc)}
.miss{padding:40px;text-align:center;color:var(--c-ink3);font-size:13px;border:1px dashed var(--c-edge);border-radius:12px}
.backrow{margin-top:44px;padding-top:22px;border-top:1px solid var(--c-line)}
.backrow a{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--c-ink2);
  border:1px solid var(--c-line);border-radius:999px;padding:8px 16px;background:var(--c-panel)}
.backrow a:hover{color:var(--c-ink);border-color:var(--c-edge)}
footer{max-width:1180px;margin:0 auto;padding:0 24px 40px;color:var(--c-ink3);font-size:11.5px}
"""

APP_JS = r"""
(function(){
  var root=document.documentElement;
  var saved=localStorage.getItem('atlas-nav-theme');
  if(saved) root.setAttribute('data-theme',saved);
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='light'?'':'light';
    if(cur) root.setAttribute('data-theme',cur); else root.removeAttribute('data-theme');
    localStorage.setItem('atlas-nav-theme',cur);
  }
  var tb=document.getElementById('themeBtn');
  if(tb){tb.onclick=toggleTheme;}
  // 垂直 TAB 切换：点左侧 tab → 右侧只显对应节
  var wrap=document.querySelector('.vt-wrap');
  if(wrap){
    var tabs=wrap.querySelectorAll('.vt-tab');
    var secs=wrap.querySelectorAll('.vt-sec');
    tabs.forEach(function(t){
      t.addEventListener('click',function(){
        var tgt=t.getAttribute('data-target');
        tabs.forEach(function(x){x.classList.toggle('active',x===t);});
        secs.forEach(function(s){s.classList.toggle('active',s.id===tgt);});
      });
    });
  }
})();
"""

_HOME_SVG = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 10.5 12 3l9 7.5"/>'
            '<path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg>')
_THEME_BTN = ('<button id="themeBtn" class="icobtn" title="切换深色 / 浅色主题" aria-label="切换主题">'
             '<span class="tt-ico tt-moon">☾</span><span class="tt-ico tt-sun">☀</span></button>')


def _head(title):
    return ("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>%s</title>
<style>%s</style>
</head>
<body>""" % (esc(title), CSS))


# ===================================================================== #
# 四、模式页 <slug>/index.html
# ===================================================================== #
def build_principle_page(p):
    prose = parse_prose(p["slug"], p["cn"])
    acc = p["color"]

    def fig(fname, alt):
        b64 = _b64_svg(p["slug"], fname)
        if not b64:
            return '<div class="miss">机理图待绘制：%s</div>' % esc(fname)
        return ('<div class="fig"><img alt="%s" src="data:image/svg+xml;base64,%s"/></div>'
                % (esc(alt), b64))

    head = p["title"].split(" · ")[0]

    nav_groups = []
    secs = []
    first = True

    def add_sec(sid, badge, ttl, fig_svg, prose_key, big=False):
        nonlocal first
        pr = prose.get(prose_key) or ""
        blurb = ('<div class="blurb%s">%s</div>' % (" ml" if big else "", pr)) if pr else ""
        figher = fig(fig_svg, ttl) if fig_svg else ""
        secs.append(
            '<section class="vt-sec%s" id="%s" data-sec="%s">'
            '<div class="secttl"><span class="badge">%s</span>'
            '<span class="t">%s</span></div>%s%s</section>'
            % (" active" if first else "", sid, sid, esc(badge), esc(ttl), figher, blurb))
        first = False

    # 概览
    eco_prose = prose.get("eco") or ('<p>%s</p>' % _md_inline(p["core"]))
    nav_groups.append(("概览 Overview", [("sec-eco", "◎", "生态架构总图")]))
    secs.append(
        '<section class="vt-sec active" id="sec-eco" data-sec="sec-eco">'
        '<div class="secttl eco"><span class="badge">◎</span>'
        '<span class="t">生态架构总图 · 这类模式在系统设计空间中的位置</span></div>'
        '%s<div class="blurb">%s</div></section>'
        % (fig(p["eco"], head + " 生态架构"), eco_prose))
    first = False

    # 各变体分组：组名做 .vt-grp 小标题，组内每个真实项目落点一个 TAB
    for grp in p.get("groups", []):
        items = []
        for m in grp["mechs"]:
            sid = "sec-%s" % m["n"].lower()
            items.append((sid, m["n"], esc(m["title"])))
            add_sec(sid, m["n"], "%s · %s" % (grp["algo"], m["title"]),
                    m["svg"], m["n"].lower())
        nav_groups.append(("变体 · %s" % grp["algo"], items))

    # 跨项目对比图（图为主）
    cmp = p.get("compare") or {}
    if cmp.get("svg"):
        nav_groups.append(("对比 Compare", [("sec-cmp", "⇄", "跨项目对比")]))
        add_sec("sec-cmp", "⇄", head + " · 跨项目实现取舍对比", cmp["svg"], "cmp", big=True)

    # 底部统一「参考文献」区（常驻，不属任何 TAB）
    refs_html = ""
    if prose.get("refs"):
        refs_html = ('<section class="refs"><div class="secttl"><span class="badge">§</span>'
                     '<span class="t">参考文献 · 权威来源（论文 / 官方文档 / 源码）</span></div>'
                     '<div class="blurb reflist">%s</div></section>' % prose["refs"])

    nav_parts = []
    for glabel, items in nav_groups:
        nav_parts.append('<div class="vt-grp">%s</div>' % esc(glabel))
        for sid, badge, label in items:
            nav_parts.append(
                '<button class="vt-tab" data-target="%s"><span class="vt-b">%s</span>'
                '<span class="vt-l">%s</span></button>' % (sid, esc(badge), label))
    navcol = "".join(nav_parts).replace('class="vt-tab" data-target="sec-eco"',
                                        'class="vt-tab active" data-target="sec-eco"', 1)

    drill = ('<div class="vt-wrap">'
             '<nav class="vt-nav" aria-label="模式内容切换">%s</nav>'
             '<div class="vt-stage">%s</div></div>'
             % (navcol, "".join(secs)))

    body = """%s
<header>
  <a class="logo" href="../../index.html#principles" title="返回系统原理"><span class="icobtn">%s</span></a>
  <div class="brand-intro">
    <div class="bt">%s</div>
    <div class="bs">系统原理 · 系统设计模式（点名真实项目实现对比）</div>
  </div>
  <div class="spacer"></div>
  %s
</header>
<div class="wrap" style="--acc:%s">
  <div class="judge">
    <span class="k">%s · 判型</span>
    <h1>%s</h1>
    <div class="core">%s</div>
  </div>
  %s
  %s
  <div class="backrow"><a href="../../index.html#principles">← 返回系统原理</a></div>
</div>
<footer>自包含离线图谱 · 以图为主：概览 + 变体分组（真实项目落点）+ 跨项目对比 · 权威参考集中于底部 · 垂直 TAB 切换</footer>
<script>%s</script>
</body>
</html>""" % (_head(head + " · 系统原理"), _HOME_SVG, esc(head), _THEME_BTN, esc(acc),
              esc(p["slug"].upper()), p["title"], esc(p["core"]),
              drill, refs_html, APP_JS)
    return body


# ===================================================================== #
# 五、主流程
# ===================================================================== #
def main():
    portal_path = os.path.join(HERE, "index.html")
    if os.path.exists(portal_path):
        os.remove(portal_path)
        print("Removed stale %s" % portal_path)

    for p in PRINCIPLES:
        d = os.path.join(HERE, p["slug"])
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_principle_page(p))
        print("Wrote %s" % out)

    expected = 0
    for p in PRINCIPLES:
        expected += 1  # eco
        expected += sum(len(g["mechs"]) for g in p.get("groups", []))
        if p.get("compare", {}).get("svg"):
            expected += 1

    print("架构原理 %d 个模式页" % len(PRINCIPLES))
    if _missing:
        print("  ⚠ 缺失 SVG（%d / %d）：" % (len(_missing), expected))
        for m in _missing:
            print("      -", m)
    else:
        print("  ✓ 全部 %d 张 SVG 就位，无缺失" % expected)


if __name__ == "__main__":
    main()
