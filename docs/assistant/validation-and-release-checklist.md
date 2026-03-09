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
- Verify markdown code blocks still render wrapper UI, support copy interaction, and highlight after stream completion.
- Verify `+ New Chat` draft mode does not show previous session messages and preserves unsent draft across session switches.
- Verify composer submit button switches to `Stop` only for the active running session; other sessions remain send-disabled.
- Verify session delete action appears at card bottom-right on hover/focus for pointer-hover devices, and remains disabled for running sessions.
- Verify sidebar remains fixed-responsive width on desktop/tablet and long session text does not resize sidebar width.
- Verify mobile (`<=600px`) and narrow desktop layouts (`.app-shell < sessionSidebarWidth * 2.7`) use the sessions drawer from the chat header button and close via backdrop/select/new-chat actions.
- Verify agent reasoning streams are paragraph-separated across steps (`agent_step_start`) and sticky in-chunk step text is split for readability.

## Contract Safety Checklist

- SSE event names are unchanged unless explicitly planned and documented.
- Error invariant remains `error` then `done(error)`.
- Request limits remain documented and consistent with schema/handlers.
- `request_id` limit (`256`) remains enforced consistently in schema, FastAPI gateway, and cancel handlers/routes.
- Provider routing and model policy remain registry-driven.
- Provider timeout precedence remains documented and tested: `<PROVIDER>_TIMEOUT_SECONDS` -> `MODEL_TIMEOUT_SECONDS` -> default.
- If `<PROVIDER>_SSL_VERIFY=false`, warning logging behavior remains intentional and tested.

## Related

- Runtime + commands: [`./runtime-and-commands.md`](./runtime-and-commands.md)
- API + SSE contract: [`./api-and-sse-contract.md`](./api-and-sse-contract.md)
- Path index: [`./path-index.md`](./path-index.md)
