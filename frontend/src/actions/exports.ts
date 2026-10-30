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

// gap-closure: this whole file — Content Factory previously had zero
// lines of frontend or backend code. See backend/app/services/export/
// service.py for exactly what this does and does not do (mechanical
// aspect-ratio variants + a listable Export record — not per-platform
// titles/descriptions/thumbnails).

export type ExportPlatform = "youtube" | "tiktok" | "instagram_reels" | "instagram_feed" | "facebook" | "master";
export type ExportAspectRatio = "16:9" | "9:16" | "1:1" | "4:5";

export interface ExportResult {
  id: string;
  project_id: string;
  platform: string;
  aspect_ratio: string;
  status: string;
  error: string | null;
  download_url: string | null;
  created_at: string | null;
}

export async function listExports(projectId: string) {
  const uid = await userId();
  return backendFetch<{ exports: ExportResult[] }>(uid, `/projects/${projectId}/exports`, { method: "GET" });
}

export async function createExport(projectId: string, platform: ExportPlatform, aspectRatio: ExportAspectRatio) {
  const uid = await userId();
  const result = await backendFetch<ExportResult>(uid, `/projects/${projectId}/exports`, {
    method: "POST",
    body: JSON.stringify({ platform, aspect_ratio: aspectRatio }),
  });
  revalidatePath(`/projects/${projectId}`);
  return result;
}
