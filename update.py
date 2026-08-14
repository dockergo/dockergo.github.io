#!/usr/bin/env python3
"""一键分层更新:从下到上重建整站图谱。

分两层,顺序固定(下 → 上):
  第 1 层 · 各项目  —— 发现所有含 gen.py 的 *-design/ 子项目,逐个调用其 gen.py,
                      在各自目录内生成/刷新 index.html(自包含交互式图谱)。
  第 2 层 · 整体导航 —— 全部子项目完成后,调用根 gen.py 重新扫描所有 *-design 目录,
                      重建整站主导航 index.html(状态/主题/统计随子项目产物刷新)。

为何分层且自下而上:根导航的卡片状态(ready/assets/plan)、主题 chips、图/篇计数
都是从各子项目目录的实际产物与素材扫描得来。必须先让每个项目的 index.html 与
design/ 处于最新,再重建导航,导航才会反映真实最新状态。

完全自包含:仅用标准库,逐个子进程调用 python3 <gen.py>,不依赖服务器/网络。

用法:
  python3 update.py                  # 全量:先所有项目,后整体导航
  python3 update.py --nav-only       # 只重建整体导航(跳过所有项目 gen.py)
  python3 update.py --only clickhouse doris   # 只更新指定项目(仍会重建导航)
  python3 update.py --skip spark     # 跳过指定项目(其余项目 + 导航照常)
  python3 update.py --list           # 只列出发现的项目与其 gen.py,不执行
  python3 update.py --no-nav         # 只更新项目,不重建导航
  python3 update.py --no-optimize    # 生成后不跑第 3 层资源优化(保留 base64 内联版)

第 3 层 · 资源优化:两层生成完毕后默认跑 optimize_assets.py,把 base64 内联图抽外部
              去重 + 内联 <style> 抽共享 css(降体积、跨页缓存)。纯后处理、可回滚。

退出码:全部成功 0;任一步骤失败 1(失败不中断后续,末尾汇总)。
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = "-design"
ROOT_GEN = os.path.join(HERE, "gen.py")

# ── 颜色(仅 TTY 时启用,避免污染重定向日志) ──
_TTY = sys.stdout.isatty()
def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if _TTY else s
def bold(s):  return _c("1", s)
def green(s): return _c("32", s)
def red(s):   return _c("31", s)
def dim(s):   return _c("2", s)
def cyan(s):  return _c("36", s)


def discover_projects():
    """发现所有含 gen.py 的项目子目录,返回 [(key, dir, gen_path)] 按名排序。
    新结构:projects/<name>/;向后兼容:projects/ 缺失时回退根级 *-design/。
    另把六大一级分层中除 projects/ 外含 gen.py 的分层(basic/topics/
    principles/llm-agent)末位追加,各自单独构建(根 gen.py 只读它们的元数据常量)。"""
    out = []
    proot = os.path.join(HERE, "projects")
    if os.path.isdir(proot):
        base, strip = proot, False
    else:
        base, strip = HERE, True
    for entry in sorted(os.listdir(base)):
        full = os.path.join(base, entry)
        if not os.path.isdir(full):
            continue
        if strip and not entry.endswith(SUFFIX):
            continue
        gen = os.path.join(full, "gen.py")
        if os.path.isfile(gen):
            key = entry[: -len(SUFFIX)] if strip else entry
            out.append((key, full, gen))
    # 六大一级分层中,除 projects/ 外的其余含 gen.py 的门户/模式页作为特殊"项目"末位追加。
    # 根 gen.py 只 import 这些子 gen.py 的元数据常量(不代跑),故它们必须在此各自单独构建,
    # 否则改了其 design 内容后 update.py 不会刷新对应产物。scenarios/ 无 gen.py,不在此列。
    for key in ("basic", "topics", "principles", "llm-agent"):
        g = os.path.join(HERE, key, "gen.py")
        if os.path.isfile(g):
            out.append((key, os.path.join(HERE, key), g))
    return out


def run_gen(gen_path, label):
    """在其所在目录调用一个 gen.py,返回 (ok, seconds, tail)。"""
    cwd = os.path.dirname(gen_path)
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, gen_path],
            cwd=cwd, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, time.time() - t0, "超时(>600s)"
    except Exception as e:  # noqa: BLE001
        return False, time.time() - t0, f"启动失败:{e}"
    dt = time.time() - t0
    ok = proc.returncode == 0
    stream = (proc.stdout or "") + (proc.stderr or "")
    tail = ""
    lines = [ln for ln in stream.splitlines() if ln.strip()]
    if lines:
        tail = lines[-1].strip()
    if not ok and not tail:
        tail = f"退出码 {proc.returncode}"
    return ok, dt, tail


def run_optimize():
    """gen.py 全部生成后,跑根目录 optimize_assets.py 把产物做加载性能后处理:
    内联 base64 svg 抽外部去重 + 内联 <style> 抽共享 css。纯二次加工,可回滚。
    返回 (ok, seconds, tail)。"""
    opt = os.path.join(HERE, "optimize_assets.py")
    if not os.path.isfile(opt):
        return False, 0.0, "缺少 optimize_assets.py"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, opt],
            cwd=HERE, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, time.time() - t0, "超时(>600s)"
    except Exception as e:  # noqa: BLE001
        return False, time.time() - t0, f"启动失败:{e}"
    dt = time.time() - t0
    ok = proc.returncode == 0
    stream = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in stream.splitlines() if ln.strip()]
    tail = lines[-1].strip() if lines else ""
    if not ok and not tail:
        tail = f"退出码 {proc.returncode}"
    return ok, dt, tail


def main():
    ap = argparse.ArgumentParser(
        description="一键分层更新:先各项目 gen.py,后根 gen.py 重建整体导航",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--only", nargs="+", metavar="KEY",
                    help="只更新指定项目(按 key,如 clickhouse doris);仍重建导航")
    ap.add_argument("--skip", nargs="+", metavar="KEY",
                    help="跳过指定项目;其余项目与导航照常")
    ap.add_argument("--nav-only", action="store_true",
                    help="只重建整体导航,跳过所有项目 gen.py")
    ap.add_argument("--no-nav", action="store_true",
                    help="只更新项目,不重建整体导航")
    ap.add_argument("--list", action="store_true",
                    help="只列出发现的项目及其 gen.py,不执行")
    ap.add_argument("--no-optimize", action="store_true",
                    help="跳过第 3 层资源优化(默认生成后跑 optimize_assets.py 抽外链)")
    args = ap.parse_args()

    projects = discover_projects()

    if args.list:
        print(bold(f"发现 {len(projects)} 个含 gen.py 的项目:"))
        for key, d, gen in projects:
            print(f"  · {key:<14} {os.path.relpath(gen, HERE)}")
        no_gen = [
            e[: -len(SUFFIX)] for e in sorted(os.listdir(HERE))
            if e.endswith(SUFFIX) and os.path.isdir(os.path.join(HERE, e))
            and not os.path.isfile(os.path.join(HERE, e, "gen.py"))
        ]
        if no_gen:
            print(dim(f"  (另有 {len(no_gen)} 个 *-design 目录无 gen.py,导航仍会按素材收录:{', '.join(no_gen)})"))
        return 0

    # 选择要跑的项目
    selected = projects
    if args.only:
        want = set(args.only)
        selected = [p for p in projects if p[0] in want]
        missing = want - {p[0] for p in projects}
        if missing:
            print(red(f"⚠ --only 指定但未找到(或无 gen.py):{', '.join(sorted(missing))}"))
    if args.skip:
        skip = set(args.skip)
        selected = [p for p in selected if p[0] not in skip]
    if args.nav_only:
        selected = []

    failures = []
    if args.only:
        for m in sorted(want - {p[0] for p in projects}):
            failures.append(("--only " + m, "未找到该项目或其无 gen.py"))
    t_start = time.time()

    # ── 第 1 层:各项目(自下而上的"下") ──
    if selected:
        print(bold(cyan(f"\n▼ 第 1 层 · 更新 {len(selected)} 个项目\n")))
        for i, (key, d, gen) in enumerate(selected, 1):
            print(f"  [{i}/{len(selected)}] {bold(key)} …", end="", flush=True)
            ok, dt, tail = run_gen(gen, key)
            if ok:
                print(f"\r  [{i}/{len(selected)}] {green('✓')} {bold(key):<22} {dim(f'{dt:.2f}s')}  {dim(tail)}")
            else:
                print(f"\r  [{i}/{len(selected)}] {red('✗')} {bold(key):<22} {dim(f'{dt:.2f}s')}  {red(tail)}")
                failures.append(("项目 " + key, tail))
    elif not args.nav_only:
        print(dim("\n(无匹配项目可更新)"))

    # ── 第 2 层:整体导航(自下而上的"上") ──
    if not args.no_nav:
        print(bold(cyan("\n▲ 第 2 层 · 重建整体导航\n")))
        if not os.path.isfile(ROOT_GEN):
            print(red(f"  ✗ 未找到根 gen.py:{ROOT_GEN}"))
            failures.append(("整体导航", "根 gen.py 缺失"))
        else:
            ok, dt, tail = run_gen(ROOT_GEN, "nav")
            if ok:
                print(f"  {green('✓')} 整体导航 {dim(f'{dt:.2f}s')}  {dim(tail)}")
            else:
                print(f"  {red('✗')} 整体导航 {dim(f'{dt:.2f}s')}  {red(tail)}")
                failures.append(("整体导航", tail))

    # ── 第 3 层:资源优化(把 base64 内联产物抽外链,恢复加载性能) ──
    # gen.py 生成的是 base64 内联版;此步把内联 svg 抽外部去重 + 内联 <style>
    # 抽共享 css,降体积、启用跨页缓存。纯后处理、幂等、可回滚(重跑 gen.py 恢复)。
    if not args.no_optimize:
        print(bold(cyan("\n◆ 第 3 层 · 资源优化(base64 外链 + CSS 抽离)\n")))
        ok, dt, tail = run_optimize()
        if ok:
            print(f"  {green('✓')} 资源优化 {dim(f'{dt:.2f}s')}  {dim(tail)}")
        else:
            print(f"  {red('✗')} 资源优化 {dim(f'{dt:.2f}s')}  {red(tail)}")
            failures.append(("资源优化", tail))

    # ── 汇总 ──
    total = time.time() - t_start
    print(bold(f"\n{'─'*46}"))
    if failures:
        print(red(bold(f"✗ 完成但有 {len(failures)} 处失败(耗时 {total:.2f}s):")))
        for name, why in failures:
            print(red(f"    · {name}: {why}"))
        return 1
    print(green(bold(f"✓ 全部成功(耗时 {total:.2f}s)")))
    print(dim(f"  项目 {len(selected)} 个 · 整体导航 {'已重建' if not args.no_nav else '跳过'} · 资源优化 {'跳过' if args.no_optimize else '已执行'}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
