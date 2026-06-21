"use client";

import { useMemo, useState } from "react";
import type {
  DeckType,
  OutputLanguage,
  ProjectBrief,
  QualityReport,
  RenderResult,
  VisualDirectionId,
} from "../../../../packages/contracts/typescript";

type ApiExport = {
  target: "pptx" | "hyperframes_html";
  contentType: string;
  slideCount: number;
  downloadUrl: string;
};

type WorkflowState = {
  projectId?: string;
  outlineVersion?: number;
  visualVersion?: number;
  slideDeckVersion?: number;
  renderVersion?: number;
  qualityVersion?: number;
  renderResult?: RenderResult;
  exports: ApiExport[];
};

type LogItem = {
  label: string;
  detail: string;
};

const deckTypes: DeckType[] = [
  "course_presentation",
  "thesis_defense",
  "research_report",
  "business_pitch",
  "case_competition",
];

const outputLanguages: OutputLanguage[] = ["en", "zh", "bilingual"];

const directions: VisualDirectionId[] = ["apple", "mckinsey", "airbnb"];

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api").replace(/\/$/, "");

function apiOrigin() {
  return apiBase.replace(/\/api$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export default function WorkflowClient() {
  const [topic, setTopic] = useState("CRISPR for undergraduate biology students");
  const [audience, setAudience] = useState("Undergraduates");
  const [deckType, setDeckType] = useState<DeckType>("course_presentation");
  const [outputLanguage, setOutputLanguage] = useState<OutputLanguage>("en");
  const [direction, setDirection] = useState<VisualDirectionId>("apple");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [state, setState] = useState<WorkflowState>({ exports: [] });

  const canDownload = state.exports.length > 0;
  const runLabel = useMemo(
    () => (isRunning ? "Generating full workflow..." : "Run full local workflow"),
    [isRunning],
  );

  function push(label: string, detail: string) {
    setLogs((current) => [...current, { label, detail }]);
  }

  async function runWorkflow() {
    setIsRunning(true);
    setError(null);
    setLogs([]);
    setState({ exports: [] });
    try {
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
      };

      await request<{ projectId: string }>("/projects", {
        method: "POST",
        body: JSON.stringify(brief),
      });
      push("Project", `Created ${projectId}`);

      const outline = await request<{
        version: number;
        status: "draft" | "confirmed";
        outlineDecision: unknown;
      }>(`/projects/${projectId}/outline/generate`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      push("Outline", `Generated OutlineDecision v${outline.version}`);

      const confirmedOutline =
        outline.status === "confirmed"
          ? outline
          : await request<{ version: number }>(`/projects/${projectId}/outline/confirm`, {
              method: "POST",
              body: JSON.stringify({ outlineDecisionVersion: outline.version }),
            });
      push("Outline", `Confirmed outline v${confirmedOutline.version}`);

      const visual = await request<{ version: number; visualDirection: unknown }>(
        `/projects/${projectId}/visual-directions/generate`,
        {
          method: "POST",
          body: JSON.stringify({ outlineDecisionVersion: confirmedOutline.version }),
        },
      );
      push("Visual", "Generated Apple, McKinsey, and Airbnb directions");

      const selected = await request<{ version: number }>(
        `/projects/${projectId}/visual-directions/select`,
        {
          method: "POST",
          body: JSON.stringify({ visualDirectionVersion: visual.version, directionId: direction }),
        },
      );
      push("Visual", `Selected ${direction} direction v${selected.version}`);

      const deck = await request<{ version: number; slideDeck: { slides: unknown[] } }>(
        `/projects/${projectId}/slide-deck/assemble`,
        {
          method: "POST",
          body: JSON.stringify({ visualDirectionVersion: selected.version }),
        },
      );
      push("SlideDeck", `Assembled ${deck.slideDeck.slides.length} slides from one JSON contract`);

      const rendered = await request<{ version: number; renderResult: RenderResult }>(
        `/projects/${projectId}/render`,
        {
          method: "POST",
          body: JSON.stringify({ slideDeckVersion: deck.version }),
        },
      );
      push("Render", "Rendered editable PPTX and HyperFrames HTML");

      const quality = await request<{ version: number; qualityReport: QualityReport }>(
        `/projects/${projectId}/quality/check`,
        {
          method: "POST",
          body: JSON.stringify({ renderVersion: rendered.version }),
        },
      );
      push("Quality", `Quality check ${quality.qualityReport.passed ? "passed" : "failed"} v${quality.version}`);

      const exports = await request<{ exports: ApiExport[] }>(`/projects/${projectId}/exports`);
      push("Export", "Download links are ready");

      setState({
        projectId,
        outlineVersion: confirmedOutline.version,
        visualVersion: selected.version,
        slideDeckVersion: deck.version,
        renderVersion: rendered.version,
        qualityVersion: quality.version,
        renderResult: rendered.renderResult,
        exports: exports.exports,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown workflow error");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="workflow-page">
      <section className="workflow-shell">
        <div className="workflow-intro">
          <a className="back-link" href="/">← Back to landing</a>
          <p className="eyebrow">Live local workflow / 本地完整流程</p>
          <h1>Generate a deck all the way to downloads.</h1>
          <p className="lead">
            This page calls the local FastAPI backend and runs the entire checkpointed flow in one click:
            brief, outline, visual direction, SlideDeck JSON, render, and export.
          </p>
        </div>

        <div className="workflow-console">
          <form
            className="run-card"
            onSubmit={(event) => {
              event.preventDefault();
              void runWorkflow();
            }}
          >
            <label>
              Topic
              <textarea value={topic} onChange={(event) => setTopic(event.target.value)} />
            </label>
            <label>
              Audience
              <input value={audience} onChange={(event) => setAudience(event.target.value)} />
            </label>
            <div className="form-grid">
              <label>
                Deck type
                <select value={deckType} onChange={(event) => setDeckType(event.target.value as DeckType)}>
                  {deckTypes.map((item) => (
                    <option value={item} key={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Output language
                <select
                  value={outputLanguage}
                  onChange={(event) => setOutputLanguage(event.target.value as OutputLanguage)}
                >
                  {outputLanguages.map((item) => (
                    <option value={item} key={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Visual direction
                <select value={direction} onChange={(event) => setDirection(event.target.value as VisualDirectionId)}>
                  {directions.map((item) => (
                    <option value={item} key={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button className="button primary run-button" disabled={isRunning || !topic.trim() || !audience.trim()}>
              {runLabel}
            </button>
            <p className="hint">Backend default: {apiBase}</p>
          </form>

          <section className="result-card" aria-live="polite">
            <h2>Run status</h2>
            {error ? <pre className="error-box">{error}</pre> : null}
            <ol className="run-log">
              {logs.map((item, index) => (
                <li key={`${item.label}-${index}`}>
                  <strong>{item.label}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ol>
            {canDownload ? (
              <div className="download-panel">
                <h3>Exports ready</h3>
                <p>
                  Project {state.projectId} · outline v{state.outlineVersion} · visual v{state.visualVersion} 路
                  deck v{state.slideDeckVersion} · render v{state.renderVersion} · quality v{state.qualityVersion}
                </p>
                <div className="download-actions">
                  {state.exports.map((item) => (
                    <a className="button secondary" href={`${apiOrigin()}${item.downloadUrl}`} key={item.target}>
                      Download {item.target === "pptx" ? "PPTX" : "HTML"}
                    </a>
                  ))}
                </div>
              </div>
            ) : (
              <p className="empty-state">Run the workflow to create local exports.</p>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}

