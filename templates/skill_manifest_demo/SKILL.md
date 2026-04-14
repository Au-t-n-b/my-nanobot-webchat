---
name: skill-manifest-hitl-demo
description: Use when validating two-file upload gating, automatic progression, and fixed output choices driven by skill.manifest.json
---

# Skill Manifest Demo

This template demonstrates a complete declarative flow:
1. Check whether `到货表.xlsx` and `人员信息表.xlsx` exist.
2. If either file is missing, keep showing the upload card.
3. After uploads complete, automatically re-check required files.
4. Once both files exist, automatically enter the output choice step.
5. Route to one of three fixed test actions: HTML, MD, or other.

Use `skill.manifest.json` for executable file checks, automatic progression, and output choices.
Use `SKILL.md` for the human-readable business instructions and testing notes.
