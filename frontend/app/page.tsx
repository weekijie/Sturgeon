"use client";

import { useState, useCallback } from "react";
import { Card, Button, Spinner } from "@heroui/react";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [patientHistory, setPatientHistory] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

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
    // TODO: Connect to backend API
    await new Promise(resolve => setTimeout(resolve, 2000));
    setIsAnalyzing(false);
    // Navigate to debate page (will wire up later)
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
                Patient History (Optional)
              </label>
              <textarea
                id="patient-history"
                placeholder="Enter relevant patient history, symptoms, medications, previous diagnoses..."
                rows={4}
                value={patientHistory}
                onChange={(e) => setPatientHistory(e.target.value)}
                className="w-full rounded-lg bg-surface border border-border px-4 py-3 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent resize-none"
              />
            </div>
          </div>

          {/* Card Footer */}
          <div className="p-6 pt-0 flex justify-end">
            <Button
              variant="solid"
              onPress={handleAnalyze}
              isDisabled={!file && !patientHistory.trim()}
              className={`
                min-w-[200px] transition-all duration-300 font-semibold
                ${isAnalyzing ? "animate-pulse" : "shadow-lg shadow-accent/20 hover:shadow-accent/40 hover:scale-[1.02]"}
              `}
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
