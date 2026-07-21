# ClickHouse 核心原理 · DCL 数据控制

> **定位**：DCL 是"管权限/配额"的接口主线，骨架 = `AccessControl 管理器 → 实体（User/Role/RowPolicy/Quota/SettingsProfile）→ 多后端 AccessStorage`；依赖 **元数据与协调**（ReplicatedAccessStorage 经 Keeper 全集群一致），与 **资源与负载管理**（Quota/SettingsProfile）共用配额与约束机制。核实基准：社区 v25.8，源码 `src/Access/`。

## 一、DCL 生命周期与权限判定

![权限判定链路](ClickHouse原理_DCL_01判定链路.svg)

每条查询的鉴权在 `ContextAccess`（`ContextAccess.h:38`）：`checkAccess`（`:74`）→ `calculateAccessRights`（`ContextAccess.cpp:404`）算出含隐式权限的 `AccessRights`（`:407`），`checkAccessImplHelper`（`:570`）判定——用户被删则抛 `UNKNOWN_USER`（`:577`），`full_access` 短路（`:581`），否则 `isGranted(flags, args...)`（`:634`）在权限树上按 库/表/列 粒度匹配。中枢是 `AccessControl`（`AccessControl.h:57`），持有各类缓存（`:271-275`）与认证入口（`authenticate:131`）。

---

## 二、RBAC 模型：User / Role / GRANT

![RBAC 权限模型](ClickHouse原理_DCL_02权限模型.svg)

`IAccessEntity`（`IAccessEntity.h:15`）是所有实体基类。`User`（`User.h:16`）持有认证方式（`authentication_methods:18`）、被授予的角色（`granted_roles:21`）、默认角色（`default_roles:22`）与直接权限。`Role`（`Role.h:12`）可再持有角色（角色可嵌套）。角色解析经 `RoleCache`（`RoleCache.h:15`）→ `getEnabledRoles`（`:21`）产出 `EnabledRoles`，其 `getRolesInfo`（`EnabledRoles.h:36`）聚合出"当前生效的所有角色 + 权限"。`AccessRights`（`AccessRights.h:16`）是权限树，支持 库/表/列 粒度、通配符、`WITH GRANT OPTION`。

---

## 三、认证方式（Authentication）

![认证方式](ClickHouse原理_DCL_03认证.svg)

`Authentication::areCredentialsValid`（`Authentication.h:26`）校验凭据。`AuthenticationType`（`AuthenticationType.h:9`）支持多种：

| 方式 | 说明 | 适用 |
|---|---|---|
| `no_password` | 无密码 | 内网测试（默认允许开关控制） |
| `plaintext_password` | 明文 | 简单场景 |
| `sha256_password` | SHA-256 哈希 | 推荐的密码方式 |
| `double_sha1_password` | 双 SHA-1 | MySQL 协议兼容 |
| `bcrypt_password` | bcrypt | 更强的密码哈希 |
| `ldap` / `kerberos` | 外部目录/票据 | 企业统一认证 |
| `ssl_certificate` | TLS 客户端证书 | 双向 TLS |
| `ssh_key` / `http` / `jwt` | SSH 密钥 / HTTP / JWT | 免密/令牌 |

外部认证器（LDAP/Kerberos 服务器）在 `ExternalAuthenticators`（`ExternalAuthenticators.h:36`）。

---

## 四、行级安全（Row Policy）

![行级安全](ClickHouse原理_DCL_04行级安全.svg)

`RowPolicy`（`RowPolicy.h:15`）给表附加过滤表达式，分 **restrictive（限制型，AND）** 与 **permissive（许可型，OR）**（`isRestrictive:36`/`isPermissive:45`）。`RowPolicyCache::mixFilters`（`RowPolicyCache.cpp:24`）把它们组合：restrictive 用 AND、permissive 用 OR（如 `a=1 AND b=2 AND c=3`，`:306`）。应用点在查询规划期：`InterpreterSelectQuery.cpp:695` 取 `getRowPolicyFilter(...)`，`:894` 把策略表达式 push 进 `query_info.filter_asts`——**每个用户看到的行由其行策略自动过滤**，对用户透明。

---

## 五、配额与约束（Quota / SettingsProfile / Constraints）

![配额与约束](ClickHouse原理_DCL_05配额约束.svg)

- **Quota**（`Quota.h:20`）按周期限流，维度含 `QUERIES/ERRORS/RESULT_ROWS/RESULT_BYTES/READ_ROWS/READ_BYTES/EXECUTION_TIME`（`QuotaDefs.h:12-22`）。`EnabledQuota::checkExceeded`（`EnabledQuota.h:52`）在消费时判超限。
- **SettingsProfile**（`SettingsProfile.h:12`）成组应用设置，`SettingsProfileElement`（`SettingsProfileElement.h:23`）带 `min_value/max_value`（`:29`）与可写性（`writability:32`）。`SettingsConstraints`（`SettingsConstraints.h:61`）在设置被改时 `check`（THROW，`:205`）或 `clamp`（夹取，`:237`），并支持 `WRITABLE`/`CONST`（只读锁定）。

这套配额/约束机制与 **资源与负载管理** 主线共用——DCL 定义"谁受什么限"，资源主线执行"运行时怎么限"。

---

## 深化 · AccessStorage 多后端与复制

![AccessStorage 多后端](ClickHouse原理_DCL_06存储后端.svg)

`IAccessStorage`（`IAccessStorage.h:40`）是实体存储抽象，多后端由 `MultipleAccessStorage`（`"multiple"`）聚合：

| 后端 | 类型名 | 存储位置 | 复制 |
|---|---|---|---|
| `DiskAccessStorage` | `local_directory` | 本地 `<uuid>.sql` 文件 | 否（SQL 创建的实体，本节点） |
| `UsersConfigAccessStorage` | `users_xml` | `users.xml` | 否（节点本地、只读） |
| `ReplicatedAccessStorage` | `replicated` | Keeper znode | **是**（全集群） |
| `MemoryAccessStorage` | `memory` | 内存 | 否 |
| `LDAPAccessStorage` | `ldap` | 外部 LDAP | — |

**SQL 驱动的访问控制默认开启**（`AccessControl.cpp:524`，`access_control_path` 设置时加可写 DiskAccessStorage）。`ReplicatedAccessStorage`（`ReplicatedAccessStorage.h:12`）把实体存在 Keeper（`ZooKeeperReplicator`，znode `<zk>/uuid/<uuid>`，`ZooKeeperReplicator.cpp:149`），watching 线程监听变更并 `refreshEntity`（`:335`）——所以 `GRANT`/`CREATE USER` 能**全集群自动生效**，而 `users.xml` 是节点本地、只读的。

---

## 拓展 · 权限对象全景

| 类别 | 项 | 说明 |
|---|---|---|
| 主体 | User / Role | 谁 |
| 权限 | GRANT/REVOKE（库/表/列/通配） | 能做什么 |
| 行安全 | Row Policy（restrictive/permissive） | 能看哪些行 |
| 限流 | Quota（7 维度 × 周期） | 用多少 |
| 设置 | Settings Profile + Constraints | 用什么设置、能否改 |
| 认证 | 12 种 AuthenticationType | 怎么证明身份 |

---

## 调优要点（关键开关）

- **认证方式**：生产用 `sha256_password`/`bcrypt`/`ldap`/证书，避免 `plaintext`/`no_password`。
- `access_control_improvements.*`：一组收紧默认安全的开关，**多数默认 true**（如 `on_cluster_queries_require_cluster_grant`、`select_from_system_db_requires_grant`、`users_without_row_policies_can_read_rows`），但少数为兼容旧配置**默认 false**（如 `table_engines_require_grant`、`enable_read_write_grants`，`AccessControl.cpp` 有显式注释说明）。
- **ReplicatedAccessStorage**：多节点集群应启用，让 DCL 全集群一致，避免各节点 users.xml 漂移。
- **Quota 维度**：按 `read_rows`/`execution_time` 限"重查询"比只限 `queries` 更有效。
- **SettingsConstraints**：用 `readonly`/`min/max` 锁定关键设置，防止用户改坏（如关掉内存限制）。

---

## 常见误区与工程要点

- **只用 users.xml 管多节点权限**：users.xml 是节点本地的，改一台不影响其他；多节点要用 `ReplicatedAccessStorage`（经 Keeper）让 SQL 权限全集群一致。
- **依赖 `no_password`**：内网也应设密码；`allow_implicit_no_password` 虽默认 true，但生产应显式设强认证。
- **行策略以为默认拦截**：`users_without_row_policies_can_read_rows` 默认 true——没给某用户设策略时，它能看全部行；要"默认拒绝"需显式配置。
- **Quota 只限查询数**：一个重查询能拖垮系统，应同时限 `read_rows`/`memory`/`execution_time`。

---

## 一句话总纲

**DCL 以 `AccessControl` 为中枢：RBAC（User/Role/GRANT，权限树按库/表/列匹配）+ 12 种认证 + 行级安全（restrictive AND / permissive OR，规划期注入 WHERE）+ 配额与设置约束；实体存于多后端 AccessStorage，其中 ReplicatedAccessStorage 经 Keeper 让 SQL 权限全集群一致——这与节点本地的 users.xml 形成互补。**
