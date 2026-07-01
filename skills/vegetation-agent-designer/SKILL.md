---
name: vegetation-agent-designer
description: "Design and evolve the vegetation-index analysis agent for this project: LangChain provider setup, RAG over index knowledge, safe custom-index tools, user-confirmed execution, PostgreSQL persistence, and result interpretation."
---

# Vegetation Agent Designer

Use this skill when improving, reviewing, or extending the project's intelligent vegetation-analysis agent.

## Scope

This project agent is not an open-ended chatbot. It is a remote-sensing analysis planner that turns user intent into a safe, auditable workflow:

```text
understand request -> inspect data -> retrieve index knowledge -> recommend plan
-> show formula/risks/cost -> user confirms -> submit job -> monitor status
-> summarize statistics and limitations
```

## Required Design Principles

- Keep the deterministic rule engine as the reliable fallback.
- Use LangChain only as a pluggable enhancement for intent, reasoning, and summary generation.
- Support OpenAI-compatible and Anthropic providers through request-level `token`, `base_url`, and `model`.
- Never let the LLM directly execute code, write files, choose arbitrary paths, or submit high-cost jobs.
- Any custom vegetation index must pass AST whitelist validation, required-band inference, and sample-array execution before registration.
- Persist accepted custom indices in PostgreSQL when `VIP_DATABASE_URL` is configured; otherwise degrade to memory and surface the storage mode.
- RAG must retrieve from the index registry first, then optional external/web sources. Show citations or source labels in the UI.
- Every agent run must expose a trace: retrieval, tool calls, validation, engine selection, confirmation, execution, and result interpretation.

## Project Touchpoints

- Backend agent orchestration: `backend/app/services/agent.py`
- Agent tools and RAG: `backend/app/services/agent_tools.py`
- Custom index persistence: `backend/app/services/custom_index_store.py`
- API schemas/routes: `backend/app/api/schemas.py`, `backend/app/api/routes.py`
- Index registry: `backend/app/core/indices.py`
- Execution and manifest: `backend/app/services/raster_pipeline.py`, `backend/app/services/jobs.py`
- Frontend agent UI: `frontend/src/components/AgentDrawer.vue`
- Job status UI: `frontend/src/components/JobProgressPanel.vue`
- API client/types: `frontend/src/composables/usePlatformApi.ts`, `frontend/src/types/platform.ts`

## Implementation Checklist

When adding agent capabilities:

1. Define the user-facing workflow and safety boundary first.
2. Add or update a typed request/response schema.
3. Implement deterministic behavior before LLM behavior.
4. If using LangChain, make imports lazy or keep graceful fallback behavior.
5. Add trace steps for every hidden operation.
6. Add tests for fallback, missing-band blocking, unsafe custom formulas, and no-confirmation/no-submit behavior.
7. Update `/api/system/taskbook-coverage` if the feature maps to a task-book requirement.
8. Run backend tests, Ruff, frontend build, and write evidence.

## Verification Commands

```powershell
cd backend
D:\miniconda\envs\giskeshe\python.exe -m pytest -q
D:\miniconda\envs\giskeshe\python.exe -m ruff check .

cd ..\frontend
npm run build
```

## Evidence Expectations

Record:

- user intent and assumptions;
- changed agent tools/providers/storage;
- safety checks and fallback paths;
- verification output;
- any remaining demo-only or environment-specific limitations.
