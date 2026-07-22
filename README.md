# 技术图谱 · 计算机体系架构导航

离线自包含的计算机体系原理图谱。根 `index.html` 本身是一张计算机体系结构图——按系统层次(接口/语言层 → 计算引擎 → 存储引擎 → 消息/流 → 分布式协调 → 编排/服务网格 → OS 内核 → 网络 → AI/ML → 语言运行时)自上而下布局,每个开源项目、每条原理主线是图上一个可点模块,点进去是该主题的交互式子图谱(架构图 + 源码级 `file:line` 引用 + 统计/依赖矩阵)。全站零依赖,纯 HTML/SVG/内联 JS,双击打开即用。

## 目录分层

六个一级分层,内容各自独立、结构同构:

| 目录 | 内容 |
|---|---|
| `basic/` | 数据结构与算法基础(排序/树/图/动态规划 …) |
| `llm/` | LLM 与 Agent 原理(Transformer/推理优化/RAG/多智能体 …) |
| `principles/` | 分布式系统原理(缓存/一致性/复制/消息/服务发现 …) |
| `projects/` | 开源项目原理精读(Redis/Kafka/Kubernetes/Spark …) |
| `topics/` | 跨项目主题横切对比(共识/存储/事务/网络 IO …) |
| `scenarios/` | 业务场景落地全景(秒杀/推荐/风控/AIGC …) |

每个主题/项目遵循同一约定:

```
<tier>/<topic>/design/{<topic>.md, *.svg}   ← 源材料:文字定位 + 手绘/程序化架构图
<tier>/<topic>/gen.py                       ← 编译器:读 design/,产出交互式页面
<tier>/<topic>/index.html                   ← 产物:自包含单文件页面,不手改
```

`index.html` 永远是生成产物,改动请改 `design/` 下的 `.md`/`.svg` 或对应 `gen.py`,再重新生成。

## 重新生成

```bash
python3 update.py                # 全量:先所有子项目 gen.py,后根 gen.py 重建整体导航
python3 update.py --only redis    # 只更新指定项目(仍会重建导航)
python3 update.py --list          # 只列出发现的项目及其 gen.py,不执行
python3 update.py --help          # 查看全部参数
```

`update.py` 自下而上两层:先跑各子项目 `gen.py` 刷新自己的 `index.html`,再跑根 `gen.py` 重新扫描全部产物、重建整体导航——根导航的状态/主题/统计都从子项目产物扫描得来,必须先子后主。全程仅用标准库,不依赖网络或服务器。
