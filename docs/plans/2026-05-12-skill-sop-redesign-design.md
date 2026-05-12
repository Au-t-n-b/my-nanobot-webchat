# Skill SOP Redesign Design

## Background

This redesign updates the Skill development SOP so developers and AI assistants follow a visible, gated workflow before generating any Skill files.

The current `docs/README.md` already points Skill developers to the relevant docs, and `docs/skill/cursor-sop.md` already contains useful implementation prompts. However, the intended flow is not explicit enough:

- Developers may start by copying a starter before the requirement is clear.
- AI assistants may rush into writing `module.json`, `dashboard.json`, `driver.py`, or UI files.
- The required decision about interaction ownership is not framed as a hard question: left ChatCard/HITL vs middle Dashboard/SDUI vs EmbeddedWeb vs right Preview/artifact.

The new SOP makes that workflow visible and enforceable.

## Goals

- Add a Mermaid flowchart at the top of `docs/skill/cursor-sop.md` as a visual map for both humans and AI assistants.
- Add a Hard Gate that forbids generating Skill business files before multi-round clarification is complete and the user explicitly approves the implementation plan.
- Make UI ownership a required clarification question: ChatCard/HITL, Dashboard/SDUI, EmbeddedWeb, Preview/artifact, or a mixed layout with ownership called out per surface.
- Reorder `docs/README.md` so `cursor-sop.md` is the entry point for Skill development, with starter docs used after the Hard Gate is cleared.
- Preserve the existing starter, implementation prompt, three-round delivery, EmbeddedWeb notes, and common pitfalls where they still apply.

## Non-Goals

- Do not change platform runtime behavior, SDUI schema, HITL implementation, or starter source code.
- Do not introduce a new Skill development framework.
- Do not solve the separate `template` Skill dashboard patch debugging issue in this redesign.
- Do not require every Skill to use HITL or artifact publishing; explicitly confirming "none for MVP" is acceptable.

## Proposed Documentation Changes

### `docs/README.md`

Update the Skill developer path so `docs/skill/cursor-sop.md` is the first required reading item.

Add a strong entry warning:

- If the user or their AI assistant wants to develop a Skill, read the Cursor SOP Hard Gate first.
- Before clarification and explicit approval, generating Skill files is forbidden.
- Starter, guide, protocol, and patch docs are references used after the Hard Gate or during clarification.

Keep the platform maintainer path and design/plans sections unchanged.

### `docs/skill/cursor-sop.md`

Replace the current opening sections with a clearer structure:

1. Add a Mermaid flowchart immediately after the title and introductory paragraph.
2. Add a Hard Gate section.
3. Move the existing clarification prompt into the Hard Gate section as an execution template.
4. Compress the old "prepare materials" and "organize clarification result" sections into one post-gate input summary.
5. Keep starter selection, implementation prompt, three-round delivery, EmbeddedWeb SOP, and pitfalls.
6. Add "violating the Hard Gate" as a common pitfall.

## Hard Gate Rules

The Hard Gate applies when creating a new stage Skill or reworking an existing Skill's core interaction.

Before it is cleared:

- Do not create files under `~/.nanobot/workspace/skills/<name>/`.
- Do not generate `module.json`, `data/dashboard.json`, `runtime/driver.py`, `ui/*.html`, or business code.
- Do not modify platform code as part of the Skill implementation.

Allowed before the gate clears:

- Read docs, starters, and reference implementations.
- Ask clarification questions.
- Draft state machines, node trees, event plans, and implementation options.
- Present pseudocode or diagrams.

The gate clears only when both conditions are true:

- All five clarification questions are answered:
  - Business goal, input, and output.
  - State machine: state, action, trigger, and emitted events.
  - UI ownership: ChatCard/HITL, Dashboard/SDUI, EmbeddedWeb, Preview/artifact, or mixed.
  - HITL mode: file, text, choice, confirm, or explicitly none for MVP.
  - Artifact output and preview behavior, or explicitly none for MVP.
- The user explicitly approves the proposed implementation approach.

## Mermaid Flow

The flowchart should show:

- Developer starts from `@docs/README.md`.
- README routes to `docs/skill/cursor-sop.md`.
- Cursor enters multi-round clarification and must not generate code.
- Clarification includes the required UI ownership question.
- If answers are incomplete, loop back to clarification.
- Cursor presents an implementation plan.
- If the user requests changes, loop back to clarification.
- If the user approves, the Hard Gate is cleared.
- Only then select a starter and implement in three rounds: mount + patch, HITL, artifacts.

## Alternatives Considered

### Only Modify `cursor-sop.md`

This keeps the change tightly scoped but leaves `README.md` under-emphasizing the SOP as the entry point.

Rejected because the observed workflow starts with `@docs/README.md`, so the entry document should carry the warning.

### Modify `README.md` and `cursor-sop.md`

This is the selected approach. It keeps the strong process in one place while making the README route developers into it.

### Add a Separate Workflow Document

This would be more formal but adds one more place for developers to read. The SOP should be the source of truth.

Rejected for now.

## Success Criteria

- A developer opening `docs/skill/cursor-sop.md` sees the whole Skill development path before any implementation instructions.
- The SOP clearly states that AI must not generate Skill files before multi-round clarification and explicit user approval.
- The UI ownership decision is impossible to miss.
- `docs/README.md` directs Skill developers to the SOP before starter usage.
- Existing useful implementation material remains available after the gate.

