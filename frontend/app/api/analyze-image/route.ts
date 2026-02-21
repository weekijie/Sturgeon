import { NextRequest, NextResponse } from "next/server";
import { copyRateLimitHeaders } from "../utils";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const TIMEOUT_MS = 180000; // 3 minutes for image analysis (MedSigLIP + MedGemma pipeline)

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: "No image file provided" },
        { status: 400 }
      );
    }

    const backendForm = new FormData();
    backendForm.append("file", file);

    const response = await fetch(`${BACKEND_URL}/analyze-image`, {
      method: "POST",
      body: backendForm,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!response.ok) {
      const error = await response.text();
      const headers = new Headers();
      copyRateLimitHeaders(response.headers, headers);

      return NextResponse.json(
        { error: "Backend error", details: error },
        { status: response.status, headers }
      );
    }

    const data = await response.json();
    
    // Pass through rate limit headers
    const headers = new Headers();
    copyRateLimitHeaders(response.headers, headers);
    
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return NextResponse.json(
        { error: "Image analysis timed out. Please try again." },
        { status: 504 }
      );
    }
    console.error("Analyze-image API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
