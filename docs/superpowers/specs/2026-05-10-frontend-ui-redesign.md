# PIAP Frontend UI Redesign Spec

**Date:** 2026-05-10
**Status:** approved
**Scope:** Full visual redesign of the PIAP Vue 3 frontend

## Goal

Transform the PIAP frontend from basic Element Plus default styling to a modern minimal (Linear/Vercel-inspired) design using Tailwind CSS for layout/styling alongside Element Plus for complex interactive components.

## Tech Stack

- Vue 3 + TypeScript + Vite (unchanged)
- Element Plus 2.13.5 (retained for complex components: Table, Form, Dialog, Select, DatePicker, Upload, etc.)
- Tailwind CSS v3 (new dependency)
- ECharts 6 (unchanged, chart colors adjusted to new palette)
- Pinia + Vue Router (unchanged)

## Design System

### Color Palette (zinc-based monochrome)

```
brand:         #18181b (zinc-900) — primary actions, active states
brand-soft:    #3f3f46 (zinc-700) — hover states
bg-page:       #fafafa (zinc-50)  — page background
bg-surface:    #ffffff            — cards, surfaces
border:        #e4e4e7 (zinc-200) — borders, dividers
text-primary:  #09090b (zinc-950) — headings, body text
text-secondary:#71717a (zinc-500) — captions, metadata
success:       #22c55e            — pass/success states
warning:       #f59e0b            — warnings
danger:        #ef4444            — errors/failures
```

### Spacing (4px grid)

8, 12, 16, 20, 24, 32, 40, 48

### Border Radius

- Small elements (buttons, inputs, tags): 8px
- Cards: 12px
- Large containers: 16px

### Shadows (minimal)

- `sm`: 0 1px 2px rgba(0,0,0,0.04)
- `md`: 0 4px 12px rgba(0,0,0,0.06)
- `lg`: 0 12px 24px rgba(0,0,0,0.08)

### Typography

- Font: Noto Sans SC (unchanged)
- Scale: 12/13/14/16/18/20/24/32/42

## Implementation Phases

### Phase 1: Infrastructure
- Install Tailwind CSS v3 (tailwindcss, postcss, autoprefixer)
- Create tailwind.config.js with custom color palette and spacing
- Update styles/index.css with Tailwind directives and base resets
- Bridge Element Plus CSS variables to Tailwind theme
- Verify no visual breakage on existing pages

### Phase 2: Layout Shell
- Rewrite AppLayout.vue with Tailwind classes instead of scoped CSS
  - Sidebar: white bg, thin right border, 200px width
  - Topbar: 48px height, white bg, thin bottom border
  - Content: zinc-50 bg, padded
- Rewrite AuthLayout.vue with Tailwind
  - Split layout with brand-colored left panel, white right panel
- Remove old scoped CSS blocks replaced by Tailwind

### Phase 3: Auth Pages
- LoginView.vue: replace native inputs with styled ElInput, Tailwind form layout
- RegisterView.vue: same treatment

### Phase 4: Dashboard
- Hero section: Tailwind gradient, refined typography
- Metric cards: Tailwind card layout, remove custom colored values
- Chart containers: unified card style
- Table containers: cleaner borders and spacing

### Phase 5: ChatView
- Chat toolbar: Tailwind layout
- Message bubbles: Tailwind styling, keep semantic role colors
- Composer: Tailwind input area
- Result cards: Tailwind card with subtle border

### Phase 6: Element Plus Global Theme
- Override Element Plus CSS variables to match zinc palette
- Button: black primary, bordered default, text secondary
- Input: minimal border, zinc focus ring
- Table: no vertical borders, zebra-stripe optional
- Tag: monochrome variants
- Dialog: minimal header/footer

### Phase 7: List & Management Pages
- TaskListView, ResultListView, AlertListView: unified table and filter styling
- Admin pages: consistent form and card layout
- ProfileView: clean card layout

## Non-Goals

- Replacing Element Plus with another component library
- Adding dark mode
- Changing page functionality or behavior
- Modifying backend APIs
- Adding animation/motion (beyond existing transitions)
- Internationalization changes

## Risks & Mitigations

- **Tailwind + Element Plus CSS conflicts**: Use `important: false` in Tailwind config, let Element Plus handle its own components via CSS variables
- **Bundle size increase**: Tailwind purges unused classes in build; expected ~10KB gzipped addition
- **Incremental breakage**: Each phase is self-contained; pages not yet migrated keep their existing scoped CSS
