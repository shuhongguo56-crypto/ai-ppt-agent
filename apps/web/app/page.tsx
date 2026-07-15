export const dynamic = "force-static";

const steps = [
  ["01", "读懂资料", "解析主题、文章与上传文件，补齐可靠资料。"],
  ["02", "形成观点", "先完成有逻辑、可追溯的演示大纲。"],
  ["03", "完成交付", "从同一份内容生成 PPTX 与动态演示。"],
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <nav className="nav" aria-label="主导航">
          <a className="brand" href="/" aria-label="HumanizePPT 首页">
            <span className="brand-mark">H</span>
            <span>HumanizePPT</span>
          </a>
          <div className="nav-links">
            <a href="/projects">我的项目</a>
            <a className="button primary" href="/workflow">
              开始创作
            </a>
          </div>
        </nav>

        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">AI PRESENTATION STUDIO</p>
            <h1>把你的资料，变成一场有观点的演示。</h1>
            <p className="lead">
              从文件解析、研究型大纲到定制视觉，一步步完成可编辑 PPTX
              与动态演示。
            </p>
            <div className="actions">
              <a className="button primary" href="/workflow">
                立即生成 PPT
              </a>
              <a className="button secondary" href="/projects">
                查看项目
              </a>
            </div>
          </div>

          <div className="preview-card" aria-label="产品流程预览">
            <div className="preview-top" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div className="preview-slide">
              <p className="eyebrow">FROM SOURCE TO STORY</p>
              <h2>先想清楚，再设计。</h2>
              <div className="mini-grid">
                <div>文件解析</div>
                <div>研究大纲</div>
                <div>定制视觉</div>
                <div>双格式导出</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="how-it-works">
        <div className="section-heading">
          <p className="eyebrow">HOW IT WORKS</p>
          <h2 id="how-it-works">三步得到可交付的演示。</h2>
        </div>
        <div className="workflow">
          {steps.map(([step, title, description]) => (
            <article className="workflow-card" key={step}>
              <span>{step}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
