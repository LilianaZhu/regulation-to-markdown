# 法规转 Markdown Agent Plugin

本工具将官方法规 PDF 转成经过官方原文核验的 Markdown。

核心原则：

- 官方 PDF 是唯一权威来源；
- MinerU 只负责提取；
- Python只执行确定性处理和验证；
- AI逐页对照官方PDF；
- 任何法律文字修改都必须有页码、原文、批准、修复日志和独立复核；
- 未通过发布门禁的文件不能标记为FINAL。

## 插件形态

仓库同时提供：

```text
plugin.json                     Agent Plugins 1.0.0标准
.claude-plugin/plugin.json      Claude Code/Desktop插件清单
.claude-plugin/marketplace.json Claude插件市场目录
mcp.json                        Agent Plugins MCP配置
.mcp.json                       Claude MCP配置
```

仓库本身是唯一可编辑源码包。Claude安装后的cache和插件数据目录由系统管理，
不应手工修改。

## 在Claude Code或Claude Desktop安装

在Claude中执行：

```text
/plugin marketplace add https://github.com/LilianaZhu/regulation-to-markdown
/plugin install regulation-to-markdown@liliana-legal-tools
/reload-plugins
```

启用插件时，填写MinerU API Token：

<https://mineru.net/apiManage/token>

该字段标记为敏感信息，由Claude凭据机制保存。不要把Token发到聊天、写入Git、
任务目录或验证报告。

## 使用

```text
/regulation-to-markdown:regulation-to-markdown @法规文件.pdf
```

插件会：

1. 检查PDF页数、大小、哈希和文本层；
2. 提供高可靠/低成本分页方案；
3. 等待用户确认后才上传MinerU；
4. 保存MinerU原始结果；
5. 确定性规范化、页码映射和重叠去重；
6. 分批核对官方PDF文本和页面图像；
7. 展示需要批准的原文修复；
8. 独立复核最终文件；
9. 通过门禁后导出FINAL.md和validation-report.md。

本工具不写死印尼BAB/Pasal结构，会识别不同法域和不同文件类型的自身层级。

## 其他Agent Plugin客户端

支持Agent Plugins 1.0.0的客户端读取根目录：

```text
plugin.json
mcp.json
```

由于开放标准暂未定义通用凭据存储，其他客户端需在宿主环境中配置：

```text
MINERU_API_TOKEN
```

## 本地开发

```powershell
claude --plugin-dir C:\path\to\regulation-to-markdown
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Dev -InstallClaudePlugin
```

质量检查：

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
claude plugin validate .
```

## 任务文件

```text
jobs/<文件ID>/
├─ job.json
├─ events.jsonl
├─ batches/
├─ merged/
├─ audit/
├─ final/
└─ validation-report.md
```

`jobs/`仅保留在本地并由Git忽略，不会发布到插件仓库。

## 更新

如果通过Marketplace安装：

```text
/plugin marketplace update liliana-legal-tools
/plugin update regulation-to-markdown@liliana-legal-tools
/reload-plugins
```

请勿手工修改Claude插件cache。

## 官方文档

- <https://agent-plugins.org/plugin-authors/manifest>
- <https://agent-plugins.org/plugin-authors/mcp-servers>
- <https://code.claude.com/docs/en/plugins>
- <https://code.claude.com/docs/en/discover-plugins>
