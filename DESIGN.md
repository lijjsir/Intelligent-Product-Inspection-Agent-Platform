# PIAP Design Context

PIAP is a product console. Design should serve operational clarity first: compact navigation, predictable controls, dense but readable data, and traceable quality signals.

## Visual Direction

- Register: product.
- Theme: light, work-focused, and restrained. Operators use the app during normal desk work and need a clear control surface, not an immersive brand page.
- Color strategy: restrained neutrals with purposeful status accents. The current interface uses zinc neutrals, teal for quality/healthy state, amber for attention, red for danger, blue for links and trace actions.
- Avoid one-note palettes. Do not let teal, blue, beige, or dark slate dominate every surface.

## Layout

- Use a persistent left sidebar for workspace navigation and a compact top bar for session/profile actions.
- Prefer full-width tool surfaces, tables, filters, tabs, and metric strips over decorative repeated cards.
- Page sections should be unframed layouts or purposeful panels. Avoid cards inside cards.
- Fixed-format controls such as nav items, tab bars, metric rows, and tables should have stable dimensions to prevent layout shift.
- For governance and analytics pages, prioritize filters, comparison, drilldown, and trace links above explanatory text.

## Components

- Framework: Vue 3, Vite, Element Plus, Pinia, Tailwind CSS.
- Existing primitives include `page-shell`, `card-surface`, `card-surface-hover`, Element Plus buttons, tags, tables, date pickers, selects, collapses, and tabs.
- Navigation labels are usually Chinese. Keep route titles and menu labels consistent.
- Buttons should be clear commands. Prefer icon-capable Element Plus controls where appropriate, but do not add unfamiliar icon-only actions without tooltips.

## Typography

- Default stack: Noto Sans SC, Source Han Sans SC, Helvetica Neue, Arial, sans-serif.
- Compact admin pages should use modest headings and high information density.
- Avoid viewport-scaled font sizes and negative letter spacing.

## Color And Elevation

- Current base CSS maps Element Plus to a zinc monochrome palette.
- Use subtle borders and restrained shadows for operational panels.
- Reserve color for semantic state: success, warning, danger, info, score, trace, and selected state.
- Do not use decorative orbs, bokeh, glassmorphism, gradient text, or marketing hero art.

## Interaction

- Preserve legacy URLs with redirects when consolidating navigation.
- Streaming chat messages should keep content visible and avoid extra labels unless those labels are necessary for workflow state.
- Trust scoring should show status while reviewing, then score/risk/trace after Celery updates the result.
- Langfuse trace links should be easy to find from quality and chat workflows.

## Accessibility

- Keep text inside controls from wrapping awkwardly or clipping.
- Preserve keyboard-accessible Element Plus controls.
- Use sufficient contrast for sidebar text, disabled placeholders, tags, and table metadata.
