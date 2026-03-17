# Doc Coverage Checklist

Use this checklist to scan the selected scope (main = comprehensive, or current-branch diff) and validate documentation coverage.

## Feature inventory targets

- Backend modules: gateway routes, facades, domain services, infrastructure adapters.
- Frontend components: hooks, components, shared utilities, store.
- Configuration options: environment variables, timeout settings, provider config.
- API endpoints and SSE event types.
- User-facing behaviors: streaming, search, agent mode, error handling, session management.
- Deprecations, removals, or renamed settings.

## Doc-first pass (page-by-page)

- Review each L2/L3/L4 page under `docs/assistant/`.
- Check `CLAUDE.md` and `AGENTS.md` for stale links or outdated fast-reference content.
- Check `README.md` for consistency with `docs/assistant/` canonical details.
- Look for missing env vars, model defaults, or SSE event changes that the page implies.

## Code-first pass (feature inventory)

- Map features to the closest existing page based on the L2/L3/L4 structure.
- Prefer updating existing pages over creating new ones unless the topic is clearly new.
- Use L2 pages for cross-cutting concerns (API contract, architecture rules, provider policy).
- Keep L1 entry pages minimal; move details into L2+ pages.

## Evidence capture

- Record the file path and symbol/setting name.
- Note defaults or behavior-critical details for accuracy checks.
- Avoid large code dumps; a short identifier is enough.

## Red flags for outdated or incorrect docs

- Option names/types no longer exist or differ from code.
- Default values or allowed ranges do not match implementation.
- Features removed in code but still documented.
- New behaviors introduced without corresponding docs updates.
- L1 entry pages (CLAUDE.md, AGENTS.md) diverged from L2 canonical content.

## When to propose structural changes

- A page mixes unrelated audiences (quick-start + deep reference) without clear separation.
- Multiple pages duplicate the same concept without cross-links.
- New feature areas have no obvious home in the L2/L3/L4 structure.

## Diff mode guidance (current branch vs main)

- Focus only on changed behavior: new endpoints/events, modified defaults, removed features, or renamed settings.
- Use `git diff main...HEAD` (or equivalent) to constrain analysis.
- Document removals explicitly so docs can be pruned if needed.

## Patch guidance

- Keep edits scoped and aligned with existing tone and format.
- Update cross-links when moving or renaming sections.
- Follow the documentation update rule: `docs/assistant/*` → `CLAUDE.md`/`AGENTS.md` → `CHANGELOG.md` → `README.md`.
