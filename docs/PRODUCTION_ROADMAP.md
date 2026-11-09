# Vivid Gen V2 — Production Roadmap

> **Repository scope:** `C:\Users\SAMSUNG\Documents\Vivid-Gen-V2` only. V2 is the sole source of truth going forward. The separate `C:\Users\SAMSUNG\Documents\vivid-gen` checkout is V1 and is not a target for implementation or a source of migrations. Port product behavior only when V2 needs it; do not copy V1 Prisma generation tables or its `PolarOrder` model into V2.
>
> **Evidence boundary:** This roadmap separates local evidence from hosted/production verification. A local schema or passing unit test does not prove production readiness.

## Product goal and scope

Vivid Gen V2 is a creative video studio: users create images, clips, audio, and storyboard-based productions; review progress and outputs; then export or download finished work. The product should make the next useful action obvious, show honest cost/status, and preserve user work when a provider or render fails.

Use Pictory as a workflow reference for idea/script → storyboard → scene review → narration/captions → render/export. Adapt the workflow, not its branding or proprietary interface. V2 already has a broader production model; focus on making its actual capabilities coherent and dependable rather than adding another editing platform.

### Product rules

- One primary next action per page; use plain user-facing terms, not provider IDs, internal status strings, or cryptic job names.
- Keep user projects private by default. Check project ownership in every read, write, download, worker, and callback path.
- Show a credit estimate and relevant limits before a paid generation. Reserve atomically, settle once, and release/refund through an auditable ledger path.
- Do not claim fake progress. Show provider-backed progress when available and understandable stage/status otherwise.
- Prefer existing components and architecture. No microservices, extra databases, competing queues, or generic framework layers without a concrete requirement.
- Use existing icon libraries for controls. Use Lottie sparingly for meaningful onboarding/completion feedback, with reduced-motion support; never animate every icon or imply progress that is not real.

## V2 architecture — preserve these boundaries

| Concern | V2 owner and boundary |
|---|---|
| Product/generation API | FastAPI in `backend/` |
| Product data | PostgreSQL `core` schema; backend Alembic owns its migrations |
| Authentication | Next.js/Better Auth in `frontend/` |
| Auth data | PostgreSQL `auth` schema; Prisma owns only auth migrations/models |
| Durable provider inference | Fal queue/webhooks; do not add another AI-generation queue |
| Application post-processing | Existing Redis/ARQ jobs/workers |
| Media | Private S3 storage; persist application-owned asset metadata and final outputs |
| Local services | `backend/docker-compose.yml`; PostgreSQL host 5432, API host 8001; frontend host 3001 per current project setup |

The schemas may share one PostgreSQL database while retaining separate ownership and migration histories. Do not port V1's Prisma-owned generation tables or V1 `PolarOrder` model. Translate only useful concepts into V2's `core` credit ledger, webhook-event records, generation state, upload route, and existing project/result pages.

## Current V2 inventory and evidence

This is a repository-oriented snapshot, not an exhaustive security audit. Re-check code and runtime before treating any item as done.

| Area | Present in V2 | Remaining verification/work |
|---|---|---|
| API and services | FastAPI router groups for account, admin, brand kits, credits, exports, generations, health, media, models, productions, projects, uploads, webhooks, workflows | Confirm every route is registered, authenticated as intended, documented, and covered by contract/integration checks |
| Generation | Typed generation states, model catalog/pricing, provider abstraction, retries/fallback, generation attempts, credit reservation/refund services | Verify state transitions under duplicate/out-of-order callbacks, concurrent submissions, provider outages, and worker restart |
| Credits | `core.credit_transaction`, reservation/charge/refund/reconciliation services | Prove all generation paths use one atomic ledger flow; reconcile provider invoice/cost evidence; ensure no double debit/refund |
| Callbacks | Fal signature verification, replay tolerance, webhook event model/idempotency; Modal callback path exists | Verify signature/replay tests and callback-to-job/user mapping; verify durable dedupe and behavior on retries in deployed provider configuration |
| Uploads/storage | Authenticated presign route, configured content-type allowlist and size constraints, S3 service | Verify object ownership, actual file-content checks where practical, private ACL, upload completion/abandonment cleanup, signed download expiry, and deletion lifecycle |
| Project library | Projects, productions, shots, assets, brand kits, exports, generation/detail pages and frontend routes | Verify complete list/detail/search/status filters, empty/error states, ownership, export/download behavior, and responsive accessibility |
| Production orchestration | Production plan, tasks/dependencies, budget/ledger, generation attempts, render jobs, scheduler/worker and reconciliation code | Validate dependency ordering, cancellation, partial failure, resumability, concurrency limits, leases and idempotent recovery end to end |
| Observability | Health/readiness, Prometheus metrics, scheduler/reconciliation and provider health models | Verify production alerts, dashboards, sensitive-data redaction, runbooks, retention, backup/restore, and alert ownership |
| Auth/account | Better Auth + Prisma `auth` schema; account/credits/portal pages and API | Verify email delivery/verification, recovery, session lifecycle, account export/deletion, billing history, and production origin/cookie/security configuration |
| Provider economics | Catalog capabilities, price/cost-source metadata, provider-cost reconciliation | Verify live Fal/Modal price and commercial-use terms, unit economics, cost alerts, and no unsupported model options exposed to users |

### Confirmed local migration state (reported and inspected during this work)

- Alembic revisions `0001_generation_platform` through `0014_widen_varchar32_columns` are restored in `backend/alembic/versions`; Docker history reports one head at `0014`.
- The local V2 Docker database reported `core.alembic_version = 0014_widen_varchar32_columns`; Alembic `current` agreed.
- A read-only table listing showed the expected 26 `core` tables, including credit, generation, project, production, provider-cost, webhook, render and asset families.
- Prisma `migrate deploy` reported no pending migrations and `migrate status` reported the local `auth` schema up to date (one migration found).
- These checks establish local migration alignment only. They do not verify the backup dump, hosted database, production credentials, provider event delivery, RLS behavior under production roles, or restore procedure.
- Revisions `0003`–`0014` were recovered from the V2 stash as individual files. Keep the stash intact until the recovery is reviewed and safely committed by the repository owner.
- V2 backend source compiles successfully inside the running API image (`python -m compileall -q app`), and the API health endpoint remains healthy. Two concrete frontend type errors were fixed in the ResizeObserver guard and authenticated S3 download helper; a full frontend `tsc --noEmit` run remains unverified because the local TypeScript process did not complete within the available verification window.
- Final local verification: Alembic `current` and `heads` both report `0014_widen_varchar32_columns`; backend readiness reports database and Redis `ok`; backend compilation passes; targeted frontend formatting passes. The working tree still contains broad pre-existing/uncommitted V2 work, so no release gate is closed by this check alone.
- Full frontend `npm run typecheck` completed successfully. The production build compiled successfully but failed during lint with existing code-quality errors across legacy/current UI files; two low-risk errors in the active generation/project/page changes were corrected and formatted. The remaining lint findings are recorded as a release blocker rather than hidden by weakening lint rules.
- The existing backend virtualenv ran the full pytest suite successfully: `27 passed in 29.90s`. Deleted integration tests were not restored because they are user changes and require a deliberate decision about their dedicated database fixtures.

## User journeys and page behavior

### Public entry and authentication

Routes include the landing pages, `/auth/[authView]`, `/account/[accountView]`, and Better Auth API route. A visitor learns what the studio can produce, creates/signs into an account, verifies email as required, then reaches a useful studio screen. Ensure sign-in return paths are safe, errors are readable, and recovery works without exposing account data.

### Studio and generation discovery

`/dashboard`, `/generations`, `/generations/[id]`, and `/projects` are the primary discovery/review surfaces. Users should be able to find prior work by project/title/status/type/date, see the next action, retry only when safe, and distinguish a generation from a multi-scene production. Search and filters must be server-side and user-scoped when result volume warrants it.

### Simple generation

Create route or tool page → select/validate inputs → choose only supported settings → show cost/limits → confirm → reserve credits → provider job → status/result → export/download. Preserve source assets; generated output is a separate versioned asset. Every failure should say whether credits were released and offer a safe next action.

### Storyboard/movie production

Project brief → review/edit plan → approve budget → create production → execute dependency-aware scene tasks → review shots and versions → render → review final output → export aspect/platform variants → download. Users must be able to resume or retry failed steps without losing approved scenes or paying twice. Advanced DAG/budget details belong in focused production views, not on the ordinary creation path.

### Credits and account

`/credits`, `/customer-portal`, account pages, and account API should show current balance, purchase/usage history, pending reservations where useful, receipts/portal access, and support actions. Never mix estimate, reserved, charged, released, and refunded amounts into an unexplained number.

### Admin and support

Keep admin functions narrowly authorized and auditable. Support tooling should expose safe operational metadata first. Any cross-user inspection must be privileged, reasoned, time-bounded where possible, and audited; do not add enterprise roles or a broad admin platform without product need.

## Route and service map to maintain

### Frontend routes present in the current tree

- Public/auth: landing route group, `/auth/[authView]`, `/account/[accountView]`, `/api/auth/[...all]`.
- Main studio: `/dashboard`, `/create` and its tool routes (`ads`, `audio-replace`, `avatar`, `dubbing`, `image-to-image`, `image-to-video`, `podcast`, `presentation`, `product-video`, `shorts`, `text-to-image`, `text-to-video`, `translate`, `url-to-video`, `youtube`), `/generations`, `/generations/[id]`, `/projects`, `/projects/[id]`, `/brand-kits`, `/credits`, `/customer-portal`.
- Internal handlers: `/api/fal` and `/api/inngest` exist in the frontend tree; verify whether any are legacy/active in V2 because V2 backend documentation assigns Fal callback ownership to FastAPI.

### FastAPI router groups present

`/health`, `/account`, `/admin`, `/brand-kits`, `/credits`, `/exports`, `/generations`, `/media`, `/models`, `/productions`, `/projects`, `/uploads`, `/webhooks`, `/workflows` (prefixes depend on `main.py` and `api_prefix`). Treat `main.py` and OpenAPI in the running V2 service as authoritative; generate/update the exact endpoint/method inventory when route work is undertaken.

### Service/worker responsibilities

- `GenerationService` and provider registry: validate, price, reserve, choose provider/model, submit, and record provider IDs/attempts.
- Credit service/repository: atomic reserve, charge, release/refund, idempotency, and auditable ledger.
- Webhook handlers: verify signatures and replay window, map provider events to the correct request, deduplicate, and invoke idempotent state changes.
- Upload/storage services: authorize, constrain, presign, persist metadata, import/validate outputs, and clean up lifecycle artifacts.
- Production/movie orchestration: persist plans, budgets, dependency tasks, scene versions, renders, and exports; recover from partial failure without duplicating cost.
- Workers/scheduler: process IDs only, reload authoritative ownership/status, use bounded retries and leases, emit safe failure codes, and reconcile abandoned work.

## Data model and database rules

Use existing tables first. Current V2 migrations define model catalog, user-owned generations and credits, projects/shots/characters, assets/brand kits, productions/plans/budgets/tasks/dependencies, generation attempts, render jobs/exports/content variants, entitlements, provider health/cost records, captions, and webhook events.

Required invariants:

- Monetary/provider costs use fixed precision and explicit currency/source; user credits are integer ledger units with an auditable conversion/pricing version.
- Idempotency keys and provider event/request IDs have appropriate unique constraints; webhook retries cannot duplicate side effects.
- User-owned rows are scoped by authenticated identity and protected by RLS where configured. System jobs use explicit narrowly scoped system context.
- Migrations are append-only after use in shared environments. Review generated SQL and downgrade/forward strategy; never reset a database to hide drift.
- Alembic owns `core`; Prisma owns `auth`. Verify both histories separately against the same target.
- Before any hosted migration, positively identify the environment, inspect its revision, make a recoverable backup/branch, test the migration against a copy, apply only the pending revisions, and verify schema and application behavior.

## Production release gates

No gate is marked complete merely because implementation code exists. Record evidence beside each gate in this roadmap.

### P0 — Money, jobs, and trust boundaries

- [ ] Every generation path performs atomic credit reservation and exactly-once charge/release/refund under concurrency, retries, cancellation, and duplicate callbacks.
- [ ] Fal and Modal callbacks authenticate as configured, reject stale/replayed/unknown events, map to the expected request, and persist idempotent event outcomes.
- [ ] Generation/production transitions are validated; retries are bounded; workers recover leases/stuck jobs; terminal jobs cannot reserve or charge again.
- [ ] Every project, generation, asset, export, callback, and download is owner-scoped; RLS is tested under the actual application role and explicit system context.
- [ ] Uploads and outputs are private, constrained by purpose/type/size/duration, safely imported, and cleaned up when abandoned/deleted.
- [ ] Polar products, prices, webhook secret/signature, receipts, cancellations/refunds, credit reconciliation, production origin, and callback URLs are verified in the intended production environment before real paid actions are enabled.

### P1 — User workflow

- [ ] New user can sign up, verify/recover account, create a project/generation, see honest status/cost, review output, and download it without learning internal provider details.
- [ ] Storyboard plan and budget can be reviewed before execution; scene retries/version history preserve approved work; production can resume after worker/provider interruption.
- [ ] Project/generation lists have useful search/filter/sort/paging, clear status and next action, accessible empty/error/loading states, and responsive behavior.
- [ ] Credit, purchase, usage, and export history is understandable; account security, deletion/export, and support routes work.
- [ ] Frontend and backend agree on request/response contracts; no stale frontend callback path bypasses backend webhook validation.

### P2 — Operability and economics

- [ ] Production config/secrets are documented and validated; no development keys/defaults run in production.
- [ ] Queue age, generation outcomes, provider latency/failure/cost, webhook lag, stuck tasks, storage growth, and ledger drift are observable with actionable alerts and an owner.
- [ ] Backups include database and required media metadata; restore has been tested; retention/deletion policy and incident runbooks are usable.
- [ ] Provider model availability, commercial rights, current cost, margin assumptions, rate limits, and output constraints are verified before enabling choices for users.
- [ ] Production migrations have staging evidence, rollback/forward-recovery guidance, and verified deployed schema/version.
- [ ] Accessibility, keyboard use, contrast, reduced motion, and mobile layout are checked on the core creation, project, and result flows.

## Delivery order — continue until no in-scope work remains

### Phase 0 — Reconcile the V2 baseline (local evidence mostly collected)

1. Preserve current working tree and V2 stash; no broad stash operations.
2. Verify Alembic `0001`–`0014` history and current local DB revision (observed at `0014`), verify Prisma auth status, and keep `core`/`auth` ownership separate. **Local observations above are documented; hosted DB remains unverified.**
3. Reconcile `backend/alembic.ini` fallback URL with documented `DATABASE_URL` config so future operators are not misled; do not print secrets.
4. Run V2-focused tests and inspect the current uncommitted tree, including deleted integration tests and deleted `backend/app/jobs/media.py`; determine whether deletions are intentional and whether required behavior/tests were lost.
5. Preserve a known-good backup and document restore steps for the local/hosted target before any migration change.

### Phase 1 — Prove generation and credit safety

1. Trace every generation type from frontend action → FastAPI route → service → ledger → provider → callback → worker → final asset.
2. Add/repair tests for concurrent reservation, duplicate idempotency key, duplicate/out-of-order callback, provider submission failure, worker crash, cancellation, and refund/settlement exactly once.
3. Verify Fal and Modal callback trust, payload bounds, event dedupe, ownership, and safe logging.
4. Ensure model costs and credit estimate shown in UI match backend price source/version and supported model capabilities.
5. Keep real billing/generation gated until the production provider credentials, products, webhook delivery, refund policy, and reconciliation are verified.

### Phase 2 — Prove media and production orchestration

1. Verify upload presign authorization, MIME/size policy, object key ownership, upload completion, and file-content/media-probe checks where appropriate.
2. Verify private S3 access, short-lived preview/download, output import constraints, abandoned upload cleanup, user deletion, and storage retention.
3. Exercise production dependency graph, budget reserve/settle/release, per-scene retry/version preservation, render/export, cancellation, worker restart, and scheduler reconciliation.
4. Add focused regression coverage for every confirmed gap; avoid rebuilding existing abstractions that already satisfy the behavior.

### Phase 3 — Finish the studio workflow and account experience

1. Verify landing → auth → dashboard → create → progress → result → download for each supported generation mode.
2. Finish project/generation library search and useful filters, pagination, status presentation, rename/delete/archive where supported, and robust empty/error states.
3. Finish credits/history/purchase and customer portal states; account recovery/deletion/export; ensure purchase history uses V2 `auth`/backend contracts rather than V1 Prisma schema assumptions.
4. Review mobile, keyboard, accessibility, reduced motion, and remove confusing or internal UI details.

### Phase 4 — Production operations and release

1. Verify production environment variables, secret storage, callback URLs, CORS/origins, TLS, rate limits, and database role privileges.
2. Set up dashboards/alerts/runbooks for provider outages, queue backlogs, webhook failures, stuck productions, credit reconciliation, storage, and DB restore.
3. Test database/media backup and restore; document retention, deletion, incident and support procedures.
4. Stage and verify migrations against a copy of the intended hosted database; apply only with known target and recoverability; verify deployed Alembic and Prisma histories separately.
5. Run backend test suite, integration checks with dedicated databases, frontend lint/typecheck/build, and browser verification against only V2 backend `http://localhost:8001` and frontend `http://localhost:3001`. Report failures with classification; do not hide them.
6. Mark release gates complete only when evidence exists. If external provider/legal/business choices remain, complete all independent work, leave live money-moving actions fail-closed, and state exact required inputs.

## External decisions that must not be guessed

- Production legal entity, launch country/currency, tax treatment, Polar product configuration, and whether checkout/purchases are enabled.
- Production S3/CDN account, retention requirements, and allowed provider/model commercial rights.
- Any additional payment rails or provider beyond the existing Polar credit purchase setup.

Agents must continue all work that does not require these decisions and must never invent credentials or enable production money movement as a workaround.

## Competitor workflow references

Use these as workflow references, not UI or brand templates:

- Pictory idea/script to video: https://kb.pictory.ai/en/articles/10971729-how-to-turn-your-ideas-into-a-video-script-and-video
- Pictory text-to-video: https://pictory.ai/text-to-video-generator
- Pictory script-to-video: https://pictory.ai/pictory-features/script-to-video

## Skills and working method

- **Superpowers brainstorming/writing-plans:** scope multi-step work and define safe, reviewable slices before implementation.
- **TDD:** prove behavior with focused tests, especially around money, callbacks, ownership, and retries.
- **Ponytail + Karpathy Guidelines:** reuse V2 code, make the smallest complete change, and defer speculative subsystems.
- **UI/UX Pro Max:** use for actual frontend design/implementation; keep clear task hierarchy, search, accessibility, and responsive behavior.
- Use focused security, debugging, animation, or review skills only when they directly apply. Do not run every skill for appearance.

## Change log / evidence updates

- **2026-11-06:** Added a non-destructive V2 account export at `GET /api/v1/account/export`, plus the authenticated frontend download route `/api/account/export` and a Credits-page link. The export is owner-scoped through the existing RLS/session dependency, includes product-side projects, generations, assets, brand kits, balance, and credit ledger, and excludes prompts/metadata/output URLs, credentials, sessions, passwords, and signed media URLs. Focused serialization coverage passes. Account deletion remains disabled pending an explicit retention/refund/legal policy; Better Auth's destructive delete cannot safely remove V2 core rows or private media without that decision.
- **2026-11-06:** Full V2 backend suite after the export change passes (`38 passed, 4 skipped in 34.26s`); frontend typecheck and lint pass with only the existing image/polling warnings. The restarted V2 frontend on port 3001 returned `200` for `/api/auth/get-session` and `401` for unauthenticated `/api/account/export`; a fresh `next build` did not complete within 90 seconds in this Windows worktree and was stopped, so the prior successful build evidence remains valid for the pre-export tree but this export route still needs a clean production-build run.

- **2026-11-05:** Recovered the four deleted integration-test behaviors under new files in `backend/tests/integration_recovered/` without restoring or overwriting the originals. Against the isolated `backend/docker-compose.test.yml` database, Alembic now reaches `0014` after two fresh-chain fixes: revision `0011` executes its literal JSON SQL without SQLAlchemy bind parsing, and revision `0013` widens `core.alembic_version.version_num` before recording its 33-character revision. With a dedicated non-superuser `vividgen_test_app` role, all four replacement tests pass (`4 passed in 31.21s`), covering credit races, duplicate Fal callbacks, RLS isolation/system context, and postprocessing worker-crash recovery. The test containers were then stopped; the development stack was not reset or altered.
- **2026-11-05:** Added production configuration validation that fails closed for missing metrics tokens, non-HTTPS public/callback origins, unsafe CORS, missing Fal credentials, and missing Modal webhook secret when Modal is configured. Focused config/storage tests pass (`8 passed`, then `7 passed`); full backend suite passes `37 passed, 4 skipped in 67.26s`. Added narrow `delete_object` storage behavior that allows only V2 `uploads/` and `generations/` prefixes and propagates AWS `AccessDenied`.
- **2026-11-05:** Added client-side project search and status filtering with accessible labels in `frontend/src/components/projects/projects-list.tsx`. Frontend typecheck and lint pass; lint retains only existing image optimization and polling dependency warnings. The supplied ngrok URL reaches the V2 Fal path: an invalid POST returned `401`; the health GET shows ngrok's free interstitial (`ERR_NGROK_6024`) rather than a backend health response, so it is not treated as a production endpoint or used for provider configuration.
- **2026-11-05:** Final frontend `npm run build` completed successfully after the project-library change, generated all 45 routes, and exited 0. Only the previously documented non-blocking lint warnings remain.
- **2026-11-05:** The supplied `vivid-gen-backend.zip` contains `modal_app/` as a directory entry but no Modal worker source file; the checkout has only `backend/modal_app/__pycache__/wan_worker.cpython-311.pyc`. The worker's deployed signing behavior and secret storage therefore remain unverifiable from V2 source/history, while backend HMAC verification and local tests remain verified.

- **2026-11-04:** Added server-only `BETTER_AUTH_SECRET` validation and passed it to `betterAuth({ secret })`; added validated `POLAR_SERVER` with sandbox default and documented empty `BETTER_AUTH_SECRET`/sandbox placeholder values in `frontend/.env.example`. With the existing local secret, the frontend build completed without Better Auth default-secret errors, and the V2 frontend smoke checks returned 200 for `/`, `/auth/sign-in`, and `/api/auth/get-session` on port 3001.
- **2026-11-04:** Added focused provider verifier coverage: Modal exact-body/timestamp HMAC, stale/missing-secret rejection, and Fal Ed25519 body-hash/stale rejection (`3 passed`). The configured backend routes are `/api/v1/webhooks/fal` and `/api/v1/webhooks/modal`; Polar Better Auth exposes its webhook endpoint at `/api/auth/polar/webhooks` (verified from the installed plugin, POST-only). Ngrok is not installed, so no live inbound tunnel tests were attempted. The checkout contains no deployable Modal worker source, only compiled bytecode; remote signing/configuration remains unverified.
- **2026-11-04:** Existing S3 configuration allowed one isolated probe upload and a one-second V2 presigned download; an unsigned request returned HTTP 403. Cleanup of the probe object was denied with `AccessDenied`, so the required missing permission is `s3:DeleteObject` for the probe prefix (no policy was changed). Backend ownership code scopes presigned keys to `uploads/{user_id}/` or `generations/{user_id}/`; cross-user API verification remains blocked while the backend database stack is stopped.
- **2026-11-04:** Local Polar product IDs and credit amounts are not present in the backend `.env` (backend settings therefore expose empty product IDs/default amounts), so no sandbox purchase was run. Production checkout remains disabled; sandbox product setup and duplicate/refund reconciliation still require configured test products and a reachable backend/database.
- **2026-11-04:** Frontend `npm run lint` passes with only the previously documented image-optimization and polling dependency warnings. No new lint errors were introduced by the auth/Polar changes.
- **2026-11-04:** Docker became available without intervention; V2 `/health/live` and `/health/ready` returned 200 with database and Redis healthy. Full backend pytest then passed `30 passed in 34.49s`; invalid POSTs to both V2 webhook routes returned 401. The isolated upload presign route returned 200 with a user-scoped key for an allowed image type, while a cross-user download request returned 403. `tests/integration` currently collects no tests because the four integration files remain deleted user changes.
- **2026-11-04:** The installed Polar Better Auth webhook route accepted a POST request at `/api/auth/polar/webhooks` and rejected an unsigned empty payload with 400, confirming the configured route without exercising a purchase or exposing provider credentials.

- **2026-11-04:** Added `backend/docs/OPERATIONS_RUNBOOK.md` with fail-closed incident, backup/restore, queue/callback, storage-retention, and required-production-input procedures. This documents the operational path; it does not claim that hosted alerts, backups, or provider configuration have been verified.

- **2026-11-04:** Frontend lint was rerun after focused cleanup of unused imports/props and unsafe timer callbacks. It completes successfully with only non-blocking image optimization notices and two intentional polling dependency notices; no correctness lint errors remain. `npx tsc --noEmit --pretty false` also completed successfully. `npm run build` completed successfully, generated all 45 routes, and exited 0; its static collection logs still report Better Auth's default-secret error, so a real `BETTER_AUTH_SECRET` remains a production configuration requirement.
- **2026-11-04:** Backend `..\\.venv\\Scripts\\python.exe -m pytest -q` was rerun while Docker was unavailable: 26 tests passed and one HTTP privilege test failed because Redis/PostgreSQL connections were refused. This is an environment availability failure, not evidence of a regression; the full suite previously passed 27 tests with the local stack running. No database or migration was changed. `docker info` currently cannot connect to Docker Desktop, and ports 3001/8001 are stopped.
- **2026-11-04:** Backend `compileall` passed. Dedicated integration coverage was not executed because Docker Desktop is unavailable; `backend/docker-compose.test.yml` remains the isolated test-stack definition, and the four deleted integration test files were preserved as-is rather than restored over the user’s working tree.

- **2026-11-01:** V2 migration files `0003`–`0014` restored individually from the existing stash; `alembic history --verbose` shows a single linear chain with `0014` head. Local Docker DB reports `core.alembic_version = 0014`; `alembic current` agrees; 26 `core` tables listed. Frontend `prisma migrate deploy` reported no pending migrations and `migrate status` reported the single auth migration up to date. No hosted database was verified in this step.
- **2026-11-01:** V2 working tree includes substantial uncommitted implementation work across backend/frontend. Presence is not equivalent to passing tests or production readiness; audit and verify before marking individual gates done.
