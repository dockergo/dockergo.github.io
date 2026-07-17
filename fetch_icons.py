#!/usr/bin/env python3
"""站点级图标抓取器 —— 为每个 <xxx>-design/ 拉取品牌图标存入 design/icon.svg。

与 gen.py 的关系(职责分离,勿混):
· 本脚本是**唯一联网**的一步:从 simple-icons CDN 拉取单文件矢量品牌图标,写入
  <key>-design/design/icon.svg。矢量(非位图头像)→ 可无损缩放、可被 CSS 变量重着色。
· gen.py 恒离线(仅标准库、零网络):只把已存在的 design/icon.svg base64 内联进导航图。
  因此本脚本可择时单独跑;跑不跑都不影响 gen.py 出图(缺图标自动回退首字母 tile)。

泛化(新增项目零改代码即可尝试):
· 目录名 <key>-design → 先查 SLUG 显式映射,再退到 key 本身当 slug 猜测。
· 命中(HTTP 200)才写盘;未命中留空,gen.py 回退精修首字母 tile。
· --force 覆盖已存在图标;默认跳过已存在的,便于增量补齐。

用法:
  python3 fetch_icons.py                # 增量:仅补缺失
  python3 fetch_icons.py --force        # 全量重拉
  python3 fetch_icons.py --only redis   # 只处理某项目
  python3 fetch_icons.py --list         # 只打印将要拉取的 key→slug 映射,不联网
"""
from __future__ import annotations
import argparse
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = "-design"
CDN = "https://cdn.simpleicons.org/{slug}"
UA = {"User-Agent": "Mozilla/5.0 (compatible; atlas-icon-fetch/1.0)"}

# ── 目录 key → simple-icons slug(仅需登记与目录名不一致者;一致的可省)──
# 未登记的项目:先试 key 本身,失败则跳过(gen.py 回退首字母 tile)。
SLUG = {
    "doris": "apachedoris", "spark": "apachespark", "flink": "apacheflink",
    "fluss": "apacheflink",          # Fluss 属 Flink 生态,借用其标识
    "postgres": "postgresql", "hadoop": "apachehadoop", "kafka": "apachekafka",
    "spring-boot": "springboot", "traefik": "traefikproxy",
    "quic-go": "go",                 # QUIC 的 Go 实现
    "quiche": "cloudflare",          # Cloudflare 的 QUIC 实现
    # 已知 simple-icons 无收录 → 显式置空,直接走首字母 tile,省一次联网探测:
    "iceberg": "", "hudi": "", "orc": "", "starrocks": "",
    "zookeeper": "", "raft": "", "gorm": "",
    # 注:上面 7 个 simple-icons 无收录。其中 3 个方形 brandmark 已手工从官方源取真 logo
    # 存入各 design/icon.svg(本抓取器不覆盖已存在文件,故手工 logo 安全):
    #   orc       ← vectorlogo.zone/logos/apache_orc(64×64 方形)
    #   zookeeper ← vectorlogo.zone/logos/apache_zookeeper(近方形)
    #   starrocks ← StarRocks/starrocks: docs/docusaurus/static/img/logo.svg(54×62)
    # 另 4 个是宽版 wordmark / banner / 无 logo,在 34px 方 tile 里会糊成细条,
    # 故保留精修首字母 tile(iceberg/gorm/hudi 宽标;raft 协议无 logo)。
}


def discover_keys():
    keys = []
    for entry in sorted(os.listdir(HERE)):
        full = os.path.join(HERE, entry)
        if entry.endswith(SUFFIX) and os.path.isdir(full):
            keys.append(entry[: -len(SUFFIX)].strip())
    return keys


def slug_for(key):
    """key → slug。显式映射优先(含显式置空);否则猜 key 本身。"""
    if key in SLUG:
        return SLUG[key]           # 可能是 ""(明确无图标)
    return key.lower()


def fetch(slug):
    url = CDN.format(slug=slug)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        if r.getcode() != 200:
            return None
        data = r.read()
    if not data.lstrip().startswith(b"<svg"):
        return None
    return data.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description="为各 <xxx>-design/ 抓取品牌图标到 design/icon.svg")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 icon.svg")
    ap.add_argument("--only", metavar="KEY", help="只处理某个项目 key(如 redis)")
    ap.add_argument("--list", action="store_true", help="只打印 key→slug 映射,不联网")
    args = ap.parse_args()

    keys = discover_keys()
    if args.only:
        keys = [k for k in keys if k == args.only]
        if not keys:
            print(f"未找到项目:{args.only}-design", file=sys.stderr)
            sys.exit(1)

    if args.list:
        for k in keys:
            s = slug_for(k)
            print(f"  {k:14} → {s or '(首字母 tile)'}")
        return

    got = skip = tile = fail = 0
    for key in keys:
        proj = os.path.join(HERE, f"{key}{SUFFIX}")
        if not os.path.isdir(proj):
            continue
        # 图标存到 <key>-design/design/icon.svg(项目 design/ 内,符合约定)。
        # 若 design/ 不存在则创建;gen.py 的状态判定只看真实图/文档数(图标已排除),
        # 因此仅含 icon.svg 的 design/ 不会把"规划中"项目误翻成"资源"。
        design = os.path.join(proj, "design")
        os.makedirs(design, exist_ok=True)
        out = os.path.join(design, "icon.svg")
        slug = slug_for(key)
        if not slug:
            tile += 1
            print(f"○ {key:14} 无 slug → 首字母 tile")
            continue
        if os.path.exists(out) and not args.force:
            skip += 1
            print(f"= {key:14} 已存在,跳过(--force 覆盖)")
            continue
        try:
            svg = fetch(slug)
        except Exception as e:
            svg = None
            print(f"✗ {key:14} 拉取异常({slug}):{type(e).__name__}", file=sys.stderr)
        if svg:
            with open(out, "w", encoding="utf-8") as f:
                f.write(svg)
            got += 1
            print(f"✓ {key:14} ← simpleicons/{slug}  ({len(svg)}B)")
        else:
            fail += 1
            print(f"✗ {key:14} 未命中({slug}) → 首字母 tile")

    print(f"\n汇总:新增 {got} · 跳过 {skip} · 无 slug {tile} · 未命中 {fail}")
    print("下一步:重跑 python3 gen.py 让导航图内联新图标。")


if __name__ == "__main__":
    main()
