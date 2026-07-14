# nginx 核心原理 · 接触面主线 · 配置指令体系

> **定位**：接触面主线之一——用户通过 `nginx.conf` 的**配置指令（directive）**声明 nginx 的一切静态行为。每条指令由某模块的 `ngx_command_t` 注册，在合法上下文里由 set 回调写进配置结构。它是**模块体系**的入口，被几乎所有支撑能力域依赖；与另一条接触面"信号控制"分工——配置声明静态行为、信号驱动运维动作。核实基准：官方源码 `nginx/src`。

## 一、指令结构：ngx_command_t 五要素

![指令结构](Nginx原理_配置_01指令结构.svg)

每条指令是一个 `ngx_command_t`（`core/ngx_conf_file.h:77`）：**name**（指令名，如 `worker_processes`/`proxy_pass`）、**type**（位掩码——上下文 + 参数个数 + 是否块/开关）、**set 回调**（解析到时把参数写进配置结构）、**conf**（存哪层配置）、**offset**（字段偏移）。type 分两组标志：上下文（`NGX_MAIN_CONF`/`NGX_HTTP_MAIN_CONF`/`NGX_HTTP_SRV_CONF`/`NGX_HTTP_LOC_CONF`，决定在哪块合法）与参数形态（`TAKE1/2…` 定参数、`NGX_CONF_BLOCK` 带 `{}`、`NGX_CONF_FLAG` on/off）。放错上下文报 "directive is not allowed here"，参数不符报 "invalid number of arguments"。全库用同一份贯穿示例配置。

---

## 二、解析流程：递归下降派发给 set 回调

![解析流程](Nginx原理_配置_02解析流程.svg)

`ngx_conf_parse`（`ngx_conf_file.c:158`）主循环：`ngx_conf_read_token`（`:243`）逐字符切出一条指令的 name + 参数（遇 `{` 返回 `NGX_CONF_BLOCK_START`）→ `ngx_conf_handler` 在所有模块的 commands 里按 name 找匹配指令、校验上下文与参数个数 → 调用 set 回调把参数写进配置结构（`set_str/num/flag_slot` 或自定义）；遇块指令则 set 回调内递归再调 `ngx_conf_parse` 进入子块。解析发生在启动/reload 时（非请求路径），语法/上下文/参数错误在此暴露；`nginx -t` 只校验不启动，上线前必做。产物是只读配置结构，供 worker 请求处理时查。

---

## 深化 · 配置继承与合并

![继承合并](Nginx原理_配置_03继承合并.svg)

指令值沿嵌套 `http → server → location` 向内继承、可就近覆盖。机制在解析后的 merge 阶段：`create_loc_conf` 每层先建字段为 UNSET 的配置结构；`ngx_http_core_merge_loc_conf`（`core_module.c:39`）自外向内合并——本层 UNSET 取父层值（继承）、已设则保留（覆盖），用 `ngx_conf_merge_*` 宏族（`merge_value`/`merge_size_value`/`merge_msec_value`…带默认值）。意义是"顶层配一次、下层按需覆盖"。注意并非所有指令都简单继承——数组类指令（如 `add_header`）遵循"就近整体替换"语义，子块出现同名会覆盖父层全部而非叠加。

---

## 拓展 · 上下文与常见指令归属

| 上下文 | 典型指令 | 作用 |
|---|---|---|
| main（顶层） | `worker_processes`、`user`、`pid` | 进程与全局 |
| events | `worker_connections`、`use epoll` | 事件模型 |
| http | `gzip`、`log_format`、`upstream{}` | HTTP 全局默认 |
| server | `listen`、`server_name`、`ssl_certificate` | 虚拟主机 |
| location | `proxy_pass`、`root`、`limit_req` | 按 URI 路径的处理 |

---

## 调优要点（关键开关）

- `nginx -t`：改配置后先测试语法与上下文，再 reload。
- `include`：拆分大配置（`ngx_conf_include`），按 vhost/模块组织。
- 善用继承：公共项放 http/server，仅差异项放 location，减少重复与出错。
- 注意数组类指令（add_header/proxy_set_header）的"就近替换"陷阱——子块要重申父层需要的项。

---

## 常见误区与工程要点

- **指令放错块**：`proxy_pass` 只在 location 有意义，放 http 报错；先查指令的合法上下文。
- **以为所有指令都叠加继承**：多数标量继承覆盖，但 add_header 等在子块出现会整体替换父层。
- **变量在解析期求值**：`$host` 等变量是请求期求值的，配置解析期只记表达式。
- **不测试就 reload**：语法错会让 reload 失败（但旧配置仍在跑）；养成 `nginx -t` 习惯。

---

## 一句话总纲

**配置指令是 nginx 唯一的声明式接触面：每条 directive 由某模块的 ngx_command_t（name + 上下文/参数位掩码 type + set 回调）注册，ngx_conf_parse 递归下降读 token 后经 ngx_conf_handler 校验上下文并派发给 set 回调写入配置结构，值沿 http→server→location 经 merge_loc_conf 继承覆盖——启动/reload 期一次性解析成只读配置结构供 worker 查，`nginx -t` 是上线前的安全闸。**
