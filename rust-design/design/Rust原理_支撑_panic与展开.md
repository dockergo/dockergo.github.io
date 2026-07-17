# Rust 原理 · 支撑主线 · panic 与展开

> **定位**：属"错误能力域"。管不可恢复错误的处理:panic 触发、栈展开(unwind)vs 直接终止(abort)两运行时、catch_unwind。是 Rust 崩溃路径的机制。依赖【内存与 Drop】(展开时调 Drop)。源码基准 **Rust 1.99.0**(`library/std/src/panicking.rs`、`library/panic_unwind/`、`library/panic_abort/`)。

Rust 错误分两类:可恢复(`Result`,正常返回)和不可恢复(**panic**,程序逻辑错如数组越界)。panic 时两种运行时行为:**展开(unwind)**——逐层析构栈上的值(调 Drop)后终止,可被 catch_unwind 捕获;**abort**——直接终止进程(不析构)。理解 panic 展开 vs abort + Drop 联动,就懂了 Rust 的崩溃路径。

---

## 一、panic 触发与 handler

![Rust panic 触发](Rust原理_panic_01触发.svg)

panic 从 core 抛出、std 处理:

- **触发**:`panic!` 宏、数组越界、`unwrap()` on None/Err 等 → core 的 panic → std 的 `#[panic_handler]`(`library/std/src/panicking.rs:612` "core crate panic 入口")。
- **流程**:`rust_panic_with_hook`(跑 panic hook,默认打印消息+backtrace)→ `rust_panic(payload)`(`:840`)→ 按 cfg 分展开/abort。
- **panic hook** 可自定义(`std::panic::set_hook`)——改 panic 时的输出(如日志/上报)。

**为什么 handler 分层**:core(no_std)只定义 panic 的"发生",不定策略(展开/abort);std 提供 handler 实现具体行为——嵌入式(no_std)可自定义 handler。

---

## 二、展开 vs abort:两运行时

![Rust 展开vs abort](Rust原理_panic_02展开abort.svg)

panic 后两种运行时(编译期 `-C panic=` 选):

- **展开(unwind,默认)**:`library/panic_unwind`——`__rust_start_panic`(`lib.rs:99`)启动栈展开,**逐层析构栈上的值**(调各 owner 的 Drop,回收资源)、直到线程边界终止。开销大(展开表)但资源正确释放、可 catch。
- **abort**:`library/panic_abort`(`lib.rs:1` "via process aborts")——`__rust_start_panic` 忽略 payload、直接 `__rust_abort()`(`:33`)终止进程,**不析构**。快、小(无展开表)但资源不释放(靠 OS 回收)。

选择:`-C panic=unwind`(默认,可 catch、资源释放)vs `-C panic=abort`(嵌入式/减体积,直接崩)。

**为什么两种**:展开保证 panic 时也析构(RAII 一致)+ 可恢复(catch_unwind);abort 省展开表(减二进制体积)+ 更快崩(嵌入式/确定性)——按场景选。

---

## 三、catch_unwind:边界捕获

![Rust catch_unwind](Rust原理_panic_03catch.svg)

**catch_unwind** 在展开模式下可捕获 panic(不让它跨边界):

- `std::panic::catch_unwind`(`library/std/src/panic.rs:358`,带 `UnwindSafe` 约束)——把可能 panic 的代码包起来,panic 被捕获返回 `Err`,不向上传播。
- 实现用 `intrinsics::catch_unwind`(`panicking.rs:544`);abort 模式下退化为直接 `Ok(f())`(不能捕获,`:494`)。
- **用途**:FFI 边界(不让 panic 跨语言边界,是 UB)、线程边界(线程 panic 不崩主进程)、插件隔离。
- **不是异常处理**:catch_unwind 是最后防线,不该当常规 `try/catch` 用(panic 是逻辑 bug,应修不是常规处理)。

**为什么有捕获但不鼓励常规用**:panic 表示程序 bug(不该发生的),正常错误用 `Result`;catch_unwind 只在边界(FFI/线程/插件)防扩散——不是控制流工具。

---

## 拓展 · panic 关键结构一览

| 结构 | 定义 | 职责 |
|---|---|---|
| panic_handler | `library/std/src/panicking.rs:612` | core panic 入口(std 实现) |
| rust_panic | `panicking.rs:840` | 触发展开/abort |
| panic_unwind | `library/panic_unwind/src/lib.rs:99` | 展开运行时(逐层析构) |
| panic_abort | `library/panic_abort/src/lib.rs:33` | abort 运行时(直接终止) |
| catch_unwind | `library/std/src/panic.rs:358` | 边界捕获 panic |

## 调优要点（理解要点）

- **-C panic=abort**:减二进制体积 + 快崩(嵌入式/容器);牺牲 catch_unwind 和资源析构。
- **panic hook**:`set_hook` 自定义 panic 输出(日志/上报/backtrace)。
- **catch_unwind 用在边界**:FFI 导出函数、线程池 worker——防 panic 跨边界(FFI panic 是 UB)。
- **Result vs panic**:预期错误(文件不存在/解析失败)用 Result;不该发生的 bug(越界/断言)用 panic。

## 常见误区与工程要点

- **误区:panic 是异常,用 catch_unwind 当 try/catch。** panic 表逻辑 bug,常规错误用 Result;catch_unwind 只在边界防扩散,非控制流。
- **误区:panic 总能 catch。** 仅展开模式(-C panic=unwind);abort 模式 catch_unwind 退化不捕获。
- **误区:panic 不析构资源。** 展开模式逐层调 Drop 释放资源(RAII 一致);只有 abort 模式不析构(靠 OS)。
- **误区:Drop 里 panic 没事。** 展开中再 panic = double-panic → abort;Drop 里避免 panic。
- **归属提醒**:展开时调的 Drop 在【内存与 Drop】;panic 触发点(unwrap/越界)是运行时;Result(可恢复错误)是另一条路不在本篇;abort 直接终止不走【内存与 Drop】析构。

## 一句话总纲

**Rust 不可恢复错误用 panic(数组越界/unwrap None,区别可恢复的 Result):core 抛 panic→std 的 #[panic_handler]→rust_panic 按 cfg 分两运行时——展开(unwind,默认,panic_unwind 逐层析构栈上值调 Drop 后终止,可 catch_unwind 捕获,开销大资源正确释放)vs abort(panic_abort,直接 __rust_abort 终止不析构,快小无展开表);catch_unwind 仅展开模式在边界(FFI/线程/插件)捕获防扩散(非常规 try/catch,panic 是 bug 应修);Drop 里再 panic = double-panic→abort。**
