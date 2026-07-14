# PyTorch 核心原理 · 接口主线 · 张量编程

> **定位**：最底层的用户接触面——用张量（多维数组）+ 算子写数值计算。它是一切上层（autograd/nn）的基石，强依赖**张量与存储**、**Dispatcher 分发**、**ATen 算子库**、**设备后端与内存**四个能力域。核实基准：官方源码 `pytorch/src`。

## 一、张量与视图：元信息 + 共享存储

![张量与视图](PyTorch原理_张量编程_01张量与视图.svg)

Tensor = **元信息**（shape/stride/dtype/device/offset，每张量各一份，加可选 requires_grad）+ 指向 **Storage**（一维连续内存、引用计数、可被多张量共享）。shape+stride+offset 决定"如何在一维内存里索引出多维视图"。**视图（view）**：`t.T`/`reshape`/切片/`transpose` 只改元信息、与原张量共享同一 Storage（零拷贝、改视图=改原张量，要小心别名副作用）；某些算子要求 `contiguous`（连续内存），转置后非连续需 `.contiguous()` 触发拷贝重排。**广播**（形状不同逐元素运算时从尾维对齐、大小 1 维自动扩展）、**dtype 提升**（int+float→float）、**device**（算子要求同设备、`.to('cuda')` 显式搬运）都是"自动"行为，背后由算子在 Dispatcher/ATen 实现。

---

## 二、算子的即时执行与操作族

![即时执行与操作族](PyTorch原理_张量编程_02即时执行与操作族.svg)

**即时执行（eager）**：`z=x+y` 立刻算出结果、不攒图不延迟——可 print/断点/按值分支，调试友好，代价是逐算子派发开销（torch.compile 补）。**函数式 vs 原地**：`add` 返回新张量（安全），`add_`（尾下划线）原地改（省内存但可能破坏 autograd 所需的中间值），`out=` 写进预分配张量。**操作族**：逐元素/归约（add/relu/sum/mean）、线性代数（matmul/@/conv/einsum）、形状/索引（reshape/permute/cat/切片）、设备/类型（to/cuda/float）——~2000 个算子覆盖张量运算全谱，内部统一经 Dispatcher→ATen→后端 kernel。贯穿示例 `model(x)` 展开就是 `x @ W.T + b`：一次 matmul + 一次广播 add。

---

## 拓展 · 张量关键属性

| 属性 | 含义 | 锚点 |
|---|---|---|
| shape/stride | 多维视图如何映射一维内存 | `c10/core/TensorImpl.h` |
| dtype | float32/16/bf16/int64… | `c10/core/ScalarType.h` |
| device | cpu/cuda:N | `c10/core/Device.h` |
| requires_grad | 是否追踪梯度 | autograd（见对应主线） |
| is_contiguous | 内存是否连续 | 影响能否零拷贝 reshape |

---

## 调优要点（关键开关）

- 尽量用视图（reshape/permute）避免拷贝；只在必要时 `.contiguous()`。
- 混合精度用 `float16`/`bfloat16` + autocast 省显存提速。
- 批量搬设备用 `non_blocking=True` + pin_memory 重叠传输。
- 避免 Python 循环里逐元素操作，改用向量化算子（广播/批量）。

---

## 常见误区与工程要点

- **以为视图是拷贝**：view 共享内存，改一个动全部；要独立副本用 `.clone()`。
- **原地操作乱用**：`x.add_()` 可能覆盖反向所需中间值导致 backward 报错。
- **跨设备直接运算**：cpu 张量与 cuda 张量运算报错，先 `.to()` 对齐。
- **忽视 dtype**：int 张量除法/精度问题；训练一般 float32/bf16。

---

## 一句话总纲

**张量编程是用"元信息（shape/stride/dtype/device）+ 共享 Storage"的多维数组写即时执行的算子：视图零拷贝地改元信息共享底层内存、广播/dtype 提升/设备规则让运算"自动"对齐，~2000 个算子（逐元素/线代/形状/设备）统一经 Dispatcher→ATen→后端 kernel 执行——这是 autograd 与 nn 的计算基石。**
