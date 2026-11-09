"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";
import type { ProductionPlan } from "~/actions/director";
import type { GenerationResult } from "~/actions/generation";

async function userId() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return session.user.id;
}

type PlanResult = {
  project_id: string;
  status: string;
  production_plan: ProductionPlan;
};
type ClipsResult = {
  project_id: string;
  clips: {
    id: string;
    s3_key: string;
    duration_seconds: number;
    metadata: Record<string, unknown>;
  }[];
};
export type UrlArticlePreview = {
  url: string;
  title: string | null;
  description: string | null;
  article_text: string;
  word_count: number;
  visual_candidates: number;
};

// POST /workflows/ads — verified in backend/app/routers/workflows.py + workflows/ads.py
export async function createAdWorkflow(input: {
  product_name: string;
  product_description: string;
  audience?: string;
  goal?: string;
  platform?: string;
  style?: string;
  duration_seconds?: number;
  language?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/ads", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/product-video
export async function createProductVideoWorkflow(input: {
  product_name: string;
  product_description: string;
  features?: string[];
  duration_seconds?: number;
  language?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/product-video", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/youtube
export async function createYoutubeWorkflow(input: {
  topic: string;
  duration_seconds?: number;
  style?: string;
  audience?: string;
  language?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/youtube", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/url-to-video/preview — read-only source review before planning
export async function previewUrlToVideoArticle(input: { url: string }) {
  const uid = await userId();
  return backendFetch<UrlArticlePreview>(
    uid,
    "/workflows/url-to-video/preview",
    { method: "POST", body: JSON.stringify(input) },
  );
}

// POST /workflows/url-to-video — real article extraction on the backend
export async function createUrlToVideoWorkflow(input: {
  url: string;
  duration_seconds?: number;
  style?: string;
  language?: string;
  article_text?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/url-to-video", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/podcast — real transcription on the backend
export async function createPodcastWorkflow(input: {
  audio_s3_key: string;
  duration_seconds?: number;
  style?: string;
  language?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/podcast", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/presentation — real .pptx text extraction on the backend
export async function createPresentationWorkflow(input: {
  pptx_s3_key: string;
  duration_seconds?: number;
  style?: string;
  language?: string;
}) {
  const uid = await userId();
  return backendFetch<PlanResult>(uid, "/workflows/presentation", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/shorts — real transcribe + highlight-detect + trim/reframe pipeline
export async function createShortsWorkflow(input: {
  source_video_s3_key: string;
  max_clips?: number;
}) {
  const uid = await userId();
  return backendFetch<ClipsResult>(uid, "/workflows/shorts", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// POST /workflows/repurpose/{project_id} — Shorts pipeline against an already-completed project
export async function repurposeAsShorts(projectId: string, maxClips?: number) {
  const uid = await userId();
  return backendFetch<ClipsResult>(uid, `/workflows/repurpose/${projectId}`, {
    method: "POST",
    body: JSON.stringify({ max_clips: maxClips ?? 5 }),
  });
}

// POST /workflows/dubbing — submits directly to the existing, already-working
// video-translation generation (see backend/app/workflows/dubbing.py for why
// this deliberately doesn't build a new pipeline).
export async function createDubbingWorkflow(input: {
  source_video_s3_key: string;
  target_language: string;
  lip_sync?: boolean;
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/workflows/dubbing", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
