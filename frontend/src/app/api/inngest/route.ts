import { NextResponse } from "next/server";
export async function GET() { return NextResponse.json({ error: "Generation queue moved to fal.ai" }, { status: 410 }); }
export async function POST() { return NextResponse.json({ error: "Generation queue moved to fal.ai" }, { status: 410 }); }
