"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";

export interface CatalogModel {
  id: string;
  // Which backend GenerationProvider handles this model — "fal" today,
  // "modal" (self-hosted) once that provider exists. Not yet used for
  // anything in the UI (no per-provider behavior needed yet), but the
  // type now matches the real backend response instead of silently
  // omitting a field the API actually sends.
  provider: string;
  quality_tier?: "economy" | "standard" | "premium";
  provider_model_id: string;
  name: string;
  type: string;
  unit: "second" | "minute" | "image" | "flat";
  price: number;
  max_resolution: string | null;
  supports_movie_shots: boolean;
  credits_per_unit: number;
  provider_configured: boolean;
  cost_estimate_basis: string;
  example_estimate_credits?: number;
  capabilities: {
    input_type?: string;
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
    pricing_strategy?: string;
    cost_estimate_basis?: string;
  };
}

// GET /models — verified in backend/app/routers/models.py. Public catalog,
// no per-user data, but still routed through the authenticated backendFetch
// helper since that's the only client this app has for the FastAPI service.
export async function getModelCatalog() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return backendFetch<{ models: CatalogModel[] }>(session.user.id, "/models", { method: "GET" });
}

export interface ProductionEstimate {
  generation_type: "text_to_video" | "image_to_video";
  target_duration_seconds: number;
  model_id: string;
  model_name: string;
  provider: string;
  provider_model_id: string;
  quality_tier: string;
  resolution: "420p" | "720p";
  max_shot_duration_seconds: number;
  shot_count: number;
  scene_count_estimate: number;
  billable_generation_seconds: number;
  estimated_provider_cost_usd: number;
  credits_to_reserve: number;
  credit_usd_value: number;
  pricing_strategy: string;
  cost_estimate_basis: string;
  cost_rate_version: string | null;
  capabilities: Record<string, unknown>;
  included: string[];
  excluded: string[];
  note: string;
}

export async function estimateProduction(input: {
  generation_type: "text_to_video" | "image_to_video";
  target_duration_seconds: number;
  quality_mode: "low" | "medium" | "high";
  model_id?: string;
  resolution: "420p" | "720p";
  aspect_ratio: string;
}) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return backendFetch<ProductionEstimate>(session.user.id, "/models/estimate-production", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
