# 问题确认工作流

## 适用范围

当智能体在需求、交互、业务规则、验收口径或设计取舍上遇到无法从现有权威资料确定、且会影响实现或测试结论的问题时，向产品经理发起问题确认。先检查已提供的需求、设计稿、历史决定和当前实现证据；能自行核验的问题不要外发。

问题确认使用一对一消息，以便稳定关联产品经理回复。用户明确要求在群内提问时，按普通群消息流程发送并人工关联回复，不写入本问题登记表。该能力通过查询聊天记录接收回复，不是常驻监听器。

## 解析产品经理

用户指定姓名时按姓名查询：

```powershell
dws aisearch person --keyword "<姓名>" --dimension name --format json
```

只给出产品或模块时，按职责和职位搜索负责人：

```powershell
dws aisearch person --keyword "<产品或模块连续关键词>" --dimension duty,position --format json
```

只有唯一候选时才能继续。多个产品经理、职责不清或查询字段缺失时列出候选并让用户选择；不要根据聊天频率、联系人排序或姓名印象猜测负责人。使用查询响应中的 `userId` 和 `openDingTalkId`。

## 创建并发送问题

1. 用 `conversation-info --open-dingtalk-id` 获取单聊 `openConversationId`。
2. 用登记脚本分配问题编号；若能获得当前 Codex 任务 ID，则写入 `origin-thread-id`：

```powershell
python scripts/question_registry.py new --recipient-name "<姓名>" --user-id <userId> --open-dingtalk-id <openDingTalkId> --title "<短标题>" --origin-thread-id <threadId> --origin-task "<任务短名>"
```

3. 使用脚本返回的 `question_id`，按以下结构撰写。每条消息只处理一个决策主题，最多包含三个强相关子问题：

```text
【问题确认 Q-YYYYMMDD-XXXXXXXX】
主题：<一句话>
背景：<仅保留理解问题所需事实>
待确认：<需要产品明确回答的问题>
选项：<确有明确方案时列出；开放问题不要硬造选项>
影响：<不同答案影响的实现、测试或交付>
期望回复：请引用本消息回复，或在回复中保留问题编号。
```

4. 按 [delivery-policy.md](delivery-policy.md) 添加 `【AI生成】` 水印并执行 500 字符分流。水印必须是第一行，问题编号紧随其后。超过 500 字符时，摘要和完整原文附件都必须包含问题编号。
5. 普通产品经理仍遵循预览确认；只有命中可信好友豁免时才免二次确认。发送使用新的 UUID。
6. 发送前用 `question_registry.py prepare --question-id <id> --content-file <带水印文件>` 保存正文哈希；发送成功后用 `mark-sent` 保存任务键、会话 ID 和发送时间。发送失败则用 `mark-failed` 登记错误。
7. 立即拉取一次发送时间附近的单聊消息，定位包含问题编号的本人消息并保存其 `openMessageId`。没有定位到时保留 `sent` 状态，不得编造消息 ID。

登记表默认位于 `~/.codex/state/dingtalk-chat-assistant/questions.sqlite3`，不保存完整问题正文或回复正文，只保存路由 ID、时间、状态、正文哈希和关联消息 ID。所有脚本输出均为 JSON。

## 接收和关联回复

用户要求“查看问题回复”“检查产品答复”或继续一个等待中的确认时：

1. 用 `question_registry.py list --status sent` 找到待答问题；另行检查 `ambiguous` 和 `needs_follow_up` 状态，或用 `get --question-id <id>` 读取指定记录。
2. 从记录的 `query_since` 开始拉取与该产品经理的单聊消息，按消息 ID 去重并按时间升序排列。
3. 只把产品经理发送、时间晚于问题发送时间的人工消息作为候选。按以下强度关联：
   - 强关联：回复关系指向登记的 `outbound_message_id`。
   - 强关联：正文包含完整问题编号。
   - 弱关联：没有引用或编号，但问题后只有一条语义相关的产品经理消息。
4. 强关联且内容明确回答问题时标记 `answered`；回复提出反问或缺少关键结论时标记 `needs-follow-up`；只有弱关联、多条候选或答复边界不清时标记 `ambiguous` 并请用户判断，不得自动当成产品决定。
5. 提取明确结论、适用范围、例外、后续行动和仍未回答项。不要把智能体推断写成产品答复，也不要把表情、系统消息或他人转述当成正式回复。
6. 用 `mark-checked` 记录检查时间；匹配回复后用 `mark-reply` 保存回复消息 ID、时间和分类。需要继续追问时重新走发送预览和水印流程，并保留原问题编号。

如果发送记录包含 `origin_thread_id`，收到明确答复后可把结构化答复交回原 Codex 任务；只有用户已明确要求“收到回复后自动继续”时才发送到原任务并继续执行，否则只报告答复。

## 等待模式

默认只做一次即时检查。用户明确要求等待时，可每 30 秒执行一次只读检查，并定期报告状态；单次等待不超过 10 分钟。不要使用超过 60 秒的阻塞等待。需要跨更长时间时，只有用户明确要求后才使用宿主的自动化或定时恢复能力，每次恢复只执行一次检查。

没有回复是正常状态，不应标记为失败。用户要求实时、持续接收时，说明本技能本身不常驻；需要按 [official-docs.md](official-docs.md) 建立独立企业机器人接收服务。
