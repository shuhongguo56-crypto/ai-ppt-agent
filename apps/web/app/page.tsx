const workflow = [
  ["01", "Brief", "输入主题 / 上传资料", "Create a project brief with audience, language, and deck type."],
  ["02", "Outline", "HumanizePPT 大纲", "Generate, edit, and confirm an OutlineDecision."],
  ["03", "Style", "三套视觉方向", "Choose Apple, McKinsey, or Airbnb visual language."],
  ["04", "Deck JSON", "统一 SlideDeck", "Assemble one canonical deck used by every renderer."],
  ["05", "Render", "PPTX + HyperFrames", "Export editable PowerPoint and dynamic HTML from the same source."],
];

const plans = [
  ["Free", "$0", "60 credits", "Outline + 3-page watermarked preview"],
  ["Student", "$7.99/mo", "250 credits", "About 2 standard decks"],
  ["Plus", "$14.99/mo", "500 credits", "About 5 standard decks"],
  ["Pro", "$29.99/mo", "1000 credits", "About 10 standard decks"],
];

const outputs = [
  "Editable PPTX with structured text boxes",
  "HyperFrames-style HTML presentation",
  "Shared SlideDeck JSON contract",
  "Checkpointed workflow for safe resume",
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <nav className="nav" aria-label="Main navigation">
          <div className="brand">
            <span className="brand-mark">A</span>
            <span>AI PPT Agent</span>
          </div>
          <div className="nav-links">
            <a href="#workflow">Workflow</a>
            <a href="#pricing">Pricing</a>
            <a href="#status">Status</a>
          </div>
        </nav>

        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">International bilingual AI presentation SaaS</p>
            <h1>Turn raw ideas into premium PPTX and dynamic HTML decks.</h1>
            <p className="lead">
              面向学生、老师、留学生、论文答辩和商业汇报用户。系统先生成专业大纲，再提供三套高级视觉方向，
              最终从同一份 SlideDeck JSON 同时导出可编辑 PPTX 与 HyperFrames HTML。
            </p>
            <div className="actions">
              <a className="button primary" href="/workflow">Run workflow</a>
              <a className="button secondary" href="#status">Local build status</a>
            </div>
          </div>

          <div className="preview-card" aria-label="Product preview">
            <div className="preview-top">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div className="preview-slide">
              <p className="eyebrow">SlideDeck JSON</p>
              <h2>One source. Two exports.</h2>
              <div className="mini-grid">
                <div>PPTX</div>
                <div>HyperFrames</div>
                <div>Outline</div>
                <div>Visual Direction</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="workflow">
        <div className="section-heading">
          <p className="eyebrow">Workflow / 工作流</p>
          <h2>Built around checkpoints, not magic jumps.</h2>
        </div>
        <div className="workflow">
          {workflow.map(([step, title, zh, description]) => (
            <article className="workflow-card" key={step}>
              <span>{step}</span>
              <h3>{title}</h3>
              <p className="zh">{zh}</p>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section split">
        <div>
          <p className="eyebrow">Exports / 输出</p>
          <h2>PPTX and HTML stay consistent because they share one deck contract.</h2>
        </div>
        <ul className="output-list">
          {outputs.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="section" id="pricing">
        <div className="section-heading">
          <p className="eyebrow">Credits / 会员积分</p>
          <h2>Simple SaaS packaging for the international version.</h2>
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
        <p className="eyebrow">Local foundation status</p>
        <h2>后端主链路已跑通到 render。</h2>
        <p>
          Current branch includes project creation, outline generation/confirmation, visual direction selection,
          canonical SlideDeck assembly, and local PPTX + HyperFrames HTML artifact rendering.
        </p>
        <div className="status-pill">249 backend tests passing · TypeScript contracts passing</div>
      </section>
    </main>
  );
}
