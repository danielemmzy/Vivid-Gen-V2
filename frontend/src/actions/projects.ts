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

// This is the "movie"/storyboard feature — verified in
// backend/app/routers/projects.py + services/movie/service.py. It is NOT a
// generic folder/asset organizer: a project has characters (reference-image
// identity sheets) and shots (individual generations), and gets assembled
// into a final video.

import type { ProductionPlan } from "~/actions/director";

export interface Project {
  id: string;
  title: string;
  description: string | null;
  status: string;
  aspect_ratio: string;
  resolution: string;
  output_url: string | null;
  error_message: string | null;
  // V2: set once POST /projects/{id}/plan has been called — see actions/director.ts
  production_plan: ProductionPlan | null;
  // gap-closure (0007): points at this project's most recent Production
  // run — see actions/productions.ts for the full Production/DAG/
  // budget/attempts surface. Not the source of truth for history (a
  // project can have multiple productions) but is what the UI polls.
  current_production_id: string | null;
  editor_timeline?: EditorTimeline | null;
}

export interface Shot {
  id: string;
  order_index: number;
  scene_number?: number | null;
  status: string;
  prompt: string;
  camera_notes: string | null;
  duration_seconds: number;
  timeline_duration_seconds?: number | null;
  character_ids: string[];
  generation_id: string | null;
  // V2 (B08): past generation_ids for this shot, oldest first
  generation_history: string[];
  reference_shot_id?: string | null;
  product_id?: string | null;
  continuity_mode?: string;
}

export interface Character {
  id: string;
  name: string;
  locked_version: number;
  reference_urls: string[];
  voice_id: string | null;
}

export interface EditorAsset {
  id: string;
  type: string;
  source?: string;
  mime_type: string | null;
  source_generation_id?: string | null;
  scene_number?: number | null;
  duration_seconds: number | null;
  file_name: string;
  url: string;
}

export interface EditorTimeline {
  version: 1;
  clips: Array<{
    id: string;
    shotId: string;
    title: string;
    prompt: string;
    duration: number;
    trimStart: number;
    trimEnd: number;
    transition: "none" | "fade" | "dissolve" | "wipe";
    volume: number;
    muted: boolean;
  }>;
  textLayers: Array<{
    id: string;
    text: string;
    start: number;
    duration: number;
    style: "title" | "caption" | "label";
  }>;
  audioLayers: Array<{
    id: string;
    name: string;
    assetId: string | null;
    start: number;
    duration: number;
    volume: number;
    kind: "music" | "voice" | "sfx";
    loop?: boolean;
  }>;
  aspectRatio: string;
  zoom: number;
  selectedId: string | null;
}

export async function getProjectAssetUploadUrl(
  fileName: string,
  mimeType: string,
) {
  const uid = await userId();
  return backendFetch<{ url: string; key: string }>(uid, "/uploads/presign", {
    method: "POST",
    body: JSON.stringify({
      file_name: fileName,
      content_type: mimeType,
      purpose: uid,
    }),
  });
}

export async function listProjectAssets(projectId: string) {
  const uid = await userId();
  return backendFetch<{ assets: EditorAsset[] }>(
    uid,
    `/projects/${projectId}/assets`,
    { method: "GET" },
  );
}

export async function registerProjectAsset(
  projectId: string,
  input: {
    key: string;
    file_name: string;
    mime_type: string;
    duration_seconds?: number | null;
  },
) {
  const uid = await userId();
  return backendFetch<{ asset: EditorAsset }>(
    uid,
    `/projects/${projectId}/assets`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function saveEditorTimeline(
  projectId: string,
  timeline: EditorTimeline,
) {
  const uid = await userId();
  const result = await backendFetch<{
    saved: boolean;
    editor_timeline: EditorTimeline;
  }>(uid, `/projects/${projectId}/editor-timeline`, {
    method: "PUT",
    body: JSON.stringify({ timeline }),
  });
  revalidatePath(`/projects/${projectId}`);
  return result;
}

export async function renderEditorTimeline(projectId: string) {
  const uid = await userId();
  const result = await backendFetch<{
    queued: boolean;
    production_id: string;
    message: string;
  }>(uid, `/projects/${projectId}/render-editor`, { method: "POST" });
  revalidatePath(`/projects/${projectId}`);
  return result;
}

export async function listProjects() {
  const uid = await userId();
  return backendFetch<{ projects: Project[] }>(uid, "/projects", {
    method: "GET",
  });
}

export async function getProject(id: string) {
  const uid = await userId();
  return backendFetch<Project & { shots: Shot[]; characters: Character[] }>(
    uid,
    `/projects/${id}`,
    { method: "GET" },
  );
}

export async function createProject(input: {
  title: string;
  description?: string;
  aspect_ratio?: string;
  resolution?: string;
}) {
  const uid = await userId();
  const result = await backendFetch<Project>(uid, "/projects", {
    method: "POST",
    body: JSON.stringify({
      title: input.title,
      description: input.description,
      aspect_ratio: input.aspect_ratio ?? "16:9",
      resolution: input.resolution ?? "1080p",
    }),
  });
  revalidatePath("/projects");
  return result;
}

export async function createCharacter(
  projectId: string,
  input: {
    name: string;
    description?: string;
    reference_s3_keys: string[];
    voice_id?: string;
  },
) {
  const uid = await userId();
  const result = await backendFetch<Character>(
    uid,
    `/projects/${projectId}/characters`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

export async function addShot(
  projectId: string,
  input: {
    prompt: string;
    camera_notes?: string;
    duration_seconds?: number;
    character_ids?: string[];
    model_id?: string;
  },
) {
  const uid = await userId();
  const result = await backendFetch<Shot>(uid, `/projects/${projectId}/shots`, {
    method: "POST",
    body: JSON.stringify({ duration_seconds: 5, character_ids: [], ...input }),
  });
  revalidatePath(`/projects/${projectId}`);
  return result;
}

export async function submitShot(projectId: string, shotId: string) {
  const uid = await userId();
  const result = await backendFetch<Shot>(
    uid,
    `/projects/${projectId}/shots/${shotId}/submit`,
    {
      method: "POST",
    },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

// POST /projects/{id}/shots/{shot_id}/regenerate — V2 (B08): a new attempt
// at this shot, keeping the previous one in history rather than losing it.
export async function regenerateShot(
  projectId: string,
  shotId: string,
  prompt?: string,
) {
  const uid = await userId();
  const result = await backendFetch<Shot>(
    uid,
    `/projects/${projectId}/shots/${shotId}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify({ prompt: prompt ?? null }),
    },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

// POST /projects/{id}/shots/{shot_id}/select-version
export async function selectShotVersion(
  projectId: string,
  shotId: string,
  generationId: string,
) {
  const uid = await userId();
  const result = await backendFetch<Shot>(
    uid,
    `/projects/${projectId}/shots/${shotId}/select-version`,
    {
      method: "POST",
      body: JSON.stringify({ generation_id: generationId }),
    },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

// POST /projects/{id}/cancel — gap-closure: previously there was no way
// to cancel an in-flight project anywhere in the API. See
// backend/app/services/movie/service.py::MovieService.cancel_project.
export async function cancelProject(projectId: string) {
  const uid = await userId();
  const result = await backendFetch<Project>(
    uid,
    `/projects/${projectId}/cancel`,
    { method: "POST" },
  );
  revalidatePath(`/projects/${projectId}`);
  return result;
}

export interface RenderJob {
  id: string;
  status: string;
  progress_percent: number;
  current_step: string | null;
  attempt: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// GET /projects/{id}/render-job — gap-closure: previously the only render
// observability was Project.status (a 3-value string). See
// backend/app/models/render_job.py.
export async function getLatestRenderJob(projectId: string) {
  const uid = await userId();
  return backendFetch<{ render_job: RenderJob | null }>(
    uid,
    `/projects/${projectId}/render-job`,
    { method: "GET" },
  );
}
