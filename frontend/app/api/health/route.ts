import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const HEALTH_TIMEOUT_MS = 5000;

export const runtime = "nodejs";
export const maxDuration = 15;

export async function GET() {
  try {
    const signal = AbortSignal.timeout(HEALTH_TIMEOUT_MS);
    const response = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      signal,
    });

    if (!response.ok) {
      return NextResponse.json(
        { status: "error", message: "Backend unavailable" },
        { status: 503 }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { status: "error", message: "Failed to connect to backend" },
      { status: 503 }
    );
  }
}
