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
  sources: SourceItem[];
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
