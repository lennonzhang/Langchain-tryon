# Validation and Release Checklist

**Purpose:** Standard verification and documentation checklist for safe changes.  
**When to read:** Before merge or release, especially for behavior or contract changes.

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend-react
pnpm test
pnpm test:e2e
pnpm run build
```

## Behavior-Change Checklist

- Update tests for changed behavior.
- Update shared assistant docs under `docs/assistant/*`.
- Keep `AGENTS.md` and `CLAUDE.md` as thin entry pages with correct links.
- Add a detailed `CHANGELOG.md` entry.
- Update `README.md` if user-facing behavior changed.

## Contract Safety Checklist

- SSE event names are unchanged unless explicitly planned and documented.
- Error invariant remains `error` then `done(error)`.
- Request limits remain documented and consistent with schema/handlers.
- Provider routing and model policy remain registry-driven.

## Related

- Runtime + commands: [`./runtime-and-commands.md`](./runtime-and-commands.md)
- API + SSE contract: [`./api-and-sse-contract.md`](./api-and-sse-contract.md)
- Path index: [`./path-index.md`](./path-index.md)
