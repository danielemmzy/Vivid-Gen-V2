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

export async function getPresignedUrl(
  fileName: string,
  fileType: string,
  purpose: string,
) {
  const uid = await userId();
  return backendFetch<{ url: string; key: string }>(uid, "/uploads/presign", {
    method: "POST",
    body: JSON.stringify({
      file_name: fileName,
      content_type: fileType,
      purpose,
    }),
  });
}

export interface GenerationResult {
  id: string;
  status: string;
  type: string;
  model_id: string;
  duration_seconds: number | null;
  resolution: string | null;
  aspect_ratio: string | null;
  title: string | null;
  credits_reserved: number;
  credits_charged: number;
  estimated_provider_cost_usd: number;
  // gap-closure: previously these two backend fields existed but the
  // frontend type didn't even declare them — see
  // backend/app/schemas/generation.py::GenerationResponse.
  actual_provider_cost_usd: number | null;
  actual_cost_source: string | null;
  retry_count: number;
  output_url: string | null;
  thumbnail_url: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
}

export interface GenerateRequest {
  photoS3Key: string;
  script?: string;
  audioS3Key?: string | null;
  voiceS3Key?: string | null;
  expressiveness?: number;
  enhancement: boolean;
  experimentalModel: boolean;
  quality_mode?: "low" | "medium" | "high";
  resolution: string;
  audioDurationSeconds?: number;
  model?: string;
}

export async function photoToVideo(request: GenerateRequest) {
  const uid = await userId();
  if (!request.audioS3Key) {
    return backendFetch<GenerationResult>(uid, "/generations/image-to-video", {
      method: "POST",
      body: JSON.stringify({
        prompt:
          request.script ??
          "Cinematic natural camera movement and subtle subject motion",
        input_s3_key: request.photoS3Key,
        model: request.model,
        quality_mode: request.quality_mode ?? "medium",
        duration_seconds: 5,
        resolution: request.model?.startsWith("kling-2.5")
          ? undefined
          : request.resolution === "1080"
            ? "1080p"
            : "720p",
      }),
    });
  }
  return backendFetch<GenerationResult>(uid, "/generations/avatar", {
    method: "POST",
    body: JSON.stringify({
      image_s3_key: request.photoS3Key,
      audio_s3_key: request.audioS3Key,
      model: request.model,
      duration_seconds: request.audioDurationSeconds,
    }),
  });
}

export async function textToImage(request: {
  prompt: string;
  model?: string;
  quality_mode?: "low" | "medium" | "high";
  aspect_ratio?: string;
  num_images?: number;
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/text-to-image", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function imageToImage(request: {
  prompt: string;
  input_s3_key: string;
  model?: string;
  quality_mode?: "low" | "medium" | "high";
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/image-to-image", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface GenerationEstimate {
  generation_type: string;
  model_id: string;
  model_name: string;
  provider: string;
  provider_model_id: string;
  quality_tier: string;
  duration_seconds: number | null;
  resolution: string | null;
  estimated_provider_cost_usd: number;
  estimated_reservation_cost_usd: number;
  credits_to_reserve: number;
  credit_usd_value: number;
  pricing_strategy: string;
  cost_estimate_basis: string;
  cost_rate_version: string | null;
  capabilities: {
    resolutions: string[];
    duration_options: number[];
    aspect_ratios: string[];
    audio_input: boolean;
    audio_output: boolean;
    image_input: boolean;
    movie_shots: boolean;
    resolution_mode?: string;
    provider_resolution?: string;
    output_resolution_mode?: string;
  };
  note?: string | null;
}

export interface GenerationEstimateRequest {
  generation_type:
    | "text_to_video"
    | "image_to_video"
    | "text_to_image"
    | "image_to_image"
    | "avatar"
    | "video_translation"
    | "audio_replace"
    | "text_to_speech";
  model_id?: string | null;
  quality_mode?: "low" | "medium" | "high";
  duration_seconds?: number;
  resolution?: "420p" | "720p";
  aspect_ratio?: string;
  num_images?: number;
}

export async function estimateGeneration(request: GenerationEstimateRequest) {
  const uid = await userId();
  return backendFetch<GenerationEstimate>(uid, "/models/estimate", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function textToVideo(request: {
  prompt: string;
  model?: string;
  quality_mode?: "low" | "medium" | "high";
  duration_seconds?: number;
  resolution?: "420p" | "720p";
  aspect_ratio?: string;
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/text-to-video", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function imageToVideo(request: {
  prompt: string;
  input_s3_key: string;
  model?: string;
  quality_mode?: "low" | "medium" | "high";
  duration_seconds?: number;
  resolution?: "420p" | "720p";
  aspect_ratio?: string;
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/image-to-video", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// POST /generations/avatar — verified in backend/app/schemas/generation.py::AvatarRequest.
// photoToVideo() above also reaches this endpoint as an implicit branch when
// audio is present; this is the explicit, schema-accurate entry point for a
// dedicated Avatar workflow page.
export async function createAvatar(request: {
  image_s3_key: string;
  audio_s3_key: string;
  duration_seconds?: number;
  model?: string;
}) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/avatar", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getGeneration(id: string) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, `/generations/${id}`, {
    method: "GET",
  });
}

// POST /generations/{id}/cancel — gap-closure: previously there was no way
// to cancel a generation anywhere in the API. See
// backend/app/services/generation/service.py::GenerationService.cancel.
export async function cancelGeneration(id: string) {
  const uid = await userId();
  const result = await backendFetch<GenerationResult>(
    uid,
    `/generations/${id}/cancel`,
    { method: "POST" },
  );
  revalidatePath(`/generations/${id}`);
  return result;
}

export async function listGenerations(limit = 50, offset = 0) {
  const uid = await userId();
  return backendFetch<{
    generations: GenerationResult[];
    limit: number;
    offset: number;
  }>(uid, `/generations?limit=${limit}&offset=${offset}`, { method: "GET" });
}

export interface TranslateRequest {
  sourceVideoS3Key: string;
  targetLanguage: string;
  lipSync?: boolean;
  sourceDurationSeconds?: number;
  model?: string;
}

export async function translateVideo(request: TranslateRequest) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/video-translation", {
    method: "POST",
    body: JSON.stringify({
      video_s3_key: request.sourceVideoS3Key,
      target_language: request.targetLanguage,
      lip_sync: request.lipSync ?? true,
      source_duration_seconds: request.sourceDurationSeconds,
      model: request.model,
    }),
  });
}

export interface ChangeVideoAudioRequest {
  sourceVideoS3Key: string;
  newAudioS3Key: string;
  videoName?: string;
  sourceDurationSeconds?: number;
  model?: string;
}

export async function changeVideoAudio(request: ChangeVideoAudioRequest) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/audio-replace", {
    method: "POST",
    body: JSON.stringify({
      video_s3_key: request.sourceVideoS3Key,
      audio_s3_key: request.newAudioS3Key,
      source_duration_seconds: request.sourceDurationSeconds,
      model: request.model ?? "audio-replace",
    }),
  });
}
