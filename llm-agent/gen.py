#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI Agents 生态图谱生成器（llm-agent/gen.py）—— 「按模块」组织的多智能体系统原理图谱。

与 topics/（计算系统主题）平行，这里按 **AI Agents 生态的核心模块**（概念层，
不点名具体框架）组织：一个生态架构总图 + 若干机理图解点（机理图 + 短注解）。

产物（全部自包含、仅标准库、离线、SVG 全部 base64 内联、双主题 + 记忆切换）：
  llm-agent/index.html            —— 门户：6 张模块卡片（标题 + 核心一句 + 机理点预览）
  llm-agent/<slug>/index.html     —— 模块页：判型标题带 → 生态架构总图 → 机理图解点 → 对比

设计文件命名（各模块 design/ 目录内）：
  生态架构  <模块中文>_00生态架构.svg
  机理图    <模块中文>_01xxx.svg / _02xxx.svg …
  对比      <模块中文>_CMP机制对比.svg / _ENG工程对比.svg
  注解散文  <模块中文>.md   （用 @eco / @xx / @cmp / @eng / @refs 分节）

用法：  cd llm-agent && python3 gen.py
"""
import base64
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# ===================================================================== #
# 一、片区元数据（ZONES）+ 模块内容契约（THEMES）
#   ZONES：门户分两大片区 —— Agents 生态 / LLM 原理
#   THEMES：每个 theme 用 "zone" 归属到某片区；模块页渲染两片区共用同一套骨架
# ===================================================================== #
ZONES = [
    {"id": "agents", "name": "Agents 生态", "en": "AI Agents Ecosystem",
     "desc": "从「一次问答」到「自主 Agent」：抽掉具体框架，只看构成多智能体系统的核心模块如何自洽拼合。"},
    {"id": "llm", "name": "LLM 原理", "en": "LLM Foundations",
     "desc": "语言模型本体的架构与工程理论：从 Transformer 的一层层堆叠，到预训练、对齐、推理落地的完整链路。"},
]

THEMES = [
    {
        "slug": "reasoning", "cn": "推理循环", "zone": "agents",
        "en": "Reasoning & Planning Loop",
        "title": "Reasoning & Planning · Agent 推理与规划循环",
        "core": "把「一次问答」变成「感知→思考→行动→观察」的闭环：LLM 在每一步依据历史轨迹决定下一动作，直到目标达成或预算耗尽。",
        "color": "#0a84ff", "eco": "推理循环_00生态架构.svg",
        "groups": [
            {"algo": "ReAct", "mechs": [
                {"n": "R1", "title": "思考-行动-观察交织", "svg": "推理循环_01ReAct循环.svg"},
            ]},
            {"algo": "Plan-and-Execute", "mechs": [
                {"n": "R2", "title": "先规划全局再逐步执行", "svg": "推理循环_02规划执行.svg"},
            ]},
            {"algo": "Reflexion", "mechs": [
                {"n": "R3", "title": "失败反思写入记忆重试", "svg": "推理循环_03反思重试.svg"},
            ]},
            {"algo": "Tree-of-Thoughts", "mechs": [
                {"n": "R4", "title": "多分支搜索 + 自评剪枝", "svg": "推理循环_04思维树.svg"},
            ]},
        ],
        "compare": {"svg": "推理循环_CMP机制对比.svg"},
        "eng": {"svg": "推理循环_ENG工程对比.svg"},
    },
    {
        "slug": "tooluse", "cn": "工具调用", "zone": "agents",
        "en": "Tool Use & Function Calling",
        "title": "Tool Use · 工具调用与外部行动",
        "core": "给语言模型装上「手」:模型输出结构化调用意图,运行时执行真实副作用,再把结果回灌上下文——语言与世界由此闭环。",
        "color": "#a78bfa", "eco": "工具调用_00生态架构.svg",
        "groups": [
            {"algo": "Function Calling", "mechs": [
                {"n": "T1", "title": "Schema 约束的结构化调用", "svg": "工具调用_01结构化调用.svg"},
            ]},
            {"algo": "工具路由", "mechs": [
                {"n": "T2", "title": "海量工具的检索式选择", "svg": "工具调用_02工具路由.svg"},
            ]},
            {"algo": "MCP 协议", "mechs": [
                {"n": "T3", "title": "标准化工具/资源接入层", "svg": "工具调用_03MCP协议.svg"},
            ]},
            {"algo": "代码执行", "mechs": [
                {"n": "T4", "title": "沙箱内 Code-as-Action", "svg": "工具调用_04代码执行.svg"},
            ]},
        ],
        "compare": {"svg": "工具调用_CMP机制对比.svg"},
        "eng": {"svg": "工具调用_ENG工程对比.svg"},
    },
    {
        "slug": "memory", "cn": "记忆系统", "zone": "agents",
        "en": "Agent Memory",
        "title": "Agent Memory · 智能体记忆系统",
        "core": "上下文窗口是易失的工作台,长期记忆是可回溯的仓库:写入-检索-遗忘三态循环,让 Agent 跨会话保持连贯与个性化。",
        "color": "#2dd4bf", "eco": "记忆系统_00生态架构.svg",
        "groups": [
        {"algo": "短期/工作记忆", "mechs": [
                {"n": "M1", "title": "对话缓冲与滚动摘要", "svg": "记忆系统_01短期记忆.svg"},
            ]},
            {"algo": "长期记忆", "mechs": [
                {"n": "M2", "title": "向量化存储与语义检索", "svg": "记忆系统_02长期记忆.svg"},
            ]},
            {"algo": "记忆管理", "mechs": [
                {"n": "M3", "title": "写入判定与遗忘衰减", "svg": "记忆系统_03记忆管理.svg"},
            ]},
        ],
        "compare": {"svg": "记忆系统_CMP机制对比.svg"},
        "eng": {"svg": "记忆系统_ENG工程对比.svg"},
    },
    {
        "slug": "rag", "cn": "检索增强", "zone": "agents",
        "en": "Retrieval-Augmented Generation",
        "title": "RAG · 检索增强生成",
        "core": "把外部知识变成可检索的向量索引,在生成前召回相关片段注入上下文:用检索的确定性补足参数记忆的模糊与过时。",
        "color": "#4a9eff", "eco": "检索增强_00生态架构.svg",
        "groups": [
            {"algo": "索引构建", "mechs": [
                {"n": "G1", "title": "分块 + 嵌入 + 建索引", "svg": "检索增强_01索引构建.svg"},
            ]},
            {"algo": "检索召回", "mechs": [
                {"n": "G2", "title": "向量 + 关键词混合检索", "svg": "检索增强_02混合检索.svg"},
            ]},
            {"algo": "重排与生成", "mechs": [
                {"n": "G3", "title": "Rerank 精排 + 上下文压缩", "svg": "检索增强_03重排生成.svg"},
            ]},
            {"algo": "GraphRAG", "mechs": [
                {"n": "G4", "title": "实体图谱 + 社区摘要", "svg": "检索增强_04图谱检索.svg"},
            ]},
        ],
        "compare": {"svg": "检索增强_CMP机制对比.svg"},
        "eng": {"svg": "检索增强_ENG工程对比.svg"},
    },
    {
        "slug": "multiagent", "cn": "多智能体协作", "zone": "agents",
        "en": "Multi-Agent Orchestration",
        "title": "Multi-Agent · 多智能体协作与编排",
        "core": "把一个大任务拆给多个专精 Agent:用编排拓扑决定谁先谁后、用通信协议传递中间态、用仲裁者消解冲突并汇聚结果。",
        "color": "#f5873a", "eco": "多智能体协作_00生态架构.svg",
        "groups": [
            {"algo": "编排拓扑", "mechs": [
                {"n": "A1", "title": "监督者 vs 去中心化网络", "svg": "多智能体协作_01编排拓扑.svg"},
            ]},
            {"algo": "角色分工", "mechs": [
                {"n": "A2", "title": "规划者/执行者/评审者", "svg": "多智能体协作_02角色分工.svg"},
            ]},
            {"algo": "通信协作", "mechs": [
                {"n": "A3", "title": "黑板 + 消息传递", "svg": "多智能体协作_03通信协作.svg"},
            ]},
        ],
        "compare": {"svg": "多智能体协作_CMP机制对比.svg"},
        "eng": {"svg": "多智能体协作_ENG工程对比.svg"},
    },
    {
        "slug": "context", "cn": "上下文工程", "zone": "agents",
        "en": "Context Engineering",
        "title": "Context Engineering · 上下文工程与窗口管理",
        "core": "上下文窗口是 Agent 唯一的「视野」:在有限 token 预算内,决定塞什么、怎么排、何时压缩,直接决定推理质量与成本。",
        "color": "#c084fc", "eco": "上下文工程_00生态架构.svg",
        "groups": [
            {"algo": "上下文装配", "mechs": [
                {"n": "C1", "title": "系统提示/工具/记忆的分层拼装", "svg": "上下文工程_01上下文装配.svg"},
            ]},
            {"algo": "KV-Cache 复用", "mechs": [
                {"n": "C2", "title": "前缀稳定换缓存命中", "svg": "上下文工程_02前缀缓存.svg"},
            ]},
            {"algo": "压缩与卸载", "mechs": [
                {"n": "C3", "title": "摘要压缩 + 外部卸载", "svg": "上下文工程_03压缩卸载.svg"},
            ]},
        ],
        "compare": {"svg": "上下文工程_CMP机制对比.svg"},
        "eng": {"svg": "上下文工程_ENG工程对比.svg"},
    },
    # ================= 片区 B：LLM 原理 =================
    {
        "slug": "transformer", "cn": "Transformer架构", "zone": "llm",
        "en": "Transformer Architecture",
        "title": "Transformer · 现代大模型的骨架",
        "core": "抛弃循环与卷积，只用「自注意力 + 前馈」堆叠：每个 token 一次性看见全序列，用残差与归一化稳住深层梯度，用并行换来规模。",
        "color": "#0a84ff", "eco": "Transformer架构_00生态架构.svg",
        "groups": [
            {"algo": "整体结构", "mechs": [
                {"n": "F1", "title": "编码器/解码器与堆叠层", "svg": "Transformer架构_01整体结构.svg"},
            ]},
            {"algo": "子层构造", "mechs": [
                {"n": "F2", "title": "残差连接 + 层归一化", "svg": "Transformer架构_02残差归一.svg"},
            ]},
            {"algo": "前馈网络", "mechs": [
                {"n": "F3", "title": "逐位置 FFN 与激活", "svg": "Transformer架构_03前馈网络.svg"},
            ]},
        ],
        "compare": {"svg": "Transformer架构_CMP机制对比.svg"},
        "eng": {"svg": "Transformer架构_ENG工程对比.svg"},
    },
    {
        "slug": "attention", "cn": "注意力机制", "zone": "llm",
        "en": "Attention Mechanism",
        "title": "Attention · 让 token 彼此对话",
        "core": "用 Query·Key 的点积算出「谁该关注谁」，再对 Value 加权求和：多头让模型在不同子空间并行捕捉多种关系。",
        "color": "#5e5ce6", "eco": "注意力机制_00生态架构.svg",
        "groups": [
            {"algo": "缩放点积", "mechs": [
                {"n": "N1", "title": "QKV 与 softmax 加权", "svg": "注意力机制_01缩放点积.svg"},
            ]},
            {"algo": "多头注意力", "mechs": [
                {"n": "N2", "title": "多子空间并行 + 拼接投影", "svg": "注意力机制_02多头注意力.svg"},
            ]},
            {"algo": "高效注意力", "mechs": [
                {"n": "N3", "title": "因果掩码与 FlashAttention", "svg": "注意力机制_03高效注意力.svg"},
            ]},
        ],
        "compare": {"svg": "注意力机制_CMP机制对比.svg"},
        "eng": {"svg": "注意力机制_ENG工程对比.svg"},
    },
    {
        "slug": "posenc", "cn": "位置编码", "zone": "llm",
        "en": "Positional Encoding",
        "title": "Positional Encoding · 给序列注入顺序",
        "core": "自注意力本身对顺序无感，必须显式告诉模型「谁在前谁在后」：从正弦绝对位置，到可学习、再到旋转式相对位置。",
        "color": "#2dd4bf", "eco": "位置编码_00生态架构.svg",
        "groups": [
            {"algo": "绝对位置", "mechs": [
                {"n": "P1", "title": "正弦编码与可学习编码", "svg": "位置编码_01绝对位置.svg"},
            ]},
            {"algo": "相对位置", "mechs": [
                {"n": "P2", "title": "RoPE 旋转位置编码", "svg": "位置编码_02旋转编码.svg"},
            ]},
            {"algo": "长度外推", "mechs": [
                {"n": "P3", "title": "插值与 NTK 扩展窗口", "svg": "位置编码_03长度外推.svg"},
            ]},
        ],
        "compare": {"svg": "位置编码_CMP机制对比.svg"},
        "eng": {"svg": "位置编码_ENG工程对比.svg"},
    },
    {
        "slug": "pretrain", "cn": "预训练", "zone": "llm",
        "en": "Pre-training",
        "title": "Pre-training · 从海量文本自监督学习",
        "core": "在无标注语料上用「预测下一个 token」自监督学习：数据配比、tokenizer、Scaling Law 与训练稳定性共同决定基座能力上限。",
        "color": "#4a9eff", "eco": "预训练_00生态架构.svg",
        "groups": [
            {"algo": "训练目标", "mechs": [
                {"n": "E1", "title": "自回归 vs 掩码语言建模", "svg": "预训练_01训练目标.svg"},
            ]},
            {"algo": "数据与分词", "mechs": [
                {"n": "E2", "title": "语料清洗与 BPE 分词", "svg": "预训练_02数据分词.svg"},
            ]},
            {"algo": "规模法则", "mechs": [
                {"n": "E3", "title": "Scaling Law 与算力配比", "svg": "预训练_03规模法则.svg"},
            ]},
        ],
        "compare": {"svg": "预训练_CMP机制对比.svg"},
        "eng": {"svg": "预训练_ENG工程对比.svg"},
    },
    {
        "slug": "finetune", "cn": "微调对齐", "zone": "llm",
        "en": "Fine-tuning & Alignment",
        "title": "Fine-tuning · 从基座到可用助手",
        "core": "基座只会续写，要变成听话的助手需两步：SFT 用示范数据教「怎么答」，RLHF/DPO 用偏好信号教「答得更好」，PEFT 让这一切低成本。",
        "color": "#f5873a", "eco": "微调对齐_00生态架构.svg",
        "groups": [
            {"algo": "监督微调", "mechs": [
                {"n": "S1", "title": "指令数据 SFT", "svg": "微调对齐_01监督微调.svg"},
            ]},
            {"algo": "偏好对齐", "mechs": [
                {"n": "S2", "title": "RLHF 与 DPO", "svg": "微调对齐_02偏好对齐.svg"},
            ]},
            {"algo": "参数高效", "mechs": [
                {"n": "S3", "title": "LoRA / Adapter", "svg": "微调对齐_03参数高效.svg"},
            ]},
        ],
        "compare": {"svg": "微调对齐_CMP机制对比.svg"},
        "eng": {"svg": "微调对齐_ENG工程对比.svg"},
    },
    {
        "slug": "inference", "cn": "推理优化", "zone": "llm",
        "en": "Inference Optimization",
        "title": "Inference · 让大模型跑得起、跑得快",
        "core": "推理成本集中在自回归解码与显存带宽：KV-Cache 省重算、量化蒸馏压体积、连续批处理与 PagedAttention 榨干吞吐。",
        "color": "#c084fc", "eco": "推理优化_00生态架构.svg",
        "groups": [
            {"algo": "KV-Cache", "mechs": [
                {"n": "I1", "title": "缓存历史键值免重算", "svg": "推理优化_01KV缓存.svg"},
            ]},
            {"algo": "模型压缩", "mechs": [
                {"n": "I2", "title": "量化 / 蒸馏 / 剪枝", "svg": "推理优化_02模型压缩.svg"},
            ]},
            {"algo": "服务调度", "mechs": [
                {"n": "I3", "title": "连续批处理 + PagedAttention", "svg": "推理优化_03服务调度.svg"},
            ]},
        ],
        "compare": {"svg": "推理优化_CMP机制对比.svg"},
        "eng": {"svg": "推理优化_ENG工程对比.svg"},
    },
]

# ===================================================================== #
# 二、文件读取 / base64 内联 / markdown 行内
# ===================================================================== #
_missing = []
_svg_seq = 0  # 内联 SVG 计数,用于 id 命名空间化避免同页多图 defs 冲突


# 片区 → 子目录:llm 原理 6 模块收纳进 foundations/ 子目录,agents 直接在 llm/ 下
ZONE_SUBDIR = {"llm": "foundations"}


def _rel(th):
    """模块目录相对 llm/ 的路径(用于文件读写 & 门户链接)。
    llm zone → foundations/<slug>;agents zone → <slug>。"""
    sub = ZONE_SUBDIR.get(th.get("zone"))
    return "%s/%s" % (sub, th["slug"]) if sub else th["slug"]


def _up(th):
    """模块页返回门户的相对前缀:深一层子目录需多一级 ../。"""
    return "../../" if th.get("zone") in ZONE_SUBDIR else "../"


def _design_dir(rel):
    return os.path.join(HERE, *rel.split("/"), "design")


def _read(rel, fname):
    p = os.path.join(_design_dir(rel), fname)
    if not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def _b64_svg(rel, fname):
    p = os.path.join(_design_dir(rel), fname)
    if not os.path.isfile(p):
        _missing.append("%s/%s" % (rel, fname))
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# design SVG 全是浅色硬编码着色（白底/深字/灰线/浅底块）。内联后无法随
# data-theme 切换，故按「结构中性色 → CSS 变量」映射:浅色下 fallback 回原
# 色不变，深色下由页面 --sc-* 变量翻转。品牌强调色(紫/蓝/青/橙)深浅通用，
# 不映射保持不变。键必须小写，与 SVG 里的 fill/stroke 写法一致。
_SVG_THEME_MAP = {
    # 面板 / 卡片底：白 → 深色面板
    "#fbfbfd": "var(--sc-bg,#fbfbfd)",
    "#ffffff": "var(--sc-panel,#ffffff)",
    "#f5f5f7": "var(--sc-panel,#f5f5f7)",
    # 主文字：深 → 浅
    "#1d1d1f": "var(--sc-ink,#1d1d1f)",
    "#424245": "var(--sc-ink2,#424245)",
    # 次要 / 说明文字：中灰（深浅都可读，仍给变量微调）
    "#6e6e73": "var(--sc-sub,#6e6e73)",
    "#86868b": "var(--sc-sub,#86868b)",
    "#9aa0a6": "var(--sc-sub,#9aa0a6)",
    "#a1a1a6": "var(--sc-sub,#a1a1a6)",
    # 描边 / 分隔线：浅灰 → 深灰
    "#d2d2d7": "var(--sc-line,#d2d2d7)",
    "#e5e5ea": "var(--sc-line,#e5e5ea)",
    "#e2e2e6": "var(--sc-line,#e2e2e6)",
    "#e0e0e5": "var(--sc-line,#e0e0e5)",
    "#b8b8bf": "var(--sc-line2,#b8b8bf)",
    # 浅色语义填充块：深色下压暗，避免大面积亮块刺眼
    "#eef4ff": "var(--sc-fill-blue,#eef4ff)",
    "#eaf3ff": "var(--sc-fill-blue,#eaf3ff)",
    "#dbeafe": "var(--sc-fill-blue,#dbeafe)",
    "#f3ecff": "var(--sc-fill-purple,#f3ecff)",
    "#e9e6ff": "var(--sc-fill-purple,#e9e6ff)",
    "#f3e8ff": "var(--sc-fill-purple,#f3e8ff)",
    "#e5e0f0": "var(--sc-fill-purple,#e5e0f0)",
    "#fff3ea": "var(--sc-fill-orange,#fff3ea)",
    "#f7e4d3": "var(--sc-fill-orange,#f7e4d3)",
    "#e9fbf6": "var(--sc-fill-teal,#e9fbf6)",
    "#e6fbf6": "var(--sc-fill-teal,#e6fbf6)",
    "#c9efe7": "var(--sc-fill-teal,#c9efe7)",
    "#d5f2eb": "var(--sc-fill-teal,#d5f2eb)",
}

_SVG_COLOR_RE = re.compile(
    "(" + "|".join(re.escape(k) for k in _SVG_THEME_MAP) + ")", re.IGNORECASE)


def _themed_svg(rel, fname):
    """读取 design SVG 原文并内联(而非 base64<img>),把结构中性色替换为
    CSS 变量,使其能随页面 data-theme 主题切换。品牌强调色保持不变。
    同页多次内联时 defs 内 id(filter/marker/gradient 等)会重名冲突,
    故为本图所有 id 及其 url(#..)/href="#.." 引用加唯一前缀隔离。
    找不到文件返回空串并登记 _missing。"""
    txt = _read(rel, fname)
    if not txt:
        _missing.append("%s/%s" % (rel, fname))
        return ""
    txt = _SVG_COLOR_RE.sub(lambda m: _SVG_THEME_MAP[m.group(1).lower()], txt)
    # id 命名空间化:防止同页多图 defs(filter/marker/gradient)id 冲突串味
    global _svg_seq
    _svg_seq += 1
    pfx = "s%d_" % _svg_seq
    ids = set(re.findall(r'\bid="([^"]+)"', txt))
    for _id in ids:
        e = re.escape(_id)
        txt = re.sub(r'\bid="%s"' % e, 'id="%s%s"' % (pfx, _id), txt)
        txt = re.sub(r'url\(#%s\)' % e, 'url(#%s%s)' % (pfx, _id), txt)
        txt = re.sub(r'(href)="#%s"' % e, r'\1="#%s%s"' % (pfx, _id), txt)
    # 加 class 便于外层 CSS 兜底控制;去掉可能的前导空白
    txt = txt.replace("<svg ", '<svg class="figsvg" ', 1)
    return txt.strip()


def _md_inline(s):
    """行内 markdown → HTML：链接 → bold → code。escape 后再匹配（url 里无 * `，安全）。"""
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener" class="ref">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _md_para(body):
    """把一段散文（可能多行）转成若干 <p>。空行分段。"""
    body = (body or "").strip()
    if not body:
        return ""
    chunks = re.split(r"\n\s*\n", body)
    return "".join("<p>%s</p>" % _md_inline(c.strip().replace("\n", " "))
                   for c in chunks if c.strip())


def parse_prose(slug, cn):
    """读取 <cn>.md，按任意 @marker 分节（@eco / @r1 / @cmp / @refs …），返回 dict。"""
    txt = _read(slug, cn + ".md")
    buf = {}
    cur = None
    for line in txt.splitlines():
        m = re.match(r"^@(\w+)\s*$", line.strip())
        if m:
            cur = m.group(1).lower()
            buf.setdefault(cur, [])
            continue
        if cur is not None:
            buf[cur].append(line)
    return {k: _md_para("\n".join(v)) for k, v in buf.items()}


def esc(s):
    return html.escape(str(s), quote=True)


# ===================================================================== #
# 三、页面模板：CSS（双主题 graphite / light）+ JS（记忆切换）
# ===================================================================== #
CSS = r"""
:root{
  --c-bg:#fbfbfd; --c-card:#ffffff; --c-card2:#f5f5f7; --c-ink:#1d1d1f;
  --c-ink2:#6e6e73; --c-ink3:#a1a1a6; --c-line:#e6e6ea; --c-edge:#d2d2d7;
  --c-panel:#ffffff; --c-shadow:rgba(0,0,0,.08);
}
html[data-theme="dark"]{
  --c-bg:#0d0d0f; --c-card:#17171a; --c-card2:#1e1e22; --c-ink:#f2f2f5;
  --c-ink2:#a1a1a6; --c-ink3:#6e6e73; --c-line:#2a2a30; --c-edge:#33333a;
  --c-panel:#161619; --c-shadow:rgba(0,0,0,.5);
  /* 架构图内联 SVG 结构中性色深色翻转(品牌强调色不变) */
  --sc-bg:#17171a; --sc-panel:#1e1e22; --sc-ink:#e8e8ea; --sc-ink2:#c4c4c8;
  --sc-sub:#9a9aa2; --sc-line:#33333a; --sc-line2:#3d3d45;
  --sc-fill-blue:#16253d; --sc-fill-purple:#241d3a; --sc-fill-orange:#382214; --sc-fill-teal:#0f3330;
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
.tt-ico{font-size:16px;line-height:1}.tt-moon{display:none}
html[data-theme="dark"] .tt-sun{display:none}html[data-theme="dark"] .tt-moon{display:inline}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 80px}

/* ---- 门户 hero ---- */
.hero{margin:6px 0 26px}
.hero h1{font-size:26px;font-weight:800;letter-spacing:.2px}
.hero .sub{margin-top:8px;font-size:13.5px;color:var(--c-ink2);max-width:820px}
.hero .back{display:inline-flex;align-items:center;gap:6px;margin-bottom:14px;
  font-size:12.5px;color:var(--c-ink2);border:1px solid var(--c-line);
  border-radius:999px;padding:5px 13px;background:var(--c-panel)}
.hero .back:hover{color:var(--c-ink);border-color:var(--c-edge)}

/* ---- 门户卡片栅格 ---- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px}
.card{position:relative;display:block;background:var(--c-card);border:1px solid var(--c-line);
  border-radius:16px;padding:20px 20px 18px;overflow:hidden;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}
.card:hover{transform:translateY(-3px);border-color:var(--acc);box-shadow:0 10px 30px var(--c-shadow)}
.card .bar{position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--acc)}
.card .k{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.6px;
  color:var(--acc);text-transform:uppercase;margin-bottom:8px}
.card h3{font-size:17px;font-weight:750;line-height:1.35;color:var(--c-ink)}
.card .core{margin-top:9px;font-size:12.5px;color:var(--c-ink2);line-height:1.6}
.card .tags{margin-top:14px;display:flex;flex-direction:column;gap:7px}
.card .tag{display:flex;gap:8px;align-items:baseline;font-size:12px;color:var(--c-ink2)}
.card .tag .n{font-weight:800;color:var(--acc);flex:none;font-variant-numeric:tabular-nums}
.card .go{margin-top:16px;font-size:12px;font-weight:700;color:var(--acc);display:inline-flex;align-items:center;gap:5px}

/* ---- 模块页 ---- */
.judge{background:var(--c-card);border:1px solid var(--c-line);border-left:4px solid var(--acc);
  border-radius:14px;padding:18px 22px;margin-bottom:26px}
.judge .k{font-size:11px;font-weight:700;letter-spacing:.6px;color:var(--acc);text-transform:uppercase}
.judge h1{font-size:22px;font-weight:800;line-height:1.34;margin-top:7px}
.judge .core{margin-top:11px;font-size:13.5px;color:var(--c-ink2);line-height:1.7;max-width:900px}
.secttl{display:flex;align-items:center;gap:11px;margin:34px 0 14px}
.secttl .badge{flex:none;min-width:30px;height:30px;padding:0 9px;border-radius:9px;background:var(--acc);
  color:#fff;font-weight:800;font-size:15px;display:inline-grid;place-items:center}
.secttl .t{font-size:17px;font-weight:750}
.secttl.eco .badge{background:var(--c-ink);color:var(--c-bg)}
/* ── 垂直 TAB 布局 ── */
.vt-wrap{display:flex;gap:22px;margin-top:26px;align-items:flex-start}
.vt-nav{flex:none;width:236px;position:sticky;top:20px;display:flex;flex-direction:column;gap:8px}
.vt-grp{font-size:11px;font-weight:800;letter-spacing:.04em;color:var(--c-ink3);
  text-transform:none;margin:14px 4px 2px;padding-top:8px;border-top:1px solid var(--c-line)}
.vt-grp:first-child{margin-top:0;padding-top:0;border-top:none}
.vt-tab{display:flex;align-items:center;gap:10px;text-align:left;cursor:pointer;
  background:var(--c-card);border:1px solid var(--c-line);border-radius:12px;
  padding:12px 13px;color:var(--c-ink2);font:inherit;transition:.15s}
.vt-tab:hover{border-color:var(--acc);color:var(--c-ink)}
.vt-tab.active{background:var(--acc);border-color:var(--acc);color:#fff;box-shadow:0 4px 14px -6px var(--acc)}
.vt-tab .vt-b{flex:none;min-width:26px;height:26px;padding:0 7px;border-radius:8px;
  background:var(--c-card2);color:var(--acc);font-weight:800;font-size:13px;
  display:inline-grid;place-items:center}
.vt-tab.active .vt-b{background:rgba(255,255,255,.24);color:#fff}
.vt-tab .vt-l{font-size:12.5px;font-weight:650;line-height:1.35}
.vt-stage{flex:1;min-width:0}
.vt-sec{display:none}
.vt-sec.active{display:block;animation:vtfade .22s ease}
.vt-sec .secttl{margin-top:0}
@keyframes vtfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(max-width:820px){.vt-wrap{flex-direction:column}.vt-nav{position:static;width:100%;flex-direction:row;flex-wrap:wrap}.vt-tab{flex:1 1 44%}}
.fig{background:var(--c-card);border:1px solid var(--c-line);border-radius:16px;
  padding:16px;overflow:hidden}
.fig img{display:block;width:100%;height:auto;border-radius:8px}
.fig .figsvg{display:block;width:100%;height:auto;border-radius:8px}
.blurb{margin-top:14px;background:var(--c-card);border:1px solid var(--c-line);
  border-radius:14px;padding:15px 19px}
.blurb p{font-size:13px;color:var(--c-ink2);line-height:1.75}
.blurb p+p{margin-top:9px}
.blurb b{color:var(--c-ink);font-weight:700}
.blurb code{font-family:'SF Mono',ui-monospace,Menlo,monospace;font-size:.88em;
  background:var(--c-card2);border:1px solid var(--c-line);border-radius:5px;padding:1px 5px;color:var(--acc)}
.blurb a{color:var(--acc);text-decoration:none;
  border-bottom:1px solid color-mix(in srgb,var(--acc) 40%,transparent);transition:border-color .15s}
.blurb a:hover{border-bottom-color:var(--acc)}
.refs{margin-top:30px;padding-top:18px;border-top:2px solid var(--c-line)}
.reflist{margin-top:12px}
.reflist p{margin:5px 0;font-size:12.5px;color:var(--c-ink2);line-height:1.7}
.reflist a{color:var(--acc)}
.miss{padding:40px;text-align:center;color:var(--c-ink3);font-size:13px;border:1px dashed var(--c-edge);border-radius:12px}
.backrow{margin-top:44px;padding-top:22px;border-top:1px solid var(--c-line)}
.backrow a{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--c-ink2);
  border:1px solid var(--c-line);border-radius:999px;padding:8px 16px;background:var(--c-panel)}
.backrow a:hover{color:var(--c-ink);border-color:var(--c-edge)}
footer{max-width:1180px;margin:0 auto;padding:0 24px 40px;color:var(--c-ink3);font-size:11.5px}

/* ---- 门户片区切换 tab + 片区标题条 ---- */
.zbar{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap}
.zseg{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;
  color:var(--c-ink2);border:1px solid var(--c-line);border-radius:999px;
  padding:8px 16px;background:var(--c-panel);transition:.15s}
.zseg:hover{color:var(--c-ink);border-color:var(--c-edge)}
.zseg.active{color:var(--c-ink);border-color:var(--c-ink);background:var(--c-card)}
.zseg .zn{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--c-card2);
  color:var(--c-ink2);font-size:11px;font-weight:800;display:inline-grid;place-items:center}
.zone{margin-top:38px;scroll-margin-top:80px}
.zone:first-of-type{margin-top:30px}
.zhd{margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--c-line)}
.zhd .zk{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--c-ink3);text-transform:uppercase}
.zhd h2{font-size:20px;font-weight:800;margin-top:5px;color:var(--c-ink)}
.zhd p{font-size:12.5px;color:var(--c-ink2);margin-top:6px;max-width:860px;line-height:1.65}
"""

APP_JS = r"""
(function(){
  var root=document.documentElement;
  var saved=localStorage.getItem('atlas-nav-theme');
  if(saved==='dark') root.setAttribute('data-theme','dark');
  function toggleTheme(){
    var cur=root.getAttribute('data-theme')==='dark'?'':'dark';
    if(cur) root.setAttribute('data-theme',cur); else root.removeAttribute('data-theme');
    localStorage.setItem('atlas-nav-theme',cur||'light');
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
  var zsegs=document.querySelectorAll('.zseg');
  var zones=document.querySelectorAll('.zone');
  if(zsegs.length&&zones.length){
    zsegs.forEach(function(s){
      s.addEventListener('click',function(){
        zsegs.forEach(function(x){x.classList.toggle('active',x===s);});
      });
    });
    if('IntersectionObserver' in window){
      var io=new IntersectionObserver(function(es){
        es.forEach(function(e){
          if(e.isIntersecting){
            var id=e.target.id;
            zsegs.forEach(function(x){x.classList.toggle('active',x.getAttribute('href')==='#'+id);});
          }
        });
      },{rootMargin:'-40% 0px -55% 0px'});
      zones.forEach(function(z){io.observe(z);});
    }
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
<script>(function(){try{var s=localStorage.getItem('atlas-nav-theme');if(s==='dark')document.documentElement.setAttribute('data-theme','dark');}catch(e){}})();</script>
<style>%s</style>
</head>
<body>""" % (esc(title), CSS))


# ===================================================================== #
# 四、门户 index.html
# ===================================================================== #
# （门户 index.html 已废弃删除；根 index.html 的 LLM & Agent 热区直接下钻
#   到各模块子页，子页 home 回到根 index.html#agent，故不再生成独立门户。）


# ===================================================================== #
# 五、模块页 <slug>/index.html
# ===================================================================== #
def build_theme_page(th):
    rel = _rel(th)
    up = _up(th)
    prose = parse_prose(rel, th["cn"])
    acc = th["color"]

    def fig(fname, alt):
        svg = _themed_svg(rel, fname)
        if not svg:
            return '<div class="miss">机理图待绘制：%s</div>' % esc(fname)
        # 内联 SVG(非 base64<img>),使图内颜色能随 data-theme 主题切换
        return '<div class="fig" role="img" aria-label="%s">%s</div>' % (esc(alt), svg)

    head = th["title"].split(" · ")[0]

    nav_groups = []
    secs = []
    first = True

    def add_sec(sid, badge, ttl, fig_svg, prose_key, big=False):
        nonlocal first
        pr = prose.get(prose_key) or ""
        blurb = ('<div class="blurb%s">%s</div>' % (" ml" if big else "", pr)) if pr else ""
        figher = fig(fig_svg, ttl) if fig_svg else ""
        secs.append(
            '<section class="vt-sec%s" id="%s" data-sec="%s">'
            '<div class="secttl"><span class="badge">%s</span>'
            '<span class="t">%s</span></div>%s%s</section>'
            % (" active" if first else "", sid, sid, esc(badge), esc(ttl), figher, blurb))
        first = False

    eco_prose = prose.get("eco") or ('<p>%s</p>' % _md_inline(th["core"]))
    nav_groups.append(("概览 Overview", [("sec-eco", "◎", "生态架构总图")]))
    secs.append(
        '<section class="vt-sec active" id="sec-eco" data-sec="sec-eco">'
        '<div class="secttl eco"><span class="badge">◎</span>'
        '<span class="t">生态架构总图 · 这一模块如何在 Agent 系统中自洽拼合</span></div>'
        '%s<div class="blurb">%s</div></section>'
        % (fig(th["eco"], head + " 生态架构"), eco_prose))
    first = False

    for gi, grp in enumerate(th.get("groups", [])):
        items = []
        for m in grp["mechs"]:
            sid = "sec-%s" % m["n"].lower()
            items.append((sid, m["n"], esc(m["title"])))
            add_sec(sid, m["n"], "%s · %s" % (grp["algo"], m["title"]),
                    m["svg"], m["n"].lower())
        nav_groups.append(("机制 · %s" % grp["algo"], items))

    cmp = th.get("compare") or {}
    if cmp.get("svg"):
        nav_groups.append(("对比 Compare", [("sec-cmp", "⇄", "机制差异对比")]))
        add_sec("sec-cmp", "⇄", head + " · 核心机制差异对比", cmp["svg"], "cmp", big=True)

    eng = th.get("eng") or {}
    if eng.get("svg") or prose.get("eng"):
        nav_groups.append(("工程 Engineering", [("sec-eng", "⚙", "框架实现差异")]))
        add_sec("sec-eng", "⚙", head + " · 工程实现差异（真实框架落地取舍）",
                eng.get("svg"), "eng", big=True)

    refs_html = ""
    if prose.get("refs"):
        refs_html = ('<section class="refs"><div class="secttl"><span class="badge">§</span>'
                     '<span class="t">参考文献 · 权威来源（论文 / 官方文档）</span></div>'
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

    drill = ('<div class="vt-wrap">'
             '<nav class="vt-nav" aria-label="模块内容切换">%s</nav>'
             '<div class="vt-stage">%s</div></div>'
             % (navcol, "".join(secs)))

    body = """%s
<header>
  <a class="logo" href="@@ROOT@@index.html#agent" title="返回 LLM & Agent 导航"><span class="icobtn">%s</span></a>
  <div class="brand-intro">
    <div class="bt">%s</div>
    <div class="bs">AI Agents 生态图谱 · 概念层机理（不点名具体框架）</div>
  </div>
  <div class="spacer"></div>
  %s
</header>
<div class="wrap" style="--acc:%s">
  <div class="judge">
    <span class="k">%s · 定位</span>
    <h1>%s</h1>
    <div class="core">%s</div>
  </div>
  %s
  %s
  <div class="backrow"><a href="@@ROOT@@index.html#agent">← 返回 LLM & Agent 导航</a></div>
</div>
<footer>自包含离线图谱 · 以图为主：概览 + 机制分组图 + 机制对比 · 权威参考集中于底部 · 垂直 TAB 切换</footer>
<script>%s</script>
</body>
</html>""" % (_head(head + " · AI Agents 图谱"), _HOME_SVG, esc(head), _THEME_BTN, esc(acc),
              esc(th["slug"].upper()), th["title"], esc(th["core"]),
              drill, refs_html, APP_JS)
    return body.replace("@@ROOT@@", up + "../").replace("@@UP@@", up)


# ===================================================================== #
# 六、主流程
# ===================================================================== #
def main():
    # 门户页(llm/index.html)已废弃:根 index.html 的「LLM & Agent 总架构」
    # 热区直接下钻到各模块子页,子页 home 亦回到根 #agent,无需独立门户。
    for th in THEMES:
        d = os.path.join(HERE, *_rel(th).split("/"))
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_theme_page(th))
        print("Wrote %s" % out)

    total = sum(1 + sum(len(g["mechs"]) for g in th.get("groups", []))
                + (1 if th.get("compare", {}).get("svg") else 0)
                + (1 if th.get("eng", {}).get("svg") else 0) for th in THEMES)
    print("模块 %d 个 · 模块页 %d(无独立门户)" % (len(THEMES), len(THEMES)))
    if _missing:
        print("  ⚠ 缺失 SVG（%d）：" % len(_missing))
        for m in _missing:
            print("      -", m)
    else:
        print("  ✓ 全部 %d 张 SVG就位，无缺失" % total)


if __name__ == "__main__":
    main()