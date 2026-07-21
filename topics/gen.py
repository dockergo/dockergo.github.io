#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题导航层生成器（topics/gen.py）—— 跨项目「主题图谱」门户。

与各 *-design 项目的「按项目」导航平行，这里按 **计算系统的核心主题**（概念层，
不点名具体项目）组织：一个生态架构总图 + 恰好 3 个图解点（机理图 + 短注解）。

产物（全部自包含、仅标准库、离线、SVG 全部 base64 内联、双主题 + 记忆切换）：
  topics/index.html            —— 门户：6 张主题卡片（标题 + 核心一句 + 3 图解点预览）
  topics/<slug>/index.html     —— 主题页：判型标题带 → 生态架构总图 → 3 图解点（图 + 注解）

设计文件命名（各主题 design/ 目录内）：
  生态架构  <主题中文>_00生态架构.svg
  图解点    <主题中文>_01xxx.svg / _02xxx.svg / _03xxx.svg
  注解散文  <主题中文>.md   （用 @eco / @p1 / @p2 / @p3 分节）

用法：  cd topics && python3 gen.py
"""
import base64
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# ===================================================================== #
# 一、主题内容契约（THEMES）—— 用户逐字规格
# ===================================================================== #
THEMES = [
    {
        "slug": "consensus", "cn": "分布式共识",
        "en": "Consensus & Replication",
        "title": "Consensus & Replication · 分布式共识与状态复制",
        "core": "把「一个值」变成「一条只增不改的日志」，多数派确认即提交；副本按同一日志顺序回放，得到同一状态机。",
        "color": "#4a7fd0", "eco": "分布式共识_00生态架构.svg",
        "groups": [
            {"algo": "Raft", "mechs": [
                {"n": "R1", "title": "Leader 选举与任期", "svg": "分布式共识_R1选举.svg"},
                {"n": "R2", "title": "日志连续性回溯匹配", "svg": "分布式共识_01日志回溯.svg"},
                {"n": "R3", "title": "成员变更（联合/单步）", "svg": "分布式共识_R3成员变更.svg"},
                {"n": "R4", "title": "ReadIndex / Lease 读一致", "svg": "分布式共识_03读一致性.svg"},
            ]},
            {"algo": "Multi-Paxos", "mechs": [
                {"n": "P1", "title": "两阶段 prepare/accept", "svg": "分布式共识_P1两阶段.svg"},
                {"n": "P2", "title": "稳定 Leader 摊销一阶段", "svg": "分布式共识_P2稳定Leader.svg"},
            ]},
            {"algo": "ZAB", "mechs": [
                {"n": "Z1", "title": "原子广播提交", "svg": "分布式共识_Z1广播.svg"},
                {"n": "Z2", "title": "崩溃恢复同步", "svg": "分布式共识_Z2恢复.svg"},
            ]},
        ],
        "compare": {"svg": "分布式共识_CMP算法对比.svg"},
        "eng": {"svg": "分布式共识_ENG工程对比.svg"},
    },
    {
        "slug": "transaction", "cn": "事务并发",
        "en": "Transaction & Concurrency",
        "title": "Transaction & Concurrency · 事务处理与并发控制",
        "core": "用时间戳给事务与版本排序、用锁/校验解决写冲突：读走快照不阻塞写，写靠仲裁点原子成败。",
        "color": "#8a5cae", "eco": "事务并发_00生态架构.svg",
        "groups": [
            {"algo": "MVCC / 快照隔离", "mechs": [
                {"n": "M1", "title": "快照可见性判定", "svg": "事务并发_01快照可见性.svg"},
                {"n": "M2", "title": "SSI 危险结构检测", "svg": "事务并发_M2SSI.svg"},
            ]},
            {"algo": "2PL 悲观锁", "mechs": [
                {"n": "L1", "title": "两阶段锁 + 死锁检测", "svg": "事务并发_L1两阶段锁.svg"},
            ]},
            {"algo": "OCC 乐观", "mechs": [
                {"n": "O1", "title": "验证阶段冲突检测", "svg": "事务并发_03乐观验证.svg"},
            ]},
            {"algo": "分布式提交", "mechs": [
                {"n": "D1", "title": "Percolator 两阶段提交", "svg": "事务并发_02两阶段提交.svg"},
            ]},
        ],
        "compare": {"svg": "事务并发_CMP算法对比.svg"},
        "eng": {"svg": "事务并发_ENG工程对比.svg"},
    },
    {
        "slug": "storage", "cn": "存储引擎",
        "en": "Storage Engine",
        "title": "Storage Engine · 存储引擎与物理数据布局",
        "core": "介质的顺序快、随机慢决定布局：写走追加换顺序 IO，代价是后台合并的写放大与读放大平衡。",
        "color": "#2f9e6e", "eco": "存储引擎_00生态架构.svg",
        "groups": [
            {"algo": "LSM-tree", "mechs": [
                {"n": "S1", "title": "Compaction 写放大与 L0 停顿", "svg": "存储引擎_01写放大.svg"},
            ]},
            {"algo": "B-link tree", "mechs": [
                {"n": "S2", "title": "无锁页分裂（兄弟指针）", "svg": "存储引擎_02无锁分裂.svg"},
            ]},
            {"algo": "列存 / 向量", "mechs": [
                {"n": "S3", "title": "压缩管线 + SIMD 下推", "svg": "存储引擎_03列存压缩.svg"},
            ]},
        ],
        "compare": {"svg": "存储引擎_CMP算法对比.svg"},
        "eng": {"svg": "存储引擎_ENG工程对比.svg"},
    },
    {
        "slug": "query", "cn": "查询引擎",
        "en": "Query Engine",
        "title": "Query Engine · 查询优化与执行引擎",
        "core": "声明式查询先被优化器在计划空间里搜到代价最小的形状，再由执行器以向量化 / JIT 榨干 CPU。",
        "color": "#d98a00", "eco": "查询引擎_00生态架构.svg",
        "groups": [
            {"algo": "优化器", "mechs": [
                {"n": "Q1", "title": "Join Reorder 自底向上 DP", "svg": "查询引擎_01连接重排.svg"},
            ]},
            {"algo": "向量化执行", "mechs": [
                {"n": "Q2", "title": "列批 + SIMD", "svg": "查询引擎_02向量化.svg"},
            ]},
            {"algo": "JIT 编译", "mechs": [
                {"n": "Q3", "title": "表达式树编译为 IR", "svg": "查询引擎_03JIT编译.svg"},
            ]},
        ],
        "compare": {"svg": "查询引擎_CMP算法对比.svg"},
        "eng": {"svg": "查询引擎_ENG工程对比.svg"},
    },
    {
        "slug": "netio", "cn": "网络IO",
        "en": "Network I/O",
        "title": "Network I/O · 高性能网络 I/O 与协议栈",
        "core": "数据面绕开内核拷贝把字节直送用户态；控制面用带标签 / 偏移的协议做前后兼容，多路复用摊薄连接。",
        "color": "#2aa0a4", "eco": "网络IO_00生态架构.svg",
        "groups": [
            {"algo": "内核旁路零拷贝", "mechs": [
                {"n": "N1", "title": "DPDK 用户态 DMA 与 mbuf", "svg": "网络IO_01零拷贝.svg"},
            ]},
            {"algo": "异步 I/O 模型", "mechs": [
                {"n": "N2", "title": "epoll 就绪 vs io_uring 完成", "svg": "网络IO_N2异步模型.svg"},
            ]},
            {"algo": "HTTP/2 传输", "mechs": [
                {"n": "N3", "title": "流复用 + 双层流控", "svg": "网络IO_03多路复用.svg"},
            ]},
            {"algo": "序列化", "mechs": [
                {"n": "N4", "title": "标签号 vs 偏移表", "svg": "网络IO_02序列化兼容.svg"},
            ]},
        ],
        "compare": {"svg": "网络IO_CMP算法对比.svg"},
        "eng": {"svg": "网络IO_ENG工程对比.svg"},
    },
    {
        "slug": "osmem", "cn": "内存调度",
        "en": "OS Memory & Scheduling",
        "title": "OS Memory & Scheduling · 操作系统内存管理与资源调度",
        "core": "页表把虚拟地址翻译成物理页、TLB 做缓存；分配器分层供给物理页，cgroup 用水位线把资源关进笼子。",
        "color": "#c4562f", "eco": "内存调度_00生态架构.svg",
        "groups": [
            {"algo": "地址翻译", "mechs": [
                {"n": "V1", "title": "页表 walk / TLB / 缺页", "svg": "内存调度_01缺页TLB.svg"},
            ]},
            {"algo": "物理页分配", "mechs": [
                {"n": "V2", "title": "伙伴系统 + Slab 链路", "svg": "内存调度_02分配器.svg"},
            ]},
            {"algo": "资源隔离", "mechs": [
                {"n": "V3", "title": "cgroup 水位线与 OOM", "svg": "内存调度_03cgroup水位.svg"},
            ]},
        ],
        "compare": {"svg": "内存调度_CMP算法对比.svg"},
        "eng": {"svg": "内存调度_ENG工程对比.svg"},
    },
]

# ===================================================================== #
# 二、文件读取 / base64 内联 / markdown 行内
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
    # [title](http…) → 权威参考链接（新窗口打开）
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
    """读取 <cn>.md，按任意 @marker 分节（@eco / @r1 / @cmp / @refs …），返回 dict。
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
# 三、页面模板：CSS（双主题 graphite / light）+ JS（记忆切换）
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

/* ---- 门户 hero ---- */
.hero{margin:6px 0 26px}
.hero h1{font-size:26px;font-weight:800;letter-spacing:.2px}
.hero .sub{margin-top:8px;font-size:13.5px;color:var(--c-ink2);max-width:820px}
.hero .back{display:inline-flex;align-items:center;gap:6px;margin-bottom:14px;
  font-size:12.5px;color:var(--c-ink2);border:1px solid var(--c-line);
  border-radius:999px;padding:5px 13px;background:var(--c-panel)}
.hero .back:hover{color:var(--c-ink);border-color:var(--c-edge)}

/* ---- 门户卡片栅格 ---- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px}
.card{position:relative;display:block;background:var(--c-card);border:1px solid var(--c-line);
  border-radius:16px;padding:20px 20px 18px;overflow:hidden;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}
.card:hover{transform:translateY(-3px);border-color:var(--acc);box-shadow:0 10px 30px var(--c-shadow)}
.card .bar{position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--acc)}
.card .k{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.6px;
  color:var(--acc);text-transform:uppercase;margin-bottom:8px}
.card h3{font-size:17px;font-weight:750;line-height:1.35;color:var(--c-ink)}
.card .core{margin-top:9px;font-size:12.5px;color:var(--c-ink2);line-height:1.6}
.card .tags{margin-top:14px;display:flex;flex-direction:column;gap:7px}
.card .tag{display:flex;gap:8px;align-items:baseline;font-size:12px;color:var(--c-ink2)}
.card .tag .n{font-weight:800;color:var(--acc);flex:none;font-variant-numeric:tabular-nums}
.card .go{margin-top:16px;font-size:12px;font-weight:700;color:var(--acc);display:inline-flex;align-items:center;gap:5px}

/* ---- 主题页 ---- */
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
# 四、门户 index.html
# ===================================================================== #
def build_portal():
    cards = []
    for th in THEMES:
        tags = "".join(
            '<div class="tag"><span class="n">%s</span><span>%s</span></div>'
            % (esc(g["algo"]), esc("·".join(m["title"] for m in g["mechs"])[:22]))
            for g in th.get("groups", []))
        # 判型式主标题里「·」前段作为卡片标题，核心一句取 core
        head = th["title"].split(" · ")[0]
        kicker = th["slug"].upper()
        cards.append(
            '<a class="card" href="%s/index.html" style="--acc:%s">'
            '<span class="bar"></span>'
            '<span class="k">%s</span>'
            '<h3>%s</h3>'
            '<div class="core">%s</div>'
            '<div class="tags">%s</div>'
            '<div class="go">进入主题页 →</div>'
            '</a>'
            % (esc(th["slug"]), esc(th["color"]), esc(kicker),
               esc(head), esc(th["core"]), tags))
    body = """%s
<header>
  <a class="logo" href="../index.html" title="返回项目图谱"><span class="icobtn">%s</span></a>
  <div class="brand-intro">
    <div class="bt">主题图谱 · 计算系统核心机理</div>
    <div class="bs">按主题（而非项目）组织的概念层导航：每个主题一张生态架构总图 + 3 个机理图解点</div>
  </div>
  <div class="spacer"></div>
  %s
</header>
<div class="wrap">
  <div class="hero">
    <a class="back" href="../index.html">← 返回项目图谱</a>
    <h1>主题图谱门户</h1>
    <div class="sub">从「按项目」切到「按主题」的横向视角：抽掉具体实现，只看一类核心逻辑在整个计算系统中如何自洽地拼起来。共 %d 个主题，每个主题 = 1 张生态架构总图 + 3 个图解点机理图（以图为主，散文为辅注）。</div>
  </div>
  <div class="grid">
    %s
  </div>
</div>
<footer>自包含离线图谱 · 概念层机理（不点名具体项目）· 仅标准库生成 · SVG 全部 base64 内联</footer>
<script>%s</script>
</body>
</html>""" % (_head("主题图谱门户 · 计算系统核心机理"), _HOME_SVG, _THEME_BTN,
              len(THEMES), "\n    ".join(cards), APP_JS)
    return body


# ===================================================================== #
# 五、主题页 <slug>/index.html
# ===================================================================== #
def build_theme_page(th):
    prose = parse_prose(th["slug"], th["cn"])
    acc = th["color"]

    def fig(fname, alt):
        b64 = _b64_svg(th["slug"], fname)
        if not b64:
            return '<div class="miss">机理图待绘制：%s</div>' % esc(fname)
        return ('<div class="fig"><img alt="%s" src="data:image/svg+xml;base64,%s"/></div>'
                % (esc(alt), b64))

    head = th["title"].split(" · ")[0]

    # ── 垂直 TAB：概览 → 各【算法组】(组内关键机制各一 TAB) → 算法对比 → 底部参考区 ──
    nav_groups = []   # [(group_label, [(sid, badge, label), ...])]
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
    eco_prose = prose.get("eco") or ('<p>%s</p>' % _md_inline(th["core"]))
    nav_groups.append(("概览 Overview", [("sec-eco", "◎", "生态架构总图")]))
    secs.append(
        '<section class="vt-sec active" id="sec-eco" data-sec="sec-eco">'
        '<div class="secttl eco"><span class="badge">◎</span>'
        '<span class="t">生态架构总图 · 这一类核心逻辑如何在计算系统中自洽拼合</span></div>'
        '%s<div class="blurb">%s</div></section>'
        % (fig(th["eco"], head + " 生态架构"), eco_prose))
    first = False

    # 各算法组：组名做 .vt-grp 小标题，组内每个关键机制一个 TAB（机制图 + 短注）
    for gi, grp in enumerate(th.get("groups", [])):
        items = []
        for m in grp["mechs"]:
            sid = "sec-%s" % m["n"].lower()
            items.append((sid, m["n"], esc(m["title"])))
            add_sec(sid, m["n"], "%s · %s" % (grp["algo"], m["title"]),
                    m["svg"], m["n"].lower())
        nav_groups.append(("算法 · %s" % grp["algo"], items))

    # 算法对比（图为主；图难表达处 md 里用表格）
    cmp = th.get("compare") or {}
    if cmp.get("svg"):
        nav_groups.append(("对比 Compare", [("sec-cmp", "⇄", "算法差异对比")]))
        add_sec("sec-cmp", "⇄", head + " · 算法核心差异对比", cmp["svg"], "cmp", big=True)

    # 工程实现差异（跨真实项目：同一算法在不同系统里的落地取舍；图为主 + @eng 注解）
    eng = th.get("eng") or {}
    if eng.get("svg") or prose.get("eng"):
        nav_groups.append(("工程 Engineering", [("sec-eng", "⚙", "项目实现差异")]))
        add_sec("sec-eng", "⚙", head + " · 工程实现差异（真实项目落地取舍）",
                eng.get("svg"), "eng", big=True)

    # 底部统一「参考文献」区（常驻，不属任何 TAB）
    refs_html = ""
    if prose.get("refs"):
        refs_html = ('<section class="refs"><div class="secttl"><span class="badge">§</span>'
                     '<span class="t">参考文献 · 权威来源（论文 / 官方文档 / RFC）</span></div>'
                     '<div class="blurb reflist">%s</div></section>' % prose["refs"])

    nav_parts = []
    for glabel, items in nav_groups:
        nav_parts.append('<div class="vt-grp">%s</div>' % esc(glabel))
        for sid, badge, label in items:
            nav_parts.append(
                '<button class="vt-tab" data-target="%s"><span class="vt-b">%s</span>'
                '<span class="vt-l">%s</span></button>' % (sid, esc(badge), label))
    # 首个 TAB 高亮
    navcol = "".join(nav_parts).replace('class="vt-tab" data-target="sec-eco"',
                                        'class="vt-tab active" data-target="sec-eco"', 1)

    drill = ('<div class="vt-wrap">'
             '<nav class="vt-nav" aria-label="主题内容切换">%s</nav>'
             '<div class="vt-stage">%s</div></div>'
             % (navcol, "".join(secs)))

    body = """%s
<header>
  <a class="logo" href="../index.html" title="返回主题门户"><span class="icobtn">%s</span></a>
  <div class="brand-intro">
    <div class="bt">%s</div>
    <div class="bs">主题图谱 · 概念层机理（不点名具体项目）</div>
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
  <div class="backrow"><a href="../index.html">← 返回主题门户</a></div>
</div>
<footer>自包含离线图谱 · 以图为主：概览 + 算法分组机制图 + 算法对比 · 权威参考集中于底部 · 垂直 TAB 切换</footer>
<script>%s</script>
</body>
</html>""" % (_head(head + " · 主题图谱"), _HOME_SVG, esc(head), _THEME_BTN, esc(acc),
              esc(th["slug"].upper()), th["title"], esc(th["core"]),
              drill, refs_html, APP_JS)
    return body


# ===================================================================== #
# 六、主流程
# ===================================================================== #
def main():
    # 门户
    portal_path = os.path.join(HERE, "index.html")
    with open(portal_path, "w", encoding="utf-8") as f:
        f.write(build_portal())
    print("Wrote %s" % portal_path)

    # 各主题页
    for th in THEMES:
        d = os.path.join(HERE, th["slug"])
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_theme_page(th))
        print("Wrote %s" % out)

    print("主题 %d 个 · 门户 1 + 主题页 %d" % (len(THEMES), len(THEMES)))
    if _missing:
        print("  ⚠ 缺失 SVG（%d）：" % len(_missing))
        for m in _missing:
            print("      -", m)
    else:
        print("  ✓ 全部 24 张 SVG 就位，无缺失")


if __name__ == "__main__":
    main()
