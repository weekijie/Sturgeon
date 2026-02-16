import { NextRequest, NextResponse } from "next/server";
import { copyRateLimitHeaders } from "../utils";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// 2-minute timeout for debate turns (backend has 90s timeout + overhead)
const DEBATE_TIMEOUT_MS = 120000;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/debate-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(DEBATE_TIMEOUT_MS),
    });

    // Prepare headers with rate limit info
    const headers = new Headers();
    copyRateLimitHeaders(response.headers, headers);

    if (!response.ok) {
      // Parse backend error — FastAPI returns { detail: "..." }
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
    // Handle timeout specifically
    if (error instanceof Error && error.name === "TimeoutError") {
      console.error("Debate turn timeout after", DEBATE_TIMEOUT_MS, "ms");
      return NextResponse.json(
        { error: "Request timed out. The AI is processing a complex case. Please try again with a simpler query." },
        { status: 504 }
      );
    }
    console.error("Debate turn API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
