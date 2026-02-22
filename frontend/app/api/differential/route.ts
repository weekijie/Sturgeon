import { NextRequest, NextResponse } from "next/server";
import { copyRateLimitHeaders } from "../utils";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const TIMEOUT_MS = 295000; // allow queue + retry path without premature frontend timeout

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/differential`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    // Prepare headers with rate limit info
    const headers = new Headers();
    copyRateLimitHeaders(response.headers, headers);

    if (!response.ok) {
      let detail = "Backend error";
      try {
        const errBody = await response.json();
        detail = errBody.detail || JSON.stringify(errBody);
      } catch {
        detail = await response.text();
      }
      return NextResponse.json(
        { error: "Backend error", detail },
        { status: response.status, headers }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return NextResponse.json(
        { error: "Request timed out. Please try again." },
        { status: 504 }
      );
    }
    console.error("Differential API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
