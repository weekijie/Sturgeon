"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Spinner } from "@heroui/react";
import { useCase } from "./context/CaseContext";

export default function UploadPage() {
  const router = useRouter();
  const { setPatientHistory, setDifferential } = useCase();
  
  const [file, setFile] = useState<File | null>(null);
  const [patientHistory, setPatientHistoryLocal] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  }, []);

  const handleAnalyze = async () => {
    if (!file && !patientHistory.trim()) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      // For now, we'll use the patient history text directly
      // File processing can be added later
      const response = await fetch("/api/differential", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_history: patientHistory,
          lab_values: {}, // Can be extracted from file in future
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to analyze. Please try again.");
      }

      const data = await response.json();
      
      // Store in context
      setPatientHistory(patientHistory);
      setDifferential(data.diagnoses);
      
      // Navigate to debate page
      router.push("/debate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold tracking-tight">
            <span className="text-teal">Sturgeon</span>
          </h1>
          <p className="text-muted text-lg">
            Diagnostic Debate AI — Challenge the diagnosis
          </p>
        </div>

        {/* Upload Card */}
        <Card className="p-0">
          {/* Card Header */}
          <div className="p-6 pb-0">
            <h2 className="text-xl font-semibold">Upload Lab Report</h2>
            <p className="text-muted text-sm mt-1">
              Upload a lab report or imaging result to begin the diagnostic debate
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
                ${isDragging
                  ? "border-accent bg-accent/10"
                  : "border-border hover:border-accent/50 hover:bg-surface/50"
                }
                ${file ? "border-success bg-success/10" : ""}
              `}
            >
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.txt"
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />

              {file ? (
                <div className="space-y-2">
                  <div className="text-success text-2xl">✓</div>
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-muted">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-4xl opacity-50">📄</div>
                  <p className="font-medium">
                    Drop lab report here or click to browse
                  </p>
                  <p className="text-sm text-muted">
                    Supports PDF, images, or text files
                  </p>
                </div>
              )}
            </div>

            {/* Patient History - using native textarea */}
            <div className="space-y-2">
              <label htmlFor="patient-history" className="text-sm font-medium">
                Patient History (Required)
              </label>
              <textarea
                id="patient-history"
                placeholder="Enter relevant patient history, symptoms, medications, previous diagnoses..."
                rows={4}
                value={patientHistory}
                onChange={(e) => setPatientHistoryLocal(e.target.value)}
                className="w-full rounded-lg bg-surface border border-border px-4 py-3 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent resize-none"
              />
            </div>

            {/* Error Message */}
            {error && (
              <div className="text-danger text-sm bg-danger/10 p-3 rounded-lg">
                {error}
              </div>
            )}
          </div>

          {/* Card Footer */}
          <div className="p-6 pt-0 flex justify-end">
            <Button
              variant="solid"
              onPress={handleAnalyze}
              isDisabled={(!file && !patientHistory.trim()) || isAnalyzing}
              className={`
                min-w-[200px] transition-all duration-300 font-semibold
                ${isAnalyzing ? "animate-pulse" : "shadow-lg shadow-accent-soft hover:shadow-accent-soft hover:scale-[1.02]"}
              `}
            >
              {isAnalyzing ? (
                <>
                  <Spinner size="sm" color="white" />
                  Analyzing with MedGemma...
                </>
              ) : (
                "Analyze & Begin Debate"
              )}
            </Button>
          </div>
        </Card>

        {/* Footer hint */}
        <p className="text-center text-sm text-muted">
          Powered by MedGemma — For educational purposes only
        </p>
      </div>
    </main>
  );
}
