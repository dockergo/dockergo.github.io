# PyTorch 核心原理 · 接口主线 · 自动微分

> **定位**：让张量计算"可求导"的用户接触面——设 `requires_grad`、前向自动建反向图、`backward` 得梯度。它是训练的核心，强依赖**自动微分引擎**（图与遍历）与 **Dispatcher**（Autograd key 建节点）。核实基准：官方源码 `pytorch/pytorch` v2.13.0。

## 一、requires_grad → 前向建图 → backward → .grad

![自动微分接口](PyTorch原理_自动微分_01接口.svg)

**标记**：`requires_grad_(True)` 最终落到 `TensorImpl::set_requires_grad`（`c10/core/TensorImpl.h:1404`），惰性分配 `AutogradMeta`（`torch/csrc/autograd/variable.h:225`）并把 Autograd 键加进张量的 `key_set_`——从此该张量参与的算子会走 Dispatcher 的 Autograd 层。

**前向**：涉及 `requires_grad=True` 张量的每个可微算子边算边连反向图——Autograd 层用 `collect_next_edges`（`torch/csrc/autograd/function.h:71`）收集输入的 grad_fn、`set_history`（`torch/csrc/autograd/functions/utils.h:67`）让输出张量的 `grad_fn`（`variable.h:229`）指向新建的反向 Node，如 `y=x@W` 得 `MmBackward`、`z=relu(y)` 得 `ReluBackward`，图自动连成（define-by-run，不需预先声明）；不涉及梯度的算子不建节点（省开销）。

**backward**：`Tensor.backward`（`torch/_tensor.py:566`）转调 `torch.autograd.backward`（`torch/autograd/__init__.py:255`），驱动 C++ `Engine::execute`（`torch/csrc/autograd/engine.cpp:1294`）从 loss 沿反向图逆序遍历，每个 grad_fn 算局部梯度、链式法则累积，把 `∂loss/∂W` 写进叶子张量的 `.grad`（`variable.h:228`），optimizer 据此更新；图默认用完即释放（`retain_graph` 可留）。显式求偏导用 `torch.autograd.grad`（`torch/autograd/__init__.py:407`）。

**梯度上下文**：`torch.no_grad`（`torch/autograd/grad_mode.py:22`，推理/更新时不建图省内存）、`inference_mode`（`grad_mode.py:213`，更激进、连版本计数都省）、`detach`（把张量从图剪断停止回传）、`register_hook`（`torch/_tensor.py:655`，在梯度流经时插钩子）、`.grad` 默认累加所以每步先 `zero_grad`。

---

## 拓展 · autograd 用户接口

| 接口 | 作用 | 锚点 |
|---|---|---|
| `requires_grad_(True)` | 标记张量需要梯度 | `c10/core/TensorImpl.h:1404` |
| `.backward` | 从标量反向求梯度 | `torch/_tensor.py:566` → `autograd/__init__.py:255` |
| `.grad` | 累积的梯度（叶子张量上） | `torch/csrc/autograd/variable.h:228` |
| `torch.autograd.grad(...)` | 显式求某些输出对某些输入的梯度 | `torch/autograd/__init__.py:407` |
| `torch.no_grad` / `inference_mode` | 关闭建图 | `grad_mode.py:22` / `:213` |
| `.detach` | 切断梯度流（共享数据、清 grad_fn） | `torch/_tensor.py`（TensorBase） |
| `.register_hook` | 梯度流经时的钩子 | `torch/_tensor.py:655` |
| `torch.autograd.Function` | 自定义前向/反向 | `torch/autograd/function.py` |

---

## 深化 · 三种"关梯度"的差异

| 方式 | 建反向图 | 版本计数追踪 | 典型用途 | 锚点 |
|---|---|---|---|---|
| `no_grad()` | 否 | 仍追踪 | 推理、optimizer.step 内更新参数 | `grad_mode.py:22` |
| `inference_mode()` | 否 | 否（更省、张量不可再入图） | 纯推理服务 | `grad_mode.py:213` |
| `.detach()` | 否（就地剪断该张量） | 共享存储 | 截断部分梯度流、记录 loss 值 | `torch/_tensor.py` |

`set_grad_enabled`（`grad_mode.py:144`）可按条件开关，等价于可编程的 no_grad/enable_grad。

**自定义可微算子**：`torch.autograd.Function`（`torch/autograd/function.py`）让你写不可自动微分或需特殊反向的算子——`forward(ctx, ...)` 里用 `ctx.save_for_backward` 存反向所需张量（内部即 SavedVariable，`torch/csrc/autograd/saved_variable.h:22`）、`backward(ctx, grad_out)` 返回对各输入的梯度；PyTorch 会把它当作一个 Node 接进反向图。**高阶导数**：`backward(create_graph=True)` 或 `torch.autograd.grad(..., create_graph=True)`（`autograd/__init__.py:407`）让反向算子本身也建图，从而可对梯度再求导（如二阶优化、meta-learning）。

---

## 调优要点（关键开关）

- 推理用 `with torch.no_grad:`（`grad_mode.py:22`）或 `inference_mode`（`:213`）——省内存省时间。
- 记录 loss 用 `loss.item`/`.detach`，别拖着整张图不释放。
- 梯度检查点（checkpoint）用重算换显存：反向时重跑前向而非全存中间值（SavedVariable）。
- 自定义不可微/特殊算子用 `autograd.Function` 写 forward+backward。

---

## 常见误区与工程要点

- **忘 zero_grad**：`.grad`（`variable.h:228`）累加导致梯度错误、训练发散。
- **在需要梯度的张量上做原地操作**：可能覆盖反向所需 SavedVariable、改版本计数而报错。
- **推理不关梯度**：白建图、多占显存；应 `no_grad`/`inference_mode`。
- **对非标量直接 backward**：需传 `gradient=` 或先归约成标量（`autograd/__init__.py:255`）。

---

## 一句话总纲

**自动微分让张量可求导：`requires_grad_` 经 set_requires_grad（TensorImpl.h:1404）加 Autograd 键并分配 AutogradMeta，前向每个可微算子在 Autograd 层用 collect_next_edges+set_history 留下 grad_fn 节点连成动态反向图（define-by-run）；`Tensor.backward`（_tensor.py:566）驱动 Engine::execute 沿图逆序遍历、链式累积梯度到叶子 .grad 供 optimizer 更新；no_grad/inference_mode/detach 控制建不建图、.grad 累加需每步 zero_grad——这是 PyTorch 训练的核心机制。**
