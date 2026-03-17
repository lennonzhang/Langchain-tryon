---
name: code-change-verification
description: Run the mandatory verification stack when changes affect runtime code, tests, or build/test behavior in the langchain-tryon repository.
---

# Code Change Verification

## Overview

Ensure work is only marked complete after backend tests, frontend tests, and frontend build pass. Use this skill when changes affect runtime code, tests, or build/test configuration. You can skip it for docs-only or repository metadata unless a user asks for the full stack.

## Quick start

1. Keep this skill at `./.agents/skills/code-change-verification` so it loads automatically for the repository.
2. macOS/Linux: `bash .agents/skills/code-change-verification/scripts/run.sh`.
3. Windows: `powershell -ExecutionPolicy Bypass -File .agents/skills/code-change-verification/scripts/run.ps1`.
4. If any command fails, fix the issue, rerun the script, and report the failing output.
5. Confirm completion only when all commands succeed with no remaining issues.

## Manual workflow

- If backend dependencies are not installed or have changed, run `pip install -r requirements.txt` first.
- If frontend dependencies are not installed or have changed, run `pnpm install` from `frontend-react/`.
- Run from the repository root in this order:
  1. Backend tests: `python -m unittest discover -s tests -v`
  2. Frontend tests (from `frontend-react/`): `pnpm test`
  3. Frontend e2e tests (from `frontend-react/`): `pnpm test:e2e`
  4. Frontend build (from `frontend-react/`): `pnpm run build`
- Do not skip steps; stop and fix issues immediately when a command fails.
- Re-run the full stack after applying fixes so the commands execute in the required order.

## Resources

### scripts/run.sh

- Executes the full verification sequence with fail-fast semantics from the repository root. Prefer this entry point to ensure the required commands run in the correct order.

### scripts/run.ps1

- Windows-friendly wrapper that runs the same verification sequence with fail-fast semantics. Use from PowerShell with execution policy bypass if required by your environment.
