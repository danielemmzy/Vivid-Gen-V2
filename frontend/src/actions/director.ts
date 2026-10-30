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

// Matches backend/app/orchestration/production_plan.py exactly — keep in
// sync if that file changes, there is no shared codegen between the two
// repos today.
export interface ScenePlan {
  scene_number: number;
  duration_seconds: number;
  purpose: string;
  visual_type: "generated_video" | "generated_image" | "stock_video" | "stock_image" | "user_asset" | "text_graphic";
  visual_prompt: string;
  voiceover_line: string | null;
  camera_notes: string | null;
  requires_character_reference: boolean;
  requires_product_reference: boolean;
  // gap-closure: previously these two `requires_*_reference` flags had no
  // way to actually be acted on — character_id is what makes them real
  // (executor.py threads it into the actual generation). See
  // backend/app/orchestration/production_plan.py::ScenePlan.
  character_id: string | null;
  source_asset_s3_key: string | null;
  // gap-closure (0006): pragmatic stock-asset substitute — see
  // backend/app/orchestration/asset_fetch.py. Only meaningful for
  // visual_type "stock_video"/"stock_image".
  stock_source_url: string | null;
}

export interface ProductionPlan {
  project_type: string;
  title: string;
  duration_seconds: number;
  aspect_ratio: string;
  resolution: string;
  target_platform: string | null;
  language: string;
  style: string | null;
  audience: string | null;
  goal: string | null;
  quality_mode: "low" | "medium" | "high" | "fast" | "balanced" | "best";
  video_engine?: "auto" | "wan" | "kling";
  script: string | null;
  scenes: ScenePlan[];
  voiceover: { enabled: boolean; style: string | null; voice_id: string | null };
  music: { enabled: boolean; mood: string | null; genre: string | null };
  captions: { enabled: boolean; style: string };
  branding: { enabled: boolean; brand_kit_id: string | null };
}

export interface DirectorProject {
  id: string;
  title: string;
  description: string | null;
  status: string;
  aspect_ratio: string;
  resolution: string;
  output_url: string | null;
  error_message: string | null;
  production_plan: ProductionPlan | null;
}

// POST /projects/{id}/plan — verified in backend/app/routers/projects.py
export async function createPlan(
  projectId: string,
  input: {
    prompt: string;
    project_type?: string;
    duration_seconds?: number;
    aspect_ratio?: string;
    target_platform?: string;
    style?: string;
    audience?: string;
    language?: string;
    source_facts?: string;
  },
) {
  const uid = await userId();
  const result = await backendFetch<DirectorProject>(uid, `/projects/${projectId}/plan`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  revalidatePath(`/projects/${projectId}`);
  return result;
}

// POST /projects/{id}/approve-plan — creates real Shots from the stored
// (or an edited) plan. Still spends no credits.
export async function approvePlan(projectId: string, editedPlan?: ProductionPlan) {
  const uid = await userId();
  const result = await backendFetch<DirectorProject & { shots: unknown[]; skipped_scenes: { scene_number: number; reason: string }[] }>(
    uid, `/projects/${projectId}/approve-plan`,
    { method: "POST", body: JSON.stringify({ plan: editedPlan ?? null }) },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

// POST /projects/{id}/generate — the actual credit-spending step.
export async function generateProject(projectId: string) {
  const uid = await userId();
  const result = await backendFetch<DirectorProject>(uid, `/projects/${projectId}/generate`, { method: "POST" });
  revalidatePath(`/projects/${projectId}`);
  return result;
}
