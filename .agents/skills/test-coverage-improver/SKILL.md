---
name: test-coverage-improver
description: 'Improve test coverage in the langchain-tryon repository: run backend and frontend test suites, identify low-coverage files, propose high-impact tests, and confirm with the user before writing tests.'
---

# Test Coverage Improver

## Overview

Use this skill whenever coverage needs assessment or improvement (coverage regressions, failing thresholds, or user requests for stronger tests). It runs the test suites, analyzes results, highlights the biggest gaps, and prepares test additions while confirming with the user before changing code.

## Quick Start

1. Run backend tests from the repo root: `python -m unittest discover -s tests -v`.
2. Run frontend tests from `frontend-react/`: `pnpm test`.
3. Identify files with missing or minimal test coverage by inspecting:
   - Backend: compare `backend/*.py` against `tests/test_*.py`.
   - Frontend: compare `frontend-react/src/**/*.{js,jsx}` against `frontend-react/src/__tests__/*` and `frontend-react/tests/*`.
4. Summarize coverage gaps: untested modules, untested code paths, and uncovered edge cases.
5. Draft test ideas per file: scenario, behavior under test, expected outcome, and likely coverage gain.
6. Ask the user for approval to implement the proposed tests; pause until they agree.
7. After approval, write the tests, rerun the test suites, and then run `$code-change-verification` before marking work complete.

## Workflow Details

- **Run tests**: Execute backend and frontend test suites. Avoid watch flags.
- **Prioritize targets**:
  - Gateway routes and admission logic (`backend/gateway/`) before internal helpers.
  - Provider protocol adapters (`backend/infrastructure/protocols/`) — error paths, lifecycle recovery.
  - Event mapping and stream normalization (`backend/event_mapper.py`, `backend/provider_event_normalizer.py`).
  - Frontend stream controller, send pipeline, and session isolation (`frontend-react/src/features/chat/`).
  - Files with newly added code or recent bug fixes.
  - Risky code paths: error handling, timeouts, cancellation, concurrent streaming.
- **Design impactful tests**:
  - Hit uncovered paths: error cases, boundary inputs, cancellation/timeouts, and provider failure scenarios.
  - Cover combinational logic rather than trivial happy paths.
  - Backend tests go in `tests/`; frontend unit tests go in `frontend-react/src/__tests__/`; e2e tests go in `frontend-react/tests/`.
  - Avoid flaky async timing.
- **Coordinate with the user**: Present a numbered, concise list of proposed test additions and expected coverage gains. Ask explicitly before editing code or fixtures.
- **After implementation**: Rerun tests, report the updated results, and note any remaining coverage gaps.

## Notes

- Keep any added comments or code in English.
- Do not create `scripts/`, `references/`, or `assets/` unless needed later.
