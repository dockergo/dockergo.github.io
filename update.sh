#!/usr/bin/env bash
# 一键分层更新整站图谱(下 → 上):
#   第 1 层 · 各项目   —— 发现所有含 gen.py 的 *-design/ 子项目,逐个跑其 gen.py 刷新 index.html
#   第 2 层 · 整体导航 —— 全部子项目完成后,跑根 gen.py 重建整站主导航 index.html
#   第 3 层 · 资源优化 —— 生成完毕后跑 optimize_assets.py,把 base64 内联图抽外部去重、
#                        内联 CSS 抽共享文件(降体积、跨页缓存)。纯后处理、可回滚。
#
# 本脚本是 .sh 入口,内部委托给自包含的 update.py(纯标准库、无网络、无服务器)。
# 透传全部参数,例如:
#   ./update.sh                       # 全量:项目 → 导航 → 资源优化(最终优化版文档)
#   ./update.sh --nav-only            # 只重建整体导航(仍会跑资源优化)
#   ./update.sh --only clickhouse doris
#   ./update.sh --skip spark
#   ./update.sh --list                # 只列出发现的项目,不执行
#   ./update.sh --no-nav              # 只更新项目,不重建导航
#   ./update.sh --no-optimize         # 跳过第 3 层资源优化(保留 base64 内联版)
# 退出码透传 update.py:全部成功 0;任一步失败 1。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 选 Python 解释器:优先 python3,回退 python
PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "✗ 未找到 python3 / python,无法运行 update.py" >&2
  exit 127
fi

if [ ! -f "$HERE/update.py" ]; then
  echo "✗ 缺少编排实现:$HERE/update.py" >&2
  exit 1
fi

exec "$PY" "$HERE/update.py" "$@"
