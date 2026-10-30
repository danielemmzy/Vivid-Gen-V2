"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";

async function userId() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return session.user.id;
}

// gap-closure (0007): the Production domain — previously a production
// run was implicit (Project.status + a JSON blob in
// Project.metadata_json), ProductionTask (round 2) was a flat list with
// no real dependency graph, and there was no budget ledger or per-
// attempt generation history. See backend/app/models/production.py and
// backend/app/orchestration/{dag,scheduler}.py.

export interface ProductionResult {
  id: string;
  project_id: string;
  status: string;
  planning_status: string;
  execution_status: string;
  production_type: string;
  plan_version: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string | null;
}

export interface ProductionTaskResult {
  id: string;
  type: string;
  scene_number: number | null;
  status: string;
  shot_id: string | null;
  render_job_id: string | null;
  error: string | null;
  output_json: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProductionTaskEdge {
  upstream_task_id: string;
  downstream_task_id: string;
}

export interface ProductionBudgetResult {
  id: string;
  status: string;
  currency: string;
  estimated_credits: number;
  reserved_credits: number;
  consumed_credits: number;
  refunded_credits: number;
  budget_profile: "short_form" | "long_form";
  max_shots: number;
  max_retries_per_shot: number;
}

export interface ProductionBudgetLedgerEntry {
  id: string;
  type: string;
  amount: number;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string | null;
}

export interface GenerationAttemptResult {
  id: string;
  generation_id: string;
  production_task_id: string | null;
  attempt_number: number;
  provider: string | null;
  model_id: string | null;
  status: string;
  estimated_cost_usd: number | null;
  actual_cost_usd: number | null;
  failure_type: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export async function listProductionsForProject(projectId: string) {
  const uid = await userId();
  return backendFetch<{ productions: ProductionResult[] }>(uid, `/projects/${projectId}/productions`, { method: "GET" });
}

export async function getProduction(productionId: string) {
  const uid = await userId();
  return backendFetch<ProductionResult>(uid, `/productions/${productionId}`, { method: "GET" });
}

export async function getProductionDag(productionId: string) {
  const uid = await userId();
  return backendFetch<{ tasks: ProductionTaskResult[]; edges: ProductionTaskEdge[] }>(uid, `/productions/${productionId}/dag`, { method: "GET" });
}

export async function getProductionBudget(productionId: string) {
  const uid = await userId();
  return backendFetch<{ budget: ProductionBudgetResult | null; ledger: ProductionBudgetLedgerEntry[] }>(uid, `/productions/${productionId}/budget`, { method: "GET" });
}

export async function getProductionAttempts(productionId: string) {
  const uid = await userId();
  return backendFetch<{ attempts: GenerationAttemptResult[] }>(uid, `/productions/${productionId}/attempts`, { method: "GET" });
}

export async function cancelProductionById(productionId: string) {
  const uid = await userId();
  const result = await backendFetch<ProductionResult>(uid, `/productions/${productionId}/cancel`, { method: "POST" });
  revalidatePath(`/projects/${result.project_id}`);
  return result;
}

export async function resumeProduction(productionId: string, shotId?: string) {
  const uid = await userId();
  const result = await backendFetch<{
    production_id: string; resumed: boolean; retried_shot_ids: string[];
    tasks_enqueued: number; preserved_completed_shots: string[];
  }>(uid, `/productions/${productionId}/resume`, {
    method: "POST", body: JSON.stringify(shotId ? { shot_id: shotId } : {}),
  });
  revalidatePath(`/projects`);
  return result;
}
