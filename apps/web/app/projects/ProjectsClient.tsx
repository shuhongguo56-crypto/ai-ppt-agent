"use client";

import { useEffect, useMemo, useState } from "react";
import type { ProjectBrief, WorkflowCheckpoint } from "../../../../packages/contracts/typescript";

type ProjectListItem = {
  projectId: string;
  brief: ProjectBrief;
  createdAt: string;
  latestCheckpoint: WorkflowCheckpoint | null;
};

type ProjectListResponse = {
  projects: ProjectListItem[];
};

type ProjectFilter = "all" | "ready" | "active";
type ProjectStage = "brief" | "outline" | "visual_direction" | "slide_deck" | "render" | "quality";

const defaultApiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api").replace(/\/$/, "");

function normalizeApiBase(value: string) {
  const trimmed = value.trim().replace(/\/$/, "");
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

function apiBase() {
  if (typeof window === "undefined") return defaultApiBase;
  const queryApi = new URLSearchParams(window.location.search).get("api");
  if (queryApi?.trim()) {
    const normalized = normalizeApiBase(queryApi);
    window.localStorage.setItem("ai-ppt-api-base", normalized);
    return normalized;
  }
  return window.localStorage.getItem("ai-ppt-api-base") ?? defaultApiBase;
}

const projectStages: Array<{ key: ProjectStage; label: string }> = [
  { key: "brief", label: "输入" },
  { key: "outline", label: "大纲" },
  { key: "visual_direction", label: "视觉" },
  { key: "slide_deck", label: "成稿" },
  { key: "render", label: "渲染" },
  { key: "quality", label: "交付" },
];

function apiOrigin() {
  return apiBase().replace(/\/api$/, "");
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }
  return (await response.json()) as T;
}

function stageLabel(stage?: string) {
  switch (stage) {
    case "outline":
      return "大纲审阅";
    case "visual_direction":
      return "视觉方向";
    case "slide_deck":
      return "统一成稿";
    case "render":
      return "渲染完成";
    case "quality":
      return "可交付";
    case "export":
      return "已导出";
    case "brief":
      return "项目输入";
    default:
      return "未开始";
  }
}

function statusLabel(status?: string) {
  switch (status) {
    case "complete":
      return "已完成";
    case "confirmed":
      return "已确认";
    case "draft":
      return "草稿";
    case "failed":
      return "失败";
    case "pending":
      return "处理中";
    default:
      return "待开始";
  }
}

function deckTypeLabel(value: string) {
  return {
    course_presentation: "课程汇报",
    thesis_defense: "论文答辩",
    research_report: "研究报告",
    business_pitch: "商业路演",
    case_competition: "案例竞赛",
  }[value] ?? value;
}

function stageRank(stage?: string) {
  const index = projectStages.findIndex((item) => item.key === stage);
  return index >= 0 ? index : -1;
}

function looksUnreadable(value?: string | null) {
  const text = value?.trim() ?? "";
  if (!text) return true;
  const questionMarks = (text.match(/\?/g) ?? []).length;
  const questionRatio = questionMarks / Math.max(text.length, 1);
  return questionRatio > 0.35 || /[æçèåäãÂÃ�]|闁|閳|绗|绛|涓|鍑|鐢/.test(text);
}

function safeText(value: string | undefined | null, fallback: string) {
  return looksUnreadable(value) ? fallback : value?.trim() || fallback;
}

function projectTitle(project: ProjectListItem) {
  return safeText(project.brief.topic, "未命名 PPT 项目");
}

function projectAudience(project: ProjectListItem) {
  return safeText(project.brief.audience, "未填写受众");
}

function isReady(project: ProjectListItem) {
  return project.latestCheckpoint?.stage === "quality" && project.latestCheckpoint.status === "complete";
}

function projectMatches(project: ProjectListItem, query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [project.projectId, projectTitle(project), projectAudience(project), deckTypeLabel(project.brief.deckType)]
    .filter(Boolean)
    .some((value) => value.toLowerCase().includes(normalized));
}

export default function ProjectsClient() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ProjectFilter>("all");
  const [query, setQuery] = useState("");

  const readyCount = useMemo(() => projects.filter(isReady).length, [projects]);
  const activeCount = projects.length - readyCount;
  const latestProject = projects[0];
  const filteredProjects = useMemo(
    () =>
      projects.filter((project) => {
        if (!projectMatches(project, query)) return false;
        if (filter === "ready") return isReady(project);
        if (filter === "active") return !isReady(project);
        return true;
      }),
    [filter, projects, query],
  );

  async function loadProjects() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await request<ProjectListResponse>("/projects");
      setProjects(response.projects);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "项目加载失败");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  return (
    <main className="workflow-page">
      <section className="workflow-shell">
        <div className="workflow-intro project-library-hero">
          <a className="back-link" href="/">← 返回首页</a>
          <p className="eyebrow">我的 PPT 项目库</p>
          <h1>管理你已经生成过的 AI PPT。</h1>
          <p className="lead">
            这里保存本地生成历史。完成质量检查的项目可以直接预览 HyperFrames HTML，或下载可编辑 PPTX 和可离线打开的 HTML 演示包。
          </p>
          <div className="actions">
            <a className="button primary" href="/workflow">新建 PPT</a>
            <button className="button secondary run-button" type="button" disabled={isLoading} onClick={() => void loadProjects()}>
              {isLoading ? "正在刷新…" : "刷新项目库"}
            </button>
          </div>
        </div>

        <section className="project-summary" aria-label="项目库概览">
          <div>
            <strong>{projects.length}</strong>
            <span>全部项目</span>
          </div>
          <div>
            <strong>{readyCount}</strong>
            <span>可下载</span>
          </div>
          <div>
            <strong>{activeCount}</strong>
            <span>未完成 / 草稿</span>
          </div>
          <div className="wide">
            <strong>{latestProject ? new Date(latestProject.createdAt).toLocaleString("zh-CN") : "暂无"}</strong>
            <span>最近一次生成</span>
          </div>
        </section>

        <section className="project-toolbar" aria-label="项目筛选">
          <label>
            搜索项目
            <input
              value={query}
              placeholder="按主题、受众、项目 ID 搜索"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="project-filter" role="group" aria-label="项目状态筛选">
            {[
              ["all", "全部"],
              ["ready", "可下载"],
              ["active", "未完成"],
            ].map(([value, label]) => (
              <button
                className={filter === value ? "selected" : ""}
                key={value}
                type="button"
                onClick={() => setFilter(value as ProjectFilter)}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {error ? <pre className="error-box">{error}</pre> : null}
        {isLoading ? <p className="empty-state">正在加载项目库…</p> : null}

        <div className="project-grid">
          {filteredProjects.map((project) => {
            const latest = project.latestCheckpoint;
            const currentRank = stageRank(latest?.stage);
            const canDownload = isReady(project);
            return (
              <article className={`project-card ${canDownload ? "ready" : ""}`} key={project.projectId}>
                <div className="project-card-top">
                  <span>{stageLabel(latest?.stage)}</span>
                  <span>{statusLabel(latest?.status)}</span>
                </div>
                <h2>{projectTitle(project)}</h2>
                <p>{projectAudience(project)}</p>
                <ol className="project-stage-mini" aria-label="项目进度">
                  {projectStages.map((stage, index) => (
                    <li className={index <= currentRank || canDownload ? "done" : ""} key={stage.key}>
                      {stage.label}
                    </li>
                  ))}
                </ol>
                <div className="outline-meta">
                  <span>{deckTypeLabel(project.brief.deckType)}</span>
                  <span>{project.brief.outputLanguage === "zh" ? "中文" : project.brief.outputLanguage === "en" ? "English" : "双语"}</span>
                  <span>{new Date(project.createdAt).toLocaleString("zh-CN")}</span>
                </div>
                <p className="hint">项目 ID：{project.projectId}</p>
                <div className="project-actions">
                  {canDownload ? (
                    <>
                      <a className="button primary" href={`${apiOrigin()}/api/projects/${project.projectId}/exports/hyperframes_html?inline=true`} target="_blank" rel="noreferrer">
                        预览 HTML
                      </a>
                      <a className="button secondary" href={`${apiOrigin()}/api/projects/${project.projectId}/exports/pptx`}>
                        下载 PPTX
                      </a>
                      <a className="button secondary" href={`${apiOrigin()}/api/projects/${project.projectId}/exports/hyperframes_html`}>
                        下载 HTML 演示包
                      </a>
                    </>
                  ) : (
                    <span className="project-note">项目还没通过质量检查，完成生成后会开放下载。</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>

        {!isLoading && projects.length === 0 ? (
          <div className="empty-state ppt-placeholder">
            <span>还没有 PPT 项目</span>
            <p>先去工作台生成一份，完成后它会出现在这里。</p>
            <a className="button primary" href="/workflow">开始生成</a>
          </div>
        ) : null}

        {!isLoading && projects.length > 0 && filteredProjects.length === 0 ? (
          <div className="empty-state ppt-placeholder">
            <span>没有匹配的项目</span>
            <p>换个关键词，或切回“全部”。</p>
          </div>
        ) : null}
      </section>
    </main>
  );
}
