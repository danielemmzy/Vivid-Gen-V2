import { createHmac } from "crypto";
import { env } from "~/env";

/**
 * `role` is signed into the HMAC alongside user_id/timestamp — see
 * backend/app/core/security.py's docstring for why: an unsigned role
 * header would let a compromised or buggy route hand a user an "admin"
 * claim the backend has no way to detect as tampered. `role` must come
 * from the session's own DB-backed User.role field (see prisma/schema.prisma),
 * never from anything the caller of backendFetch supplies directly.
 */
function internalHeaders(userId: string, role: string) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signature = createHmac("sha256", env.BACKEND_INTERNAL_SECRET)
    .update(`${userId}:${timestamp}:${role}`)
    .digest("hex");
  return {
    "Content-Type": "application/json",
    "X-Vivid-User-ID": userId,
    "X-Vivid-Timestamp": timestamp,
    "X-Vivid-Role": role,
    "X-Vivid-Signature": signature,
  };
}

export async function backendFetch<T>(
  userId: string,
  path: string,
  init: RequestInit = {},
  role = "user",
): Promise<T> {
  const response = await fetch(`${env.BACKEND_API_URL.replace(/\/$/, "")}/api/v1${path}`, {
    ...init,
    headers: { ...internalHeaders(userId, role), ...(init.headers ?? {}) },
    cache: "no-store",
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof body?.detail === "string" ? body.detail : (body?.detail?.message ?? body?.error?.message ?? "Backend request failed");
    throw new Error(message);
  }
  return body as T;
}
