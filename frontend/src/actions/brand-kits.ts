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

// Matches backend/app/routers/brand_kits.py's _dict() exactly.
export interface BrandKit {
  id: string;
  name: string;
  logo_url: string | null;
  watermark_url: string | null;
  default_music_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  font_family: string | null;
  caption_style: string;
  cta_text: string | null;
  voice_id: string | null;
  // gap-closure: these existed on the model since migration 0003 but
  // were never accepted by the create/update API until this pass — see
  // backend/app/routers/brand_kits.py.
  intro_asset_id: string | null;
  outro_asset_id: string | null;
}

export async function listBrandKits() {
  const uid = await userId();
  return backendFetch<{ brand_kits: BrandKit[] }>(uid, "/brand-kits", { method: "GET" });
}

export async function createBrandKit(input: {
  name: string;
  logo_s3_key?: string;
  watermark_s3_key?: string;
  default_music_s3_key?: string;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  caption_style?: string;
  cta_text?: string;
  voice_id?: string;
}) {
  const uid = await userId();
  const result = await backendFetch<BrandKit>(uid, "/brand-kits", { method: "POST", body: JSON.stringify(input) });
  revalidatePath("/brand-kits");
  return result;
}

// DELETE /brand-kits/{id} — gap-closure: previously there was no way to
// delete a brand kit through the API at all.
export async function deleteBrandKit(id: string) {
  const uid = await userId();
  const result = await backendFetch<{ deleted: boolean }>(uid, `/brand-kits/${id}`, { method: "DELETE" });
  revalidatePath("/brand-kits");
  return result;
}
