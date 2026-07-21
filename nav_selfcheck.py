#!/usr/bin/env python3
"""全站项目页导航合规 + 架构图热区对齐自检（只读）。

判据（对每个 <name>-design/ 项目）：
  1. 导航合规：生成的 index.html 里 arch-hot > 0（架构图上有可点热区）、
     无 legacy 卡片/树/切换（tcard / tree-node / tree-leaf / nav-seg）。
  2. 克隆无残留：gen.py 里不得残留任何克隆源项目名（Iceberg/Quiche/…），
     PANO_NAME/ARCH_SVG_NAME 必须是本项目名。
  3. viewBox 对齐：wrap 族 ARCH_W×ARCH_H 必须逐字节等于架构 SVG 的 viewBox；
     doris 族百分比除数同理（此脚本对 wrap 族做强断言，doris 族只提示）。
  4. 架构底图存在：ARCH_SVG_NAME 指向的 svg 在 design/ 里真实存在。

用法：python3 nav_selfcheck.py [supports根目录，默认脚本同级]
退出码：全绿 0；任何 FAIL 非 0。
"""
import os, re, sys, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
# 已知克隆源项目名（出现在别的项目 gen.py 里即残留）
CLONE_SOURCES = ["Iceberg", "Quiche", "iceberg", "quiche"]

def check(proj_dir):
    b = os.path.basename(proj_dir)
    key = b[:-7] if b.endswith("-design") else b
    gen = os.path.join(proj_dir, "gen.py")
    ix = os.path.join(proj_dir, "index.html")
    fails = []
    if not os.path.isfile(gen):
        return key, ["no gen.py"]
    g = open(gen, encoding="utf-8").read()

    # 判据 2：克隆残留 —— 只查配置标识符（不查正文；正文可合法提及别的项目名，如 doris 讲 Iceberg 表格式）
    #   配置标识 = 生成器 docstring 首行、PANO_NAME、ARCH_SVG_NAME、localStorage key、argparse env 前缀。
    cfg_ids = []
    m = re.search(r'"""(\S+)-design 交互式', g);            cfg_ids.append(("docstring", m.group(1) if m else ""))
    m = re.search(r'PANO_NAME\s*=\s*"([^"]+)"', g);          cfg_ids.append(("PANO_NAME", m.group(1) if m else ""))
    m = re.search(r'ARCH_SVG_NAME\s*=\s*"([^"]+)"', g);      cfg_ids.append(("ARCH_SVG_NAME", m.group(1) if m else ""))
    m = re.search(r"localStorage\.getItem\('([^']+)-atlas-theme'\)", g); cfg_ids.append(("localStorage", m.group(1) if m else ""))
    for src in CLONE_SOURCES:
        if src.lower() == key.lower():
            continue
        hit = [name for name, val in cfg_ids if val and src.lower() in val.lower()]
        if hit:
            fails.append(f"clone-residue-in-config:{src}@{'/'.join(hit)}")

    # 判据 1：生成产物合规 —— 数“渲染出的 nav 元素”，不数 CSS/JS 里的类名定义
    t = ""
    if os.path.isfile(ix):
        t = open(ix, encoding="utf-8").read()
        if t.count('class="arch-hot"') == 0:
            fails.append("arch-hot=0 (架构图无热区)")
        if "缺项目总架构图" in t or "缺总架构" in t:
            fails.append("缺项目总架构图 (底图未内联)")
        for legacy in ["tcard", "tree-node", "tree-leaf", "nav-seg"]:
            # 只匹配真正作为元素 class 渲染的（<... class="...legacy...">），排除 CSS 规则 / JS 字符串
            n = len(re.findall(r'<[^>]*class="[^"]*\b' + legacy + r'\b[^"]*"', t))
            if n:
                fails.append(f"legacy-rendered:{legacy}×{n}")
    else:
        fails.append("no index.html")

    # 判据 4b：热区容器无内边距（padding 会把底图推偏，热区百分比错位——见坑 C.5）
    mp = re.search(r'\.arch-wrap\{[^}]*?padding:\s*([0-9]+)px', g)
    if mp and mp.group(1) != "0":
        fails.append(f".arch-wrap padding:{mp.group(1)}px≠0 (热区会错位)")

    # 判据 3：wrap 族 ARCH_W×H == svg viewBox
    mw = re.search(r'ARCH_W,\s*ARCH_H\s*=\s*(\d+),\s*(\d+)', g)
    mn = re.search(r'ARCH_SVG_NAME\s*=\s*"([^"]+)"', g)
    if mw and mn:
        W, H = mw.group(1), mw.group(2)
        svg = os.path.join(proj_dir, "design", mn.group(1))
        # 判据 4：底图存在
        if not os.path.isfile(svg):
            fails.append(f"arch-svg missing:{mn.group(1)}")
        else:
            st = open(svg, encoding="utf-8").read()
            vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', st)
            if vb and (vb.group(1), vb.group(2)) != (W, H):
                fails.append(f"viewBox mismatch: decl {W}x{H} vs svg {vb.group(1)}x{vb.group(2)}")

    # 判据 5：主线→可达 —— 每条 MAINLINES 主线都被某热区或 ALWAYS_CHIP 覆盖（否则架构图入口"失联"）
    mains = set(re.findall(r'\(\s*"([^"]+原理[^"]*)"\s*,\s*"(?:pano|iface|support)"', g))
    # 兼容"热区自动派生"：以产物 index.html 实际渲染的 data-theme-id（热区+chip）判定覆盖，
    # 不再仅依赖 gen.py 源码里的静态 ARCH_HOTSPOTS 列表（派生后已无此列表）。
    chip_block = re.search(r'ARCH_ALWAYS_CHIP\s*=\s*\[(.*?)\]', g, re.S)
    covered = set(re.findall(r'data-(?:theme-id|mid|k|tid)="([^"]+原理[^"]*)"', t))
    hs_block = re.search(r'ARCH_HOTSPOTS\s*=\s*\[(.*?)\]\s*\n', g, re.S)
    if hs_block:
        covered |= set(re.findall(r'"([^"]+原理[^"]*)"', hs_block.group(1)))
    if chip_block:
        covered |= set(re.findall(r'"([^"]+原理[^"]*)"', chip_block.group(1)))
    lost = (mains - covered) if t else set()
    if lost:
        fails.append(f"失联主线×{len(lost)}:{','.join(sorted(lost))[:60]}")
    return key, fails

def check_portal(root, proj_keys):
    """一级门户自检:每个可构建项目 ∈ ≥1 lens tier(防 grpc 式静默掉出);
    每个 lens 引用的项目有真 index.html(无死链)。读根 gen.py 的 LENSES。"""
    fails = []
    rg = os.path.join(root, "gen.py")
    if not os.path.isfile(rg):
        return ["portal: no root gen.py"]
    s = open(rg, encoding="utf-8").read()
    if "LENSES" not in s:
        return []  # 非多视角门户,跳过
    # 只取 LENSES 区(到 TOPICS 前),避免把 TOPICS 的 projects 列表误当 lens 项目
    _l0 = s.index("LENSES")
    _l1 = s.index("TOPICS", _l0) if "TOPICS" in s[_l0:] else len(s)
    lr = s[_l0:_l1]
    lens_keys = set()
    for grp in re.findall(r'\(\s*"[a-z_]+"\s*,[^\[]*\[([^\]]*)\]', lr):
        lens_keys |= set(re.findall(r'"([a-z0-9-]+)"', grp))
    lens_keys -= {"id", "runtime", "stack"}
    lens_lower = {k.lower() for k in lens_keys}
    # (1) 孤儿:可构建项目不在任何 lens
    orphans = sorted(k for k in proj_keys if k.lower() not in lens_lower)
    if orphans:
        fails.append(f"portal 孤儿×{len(orphans)}(不在任何 lens):{','.join(orphans)}")
    # (2) 死链:lens 引用项目无 index.html(兼容 projects/<name>/ 新布局 + <name>-design/ 旧布局)
    proot = os.path.join(root, "projects")
    def _proj_idx(k):
        for cand in (os.path.join(proot, k, "index.html"),
                     os.path.join(root, k + "-design", "index.html")):
            if os.path.isfile(cand):
                return cand
        return None
    for k in sorted(lens_keys):
        if not _proj_idx(k):
            fails.append(f"portal 死链:{k} -> 无 index.html")
    # (3) 关系视角(INDUSTRY/STANDARDS/PEOPLE)的 proj 关联键须能下钻(∈ 真实项目)
    rel_projs = set(re.findall(r'"proj":\s*"([a-z0-9-]+)"', s))
    for k in sorted(rel_projs):
        if not _proj_idx(k):
            fails.append(f"portal 关系视角死链:{k} -> 无 index.html")
    return fails


def main():
    # 兼容 projects/<name>/ 新布局(优先)+ 根级 <name>-design/ 旧布局
    proot = os.path.join(ROOT, "projects")
    if os.path.isdir(proot):
        projs = sorted(p for p in glob.glob(os.path.join(proot, "*"))
                       if os.path.isdir(p))
    else:
        projs = sorted(glob.glob(os.path.join(ROOT, "*-design")))
    proj_keys = [os.path.basename(p)[:-7] if p.endswith("-design") else os.path.basename(p)
                 for p in projs if os.path.isfile(os.path.join(p, "gen.py"))]
    bad = 0
    for p in projs:
        key, fails = check(p)
        if fails:
            bad += 1
            print(f"FAIL {key:<14} " + " | ".join(fails))
        else:
            print(f"ok   {key}")
    # 一级门户链路自检
    pf = check_portal(ROOT, proj_keys)
    if pf:
        bad += 1
        for f in pf:
            print(f"FAIL portal        {f}")
    else:
        print("ok   portal (一级:无孤儿/无死链)")
    print(f"\n{'ALL GREEN' if not bad else str(bad)+' PROJECT(S) FAIL'} · {len(projs)} checked")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
