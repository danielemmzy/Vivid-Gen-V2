"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";

/**
 * Renaming used to write directly to three legacy Prisma tables
 * (PhotoToVideoGeneration / VideoTranslationGeneration /
 * ChangeVideoAudioGeneration). Those tables are gone — FastAPI's
 * `core.generation` table is the single source of truth for every
 * generation type now (see architecture plan Decision 1), so this just
 * calls its rename endpoint instead of touching Prisma.
 */
export async function updateCreationName(id: string, name: string) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/auth/sign-in");

  await backendFetch(session.user.id, `/generations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title: name }),
  });

  revalidatePath("/");
}
