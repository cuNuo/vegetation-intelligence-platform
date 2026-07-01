# Repository Guidelines

## Project Structure & Module Organization

This repository implements the internship task book: a vegetation-index algorithm package exposed as OGC-style Web services with a Vue remote-sensing workstation. Backend code is in `backend/app/`: index definitions, NumPy/Joblib/PyTorch engines, Rasterio window pipelines, API routes, Celery workers, storage, and the analysis agent. Backend tests live in `backend/tests/`. Frontend code is in `frontend/src/`, organized around Vue 3 components, Pinia state, MapLibre maps, ECharts statistics, upload/batch workflows, and the agent drawer. Deployment files are in `compose.yml` and `infra/` for Traefik, Nacos, MinIO, Redis, and pygeoapi-related configuration.

## Task Book Alignment

Before major changes, consult `植被指数提取算法封装与Web服务实现实习任务书.docx`. Preserve these requirements: 30 vegetation indices, unified formula registry, Rasterio block/window processing, synchronous and asynchronous OGC API - Processes calls, Celery + Redis queues, MinIO artifact storage, Nacos + Traefik routing, Vue 3 visualization, and an agent that recommends plans but submits work only after user confirmation.

## Build, Test, and Development Commands

Run the backend with the fixed Miniconda environment:

```powershell
cd backend
D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

Run the frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

Quality checks:

```powershell
cd backend
D:\miniconda\envs\giskeshe\python.exe -m ruff check .
D:\miniconda\envs\giskeshe\python.exe -m pytest -q
cd ../frontend
npm run build
```

## Coding Style & Naming Conventions

Python targets 3.11+, uses Ruff, 100-character lines, typed small modules, and centralized formulas. Formula code must not depend directly on Rasterio, Celery, pygeoapi, or MinIO. Vue uses `<script setup lang="ts">`, Composition API, PascalCase components, and focused composables such as `usePlatformApi`.

## Testing Guidelines

Use `pytest` with `test_*.py`. Cover formula arrays, windowed raster processing, NumPy/Joblib/Torch parity, CUDA fallback, sync/async jobs, invalid bands, uploads, and agent safety. UI changes require `npm run build` and browser checks for full-screen responsiveness.

## Commit & Pull Request Guidelines

No commit history exists yet; use Conventional Commits, e.g. `feat: add torch raster engine`. PRs should include scope, task-book requirement addressed, test output, UI screenshots when relevant, and CUDA/Docker/MinIO assumptions.

## Security & Configuration Tips

Do not commit secrets or large GeoTIFF artifacts. Keep credentials in environment files based on `.env.example`. Treat TianDiTu tokens, MinIO credentials, and optional LLM keys as deploy-time configuration.

## Agent-Specific Instructions

Follow global `D:\.codex\AGENTS.md` first. This file only adds repository-specific structure and task-book constraints. Preserve `.serena/` memories and `.evidence/` logs as the audit trail.
