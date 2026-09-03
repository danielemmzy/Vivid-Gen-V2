import { NextResponse } from "next/server";
export async function POST() {
  return NextResponse.json({ error: "fal webhooks are handled by the FastAPI backend" }, { status: 410 });
}
