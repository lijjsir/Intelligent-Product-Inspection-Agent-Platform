# PIAP Product Context

register: product

PIAP, Intelligent Product Inspection Agent Platform, is an internal product-quality operations platform for AI-assisted inspection, quality analysis, governance, and agent workflow management. It is not a marketing site. The primary experience is a dense, repeat-use console for people who need to inspect products, review AI outputs, manage tasks, govern models, and trace quality signals with minimal friction.

## Users

- End users and experts use the app workspace to ask inspection questions, manage inspection tasks, review results, upload evidence, and export reports.
- Admins use the governance workspace to manage users, model configuration, inspection standards, GPU scheduling, memory governance, and quality analytics.
- Platform operators use the ops and governance workspaces to monitor models, data quality, costs, releases, templates, and quality trends.
- Algorithm engineers use the governance and ops workspaces to maintain model configuration, inspection standards, datasets, evaluation, training, deployment records, and experiment traceability.
- App developers use the ops workspace to manage agents, prompts, routes, RAG configuration, workflows, tools, and releases.

## Product Purpose

PIAP reduces the operational cost and risk of product inspection by combining structured inspection workflows, AI quality scoring, RAG-backed answers, Langfuse traceability, task execution, and governance controls in one console. The product should make quality signals auditable: users should understand what was answered, which evidence was used, how trustworthy the result is, and where to inspect the underlying trace.

## Tone

The interface should feel calm, precise, and operational. It should support repeated use without visual fatigue. Copy should be short and concrete, using Chinese labels where the surrounding UI is Chinese. Avoid marketing language, empty encouragement, decorative filler, or feature explanations inside the app.

## Strategic Principles

- Prefer one clear operational entry point over duplicated navigation. For example, quality report and quality tracing are merged into the Analysis Center.
- Surface status, risk, score, cost, trace, and ownership where operators need to act.
- Preserve legacy routes when consolidating pages, but keep the visible menu simple.
- Optimize for scanning, filtering, comparison, and drilldown rather than hero-page storytelling.
- Avoid UI patterns that hide governance evidence or make audit trails feel decorative.

## Anti-References

- Do not make SaaS landing-page layouts inside console pages.
- Do not use oversized hero sections for routine admin work.
- Do not create card-heavy decorative dashboards when a table, tab, filter bar, or compact metric strip is clearer.
- Do not rely on a one-note color theme; quality, risk, trace, status, and cost should have distinct but restrained roles.
