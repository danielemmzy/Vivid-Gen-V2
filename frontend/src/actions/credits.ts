"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";
import { env } from "~/env";

async function userId() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");
  return session.user.id;
}

export interface CreditBalance {
  credits: number;
  credit_usd_value: number;
}

export interface CreditTransaction {
  id: string;
  type: string;
  amount: number;
  balance_before: number;
  balance_after: number;
  description: string | null;
  created_at: string;
}

// GET /credits/balance — verified in backend/app/routers/credits.py
export async function getCreditBalance() {
  const uid = await userId();
  return backendFetch<CreditBalance>(uid, "/credits/balance", { method: "GET" });
}

// GET /credits/transactions — verified in backend/app/routers/credits.py
export async function getCreditTransactions() {
  const uid = await userId();
  return backendFetch<{ transactions: CreditTransaction[] }>(uid, "/credits/transactions", { method: "GET" });
}


export interface CreditPackage {
  key: "small" | "medium" | "large";
  title: string;
  product_id: string;
  credits: number;
  price_usd: number;
}

export async function getCreditPackages() {
  const uid = await userId();
  const result = await backendFetch<{ configured: boolean; packages: CreditPackage[]; message: string | null }>(uid, "/credits/packages", { method: "GET" });
  const frontendIds = new Set([env.NEXT_PUBLIC_SMALL_CREDIT_ID, env.NEXT_PUBLIC_MEDIUM_CREDIT_ID, env.NEXT_PUBLIC_LARGE_CREDIT_ID]);
  const packages = result.packages.filter((item) => item.product_id && frontendIds.has(item.product_id));
  return { configured: result.configured && packages.length === 3, packages, message: result.configured && packages.length === 3 ? null : "Credit top-ups are unavailable until the frontend and backend Polar product IDs match. No checkout will be opened." };
}
