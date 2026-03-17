# Release Diff Review Checklist

## Quick commands

- Sync tags: `git fetch origin --tags --prune`.
- Identify latest release tag (default pattern `v*`): `git tag -l 'v*' --sort=-v:refname | head -n1` or use `.agents/skills/final-release-review/scripts/find_latest_release_tag.sh`.
- Generate overview: `git diff --stat BASE...TARGET`, `git diff --dirstat=files,0 BASE...TARGET`, `git log --oneline --reverse BASE..TARGET`.
- Inspect risky files quickly: `git diff --name-status BASE...TARGET`, `git diff --word-diff BASE...TARGET -- <path>`.

## Gate decision matrix

- Choose `🟢 GREEN LIGHT TO SHIP` when no concrete blocking trigger is found.
- Choose `🔴 BLOCKED` only when at least one blocking trigger has concrete evidence and a defined unblock action.
- Blocking triggers:
  - Confirmed regression/bug introduced in the diff.
  - Confirmed breaking API/SSE/config change with missing or mismatched versioning/migration path.
  - Concrete data-loss/corruption/security-impacting issue with unresolved mitigation.
  - Release-critical build/runtime break introduced by the diff.
- Non-blocking by itself:
  - Large refactor or high file count.
  - Speculative risk without evidence.
  - Not running tests locally.
- If uncertain, keep gate green and provide focused follow-up checks.

## Actionability contract

- Every risk finding should include:
  - `Evidence`: specific file/commit/diff/test signal.
  - `Impact`: one-sentence user or runtime effect.
  - `Action`: concrete command/task with pass criteria.
- A `BLOCKED` report must contain an `Unblock checklist` with at least one executable item.
- If no executable unblock item exists, do not block; downgrade to green with follow-up checks.

## Breaking change signals

- API surface: removed/renamed endpoints, changed request/response shape, SSE event names changed, new required fields, stricter validation.
- SSE contract: event types added/removed/renamed, envelope field changes, invariant changes (error → done flow).
- Config/env: renamed env vars, default behavior flips, removed fallbacks (e.g., `SEARCH_BACKEND=legacy` removal), timeout changes.
- Dependencies/platform: Python version requirement changes, `requirements.txt` major bumps, Node/pnpm version changes.
- Provider protocol: transport adapter changes, lifecycle recovery behavior, error normalization changes.
- Frontend: session isolation changes, stream controller behavior, component contract changes.

## Regression risk clues

- Large refactors with light test deltas or deleted tests; new `skip`/`todo` markers.
- Concurrency/timing: new async flows, SSE streaming changes, retries, timeouts, debounce/caching changes, race-prone patterns.
- Error handling: catch blocks removed, swallowed errors, broader catch-all added without logging, stricter throws without caller updates.
- Stateful components: mutable shared state, global singletons, lifecycle changes (init/teardown), resource cleanup removal.
- Provider changes: swapped transport libraries, search backend changes, model registry changes.

## Improvement opportunities

- Missing coverage for new code paths; add focused tests.
- Performance: obvious N+1 loops, repeated I/O without caching, excessive serialization.
- Developer ergonomics: unclear naming, missing inline docs for public modules.
- Release hygiene: add CHANGELOG entry when behavior changes; ensure docs/assistant/* capture user-facing shifts.

## Evidence to capture in the review output

- BASE tag and TARGET ref used for the diff; confirm tags fetched.
- High-level diff stats and key directories touched.
- Concrete files/commits that indicate breaking changes or risk, with brief rationale.
- Tests or commands suggested to validate suspected risks (include pass criteria).
- Explicit release gate call (ship/block) with conditions to unblock.
- `Unblock checklist` section when (and only when) gate is `BLOCKED`.
