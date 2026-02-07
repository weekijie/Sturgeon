import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    // Forward the multipart form data directly to the backend
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: "No image file provided" },
        { status: 400 }
      );
    }

    // Rebuild FormData for the backend (Next.js may alter the original)
    const backendForm = new FormData();
    backendForm.append("file", file);

    const response = await fetch(`${BACKEND_URL}/analyze-image`, {
      method: "POST",
      body: backendForm,
      // Don't set Content-Type — fetch auto-sets multipart boundary
    });

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: "Backend error", details: error },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Analyze-image API error:", error);
    return NextResponse.json(
      { error: "Failed to connect to AI service" },
      { status: 500 }
    );
  }
}
