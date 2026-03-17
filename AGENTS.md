# AGENTS.md

Repository-level entry guide for coding agents.

## Scope

- Applies to the whole repo unless a deeper folder overrides it.
- Keep changes minimal, testable, and aligned with current architecture.
- Read the relevant L2 docs below before making changes.

## Quick Navigation (Progressive Disclosure)

IMPORTANT: Before starting any task, identify which docs below are relevant and read them first.

L2 shared rules:

- Runtime + commands: [`docs/assistant/runtime-and-commands.md`](docs/assistant/runtime-and-commands.md)
- API + SSE contract: [`docs/assistant/api-and-sse-contract.md`](docs/assistant/api-and-sse-contract.md)
- Model + provider policy: [`docs/assistant/model-and-provider-policy.md`](docs/assistant/model-and-provider-policy.md)
- Architecture rules: [`docs/assistant/architecture-rules.md`](docs/assistant/architecture-rules.md)

L3 deep index:

- Path index: [`docs/assistant/path-index.md`](docs/assistant/path-index.md)
- Validation + release checklist: [`docs/assistant/validation-and-release-checklist.md`](docs/assistant/validation-and-release-checklist.md)

L4 detailed references:

- Error status matrix: [`docs/assistant/error-status-matrix.md`](docs/assistant/error-status-matrix.md)

Skills (`.agents/skills/`):

- `code-change-verification` — run `$code-change-verification` after code changes
- `docs-sync` — run `$docs-sync` when auditing or updating documentation
- `final-release-review` — run `$final-release-review` before releases
- `implementation-strategy` — run `$implementation-strategy` before changing APIs or contracts
- `pr-draft-summary` — run `$pr-draft-summary` when wrapping up a task
