#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础层生成器（basic/gen.py）—— 「基础数据结构与算法」图谱门户。

与「按项目」「按主题」两个一级视角平行，这里是第三个一级视角：**计算的基石**
（数据结构 6 类 + 算法 6 类），每一类 = 1 张原理总览图 + 若干核心算法/结构，
每个算法/结构 = 原理机制图 + 复杂度徽章 + 可运行 Go 代码（取自 hello-algo）+ 短注解。

产物（全部自包含、仅标准库、离线、SVG base64 内联、Go 代码内嵌高亮、双主题记忆切换）：
  basic/index.html            门户：12 张卡片，分「数据结构 / 算法」两组
  basic/<slug>/index.html     条目页：原理总览图 → 各算法组（垂直 TAB：图 + 复杂度 + 代码 + 注）
  basic/code/                 单一可编译 Go module（go build/test ./... 全绿），条目页代码即取自此处

设计文件命名（各条目 design/ 目录内）：
  原理总览   <中文>_00原理总览.svg
  机制图     <中文>_NN小名.svg
  对比图     <中文>_CMP对比.svg（可选）
  注解散文   <中文>.md（用 @eco / @<mechN小写> / @cmp / @refs 分节；均可缺省）

Go 代码来源：basic/code/<code 字段>，逐份经 `go build/test ./...` 校验。

用法：  cd basic && python3 gen.py
"""

import base64
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = os.path.join(HERE, "code")

# ===================================================================== #
# 一、内容契约（ITEMS）—— 12 基础条目
#   cat: "ds"=数据结构 / "algo"=算法
#   每 mech: n(编号) / title / svg(机制图) / code(basic/code 下路径,可 list) / cx(复杂度徽章)
# ===================================================================== #
ITEMS = [
    # ----------------------- 数据结构 -----------------------
    {
        "slug": "array-linkedlist", "cn": "数组与链表", "en": "Array & Linked List",
        "cat": "ds", "color": "#2f6df0",
        "title": "Array & Linked List · 数组与链表",
        "core": "连续内存换随机访问，离散节点换增删灵活——两种最基础的线性布局，是一切容器的地基。",
        "arch": "数组与链表_00原理总览.svg",
        "groups": [
            {"algo": "数组", "mechs": [
                {"n": "A1", "title": "连续内存 · 随机访问与增删", "svg": "数组与链表_01数组.svg",
                 "code": "array-linkedlist/array.go", "cx": "访问 O(1) · 插删 O(n) · 连续内存"},
            ]},
            {"algo": "链表", "mechs": [
                {"n": "A2", "title": "指针链接 · 结点增删", "svg": "数组与链表_02链表.svg",
                 "code": "array-linkedlist/linked_list.go", "cx": "访问 O(n) · 增删 O(1) · 离散内存"},
            ]},
            {"algo": "动态数组（列表）", "mechs": [
                {"n": "A3", "title": "扩容与摊还 O(1)", "svg": "数组与链表_03动态数组.svg",
                 "code": "array-linkedlist/my_list.go", "cx": "均摊追加 O(1) · 倍增扩容"},
            ]},
        ],
        "compare": {"svg": "数组与链表_CMP对比.svg"},
    },
    {
        "slug": "stack-queue", "cn": "栈与队列", "en": "Stack & Queue",
        "cat": "ds", "color": "#2f6df0",
        "title": "Stack & Queue · 栈与队列",
        "core": "只在端点操作的受限线性表：栈 LIFO、队列 FIFO、双端队列两头皆可——用数组或链表都能承载。",
        "arch": "栈与队列_00原理总览.svg",
        "groups": [
            {"algo": "栈 Stack", "mechs": [
                {"n": "Q1", "title": "LIFO · 数组/链表两种实现", "svg": "栈与队列_01栈.svg",
                 "code": ["stack-queue/array_stack.go", "stack-queue/linkedlist_stack.go"],
                 "cx": "入栈/出栈 O(1)"},
            ]},
            {"algo": "队列 Queue", "mechs": [
                {"n": "Q2", "title": "FIFO · 环形数组避免搬移", "svg": "栈与队列_02队列.svg",
                 "code": ["stack-queue/array_queue.go", "stack-queue/linkedlist_queue.go"],
                 "cx": "入队/出队 O(1) · 环形复用"},
            ]},
            {"algo": "双端队列 Deque", "mechs": [
                {"n": "Q3", "title": "两端皆可增删", "svg": "栈与队列_03双端队列.svg",
                 "code": ["stack-queue/array_deque.go", "stack-queue/linkedlist_deque.go"],
                 "cx": "两端操作 O(1)"},
            ]},
        ],
        "compare": {"svg": "栈与队列_CMP对比.svg"},
    },
    {
        "slug": "hashing", "cn": "哈希表", "en": "Hash Table",
        "cat": "ds", "color": "#2f6df0",
        "title": "Hash Table · 哈希表",
        "core": "用哈希函数把键直接映射到桶下标，换来平均 O(1) 增删查；代价是冲突处理与扩容 rehash。",
        "arch": "哈希表_00原理总览.svg",
        "groups": [
            {"algo": "哈希函数与冲突", "mechs": [
                {"n": "H1", "title": "键→下标 · 冲突从何而来", "svg": "哈希表_01哈希函数.svg",
                 "code": "hashing/simple_hash.go", "cx": "理想 O(1) · 冲突退化 O(n)"},
            ]},
            {"algo": "链式地址", "mechs": [
                {"n": "H2", "title": "桶挂链表 · 负载因子扩容", "svg": "哈希表_02链式地址.svg",
                 "code": "hashing/hash_map_chaining.go", "cx": "均摊 O(1) · rehash O(n)"},
            ]},
            {"algo": "开放寻址", "mechs": [
                {"n": "H3", "title": "线性探测 · 懒删除标记", "svg": "哈希表_03开放寻址.svg",
                 "code": "hashing/hash_map_open_addressing.go", "cx": "均摊 O(1) · 探测序列"},
            ]},
        ],
        "compare": {"svg": "哈希表_CMP对比.svg"},
    },
    {
        "slug": "tree", "cn": "树", "en": "Tree",
        "cat": "ds", "color": "#2f6df0",
        "title": "Tree · 树与二叉树",
        "core": "层次化的分叉结构：遍历给出访问秩序，二叉搜索树给出有序 O(log n) 查找，AVL 用旋转守住平衡。",
        "arch": "树_00原理总览.svg",
        "groups": [
            {"algo": "二叉树遍历", "mechs": [
                {"n": "T1", "title": "DFS · 前/中/后序", "svg": "树_01DFS遍历.svg",
                 "code": "tree/binary_tree_dfs.go", "cx": "O(n) · 递归栈 O(h)"},
                {"n": "T2", "title": "BFS · 层序队列", "svg": "树_02BFS层序.svg",
                 "code": "tree/binary_tree_bfs.go", "cx": "O(n) · 队列 O(w)"},
            ]},
            {"algo": "二叉搜索树 BST", "mechs": [
                {"n": "T3", "title": "有序性 · 查找/插入/删除", "svg": "树_03二叉搜索树.svg",
                 "code": "tree/binary_search_tree.go", "cx": "均衡 O(log n) · 退化 O(n)"},
            ]},
            {"algo": "AVL 平衡树", "mechs": [
                {"n": "T4", "title": "四种旋转守住平衡", "svg": "树_04AVL旋转.svg",
                 "code": "tree/avl_tree.go", "cx": "查/插/删 O(log n) 保证"},
            ]},
        ],
        "compare": {"svg": "树_CMP对比.svg"},
    },
    {
        "slug": "heap", "cn": "堆", "en": "Heap",
        "cat": "ds", "color": "#2f6df0",
        "title": "Heap · 堆与优先队列",
        "core": "用数组隐式表达的完全二叉树，只保证父子间偏序；堆顶恒为极值，是优先队列与 TopK 的引擎。",
        "arch": "堆_00原理总览.svg",
        "groups": [
            {"algo": "堆的操作", "mechs": [
                {"n": "P1", "title": "上浮/下沉维持堆序", "svg": "堆_01上浮下沉.svg",
                 "code": "heap/my_heap.go", "cx": "入堆/出堆 O(log n) · 查顶 O(1)"},
            ]},
            {"algo": "建堆", "mechs": [
                {"n": "P2", "title": "自底向上 O(n) 建堆", "svg": "堆_02建堆.svg",
                 "code": "heap/my_heap.go", "cx": "建堆 O(n)"},
            ]},
            {"algo": "TopK 应用", "mechs": [
                {"n": "P3", "title": "小顶堆求 TopK", "svg": "堆_03TopK.svg",
                 "code": "heap/top_k.go", "cx": "O(n log k)"},
            ]},
        ],
        "compare": {"svg": "堆_CMP对比.svg"},
    },
    {
        "slug": "graph", "cn": "图", "en": "Graph",
        "cat": "ds", "color": "#2f6df0",
        "title": "Graph · 图",
        "core": "顶点与边的任意关系网：邻接矩阵稠密快查、邻接表稀疏省空间；BFS 逐层扩散、DFS 一路到底。",
        "arch": "图_00原理总览.svg",
        "groups": [
            {"algo": "图的表示", "mechs": [
                {"n": "G1", "title": "邻接矩阵 · 稠密 O(1) 查边", "svg": "图_01邻接矩阵.svg",
                 "code": "graph/graph_adjacency_matrix.go", "cx": "空间 O(V²) · 查边 O(1)"},
                {"n": "G2", "title": "邻接表 · 稀疏省空间", "svg": "图_02邻接表.svg",
                 "code": "graph/graph_adjacency_list.go", "cx": "空间 O(V+E)"},
            ]},
            {"algo": "图的遍历", "mechs": [
                {"n": "G3", "title": "BFS · 队列逐层扩散", "svg": "图_03BFS.svg",
                 "code": "graph/graph_bfs.go", "cx": "O(V+E)"},
                {"n": "G4", "title": "DFS · 递归一路到底", "svg": "图_04DFS.svg",
                 "code": "graph/graph_dfs.go", "cx": "O(V+E)"},
            ]},
        ],
        "compare": {"svg": "图_CMP对比.svg"},
    },
    # ----------------------- 算法 -----------------------
    {
        "slug": "searching", "cn": "搜索", "en": "Searching",
        "cat": "algo", "color": "#e0803a",
        "title": "Searching · 搜索",
        "core": "在数据里定位目标：无序只能线性 O(n)，有序可二分 O(log n)，用哈希把查找摊到 O(1)。",
        "arch": "搜索_00原理总览.svg",
        "groups": [
            {"algo": "线性与哈希查找", "mechs": [
                {"n": "SR1", "title": "线性扫描 O(n)", "svg": "搜索_01线性.svg",
                 "code": "searching/linear_search.go", "cx": "O(n) · 无序可用"},
                {"n": "SR2", "title": "哈希查找 O(1) · 空间换时间", "svg": "搜索_02哈希查找.svg",
                 "code": ["searching/hashing_search.go", "searching/two_sum.go"],
                 "cx": "均摊 O(1) · 额外 O(n) 空间"},
            ]},
            {"algo": "二分查找", "mechs": [
                {"n": "SR3", "title": "折半收缩区间", "svg": "搜索_03二分.svg",
                 "code": "searching/binary_search.go", "cx": "O(log n) · 需有序"},
                {"n": "SR4", "title": "边界与插入点（左闭右闭）", "svg": "搜索_04二分边界.svg",
                 "code": ["searching/binary_search_edge.go", "searching/binary_search_insertion.go"],
                 "cx": "O(log n) · 区间不变式"},
            ]},
        ],
        "compare": {"svg": "搜索_CMP对比.svg"},
    },
    {
        "slug": "sorting", "cn": "排序", "en": "Sorting",
        "cat": "algo", "color": "#e0803a",
        "title": "Sorting · 排序",
        "core": "把序列变有序的经典战场：比较类下界 O(n log n)，非比较类靠桶/计数/基数在特定分布下线性突破。",
        "arch": "排序_00原理总览.svg",
        "groups": [
            {"algo": "比较类 · 简单 O(n²)", "mechs": [
                {"n": "O1", "title": "冒泡 · 相邻交换与提前终止", "svg": "排序_01冒泡.svg",
                 "code": "sorting/bubble_sort.go", "cx": "O(n²)/O(1) · 稳定"},
                {"n": "O2", "title": "插入 · 有序区逐个插入", "svg": "排序_02插入.svg",
                 "code": "sorting/insertion_sort.go", "cx": "O(n²)/O(1) · 稳定 · 近序快"},
                {"n": "O3", "title": "选择 · 每轮选极值", "svg": "排序_03选择.svg",
                 "code": "sorting/selection_sort.go", "cx": "O(n²)/O(1) · 不稳定"},
            ]},
            {"algo": "比较类 · 高效 O(n log n)", "mechs": [
                {"n": "O4", "title": "快排 · 基准划分（分治）", "svg": "排序_04快排.svg",
                 "code": "sorting/quick_sort.go", "cx": "均 O(n log n) · 最坏 O(n²) · 原地"},
                {"n": "O5", "title": "归并 · 分而治之再合并", "svg": "排序_05归并.svg",
                 "code": "sorting/merge_sort.go", "cx": "O(n log n)/O(n) · 稳定"},
                {"n": "O6", "title": "堆排 · 建堆后反复取顶", "svg": "排序_06堆排.svg",
                 "code": "sorting/heap_sort.go", "cx": "O(n log n)/O(1) · 不稳定"},
            ]},
            {"algo": "非比较类 · 线性", "mechs": [
                {"n": "O7", "title": "计数 · 值域桶直接计数", "svg": "排序_07计数.svg",
                 "code": "sorting/counting_sort.go", "cx": "O(n+m) · 值域受限"},
                {"n": "O8", "title": "桶 · 分桶各自排序", "svg": "排序_08桶.svg",
                 "code": "sorting/bucket_sort.go", "cx": "均 O(n+k) · 依赖分布"},
                {"n": "O9", "title": "基数 · 按位多轮稳定排序", "svg": "排序_09基数.svg",
                 "code": "sorting/radix_sort.go", "cx": "O(nk) · 定长键"},
            ]},
        ],
        "compare": {"svg": "排序_CMP对比.svg"},
    },
    {
        "slug": "divide-conquer", "cn": "分治", "en": "Divide & Conquer",
        "cat": "algo", "color": "#e0803a",
        "title": "Divide & Conquer · 分治",
        "core": "把问题拆成同构子问题、递归求解、再合并——分治是二分、归并、快排、树形构造背后的统一骨架。",
        "arch": "分治_00原理总览.svg",
        "groups": [
            {"algo": "分治框架", "mechs": [
                {"n": "DC1", "title": "二分查找的递归视角", "svg": "分治_01二分递归.svg",
                 "code": "divide-conquer/binary_search_recur.go", "cx": "T(n)=T(n/2)+O(1)=O(log n)"},
            ]},
            {"algo": "分治构造", "mechs": [
                {"n": "DC2", "title": "前序+中序重建二叉树", "svg": "分治_02构建树.svg",
                 "code": "divide-conquer/build_tree.go", "cx": "O(n) · 哈希定位根"},
            ]},
            {"algo": "经典递归", "mechs": [
                {"n": "DC3", "title": "汉诺塔 · 规模减一的分治", "svg": "分治_03汉诺塔.svg",
                 "code": "divide-conquer/hanota.go", "cx": "O(2ⁿ) 移动数"},
            ]},
        ],
        "compare": {"svg": "分治_CMP对比.svg"},
    },
    {
        "slug": "backtracking", "cn": "回溯", "en": "Backtracking",
        "cat": "algo", "color": "#e0803a",
        "title": "Backtracking · 回溯",
        "core": "在解空间树上深度探索：尝试→递归→撤销，配合剪枝把指数搜索裁到可行——全排列、子集、N 皇后同一套框架。",
        "arch": "回溯_00原理总览.svg",
        "groups": [
            {"algo": "回溯框架", "mechs": [
                {"n": "BT1", "title": "尝试-回退 · 前序遍历三形态", "svg": "回溯_01框架.svg",
                 "code": ["backtracking/preorder_traversal_i_compact.go",
                          "backtracking/preorder_traversal_iii_template.go"],
                 "cx": "解空间树 DFS"},
            ]},
            {"algo": "全排列", "mechs": [
                {"n": "BT2", "title": "选择列表 · 含重去重剪枝", "svg": "回溯_02全排列.svg",
                 "code": ["backtracking/permutations_i.go", "backtracking/permutations_ii.go"],
                 "cx": "O(n·n!)"},
            ]},
            {"algo": "子集和", "mechs": [
                {"n": "BT3", "title": "起点约束避免重复组合", "svg": "回溯_03子集和.svg",
                 "code": ["backtracking/subset_sum_i.go", "backtracking/subset_sum_ii.go"],
                 "cx": "剪枝依赖排序"},
            ]},
            {"algo": "N 皇后", "mechs": [
                {"n": "BT4", "title": "逐行放置 · 列/对角冲突剪枝", "svg": "回溯_04N皇后.svg",
                 "code": "backtracking/n_queens.go", "cx": "O(n!) · 强剪枝"},
            ]},
        ],
        "compare": {"svg": "回溯_CMP对比.svg"},
    },
    {
        "slug": "dynamic-programming", "cn": "动态规划", "en": "Dynamic Programming",
        "cat": "algo", "color": "#e0803a",
        "title": "Dynamic Programming · 动态规划",
        "core": "有重叠子问题+最优子结构时，用状态转移方程记住子解、消除重复计算——从爬楼梯到背包、编辑距离一脉相承。",
        "arch": "动态规划_00原理总览.svg",
        "groups": [
            {"algo": "DP 引入 · 爬楼梯", "mechs": [
                {"n": "DP1", "title": "回溯→记忆化→DP→状态压缩", "svg": "动态规划_01爬楼梯演进.svg",
                 "code": ["dynamic-programming/climbing_stairs_dfs_mem.go",
                          "dynamic-programming/climbing_stairs_dp.go",
                          "dynamic-programming/climbing_stairs_constraint_dp.go"],
                 "cx": "O(n)/O(1) · 四步演进"},
            ]},
            {"algo": "路径类 DP", "mechs": [
                {"n": "DP2", "title": "最小路径和 · 二维状态", "svg": "动态规划_02最小路径和.svg",
                 "code": "dynamic-programming/min_path_sum.go", "cx": "O(nm) · 可滚动数组"},
            ]},
            {"algo": "背包问题", "mechs": [
                {"n": "DP3", "title": "0-1 背包 · 逆序滚动", "svg": "动态规划_03背包.svg",
                 "code": "dynamic-programming/knapsack.go", "cx": "O(nW)"},
                {"n": "DP4", "title": "完全背包 / 零钱兑换", "svg": "动态规划_04完全背包.svg",
                 "code": ["dynamic-programming/unbounded_knapsack.go",
                          "dynamic-programming/coin_change.go"],
                 "cx": "O(nW) · 正序可重复"},
            ]},
            {"algo": "字符串 DP", "mechs": [
                {"n": "DP5", "title": "编辑距离 · 增删改三方向", "svg": "动态规划_05编辑距离.svg",
                 "code": "dynamic-programming/edit_distance.go", "cx": "O(nm)"},
            ]},
        ],
        "compare": {"svg": "动态规划_CMP对比.svg"},
    },
    {
        "slug": "greedy", "cn": "贪心", "en": "Greedy",
        "cat": "algo", "color": "#e0803a",
        "title": "Greedy · 贪心",
        "core": "每步都取当下最优、不回头——正确性依赖「贪心选择性质」，零钱贪心的反例正说明它并非总对。",
        "arch": "贪心_00原理总览.svg",
        "groups": [
            {"algo": "贪心与反例", "mechs": [
                {"n": "GD1", "title": "零钱贪心为何会失败", "svg": "贪心_01零钱反例.svg",
                 "code": "greedy/coin_change_greedy.go", "cx": "O(n) · 但不总最优"},
            ]},
            {"algo": "分数背包", "mechs": [
                {"n": "GD2", "title": "按单位价值排序装满", "svg": "贪心_02分数背包.svg",
                 "code": "greedy/fractional_knapsack.go", "cx": "O(n log n) · 排序主导"},
            ]},
            {"algo": "双指针贪心", "mechs": [
                {"n": "GD3", "title": "最大容量 · 移动短板", "svg": "贪心_03最大容量.svg",
                 "code": "greedy/max_capacity.go", "cx": "O(n) · 双指针"},
            ]},
            {"algo": "数学贪心", "mechs": [
                {"n": "GD4", "title": "最大切分乘积 · 尽量切 3", "svg": "贪心_04切分乘积.svg",
                 "code": "greedy/max_product_cutting.go", "cx": "O(1) · 数学结论"},
            ]},
        ],
        "compare": {"svg": "贪心_CMP对比.svg"},
    },
]

# ===================================================================== #
# 二、文件读取 / base64 内联 / markdown 行内 / Go 代码高亮
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


def esc(s):
    return html.escape(str(s), quote=True)


def _md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener" class="ref">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _md_para(body):
    body = (body or "").strip()
    if not body:
        return ""
    chunks = re.split(r"\n\s*\n", body)
    return "".join("<p>%s</p>" % _md_inline(c.strip().replace("\n", " "))
                   for c in chunks if c.strip())


def parse_prose(slug, cn):
    """读取 <cn>.md，按任意 @marker 分节（@eco / @a1 / @cmp / @refs …）。"""
    txt = _read(slug, cn + ".md")
    buf, cur = {}, None
    for line in txt.splitlines():
        m = re.match(r"^@(\w+)\s*$", line.strip())
        if m:
            cur = m.group(1).lower()
            buf.setdefault(cur, [])
            continue
        if cur is not None:
            buf[cur].append(line)
    return {k: _md_para("\n".join(v)) for k, v in buf.items()}


# ---- Go 语法高亮（纯 Python，零依赖，token → <span>）----
_GO_KW = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var",
}
_GO_LIT = {"true", "false", "nil", "iota"}
_GO_TYPE = {
    "int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16",
    "uint32", "uint64", "uintptr", "float32", "float64", "complex64",
    "complex128", "byte", "rune", "string", "bool", "error", "any",
}
_GO_BUILTIN = {
    "make", "len", "cap", "append", "copy", "delete", "new", "panic",
    "recover", "print", "println", "close", "min", "max",
}
# token 正则：注释 / 字符串 / 字符 / 数字 / 标识符 / 其它
_GO_TOK = re.compile(
    r"(?P<cmt>//[^\n]*|/\*.*?\*/)"
    r"|(?P<str>\"(?:\\.|[^\"\\])*\"|`[^`]*`)"
    r"|(?P<chr>'(?:\\.|[^'\\])')"
    r"|(?P<num>\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b0[xX][0-9a-fA-F]+\b)"
    r"|(?P<id>[A-Za-z_]\w*)"
    r"|(?P<ws>\s+)"
    r"|(?P<any>.)",
    re.S,
)


def _strip_go_header(src):
    """去掉 hello-algo 文件顶部的 // File/Created/Author 注释块，页面更干净。"""
    lines = src.splitlines()
    i = 0
    while i < len(lines) and (
        lines[i].strip() == "" or
        re.match(r"^//\s*(File|Created Time|Author)\b", lines[i].strip())
    ):
        i += 1
    return "\n".join(lines[i:]).strip("\n")


def highlight_go(src):
    """把 Go 源码转成带 <span class="tk-*"> 的 HTML（已 escape）。"""
    out = []
    pos = 0
    prev_ident_before_paren = False  # 简单函数名着色：id 后紧跟 '(' → 函数
    tokens = list(_GO_TOK.finditer(src))
    for idx, m in enumerate(tokens):
        kind = m.lastgroup
        tok = m.group()
        if kind == "cmt":
            out.append('<span class="tk-c">%s</span>' % esc(tok))
        elif kind in ("str", "chr"):
            out.append('<span class="tk-s">%s</span>' % esc(tok))
        elif kind == "num":
            out.append('<span class="tk-n">%s</span>' % esc(tok))
        elif kind == "id":
            if tok in _GO_KW:
                out.append('<span class="tk-k">%s</span>' % esc(tok))
            elif tok in _GO_LIT:
                out.append('<span class="tk-l">%s</span>' % esc(tok))
            elif tok in _GO_TYPE:
                out.append('<span class="tk-t">%s</span>' % esc(tok))
            elif tok in _GO_BUILTIN:
                out.append('<span class="tk-b">%s</span>' % esc(tok))
            else:
                # 向后看：跳过空白后若是 '(' 视为函数调用/定义
                nxt = tokens[idx + 1].group() if idx + 1 < len(tokens) else ""
                nnxt = tokens[idx + 2].group() if idx + 2 < len(tokens) else ""
                follow = nxt if nxt.strip() else nnxt
                if follow.startswith("("):
                    out.append('<span class="tk-f">%s</span>' % esc(tok))
                else:
                    out.append(esc(tok))
        else:
            out.append(esc(tok))
    return "".join(out)


def _read_code(rel):
    p = os.path.join(CODE_ROOT, rel)
    if not os.path.isfile(p):
        _missing.append("code/%s" % rel)
        return None
    with open(p, encoding="utf-8") as f:
        return _strip_go_header(f.read())


def render_code(codefield):
    """codefield: str 或 list[str]（basic/code 下相对路径）→ 高亮代码块 HTML。"""
    if not codefield:
        return ""
    files = codefield if isinstance(codefield, list) else [codefield]
    blocks = []
    for rel in files:
        src = _read_code(rel)
        base = os.path.basename(rel)
        if src is None:
            blocks.append('<div class="miss">代码缺失：%s</div>' % esc(rel))
            continue
        blocks.append(
            '<div class="codeblock">'
            '<div class="codebar"><span class="cdot"></span><span class="cdot"></span>'
            '<span class="cdot"></span><span class="cfile">%s</span>'
            '<span class="cpath">basic/code/%s</span></div>'
            '<pre class="code"><code>%s</code></pre></div>'
            % (esc(base), esc(rel), highlight_go(src)))
    return "".join(blocks)


# ===================================================================== #
# 三、页面模板：CSS（双主题）+ JS（记忆切换 + 垂直 TAB）
# ===================================================================== #
CSS = r"""
:root{
  --c-bg:#0d0d0f; --c-card:#17171a; --c-card2:#1e1e22; --c-ink:#f2f2f5;
  --c-ink2:#a1a1a6; --c-ink3:#6e6e73; --c-line:#2a2a30; --c-edge:#33333a;
  --c-panel:#161619; --c-shadow:rgba(0,0,0,.5);
  --cd-bg:#111318; --cd-kw:#c792ea; --cd-str:#89ca78; --cd-num:#f78c6c;
  --cd-cmt:#5c6370; --cd-type:#4ec9b0; --cd-fn:#61afef; --cd-bi:#e5c07b; --cd-lit:#d19a66;
}
html[data-theme="light"]{
  --c-bg:#fbfbfd; --c-card:#ffffff; --c-card2:#f5f5f7; --c-ink:#1d1d1f;
  --c-ink2:#6e6e73; --c-ink3:#a1a1a6; --c-line:#e6e6ea; --c-edge:#d2d2d7;
  --c-panel:#ffffff; --c-shadow:rgba(0,0,0,.08);
  --cd-bg:#f6f8fa; --cd-kw:#a626a4; --cd-str:#50a14f; --cd-num:#b76b01;
  --cd-cmt:#a0a1a7; --cd-type:#0e7490; --cd-fn:#4078f2; --cd-bi:#986801; --cd-lit:#b76b01;
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
.hero{margin:6px 0 26px}
.hero h1{font-size:26px;font-weight:800;letter-spacing:.2px}
.hero .sub{margin-top:8px;font-size:13.5px;color:var(--c-ink2);max-width:860px}
.hero .back{display:inline-flex;align-items:center;gap:6px;margin-bottom:14px;
  font-size:12.5px;color:var(--c-ink2);border:1px solid var(--c-line);
  border-radius:999px;padding:5px 13px;background:var(--c-panel)}
.hero .back:hover{color:var(--c-ink);border-color:var(--c-edge)}
.grouphd{display:flex;align-items:center;gap:12px;margin:30px 0 15px}
.grouphd .gi{flex:none;width:30px;height:30px;border-radius:9px;display:inline-grid;place-items:center;
  color:#fff;font-size:16px;font-weight:800}
.grouphd h2{font-size:18px;font-weight:800}
.grouphd .cnt{font-size:12px;color:var(--c-ink3);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}
.card{position:relative;display:block;background:var(--c-card);border:1px solid var(--c-line);
  border-radius:16px;padding:20px 20px 18px;overflow:hidden;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}
.card:hover{transform:translateY(-3px);border-color:var(--acc);box-shadow:0 10px 30px var(--c-shadow)}
.card .bar{position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--acc)}
.card .k{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.6px;
  color:var(--acc);text-transform:uppercase;margin-bottom:8px}
.card h3{font-size:17px;font-weight:750;line-height:1.35;color:var(--c-ink)}
.card .core{margin-top:9px;font-size:12.5px;color:var(--c-ink2);line-height:1.6}
.card .tags{margin-top:14px;display:flex;flex-wrap:wrap;gap:6px}
.card .tag{font-size:11px;color:var(--c-ink2);background:var(--c-card2);
  border:1px solid var(--c-line);border-radius:7px;padding:3px 8px}
.card .go{margin-top:15px;font-size:12px;font-weight:700;color:var(--acc);display:inline-flex;align-items:center;gap:5px}
/* 条目页 */
.judge{background:var(--c-card);border:1px solid var(--c-line);border-left:4px solid var(--acc);
  border-radius:14px;padding:18px 22px;margin-bottom:26px}
.judge .k{font-size:11px;font-weight:700;letter-spacing:.6px;color:var(--acc);text-transform:uppercase}
.judge h1{font-size:22px;font-weight:800;line-height:1.34;margin-top:7px}
.judge .core{margin-top:11px;font-size:13.5px;color:var(--c-ink2);line-height:1.7;max-width:900px}
.secttl{display:flex;align-items:center;gap:11px;margin:34px 0 14px}
.secttl .badge{flex:none;min-width:30px;height:30px;padding:0 9px;border-radius:9px;background:var(--acc);
  color:#fff;font-weight:800;font-size:14px;display:inline-grid;place-items:center}
.secttl .t{font-size:16px;font-weight:750}
.secttl.eco .badge{background:var(--c-ink);color:var(--c-bg)}
.vt-wrap{display:flex;gap:22px;margin-top:26px;align-items:flex-start}
.vt-nav{flex:none;width:248px;position:sticky;top:20px;display:flex;flex-direction:column;gap:8px;max-height:calc(100vh - 40px);overflow-y:auto}
.vt-grp{font-size:11px;font-weight:800;letter-spacing:.04em;color:var(--c-ink3);
  margin:14px 4px 2px;padding-top:8px;border-top:1px solid var(--c-line)}
.vt-grp:first-child{margin-top:0;padding-top:0;border-top:none}
.vt-tab{display:flex;align-items:center;gap:10px;text-align:left;cursor:pointer;
  background:var(--c-card);border:1px solid var(--c-line);border-radius:12px;
  padding:11px 12px;color:var(--c-ink2);font:inherit;transition:.15s}
.vt-tab:hover{border-color:var(--acc);color:var(--c-ink)}
.vt-tab.active{background:var(--acc);border-color:var(--acc);color:#fff;box-shadow:0 4px 14px -6px var(--acc)}
.vt-tab .vt-b{flex:none;min-width:30px;height:24px;padding:0 6px;border-radius:7px;
  background:var(--c-card2);color:var(--acc);font-weight:800;font-size:11px;
  display:inline-grid;place-items:center;font-variant-numeric:tabular-nums}
.vt-tab.active .vt-b{background:rgba(255,255,255,.24);color:#fff}
.vt-tab .vt-l{font-size:12.5px;font-weight:650;line-height:1.35}
.vt-stage{flex:1;min-width:0}
.vt-sec{display:none}
.vt-sec.active{display:block;animation:vtfade .22s ease}
.vt-sec .secttl{margin-top:0}
@keyframes vtfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(max-width:860px){.vt-wrap{flex-direction:column}.vt-nav{position:static;width:100%;max-height:none;flex-direction:row;flex-wrap:wrap}.vt-tab{flex:1 1 44%}}
.fig{background:var(--c-card);border:1px solid var(--c-line);border-radius:16px;padding:16px;overflow:hidden}
.fig img{display:block;width:100%;height:auto;border-radius:8px}
html:not([data-theme="light"]) .fig img{filter:invert(.925) hue-rotate(180deg) saturate(.86)}
.cxbadge{display:inline-flex;align-items:center;gap:7px;margin-top:14px;font-size:12px;font-weight:650;
  color:var(--acc);background:color-mix(in srgb,var(--acc) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--acc) 30%,transparent);border-radius:999px;padding:5px 13px}
.cxbadge .lab{color:var(--c-ink3);font-weight:700;letter-spacing:.04em}
.blurb{margin-top:14px;background:var(--c-card);border:1px solid var(--c-line);border-radius:14px;padding:15px 19px}
.blurb p{font-size:13px;color:var(--c-ink2);line-height:1.75}
.blurb p+p{margin-top:9px}
.blurb b{color:var(--c-ink);font-weight:700}
.blurb code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:.88em;
  background:var(--c-card2);border:1px solid var(--c-line);border-radius:5px;padding:1px 5px;color:var(--acc)}
.blurb a{color:var(--acc);border-bottom:1px solid color-mix(in srgb,var(--acc) 40%,transparent)}
/* 代码块 */
.codeblock{margin-top:16px;border:1px solid var(--c-line);border-radius:12px;overflow:hidden;background:var(--cd-bg)}
.codebar{display:flex;align-items:center;gap:6px;padding:9px 13px;background:color-mix(in srgb,var(--cd-bg) 80%,var(--c-ink));
  border-bottom:1px solid var(--c-line)}
.codebar .cdot{width:10px;height:10px;border-radius:50%;background:var(--c-edge)}
.codebar .cfile{margin-left:8px;font:650 12px 'SF Mono',ui-monospace,Menlo,monospace;color:var(--c-ink)}
.codebar .cpath{margin-left:auto;font:500 11px 'SF Mono',ui-monospace,Menlo,monospace;color:var(--c-ink3)}
pre.code{margin:0;padding:16px 18px;overflow-x:auto;background:var(--cd-bg);
  font-family:'SF Mono',ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.65;
  color:var(--c-ink);tab-size:4}
pre.code .tk-k{color:var(--cd-kw)}
pre.code .tk-s{color:var(--cd-str)}
pre.code .tk-n{color:var(--cd-num)}
pre.code .tk-c{color:var(--cd-cmt);font-style:italic}
pre.code .tk-t{color:var(--cd-type)}
pre.code .tk-f{color:var(--cd-fn)}
pre.code .tk-b{color:var(--cd-bi)}
pre.code .tk-l{color:var(--cd-lit)}
.refs{margin-top:30px;padding-top:18px;border-top:2px solid var(--c-line)}
.reflist{margin-top:12px}
.reflist p{margin:5px 0;font-size:12.5px;color:var(--c-ink2);line-height:1.7}
.reflist a{color:var(--acc)}
.miss{padding:32px;text-align:center;color:var(--c-ink3);font-size:13px;border:1px dashed var(--c-edge);border-radius:12px;margin-top:14px}
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
<script>(function(){try{var s=localStorage.getItem('atlas-nav-theme');if(s)document.documentElement.setAttribute('data-theme',s);}catch(e){}})();</script>
<style>%s</style>
</head>
<body>""" % (esc(title), CSS))


# ===================================================================== #
# 四、门户 index.html（已废弃）
# ===================================================================== #
# basic/index.html 门户已移除：条目页 home 直接返回根 index.html#basic
# （基础原理视角）。原 _card() / build_portal() 死代码已删除。


# ===================================================================== #
# 五、条目页 <slug>/index.html
# ===================================================================== #
def build_item_page(it):
    prose = parse_prose(it["slug"], it["cn"])
    acc = it["color"]

    def fig(fname, alt):
        b64 = _b64_svg(it["slug"], fname)
        if not b64:
            return '<div class="miss">原理图待绘制：%s</div>' % esc(fname)
        return ('<div class="fig"><img alt="%s" src="data:image/svg+xml;base64,%s"/></div>'
                % (esc(alt), b64))

    head = it["title"].split(" · ")[-1] if " · " in it["title"] else it["title"]
    nav_groups, secs, first = [], [], [True]

    def add_sec(sid, badge, ttl, fig_svg, prose_key, cx=None, code=None, big=False):
        pr = prose.get(prose_key) or ""
        blurb = ('<div class="blurb">%s</div>' % pr) if pr else ""
        figh = fig(fig_svg, ttl) if fig_svg else ""
        cxh = ('<div class="cxbadge"><span class="lab">复杂度</span>%s</div>' % esc(cx)) if cx else ""
        codeh = render_code(code) if code else ""
        secs.append(
            '<section class="vt-sec%s" id="%s"><div class="secttl"><span class="badge">%s</span>'
            '<span class="t">%s</span></div>%s%s%s%s</section>'
            % (" active" if first[0] else "", sid, esc(badge), esc(ttl), figh, cxh, blurb, codeh))
        first[0] = False

    # 概览
    eco_prose = prose.get("eco") or ('<p>%s</p>' % _md_inline(it["core"]))
    nav_groups.append(("概览 Overview", [("sec-eco", "◎", "原理总览")]))
    secs.append(
        '<section class="vt-sec active" id="sec-eco"><div class="secttl eco">'
        '<span class="badge">◎</span><span class="t">原理总览 · 这一类的核心思想与取舍</span></div>'
        '%s<div class="blurb">%s</div></section>'
        % (fig(it["arch"], head + " 原理总览"), eco_prose))
    first[0] = False

    # 各算法组：组名 .vt-grp，组内每个机制一个 TAB（机制图 + 复杂度 + 注 + 代码）
    for grp in it.get("groups", []):
        items = []
        for m in grp["mechs"]:
            sid = "sec-%s" % m["n"].lower()
            items.append((sid, m["n"], esc(m["title"])))
            add_sec(sid, m["n"], "%s · %s" % (grp["algo"], m["title"]),
                    m.get("svg"), m["n"].lower(), cx=m.get("cx"), code=m.get("code"))
        nav_groups.append(("· %s" % grp["algo"], items))

    # 对比（可选）
    cmp = it.get("compare") or {}
    if cmp.get("svg") or prose.get("cmp"):
        nav_groups.append(("对比 Compare", [("sec-cmp", "⇄", "核心差异对比")]))
        add_sec("sec-cmp", "⇄", head + " · 核心差异对比", cmp.get("svg"), "cmp", big=True)

    refs_html = ""
    if prose.get("refs"):
        refs_html = ('<section class="refs"><div class="secttl"><span class="badge">§</span>'
                     '<span class="t">参考 · 权威来源</span></div>'
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

    drill = ('<div class="vt-wrap"><nav class="vt-nav" aria-label="内容切换">%s</nav>'
             '<div class="vt-stage">%s</div></div>' % (navcol, "".join(secs)))

    body = """%s
<header>
  <a class="logo" href="@@ROOT@@index.html#basic" title="返回基础原理导航"><span class="icobtn">%s</span></a>
  <div class="brand-intro">
    <div class="bt">%s</div>
    <div class="bs">基础图谱 · %s · 原理图 + 可运行 Go 代码</div>
  </div>
  <div class="spacer"></div>
  %s
</header>
<div class="wrap" style="--acc:%s">
  <div class="judge">
    <span class="k">%s</span>
    <h1>%s</h1>
    <div class="core">%s</div>
  </div>
  %s
  %s
  <div class="backrow"><a href="@@ROOT@@index.html#basic">← 返回基础原理导航</a></div>
</div>
<footer>自包含离线图谱 · 以图为主：原理总览 + 算法机制图 + 复杂度 + 可运行 Go 代码 · 垂直 TAB 切换</footer>
<script>%s</script>
</body>
</html>""" % (_head(head + " · 基础图谱"), _HOME_SVG, esc(head),
              "数据结构" if it["cat"] == "ds" else "算法", _THEME_BTN, esc(acc),
              esc(it["en"]), it["title"], esc(it["core"]),
              drill, refs_html, APP_JS)
    return body.replace("@@ROOT@@", "../../")


# ===================================================================== #
# 六、主流程
# ===================================================================== #
def main():
    # 门户已废弃：条目页 home 直接返回根 index.html#basic（基础原理视角），不再生成 basic/index.html
    for it in ITEMS:
        d = os.path.join(HERE, it["slug"])
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_item_page(it))
        print("Wrote %s" % out)

    ds = sum(1 for it in ITEMS if it["cat"] == "ds")
    algo = len(ITEMS) - ds
    print("基础条目 %d 个（数据结构 %d + 算法 %d）· 条目页 %d（无独立门户）" % (len(ITEMS), ds, algo, len(ITEMS)))
    if _missing:
        svg_miss = [m for m in _missing if not m.startswith("code/")]
        code_miss = [m for m in _missing if m.startswith("code/")]
        print("  ⚠ 缺失 SVG（%d）：" % len(svg_miss))
        for m in svg_miss:
            print("      -", m)
        if code_miss:
            print("  ⚠ 缺失代码（%d）：" % len(code_miss))
            for m in code_miss:
                print("      -", m)
    else:
        print("  ✓ 全部 SVG + 代码就位，无缺失")


if __name__ == "__main__":
    main()
