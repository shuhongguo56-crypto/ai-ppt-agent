import type { ProjectBrief, SourcePack } from "./index";

const validBrief: ProjectBrief = {
  schemaVersion: "1.0.0",
  projectId: "project-1",
  inputLanguage: "zh",
  outputLanguage: "bilingual",
  deckType: "research_report",
  topic: "A topic",
  audience: "An audience",
  mode: "professional",
};

const sourcePackWithDefaultSources: SourcePack = {
  schemaVersion: "1.0.0",
  projectId: "project-1",
};

// @ts-expect-error outputLanguage must use the declared enum.
const invalidLanguage: ProjectBrief = { ...validBrief, outputLanguage: "fr" };

// @ts-expect-error schemaVersion is required.
const missingVersion: ProjectBrief = {
  projectId: "project-1",
  inputLanguage: "zh",
  outputLanguage: "en",
  deckType: "business_pitch",
  topic: "A topic",
  audience: "An audience",
  mode: "one_click",
};

void sourcePackWithDefaultSources;
void invalidLanguage;
void missingVersion;
