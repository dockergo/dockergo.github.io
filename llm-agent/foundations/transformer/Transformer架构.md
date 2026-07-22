@eco

Transformer 是当代几乎所有 LLM 的骨架，彻底抛弃循环与卷积，只堆叠两种算子：**自注意力**让每个 token 一次性看见所有其他 token，**前馈网络**对每个位置做非线性变换。无循环依赖→整段序列可并行，这是它能扩到千亿参数的根本原因。数据旅程：Token→嵌入+位置编码→N 个相同 Block（多头自注意力+FFN，两子层均包「残差+归一化」）→输出投影+softmax 得下一 token 分布。见生态图。

@f1

三种形态：**Encoder** 双向注意力、擅理解（BERT）；**Decoder** 因果掩码只看左侧、天然自回归生成，是主流 LLM（GPT）的选择；**Encoder-Decoder** 加交叉注意力（Decoder Query 查 Encoder 的 K/V），适合翻译摘要（T5）。核心都是**堆叠 N 个相同 Block**——浅层捕词法局部、深层抽象句法语义。深度与宽度决定容量，也带来训练难度与显存压力。见图。

@f2

**残差连接**解决深层梯度衰减：子层输出为 `x + F(x)`，恒等直连让梯度无损穿透直达底部，子层只学「增量」、最坏退化为恒等映射不伤表征。**层归一化（LayerNorm）** 对每样本沿特征维归一化再缩放平移，不依赖 batch、适配变长序列。**Pre-LN**（`x + F(LN(x))`）比 Post-LN 更利深层大模型稳定收敛，被现代 LLM 广泛采用；RMSNorm 是其省算力简化版。见图。

@f3

注意力只做「加权求和」，缺非线性与存储容量。**前馈网络（FFN）** 对每个位置**独立**做「升维→非线性激活→降维」，通常扩 4 倍经 GELU/SwiGLU 再压回。它是参数主要归宿（约占全模型 **2/3**）与推理算力主要来源。研究把它理解为**键值记忆**：W1 匹配输入模式、W2 取回内容，事实性知识存于此。位置间不交互→高度并行，等价于 kernel=1 卷积。见图。

@cmp

三构件职责分明、缺一不可：**整体结构**决定如何并行处理整序列并保留依赖（代价：深堆训练难+算力开销）、**残差与归一化**是「训得动」的前提（极小开销换梯度稳定与收敛加速）、**前馈网络**提供非线性表达与知识容量、是「记得住」关键（吃掉大部分参数与推理算力）。一句话：**结构给骨架、残差归一让它训得动、FFN 让它记得住**。四维对照见图。

@eng

三主线：**架构选型**——现代大模型一致收敛到 **Decoder-only**（训练目标统一、推理路径简单、最易规模化），层数/隐藏维/头数定义规模；**稳定训练**——Pre-LN 或 RMSNorm、残差缩放、学习率 warmup、梯度裁剪、bf16 混合精度、随深度缩放的初始化；**算力优化**——FlashAttention 融合核省显存、张量/流水/序列并行、激活重计算换显存、KV-Cache 与量化加速推理。本质是权衡：**先能训得动、再算得快、最后追效果**。详见图。

@refs

- Vaswani et al., "Attention Is All You Need"（Transformer 原始论文）
- "On Layer Normalization in the Transformer Architecture"（Pre-LN vs Post-LN）
- "GLU Variants Improve Transformer"（SwiGLU 等门控激活）
- "FlashAttention: Fast and Memory-Efficient Exact Attention"
- "Scaling Laws for Neural Language Models"（规模与效果关系）