-- One-time manual migration: move existing auth tables from `public` into
-- a dedicated `auth` schema, and drop the three legacy generation tables
-- now that FastAPI's `core.generation` table is the single source of
-- truth (see architecture plan Decision 1 & 2).
--
-- Run this once, by hand, against the existing database BEFORE running
-- `prisma db push` / `prisma migrate deploy` with the updated schema.prisma.
-- Prisma's migration engine does not move existing tables between
-- schemas automatically — it will try to create fresh tables in `auth`
-- and leave your data behind in `public` if you skip this step.
--
-- BACK UP YOUR DATABASE BEFORE RUNNING THIS.

BEGIN;

CREATE SCHEMA IF NOT EXISTS auth;

ALTER TABLE IF EXISTS public."user" SET SCHEMA auth;
ALTER TABLE IF EXISTS public."session" SET SCHEMA auth;
ALTER TABLE IF EXISTS public."account" SET SCHEMA auth;
ALTER TABLE IF EXISTS public."verification" SET SCHEMA auth;

-- Legacy generation tables — data here should already have been backfilled
-- into FastAPI's core.generation table by a one-off script before this
-- runs (see architecture plan Phase 0). Dropping, not archiving, on the
-- assumption that backfill already happened; change to a RENAME instead
-- of DROP if you want a safety copy for one release cycle.
DROP TABLE IF EXISTS public."PhotoToVideoGeneration";
DROP TABLE IF EXISTS public."VideoTranslationGeneration";
DROP TABLE IF EXISTS public."ChangeVideoAudioGeneration";

COMMIT;
