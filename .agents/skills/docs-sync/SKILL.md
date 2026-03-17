---
name: docs-sync
description: Analyze implementation and configuration to find missing, incorrect, or outdated documentation in the langchain-tryon repository. Use when asked to audit doc coverage, sync docs with code, or propose doc updates/structure changes. Provide a report and ask for approval before editing docs.
---

# Docs Sync

## Overview

Identify doc coverage gaps and inaccuracies by comparing current features and configuration options against the documentation structure, then propose targeted improvements.

## Documentation Structure

This project uses a 4-level progressive disclosure model:

- **L1 (Entry):** `CLAUDE.md` and `AGENTS.md` — thin entry pages with links
- **L2 (Shared rules):** `docs/assistant/runtime-and-commands.md`, `api-and-sse-contract.md`, `model-and-provider-policy.md`, `architecture-rules.md`
- **L3 (Deep index):** `docs/assistant/path-index.md`, `validation-and-release-checklist.md`
- **L4 (Reference):** `docs/assistant/error-status-matrix.md`
- **Runbook:** `README.md` — developer setup and product behavior

## Workflow

1. Confirm scope and base branch
   - Identify the current branch and default branch (usually `main`).
   - Prefer analyzing the current branch to keep work aligned with in-flight changes.
   - If the current branch is not `main`, analyze only the diff vs `main` to scope doc updates.
   - Avoid switching branches if it would disrupt local changes; use `git show main:<path>` or `git worktree add` when needed.

2. Build a feature inventory from the selected scope
   - If on `main`: inventory the full surface area and review docs comprehensively.
   - If not on `main`: inventory only changes vs `main` (feature additions/changes/removals).
   - Focus on user-facing behavior: API endpoints, SSE events, environment variables, model defaults, frontend behavior, and documented runtime behaviors.
   - Capture evidence for each item (file path + symbol/setting).
   - Use targeted search to find option types and feature flags (for example: `rg "os.environ"`, `rg "SEARCH_BACKEND"`, `rg "TAVILY_"`).

3. Doc-first pass: review existing pages
   - Walk each relevant page under `docs/assistant/`.
   - Check `CLAUDE.md`, `AGENTS.md`, and `README.md` for consistency.
   - Identify missing mentions of important supported options (env vars, model defaults), customization points, or new features from `backend/` and `frontend-react/`.
   - Propose additions where users would reasonably expect to find them on that page.

4. Code-first pass: map features to docs
   - Review the current docs structure under `docs/assistant/`.
   - Determine the best page/section for each feature based on existing L2/L3/L4 patterns.
   - Identify features that lack any doc page or have a page but no corresponding content.
   - Note when a structural adjustment would improve discoverability.

5. Detect gaps and inaccuracies
   - **Missing**: features/configs present in code but absent in docs.
   - **Incorrect/outdated**: names, defaults, or behaviors that diverge from code.
   - **Structural issues** (optional): pages overloaded, missing overviews, or mis-grouped topics.

6. Produce a Docs Sync Report and ask for approval
   - Provide a clear report with evidence, suggested doc locations, and proposed edits.
   - Ask the user whether to proceed with doc updates.

7. If approved, apply changes
   - Update `docs/assistant/*` (single source of truth for shared rules).
   - Update `CLAUDE.md` and `AGENTS.md` entry links if needed.
   - Append a detailed entry to `CHANGELOG.md`.
   - Update `README.md` if user-facing behavior changed.

## Output format

Use this template when reporting findings:

Docs Sync Report

- Doc-first findings
  - Page + missing content -> evidence + suggested insertion point
- Code-first gaps
  - Feature + evidence -> suggested doc page/section (or missing page)
- Incorrect or outdated docs
  - Doc file + issue + correct info + evidence
- Structural suggestions (optional)
  - Proposed change + rationale
- Proposed edits
  - Doc file -> concise change summary
- Questions for the user

## References

- `references/doc-coverage-checklist.md`
