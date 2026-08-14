# DWS 聊天工作流

本参考按本机 `dws v1.0.35` 的帮助输出整理。每次执行前仍以 `dws <command> --help` 为准；所有真实调用都加 `--format json`。

## 读取消息

搜索群聊并从唯一结果提取 `openConversationId`：

```powershell
dws chat search --query "<群名连续关键词>" --limit 20 --cursor "0" --format json
```

拉取指定群聊消息：

```powershell
dws chat message list --group <openConversationId> --time "yyyy-MM-dd HH:mm:ss" --forward true --limit 50 --format json
```

按姓名解析同事；多个候选时让用户选择，并从选中结果提取 `userId`：

```powershell
dws aisearch person --keyword "<姓名>" --dimension name --format json
```

拉取与指定同事的单聊；`userId` 必须来自上述人员查询结果：

```powershell
dws chat message list-direct --user <userId> --time "yyyy-MM-dd HH:mm:ss" --forward true --limit 50 --format json
```

跨会话读取指定时间段。首页 `cursor` 为 `0`，后续使用响应的 `nextCursor`：

```powershell
dws chat message list-all --start "yyyy-MM-dd HH:mm:ss" --end "yyyy-MM-dd HH:mm:ss" --limit 50 --cursor "0" --format json
```

搜索 `@我`、关键词或指定会话；至少提供一个条件：

```powershell
dws chat message search-advanced --at-me --start "<ISO-8601>" --end "<ISO-8601>" --limit 100 --cursor "0" --format json
dws chat message search-advanced --query "<关键词>" --conversation-ids <openConversationId> --start "<ISO-8601>" --end "<ISO-8601>" --limit 100 --cursor "0" --format json
```

先发现未读会话，再按会话类型拉上下文：

```powershell
dws chat message list-unread-conversations --count 20 --format json
```

分页时只使用响应返回的 `nextCursor` 或边界 `createTime`。不要自行递增、拼接或猜测游标。话题消息需用当前帮助中列出的 `list-topic-replies` 补齐回复。

## 问题确认的发送与回复读取

按 [question-confirmation.md](question-confirmation.md) 生成问题编号并登记后，用现有单聊发送命令投递。发送成功后，从登记记录的 `query_since` 回读消息，定位包含完整问题编号的本人消息：

```powershell
dws chat message list-direct --user <productManagerUserId> --time "<query_since>" --forward true --limit 50 --format json
```

检查产品经理回复时继续使用同一命令；如果已有 `openConversationId`，可用高级搜索补充定位包含问题编号的消息：

```powershell
dws chat message search-advanced --query "<questionId>" --conversation-ids <openConversationId> --start "<sentAtISO8601>" --limit 100 --cursor "0" --format json
```

`list-direct` 的 `time` 必须是 `yyyy-MM-dd HH:mm:ss`；使用登记表的 `query_since`，不要把 ISO-8601 字符串直接传入。分页只使用响应返回的边界时间或游标。按消息 ID 去重，保留发送者、时间、回复关系和正文；关联与状态更新规则见问题确认参考。

## 当前用户引用回复

从消息查询响应提取真实的会话 ID、被引用消息 ID 和原发送者 `openDingTalkId`。先按 [delivery-policy.md](delivery-policy.md) 添加水印并完成确认或可信好友豁免，再执行：

```powershell
dws chat message reply --conversation-id <openConversationId> --ref-msg-id <openMessageId> --ref-sender <senderOpenDingTalkId> --text "<带AI水印正文>" --uuid <new-uuid-v4> --yes --format json
```

当前运行时只支持文本引用回复。不要在该命令中虚构附件、卡片或 Markdown 能力。超过 500 字符时用引用回复发送摘要，再按下节向同一会话发送原文附件。

## 当前用户身份发送与长消息附件

普通单聊文本使用人员查询响应中的 `userId`：

```powershell
dws chat message send --user <userId> --title "<标题>" --text "<带AI水印正文>" --uuid <new-uuid-v4> --yes --format json
```

执行 `--yes` 前必须已完成普通确认或命中可信好友豁免。必须先添加水印，再判断最终正文是否超过 500 个 Unicode 码点；超过时按 [delivery-policy.md](delivery-policy.md) 生成带水印摘要和 UTF-8 Markdown 原文文件，再执行以下链路。

用人员查询响应中的 `openDingTalkId` 获取单聊共享空间，并提取数字型 `newCSpaceIdIM`：

```powershell
dws chat conversation-info --open-dingtalk-id <openDingTalkId> --format json
```

上传原文附件，从响应提取 `fileId`；随后查询元数据，从响应提取数字型 `dentryId`。`drive info` 的参数名是 `--node`，不要使用过期的 `--file-id`：

```powershell
dws drive upload --file <localMarkdownPath> --file-name <fileName.md> --space-id <newCSpaceIdIM> --mime-type "text/markdown" --format json
dws drive info --node <fileId> --space-id <newCSpaceIdIM> --format json
```

附件准备全部成功后，先发送不超过 500 字符的摘要，再发送文件消息：

```powershell
dws chat message send --user <userId> --title "<标题>（摘要）" --text "<带AI水印摘要>" --uuid <summary-uuid-v4> --yes --format json
dws chat message send --open-dingtalk-id <openDingTalkId> --title "<标题>（原文）" --msg-type file --dentry-id <dentryId> --space-id <newCSpaceIdIM> --file-name <fileName.md> --file-type "md" --file-path "/<fileName.md>" --file-size <utf8Bytes> --uuid <attachment-uuid-v4> --yes --format json
```

群聊附件把摘要命令的 `--user` 和附件命令的 `--open-dingtalk-id` 都替换为真实的 `--group <openConversationId>`，并用 `conversation-info --group <openConversationId>` 获取空间。摘要和附件各自保留 UUID；摘要已成功时不要因附件失败而重发摘要。

## 机器人身份发送

查询当前用户创建的机器人并从结果提取 `robotCode`：

```powershell
dws chat bot search --name "<机器人名称>" --page 1 --size 50 --format json
```

机器人发群消息：

```powershell
dws chat message send-by-bot --robot-code <robotCode> --group <openConversationId> --title "<标题>" --text "<带AI水印正文>" --yes --format json
```

机器人发单聊消息，当前运行时每次最多 20 个 `userId`：

```powershell
dws chat message send-by-bot --robot-code <robotCode> --users <userId1,userId2> --title "<标题>" --text "<带AI水印正文>" --yes --format json
```

`--group` 与 `--users` 互斥。发群消息前查询群内机器人或由用户确认机器人已在群中；不要未经确认自动把机器人加入群。当前 `send-by-bot --help` 未暴露 `--uuid`、`--at-all` 或 `--open-dingtalk-ids`，因此不要依赖这些参数。

## 发送审查

发送前逐项对照用户原始需求：目标、发送身份、正文来源、水印、标题、引用对象和 `@` 对象。任一项不明确或同名对象不唯一时必须先确认。正文由模型新写时，普通目标必须确认；符合 [delivery-policy.md](delivery-policy.md) 的可信好友不需要二次确认，但不能省略水印。发送响应失败或含不确定状态时不要盲目重试；机器人发送返回 `processQueryKey` 时保留用于审计或撤回。
