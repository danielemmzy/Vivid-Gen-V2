# Vivid Gen V2 project instructions

## Source of truth

- This repository, `C:\Users\SAMSUNG\Documents\Vivid-Gen-V2`, is the sole target for Vivid Gen V2 work.
- Before source-code changes, read `docs/PRODUCTION_ROADMAP.md` and re-check the current implementation. Treat the roadmap as direction and phase boundaries, not proof that a gap remains.
- Do not use `C:\Users\SAMSUNG\Documents\vivid-gen` as the implementation target or copy its V1 Prisma generation/billing schema into V2. The folders are independent repositories and databases. Port behavior only when V2 needs it, using V2's architecture.
- Preserve all existing user changes, untracked files, stashes, backups, and local databases. Never use `git stash pop`, reset, clean, or broad restore commands as a shortcut.

## V2 architecture boundaries

- FastAPI owns product/generation APIs and data in PostgreSQL schema `core`; Alembic migrations live in `backend/alembic/versions`.
- Next.js owns authentication UI and auth tables in PostgreSQL schema `auth`; Prisma migrations live in `frontend/prisma/migrations`.
- Both schemas currently share the V2 PostgreSQL database. Keep schema ownership and migration histories separate.
- Local services are defined by `backend/docker-compose.yml`: PostgreSQL on host port `5432`, backend API on `8001`, and frontend on `3001` (verify the active configuration before running or changing ports).
- Preserve the existing FastAPI, Alembic, PostgreSQL, Redis/ARQ, Next.js, Prisma-auth, Fal, Modal, and S3 design. Do not introduce competing databases, job queues, providers, or service layers without a demonstrated requirement.
- The locally inspected Alembic chain is `0001` through `0014`; local Docker reported `0014_widen_varchar32_columns` as head, with the `core` table inventory present. Prisma reported its auth migration up to date. These observations apply only to the inspected local Docker database, not hosted production.

## Skill routing and implementation discipline

- Use installed skills automatically when their descriptions match. For multi-step changes use Superpowers to frame the work; use TDD for feature/fix implementation; use Ponytail and Karpathy Guidelines to keep changes minimal and avoid overengineering; use UI/UX Pro Max for interface work.
- Use systematic debugging for observed defects. Add animation, security, or other focused skills only when relevant. Do not use VibeWise unless the user explicitly starts `$vibe-wise:learn`.
- Use one coherent review workflow for code review; do not duplicate reviews. Do not invoke skills solely to claim they were used.
- Work through the roadmap in small complete slices, but continue to the next independent item instead of stopping at a progress report. Stop only for a specific external decision/access blocker after completing independent work.
- Do not enable paid generation or payment effects without verified provider configuration, webhook security, idempotency, and correct credit reconciliation. Keep secrets and user media out of logs and responses.
- Test only the V2 services: frontend `http://localhost:3001`, backend `http://localhost:8001`. Start only the needed V2 service and stop only a process started for the task; do not disrupt other projects or Docker data.
- For database work, identify the target first, inspect migration state, back up data, use the established migration tool, and verify the resulting schema. Never reset, drop, or overwrite a database to resolve drift.

## Frontend conventions

- Follow existing Next.js, Tailwind, component, accessibility, and reduced-motion patterns in `frontend/`.
- Prefer clear labels and one primary next action per screen. Keep advanced/internal settings out of the main user flow; provide useful search, filters, empty/loading/error states, and understandable generation/payment status.
- Use existing icons and motion conventions. Lottie is selective feedback/illustration, not a replacement for functional icons or real progress.

## Completion reporting

- Update `docs/PRODUCTION_ROADMAP.md` only when an item has implementation and verification evidence. Separate code presence, local verification, hosted-provider verification, and production readiness.
- Report exact files/areas changed, commands and results, database target, remaining gates, and external inputs. Never label V2 production-ready while an applicable release gate is unverified.
