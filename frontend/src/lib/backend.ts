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

export class BackendError extends Error {
  code?: string;
  details?: Record<string, unknown>;
  status: number;
  constructor(message: string, code: string | undefined, details: Record<string, unknown> | undefined, status: number) {
    super(message);
    this.name = "BackendError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
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
  const raw = await response.text();
  let body: any = null;
  if (raw.trim()) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = { detail: raw.slice(0, 2000) };
    }
  }
  if (!response.ok) {
    const message = typeof body?.detail === "string"
      ? body.detail
      : (body?.detail?.message ?? body?.error?.message ?? body?.message ?? `Backend request failed (${response.status})`);
    const details = (body?.error ?? body?.details ?? undefined) as Record<string, unknown> | undefined;
    const code = body?.error?.code ?? body?.code ?? undefined;
    throw new BackendError(message, code, details, response.status);
  }
  return body as T;
}
