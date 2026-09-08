# Frontend Task Assignment: Curated Non-Blue Light Theme, Hyper-Rounded Geometry & Flat-Depth Polish

---

## 📋 Task Overview
**Goal:** Redesign the light theme into a modern, sophisticated, non-white tinted palette without generic electric blue colors, apply full hyper-rounded pill geometry across all UI elements, and remove all glowing box-shadows in favor of crisp minimalist borders and subtle natural depth.

## 🚫 Constraints & Rules
- **Color Palette (Non-Blue & Non-White Canvas):**
  - Background: Warm/slate tinted modern canvas (`#eef2f6` / `#f0f2f5`).
  - Cards & Surfaces: Clean crisp surface (`#ffffff` / `#fafbfd`) with defined neutral borders (`#dbe2ea`).
  - Accent & Buttons: Elegant Obsidian / Dark Slate (`#111827` / `#0f172a` hover `#1f2937`) or rich refined forest spruce—no generic electric or brand blue.
  - Success / Danger: Refined Sage Green (`#166534` / `#f0fdf4`) and Soft Muted Rust/Crimson (`#991b1b` / `#fef2f2`).
  - Muted Text: Slate Charcoal (`#64748b` / `#475569`), Headings (`#0f172a`).
- **Geometry (Fully Rounded):**
  - Buttons & Inputs: Full pill radius (`border-radius: 9999px`).
  - Cards: Hyper-rounded modern corners (`border-radius: 28px` to `32px`).
  - Video Preview & Panels: Rounded corners (`border-radius: 24px`).
  - Badges, Steppers, Tabs, Search: Full pill radius (`border-radius: 9999px`).
- **Shadows & Lighting:**
  - **No glowing colored shadows** or flashy pulsing glow rings.
  - Flat, crisp borders with subtle, natural ambient depth (`0 1px 3px rgba(0,0,0,0.03)`).
- **Typography:**
  - Maintain clean **Poppins** typography with balanced weights (500/600).
- **Behavior & Stability:**
  - Zero functional regressions. All camera streams, WebSockets, event listeners, KYC verification, and routing logic must remain intact.

## 📂 Relevant Files
- `src/index.css` (tokens, theme colors, rounded styling, clean transitions)
- `src/components/` & `src/pages/` (component styling and markup consistency)

## ✅ Definition of Done
1. Curated non-blue palette with tinted backdrop and obsidian/charcoal primary interactive elements.
2. Fully rounded pill geometry applied to all buttons, inputs, tabs, search, badges, and cards.
3. Zero glowing shadows or flashy colored glow animations.
4. Clean TypeScript check and production build with 100% functional integrity.