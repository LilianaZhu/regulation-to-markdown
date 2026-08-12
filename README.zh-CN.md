# 法规转 Markdown Cursor 插件

本插件将官方法规 PDF 转成经过官方原文核验的 Markdown。

核心原则：

- 官方 PDF 是唯一依据；
- MinerU 只负责提取，不被视为权威原文；
- Python只做分页、合并、格式整理和验证；
- 法律文字只有在核对具体 PDF 页后才能修改；
- 官方原文本身存在的错字或不一致保持原样并记录。

## 团队成员如何使用

1. 将官方 PDF 放入 Cursor 工作区。
2. 在 Agent 中输入：

   ```text
   /regulation-to-markdown @法规文件.pdf
   ```

3. Cursor 会显示两种分页方案：
   - 高可靠：较小批次，适合严格逐页审查；
   - 低成本：较大批次，减少 MinerU 任务数。
4. 选择方案后才会调用 MinerU。
5. 遇到法律文字修复时，Cursor 会显示 PDF 页码、官方原文和建议修改。
6. 完成后获得：
   - `法规名称_FINAL.md`
   - `validation-report.md`

法规知识库只导入 `FINAL.md`；验证报告作为内部校对记录保存。

## 通过 GitHub 链接让 Cursor 辅助安装

本项目直接通过 GitHub 分享，不提交 Cursor Marketplace。把下面的提示词发给
Cursor Agent：

```text
请审查并安装这个 Cursor 插件：
https://github.com/LilianaZhu/regulation-to-markdown

安装前确认仓库没有硬编码密钥。Windows 下克隆仓库并执行 install.ps1
-InstallLocalPlugin；执行命令前先征得我的同意。在我明确确认分页方案之前，
不要向 MinerU 发送任何 PDF。
```

GitHub 链接不是静默安装链接；Cursor 应在克隆和执行安装脚本前请求批准。

## 第一次手动安装

要求：

- Windows 版 Cursor；
- Python 3.11或更高版本，并可通过 `python` 命令运行；
- 可以访问互联网；
- MinerU精准解析 API Token。

从 PowerShell 运行：

```powershell
git clone https://github.com/LilianaZhu/regulation-to-markdown.git
Set-Location .\regulation-to-markdown
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallLocalPlugin
```

然后：

1. 重新加载 Cursor；
2. 打开 Cursor 的 **Customize**；
3. 为插件配置 `MINERU_API_TOKEN`；
4. 不要把 Token 粘贴到聊天、代码或 Git 中。

如果只复制了插件文件而没有运行安装脚本，第一次运行命令时，Agent会申请执行
本地 `bootstrap.py`。同意后重新加载 Cursor 一次即可。

### 更新

```powershell
Set-Location .\regulation-to-markdown
git pull
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallLocalPlugin
```

更新后重新加载 Cursor。

### 卸载

```powershell
Remove-Item -Recurse -Force "$HOME\.cursor\plugins\local\regulation-to-markdown"
python -m pip uninstall regulation-to-markdown
```

## 插件自动完成什么

- 检查 PDF 页数、大小、文件哈希和文本层；
- 根据 MinerU 的200页、200MB限制建议分页；
- 物理切分长 PDF，并保留1页重叠；
- 上传官方 MinerU API并下载 Markdown和JSON；
- 生成官方页码锚点；
- 展开 HTML 表格；
- 验证重叠页完全相同后去重合并；
- 分批让 Cursor AI对照官方 PDF审查；
- 只应用已批准且有 PDF证据的修复；
- 检查页面覆盖、重复页、图片、表格和未解决高风险问题；
- 生成人机均可读取的 Markdown 验证报告。

## 哪些情况必须人工确认

- PDF文字层与页面视觉内容不一致；
- 图表需要转成文字；
- 官方原文本身疑似有错；
- AI置信度不足；
- 重叠页不一致；
- 高风险问题未解决。

系统不会根据语言常识猜测法律文字。

## 失败后如何继续

每个任务会保存：

```text
work/<任务编号>/
├─ job.json
├─ events.jsonl
├─ batches/
├─ findings.jsonl
├─ audit-manifest.json
├─ repairs/
├─ FINAL.md
└─ validation-report.md
```

MinerU任务ID和当前状态都记录在 `job.json`，失败后可以继续查询，不必从头开始。

## 分享

直接分享公开仓库：

<https://github.com/LilianaZhu/regulation-to-markdown>

接收者可以把链接和上面的安装提示词交给 Cursor Agent，也可以手动克隆并运行
安装脚本，无需 Cursor Marketplace。
