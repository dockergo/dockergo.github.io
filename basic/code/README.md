# basic/code —— 基础数据结构与算法 · 可运行 Go 模块

单一 Go module（`module helloalgo`），按 12 个基础条目分子目录，共享 `pkg/`
（链表节点 / 二叉树节点 / 顶点 / 打印工具）。代码取自 [hello-algo](https://github.com/krahets/hello-algo)
的 `codes/go`，仅将 import 路径由 `github.com/krahets/hello-algo/pkg` 改写为 `helloalgo/pkg`，
逻辑保持不变（含配套 `_test.go`）。

## 目录

| 子目录 | 主题 | 子目录 | 主题 |
|---|---|---|---|
| `array-linkedlist` | 数组与链表 | `searching` | 搜索 |
| `stack-queue` | 栈与队列 | `sorting` | 排序 |
| `hashing` | 哈希表 | `divide-conquer` | 分治 |
| `tree` | 树 | `backtracking` | 回溯 |
| `heap` | 堆 | `dynamic-programming` | 动态规划 |
| `graph` | 图 | `greedy` | 贪心 |

## 运行

```bash
cd basic/code
go build ./...   # 全部编译
go test  ./...   # 全部单测（13 个包全绿）
```
