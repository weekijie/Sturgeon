import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    // Forward the multipart form data to the backend /extract-labs-file endpoint
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: "No file provided" },
        { status: 400 }
      );
    }

    // Rebuild FormData for the backend
    const backendForm = new FormData();
    backendForm.append("file", file);

    const response = await fetch(`${BACKEND_URL}/extract-labs-file`, {
      method: "POST",
      body: backendForm,
      // Don't set Content-Type — fetch auto-sets multipart boundary
    });

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
        { error: "Backend error", details: errorMessage },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Extract-labs API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
