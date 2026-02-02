# 认证与登录架构设计（JWT）

## 目标与范围
- 仅增加“登录功能”，不做角色/权限区分
- 采用 JWT Token Based Authentication
- 不支持用户注册；账号仅由管理员/脚本预置
- 前后端仅需完成登录、鉴权、路由/接口保护

## 认证流程（建议方案）
1. 用户在前端登录页输入账号/密码
2. 前端调用 `POST /api/auth/login`
3. 后端校验密码哈希，签发 **Access Token（JWT）** 与 **Refresh Token**
4. 后端将 Refresh Token 写入 **httpOnly Cookie**
5. 前端保存 Access Token，并在后续请求中带上 `Authorization: Bearer <token>`
6. Access Token 过期时，前端调用 `POST /api/auth/refresh` 获取新 Access Token
7. 后端在需要保护的接口中校验 JWT，有效则放行并注入 `current_user`

> 本需求要求：
> - 使用 Refresh Token + httpOnly Cookie，提供更好体验与可撤销能力

## JWT 设计
- **算法**：HS256（对称签名）
- **载荷字段（claims）**：
  - `sub`: 用户唯一标识（ObjectId 或 username）
  - `iat`: 签发时间
  - `exp`: 过期时间
- **过期策略**：
  - Access Token：2h（可配置）
  - Refresh Token：7d（可配置）
- **配置项**（新增到后端配置/环境变量）：
  - `JWT_SECRET`
  - `JWT_ALGORITHM`（默认 HS256）
  - `ACCESS_TOKEN_EXPIRES_MINUTES`
  - `REFRESH_TOKEN_EXPIRES_DAYS`
  - `AUTH_COOKIE_DOMAIN`（可选）
  - `AUTH_COOKIE_SECURE`（生产环境建议 true）
  - `AUTH_COOKIE_SAMESITE`（建议 Lax/Strict）

## MongoDB 表结构设计
### 1) users
用于保存登录账号（管理员预置）。

字段建议：
- `_id`: ObjectId
- `username`: string（唯一）
- `password_hash`: string（bcrypt）
- `display_name`: string（可选）
- `status`: string（active/disabled）
- `created_at`: datetime
- `updated_at`: datetime
- `last_login_at`: datetime（可选）

索引：
- `username` 唯一索引

### 2) refresh_tokens（必需）
用于 Refresh Token/登出/强制失效能力。

字段建议：
- `_id`: ObjectId
- `user_id`: ObjectId
- `token_hash`: string
- `expires_at`: datetime
- `revoked_at`: datetime（可选）
- `created_at`: datetime

索引：
- `user_id`
- `expires_at`（用于定期清理）

## 后端需要修改/新增的部分（仅罗列）
- 配置项
  - JWT 相关环境变量与 settings
- 数据层
  - 新增 `users` collection 的数据访问层
  - `refresh_tokens` collection
- 业务层
  - 密码哈希与校验工具（bcrypt）
  - JWT 生成与验证工具
  - 认证依赖/中间件（FastAPI dependency）
- API 路由
  - `POST /api/auth/login`
  - `POST /api/auth/refresh`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`（返回当前用户信息，便于前端自检）
- 现有路由保护
  - 除 health 以外的业务接口增加鉴权依赖
- 运维/初始化
  - 管理员账号初始化脚本（或启动时检测并创建）

## 前端需要修改/新增的部分（仅罗列）
- 登录页
  - `pages/login` 页面与表单
- 认证状态管理
  - 保存 Access Token（内存或 localStorage）
  - 全局登录态（Context/Provider）
- API 请求封装
  - 自动附加 `Authorization: Bearer <token>`
  - 处理 401 跳转登录页
- 路由保护
  - 需要登录的页面加鉴权
- 刷新机制
  - Refresh Token 续期流程与失败回退
- 用户管理页面
  - 新增用户管理入口与页面
  - 功能范围（后台账号管理）：
    - 用户列表（分页/搜索：username、status）
    - 新增用户（设置初始密码）
    - 启用/禁用账号
    - 重置密码
    - 查看基础信息（创建时间/最后登录时间）

## 管理员账号初始化（本需求要求）
- 默认管理员账号：`james`
- 默认管理员密码：`james1031`
- 初始化方式：建议提供一次性脚本或启动时检测并创建
- 安全建议：首次登录后强制修改密码（可选）

## 安全与运维注意事项
- 密码存储必须使用强哈希（bcrypt），不可明文
- JWT secret 必须通过环境变量注入，不可写死在代码中
- Access Token 过期要合理，避免长期有效
- 若使用 localStorage，需注意 XSS 风险；优先考虑 httpOnly Cookie + Refresh Token

## 路由保护范围（明确鉴权）
- 公开接口：`/api/health`、`/api/auth/login`、`/api/auth/refresh`、`/api/auth/logout`
- 需登录接口：除以上公开接口外的所有业务接口（stocks/strategies/signal/backtests 等）

## Token 存储与传输策略（明确要求）
- Access Token：前端内存保存（页面刷新失效）或 localStorage（更易用但有 XSS 风险）
- Refresh Token：后端写入 **httpOnly Cookie**（前端不可读）
- Cookie 属性建议：
  - `httpOnly: true`
  - `secure: true`（生产环境）
  - `sameSite: Lax`（默认）或 `Strict`
  - `path: /api/auth/refresh`（可选）

## 刷新与登出策略（明确流程）
- Refresh Token 需在 `refresh_tokens` 中落库并可撤销
- refresh 时：校验 cookie 中的 refresh token -> 若有效，返回新 access token，并可轮换 refresh token
- logout 时：撤销 refresh token（标记 revoked_at 或删除记录）
- refresh 失败：前端清理登录态并跳转登录页

## API 契约（建议，便于实现与联调）
### 1) POST /api/auth/login
请求：
```
{ "username": "james", "password": "james1031" }
```
响应：
```
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 7200 }
```
错误：
- 401：账号或密码错误
- 403：账号已禁用

### 2) POST /api/auth/refresh
请求：无 body（使用 httpOnly cookie）
响应：
```
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 7200 }
```
错误：
- 401：refresh token 无效或过期

### 3) POST /api/auth/logout
请求：无 body（使用 httpOnly cookie）
响应：
```
{ "ok": true }
```

### 4) GET /api/auth/me
响应：
```
{ "id": "<user_id>", "username": "james", "display_name": "James", "status": "active", "last_login_at": "...", "created_at": "..." }
```

### 5) 用户管理（建议 API）
- `GET /api/users?search=&status=&page=&page_size=`（列表）
- `POST /api/users`（新增）
- `PATCH /api/users/{id}`（启用/禁用、修改显示名等）
- `POST /api/users/{id}/reset-password`（重置密码）
- `GET /api/users/{id}`（详情）

## 用户管理细则（可执行约束）
- 仅管理员可操作（当前不区分角色时，可默认“已登录用户”即管理员）
- 禁用账号后应拒绝登录并阻止 token 续期
- 重置密码：直接设置新密码，不生成临时密码，不强制首次修改
- 不支持注册功能；仅允许在用户管理页面手动创建
- 不允许删除用户（可选，避免误删审计）

## 管理员账号初始化（细化）
- 启动时检测 `users` 集合是否存在 username 为 `james` 的账号
- 若不存在则创建（password_hash 使用 bcrypt）
- 初始化逻辑需幂等（重复运行不会覆盖已有密码）

## 已确认的实现约束
- Access Token 存储：localStorage
- Refresh Token 轮换：每次 refresh 重发新的 refresh token（旧 token 作废）
- 多端登录：允许同一用户多 refresh token 并存
- 用户创建：仅允许通过用户管理页面手动创建，不支持注册功能
- 重置密码：直接设置新密码，不生成临时密码，不强制首次修改

## Implementation Checklist（给 AI 执行的步骤）
1. 后端配置
   - 新增 JWT 与 Cookie 相关配置项
2. 数据层
   - 建 `users` 与 `refresh_tokens` 集合与索引
   - 增加初始化管理员账号逻辑（幂等）
3. 安全工具
   - bcrypt 密码哈希与校验
   - JWT 签发与验证
4. 认证接口
   - `/api/auth/login`、`/api/auth/refresh`、`/api/auth/logout`、`/api/auth/me`
5. 用户管理接口
   - 用户列表、创建、禁用/启用、重置密码、详情
6. 业务接口鉴权
   - 除 health/login/refresh/logout 外全部加鉴权
7. 前端登录与状态管理
   - 登录页、保存 access token、全局登录态
8. 前端请求封装
   - 自动加 Authorization header
   - 401 自动 refresh/跳转登录
9. 前端用户管理页面
   - 列表、创建、禁用/启用、重置密码
10. 基础联调
   - 登录 -> 请求业务接口 -> token 过期 refresh -> 用户禁用处理
