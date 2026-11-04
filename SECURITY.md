# Security

## 密钥边界

- 唯一真实云模型密钥文件：项目母目录 `model_api_keys.env`。
- 文件保持可见，但必须使用最小 ACL；运行账户可读，普通账户不可读。
- 仓库内只允许 `model_api_keys.env.example`，不得包含真实值。
- Key 不得进入：
  - Git 工作树或历史
  - 前端 bundle、`VITE_*`、`NEXT_PUBLIC_*`、构建参数
  - 浏览器 localStorage、IndexedDB、Cookie 或网页表单默认值
  - 应用响应、异常、普通日志、截图和测试证据
- 服务端健康检查只报告 `SET` / `MISSING` 和变量名，绝不返回值、长度或前后缀。

## 身份和内部接口

- 浏览器只持 LibreChat 登录态。
- Memos PAT、LibreChat 内部令牌和云模型 Key 只存在后端进程。
- `/internal/*` 不得由同源网关公开；网关按方法和路径白名单转发。
- 用户、会话、消息和回忆均按服务端身份作用域校验。
- 不信任客户端声明的 `user_id`、任意上游 URL或以 `http://127.0.0.1` 开头的
  客户端输入来绕过 egress 限制。

## 用户数据和媒体

- 真实聊天、数据库、上传、生成图片、运行日志与账号映射不进入 Git。
- 回忆图片是 AI 艺术化创作，UI 必须保留 `AI 生成` / `AI 创作画面` 标识。
- 不应声称生成图是用户拍摄的真实照片。
- 不根据缺失事实添加真实身份、精确地点或写实人脸。
- 未经用户授权，不把真实内容发送给第三方模型。

## 日志

- 禁止记录 Authorization、Cookie、PAT、内部令牌、模型 Key、完整请求体。
- 模型诊断只记录 Provider 与 `SET` / `MISSING`。
- 运行日志写入被忽略的 `infra/runtime/` 或容器日志，并配置轮转。
- 失败证据保留错误码、trace ID 和脱敏摘要，不保留凭据。

## 文件权限

Windows：

```powershell
$file = (Resolve-Path ..\model_api_keys.env).Path
icacls $file /inheritance:r
icacls $file /grant:r "$env:USERNAME:(R)"
icacls $file /grant:r "SYSTEM:(F)"
icacls $file /grant:r "BUILTIN\Administrators:(F)"
```

Ubuntu：

```bash
chmod 600 ../model_api_keys.env
chown "$USER":"$USER" ../model_api_keys.env
```

运行服务账户如果需要读取文件，应单独授予读权限；不要使用全局可读的 `0644`。

## GitHub 发布前

1. 确认 remote 是项目所有者指定的仓库，不是 `Silver-economy` 或其他副本。
2. 检查 `git status` 和 `.gitignore`，确保 `.env`、运行时、数据库、媒体、
   账号文件和真实密钥未暂存。
3. 使用 Gitleaks 或等价工具扫描工作树和完整 Git 历史。
4. 扫描 `model_api_keys.env` 中真实值是否在工作树或历史出现，只输出命中
   文件与规则名，不输出值。
5. 检查许可证、第三方素材、截图中的个人信息和测试账号。
6. 发现历史泄露时轮换受影响 Key，并按需净化历史；删除当前文件不足以清除历史。
7. 未验证远端或权限时保持 `BLOCKED_REMOTE`，不得创建错误仓库或强推。

## 数据迁移

Git clone 不包含真实用户数据库和照片。若要迁移真实业务数据，应停止写入、
加密备份、校验 SHA256，并通过受控通道恢复。不得把真实数据打包到公开仓库。
