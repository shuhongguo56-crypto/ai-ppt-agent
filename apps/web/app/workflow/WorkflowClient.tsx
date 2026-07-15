"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import type {
  AgentMode,
  CreditQuote,
  CompositionArchetype,
  DeckType,
  ImageAssetType,
  OutputLanguage,
  OutlineDecision,
  ProjectBrief,
  QualityReport,
  RenderResult,
  SlideDeck,
  SourceItem,
  SourcePack,
  VisualDirection,
  VisualDirectionDecision,
  VisualDirectionId,
} from "../../../../packages/contracts/typescript";

type ApiExport = {
  target: "pptx" | "hyperframes_html";
  contentType: string;
  slideCount: number;
  downloadUrl: string;
  previewUrl?: string | null;
};

type RuntimeStatus = {
  status: "ok";
  modelBackend: "fake" | "ollama" | "openai" | "cascade";
  realModelEnabled: boolean;
  realModelReady: boolean;
  freeModelEnabled?: boolean;
  freeModelReady?: boolean;
  modelReadinessMessage?: string | null;
  textModel: string;
  qualityModel: string;
  imageModel: string;
  providerChain?: Array<{
    name: string;
    model: string;
    configured: boolean;
    freeOrLocal: boolean;
  }>;
  imageSearchReady?: boolean;
  imageGenerationReady?: boolean;
  imageProviderChain?: Array<{
    name: string;
    model: string;
    configured: boolean;
    freeOrLocal: boolean;
  }>;
  defaultAgentMode?: AgentModeId;
  defaultCostArchitecture?: CostArchitectureId;
  agentModePolicy?: AgentModePolicy;
};

type AgentModeId = AgentMode;
type CostArchitectureId = "byok" | "hybrid_router" | "manual_prompt_workspace";

type AgentModePolicy = {
  defaultMode: AgentModeId;
  modes: Array<{
    id: AgentModeId;
    name: string;
    chineseName: string;
    costLevel: string;
    latencyTarget: string;
    defaultArchitecture: CostArchitectureId;
    researchDepth: string;
    bestFor: string[];
    guardrails: string[];
    modelRouting: Record<string, string>;
  }>;
  legalCostArchitectures: Array<{
    id: CostArchitectureId;
    name: string;
    chineseName: string;
    positioning: string;
    allowed: string[];
    notAllowed: string[];
  }>;
  dramaAgentStageRouting?: Array<{
    stage: string;
    routing: string;
    reason: string;
  }>;
  frontendMembershipRule: string;
};

type ImageAssetResolution = {
  slide: number;
  imageType: ImageAssetType;
  sourceType: string;
  mimeType: string;
  path: string;
  assetUrl: string;
  query: string;
  purpose: string;
  attribution?: string | null;
  providerChain: string[];
};

type QualityClosedLoop = {
  status: "ready" | "repair_required";
  headline: string;
  blocksExport: boolean;
  failedChecks: Array<{ name: string; detail: string }>;
  recommendedActions: string[];
};

type QualityCheckResponse = {
  version: number;
  qualityReport: QualityReport;
  closedLoop?: QualityClosedLoop;
  nextStep?: "export" | "repair_and_rerender" | string;
};

type WorkflowState = {
  projectId?: string;
  quote?: CreditQuote;
  outlineVersion?: number;
  outlineDecision?: OutlineDecision;
  visualVersion?: number;
  visualDecision?: VisualDirectionDecision;
  slideDeck?: SlideDeck;
  slideDeckVersion?: number;
  renderVersion?: number;
  qualityVersion?: number;
  qualityReport?: QualityReport;
  qualityClosedLoop?: QualityClosedLoop;
  renderResult?: RenderResult;
  imageAssets?: ImageAssetResolution[];
  exports: ApiExport[];
};

type OutlineGenerateResponse = {
  projectId: string;
  status: "draft" | "confirmed";
  version: number;
  outlineDecision: OutlineDecision;
  sourcePack?: SourcePack | null;
  research?: {
    mode: "supplied" | "web" | "local_fallback" | "disabled";
    providers: string[];
    query: string;
    warnings: string[];
  };
};

type UnderstandingStatus = "complete" | "partial";

type ExtractionCoverage = {
  unit: string;
  discovered?: number | null;
  processed: number;
  failed: number;
  skipped: number;
  analyzedChars: number;
};

type ExtractionWarning = {
  code: string;
  message: string;
  affectedUnits?: string[];
};

type SourceExtractResponse = {
  sourcePack: SourcePack;
  extractedChars: number;
  truncated: boolean;
  understandingStatus: UnderstandingStatus;
  coverage: ExtractionCoverage;
  warnings: ExtractionWarning[];
};

type SourceReport = {
  sourceId: string;
  title: string;
  thesis: string;
  keyArguments: string[];
  evidence: string[];
  pptSuggestions: string[];
  excerpts: string[];
  url?: string;
  extractedChars?: number;
  truncated?: boolean;
  understandingStatus?: UnderstandingStatus;
  coverage?: ExtractionCoverage;
  warnings?: ExtractionWarning[];
};

type OutlinePatchResponse = {
  version: number;
  outlineDecision: OutlineDecision;
};

type VisualGenerateResponse = {
  version: number;
  visualDirection: VisualDirectionDecision;
};

type ImageAgentResolveResponse = {
  projectId: string;
  slideDeckVersion: number;
  mode: "auto" | "web_first" | "generate";
  imageAssets: ImageAssetResolution[];
};

type ImageAgentJobResponse = {
  jobId: string;
  projectId: string;
  slideDeckVersion: number;
  mode: "auto" | "web_first" | "generate";
  status: "queued" | "running" | "completed" | "failed";
  imageAssets?: ImageAssetResolution[];
  error?: string;
};

type SlideDeckRepairResponse = {
  version: number;
  slideDeck: SlideDeck;
  failedChecks: string[];
  appliedRepairs: string[];
  repairPass: number;
};

type LogItem = { label: string; detail: string };
type OutputLanguageChoice = Extract<OutputLanguage, "zh" | "en">;
type VisualPreviewStyle = CSSProperties &
  Record<"--preview-bg" | "--preview-fg" | "--preview-accent" | "--preview-soft", string>;

const deckTypes: Array<{ value: DeckType; label: string }> = [
  { value: "course_presentation", label: "课程汇报" },
  { value: "thesis_defense", label: "论文答辩" },
  { value: "research_report", label: "研究报告" },
  { value: "business_pitch", label: "商业路演" },
  { value: "case_competition", label: "案例竞赛" },
];

const outputLanguages: Array<{ value: OutputLanguageChoice; label: string }> = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

const agentModes: Array<{ value: AgentModeId; label: string; note: string }> = [
  { value: "fast", label: "快速模式", note: "低成本快速预览，适合先看方向" },
  { value: "research", label: "研究模式（默认）", note: "按企业级/竞赛级 PPT 基线执行：深检索、强大纲、web-first 配图、奖项级质检" },
  { value: "enterprise", label: "企业模式", note: "BYOK/客户自有模型优先，审计轨迹和人工复核更严格" },
];

const visualStyleLabels: Record<VisualDirectionId, { label: string; note: string }> = {
  apple: { label: "Apple 发布会高级留白", note: "大留白、发布会感，适合概念讲解" },
  mckinsey: { label: "McKinsey 咨询逻辑", note: "结论先行、图表驱动，适合商业与研究" },
  airbnb: { label: "Airbnb 温暖故事感", note: "人本叙事、圆角卡片，适合案例展示" },
  academic_clean: { label: "学术极简白底", note: "干净可信，适合论文阅读和综述" },
  thesis_blue: { label: "蓝色论文答辩", note: "正式稳定，适合答辩和学术评审" },
  research_journal: { label: "Research Journal 期刊感", note: "文献感、图注友好，适合研究报告" },
  startup_pitch: { label: "Startup Pitch 明亮路演", note: "强节奏、大数字，适合创业项目" },
  investor_dark: { label: "Investor Dark 高级深色", note: "深色高端，适合投资人演示" },
  classroom_friendly: { label: "课堂友好清爽", note: "亲切易懂，适合老师授课和学生展示" },
  data_story: { label: "Data Story 数据叙事", note: "数据驱动、对比清晰，适合图表结果" },
  editorial_magazine: { label: "Editorial Magazine 杂志叙事", note: "图文错位，适合人文社科和案例分析" },
  glassmorphism: { label: "Glassmorphism 玻璃拟态", note: "科技感、毛玻璃，适合 AI/产品汇报" },
  medical_science: { label: "Medical Science 生命科学", note: "实验室可信感，适合生物医学与科学课程" },
  cinematic_research: { label: "Cinematic Research 纪录片研究", note: "景深叙事，适合把研究问题讲成故事" },
  policy_brief: { label: "Policy Brief 政策简报", note: "问题—证据—建议清晰，适合治理与公共议题" },
  ink_classical: { label: "Ink Classical 新中式国风", note: "书卷气与留白，适合古风、诗词、历史文化" },
  product_showcase: { label: "Product Showcase 产品展示", note: "产品图与价值主张优先，适合功能发布" },
  architectural_premium: { label: "Architectural Premium 建筑网格", note: "强网格、空间感，适合高端商业方案" },
  finance_terminal: { label: "Finance Terminal 金融终端", note: "指标与趋势优先，适合市场和经营分析" },
  workshop_playbook: { label: "Workshop Playbook 教学工作坊", note: "步骤清楚、可参与，适合课程复习和训练营" },
};

const compositionLabels: Record<CompositionArchetype, string> = {
  cinematic_hero: "电影感主视觉",
  editorial_cover: "杂志式封面",
  architectural_cover: "建筑网格封面",
  chapter_index: "章节索引",
  editorial_split: "编辑式图文分屏",
  diagonal_story: "斜向叙事",
  statement_focus: "核心观点聚焦",
  proof_mosaic: "证据拼贴",
  data_landscape: "数据全景",
  process_ribbon: "流程带",
  system_map: "系统关系图",
  split_comparison: "双栏对比",
  priority_stack: "优先级阶梯",
  closing_echo: "回响式收束",
  manifesto_close: "宣言式结尾",
  future_horizon: "未来地平线",
};

const imageTypeLabels: Record<ImageAssetType, string> = {
  background: "背景图",
  course_review_atmosphere: "课程复习氛围图",
  business_scene: "商业场景图",
  classical_element: "古风元素图",
  thesis_concept: "论文主题概念图",
  product_showcase: "产品展示图",
  icon_illustration: "图标与插画",
  data_visual: "数据证据图",
};

const audiencePresets = ["本科生 / 课程老师", "论文答辩委员会", "研究小组", "投资人 / 商业评委", "企业内部团队"];

const generationStages = [
  { key: "brief", label: "提出需求" },
  { key: "outline", label: "确认大纲" },
  { key: "visual", label: "选择风格" },
  { key: "deck", label: "生成页面" },
  { key: "export", label: "预览下载" },
] as const;

const briefSteps = ["主题", "资料", "受众", "语言", "场景", "模式", "确认"] as const;

type GenerationStageKey = (typeof generationStages)[number]["key"];

const designBenchmarks = [
  {
    name: "Slidev",
    badge: "Presenter",
    idea: "演示结果要像网页一样可预览、可放映、可移动端控制。",
  },
  {
    name: "reveal.js",
    badge: "HTML deck",
    idea: "HTML 演示必须有动画、讲稿、键盘导航和全屏放映。",
  },
  {
    name: "Open WebUI",
    badge: "Model ops",
    idea: "把模型路由、图片链路、连接状态透明展示给用户。",
  },
  {
    name: "Presenton",
    badge: "BYOK",
    idea: "用户自带 Key / 本地模型 / 多提供商路由，避免隐藏成本。",
  },
] as const;

const gptGradeBar = [
  { label: "资料理解", value: "SourcePack" },
  { label: "大纲决策", value: "HumanizePPT" },
  { label: "视觉导演", value: "Frontend-Slides" },
  { label: "配图智能体", value: "Web + Image API" },
  { label: "质量门", value: "Award QA" },
] as const;

const defaultApiBase = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://timeline-strong-hearing-resolve.trycloudflare.com/api"
).replace(/\/$/, "");
let sessionApiBase: string | null = null;

function normalizeApiBase(value: string) {
  const trimmed = value.trim().replace(/\/$/, "");
  if (!trimmed) return defaultApiBase;
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function apiBase() {
  if (typeof window === "undefined") return defaultApiBase;
  if (sessionApiBase) return sessionApiBase;
  const queryApi = new URLSearchParams(window.location.search).get("api");
  if (queryApi?.trim()) {
    const normalized = normalizeApiBase(queryApi);
    sessionApiBase = normalized;
    window.localStorage.setItem("ai-ppt-api-base", normalized);
    return normalized;
  }
  sessionApiBase = window.localStorage.getItem("ai-ppt-api-base") ?? defaultApiBase;
  return sessionApiBase;
}

function apiOrigin() {
  return apiBase().replace(/\/api$/, "");
}

function connectionErrorMessage(caught: unknown) {
  if (caught instanceof Error && caught.message) {
    if (caught.message.toLowerCase().includes("failed to fetch")) {
      return "无法连接后端。请确认本地 API 或公网 tunnel 正在运行，或在这里粘贴新的 API 地址。";
    }
    return caught.message;
  }
  return "无法连接后端。请确认 API 地址正确。";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }
  return (await response.json()) as T;
}

async function resolveProjectImages(
  projectId: string,
  slideDeckVersion: number,
  mode: "auto" | "generate",
): Promise<ImageAgentResolveResponse> {
  const started = await request<ImageAgentJobResponse>(`/projects/${projectId}/image-agent/resolve`, {
    method: "POST",
    body: JSON.stringify({ slideDeckVersion, mode, background: true }),
  });
  for (let attempt = 0; attempt < 300; attempt += 1) {
    const job =
      attempt === 0
        ? started
        : await request<ImageAgentJobResponse>(`/projects/${projectId}/image-agent/jobs/${started.jobId}`);
    if (job.status === "completed" && job.imageAssets) {
      return {
        projectId,
        slideDeckVersion,
        mode,
        imageAssets: job.imageAssets,
      };
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Image Agent failed. Please retry.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }
  throw new Error("Image Agent is still running. Please retry from the project library later.");
}

function secondsSince(start: number) {
  return `${((performance.now() - start) / 1000).toFixed(1)} 秒`;
}

function deckTypeLabel(value: DeckType) {
  return deckTypes.find((item) => item.value === value)?.label ?? value;
}

function languageLabel(value: OutputLanguageChoice) {
  return outputLanguages.find((item) => item.value === value)?.label ?? value;
}

function visualDirectionLabel(value: VisualDirectionId) {
  return visualStyleLabels[value]?.label ?? value;
}

function visualPreviewStyle(direction: VisualDirection): VisualPreviewStyle {
  const palette = direction.palette;
  return {
    "--preview-bg": colorOr(palette[0], "#0B0F19"),
    "--preview-fg": colorOr(palette[1], "#F8FAFC"),
    "--preview-accent": colorOr(palette[2], "#8AB4F8"),
    "--preview-soft": colorOr(palette.at(-1), "#D7E3FF"),
  };
}

function colorOr(value: string | undefined, fallback: string) {
  return value && value.trim().startsWith("#") ? value.trim() : fallback;
}

function stageRank(key: GenerationStageKey) {
  return generationStages.findIndex((stage) => stage.key === key);
}

function providerLabel(name: string) {
  const labels: Record<string, string> = {
    openai: "OpenAI",
    gemini: "Gemini",
    openrouter: "OpenRouter",
    groq: "Groq",
    "openai-compatible-local": "本地兼容",
    ollama: "Ollama",
    "enhanced-local-fallback": "本地增强兜底",
    "open-web-search": "联网搜图",
    "openai-image": "OpenAI Image",
    "midjourney-compatible": "Midjourney API",
    "stable-diffusion": "Stable Diffusion",
    "custom-image2": "自定义 image2",
    "local-svg-fallback": "本地视觉兜底",
  };
  return labels[name] ?? name;
}

function providerTone(provider: NonNullable<RuntimeStatus["providerChain"]>[number]) {
  if (!provider.configured) return "idle";
  return provider.freeOrLocal ? "local" : "ready";
}

function modeTone(mode: AgentModeId) {
  if (mode === "enterprise") return "enterprise";
  if (mode === "research") return "research";
  return "fast";
}

function costArchitectureLabel(id: CostArchitectureId) {
  const labels: Record<CostArchitectureId, string> = {
    byok: "用户自带 API Key",
    hybrid_router: "混合模型路由",
    manual_prompt_workspace: "前端会员人机协作",
  };
  return labels[id] ?? id;
}

function runtimeModeLabel(runtime: RuntimeStatus) {
  if (runtime.modelBackend === "cascade") {
    return runtime.realModelReady ? "多模型级联已启用" : "多模型级联待配置";
  }
  if (runtime.modelBackend === "ollama") {
    return runtime.freeModelReady ? "免费本地 Ollama 已就绪" : "免费本地 Ollama 未就绪";
  }
  if (runtime.modelBackend === "openai") {
    return runtime.realModelReady ? `真实 OpenAI API：${runtime.textModel}` : "OpenAI 模式缺少 API key";
  }
  return "本地离线增强验证";
}

function sectionValue(summary: string, heading: string) {
  const direct = summary
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith(`${heading}：`) || line.startsWith(`${heading}:`));
  if (!direct) return "";
  return direct.replace(new RegExp(`^${heading}[：:]\\s*`), "").trim();
}

function sectionItems(summary: string, heading: string, maxItems = 4) {
  const lines = summary.split("\n");
  const start = lines.findIndex((line) => {
    const trimmed = line.trim();
    return trimmed === `${heading}：` || trimmed === `${heading}:` || trimmed.startsWith(`${heading}：`);
  });
  if (start < 0) return [];
  const items: string[] = [];
  const inline = lines[start].split("：").slice(1).join("：").trim();
  if (inline) items.push(inline);
  for (const line of lines.slice(start + 1)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (/^[\w\u4e00-\u9fff /-]{2,30}[：:]$/.test(trimmed)) break;
    if (!trimmed.startsWith("-") && trimmed.endsWith("：")) break;
    const item = trimmed.replace(/^[-•*·]\s*/, "").trim();
    if (item) items.push(item);
    if (items.length >= maxItems) break;
  }
  return items;
}

function compactReportText(value: string, limit = 180) {
  const compact = value.replace(/\s+/g, " ").trim();
  return compact.length > limit ? `${compact.slice(0, limit)}…` : compact;
}

function buildSourceReport(source: SourceItem, extraction?: SourceExtractResponse): SourceReport {
  const summary = source.summary ?? "";
  const title = sectionValue(summary, "核心主题") || source.title || source.sourceId;
  const thesis = sectionValue(summary, "文章主旨") || compactReportText(summary, 220);
  return {
    sourceId: source.sourceId,
    title: compactReportText(title, 96),
    thesis: compactReportText(thesis, 260),
    keyArguments: sectionItems(summary, "关键论点", 5).map((item) => compactReportText(item, 220)),
    evidence: sectionItems(summary, "重要事实/数据/证据", 4).map((item) => compactReportText(item, 220)),
    pptSuggestions: sectionItems(summary, "可做成PPT的大纲建议", 5).map((item) => compactReportText(item, 220)),
    excerpts: sectionItems(summary, "原文摘录", 3).map((item) => compactReportText(item, 220)),
    url: source.url ?? undefined,
    extractedChars: extraction?.extractedChars,
    truncated: extraction?.truncated,
    understandingStatus: extraction?.understandingStatus ?? "complete",
    coverage: extraction?.coverage,
    warnings: extraction?.warnings ?? [],
  };
}

function coverageUnitLabel(unit: string) {
  const labels: Record<string, string> = {
    characters: "字符",
    pages: "页",
    slides: "页",
    parts: "文档部件",
  };
  return labels[unit] ?? unit;
}

function formatCoverageProgress(coverage: ExtractionCoverage) {
  const unit = coverageUnitLabel(coverage.unit);
  if (coverage.discovered === null || coverage.discovered === undefined) {
    return `${coverage.processed} ${unit}`;
  }
  return `${coverage.processed}/${coverage.discovered} ${unit}`;
}

function warningCodeLabel(code: string) {
  const labels: Record<string, string> = {
    analysis_char_limit: "达到分析上限",
    malformed_xml_part: "部分结构损坏",
    pdf_page_extract_failed: "PDF 页面读取失败",
    pdf_page_text_empty: "PDF 页面无可读文字",
    zip_part_too_large: "部件过大",
    zip_part_suspicious_compression: "压缩异常",
    zip_xml_budget_exceeded: "结构过大",
    zip_part_unreadable: "部件不可读",
  };
  return labels[code] ?? code;
}

function sourceWarningText(warning: ExtractionWarning) {
  const units = warning.affectedUnits?.length ? `（${warning.affectedUnits.join("、")}）` : "";
  return `${warningCodeLabel(warning.code)}${units}：${warning.message}`;
}

function extractionNotice(extracted: SourceExtractResponse) {
  if (extracted.understandingStatus !== "partial") return "";
  const codes = extracted.warnings.map((warning) => warningCodeLabel(warning.code)).filter(Boolean);
  const reason = codes.length ? codes.slice(0, 3).join("、") : "部分内容未能读取";
  return `只部分理解：${reason}。已基于 ${extracted.coverage.analyzedChars} 字符继续生成，请在确认大纲时对照原文件。`;
}

export default function WorkflowClient() {
  const [topic, setTopic] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [audience, setAudience] = useState("");
  const [deckType, setDeckType] = useState<DeckType>("course_presentation");
  const [outputLanguage, setOutputLanguage] = useState<OutputLanguageChoice>("zh");
  const [agentMode, setAgentMode] = useState<AgentModeId>("research");
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [conversationStep, setConversationStep] = useState(1);
  const [apiBaseInput, setApiBaseInput] = useState(defaultApiBase);
  const [apiConnection, setApiConnection] = useState<"checking" | "connected" | "error">("checking");
  const [apiError, setApiError] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [state, setState] = useState<WorkflowState>({ exports: [] });
  const [outlineDraft, setOutlineDraft] = useState<OutlineDecision | null>(null);
  const [sourceReports, setSourceReports] = useState<SourceReport[]>([]);
  const [activeVisualDirectionId, setActiveVisualDirectionId] = useState<VisualDirectionId | null>(null);
  const previewAnimationRef = useRef<Animation | null>(null);
  const previewMotionRef = useRef({ x: 0, y: 0, velocityX: 0, velocityY: 0, time: 0 });

  const canDownload = state.exports.length > 0;
  const hasReviewableOutline = Boolean(state.projectId && state.outlineVersion && state.outlineDecision && !state.visualDecision && !canDownload);
  const hasVisualChoices = Boolean(state.projectId && state.visualVersion && state.visualDecision && !state.slideDeckVersion && !canDownload);
  const activeOutline = outlineDraft ?? state.outlineDecision;
  const outlineDirty = Boolean(outlineDraft && state.outlineDecision && outlineDraft !== state.outlineDecision);
  const latestLog = logs.at(-1);
  const htmlExport = state.exports.find((item) => item.target === "hyperframes_html");
  const pptxExport = state.exports.find((item) => item.target === "pptx");
  const partialSourceCount = sourceReports.filter((report) => report.understandingStatus === "partial").length;
  const qualityFailed = Boolean(state.qualityReport && !state.qualityReport.passed);
  const qualityPassedCount = state.qualityReport?.checks.filter((check) => check.status === "passed").length ?? 0;
  const qualityTotalCount = state.qualityReport?.checks.length ?? 0;
  const hasWorkflowOutput = Boolean(isRunning || error || logs.length || state.projectId || canDownload);
  const currentStage: GenerationStageKey = canDownload
    ? "export"
    : state.renderVersion || state.slideDeckVersion
      ? "deck"
      : hasVisualChoices
        ? "visual"
        : hasReviewableOutline
          ? "outline"
          : topic.trim() || isRunning
            ? "brief"
            : "brief";
  const currentStageLabel = generationStages.find((stage) => stage.key === currentStage)?.label ?? "输入信息";
  const progressText = useMemo(() => {
    if (canDownload) return "你的 PPT 已经生成好了";
    if (qualityFailed) return "我拦住了未达标文件，正在等你一键返修";
    if (hasVisualChoices) return `我准备了 ${state.visualDecision?.directions.length ?? "多"} 套视觉方案`;
    if (hasReviewableOutline) return "我先帮你整理好了大纲";
    if (isRunning) return latestLog?.detail ?? "正在为你生成 PPT…";
    return "回答左边几个问题后，我就开始生成。";
  }, [canDownload, hasReviewableOutline, hasVisualChoices, isRunning, latestLog?.detail, qualityFailed, state.visualDecision?.directions.length]);

  useEffect(() => {
    const resolvedApiBase = apiBase();
    setApiBaseInput(resolvedApiBase);
    void refreshRuntime(resolvedApiBase);
  }, []);

  useEffect(() => () => previewAnimationRef.current?.cancel(), []);

  function push(label: string, detail: string) {
    setLogs((current) => [...current, { label, detail }]);
  }

  async function refreshRuntime(nextApiBase = apiBaseInput) {
    const normalized = normalizeApiBase(nextApiBase);
    sessionApiBase = normalized;
    if (typeof window !== "undefined") {
      window.localStorage.setItem("ai-ppt-api-base", normalized);
    }
    setApiBaseInput(normalized);
    setApiConnection("checking");
    setApiError(null);
    try {
      const latestRuntime = await request<RuntimeStatus>("/runtime/status");
      setRuntime(latestRuntime);
      setApiConnection("connected");
    } catch (caught) {
      setRuntime(null);
      setApiConnection("error");
      setApiError(connectionErrorMessage(caught));
    }
  }

  function resetApiBase() {
    void refreshRuntime(defaultApiBase);
  }

  async function step<T>(label: string, detail: string, action: () => Promise<T>): Promise<T> {
    const start = performance.now();
    push(label, `${detail}…`);
    const result = await action();
    push(label, `完成，用时 ${secondsSince(start)}`);
    return result;
  }

  function importFiles(files: FileList | null) {
    setUploadedFiles(Array.from(files ?? []).slice(0, 5));
  }

  function revealNext(step: number) {
    setConversationStep(step);
  }

  function revealPrevious() {
    setConversationStep((current) => Math.max(1, current - 1));
  }

  function previewSlide(stage: HTMLDivElement) {
    return stage.querySelector<HTMLElement>(".studio-slide");
  }

  function updatePreviewFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    const slide = previewSlide(event.currentTarget);
    if (!slide || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - 0.5) * 2));
    const y = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - 0.5) * 2));
    const now = performance.now();
    const previous = previewMotionRef.current;
    const elapsed = Math.max(8, now - previous.time);
    previewMotionRef.current = {
      x,
      y,
      velocityX: ((x - previous.x) / elapsed) * 1000,
      velocityY: ((y - previous.y) / elapsed) * 1000,
      time: now,
    };
    slide.style.transform =
      `rotateX(${5 - y * 4}deg) rotateY(${-9 + x * 6}deg) rotateZ(${-1.2 + x * 0.7}deg) ` +
      `translate3d(${x * 6}px, ${y * 4}px, 0) scale(1.012)`;
  }

  function handlePreviewPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === "touch" || event.button !== 0) return;
    const slide = previewSlide(event.currentTarget);
    if (!slide) return;
    if (previewAnimationRef.current) {
      const liveTransform = window.getComputedStyle(slide).transform;
      previewAnimationRef.current.cancel();
      slide.style.transform = liveTransform;
      previewAnimationRef.current = null;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.classList.add("is-grabbed");
    previewMotionRef.current = { x: 0, y: 0, velocityX: 0, velocityY: 0, time: performance.now() };
    updatePreviewFromPointer(event);
  }

  function releasePreview(event: ReactPointerEvent<HTMLDivElement>) {
    const stage = event.currentTarget;
    const slide = previewSlide(stage);
    if (!slide || !stage.hasPointerCapture(event.pointerId)) return;
    stage.releasePointerCapture(event.pointerId);
    stage.classList.remove("is-grabbed");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      slide.style.removeProperty("transform");
      return;
    }
    const current = window.getComputedStyle(slide).transform;
    const motion = previewMotionRef.current;
    const projectedX = Math.max(-1.4, Math.min(1.4, motion.x + motion.velocityX * 0.018));
    const projectedY = Math.max(-1.4, Math.min(1.4, motion.y + motion.velocityY * 0.018));
    const projected =
      `rotateX(${5 - projectedY * 4}deg) rotateY(${-9 + projectedX * 6}deg) ` +
      `rotateZ(${-1.2 + projectedX * 0.7}deg) translate3d(${projectedX * 6}px, ${projectedY * 4}px, 0) scale(1.006)`;
    const rest = "rotateX(5deg) rotateY(-9deg) rotateZ(-1.2deg) translate3d(0, 0, 0) scale(1)";
    slide.style.transform = current;
    const animation = slide.animate(
      [
        { transform: current, offset: 0 },
        { transform: projected, offset: 0.22 },
        { transform: rest, offset: 1 },
      ],
      { duration: 420, easing: "cubic-bezier(0.22, 0.72, 0.18, 1)", fill: "forwards" },
    );
    previewAnimationRef.current = animation;
    animation.onfinish = () => {
      slide.style.removeProperty("transform");
      previewAnimationRef.current = null;
    };
  }

  function resetConversation() {
    setTopic("");
    setSourceText("");
    setAudience("");
    setDeckType("course_presentation");
    setOutputLanguage("zh");
    setAgentMode("research");
    setUploadedFiles([]);
    setConversationStep(1);
    setError(null);
    setLogs([]);
    setState({ exports: [] });
    setOutlineDraft(null);
    setSourceReports([]);
    setActiveVisualDirectionId(null);
  }

  function updateOutlineObjective(value: string) {
    setOutlineDraft((current) => (current ? { ...current, objective: value } : current));
  }

  function updateOutlineSlide(
    slideIndex: number,
    patch: Partial<Pick<OutlineDecision["slides"][number], "title" | "keyPoint" | "speakerNotesDraft">>,
  ) {
    setOutlineDraft((current) =>
      current
        ? {
            ...current,
            slides: current.slides.map((slide) =>
              slide.slideIndex === slideIndex ? { ...slide, ...patch } : slide,
            ),
          }
        : current,
    );
  }

  async function saveOutlineDraft(projectId: string, expectedVersion: number, outlineDecision: OutlineDecision) {
    const saved = await request<OutlinePatchResponse>(`/projects/${projectId}/outline`, {
      method: "PATCH",
      body: JSON.stringify({ expectedVersion, outlineDecision }),
    });
    setOutlineDraft(saved.outlineDecision);
    setState((current) => ({
      ...current,
      outlineVersion: saved.version,
      outlineDecision: saved.outlineDecision,
      exports: [],
    }));
    return saved;
  }

  async function fileToBase64(file: File): Promise<string> {
    const buffer = await file.arrayBuffer();
    let binary = "";
    const bytes = new Uint8Array(buffer);
    for (let index = 0; index < bytes.length; index += 1) {
      binary += String.fromCharCode(bytes[index]);
    }
    return btoa(binary);
  }

  function textToBase64(value: string): string {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (let index = 0; index < bytes.length; index += 1) {
      binary += String.fromCharCode(bytes[index]);
    }
    return btoa(binary);
  }

  function sourceSummaryPreview(source: SourceItem | undefined) {
    const summary = source?.summary ?? "";
    const compact = summary
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 8)
      .join(" / ");
    return compact.length > 420 ? `${compact.slice(0, 420)}…` : compact;
  }

  async function sourcePack(projectId: string): Promise<SourcePack | undefined> {
    const sources: SourceItem[] = [];
    const reports: SourceReport[] = [];
    if (sourceText.trim()) {
      const extracted = await step("资料解析", "解析你粘贴的文字资料并生成 SourcePack 阅读报告", () =>
        request<SourceExtractResponse>(`/projects/${projectId}/sources/extract`, {
          method: "POST",
          body: JSON.stringify({
            fileName: "typed-notes.txt",
            contentType: "text/plain; charset=utf-8",
            dataBase64: textToBase64(sourceText.trim()),
          }),
        }),
      );
      sources.push(...(extracted.sourcePack.sources ?? []));
      reports.push(
        ...(extracted.sourcePack.sources ?? []).map((source) => buildSourceReport(source, extracted)),
      );
      setSourceReports([...reports]);
      const preview = sourceSummaryPreview(extracted.sourcePack.sources?.[0]);
      if (preview) {
        push("文件理解", preview);
      }
      const notice = extractionNotice(extracted);
      if (notice) {
        push("资料解析提示", `粘贴资料${notice}`);
      }
    }
    for (const file of uploadedFiles) {
      const encoded = await fileToBase64(file);
      const extracted = await step("资料解析", `解析上传文件：${file.name}`, () =>
        request<SourceExtractResponse>(`/projects/${projectId}/sources/extract`, {
          method: "POST",
          body: JSON.stringify({
            fileName: file.name,
            contentType: file.type || null,
            dataBase64: encoded,
          }),
        }),
      );
      sources.push(...(extracted.sourcePack.sources ?? []));
      reports.push(
        ...(extracted.sourcePack.sources ?? []).map((source) => buildSourceReport(source, extracted)),
      );
      setSourceReports([...reports]);
      const preview = sourceSummaryPreview(extracted.sourcePack.sources?.[0]);
      if (preview) {
        push("文件理解", `${file.name}：${preview}`);
      }
      const notice = extractionNotice(extracted);
      if (notice) {
        push("资料解析提示", `${file.name} ${notice}`);
      }
    }
    setSourceReports(reports);
    if (sources.length === 0) return undefined;
    return {
      schemaVersion: "1.0.0",
      projectId,
      sources,
    };
  }

  async function createProjectAndOutline() {
    setIsRunning(true);
    setError(null);
    setLogs([]);
    setState({ exports: [] });
    setOutlineDraft(null);
    setSourceReports([]);
    setActiveVisualDirectionId(null);
    try {
      const latestRuntime = await step("运行模式", "读取 FastAPI 后端模型状态", () => request<RuntimeStatus>("/runtime/status"));
      setRuntime(latestRuntime);
      if (latestRuntime.realModelReady) {
        push(
          "模型后端",
          latestRuntime.modelBackend === "cascade"
            ? `多模型级联已启用：${latestRuntime.providerChain?.map((item) => item.name).join(" → ") || latestRuntime.textModel}`
            : `真实 OpenAI API 已启用：${latestRuntime.textModel}`,
        );
      } else if (latestRuntime.modelBackend === "ollama") {
        push(
          "模型后端",
          latestRuntime.freeModelReady
            ? `免费本地 Ollama AI 已就绪：${latestRuntime.textModel}`
            : latestRuntime.modelReadinessMessage ?? `免费本地 Ollama AI 未就绪：${latestRuntime.textModel}`,
        );
      } else if (latestRuntime.modelBackend === "openai") {
        push("模型后端", "OpenAI 模式已开启，但 key 未配置，后端会拒绝真实生成。");
      } else if (latestRuntime.modelBackend === "cascade") {
        push("模型后端", latestRuntime.modelReadinessMessage ?? "多模型级联模式已开启，但没有可用模型。");
      } else {
        push("模型后端", "当前是本地 Fake 离线验证模式；配置 key 后可切换真实 API。");
      }

      const projectId = `demo-${Date.now()}`;
      const brief: ProjectBrief = {
        schemaVersion: "1.0.0",
        projectId,
        inputLanguage: "zh",
        outputLanguage,
        deckType,
        topic,
        audience,
        mode: "professional",
        agentMode,
      };
      const selectedAgentMode = agentModes.find((item) => item.value === agentMode);
      push("生成层级", `${selectedAgentMode?.label ?? agentMode}：${selectedAgentMode?.note ?? ""}`);

      await step("项目", "创建 ProjectBrief", () =>
        request<{ projectId: string }>("/projects", { method: "POST", body: JSON.stringify(brief) }),
      );

      const quote = await step("积分", "计算本次生成积分预估", () =>
        request<{ quote: CreditQuote }>(`/projects/${projectId}/credits/quote`),
      );

      const pack = await sourcePack(projectId);
      const outline = await step(
        pack ? "大纲" : "联网研究",
        pack
          ? "调用 HumanizePPT 从 SourcePack 生成 OutlineDecision JSON"
          : "未提供资料：先检索公开资料并生成 SourcePack，再调用 HumanizePPT",
        () =>
        request<OutlineGenerateResponse>(`/projects/${projectId}/outline/generate`, {
          method: "POST",
          body: JSON.stringify(
            pack
              ? { sourcePack: pack, supplementResearch: agentMode !== "fast" }
              : {},
          ),
        }),
      );

      if (outline.sourcePack?.sources?.length) {
        setSourceReports(outline.sourcePack.sources.map((source) => buildSourceReport(source)));
        const providers = outline.research?.providers.join("、") || "本地研究降级";
        push(
          outline.research?.mode.includes("web") ? "联网研究完成" : "联网研究降级",
          outline.research?.mode.includes("web")
            ? `已从 ${providers} 获取 ${outline.sourcePack.sources.length} 个公开来源，大纲将引用这些资料。`
            : "公开资料暂时不可用，已明确标记为本地研究框架；涉及事实和数据的内容仍需联网来源验证。",
        );
        outline.research?.warnings.forEach((warning) => push("研究提示", warning));
      }

      setState({
        projectId,
        quote: quote.quote,
        outlineVersion: outline.version,
        outlineDecision: outline.outlineDecision,
        exports: [],
      });
      setOutlineDraft(outline.outlineDecision);
      push("大纲审阅", "已暂停在 PPT 大纲审阅步骤；确认大纲后，才能进入视觉方案和导出。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "未知工作流错误");
    } finally {
      setIsRunning(false);
    }
  }

  async function continueAfterOutline(
    projectId = state.projectId,
    outlineVersion = state.outlineVersion,
    quote = state.quote,
    outlineDecision = state.outlineDecision,
  ) {
    if (!projectId || !outlineVersion || !outlineDecision) return;
    setIsRunning(true);
    setError(null);
    setActiveVisualDirectionId(null);
    try {
      let versionToConfirm = outlineVersion;
      let outlineToUse = outlineDecision;
      const draftToSave = outlineDraft?.projectId === projectId ? outlineDraft : undefined;
      const savedOutline = state.outlineDecision?.projectId === projectId ? state.outlineDecision : undefined;
      if (draftToSave && savedOutline && draftToSave !== savedOutline) {
        const saved = await step("大纲保存", "保存你编辑后的标题、要点和讲稿备注", () =>
          saveOutlineDraft(projectId, outlineVersion, draftToSave),
        );
        versionToConfirm = saved.version;
        outlineToUse = saved.outlineDecision;
      }

      const confirmedOutline = await step("大纲确认", "确认大纲检查点，进入视觉阶段", () =>
        request<{ version: number }>(`/projects/${projectId}/outline/confirm`, {
          method: "POST",
          body: JSON.stringify({ outlineDecisionVersion: versionToConfirm }),
        }),
      );

      const visual = await step("视觉方案", "调用 Frontend-Slides 基于大纲动态生成多套 VisualDirection，由内容复杂度和模式决定数量", () =>
        request<VisualGenerateResponse>(`/projects/${projectId}/visual-directions/generate`, {
          method: "POST",
          body: JSON.stringify({ outlineDecisionVersion: confirmedOutline.version }),
        }),
      );

      setState({
        projectId,
        quote,
        outlineVersion: confirmedOutline.version,
        outlineDecision: outlineToUse,
        visualVersion: visual.version,
        visualDecision: visual.visualDirection,
        exports: [],
      });
      setOutlineDraft(outlineToUse);
      push("视觉方案", `Frontend-Slides 已基于大纲生成 ${visual.visualDirection.directions.length} 套候选方向。选择任一方向后，将立即组装 SlideDeck JSON 并导出 PPTX/HTML。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "未知工作流错误");
    } finally {
      setIsRunning(false);
    }
  }

  async function finishWithVisualDirection(direction: VisualDirection) {
    if (!state.projectId || !state.visualVersion || !state.visualDecision || !state.outlineDecision) return;
    setIsRunning(true);
    setError(null);
    setActiveVisualDirectionId(direction.directionId);
    try {
      const selected = await step("方案选择", `选择视觉方案：${direction.name}`, () =>
        request<{ version: number; visualDirection: VisualDirectionDecision }>(`/projects/${state.projectId}/visual-directions/select`, {
          method: "POST",
          body: JSON.stringify({ visualDirectionVersion: state.visualVersion, directionId: direction.directionId }),
        }),
      );

      const deck = await step("逐页设计", "按每页内容规划构图、层级、配图与动效，并组装统一 SlideDeck JSON", () =>
        request<{ version: number; slideDeck: SlideDeck }>(`/projects/${state.projectId}/slide-deck/assemble`, {
          method: "POST",
          body: JSON.stringify({ visualDirectionVersion: selected.version }),
        }),
      );
      const compositionCount = new Set(
        deck.slideDeck.slides.map((slide) => slide.designPlan.compositionArchetype),
      ).size;
      push(
        "逐页设计",
        `已为 ${deck.slideDeck.slides.length} 页分别规划版式，共使用 ${compositionCount} 种构图；PPTX 和 HTML 共用这份 JSON。`,
      );

      const resolvedImages = await step("Image Agent", "先联网搜图；搜不到时调用已配置的生图 provider，并保留本地视觉兜底", () =>
        resolveProjectImages(state.projectId!, deck.version, "auto"),
      );
      push("Image Agent", imageSourceSummary(resolvedImages.imageAssets));

      const rendered = await step("渲染", "从同一份 SlideDeck JSON 渲染 PPTX 与 HyperFrames HTML", () =>
        request<{ version: number; renderResult: RenderResult }>(`/projects/${state.projectId}/render`, {
          method: "POST",
          body: JSON.stringify({ slideDeckVersion: deck.version }),
        }),
      );

      const quality = await step("质量检查", "检查渲染产物和导出门禁", () =>
        request<QualityCheckResponse>(`/projects/${state.projectId}/quality/check`, {
          method: "POST",
          body: JSON.stringify({ renderVersion: rendered.version }),
        }),
      );
      push("质量检查", quality.qualityReport.passed ? "质量检查通过，可以下载。" : "质量检查未通过，已进入返修闭环。");

      if (!quality.qualityReport.passed) {
        setState((current) => ({
          ...current,
          visualVersion: selected.version,
          visualDecision: selected.visualDirection,
          slideDeck: deck.slideDeck,
          slideDeckVersion: deck.version,
          imageAssets: resolvedImages.imageAssets,
          renderVersion: rendered.version,
          qualityVersion: quality.version,
          qualityReport: quality.qualityReport,
          qualityClosedLoop: quality.closedLoop,
          renderResult: rendered.renderResult,
          exports: [],
        }));
        return;
      }

      const exports = await step("导出", "生成下载链接", () =>
        request<{ exports: ApiExport[] }>(`/projects/${state.projectId}/exports`),
      );

      setState((current) => ({
        ...current,
        visualVersion: selected.version,
        visualDecision: selected.visualDirection,
        slideDeck: deck.slideDeck,
        slideDeckVersion: deck.version,
        imageAssets: resolvedImages.imageAssets,
        renderVersion: rendered.version,
        qualityVersion: quality.version,
        qualityReport: quality.qualityReport,
        qualityClosedLoop: quality.closedLoop,
        renderResult: rendered.renderResult,
        exports: exports.exports,
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "未知工作流错误");
    } finally {
      setIsRunning(false);
      setActiveVisualDirectionId(null);
    }
  }

  function imageSourceSummary(assets: ImageAssetResolution[]) {
    const counts = assets.reduce<Record<string, number>>((acc, asset) => {
      acc[asset.sourceType] = (acc[asset.sourceType] ?? 0) + 1;
      return acc;
    }, {});
    const summary = Object.entries(counts)
      .map(([source, count]) => `${source} × ${count}`)
      .join("，");
    return `已为 ${assets.length} 页解析配图资产：${summary || "暂无资产"}。`;
  }

  async function regenerateImages(mode: "auto" | "generate") {
    if (!state.projectId || !state.slideDeckVersion || !state.renderVersion) return;
    setIsRunning(true);
    setError(null);
    try {
      const resolvedImages = await step(
        "Image Agent",
        mode === "generate" ? "一键调用生图 provider 重新生成每页视觉资产" : "重新联网搜图并刷新每页视觉资产",
        () =>
          resolveProjectImages(state.projectId!, state.slideDeckVersion!, mode),
      );
      push("Image Agent", imageSourceSummary(resolvedImages.imageAssets));
      const rendered = await step("重新渲染", "用新的图片资产刷新 PPTX 与 HyperFrames HTML", () =>
        request<{ version: number; renderResult: RenderResult }>(`/projects/${state.projectId}/render`, {
          method: "POST",
          body: JSON.stringify({
            slideDeckVersion: state.slideDeckVersion,
            imageResolutionMode: mode === "generate" ? "generate" : "auto",
          }),
        }),
      );
      const quality = await step("质量检查", "重新检查渲染产物和导出门禁", () =>
        request<QualityCheckResponse>(`/projects/${state.projectId}/quality/check`, {
          method: "POST",
          body: JSON.stringify({ renderVersion: rendered.version }),
        }),
      );
      if (!quality.qualityReport.passed) {
        setState((current) => ({
          ...current,
          imageAssets: resolvedImages.imageAssets,
          renderVersion: rendered.version,
          qualityVersion: quality.version,
          qualityReport: quality.qualityReport,
          qualityClosedLoop: quality.closedLoop,
          renderResult: rendered.renderResult,
          exports: [],
        }));
        return;
      }
      const exports = await step("导出", "刷新下载链接", () =>
        request<{ exports: ApiExport[] }>(`/projects/${state.projectId}/exports`),
      );
      setState((current) => ({
        ...current,
        imageAssets: resolvedImages.imageAssets,
        renderVersion: rendered.version,
        qualityVersion: quality.version,
        qualityReport: quality.qualityReport,
        qualityClosedLoop: quality.closedLoop,
        renderResult: rendered.renderResult,
        exports: exports.exports,
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "未知工作流错误");
    } finally {
      setIsRunning(false);
    }
  }

  async function autoRepairQuality() {
    if (!state.projectId || !state.slideDeckVersion || !state.qualityVersion) return;
    setIsRunning(true);
    setError(null);
    let deckVersion = state.slideDeckVersion;
    let qualityVersion = state.qualityVersion;
    let finalDeck = state.slideDeck;
    let finalImages = state.imageAssets;
    let finalRender = state.renderResult;
    let finalRenderVersion = state.renderVersion;
    let finalQuality = state.qualityReport;
    let finalClosedLoop = state.qualityClosedLoop;
    try {
      for (let repairPass = 1; repairPass <= 2; repairPass += 1) {
        const repaired = await step(
          "自动返修",
          `第 ${repairPass} 轮：按未通过项压缩文案、调整页面构图和配图意图`,
          () =>
            request<SlideDeckRepairResponse>(`/projects/${state.projectId}/slide-deck/repair`, {
              method: "POST",
              body: JSON.stringify({
                slideDeckVersion: deckVersion,
                qualityReportVersion: qualityVersion,
                repairPass,
              }),
            }),
        );
        deckVersion = repaired.version;
        finalDeck = repaired.slideDeck;
        push("返修策略", repaired.appliedRepairs.join(" · "));

        const imageMode = repairPass === 1 ? "auto" : "generate";
        const resolvedImages = await step(
          "Image Agent",
          repairPass === 1 ? "按新页面意图重新联网搜图" : "第二轮改用生图链路补齐视觉资产",
          () =>
            resolveProjectImages(state.projectId!, deckVersion, imageMode),
        );
        finalImages = resolvedImages.imageAssets;
        push("Image Agent", imageSourceSummary(resolvedImages.imageAssets));

        const rendered = await step("重新渲染", "从返修后的统一 SlideDeck JSON 重建 PPTX 与动态 HTML", () =>
          request<{ version: number; renderResult: RenderResult }>(`/projects/${state.projectId}/render`, {
            method: "POST",
            body: JSON.stringify({
              slideDeckVersion: deckVersion,
              imageResolutionMode: imageMode,
            }),
          }),
        );
        finalRender = rendered.renderResult;
        finalRenderVersion = rendered.version;

        const quality = await step("重新质检", `执行第 ${repairPass} 轮客户交付门禁`, () =>
          request<QualityCheckResponse>(`/projects/${state.projectId}/quality/check`, {
            method: "POST",
            body: JSON.stringify({ renderVersion: rendered.version }),
          }),
        );
        qualityVersion = quality.version;
        finalQuality = quality.qualityReport;
        finalClosedLoop = quality.closedLoop;

        if (quality.qualityReport.passed) {
          const exports = await step("导出", "质检通过，开放客户下载", () =>
            request<{ exports: ApiExport[] }>(`/projects/${state.projectId}/exports`),
          );
          setState((current) => ({
            ...current,
            slideDeck: finalDeck,
            slideDeckVersion: deckVersion,
            imageAssets: finalImages,
            renderVersion: finalRenderVersion,
            renderResult: finalRender,
            qualityVersion,
            qualityReport: finalQuality,
            qualityClosedLoop: finalClosedLoop,
            exports: exports.exports,
          }));
          return;
        }
      }

      setState((current) => ({
        ...current,
        slideDeck: finalDeck,
        slideDeckVersion: deckVersion,
        imageAssets: finalImages,
        renderVersion: finalRenderVersion,
        renderResult: finalRender,
        qualityVersion,
        qualityReport: finalQuality,
        qualityClosedLoop: finalClosedLoop,
        exports: [],
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "自动返修失败");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="workflow-page">
      <section className="workflow-shell">
        <nav className="workspace-chrome" aria-label="AI PPT 工作台导航">
          <a className="workspace-brand" href="/" aria-label="返回 AI PPT 首页">
            <span aria-hidden="true">A</span>
            <strong>AI PPT</strong>
          </a>
          <div className="workspace-context" aria-live="polite">
            <small>当前步骤</small>
            <span>{currentStageLabel}</span>
          </div>
          <div className="workspace-actions">
            <a href="/projects">项目库</a>
            <span className={`connection-chip ${apiConnection}`}>
              <i aria-hidden="true" />
              {apiConnection === "connected" ? "准备就绪" : apiConnection === "checking" ? "准备中" : "暂不可用"}
            </span>
          </div>
        </nav>
        <div className="workflow-intro">
          <div className="customer-hero">
            <div className="customer-hero-copy">
              <p className="eyebrow">AI PRESENTATION STUDIO</p>
              <h1>让内容，<br />值得被看见。</h1>
              <p className="lead">输入主题或文件，下一步即可。</p>
              <a className="hero-start" href="#ppt-brief">
                开始创作
                <span aria-hidden="true">↘</span>
              </a>
            </div>
            <div className="studio-showcase" aria-label="PPT 视觉方向动态预览">
              <div
                className="studio-stage"
                aria-hidden="true"
                onPointerDown={handlePreviewPointerDown}
                onPointerMove={(event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) updatePreviewFromPointer(event);
                }}
                onPointerUp={releasePreview}
                onPointerCancel={releasePreview}
              >
                <div className="studio-backdrop studio-backdrop-one" />
                <div className="studio-backdrop studio-backdrop-two" />
                <div className="studio-slide">
                  <span>VISION / 01</span>
                  <strong>{topic.trim() || "让洞察成为画面的主角"}</strong>
                  <em>CONTENT-LED PRESENTATION</em>
                  <div className="studio-slide-art" />
                </div>
              </div>
              <div className="studio-copy">
                <strong>每份内容，都有自己的视觉语言。</strong>
              </div>
            </div>
          </div>
          <details className={`runtime-banner api-health ${apiConnection}`}>
            <summary className="runtime-summary">
              <span className="runtime-status-line">
                <strong>专业设置</strong>
                {apiConnection === "connected" ? <span>在线</span> : null}
                {apiConnection === "checking" ? <span>连接中</span> : null}
                {apiConnection === "error" ? <span>离线</span> : null}
              </span>
            </summary>
            <div className="runtime-panel">
              <label className="api-base-control">
                API 地址
                <input
                  aria-label="当前 API 地址"
                  value={apiBaseInput}
                  placeholder="https://your-api.example.com/api"
                  onChange={(event) => setApiBaseInput(event.target.value)}
                />
              </label>
              <div className="api-actions">
                <button className="button secondary api-button" type="button" onClick={() => void refreshRuntime()}>
                  重新连接
                </button>
                <button className="button ghost-button api-button" type="button" onClick={resetApiBase}>
                  恢复本机默认
                </button>
              </div>
              {runtime?.providerChain?.length ? (
                <div className="provider-chain" aria-label="模型调用顺序">
                  <strong>模型：</strong>
                  {runtime.providerChain.map((provider) => (
                    <span className={`provider-pill ${providerTone(provider)}`} key={`${provider.name}-${provider.model}`}>
                      {providerLabel(provider.name)}
                    </span>
                  ))}
                </div>
              ) : null}
              {runtime?.imageProviderChain?.length ? (
                <div className="provider-chain image-provider-chain" aria-label="图片搜索与生图调用顺序">
                  <strong>图片：</strong>
                  {runtime.imageProviderChain.map((provider) => (
                    <span className={`provider-pill ${providerTone(provider)}`} key={`image-${provider.name}-${provider.model}`}>
                      {providerLabel(provider.name)}
                    </span>
                  ))}
                </div>
              ) : null}
              {runtime?.agentModePolicy ? (
                <div className="agent-mode-panel" aria-label="合法低成本智能体模式">
                  <div className="agent-mode-heading">
                    <strong>智能体分层</strong>
                    <span>
                      默认：{runtime.agentModePolicy.modes.find((mode) => mode.id === runtime.agentModePolicy?.defaultMode)?.chineseName ??
                        runtime.agentModePolicy.defaultMode}
                    </span>
                  </div>
                  <div className="agent-mode-grid">
                    {runtime.agentModePolicy.modes.map((mode) => (
                      <article className={`agent-mode-card ${modeTone(mode.id)}`} key={mode.id}>
                        <div>
                          <strong>{mode.chineseName}</strong>
                          <small>{mode.costLevel} · {costArchitectureLabel(mode.defaultArchitecture)}</small>
                        </div>
                        <p>{mode.researchDepth}</p>
                        <em>{mode.bestFor.slice(0, 2).join(" / ")}</em>
                      </article>
                    ))}
                  </div>
                  <div className="cost-architecture-grid">
                    {runtime.agentModePolicy.legalCostArchitectures.map((architecture) => (
                      <article key={architecture.id}>
                        <strong>{architecture.chineseName}</strong>
                        <p>{architecture.positioning}</p>
                      </article>
                    ))}
                  </div>
                  <p className="membership-rule">{runtime.agentModePolicy.frontendMembershipRule}</p>
                </div>
              ) : null}
              {apiError ? <em className="api-error">{apiError}</em> : null}
              {runtime?.modelReadinessMessage ? <em>{runtime.modelReadinessMessage}</em> : null}
              <div className="gpt-grade-panel backstage-mini" aria-label="PPT 生成能力">
                <div className="gpt-grade-heading">
                  <strong>后台生成链路</strong>
                  <span>{runtime ? runtimeModeLabel(runtime) : "等待连接"}</span>
                </div>
                <div className="gpt-grade-bar">
                  {gptGradeBar.map((item) => (
                    <span key={item.label}>
                      <b>{item.label}</b>
                      <em>{item.value}</em>
                    </span>
                  ))}
                </div>
              </div>
              <div className="github-design-panel backstage-mini" aria-label="设计基准">
                <div className="github-design-title">
                  <strong>设计基准</strong>
                  <span>客户侧隐藏，后台用于约束体验。</span>
                </div>
                <div className="github-design-grid">
                  {designBenchmarks.map((item) => (
                    <article key={item.name}>
                      <small>{item.badge}</small>
                      <strong>{item.name}</strong>
                      <p>{item.idea}</p>
                    </article>
                  ))}
                </div>
              </div>
            </div>
          </details>
        </div>

        <div className={`workflow-console${canDownload ? " delivery-ready" : ""}${hasWorkflowOutput ? " has-output" : " is-briefing"}`}>
          <section id="ppt-brief" className={`run-card chat-card wizard-card${canDownload ? " completed" : ""}`} aria-busy={isRunning} aria-label="PPT 分页生成向导">
            {canDownload ? (
              <div className="completed-brief">
                <span>本次任务</span>
                <h3>{topic}</h3>
                <div>
                  <em>{state.slideDeck?.slides.length ?? 0} 页</em>
                  <em>{languageLabel(outputLanguage)}</em>
                  <em>{agentModes.find((item) => item.value === agentMode)?.label ?? agentMode}</em>
                </div>
                <button className="button secondary run-button" type="button" onClick={resetConversation}>
                  新建另一份 PPT
                </button>
              </div>
            ) : (
              <>
                <header className="wizard-header">
                  <button
                    className="wizard-back"
                    type="button"
                    disabled={conversationStep === 1}
                    onClick={revealPrevious}
                    aria-label="返回上一步"
                  >
                    <span aria-hidden="true">←</span>
                    <em>上一步</em>
                  </button>
                  <div className="wizard-position">
                    <small>创建 PPT</small>
                    <strong>{briefSteps[conversationStep - 1]}</strong>
                  </div>
                  <span className="wizard-count">{conversationStep} / {briefSteps.length}</span>
                </header>
                <div className="wizard-meter" aria-hidden="true">
                  <i style={{ width: `${(conversationStep / briefSteps.length) * 100}%` }} />
                </div>

                <div className="wizard-viewport">
                  {conversationStep === 1 ? (
                    <div className="chat-step wizard-page" key="topic">
                      <div className="wizard-question">
                        <small>01</small>
                        <h2>你想做什么主题？</h2>
                      </div>
                      <textarea
                        aria-label="PPT 主题"
                        value={topic}
                        placeholder="例如：面向本科生的 CRISPR 基因编辑课程汇报"
                        onChange={(event) => setTopic(event.target.value)}
                      />
                      <button className="button primary run-button wizard-next" type="button" disabled={!topic.trim()} onClick={() => revealNext(2)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 2 ? (
                    <div className="chat-step wizard-page" key="source">
                      <div className="wizard-question">
                        <small>02</small>
                        <h2>有参考资料吗？</h2>
                      </div>
                      <textarea
                        aria-label="参考资料"
                        value={sourceText}
                        placeholder="粘贴文字，或直接上传文件"
                        onChange={(event) => setSourceText(event.target.value)}
                      />
                      <label className="file-upload wizard-upload">
                        选择文件
                        <input
                          aria-label="上传参考资料文件"
                          type="file"
                          multiple
                          accept=".txt,.md,.docx,.pptx,.pdf,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                          onChange={(event) => importFiles(event.target.files)}
                        />
                      </label>
                      {uploadedFiles.length > 0 ? (
                        <div className="file-list">
                          {uploadedFiles.map((file) => (
                            <span key={`${file.name}-${file.size}`}>{file.name}</span>
                          ))}
                        </div>
                      ) : null}
                      <button className="button primary run-button wizard-next" type="button" onClick={() => revealNext(3)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 3 ? (
                    <div className="chat-step wizard-page" key="audience">
                      <div className="wizard-question">
                        <small>03</small>
                        <h2>这份 PPT 给谁看？</h2>
                      </div>
                      <input
                        aria-label="PPT 受众"
                        value={audience}
                        placeholder="输入受众，或选择下方选项"
                        onChange={(event) => setAudience(event.target.value)}
                      />
                      <div className="option-grid compact wizard-options">
                        {audiencePresets.map((item) => (
                          <button
                            className={`option-card ${audience === item ? "selected" : ""}`}
                            key={item}
                            type="button"
                            onClick={() => setAudience(item)}
                          >
                            {item}
                          </button>
                        ))}
                      </div>
                      <button className="button primary run-button wizard-next" type="button" disabled={!audience.trim()} onClick={() => revealNext(4)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 4 ? (
                    <div className="chat-step wizard-page" key="language">
                      <div className="wizard-question">
                        <small>04</small>
                        <h2>使用哪种语言？</h2>
                      </div>
                      <div className="option-grid compact wizard-options">
                        {outputLanguages.map((item) => (
                          <button
                            className={`option-card ${outputLanguage === item.value ? "selected" : ""}`}
                            key={item.value}
                            type="button"
                            onClick={() => setOutputLanguage(item.value)}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                      <button className="button primary run-button wizard-next" type="button" onClick={() => revealNext(5)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 5 ? (
                    <div className="chat-step wizard-page" key="scene">
                      <div className="wizard-question">
                        <small>05</small>
                        <h2>这是哪种场景？</h2>
                      </div>
                      <div className="option-grid compact wizard-options">
                        {deckTypes.map((item) => (
                          <button
                            className={`option-card ${deckType === item.value ? "selected" : ""}`}
                            key={item.value}
                            type="button"
                            onClick={() => setDeckType(item.value)}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                      <button className="button primary run-button wizard-next" type="button" onClick={() => revealNext(6)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 6 ? (
                    <div className="chat-step wizard-page" key="mode">
                      <div className="wizard-question">
                        <small>06</small>
                        <h2>选择生成模式</h2>
                      </div>
                      <div className="option-grid compact agent-choice-grid wizard-options">
                        {agentModes.map((item) => (
                          <button
                            className={`option-card agent-choice-card ${agentMode === item.value ? "selected" : ""}`}
                            key={item.value}
                            type="button"
                            onClick={() => setAgentMode(item.value)}
                          >
                            <strong>{item.label}</strong>
                          </button>
                        ))}
                      </div>
                      <button className="button primary run-button wizard-next" type="button" onClick={() => revealNext(7)}>
                        下一步 <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}

                  {conversationStep === 7 ? (
                    <div className="chat-step wizard-page final-step" key="confirm">
                      <div className="wizard-question">
                        <small>07</small>
                        <h2>准备开始</h2>
                      </div>
                      <div className="answer-summary wizard-summary">
                        <span>{languageLabel(outputLanguage)}</span>
                        <span>{deckTypeLabel(deckType)}</span>
                        <span>{agentModes.find((item) => item.value === agentMode)?.label ?? agentMode}</span>
                      </div>
                      <button className="button primary run-button wizard-next" type="button" disabled={isRunning} onClick={() => void createProjectAndOutline()}>
                        {isRunning ? "正在生成…" : "生成大纲"} <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  ) : null}
                  </div>
              </>
            )}
          </section>

          {hasWorkflowOutput ? (
          <section className="result-card" aria-busy={isRunning} aria-live="polite">
            <p className="eyebrow">你的 PPT</p>
            <h2>{progressText}</h2>
            <ol className="stage-rail" aria-label="当前生成进度">
              {generationStages.map((stage) => {
                const rank = stageRank(stage.key);
                const currentRank = stageRank(currentStage);
                const stateClass = rank < currentRank || canDownload ? "done" : rank === currentRank ? "current" : "upcoming";
                return (
                  <li className={stateClass} key={stage.key}>
                    <span>{stage.label}</span>
                  </li>
                );
              })}
            </ol>
            {error ? <pre className="error-box">{error}</pre> : null}
            {isRunning ? (
              <div className="ppt-progress">
                <div className="progress-orb" />
                <p>{latestLog ? `${latestLog.label}：${latestLog.detail}` : "正在开始生成…"}</p>
              </div>
            ) : null}

            {sourceReports.length > 0 ? (
              <details className="source-report-panel backstage-panel">
                <summary>
                  <span>查看资料理解摘要</span>
                  <small>{partialSourceCount ? `${partialSourceCount} 个来源需人工确认` : `${sourceReports.length} 个来源已读取`}</small>
                </summary>
                <div className="source-report-body">
                <div className="source-report-heading">
                  <div>
                    <span>资料理解报告</span>
                    <p>这些内容来自文件解析或公开资料检索形成的 SourcePack；PPT 大纲会围绕这里的主旨、论点和证据生成。</p>
                  </div>
                  <div className={`source-understanding-summary ${partialSourceCount ? "partial" : "complete"}`}>
                    <strong>
                      {partialSourceCount
                        ? `${partialSourceCount} 个来源只被部分读取`
                        : `${sourceReports.length} 个来源已完整读取`}
                    </strong>
                    <small>
                      {partialSourceCount
                        ? "已继续生成，但大纲只基于可读内容；建议确认时对照原文件。"
                        : "当前没有发现截断、损坏部件或无法读取页面。"}
                    </small>
                  </div>
                </div>
                <div className="source-report-grid">
                  {sourceReports.map((report) => {
                    const isPartial = report.understandingStatus === "partial";
                    const warnings = report.warnings ?? [];
                    return (
                      <article className={`source-report-card ${isPartial ? "partial" : "complete"}`} key={report.sourceId}>
                        <div className="source-report-title">
                          <div className="source-report-title-main">
                            <strong>{report.title}</strong>
                            <span className={`source-status-pill ${isPartial ? "partial" : "complete"}`}>
                              {isPartial ? "部分读取" : "完整读取"}
                            </span>
                          </div>
                          <small>
                            {report.extractedChars ? `已分析 ${report.extractedChars} 字符` : report.sourceId}
                            {report.truncated ? " · 已截取参与分析" : ""}
                            {report.url ? (
                              <a href={report.url} target="_blank" rel="noreferrer">
                                查看原始来源 ↗
                              </a>
                            ) : null}
                          </small>
                        </div>
                        {isPartial ? (
                          <div className="source-warning-block" role="status">
                            <strong>这份资料只被部分理解</strong>
                            <p>生成会继续，但下面的主旨、论点和证据只代表已成功读取的内容。</p>
                            {warnings.length ? (
                              <ul>
                                {warnings.slice(0, 4).map((warning) => (
                                  <li key={`${report.sourceId}-${warning.code}-${warning.affectedUnits?.join("-") ?? "all"}`}>
                                    {sourceWarningText(warning)}
                                  </li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ) : null}
                        {report.coverage ? (
                          <div className="source-coverage-grid" aria-label={`${report.title} 读取覆盖率`}>
                            <span>
                              <b>覆盖</b>
                              {formatCoverageProgress(report.coverage)}
                            </span>
                            <span>
                              <b>已分析</b>
                              {report.coverage.analyzedChars} 字符
                            </span>
                            <span>
                              <b>失败</b>
                              {report.coverage.failed}
                            </span>
                            <span>
                              <b>跳过</b>
                              {report.coverage.skipped}
                            </span>
                          </div>
                        ) : null}
                        <div className="source-thesis">
                          <b>{isPartial ? "基于已读取内容的主旨" : "文章主旨"}</b>
                          <p>{report.thesis}</p>
                        </div>
                        {[
                          { label: "关键论点", items: report.keyArguments },
                          { label: "证据/数据", items: report.evidence },
                          { label: "PPT 结构建议", items: report.pptSuggestions },
                          { label: "原文摘录", items: report.excerpts },
                        ].map((section) =>
                          section.items.length > 0 ? (
                            <div className="source-report-section" key={`${report.sourceId}-${section.label}`}>
                              <b>{section.label}</b>
                              <ul>
                                {section.items.map((item) => (
                                  <li key={`${section.label}-${item}`}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null,
                        )}
                      </article>
                    );
                  })}
                </div>
                </div>
              </details>
            ) : null}

            {hasReviewableOutline && activeOutline ? (
              <div className="outline-review">
                <div className="outline-header">
                  <div>
                    <h3>先确认一下这份 PPT 的大纲</h3>
                    <p>不需要看技术数据。你只要确认页标题和核心意思对不对；想改就直接改。</p>
                  </div>
                  {outlineDirty ? <span className="dirty-pill">有未保存编辑</span> : <span className="dirty-pill clean">已同步</span>}
                </div>
                <div className="outline-meta">
                  <span>{activeOutline.targetSlideCount} 页</span>
                  <span>{activeOutline.language === "zh" ? "中文输出" : "英文输出"}</span>
                </div>
                <label className="outline-field">
                  演示目标
                  <textarea
                    value={activeOutline.objective}
                    onChange={(event) => updateOutlineObjective(event.target.value)}
                  />
                </label>
                <ol className="outline-list outline-editor">
                  {activeOutline.slides.map((slide) => (
                    <li key={slide.slideIndex} className="outline-slide-editor">
                      <span className="slide-index">第 {slide.slideIndex} 页</span>
                      <label>
                        页面标题
                        <input
                          value={slide.title}
                          onChange={(event) => updateOutlineSlide(slide.slideIndex, { title: event.target.value })}
                        />
                      </label>
                      <label>
                        核心要点
                        <textarea
                          value={slide.keyPoint}
                          onChange={(event) => updateOutlineSlide(slide.slideIndex, { keyPoint: event.target.value })}
                        />
                      </label>
                      <label>
                        讲稿备注
                        <textarea
                          value={slide.speakerNotesDraft}
                          onChange={(event) =>
                            updateOutlineSlide(slide.slideIndex, { speakerNotesDraft: event.target.value })
                          }
                        />
                      </label>
                    </li>
                  ))}
                </ol>
                <button className="button primary run-button" type="button" disabled={isRunning} onClick={() => void continueAfterOutline()}>
                  大纲可以，继续生成多套视觉方案
                </button>
              </div>
            ) : null}

            {hasVisualChoices && state.visualDecision ? (
              <div className="visual-choice-panel">
                <div className="visual-choice-heading">
                  <span>最后一步</span>
                  <h3>选一个你喜欢的感觉</h3>
                  <p>点击预览，立即生成 PPT 与动态演示。</p>
                </div>
                <div className="visual-direction-grid">
                  {state.visualDecision.directions.map((direction, directionIndex) => {
                    const isActiveDirection = activeVisualDirectionId === direction.directionId;
                    return (
                    <button
                      className={`visual-direction-card${isActiveDirection ? " generating" : ""}`}
                      key={direction.directionId}
                      type="button"
                      disabled={isRunning}
                      aria-busy={isActiveDirection}
                      aria-label={`选择视觉方案：${direction.name}`}
                      onClick={() => void finishWithVisualDirection(direction)}
                    >
                      <div className="visual-direction-preview" style={visualPreviewStyle(direction)} aria-hidden="true">
                        <div className={`preview-slide preview-layout-${directionIndex % 4}`}>
                          <div className="preview-copy">
                            <em>{deckTypeLabel(activeOutline?.deckType ?? deckType)}</em>
                            <b>{(activeOutline?.slides[0]?.title ?? topic.trim()) || direction.name}</b>
                          </div>
                          <div className="preview-art" />
                          <div className="preview-rule" />
                        </div>
                      </div>
                      <div className="direction-summary">
                        <div>
                          <strong>{direction.name}</strong>
                        </div>
                        <div className="direction-palette" aria-label="方案配色">
                          {direction.palette.slice(0, 4).map((color, colorIndex) => (
                            <span
                              key={`${direction.directionId}-${color}-${colorIndex}`}
                              style={{ background: colorOr(color, colorIndex === 0 ? "#0B0F19" : "#F8FAFC") }}
                            />
                          ))}
                        </div>
                      </div>
                      <i>{isActiveDirection ? "正在生成…" : "选择此方案 →"}</i>
                    </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {qualityFailed ? (
              <div className="quality-repair-panel">
                <span>还差一点</span>
                <h3>{state.qualityClosedLoop?.headline ?? "这份 PPT 还没有达到交付标准。"}</h3>
                <p>
                  我已经拦住导出，不会把有越界、乱码、配图缺失或动效问题的文件交给客户。
                  你可以先刷新配图和渲染；如果仍未通过，再回到大纲做内容压缩。
                </p>
                <div className="quality-summary compact">
                  <span>{qualityPassedCount}/{qualityTotalCount} 项质检通过</span>
                  <small>{state.qualityClosedLoop?.recommendedActions.join(" · ") || "等待返修动作"}</small>
                </div>
                <div className="download-actions">
                  <button className="button primary run-button" type="button" disabled={isRunning} onClick={() => void autoRepairQuality()}>
                    自动返修并重新质检
                  </button>
                  <button className="button secondary run-button" type="button" disabled={isRunning} onClick={() => void regenerateImages("generate")}>
                    强制重新生图
                  </button>
                </div>
                {state.qualityClosedLoop?.failedChecks.length ? (
                  <details className="debug-log repair-detail">
                    <summary>查看未通过项</summary>
                    <ol className="run-log">
                      {state.qualityClosedLoop.failedChecks.map((item) => (
                        <li key={item.name}><strong>{item.name}</strong><span>{item.detail}</span></li>
                      ))}
                    </ol>
                  </details>
                ) : null}
              </div>
            ) : null}

            {canDownload ? (
              <div className="download-panel">
                <h3>你的 PPT 已经准备好了</h3>
                <p>我已经生成了可编辑 PPTX 和可在线演示的动态 HTML。建议先预览 HTML；下载 HTML 时会打包页面和配图资源，解压后可离线打开。</p>
                <div className="quality-summary">
                  <span>{state.qualityReport?.passed ? "企业/竞赛质量检查通过" : "等待质量检查"}</span>
                  <small>
                    PPTX 和 HyperFrames HTML 已从同一份 SlideDeck JSON 渲染，
                    共 {state.renderResult?.artifacts[0]?.slideCount ?? pptxExport?.slideCount ?? 0} 页。
                  </small>
                </div>
                <details className="delivery-details backstage-panel">
                  <summary>
                    <span>查看逐页设计与配图细节</span>
                    <small>{qualityTotalCount ? `${qualityPassedCount}/${qualityTotalCount} 项质检` : "专业信息已折叠"}</small>
                  </summary>
                  <div className="delivery-details-body">
                {state.slideDeck ? (
                  <div className="page-plan-summary">
                    <div>
                      <strong>逐页定制设计</strong>
                      <span>{state.slideDeck.theme.designSystemId}</span>
                    </div>
                    <ol>
                      {state.slideDeck.slides.map((slide) => (
                        <li key={slide.slideId}>
                          <span>{String(slide.slideIndex).padStart(2, "0")}</span>
                          <b>{slide.title}</b>
                          <em>{compositionLabels[slide.designPlan.compositionArchetype]}</em>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                {state.slideDeck?.imagePlan ? (
                  <div className="page-plan-summary image-agent-summary">
                    <div>
                      <strong>Image Agent 配图规划</strong>
                      <span>每页先规划，再检索/生成/降级</span>
                    </div>
                    <ol>
                      {state.slideDeck.imagePlan.map((item) => (
                        <li key={`image-plan-${item.slide}`}>
                          <span>{String(item.slide).padStart(2, "0")}</span>
                          <b>{imageTypeLabels[item.imageType]}</b>
                          <em>{item.purpose}</em>
                          <small>{item.searchQuery}</small>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                {state.imageAssets?.length ? (
                  <div className="page-plan-summary image-agent-summary resolved-image-summary">
                    <div>
                      <strong>图片资产结果</strong>
                      <span>真实素材 / AI 生图 / 本地兜底都会在这里标明</span>
                    </div>
                    <ol>
                      {state.imageAssets.map((asset) => (
                        <li key={`resolved-image-${asset.slide}`}>
                          <span>{String(asset.slide).padStart(2, "0")}</span>
                          <b>{asset.sourceType}</b>
                          <em>{asset.attribution ?? asset.mimeType}</em>
                          <small>{asset.query}</small>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                  </div>
                </details>
                <div className="download-actions">
                  {htmlExport?.previewUrl ? (
                    <a className="button primary" href={`${apiOrigin()}${htmlExport.previewUrl}`} target="_blank" rel="noreferrer">
                      在线预览
                    </a>
                  ) : null}
                  {pptxExport ? (
                    <a className="button secondary" href={`${apiOrigin()}${pptxExport.downloadUrl}`}>
                      下载 PPTX
                    </a>
                  ) : null}
                  {htmlExport ? (
                    <a className="button secondary" href={`${apiOrigin()}${htmlExport.downloadUrl}`}>
                      下载 HTML 演示包
                    </a>
                  ) : null}
                  <button className="button secondary run-button" type="button" disabled={isRunning} onClick={() => void regenerateImages("auto")}>
                    重新联网搜图并刷新
                  </button>
                  <button className="button secondary run-button" type="button" disabled={isRunning} onClick={() => void regenerateImages("generate")}>
                    一键生图并刷新
                  </button>
                </div>
              </div>
            ) : !hasReviewableOutline && !hasVisualChoices && !qualityFailed ? (
              <div className="empty-state ppt-placeholder">
                <span>还没有开始</span>
                <p>左边回答完问题后，我会开始为你生成。</p>
              </div>
            ) : null}

            {logs.length > 0 ? (
              <details className="debug-log">
                <summary>查看生成细节</summary>
                <ol className="run-log">
                  {logs.map((item, index) => (
                    <li key={`${item.label}-${index}`}><strong>{item.label}</strong><span>{item.detail}</span></li>
                  ))}
                </ol>
              </details>
            ) : null}
          </section>
          ) : null}
        </div>
      </section>
    </main>
  );
}
