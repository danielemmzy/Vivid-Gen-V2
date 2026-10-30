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

export interface StockMediaResult {
  external_id: string;
  preview_url: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  license: string;
  attribution: string;
  content_type: string;
}

export async function searchStockMedia(input: { query: string; kind: "image" | "video"; orientation?: "landscape" | "portrait" | "square"; limit?: number }) {
  const uid = await userId();
  return backendFetch<{ provider: string; query: string; kind: "image" | "video"; results: StockMediaResult[]; count: number }>(uid, "/media/search", {
    method: "POST", body: JSON.stringify({ ...input, provider: "pexels", limit: input.limit ?? 8 }),
  });
}

export async function importStockMedia(input: { query: string; external_id: string; kind: "image" | "video"; orientation?: "landscape" | "portrait" | "square" }) {
  const uid = await userId();
  return backendFetch<{ s3_key: string; kind: "image" | "video"; content_type: string; license: string; attribution: string; provider: string; external_id: string; width: number | null; height: number | null; duration_seconds: number | null }>(uid, "/media/import-stock", {
    method: "POST", body: JSON.stringify({ ...input, provider: "pexels" }),
  });
}
