"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Spinner, Chip } from "@heroui/react";
import { useCase, ImageAnalysis } from "./context/CaseContext";
import Prose from "../components/Prose";

// Helper: is the file an image?
function isImageFile(file: File): boolean {
  return file.type.startsWith("image/");
}

// Helper: read file as data URL for preview
function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Component: Expandable text with "Read More" toggle
function ExpandableText({ text, previewLength = 400 }: { text: string; previewLength?: number }) {
  const [expanded, setExpanded] = useState(false);
  const needsExpansion = text.length > previewLength;

  return (
    <div>
      <div className={`text-sm leading-relaxed ${!expanded && needsExpansion ? "max-h-48 overflow-hidden relative" : ""}`}>
        {expanded || !needsExpansion ? (
          <Prose content={text} />
        ) : (
          <>
            <Prose content={text.slice(0, previewLength) + "..."} />
            <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white to-transparent" />
          </>
        )}
      </div>
      {needsExpansion && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
          className="text-xs text-teal hover:text-teal/80 mt-2 font-semibold px-3 py-1 rounded-full bg-teal-light/50 hover:bg-teal-light transition-colors"
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

export default function UploadPage() {
  const router = useRouter();
  const { setPatientHistory, setDifferential, setImageAnalysis } = useCase();

  const [file, setFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [patientHistory, setPatientHistoryLocal] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState<string>("");
  const [imageResult, setImageResult] = useState<ImageAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
      setImageResult(null);
      if (isImageFile(droppedFile)) {
        const url = await readAsDataUrl(droppedFile);
        setImagePreview(url);
      } else {
        setImagePreview(null);
      }
    }
  }, []);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) {
        setFile(selectedFile);
        setImageResult(null);
        if (isImageFile(selectedFile)) {
          const url = await readAsDataUrl(selectedFile);
          setImagePreview(url);
        } else {
          setImagePreview(null);
        }
      }
    },
    [],
  );

  const clearFile = useCallback(() => {
    setFile(null);
    setImagePreview(null);
    setImageResult(null);
  }, []);

  const handleAnalyze = async () => {
    if (!file && !patientHistory.trim()) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      let imgAnalysis: ImageAnalysis | null = null;
      let enrichedHistory = patientHistory;

      // Step 1: If image file, analyze it first
      if (file && isImageFile(file)) {
        setAnalysisStep("Analyzing image with MedSigLIP + MedGemma...");

        const formData = new FormData();
        formData.append("file", file);

        const imageResponse = await fetch("/api/analyze-image", {
          method: "POST",
          body: formData,
        });

        if (!imageResponse.ok) {
          const errData = await imageResponse.json().catch(() => ({}));
          throw new Error(
            errData.details || errData.error || "Image analysis failed",
          );
        }

        imgAnalysis = await imageResponse.json();
        setImageResult(imgAnalysis);

        // Store in context
        if (imgAnalysis && imagePreview) {
          setImageAnalysis(imgAnalysis, imagePreview);
        }

        // Enrich patient history with image findings for the differential
        const imageContext = [
          `\n\n--- Medical Image Analysis ---`,
          `Image type: ${imgAnalysis!.image_type}`,
          `Modality: ${imgAnalysis!.modality}`,
          imgAnalysis!.triage_summary,
          `\nDetailed Interpretation:\n${imgAnalysis!.medgemma_analysis}`,
        ].join("\n");

        enrichedHistory = patientHistory
          ? `${patientHistory}\n${imageContext}`
          : imageContext;
      }

      // Step 2: Generate differential diagnosis
      setAnalysisStep("Generating differential diagnosis...");

      const response = await fetch("/api/differential", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_history: enrichedHistory,
          lab_values: {},
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(
          errData.detail ||
            "Failed to generate differential. Please try again.",
        );
      }

      const data = await response.json();

      // Store in context
      setPatientHistory(enrichedHistory);
      setDifferential(data.diagnoses);

      // Navigate to debate page
      router.push("/debate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsAnalyzing(false);
      setAnalysisStep("");
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-6 pt-8">
      <div className="w-full max-w-2xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold tracking-tight text-foreground">
            <span className="text-teal">Sturgeon</span>
          </h1>
          <p className="text-muted text-lg">
            Diagnostic Debate AI — Challenge the diagnosis
          </p>
        </div>

        {/* Upload Card */}
        <Card className="p-0 bg-white border border-border shadow-sm">
          {/* Card Header */}
          <div className="p-6 pb-0">
            <h2 className="text-xl font-semibold text-foreground">Upload Evidence</h2>
            <p className="text-muted text-sm mt-1">
              Upload medical images (X-ray, dermatology, pathology) or provide
              patient history
            </p>
          </div>

          {/* Card Content */}
          <div className="p-6 space-y-6">
            {/* Drop Zone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`
                relative border-2 border-dashed rounded-xl p-8 text-center
                transition-all duration-200 cursor-pointer
                ${
                  isDragging
                    ? "border-teal bg-teal-light/30"
                    : "border-border hover:border-teal/50 hover:bg-surface"
                }
                ${file ? "border-success bg-green-50" : ""}
              `}
            >
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.txt"
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
              />

              {file ? (
                <div className="space-y-3">
                  {/* Image preview */}
                  {imagePreview && (
                    <div className="flex justify-center">
                      <img
                        src={imagePreview}
                        alt="Medical image preview"
                        className="max-h-48 rounded-lg border border-border object-contain"
                      />
                    </div>
                  )}
                  <div className="flex items-center justify-center gap-2">
                    <div className="text-success text-lg">&#10003;</div>
                    <p className="font-medium text-foreground">{file.name}</p>
                    <Chip size="sm" variant="flat">
                      {(file.size / 1024).toFixed(1)} KB
                    </Chip>
                    {isImageFile(file) && (
                      <Chip size="sm" variant="flat" color="secondary">
                        Medical Image
                      </Chip>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      clearFile();
                    }}
                    className="relative z-20 text-sm text-muted hover:text-danger transition-colors"
                  >
                    Remove file
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Clean SVG upload icon */}
                  <div className="flex justify-center">
                    <svg className="w-12 h-12 text-muted/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                    </svg>
                  </div>
                  <p className="font-medium text-foreground">
                    Drop medical image or report here
                  </p>
                  <p className="text-sm text-muted">
                    Chest X-ray, dermatology photo, pathology slide, or text
                    report
                  </p>
                </div>
              )}
            </div>

            {/* Image Analysis Results */}
            {imageResult && (
              <div className="rounded-xl border border-border bg-white p-4 space-y-3 border-l-4 border-l-teal">
                {/* Section: MedSigLIP Triage */}
                {imageResult.triage_findings.length > 0 && (
                  <div>
                    <h3 className="font-semibold text-sm text-foreground mb-2">Image Analysis</h3>
                    <p className="text-xs text-muted mb-1.5">MedSigLIP Triage Findings:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {imageResult.triage_findings.slice(0, 5).map((f, i) => (
                        <Chip
                          key={i}
                          size="sm"
                          variant="flat"
                          color={f.score > 0.3 ? "warning" : "default"}
                        >
                          {f.label} ({(f.score * 100).toFixed(0)}%)
                        </Chip>
                      ))}
                    </div>
                  </div>
                )}

                {/* Divider */}
                {imageResult.triage_findings.length > 0 && (
                  <div className="border-t border-border" />
                )}

                {/* Section: Clinical Interpretation */}
                <div>
                  <h3 className="font-semibold text-sm text-foreground mb-2">Clinical Interpretation</h3>
                  <ExpandableText text={imageResult.medgemma_analysis} />
                </div>
              </div>
            )}

            {/* Patient History */}
            <div className="space-y-2">
              <label htmlFor="patient-history" className="text-sm font-medium text-foreground">
                Patient History{" "}
                {file && isImageFile(file)
                  ? "(Optional — enhances analysis)"
                  : "(Required)"}
              </label>
              <textarea
                id="patient-history"
                placeholder="Enter relevant patient history, symptoms, medications, previous diagnoses..."
                rows={4}
                value={patientHistory}
                onChange={(e) => setPatientHistoryLocal(e.target.value)}
                className="w-full rounded-lg bg-white border border-border px-4 py-3 text-sm text-foreground placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-teal/40 focus:border-teal resize-none transition-colors"
              />
            </div>

            {/* Error Message */}
            {error && (
              <div className="text-danger text-sm bg-red-50 border border-red-200 p-3 rounded-lg">
                {error}
              </div>
            )}
          </div>

          {/* Card Footer */}
          <div className="p-6 pt-0 flex flex-col items-end gap-2">
            <Button
              variant="solid"
              onPress={handleAnalyze}
              isDisabled={(!file && !patientHistory.trim()) || isAnalyzing}
              className="min-w-[200px] font-semibold bg-teal text-white hover:bg-teal/90 rounded-lg px-6 py-2.5 text-sm transition-colors"
            >
              {isAnalyzing ? (
                <>
                  <Spinner size="sm" color="white" />
                  Analyzing...
                </>
              ) : (
                "Analyze & Begin Debate"
              )}
            </Button>
            {isAnalyzing && analysisStep && (
              <p className="text-xs text-muted">{analysisStep}</p>
            )}
          </div>
        </Card>

        {/* Footer hint */}
        <p className="text-center text-sm text-muted">
          Powered by MedGemma + MedSigLIP — For educational purposes only
        </p>
      </div>
    </main>
  );
}
