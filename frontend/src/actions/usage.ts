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

export interface UsageSummary {
  period_start: string;
  video_seconds_used: number;
  generations_counted: number;
  active_generations: number;
  plan_key: string;
  plan_label: string;
  monthly_video_seconds_limit: number;
  remaining_video_seconds: number;
  max_concurrent_generations: number;
  max_project_duration_seconds: number;
  credits_balance: number;
  credit_usd_value: number;
}

export async function getUsageSummary() {
  const uid = await userId();
  return backendFetch<UsageSummary>(uid, "/account/usage", { method: "GET" });
}
