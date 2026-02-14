"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Chip } from "@heroui/react";
import { useCase, ImageAnalysis, LabResults } from "./context/CaseContext";
import Prose from "../components/Prose";

// Helper: is the file an image?
function isImageFile(file: File): boolean {
  return file.type.startsWith("image/");
}

// Helper: is the file a lab report (PDF or text)?
function isLabFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".pdf") || name.endsWith(".txt");
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
function ExpandableText({
  text,
  previewLength = 400,
}: {
  text: string;
  previewLength?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const needsExpansion = text.length > previewLength;

  return (
    <div>
      <div
        className={`text-sm leading-relaxed ${!expanded && needsExpansion ? "max-h-48 overflow-hidden relative" : ""}`}
      >
        {expanded || !needsExpansion ? (
          <Prose content={text} />
        ) : (
          <>
            <Prose content={text.slice(0, previewLength) + "..."} />
            <div className="absolute bottom-0 left-0 right-0 h-12 bg-linear-to-t from-white to-transparent" />
          </>
        )}
      </div>
      {needsExpansion && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
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
  const {
    setPatientHistory,
    setDifferential,
    setImageAnalysis,
    setLabResults,
  } = useCase();

  // Multi-file state: separate slots for image and lab report
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [labFile, setLabFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [patientHistory, setPatientHistoryLocal] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState<string>("");
  const [imageResult, setImageResult] = useState<ImageAnalysis | null>(null);
  const [labResult, setLabResult] = useState<LabResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasAnyFile = imageFile || labFile;

  // Process incoming files: classify and store in the right slot
  const processFiles = useCallback(async (incoming: FileList) => {
    for (let i = 0; i < incoming.length; i++) {
      const f = incoming[i];
      if (isImageFile(f)) {
        setImageFile(f);
        setImageResult(null);
        const url = await readAsDataUrl(f);
        setImagePreview(url);
      } else if (isLabFile(f)) {
        setLabFile(f);
        setLabResult(null);
      }
      // Unsupported types are silently ignored
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      await processFiles(e.dataTransfer.files);
    },
    [processFiles],
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        await processFiles(e.target.files);
      }
    },
    [processFiles],
  );

  const clearImage = useCallback(() => {
    setImageFile(null);
    setImagePreview(null);
    setImageResult(null);
  }, []);

  const clearLab = useCallback(() => {
    setLabFile(null);
    setLabResult(null);
  }, []);

  const clearAll = useCallback(() => {
    clearImage();
    clearLab();
  }, [clearImage, clearLab]);

  const handleAnalyze = async () => {
    // 1A: Input validation — require at least some evidence
    if (!imageFile && !labFile && !patientHistory.trim()) {
      setError("Please provide at least a patient history or upload evidence (image or lab report) before analyzing.");
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      let enrichedHistory = patientHistory;

      // Step 1: Run image analysis and lab extraction in parallel
      const imagePromise = imageFile
        ? (async () => {
            setAnalysisStep("Analyzing image with MedSigLIP + MedGemma...");
            const formData = new FormData();
            formData.append("file", imageFile);

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

            return (await imageResponse.json()) as ImageAnalysis;
          })()
        : Promise.resolve(null);

      const labPromise = labFile
        ? (async () => {
            if (!imageFile)
              setAnalysisStep("Extracting lab values with MedGemma...");
            const formData = new FormData();
            formData.append("file", labFile);

            const labResponse = await fetch("/api/extract-labs", {
              method: "POST",
              body: formData,
            });

            if (!labResponse.ok) {
              const errData = await labResponse.json().catch(() => ({}));
              throw new Error(
                errData.detail ||
                  errData.details ||
                  errData.error ||
                  "Lab extraction failed",
              );
            }

            return (await labResponse.json()) as LabResults;
          })()
        : Promise.resolve(null);

      // Wait for both to complete
      setAnalysisStep(
        imageFile && labFile
          ? "Analyzing image + extracting lab values..."
          : imageFile
            ? "Analyzing image with MedSigLIP + MedGemma..."
            : "Extracting lab values with MedGemma...",
      );

      const [imgAnalysis, labExtraction] = await Promise.all([
        imagePromise,
        labPromise,
      ]);

      // Process image results
      if (imgAnalysis) {
        setImageResult(imgAnalysis);
        if (imagePreview) {
          setImageAnalysis(imgAnalysis, imagePreview);
        }

        const imageContext = [
          `\n\n--- Medical Image Analysis ---`,
          `Image type: ${imgAnalysis.image_type}`,
          `Modality: ${imgAnalysis.modality}`,
          imgAnalysis.triage_summary,
          `\nDetailed Interpretation:\n${imgAnalysis.medgemma_analysis}`,
        ].join("\n");

        enrichedHistory = patientHistory
          ? `${patientHistory}\n${imageContext}`
          : imageContext;
      }

      // Process lab results
      if (labExtraction) {
        setLabResult(labExtraction);
        setLabResults(labExtraction);
      }

      // Step 2: Generate differential diagnosis
      setAnalysisStep("Generating differential diagnosis...");

      const response = await fetch("/api/differential", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_history: enrichedHistory,
          lab_values: labExtraction?.lab_values ?? {},
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
            <h2 className="text-xl font-semibold text-foreground">
              Upload Evidence
            </h2>
            <p className="text-muted text-sm mt-1">
              Upload medical images, lab reports (PDF/TXT), or provide patient
              history
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
                ${hasAnyFile ? "border-success bg-green-50" : ""}
              `}
            >
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.txt"
                multiple
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
              />

              {hasAnyFile ? (
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

                  {/* File chips */}
                  <div className="flex flex-col items-center gap-2">
                    {/* Image file chip */}
                    {imageFile && (
                      <div className="flex items-center gap-2">
                        <div className="text-success text-lg">&#10003;</div>
                        <p className="font-medium text-foreground text-sm">
                          {imageFile.name}
                        </p>
                        <Chip size="sm" variant="flat">
                          {(imageFile.size / 1024).toFixed(1)} KB
                        </Chip>
                        <Chip size="sm" variant="flat" color="secondary">
                          Medical Image
                        </Chip>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            clearImage();
                          }}
                          className="relative z-20 text-xs text-muted hover:text-danger transition-colors ml-1"
                          title="Remove image"
                        >
                          ✕
                        </button>
                      </div>
                    )}

                    {/* Lab file chip */}
                    {labFile && (
                      <div className="flex items-center gap-2">
                        <div className="text-success text-lg">&#10003;</div>
                        <p className="font-medium text-foreground text-sm">
                          {labFile.name}
                        </p>
                        <Chip size="sm" variant="flat">
                          {(labFile.size / 1024).toFixed(1)} KB
                        </Chip>
                        <Chip size="sm" variant="flat" color="primary">
                          Lab Report
                        </Chip>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            clearLab();
                          }}
                          className="relative z-20 text-xs text-muted hover:text-danger transition-colors ml-1"
                          title="Remove lab report"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Add more / clear all */}
                  <div className="flex items-center justify-center gap-3">
                    {(!imageFile || !labFile) && (
                      <p className="text-xs text-muted">
                        {!imageFile
                          ? "Drop an image to add"
                          : "Drop a lab report to add"}
                      </p>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        clearAll();
                      }}
                      className="relative z-20 text-sm text-muted hover:text-danger transition-colors"
                    >
                      Clear all
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Clean SVG upload icon */}
                  <div className="flex justify-center">
                    <svg
                      className="w-12 h-12 text-muted/40"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={1.5}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                      />
                    </svg>
                  </div>
                  <p className="font-medium text-foreground">
                    Drop medical image or lab report here
                  </p>
                  <p className="text-sm text-muted">
                    X-ray, dermatology, pathology, PDF lab report, or text file
                  </p>
                  <p className="text-xs text-muted/70">
                    You can upload both an image and a lab report
                  </p>
                </div>
              )}
            </div>

            {/* Image Analysis Results */}
            {imageResult && (
              <div className="rounded-xl border border-border bg-white p-4 space-y-3 border-l-4 border-l-teal">
                {/* Section: MedSigLIP Triage (hidden when uncertain) */}
                {imageResult.modality !== "uncertain" &&
                  imageResult.triage_findings.length > 0 && (
                    <div>
                      <h3 className="font-semibold text-sm text-foreground mb-2">
                        Image Analysis
                      </h3>
                      <p className="text-xs text-muted mb-1.5">
                        MedSigLIP Triage Findings:
                      </p>
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

                {/* MedGemma direct analysis badge (shown when triage was uncertain) */}
                {imageResult.modality === "uncertain" && (
                  <div>
                    <h3 className="font-semibold text-sm text-foreground mb-2">
                      Image Analysis
                    </h3>
                    <p className="text-xs text-muted">
                      Image type auto-detected by MedGemma
                    </p>
                  </div>
                )}

                {/* Divider */}
                {(imageResult.modality === "uncertain" ||
                  imageResult.triage_findings.length > 0) && (
                  <div className="border-t border-border" />
                )}

                {/* Section: Clinical Interpretation */}
                <div>
                  <h3 className="font-semibold text-sm text-foreground mb-2">
                    Clinical Interpretation
                  </h3>
                  <ExpandableText text={imageResult.medgemma_analysis} />
                </div>
              </div>
            )}

            {/* Lab Extraction Results */}
            {labResult &&
              labResult.lab_values &&
              Object.keys(labResult.lab_values).length > 0 && (
                <div className="rounded-xl border border-border bg-white p-4 space-y-3 border-l-4 border-l-teal">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-sm text-foreground">
                      Extracted Lab Values
                    </h3>
                    {labResult.abnormal_values.length > 0 && (
                      <Chip size="sm" variant="flat" color="danger">
                        {labResult.abnormal_values.length} abnormal
                      </Chip>
                    )}
                  </div>

                  {/* Lab Values Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-1.5 pr-3 font-semibold text-muted">
                            Test
                          </th>
                          <th className="text-left py-1.5 pr-3 font-semibold text-muted">
                            Value
                          </th>
                          <th className="text-left py-1.5 pr-3 font-semibold text-muted">
                            Unit
                          </th>
                          <th className="text-left py-1.5 pr-3 font-semibold text-muted">
                            Reference
                          </th>
                          <th className="text-left py-1.5 font-semibold text-muted">
                            Status
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(labResult.lab_values).map(
                          ([testName, details]) => {
                            const lab = details as {
                              value?: number | string;
                              unit?: string;
                              reference?: string;
                              status?: string;
                            };
                            const isAbnormal =
                              lab.status === "high" || lab.status === "low";
                            return (
                              <tr
                                key={testName}
                                className={`border-b border-border/50 ${isAbnormal ? "bg-red-50/50" : ""}`}
                              >
                                <td
                                  className={`py-1.5 pr-3 font-medium ${isAbnormal ? "text-danger" : "text-foreground"}`}
                                >
                                  {testName}
                                </td>
                                <td
                                  className={`py-1.5 pr-3 ${isAbnormal ? "text-danger font-semibold" : "text-foreground"}`}
                                >
                                  {lab.value ?? "—"}
                                </td>
                                <td className="py-1.5 pr-3 text-muted">
                                  {lab.unit ?? "—"}
                                </td>
                                <td className="py-1.5 pr-3 text-muted">
                                  {lab.reference ?? "—"}
                                </td>
                                <td className="py-1.5">
                                  {lab.status && (
                                    <Chip
                                      size="sm"
                                      variant="flat"
                                      color={
                                        lab.status === "high"
                                          ? "danger"
                                          : lab.status === "low"
                                            ? "warning"
                                            : "success"
                                      }
                                    >
                                      {lab.status === "high"
                                        ? "H"
                                        : lab.status === "low"
                                          ? "L"
                                          : "N"}
                                    </Chip>
                                  )}
                                </td>
                              </tr>
                            );
                          },
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Abnormal Values Summary */}
                  {labResult.abnormal_values.length > 0 && (
                    <>
                      <div className="border-t border-border" />
                      <div>
                        <p className="text-xs text-muted mb-1.5">
                          Flagged Abnormal:
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {labResult.abnormal_values.map((name, i) => (
                            <Chip
                              key={i}
                              size="sm"
                              variant="flat"
                              color="danger"
                            >
                              {name}
                            </Chip>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

            {/* Patient History */}
            <div className="space-y-2">
              <label
                htmlFor="patient-history"
                className="text-sm font-medium text-foreground"
              >
                Patient History{" "}
                {hasAnyFile ? "(Optional — enhances analysis)" : "(Required)"}
              </label>
              <textarea
                id="patient-history"
                placeholder="Enter relevant patient history, symptoms, medications, previous diagnoses..."
                rows={4}
                value={patientHistory}
                onChange={(e) => {
                  setPatientHistoryLocal(e.target.value);
                  if (error) setError(null);
                }}
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
              isDisabled={
                (!hasAnyFile && !patientHistory.trim()) || isAnalyzing
              }
              className={`min-w-[200px] font-semibold bg-teal text-white hover:bg-teal/90 rounded-lg px-6 py-2.5 text-sm transition-colors ${isAnalyzing ? "animate-pulse" : ""}`}
            >
              {isAnalyzing ? "Analyzing..." : "Analyze & Begin Debate"}
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
