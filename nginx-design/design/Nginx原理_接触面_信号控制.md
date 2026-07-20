# nginx 核心原理 · 接触面主线 · 信号控制

> **定位**：接触面主线之二——通过向 master 进程发**信号**驱动运行时运维动作（reload/reopen/quit/热升级）。它与"配置指令"分工：配置声明静态行为，信号驱动动态运维；深度依赖**进程与事件模型**（master-worker 生命周期）。核实基准：官方源码 `nginx/src`（`commit 9e32c636`，nginx 1.31.3）。

## 一、信号表：命令 → 信号 → 动作

![信号表](Nginx原理_信号_01信号表.svg)

master 信号表 `signals[]`（`os/unix/ngx_process.c:39`，用 `nginx -s <cmd>` 或 `kill` 发对应信号）：**reload**（SIGHUP，重读配置、起新 worker 旧 worker 优雅退出）、**reopen**（SIGUSR1，重开日志文件配合 logrotate）、**quit**（SIGQUIT，优雅停机处理完存量）、**stop**（SIGTERM，立即停机）、**热升级**（SIGUSR2，拉起新版并存后切换）。

信号只是"触发"——`ngx_signal_handler`（`os/unix/ngx_process.c:319`）在信号上下文里**只置一个 `sig_atomic_t` 标志位**（如 `ngx_reconfigure=1` `:365`、`ngx_reopen=1` `:370`、`ngx_quit=1` `:347`、`ngx_change_binary=1` `:389`），绝不在此做复杂操作（信号上下文可重入性受限）。真正的动作由 master 主循环 `ngx_master_process_cycle`（`os/unix/ngx_process_cycle.c:74`）轮询标志后执行。worker 有自己的一套信号分派（同文件 `:412` 起的分支：`SIGWINCH`/NOACCEPT 停 accept、`SIGQUIT` 优雅退），由 master 经 socketpair 通道或直接信号通知。

---

## 二、reload 与二进制热升级

![reload 与热升级](Nginx原理_信号_02热升级.svg)

**reload（SIGHUP → `ngx_reconfigure`）**：master 主循环见 `if (ngx_reconfigure)`（`os/unix/ngx_process_cycle.c:211`）后 `ngx_reconfigure=0`（`:212`）→ 重新解析配置建新 `ngx_cycle` → 不合法则保留旧 cycle 放弃（旧 worker 照跑）→ 合法则 `ngx_start_worker_processes` fork 新 worker（用新配置开始 accept）→ `ngx_signal_worker_processes`（`:432`）给旧 worker 发 SIGQUIT，旧 worker 停 accept、处理完存量请求后退出。新旧 worker 短暂并存、客户端无感，配置错误不影响在跑的旧配置——"配置即代码"安全演进的关键；内存池随新旧 cycle 交替整体重建。

**reopen（SIGUSR1 → `ngx_reopen`）**：`if (ngx_reopen)`（`:254`）后调 `ngx_reopen_files`（`:257`）重开所有 open_files（日志），配合 logrotate 的 mv。**二进制热升级（SIGUSR2 → `ngx_change_binary`）**：`if (ngx_change_binary)`（`:262`）后 `ngx_new_binary = ngx_exec_new_binary(cycle, ngx_argv)`（`:265`）——旧 master fork+exec 新版 nginx 并通过环境变量继承监听套接字 fd → 新旧两套同端口 accept 并存验证 → 旧 master 收 SIGWINCH（NOACCEPT，`:268`）排空存量 → 确认后给旧 master 发 SIGQUIT 完成切换。全程有回滚安全网：出问题可向旧 master 发 SIGHUP 复活旧 worker、退回旧版本而不丢连接。

---

## 三、失败路径与边界

- **reload 配置非法**：新 cycle 解析失败时 master 释放新 cycle、保留旧 cycle 与旧 worker 继续服务——reload 天然安全，但务必先 `nginx -t`。
- **旧 worker 排空超时**：优雅退出的旧 worker 若存量请求迟迟不完，受 `worker_shutdown_timeout` 约束到点强杀，避免 reload 后旧进程僵留。
- **热升级新版起不来**：`ngx_exec_new_binary`（`:265`）exec 失败时旧 master 继续持有监听、照常服务，热升级中止不影响线上。
- **PID 文件冲突**：热升级期间旧 master 把 pid 文件改名为 `.oldbin`，新 master 写新 pid；回滚时需还原，运维脚本要处理这两个 pid。
- **信号丢失**：`sig_atomic_t` 标志是幂等置位，短时间多次同信号只触发一次动作——不会累积重复 reload。

---

## 拓展 · 信号与效果对照

| 命令 | 信号 | 标志位 | 优雅 | 用途 | 锚点 |
|---|---|---|---|---|---|
| reload | SIGHUP | ngx_reconfigure | ✓ | 换配置不中断 | `os/unix/ngx_process_cycle.c:211` |
| reopen | SIGUSR1 | ngx_reopen | ✓ | 日志切割后重开文件 | `os/unix/ngx_process_cycle.c:254` |
| quit | SIGQUIT | ngx_quit | ✓ | 优雅停机 | `os/unix/ngx_process_cycle.c:203` |
| stop | SIGTERM | ngx_terminate | ✗ | 立即停机 | `os/unix/ngx_process_cycle.c:181` |
| （热升级） | SIGUSR2 | ngx_change_binary | ✓ | 换 nginx 可执行文件 | `os/unix/ngx_process_cycle.c:262` |
| （停 accept） | SIGWINCH | ngx_noaccept | ✓ | 旧实例排空连接 | `os/unix/ngx_process_cycle.c:268` |

---

## 调优要点（关键开关）

- 改配置用 `nginx -s reload`（先 `nginx -t`），不要 stop+start（会中断）。
- 日志切割：先 mv 日志文件，再 `nginx -s reopen`，避免丢日志。
- 升级 nginx 用 SIGUSR2 热升级流程，生产环境零停机。
- 优雅停机用 quit 而非 stop，让存量请求正常完成；配 `worker_shutdown_timeout` 兜底。

---

## 常见误区与工程要点

- **用 stop 换配置**：会强制断连；换配置永远用 reload。
- **logrotate 后不 reopen**：nginx 仍写旧 inode，新文件不落日志——必须 reopen（`ngx_reopen_files` `:257`）。
- **以为信号立即生效**：`ngx_signal_handler`（`os/unix/ngx_process.c:319`）只置标志位、由主循环执行；动作是异步触发的。
- **热升级不验证就 kill 旧 master**：应先并存验证新版正常，再退旧实例，保留回滚能力。

---

## 一句话总纲

**信号控制是 nginx 的运维接触面：向 master 发信号，`ngx_signal_handler`（`os/unix/ngx_process.c:319`）只置 `sig_atomic_t` 标志位（`ngx_reconfigure`/`ngx_reopen`/`ngx_quit`/`ngx_change_binary`），由 master 主循环 `ngx_master_process_cycle`（`ngx_process_cycle.c:74`）轮询后执行——reload（`:211`）与热升级（`:262` → `ngx_exec_new_binary` `:265`）都靠"新旧 worker/实例短暂并存 + 旧者排空存量再退出"实现零中断切换，配置错误或新版异常都可安全回滚而不丢连接。**
