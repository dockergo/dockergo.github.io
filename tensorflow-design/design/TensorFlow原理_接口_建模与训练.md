# TensorFlow 核心原理 · 接口主线 · 建模与训练

> **定位**：接触面主线之一。高层建模与训练入口——Keras `Model`/`Layer` 组织权重、`GradientTape` 求梯度、`optimizer` 更新、`tf.data` 喂数据，串成训练闭环。核实基准：官方源码（`tensorflow/python/eager/backprop.py:705`、`tensorflow/python/data/ops/dataset_ops.py:137`）。

## 一、训练闭环：模型 + 磁带 + 优化器

![训练闭环](TensorFlow原理_建模训练_01训练闭环.svg)

一步训练（`train_step`）：① **Keras Model/Layer** 组织权重——每个 layer 持有若干 `tf.Variable`，`model.trainable_variables` 汇总；② 在 `with tf.GradientTape as tape` 内做前向 `y = model(x)`（`backprop.py:705` 的 GradientTape 边执行边把 op 录到磁带）；③ 算标量 `loss`；④ `tape.gradient(loss, vars)` 沿录制**逆序回放**求 `∂loss/∂w`；⑤ `optimizer.apply_gradients` 把梯度作用到权重（内部 `assign` 更新 Variable）。下一个 batch 重复，权重被逐步优化。整个 train_step 常用 `@tf.function` 包起来追踪成图提速。

## 二、tf.data 输入管线：声明式变换 + 后台预取

![输入管线](TensorFlow原理_建模训练_02输入管线.svg)

`tf.data.Dataset`（`dataset_ops.py:137` `DatasetV2`）是**惰性、声明式**的变换链：`from_tensor_slices`（`:745`）取源 → `map(f)` 逐元素变换 → `shuffle` 乱序 → `batch`（`:1855`）攒批 → `prefetch(AUTOTUNE)`（`:1241`）后台预取下一批。`prefetch` 让 CPU 侧数据准备与 GPU 侧训练计算 **overlap**：GPU 训第 N 批时 CPU 已在备第 N+1 批，加速器不空等。`AUTOTUNE = -1`（`:102`）让运行时按吞吐动态调缓冲与并行度。

## 深化 · 训练的关键部件

| 部件 | 职责 | 源码/说明 |
|---|---|---|
| Keras Model/Layer | 组织权重与前向 | layer 持有 tf.Variable；model.fit 内置训练循环 |
| GradientTape | 录 op、求梯度 | `backprop.py:705`；默认追踪读到的 trainable Variable |
| optimizer | 用梯度更新权重 | apply_gradients → assign Variable（SGD/Adam…） |
| tf.data.Dataset | 输入管线 | `dataset_ops.py:137`；map/batch/prefetch 惰性链 |
| loss / metrics | 目标与评估 | 标量损失驱动反向；metric 累积状态 |

## 拓展 · 两种训练写法

| 写法 | 适用 | 特点 |
|---|---|---|
| 高层 model.compile + model.fit | 标准监督训练 | Keras 内部就是 GradientTape train_step，省心 |
| 自定义 GradientTape 循环 | GAN / 多优化器 / 自定义损失 | 完全掌控前向、梯度、更新时机 |
| 分布式 strategy.run | 多卡/多机 | 在 strategy.scope 内建模型，run 并行副本（见「分布式训练」） |

## 调优要点

- **输入管线加 `prefetch(AUTOTUNE)` 和 `map(num_parallel_calls=AUTOTUNE)`**：GPU 利用率低、卡等数据时的第一优化。
- **train_step 包 `@tf.function`**：追踪成图后 Grappler/XLA 优化，比 eager 循环快得多。
- **persistent tape 只在需要多次求梯度时用**：`persistent=True`（`backprop.py:509` make_vjp 相关）会保留中间量、占更多内存，用完 `del tape`。
- **大 batch + 混合精度**：提升吞吐；配合 optimizer 的 loss scaling 防 float16 下溢。

## 常见误区

- **"GradientTape 会追踪所有东西"**：默认只追踪被读到的 `tf.Variable`；常量张量要 `tape.watch`，或用 `watch_accessed_variables=False`（`backprop.py:763`）关闭自动追踪再手动 watch。
- **"tape 可以反复 gradient"**：默认非持久，`gradient` 调一次后资源即释放；要多次求梯度需 `persistent=True`。
- **"model.fit 和自定义循环性能不同"**：底层都是同一套 train_step；fit 只是把循环写好了。
- **"数据慢就换更快的硬盘"**：多数是管线没并行/没预取；先上 tf.data 的 map 并行 + prefetch。

## 一句话总纲

**建模与训练把张量/变量/图/微分拼成闭环：Keras 组织权重、GradientTape 在 with 上下文录前向再逆序求梯度、optimizer 把梯度 assign 回 Variable、tf.data 在后台预取喂饱加速器——一步 train_step 包成 tf.function 即得图级优化。**
