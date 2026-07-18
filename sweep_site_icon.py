#!/usr/bin/env python3
"""一次性 sweep:把每个项目页顶栏 site-link 里硬编码的字母标 base64
替换成该项目 design/icon.svg 的真实 base64(官方/品牌图标)。幂等、只读校验后写。"""
import glob, os, re, base64

ROOT = os.path.dirname(os.path.abspath(__file__))
pat = re.compile(r'(<img src="data:image/svg\+xml;base64,)([^"]*)(")([^>]*alt="官网"[^>]*/?>)')
changed, skipped = [], []
for g in sorted(glob.glob(os.path.join(ROOT, "*-design/gen.py"))):
    d = os.path.dirname(g); key = os.path.basename(d)[:-7]
    icon = os.path.join(d, "design", "icon.svg")
    if not os.path.isfile(icon):
        skipped.append(key + "(no icon.svg)"); continue
    b64 = base64.b64encode(open(icon, "rb").read()).decode("ascii")
    t = open(g, encoding="utf-8").read()
    m = pat.search(t)
    if not m:
        skipped.append(key + "(no header img)"); continue
    if m.group(2) == b64:
        skipped.append(key + "(already ok)"); continue
    t2 = t[:m.start(2)] + b64 + t[m.end(2):]
    open(g, "w", encoding="utf-8").write(t2)
    changed.append(key)
print("changed(%d): %s" % (len(changed), " ".join(changed)))
print("skipped(%d): %s" % (len(skipped), " ".join(skipped)))
