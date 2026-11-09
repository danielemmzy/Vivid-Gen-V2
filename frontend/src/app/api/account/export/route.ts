import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "~/lib/auth";
import { backendFetch } from "~/lib/backend";

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json(
      { error: "Authentication required" },
      { status: 401 },
    );
  }

  const productData = await backendFetch<Record<string, unknown>>(
    session.user.id,
    "/account/export",
    { method: "GET" },
  );
  const exportData = {
    ...productData,
    account: {
      id: session.user.id,
      name: session.user.name,
      email: session.user.email,
      email_verified: session.user.emailVerified,
      created_at: session.user.createdAt,
    },
  };

  return new NextResponse(JSON.stringify(exportData, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Disposition":
        'attachment; filename="vivid-gen-account-export.json"',
      "Cache-Control": "no-store",
    },
  });
}
