const workflow = [
  ["01", "项目输入", "输入主题、粘贴资料或导入 .txt / .md / .docx / .pptx / .pdf，形成 ProjectBrief 与 SourcePack。"],
  ["02", "大纲决策", "HumanizePPT 先生成结构化 OutlineDecision，专业模式下可以编辑后再确认。"],
  ["03", "视觉方向推荐", "Frontend-Slides 根据内容复杂度动态生成多套高级视觉方向，并从风格策略库中择优组合。"],
  ["04", "统一母版", "系统把大纲和模板合成为同一份 canonical SlideDeck JSON。"],
  ["05", "双格式导出", "PPTX 与 HyperFrames HTML 都从同一份 SlideDeck JSON 渲染，保证内容一致。"],
];

const plans = [
  ["免费版", "$0", "一次性 60 积分", "开放大纲与 3 页带水印预览"],
  ["学生版", "$7.99/月", "250 积分", "约 2 套标准 PPT"],
  ["Plus", "$14.99/月", "500 积分", "约 5 套标准 PPT"],
  ["Pro", "$29.99/月", "1000 积分", "约 10 套标准 PPT"],
];

const templates = [
  "Apple 发布会高级留白",
  "McKinsey 咨询逻辑",
  "Airbnb 温暖故事感",
  "学术极简白底",
  "蓝色论文答辩",
  "Research Journal 期刊感",
  "Startup Pitch 明亮路演",
  "Investor Dark 高级深色",
  "课堂友好清爽",
  "Data Story 数据叙事",
  "Editorial Magazine 杂志叙事",
  "Glassmorphism 玻璃拟态",
];

const outputs = [
  "可编辑 PPTX：结构化文本框、标题、卡片和备注",
  "HyperFrames 动态 HTML：支持键盘翻页、进度条、缩略导航和讲稿开关",
  "统一 SlideDeck JSON：PPTX / HTML 共用同一份内容源",
  "检查点工作流：大纲、视觉、渲染、质量检查都可追踪",
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <nav className="nav" aria-label="主导航">
          <div className="brand">
            <span className="brand-mark">A</span>
            <span>AI PPT Agent</span>
          </div>
          <div className="nav-links">
            <a href="#workflow">生成流程</a>
            <a href="#templates">视觉方向</a>
            <a href="/projects">项目库</a>
            <a href="#pricing">会员积分</a>
            <a href="#status">本地状态</a>
          </div>
        </nav>

        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">国际版 AI PPT SaaS / 中文网站界面</p>
            <h1>把资料变成高质量 PPTX 和动态 HTML 演示。</h1>
            <p className="lead">
              面向大学生、研究生、教师、留学生、课程汇报、论文答辩和商业展示用户。
              系统不会直接“糊一份 PPT”，而是先生成专业大纲，再选择高级视觉方向，
              最后从同一份 SlideDeck JSON 同时导出可编辑 PPTX 和 HyperFrames HTML。
            </p>
            <div className="actions">
              <a className="button primary" href="/workflow">开始生成网站演示</a>
              <a className="button secondary" href="#templates">查看视觉方向库</a>
              <a className="button secondary" href="/projects">打开项目库</a>
            </div>
          </div>

          <div className="preview-card" aria-label="产品预览">
            <div className="preview-top">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div className="preview-slide">
              <p className="eyebrow">SlideDeck JSON</p>
              <h2>一份内容源，两种导出。</h2>
              <div className="mini-grid">
                <div>可编辑 PPTX</div>
                <div>动态 HTML</div>
                <div>大纲决策</div>
                <div>视觉方向</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="workflow">
        <div className="section-heading">
          <p className="eyebrow">核心流程</p>
          <h2>不是魔法跳转，而是可审查的 AI PPT 工作流。</h2>
        </div>
        <div className="workflow">
          {workflow.map(([step, title, description]) => (
            <article className="workflow-card" key={step}>
              <span>{step}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section" id="templates">
        <div className="section-heading">
          <p className="eyebrow">视觉方向库</p>
          <h2>首版内置 12 种视觉策略，覆盖课程、答辩、研究和商业场景。</h2>
        </div>
        <div className="template-grid">
          {templates.map((template, index) => (
            <article className="template-card" key={template}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{template}</h3>
            </article>
          ))}
        </div>
      </section>

      <section className="section split">
        <div>
          <p className="eyebrow">统一导出</p>
          <h2>PPTX 和 HTML 必须来自同一份 SlideDeck JSON。</h2>
        </div>
        <ul className="output-list">
          {outputs.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="section" id="pricing">
        <div className="section-heading">
          <p className="eyebrow">订阅与积分</p>
          <h2>先做国际版 SaaS，会员 + 积分制。</h2>
        </div>
        <div className="pricing">
          {plans.map(([name, price, credits, note]) => (
            <article className="price-card" key={name}>
              <h3>{name}</h3>
              <strong>{price}</strong>
              <p>{credits}</p>
              <span>{note}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="section status" id="status">
        <p className="eyebrow">本地开发状态</p>
        <h2>核心纵向切片已经跑通到导出层。</h2>
        <p>
          当前本地版本包含项目创建、大纲生成与确认、12 种视觉方向、SlideDeck JSON 组装、
          PPTX / HyperFrames HTML 渲染、质量检查与下载接口。
          默认是离线 Fake 模式；接入 OpenAI API 前也可切换 Ollama 免费本地 AI 模式。
        </p>
        <div className="status-pill">FastAPI 后端 · Next.js 前端 · SQLite 本地持久化</div>
      </section>
    </main>
  );
}
