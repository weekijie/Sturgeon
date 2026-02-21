import { NextRequest, NextResponse } from "next/server";
import { copyRateLimitHeaders } from "../utils";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const TIMEOUT_MS = 120000; // 2 minutes for lab extraction

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: "No file provided" },
        { status: 400 }
      );
    }

    const backendForm = new FormData();
    backendForm.append("file", file);

    const response = await fetch(`${BACKEND_URL}/extract-labs-file`, {
      method: "POST",
      body: backendForm,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    // Prepare headers with rate limit info
    const headers = new Headers();
    copyRateLimitHeaders(response.headers, headers);

    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage = errorText;
      try {
        const parsed = JSON.parse(errorText);
        errorMessage = parsed.detail || parsed.message || errorText;
      } catch {
        // Not JSON — use raw text as-is
      }
      return NextResponse.json(
        { error: "Backend error", detail: errorMessage },
        { status: response.status, headers }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return NextResponse.json(
        { error: "Lab extraction timed out. Please try again." },
        { status: 504 }
      );
    }
    console.error("Extract-labs API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
