# AI PPT Agent 本地基础底座设计

## 1. 目标与范围

本里程碑从空仓库落地交接清单的任务 1–6，建立可离线运行、可确定性测试、可渐进替换为生产基础设施的工程底座。默认开发环境不依赖 Docker、云服务、API Key 或网络。

本里程碑包含：

- monorepo 脚手架与统一开发命令；
- 版本化跨服务数据合同；
- FastAPI 服务外壳与安全配置；
- 项目与工作流检查点的 SQLite 持久化；
- HumanizePPT 与 Frontend-Slides 技能注册表；
- 类型化文本/图像模型网关及确定性 Fake 实现；
- GPT Image 2 响应的完整 PNG 安全验证。

本里程碑不包含大纲生成、视觉方案、SlideDeck、PPTX/HTML 渲染、正式前端界面、付费或云端部署。

## 2. 技术路线

采用“本地优先、生产接口预留”的混合路线：

- API：Python 3.12 + FastAPI + Pydantic v2；
- 本地持久化：SQLite；
- 本地资产：工作目录内文件存储；
- 本地任务调度：同步/内存实现；
- 数据合同：JSON Schema 与 TypeScript/Python 类型，以 `schemaVersion` 显式版本化；
- 测试：pytest，全部离线执行；
- Web：仅建立 Next.js 工程边界与健康占位页，不进入界面设计。

仓储、资产存储、任务队列和模型网关通过窄接口隔离，以后可分别替换为 PostgreSQL、Redis、S3/R2/MinIO 和 OpenAI 生产实现，不改变领域用例。

## 3. 仓库结构与模块边界

```text
apps/
  api/                    FastAPI 入口、用例、SQLite 适配器、AI 网关
  web/                    Next.js 最小占位工程
packages/
  contracts/              JSON Schema 和跨服务类型
  skills/                 技能描述、版本和注册表
  render/                 为后续渲染器预留边界，本里程碑不实现
  ui/                     为后续界面预留边界，本里程碑不实现
tests/                    跨包合同和端到端基础测试
```

模块职责：

- `contracts` 只定义数据含义和版本，不依赖 FastAPI 或持久化实现；
- API 用例只依赖仓储与网关接口，不直接依赖 SQLite 或 OpenAI SDK；
- `skills` 记录技能名、版本、输入/输出 Schema 和 prompt hash，不执行业务工作流；
- PNG 验证器是无网络、无日志、无业务依赖的纯验证单元；
- Fake 网关使用规范化输入的哈希生成稳定输出，确保相同输入始终得到相同结果。

## 4. 数据流

1. 客户端调用 FastAPI 创建项目或读写工作流检查点。
2. API 校验请求的 Schema 版本和业务字段。
3. 用例通过仓储接口读写 SQLite；检查点携带递增版本号，更新时使用乐观并发控制。
4. 需要 AI 的用例通过类型化文本或图像网关执行；默认配置注入 Fake 实现。
5. 文本结果在返回用例前必须通过目标 JSON Schema。
6. 图像结果在返回用例前必须经严格 base64 解码和 PNG 安全验证。

## 5. 数据合同

本里程碑定义后续任务所需的最小合同骨架：

- `ProjectBrief`：项目 ID、输入语言、输出语言、汇报类型、主题、受众、模式；
- `SourcePack`：来源 ID、类型、摘要、引用元数据；
- `WorkflowCheckpoint`：项目 ID、阶段、状态、版本、载荷、时间戳；
- `SkillDescriptor`：名称、版本、输入/输出 Schema ID、模型策略和 prompt hash；
- 模型网关请求/响应：显式模型、超时、重试上限、结构化输出 Schema 和使用量元数据。

所有持久化载荷和跨服务数据均必须含 `schemaVersion`。未知主版本直接拒绝，不做隐式兼容。

## 6. 持久化与并发

SQLite 至少保存 `projects` 和 `workflow_checkpoints` 两类记录。事务边界位于仓储适配器：

- 项目创建与初始检查点可原子写入；
- 检查点更新必须提供当前版本；
- 版本不匹配返回稳定的冲突错误，不覆盖新数据；
- 测试使用临时 SQLite 文件，不依赖全局数据库。

## 7. 技能注册表

首批内置两个技能：

- `HumanizePPT`：将 `ProjectBrief + SourcePack` 转换为版本化 `OutlineDecision`；
- `Frontend-Slides`：将已确认 `OutlineDecision` 转换为 3 个 `VisualDirection`。

本里程碑只注册元数据与合同，不执行两个技能。注册表拒绝重复的 `name + version`，并能按名称获取明确版本。

## 8. 模型网关与安全错误

文本和图像网关是独立接口。生产图像网关的主模型固定为 GPT Image 2；失败时不自动切换到 Nano Banana 或其他模型。

公开错误统一为稳定结构：

```json
{
  "code": "image_validation_failed",
  "message": "Generated image failed validation.",
  "retryable": false
}
```

原始 SDK 错误、traceback、完整 prompt、上传原文和图片 base64 不进入 API 响应或普通日志。日志只记录请求 ID、模型名、延迟、安全错误代码和用量摘要。重试配置限制为 1–3 次，只对显式标记为可重试的错误生效。

## 9. PNG 安全验证

验证器在图像进入业务层之前执行，并实施以下全部规则：

1. 精确匹配 PNG 8 字节签名；
2. 存在且仅存在一个 IHDR，且 IHDR 为首个 chunk；
3. 至少存在一个 IDAT，IDAT 必须在 IHDR 之后且 IEND 之前；
4. 存在且仅存在一个 IEND，IEND 长度为 0，其后无数据；
5. 每个 chunk 长度不超过配置上限，总输入大小不超过总预算；
6. 每个 chunk 的 CRC32 正确；
7. IHDR 宽高与请求尺寸一致；
8. bit depth 仅允许 8，color type 仅允许 RGB(2) 或 RGBA(6)；
9. compression、filter 和 interlace method 均必须为 0，明确拒绝 Adam7；
10. 拼接所有 IDAT 后使用受限 zlib 解压；
11. 解压数据精确等于 `height * (1 + width * bytes_per_pixel)`；
12. 每行首字节的 filter 值在 0–4 之间；
13. 解压输出一旦超过计算预算立即停止并拒绝，防止解压炸弹。

任何规则失败在网关边界统一转换为不可重试的 `image_validation_failed`，不向外暴露内部验证细节。

## 10. API 边界

本里程碑提供最小可验证 API：

- `GET /health`：返回服务状态和版本；
- `POST /api/projects`：创建项目与初始检查点；
- `GET /api/projects/{project_id}`：读取项目；
- `GET /api/projects/{project_id}/checkpoints/latest`：读取最新检查点；
- `PUT /api/projects/{project_id}/checkpoints/{stage}`：使用期望版本写入检查点；
- `GET /api/skills`：列出已注册技能和版本。

网关仅在服务内部暴露，不在此里程碑提供通用的外部模型调用端点。

## 11. 测试与验收

测试层次：

- 合同测试：Schema 版本、必填字段、未知主版本拒绝、TypeScript/Python 样例一致；
- API 测试：健康检查、项目创建/读取、检查点写入/读取与冲突；
- 注册表测试：内置技能、版本查询、重复注册拒绝；
- Fake 网关测试：确定性、结构化输出、固定 GPT Image 2 策略、不自动降级；
- 错误测试：安全错误映射、重试上限、响应与日志不包含敏感载荷；
- PNG 测试：有效 RGB/RGBA、错误签名、缺失/重复/乱序 chunk、错误 CRC、尺寸不符、非支持颜色/位深、Adam7、无效 zlib、长度不符、非法 filter、追加数据、过大 chunk 和解压炸弹。

验收条件：

1. 在无 Docker、无 API Key、无网络环境中，一条命令可运行全部测试；
2. API 可本地启动，健康检查正常；
3. 项目和检查点在服务重启后仍可读取；
4. 文本与图像 Fake 网关相同输入产生相同输出；
5. 所有恶意或损坏 PNG 样例被拒绝，有效样例被接受；
6. 公开错误和普通日志不含完整 prompt、上传原文或图片 base64；
7. 本里程碑不触发真实付费 API 调用。

## 12. 后续迁移点

进入任务 7 前不需要替换本地适配器。部署准备时，在保持领域接口不变的前提下，分别添加 PostgreSQL 仓储、Redis 队列、对象存储和 OpenAI 生产网关。这些不是本设计的验收前置条件。
