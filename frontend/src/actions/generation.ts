"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";

async function userId() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return session.user.id;
}

export async function getPresignedUrl(fileName: string, fileType: string, purpose: string) {
  const uid = await userId();
  return backendFetch<{ url: string; key: string }>(uid, "/uploads/presign", {
    method: "POST",
    body: JSON.stringify({ file_name: fileName, content_type: fileType, purpose }),
  });
}

export interface GenerationResult {
  id: string;
  status: string;
  type: string;
  model_id: string;
  credits_reserved: number;
  credits_charged: number;
  estimated_provider_cost_usd: number;
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
  resolution: string;
}

export async function photoToVideo(request: GenerateRequest) {
  const uid = await userId();
  if (!request.audioS3Key) {
    return backendFetch<GenerationResult>(uid, "/generations/image-to-video", {
      method: "POST",
      body: JSON.stringify({
        prompt: request.script || "Cinematic natural camera movement and subtle subject motion",
        input_s3_key: request.photoS3Key,
        model: "kling-2.5-turbo-pro-i2v",
        duration_seconds: 5,
        resolution: request.resolution === "1080" ? "1080p" : "720p",
      }),
    });
  }
  return backendFetch<GenerationResult>(uid, "/generations/avatar", {
    method: "POST",
    body: JSON.stringify({
      image_s3_key: request.photoS3Key,
      audio_s3_key: request.audioS3Key,
      resolution: request.resolution === "1080" ? "1080p" : "720p",
    }),
  });
}

export async function textToImage(request: { prompt: string; model?: string; aspect_ratio?: string; num_images?: number }) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/text-to-image", { method: "POST", body: JSON.stringify(request) });
}

export async function imageToImage(request: { prompt: string; input_s3_key: string; model?: string }) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/image-to-image", { method: "POST", body: JSON.stringify(request) });
}

export async function textToVideo(request: { prompt: string; model?: string; duration_seconds?: number; resolution?: string; aspect_ratio?: string }) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/text-to-video", { method: "POST", body: JSON.stringify(request) });
}

export async function imageToVideo(request: { prompt: string; input_s3_key: string; model?: string; duration_seconds?: number; resolution?: string }) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/image-to-video", { method: "POST", body: JSON.stringify(request) });
}

export async function getGeneration(id: string) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, `/generations/${id}`, { method: "GET" });
}

export async function listGenerations(limit = 50, offset = 0) {
  const uid = await userId();
  return backendFetch<{ generations: GenerationResult[]; limit: number; offset: number }>(
    uid,
    `/generations?limit=${limit}&offset=${offset}`,
    { method: "GET" },
  );
}

export interface TranslateRequest {
  sourceVideoS3Key: string;
  targetLanguage: string;
  lipSync?: boolean;
}

export async function translateVideo(request: TranslateRequest) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/video-translation", {
    method: "POST",
    body: JSON.stringify({
      video_s3_key: request.sourceVideoS3Key,
      target_language: request.targetLanguage,
      lip_sync: request.lipSync ?? true,
    }),
  });
}

export interface ChangeVideoAudioRequest {
  sourceVideoS3Key: string;
  newAudioS3Key: string;
  videoName: string;
}

export async function changeVideoAudio(request: ChangeVideoAudioRequest) {
  const uid = await userId();
  return backendFetch<GenerationResult>(uid, "/generations/audio-replace", {
    method: "POST",
    body: JSON.stringify({
      video_s3_key: request.sourceVideoS3Key,
      audio_s3_key: request.newAudioS3Key,
    }),
  });
}
