# Product

## Register

product

## Users

Students, graduate students, teachers, international students, researchers, course-report presenters, thesis-defense candidates, and business presenters who need a polished deck quickly but still want to control the storyline and visual direction.

They arrive with a topic, pasted text, or uploaded material. Their main context is deadline-driven: they want the system to understand the source, ask only the necessary questions, generate a strong outline, offer professional visual directions, and export files they can directly use or edit.

## Product Purpose

This is an international AI PPT SaaS that converts user input into a reviewed `OutlineDecision`, three premium `VisualDirection` choices, one canonical `SlideDeck JSON`, and then both editable PPTX and HyperFrames-style dynamic HTML from that same deck contract.

Success means the user feels the product actually thinks before designing: it parses source material, builds a content-aware outline, proposes distinct visual directions, and exports a presentation that feels personally tailored rather than like text swapped into a few templates.

## Brand Personality

Premium, calm, intelligent.

The product should feel like a careful presentation strategist: concise, confident, Chinese-first in the local workflow, internationally capable, and quietly high-end rather than flashy.

## Anti-references

Do not look like a generic template gallery, a data-heavy dashboard, a prompt playground, or a brittle demo that only swaps text into a few fixed templates.

Avoid exposing raw prompts, provider errors, uploaded source dumps, implementation logs, or excessive technical details to ordinary users. Avoid visual clutter, over-rounded glass cards, low-contrast muted text, and “AI SaaS boilerplate” layouts that make every step feel like the same card repeated.

## Design Principles

1. Guide one decision at a time: the conversation should reveal the next question only after the current one is useful.
2. Show thinking, not machinery: make outline quality, visual rationale, and export readiness visible without exposing implementation noise.
3. Preserve the canonical pipeline: PPTX and HyperFrames HTML must both come from the same `SlideDeck JSON`.
4. Make choice feel expert: visual directions should be distinct editorial recommendations, not a template picker.
5. Keep the interface quieter than the output: the app should stay focused so the user’s future PPT feels like the hero.

## Legal Low-Cost Agent Architecture

This product is workflow software. It must not become a hidden backend for consumer web subscriptions.

Allowed low-cost architectures:

- User-owned API keys / BYOK for OpenAI, Claude-compatible, Gemini, DeepSeek, Qwen, Kimi, OpenRouter, Groq, local OpenAI-compatible providers, or Ollama.
- Hybrid model routing: cheap/local models for cleanup and formatting, mid-tier models for planning and consistency, strong models only for final polish or high-stakes review.
- Human-in-the-loop prompt workspace: generate copyable prompt packs that users manually paste into their own ChatGPT/Claude/Gemini membership, then paste results back.

Red lines:

- Do not automate consumer-web login.
- Do not collect, store, share, or replay cookies or browser sessions.
- Do not treat ChatGPT/Claude/Gemini frontend subscriptions as backend APIs.

Product modes:

- Fast mode: low cost, quick loop, bounded research.
- Research mode: public-source cascade, source-gap brief, stronger selective QA.
- Enterprise mode: BYOK/customer-owned enterprise provider, stronger polish, audit trail, human review hooks.

## Accessibility & Inclusion

Target WCAG AA for text contrast, keyboard navigation, focus states, and form semantics. Respect reduced-motion preferences. Chinese and English users should both be able to understand the core workflow, with the current local workflow optimized for Chinese.
