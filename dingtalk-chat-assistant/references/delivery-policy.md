# 消息投递策略

## 发送意图与可信好友

免二次确认只改变发送前的确认步骤，不授予主动发送权限。当前请求必须明确要求“发送”“转发”或“回复”；仅要求总结、拟答、查看进展或生成内容时不得发送。

公开技能默认不配置可信好友。只有本地安装副本中存在
`references/trusted-recipient.local.json`，且它包含非空的 `name`、
`userId` 和 `openDingTalkId` 时，才启用一个可信好友。可运行
`python scripts/configure_trusted_recipient.py` 交互式生成该文件；无人值守
部署可用 `--from-file <private-json>` 从版本库外的秘密文件导入。不要把输入
或输出文件提交到版本库。文件结构参见
`references/trusted-recipient.example.json`。

每次发送前读取本地配置，并使用其中的 `name` 执行：

```powershell
dws aisearch person --keyword "<configured-name>" --dimension name --format json
```

仅当查询结果中恰有一个姓名与本地配置完全相等的候选，且候选的
`userId` 和 `openDingTalkId` 都与本地固定值完全一致时，才跳过二次确认
并使用查询响应中的 `userId` 发送。以下任一情况都回退到普通预览和确认
流程：本地配置不存在或格式无效、同名候选不唯一、任一 ID 缺失或变化、
查询失败、目标是群聊、要求机器人身份、目标包含其他收件人。

不要在面向用户的输出或预览中展示完整固定 ID。可信好友规则不放宽事实核验、敏感信息、承诺边界和身份边界；信息不足时仍先澄清事实，但不要仅为确认措辞而停下。

## AI 水印

通过本技能发出的每条文本消息和文本附件都必须在首行添加可见来源水印；个人消息、引用回复、群消息和机器人消息均不例外。不要用零宽字符、颜色、图片元数据或其他不可见手段代替。

- 正文包含模型生成、总结、翻译、润色、改写、补充或重排时，使用 `【AI生成】`。
- 正文完全照发用户提供的原文，只做换行规范化且没有改写时，使用 `【AI辅助发送】`。
- 人机混合内容或来源无法明确区分时，使用 `【AI生成】`。

先把无水印正文保存为 UTF-8 文件，再执行：

```powershell
python scripts/apply_watermark.py --input <source.txt> --output <watermarked.txt> --mode generated
python scripts/apply_watermark.py --input <source.txt> --output <watermarked.txt> --mode assisted
```

脚本会规范化为 `LF`、去除首行已有的受支持水印并重新应用正确水印，避免重复。预览、字符计数和实际发送必须使用脚本输出，不得使用无水印源文件。用户要求去除水印时仍保留水印，并说明这是本技能的来源标识规则。

长消息的摘要属于模型生成内容，使用 `【AI生成】`。完整原文附件沿用完整正文的来源类型：模型生成或改写用 `【AI生成】`，完全照发用户原文用 `【AI辅助发送】`。水印是最终正文的一部分；引用或用户原文内容本身不应因加水印而被改写。

## 500 字符分流

对已经添加水印的最终完整正文按 Unicode 码点计数；水印、Markdown 标记和换行都计入。不要按 UTF-8 字节数、UTF-16 代码单元或终端显示宽度计数，也不要人工估算。

- `<= 500` 个字符：按原发送或引用回复流程发送一条完整消息。
- `> 500` 个字符：生成一段添加 `【AI生成】` 后仍不超过 500 个字符、可独立理解的摘要，并把带正确来源水印的完整正文原样保存为 UTF-8 Markdown 文件；先完成附件准备，再发送摘要，最后补发原文附件。

摘要应保留目的、关键结论、决定、行动项、负责人、截止时间和主要风险；原文没有的字段不要补写。摘要末尾可提示“完整内容见附件”，该提示也计入 500 字符。附件正文不得用摘要替换、截断或改写。

附件文件名使用 `dingtalk-full-message-YYYYMMDD-HHmmss-<uuid前8位>.md`，不要包含联系人、群名或消息正文。把带水印的完整正文和摘要分别落为 UTF-8 临时文件，并用下列脚本检查长度；完整正文文件加 `--require-normalized`，只在 `readyForAttachment=true` 时上传。使用它返回的 `actualFileBytes` 作为文件消息的 `file-size`，并确保摘要的 `withinLimit=true`。

```powershell
python scripts/message_metrics.py --file <full-message.md> --limit 500 --require-normalized
python scripts/message_metrics.py --file <summary.txt> --limit 500
```

脚本路径相对于本技能目录。摘要和附件使用两个不同的新 UUID。

## 执行与失败边界

长消息按以下顺序执行：获取会话共享空间、创建原文文件、上传文件、查询 `dentryId`、发送摘要、发送附件。准备阶段失败时不要发送摘要。摘要成功而附件失败时，不要重发摘要；只用原附件发送 UUID 重试一次，并准确报告部分成功。没有明确成功响应时，不得宣称对应部分已发送。

普通目标的一次预览必须同时展示摘要和附件文件名；一次明确确认覆盖这两个发送动作。可信好友同时免除这两个动作的二次确认。成功后可删除本地临时文件；上传或附件发送失败时保留文件路径以便恢复。

`chat message reply` 只支持文本。长引用回复使用它发送摘要以保留引用关系，再用 `chat message send` 向同一会话发送原文附件。当前 `send-by-bot` 不支持文件消息；用户要求机器人身份发送超过 500 字符时，说明限制并请求选择，不得把附件静默改为当前用户身份发送。
