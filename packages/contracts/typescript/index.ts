export type SchemaVersion = "1.0.0";
export type PlanId = "free" | "student" | "plus" | "pro";
export type InputLanguage = "zh" | "en";
export type OutputLanguage = InputLanguage | "bilingual";
export type DeckType =
  | "course_presentation"
  | "thesis_defense"
  | "research_report"
  | "business_pitch"
  | "case_competition";
export type AgentMode = "fast" | "research" | "enterprise";
export type SourceType = "text" | "document" | "url" | "image";
export type WorkflowStage =
  | "brief"
  | "outline"
  | "visual_direction"
  | "slide_deck"
  | "render"
  | "quality"
  | "export";
export type WorkflowStatus = "pending" | "draft" | "confirmed" | "failed" | "complete";
export type DeckLanguage = InputLanguage | "bilingual";
export type SlidePurpose =
  | "cover"
  | "agenda"
  | "context"
  | "insight"
  | "evidence"
  | "framework"
  | "recommendation"
  | "conclusion";
export type SuggestedLayout =
  | "hero"
  | "section"
  | "two_column"
  | "three_cards"
  | "timeline"
  | "chart_focus"
  | "quote"
  | "closing";
export type VisualDirectionId =
  | "apple"
  | "mckinsey"
  | "airbnb"
  | "academic_clean"
  | "thesis_blue"
  | "research_journal"
  | "startup_pitch"
  | "investor_dark"
  | "classroom_friendly"
  | "data_story"
  | "editorial_magazine"
  | "glassmorphism"
  | "medical_science"
  | "cinematic_research"
  | "policy_brief"
  | "ink_classical"
  | "product_showcase"
  | "architectural_premium"
  | "finance_terminal"
  | "workshop_playbook";
export type SlideBlockType =
  | "headline"
  | "subtitle"
  | "body"
  | "card"
  | "chart_placeholder"
  | "image_placeholder"
  | "speaker_notes";
export type CompositionArchetype =
  | "cinematic_hero"
  | "editorial_cover"
  | "architectural_cover"
  | "chapter_index"
  | "editorial_split"
  | "diagonal_story"
  | "statement_focus"
  | "proof_mosaic"
  | "data_landscape"
  | "process_ribbon"
  | "system_map"
  | "split_comparison"
  | "priority_stack"
  | "closing_echo"
  | "manifesto_close"
  | "future_horizon";
export type ImageTreatment =
  | "full_bleed"
  | "split_crop"
  | "masked_window"
  | "layered_cutout"
  | "evidence_strip"
  | "atmospheric_backdrop";
export type AssetRole = "hero" | "context" | "evidence" | "diagram" | "metaphor" | "portrait";
export type ContentDensity = "sparse" | "balanced" | "dense";
export type ImageAssetType =
  | "background"
  | "course_review_atmosphere"
  | "business_scene"
  | "classical_element"
  | "thesis_concept"
  | "product_showcase"
  | "icon_illustration"
  | "data_visual";
export type ImageProviderAdapter =
  | "open_web_search"
  | "OpenAI Image API"
  | "Pollinations FLUX API"
  | "Midjourney API"
  | "Stable Diffusion API"
  | "custom image2 API"
  | "local_png_fallback";
export type MotionPreset =
  | "cinematic_reveal"
  | "editorial_wipe"
  | "depth_parallax"
  | "evidence_reveal"
  | "sequence_build"
  | "diagram_orbit"
  | "closing_resolve";
export type ExplanationMode =
  | "hero_photo"
  | "concept_diagram"
  | "process_diagram"
  | "data_evidence"
  | "comparison_visual"
  | "annotated_image"
  | "summary_map";
export type RenderTarget = "pptx" | "hyperframes_html";
export type QualityStatus = "passed" | "failed";

export interface ProjectBrief {
  schemaVersion: SchemaVersion;
  projectId: string;
  inputLanguage: InputLanguage;
  outputLanguage: OutputLanguage;
  deckType: DeckType;
  topic: string;
  audience: string;
  mode: "professional" | "one_click";
  agentMode: AgentMode;
}

export interface SourceItem {
  schemaVersion: SchemaVersion;
  sourceId: string;
  sourceType: SourceType;
  summary: string;
  title?: string | null;
  url?: string | null;
}

export interface SourcePack {
  schemaVersion: SchemaVersion;
  projectId: string;
  sources?: SourceItem[];
}

export interface WorkflowCheckpoint {
  schemaVersion: SchemaVersion;
  projectId: string;
  stage: WorkflowStage;
  status: WorkflowStatus;
  version: number;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface OutlineGeneratedBy {
  schemaVersion: SchemaVersion;
  skillName: "HumanizePPT";
  skillVersion: string;
  model: string;
  promptHash: string;
  generationId: string;
  generatedAt: string;
}

export interface OutlineSlide {
  schemaVersion: SchemaVersion;
  slideIndex: number;
  title: string;
  subtitle?: string | null;
  purpose: SlidePurpose;
  keyPoint: string;
  talkingPoints: string[];
  suggestedLayout: SuggestedLayout;
  visualIntent: string;
  requiredAssets?: string[];
  citationIds?: string[];
  speakerNotesDraft: string;
  constraints?: string[];
}

export interface OutlineDecision {
  schemaVersion: SchemaVersion;
  projectId: string;
  language: DeckLanguage;
  deckType: DeckType;
  audience: string;
  objective: string;
  targetSlideCount: number;
  narrative: string[];
  slides: OutlineSlide[];
  assetNeeds?: string[];
  citationNeeds?: string[];
  risks?: string[];
  qualityScores?: Record<string, number>;
  generatedBy: OutlineGeneratedBy;
}

export interface VisualGeneratedBy {
  schemaVersion: SchemaVersion;
  skillName: "Frontend-Slides";
  skillVersion: string;
  model: string;
  promptHash: string;
  generationId: string;
  generatedAt: string;
}

export interface VisualDirection {
  schemaVersion: SchemaVersion;
  directionId: VisualDirectionId;
  name: string;
  mood: string;
  palette: string[];
  typography: string;
  layoutPrinciples: string[];
  textureLayer: string;
  sampleSlideIntents: string[];
  motionPlan: string[];
  layeringPlan: string[];
  imageStrategy: string[];
  hyperframesPlan: string[];
  riskNotes?: string[];
}

export interface VisualDirectionDecision {
  schemaVersion: SchemaVersion;
  projectId: string;
  outlineVersion: number;
  directions: VisualDirection[];
  selectedDirectionId?: VisualDirectionId | null;
  generatedBy: VisualGeneratedBy;
}

export interface SlideDeckTheme {
  schemaVersion: SchemaVersion;
  directionId: VisualDirectionId;
  name: string;
  palette: string[];
  typography: string;
  textureLayer: string;
  layoutPrinciples: string[];
  designSystemId: string;
  designSeed: number;
}

export interface SlideBlock {
  schemaVersion: SchemaVersion;
  blockId: string;
  blockType: SlideBlockType;
  content: string;
  role: string;
}

export interface SlideDesignPlan {
  schemaVersion: SchemaVersion;
  compositionArchetype: CompositionArchetype;
  compositionVariant: string;
  imageTreatment: ImageTreatment;
  assetRole: AssetRole;
  assetQuery: string;
  contentDensity: ContentDensity;
  hierarchy: string[];
  visualLayers: string[];
  explanationMode: ExplanationMode;
  visualBrief: string;
  diagramLabels: string[];
  motionPreset: MotionPreset;
  rationale: string;
}

export interface ImagePlanItem {
  schemaVersion: SchemaVersion;
  slide: number;
  needsImage: boolean;
  imageType: ImageAssetType;
  prompt: string;
  purpose: string;
  searchQuery: string;
  providerChain: ImageProviderAdapter[];
}

export interface SlideDeckSlide {
  schemaVersion: SchemaVersion;
  slideId: string;
  slideIndex: number;
  title: string;
  subtitle?: string | null;
  purpose: SlidePurpose;
  layout: string;
  visualIntent: string;
  designPlan: SlideDesignPlan;
  blocks: SlideBlock[];
  speakerNotes: string;
}

export interface SlideDeck {
  schemaVersion: SchemaVersion;
  projectId: string;
  outlineVersion: number;
  visualDirectionVersion: number;
  language: DeckLanguage;
  title: string;
  theme: SlideDeckTheme;
  slides: SlideDeckSlide[];
  imagePlan: ImagePlanItem[];
  exportTargets: ["pptx", "hyperframes_html"];
}

export interface RenderArtifact {
  schemaVersion: SchemaVersion;
  target: RenderTarget;
  path: string;
  contentType: string;
  slideCount: number;
}

export interface RenderResult {
  schemaVersion: SchemaVersion;
  projectId: string;
  slideDeckVersion: number;
  artifacts: RenderArtifact[];
}

export interface QualityCheckItem {
  schemaVersion: SchemaVersion;
  name: string;
  status: QualityStatus;
  detail: string;
}

export interface QualityReport {
  schemaVersion: SchemaVersion;
  projectId: string;
  renderVersion: number;
  passed: boolean;
  checks: QualityCheckItem[];
}

export interface CreditPlan {
  schemaVersion: SchemaVersion;
  planId: PlanId;
  name: string;
  monthlyPriceUsd: number;
  credits: number;
  description: string;
}

export interface CreditQuoteItem {
  schemaVersion: SchemaVersion;
  code: string;
  label: string;
  credits: number;
}

export interface CreditQuote {
  schemaVersion: SchemaVersion;
  projectId: string;
  estimatedSlideCount: number;
  totalCredits: number;
  items: CreditQuoteItem[];
}
