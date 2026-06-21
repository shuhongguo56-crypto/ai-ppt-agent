export type SchemaVersion = "1.0.0";
export type InputLanguage = "zh" | "en";
export type OutputLanguage = InputLanguage | "bilingual";
export type DeckType =
  | "course_presentation"
  | "thesis_defense"
  | "research_report"
  | "business_pitch"
  | "case_competition";
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

export interface ProjectBrief {
  schemaVersion: SchemaVersion;
  projectId: string;
  inputLanguage: InputLanguage;
  outputLanguage: OutputLanguage;
  deckType: DeckType;
  topic: string;
  audience: string;
  mode: "professional" | "one_click";
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
