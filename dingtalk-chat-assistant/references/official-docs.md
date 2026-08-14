# 钉钉官方文档与能力边界

以下链接由 `dws devdoc article search` 于 2026-08-06 检索自钉钉开放平台。实施实时机器人前重新搜索并核对当前版本，不要把本参考中的路径当作永久 API 契约。

## 官方文档

- [机器人概述](https://pre-open.dingtalk.com/document/development/robot-overview.md)
- [配置企业机器人](https://pre-open.dingtalk.com/document/dingstart/configure-the-robot-application.md)
- [机器人接收消息](https://pre-open.dingtalk.com/document/dingstart/receive-message.md)
- [机器人发送群聊消息](https://pre-open.dingtalk.com/document/development/the-robot-sends-a-group-message.md)
- [机器人发送、查询和撤回单聊消息](https://pre-open.dingtalk.com/document/development/chatbot-sends-queries-and-withdraws-one-on-one-chat-messages.md)
- [企业内部机器人支持的消息类型](https://pre-open.dingtalk.com/document/development/message-types-supported-by-enterprise-internal-robots.md)
- [Webhook 机器人](https://pre-open.dingtalk.com/document/dingstart/webhook-robot.md)
- [钉钉 MCP 功能清单](https://pre-open.dingtalk.com/document/aipass/dingtalk-mcp-feature-list-1.md)

## 能力模型

聊天记录总结与实时机器人接收是两条不同链路：

- 本技能通过 `dws` 使用当前登录账号和企业已开放的能力读取消息。结果只覆盖该账号有权限访问且接口实际返回的范围。
- 企业机器人接收消息只覆盖发送给该机器人、`@` 该机器人或官方文档定义的触发范围。它不是读取企业任意历史聊天的后门。
- Webhook 机器人适合外部系统向群里推送消息；需要理解用户消息并回复时，应使用支持接收消息的企业机器人能力。
- Codex 技能只定义工作流。真正的实时自动应答需要单独部署常驻服务，并按官方文档配置机器人、接收模式、权限与发布范围。

## 实时服务检查表

1. 在开发者后台创建并配置企业机器人，限定最小可见范围和最小权限。
2. 按当前官方“机器人接收消息”文档选择回调或 Stream 接入方式，不从旧博客复制载荷字段。
3. 对事件或消息唯一标识做幂等，防止重试导致重复回复。
4. 校验来源与鉴权信息；凭证只放在密钥管理或环境变量中，禁止写入技能文件和日志。
5. 保存最少必要上下文，设置保留期限、访问审计、脱敏和删除机制。
6. 在回复前执行事实校验、敏感内容检测、频控、循环检测和人工接管策略。
7. 使用官方群聊或单聊发送能力回复，并记录返回的查询键或消息键。
8. 先在测试组织或测试群验证消息类型、权限、超时、重复投递、失败重试和撤回，再发布到生产范围。

具体字段、签名、回执时限、频率限制、消息类型和权限名称必须以当前官方页面为准；不要硬编码本参考未列出的数值。
