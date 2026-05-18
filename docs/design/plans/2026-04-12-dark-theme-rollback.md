# Dark Theme Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the previously approved dark theme palette for the intelligent analysis workbench while keeping the new layout and interaction structure unchanged.

**Architecture:** This change is limited to the dark-theme token definitions in `frontend/app/globals.css`. All component structure, preview drawer behavior, overview cards, and quick-action placement remain untouched; visual verification focuses on whether existing components inherit the restored palette correctly.

**Tech Stack:** Next.js app router, Tailwind utility classes, CSS custom properties in `frontend/app/globals.css`

---

### Task 1: Roll Back Dark Theme Tokens

**Files:**
- Modify: `frontend/app/globals.css`
- Verify: browser refresh of the running local app

- [ ] **Step 1: Restore the previous dark-theme token values**

Update the dark theme block in `frontend/app/globals.css` so these variables match the previous palette:

```css
:root,
[data-theme="dark"] {
  --surface-0: #09090b;
  --surface-1: #18181b;
  --surface-2: #1c1c1f;
  --surface-3: #27272a;
  --canvas-rail: #111111;
  --paper-chat: #18181b;
  --paper-card: #1c1c1f;
  --text-primary: #d4d4d8;
  --text-secondary: #a1a1aa;
  --text-muted: #71717a;
  --accent: #f59e0b;
  --accent-soft: rgba(245, 158, 11, 0.15);
}
```

- [ ] **Step 2: Confirm no other theme blocks are changed**

Visually compare the surrounding light and soft theme sections and keep them exactly as-is.

Expected: only the dark-theme token block differs after the edit.

- [ ] **Step 3: Refresh the running app and verify the palette**

Check these areas in the browser after refresh:

```text
1. Chat header buttons and send button return to amber emphasis
2. Project overview cards sit on the older black/gray surfaces
3. Preview drawer inherits the restored dark rail and paper colors
4. Quick action pills and progress highlights no longer read blue
```

Expected: the UI keeps the new structure, but the overall feel returns to the earlier black/gray + amber palette.

- [ ] **Step 4: Record environment limitation if automated lint is unavailable**

Use this note if needed in the handoff:

```text
Unable to run frontend lint in the current shell because node/npm is not installed in PATH on this machine context; verification was done by file review and browser refresh.
```
