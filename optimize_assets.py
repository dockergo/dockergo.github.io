#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物后处理:把内联 base64 svg 抽为外部 .svg 文件(哈希去重)并改外链;
   把各页 <style> 按内容分组抽为外部 .css 共享文件。
   不改动任何 gen.py 生成逻辑,纯二次加工产物,可回滚(重跑 gen.py 恢复)。

   仅对解码后 >= INLINE_MAX_BYTES(默认 4096)的大图外链;小图标保持内联,
   避免首页等页面数十个小图标各自外链造成上百个碎片化 HTTP 请求(远程访问反而更慢)。
   可用环境变量 OPTIMIZE_INLINE_MAX_BYTES 覆盖阈值。

用法:
   python3 optimize_assets.py            # 全站
   python3 optimize_assets.py a.html b/  # 仅指定页(验证用)
"""
import re, os, sys, glob, base64, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSET_IMG = os.path.join(ROOT, "assets", "img")
ASSET_CSS = os.path.join(ROOT, "assets", "css")

# 小于此字节数的 svg 保持内联 base64,不外链。
# 原因:小图标(如首页导航图内的 nd-ic,36 个共重复约 148 次)若各自外链,
# 会在每次进入/返回页面时产生上百个额外 HTTP 请求,远程访问 RTT 累加反而更慢。
# 外链只对"大图(走查图/架构图,数 KB~数十 KB)"划算——降体积且跨页缓存。
INLINE_MAX_BYTES = int(os.environ.get("OPTIMIZE_INLINE_MAX_BYTES", "4096"))

# data:image/svg+xml;base64,XXXX  —— 覆盖 <image href=> 与 <img src=>
B64_RE = re.compile(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)')
STYLE_RE = re.compile(r'<style([^>]*)>(.*?)</style>', re.S)


def rel_to(page_path, target_abs):
    """从页面所在目录到目标文件的相对路径(posix 斜杠)。"""
    page_dir = os.path.dirname(os.path.abspath(page_path))
    rel = os.path.relpath(target_abs, page_dir)
    return rel.replace(os.sep, "/")


def collect_pages(args):
    if not args:
        return sorted(glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True))
    pages = []
    for a in args:
        p = os.path.join(ROOT, a) if not os.path.isabs(a) else a
        if os.path.isdir(p):
            pages += glob.glob(os.path.join(p, "**", "*.html"), recursive=True)
        elif p.endswith(".html"):
            pages.append(p)
    return sorted(set(pages))


def inline_small_images(pages):
    """逆向:把已外链且 < INLINE_MAX_BYTES 的小图标重新内联回 base64。
       用于修正历史产物(小图标曾被无差别外链导致碎片化请求)。
       匹配 <image href="..."> 与 <img src="..."> 中指向 assets/img/*.svg 的引用。"""
    # href/src = "(可能带 ../ 前缀).../assets/img/<name>.svg"
    ref_re = re.compile(r'((?:href|src)=")((?:[^"]*/)?assets/img/([^"/]+\.svg))(")')
    cache = {}  # svg abs path -> (is_small, b64str or None)

    def load(name):
        if name in cache:
            return cache[name]
        abs_p = os.path.join(ASSET_IMG, name)
        try:
            raw = open(abs_p, "rb").read()
        except Exception:
            cache[name] = (False, None)
            return cache[name]
        if len(raw) < INLINE_MAX_BYTES:
            b64 = base64.b64encode(raw).decode("ascii")
            cache[name] = (True, "data:image/svg+xml;base64," + b64)
        else:
            cache[name] = (False, None)
        return cache[name]

    stats = {"pages": 0, "refs": 0}
    for pg in pages:
        html = open(pg, encoding="utf-8").read()
        cnt = [0]

        def repl(m):
            name = m.group(3)
            is_small, data = load(name)
            if not is_small:
                return m.group(0)
            cnt[0] += 1
            return m.group(1) + data + m.group(4)

        new = ref_re.sub(repl, html)
        if new != html:
            open(pg, "w", encoding="utf-8").write(new)
            stats["pages"] += 1
            stats["refs"] += cnt[0]
    return stats


def extract_base64_images(pages):
    """一次遍历,建立 base64 -> 外部文件名(哈希) 的全站共享映射并落盘。
       仅对解码后 >= INLINE_MAX_BYTES 的大图外链;小图标保持内联(不入 mapping)。"""
    os.makedirs(ASSET_IMG, exist_ok=True)
    mapping = {}   # b64str -> abs svg path
    skipped_small = 0
    for pg in pages:
        html = open(pg, encoding="utf-8").read()
        for b64 in set(B64_RE.findall(html)):
            if b64 in mapping:
                continue
            try:
                raw = base64.b64decode(b64)
            except Exception:
                continue
            if len(raw) < INLINE_MAX_BYTES:
                skipped_small += 1
                continue  # 小图标保持内联,避免碎片化 HTTP 请求
            h = hashlib.sha1(raw).hexdigest()[:16]
            fn = os.path.join(ASSET_IMG, h + ".svg")
            if not os.path.exists(fn):
                with open(fn, "wb") as f:
                    f.write(raw)
            mapping[b64] = fn
    if skipped_small:
        print("小图标保持内联(< %d 字节): %d 个唯一" % (INLINE_MAX_BYTES, skipped_small))
    return mapping


def rewrite_images(pages, mapping):
    """把每页 data:...base64 引用替换为外链相对路径; <img> 追加 loading=lazy。"""
    stats = {"pages": 0, "refs": 0}
    for pg in pages:
        html = open(pg, encoding="utf-8").read()
        cnt = [0]

        def repl(m):
            b64 = m.group(1)
            tgt = mapping.get(b64)
            if not tgt:
                return m.group(0)
            cnt[0] += 1
            return rel_to(pg, tgt)

        new = B64_RE.sub(repl, html)
        # 给替换后的 <img ... src="assets/..."> 补 loading=lazy(若无)
        new = re.sub(
            r'(<img\b(?![^>]*\bloading=)[^>]*\bsrc="[^"]*assets/img/[^"]+")',
            r'\1 loading="lazy"', new)
        if new != html:
            open(pg, "w", encoding="utf-8").write(new)
            stats["pages"] += 1
            stats["refs"] += cnt[0]
    return stats


def extract_css(pages):
    """各页 <style> 按内容哈希分组抽出为外部 .css,页面内改为 <link>。"""
    os.makedirs(ASSET_CSS, exist_ok=True)
    stats = {"pages": 0, "files": set()}
    for pg in pages:
        html = open(pg, encoding="utf-8").read()
        styles = STYLE_RE.findall(html)
        if not styles:
            continue
        # 合并该页所有 <style> 内容作为一份(通常仅1个)
        css_text = "\n".join(s[1] for s in styles)
        h = hashlib.sha1(css_text.encode("utf-8")).hexdigest()[:16]
        css_abs = os.path.join(ASSET_CSS, h + ".css")
        if not os.path.exists(css_abs):
            open(css_abs, "w", encoding="utf-8").write(css_text)
        stats["files"].add(h)
        href = rel_to(pg, css_abs)
        link = '<link rel="stylesheet" href="%s"/>' % href
        # 用一个 <link> 替换第一个 <style>,删除其余 <style>
        first = [True]

        def repl(m):
            if first[0]:
                first[0] = False
                return link
            return ""

        new = STYLE_RE.sub(repl, html)
        if new != html:
            open(pg, "w", encoding="utf-8").write(new)
            stats["pages"] += 1
    return stats


def clean_assets():
    """全站生成前清理 assets/img、assets/css 下旧产物,避免历史 hash 文件堆积。
       仅在全站运行(无命令行参数)时调用:此时会对所有页重新抽取,旧文件必被新产物覆盖或废弃;
       带参数只处理指定页时不清理,否则会误删其他页仍在引用的共享文件。
       文件级删除(os.remove),不删目录本身。"""
    removed = 0
    for d, pat in ((ASSET_IMG, "*.svg"), (ASSET_CSS, "*.css")):
        for f in glob.glob(os.path.join(d, pat)):
            try:
                os.remove(f)
                removed += 1
            except Exception:
                pass
    if removed:
        print("清理 assets 旧产物: 删除 %d 个历史文件" % removed)


def main():
    pages = collect_pages(sys.argv[1:])
    print("处理页面数:", len(pages))
    if not sys.argv[1:]:
        # 仅全站运行时清理,避免历史 hash 产物堆积
        clean_assets()
    inl = inline_small_images(pages)
    print("小图标内联回 base64: %d 页, %d 处引用" % (inl["pages"], inl["refs"]))
    mapping = extract_base64_images(pages)
    print("全站唯一 base64 图 -> 外部 svg 文件:", len(mapping))
    ist = rewrite_images(pages, mapping)
    print("图外链改写: %d 页, %d 处引用" % (ist["pages"], ist["refs"]))
    cst = extract_css(pages)
    print("CSS 抽离: %d 页 -> %d 个共享 css" % (cst["pages"], len(cst["files"])))


if __name__ == "__main__":
    main()