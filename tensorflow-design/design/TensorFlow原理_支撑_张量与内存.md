# TensorFlow 核心原理 · 支撑能力域 · 张量与内存

> **定位**：底座能力域。张量（Tensor）是一切算子的输入输出，其内存由引用计数的 TensorBuffer 承载、按设备用 Allocator 分配。被所有能力域依赖。核实基准：官方源码（`tensorflow/core/framework/tensor.h:72`、`tensorflow/core/framework/allocator.h`）。

## 一、Tensor 的两半：元信息 + 共享缓冲

![Tensor与Buffer](TensorFlow原理_张量内存_01Tensor与Buffer.svg)

C++ 侧的 `Tensor`（`framework/tensor.h`）分两半：**轻量元信息**（TensorShape 各维大小、dtype、指向缓冲的指针，值语义、拷贝廉价）+ **重的数据缓冲** `TensorBuffer`（`tensor.h:72` `class TensorBuffer : public core::RefCounted`）。缓冲是引用计数对象，持有一块设备内存，**多个 Tensor 可共享同一个 TensorBuffer**——`reshape`、`slice` 等视图操作复用底层内存、零拷贝，靠引用计数保活。tf.function 追踪出的图内张量是符号占位，执行期才绑定到真实缓冲。

## 二、分设备分配：Allocator

![Tensor与Buffer](TensorFlow原理_张量内存_01Tensor与Buffer.svg)

内存由 `Allocator`（`framework/allocator.h`）抽象，**每个设备一个**：CPU Allocator 做对齐的系统内存分配；GPU 用 **BFC（best-fit with coalescing）Allocator** 把显存池化——一次向驱动要大块、内部按 best-fit 切分并在释放时合并空洞，避免频繁 `cudaMalloc/cudaFree` 的高延迟。这是显存复用与碎片控制的关键。

## 深化 · 内存关键机制

| 机制 | 说明 | 依据 |
|---|---|---|
| 引用计数缓冲 | TensorBuffer : RefCounted，多 Tensor 共享 | `tensor.h:72` |
| 零拷贝视图 | reshape/slice 复用底层缓冲 | 元信息变、缓冲不变 |
| 分设备 Allocator | CPU/GPU 各一，接口统一 | `allocator.h` |
| BFC 显存池 | best-fit + 合并，池化复用 | 避免频繁 cudaMalloc |
| Grappler 内存优化 | 重算/换出省显存 | memory_optimization pass |

## 拓展 · 与相关能力域的关系

| 关联 | 关系 |
|---|---|
| 算子与 kernel | kernel 从 OpKernelContext 申请输出张量的缓冲 |
| 设备与后端 | 张量所在设备决定用哪个 Allocator；跨设备靠 Send/Recv 拷贝 |
| XLA | 融合后中间张量不落显存，直接留在寄存器/共享内存 |
| 执行引擎 | Executor 管张量在节点间的传递与生命周期 |

## 调优要点

- **显存 OOM 优先查碎片与峰值**：BFC 已池化，但峰值仍受同时存活张量制约；减小 batch、开梯度检查点（重算换显存）。
- **避免无谓拷贝**：优先用视图（reshape/slice）而非复制；跨设备传输是显式 Send/Recv，减少跨设备来回。
- **混合精度省显存**：float16/bfloat16 激活占用减半。
- **`TF_GPU_ALLOCATOR` / 显存增长**：`set_memory_growth` 按需增长而非一次占满，多进程共享 GPU 时有用。

## 常见误区

- **"每个 Tensor 独占一块内存"**：错。视图张量共享同一 TensorBuffer，靠引用计数管生命周期。
- **"GPU 显存用 cudaMalloc 逐次分配"**：默认走 BFC 池化分配器，不是每个张量一次 cudaMalloc。
- **"reshape 会复制数据"**：通常不会，只改元信息、共享缓冲（除非需要连续化）。
- **"TF 一启动就占满显存是 bug"**：默认行为（预占以减碎片）；要按需增长得显式开 memory growth。

## 一句话总纲

**张量是"轻元信息 + 引用计数的共享缓冲"：视图零拷贝复用底层内存，缓冲用引用计数管生命周期；内存按设备由 Allocator 分配，GPU 靠 BFC 池化显存避免频繁 cudaMalloc——这是所有算子计算的内存底座。**
