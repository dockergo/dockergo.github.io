# PyTorch 核心原理 · 支撑能力域 · ATen 算子库

> **定位**：表示层。~2000 个张量算子的声明与实现，是 Dispatcher 分发的落点、后端 kernel 的组织框架。被**张量编程**、**自动微分**、**编译栈**依赖。核实基准：官方源码 `pytorch/src`（`aten/src/ATen/native/`）。

## 一、schema 声明 + structured kernel

![ATen 算子库](PyTorch原理_ATen_01算子库.svg)

**算子 schema**（`native_functions.yaml` 单一真源）：如 `add.Tensor(Tensor self, Tensor other) -> Tensor` 声明名/参数类型/返回/别名与可变性；代码生成据此产出 C++ 签名、Python 绑定、分发注册样板——一处声明多处生成。**structured kernel：形状与计算分离**——meta 函数（推导输出形状/dtype、分配）+ impl 函数（在已分配输出上算数值）；meta 复用于形状推断/编译（无需真算，支撑 meta 设备），impl 各后端各写、减少重复样板。**算子分层**：基础算子（有专门 kernel，add/mm/conv，调 MKL/cuBLAS/cuDNN，性能热点）vs 复合算子（CompositeImplicit，用更基础算子拼出如 softmax=exp/sum/div，自动获得 autograd、不必每个写反向）；复合算子可降解成基础算子集，供编译器（Inductor）在小算子集上融合优化。

---

## 拓展 · ATen 关键概念

| 概念 | 含义 |
|---|---|
| native_functions.yaml | 算子 schema 单一真源 |
| structured kernel | meta（形状）+ impl（计算）分离 |
| CompositeImplicitAutograd | 复合算子，拆开自动可微 |
| 代码生成 | 从 schema 产签名/绑定/注册 |
| 别名/可变性标注 | 供 functionalization/编译分析 |

---

## 调优要点（关键开关）

- 热点用基础算子（背后是厂商高性能库）；避免大量小复合算子零散调用。
- 复合算子在 torch.compile 下被降解融合，收益大。
- 自定义高性能算子写 structured kernel 复用形状推导框架。
- meta 设备跑一遍可验证形状而不耗显存。

---

## 常见误区与工程要点

- **以为每个算子都手写反向**：复合算子拆成基础算子后自动可微。
- **以为算子实现分散难维护**：schema 单一真源 + 代码生成统一样板。
- **忽视厂商库**：matmul/conv 的性能来自 cuBLAS/cuDNN，非纯手写。
- **小算子链慢**：eager 下逐个派发+访存；编译融合是解药。

---

## 一句话总纲

**ATen 是 ~2000 算子的库：schema 在 native_functions.yaml 单一声明、代码生成产出签名/绑定/注册，structured kernel 把形状推导（meta）与计算（impl）分离以复用于编译与减样板；基础算子（add/mm/conv）委托 MKL/cuBLAS/cuDNN 是性能热点，复合算子用基础算子拼成、自动可微且可被 Inductor 降解融合——这是 Dispatcher 分发的落点与后端 kernel 的组织框架。**
