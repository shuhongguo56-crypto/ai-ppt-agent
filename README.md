# AI PPT Agent 本地 SaaS MVP

这是一个本地优先的 AI PPT SaaS 纵向切片。当前网站已经覆盖：

`项目输入 / 上传资料 -> SourcePack -> HumanizePPT 大纲 -> 大纲审阅/编辑/确认 -> 12 种 PPT 模板 -> 统一 SlideDeck JSON -> PPTX + HyperFrames HTML -> 质量检查 -> 下载导出 -> 项目库`

核心不变量：

- PPTX 和 HTML 必须来自同一份 `SlideDeck JSON`。
- 专业模式必须先审阅大纲；用户可以编辑演示目标、页面标题、核心要点和讲稿备注，再继续生成模板和导出。
- 工作台前端采用对话式逐步提问：用户回答完当前问题后才出现下一步，默认只展示用户真正关心的 PPT 进度、预览和下载。
- PPTX 渲染器会按 SlideDeck 的布局生成不同页面版式，包括封面、章节页、双栏、三卡片、时间线、图表重点和结尾页，并通过质量检查防止退化成纯文字堆叠。
- 默认使用 deterministic fake model gateway，保证离线测试不产生模型费用。
- OpenAI API 之前可切换 `ollama` 免费本地 AI 模式；需要本机已安装 Ollama 并拉取模型。
- 配置 OpenAI key 后可以切换真实模型 API。
- 图像模型固定为 `gpt-image-2`，不允许静默 fallback。
- 导出必须通过质量检查。

## 本地安装

```powershell
python -m pip install --constraint requirements.lock -e ".[dev]"
pnpm install --frozen-lockfile
pnpm test
```

## 启动网站

```powershell
.\scripts\start-local.ps1
```

打开：

- 首页：`http://localhost:3001`
- 工作台：`http://localhost:3001/workflow`
- 项目库：`http://localhost:3001/projects`
- API：`http://127.0.0.1:8000`

默认数据目录：

- SQLite：`D:\Codex\Workspaces\ai-ppt-agent-runtime\ai-ppt-runtime.db`
- 导出文件：`D:\Codex\Workspaces\ai-ppt-agent-runtime\assets`

## 切换真实 OpenAI API

PowerShell 示例：

```powershell
$env:AI_PPT_MODEL_BACKEND = "openai"
$env:AI_PPT_OPENAI_API_KEY = "你的 OpenAI API key"
.\scripts\start-local.ps1
```

注意：

- ChatGPT Plus 不包含网站自身的 OpenAI API 调用费用。
- 普通日志不得记录完整用户 prompt、上传原文、base64 图片或 provider 原始错误。

## 使用免费本地 AI（Ollama）

在接入 OpenAI API 之前，可以先用 Ollama 跑真实文本 AI，不产生 OpenAI API 费用。

先在本机安装并启动 Ollama，然后拉取一个中文/英文都比较稳的模型：

```powershell
ollama pull qwen2.5:7b
```

启动网站前设置：

```powershell
$env:AI_PPT_MODEL_BACKEND = "ollama"
$env:AI_PPT_OLLAMA_TEXT_MODEL = "qwen2.5:7b"
.\scripts\start-local.ps1
```

也可以直接：

```powershell
.\scripts\start-local.ps1 -ModelBackend ollama -OllamaTextModel qwen2.5:7b
```

说明：

- `fake` 模式是离线确定性测试，不是真实 AI。
- `ollama` 模式会调用 `http://127.0.0.1:11434` 的本地免费模型生成大纲和模板方向。
- Ollama 不提供本项目指定的 `gpt-image-2` 图像能力，因此免费模式暂不做 AI 图片生成 fallback。

## 多模型级联模式（推荐本地开发默认）

`cascade` 会按顺序尝试多个文本模型通道，尽量用免费/低成本 AI 拉高大纲和视觉方向质量；全部不可用时，会自动落到增强本地规划器，保证网站仍能完整跑通。

默认顺序：

1. OpenAI：`AI_PPT_OPENAI_API_KEY`
2. Gemini OpenAI-compatible：`AI_PPT_GEMINI_API_KEY`
3. OpenRouter OpenAI-compatible：`AI_PPT_OPENROUTER_API_KEY`
4. Groq OpenAI-compatible：`AI_PPT_GROQ_API_KEY`
5. 本地 OpenAI-compatible 服务，例如 LM Studio：`AI_PPT_COMPATIBLE_BASE_URL`
6. Ollama：`AI_PPT_OLLAMA_TEXT_MODEL`
7. 增强本地 fallback

启动：

```powershell
.\scripts\start-local.ps1 -ModelBackend cascade
```

常用本地免费组合：

```powershell
ollama pull qwen2.5:7b
$env:AI_PPT_MODEL_BACKEND = "cascade"
$env:AI_PPT_OLLAMA_TEXT_MODEL = "qwen2.5:7b"
.\scripts\start-local.ps1
```

如果你安装了 LM Studio 或其他 OpenAI-compatible 本地服务：

```powershell
$env:AI_PPT_MODEL_BACKEND = "cascade"
$env:AI_PPT_COMPATIBLE_BASE_URL = "http://127.0.0.1:1234/v1"
$env:AI_PPT_COMPATIBLE_TEXT_MODEL = "local-model"
.\scripts\start-local.ps1
```

Hosted free-tier/低成本接口通常仍需要各自平台 API key；这些 key 不会出现在普通前端日志或 runtime 状态响应里。

## 当前支持的资料上传

- `.txt`
- `.md`
- `.docx`
- `.pptx`
- `.pdf`，当前为轻量本地解析，后续可升级为更完整的文档解析管线。

## 当前内置 PPT 模板方向

- Apple 发布会高级留白
- McKinsey 咨询逻辑
- Airbnb 温暖故事感
- 学术极简白底
- 蓝色论文答辩
- Research Journal 期刊感
- Startup Pitch 明亮路演
- Investor Dark 高级深色
- 课堂友好清爽
- Data Story 数据叙事
- Editorial Magazine 杂志叙事
- Glassmorphism 玻璃拟态
