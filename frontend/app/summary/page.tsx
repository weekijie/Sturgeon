"use client";

import { Card, Button, Divider, Spinner } from "@heroui/react";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useCase } from "../context/CaseContext";
import Prose from "../../components/Prose";

interface SummaryData {
  final_diagnosis: string;
  confidence: string;
  reasoning_chain: string[];
  ruled_out: string[];
  next_steps: string[];
}

export default function SummaryPage() {
  const router = useRouter();
  const { caseData, resetCase } = useCase();
  
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fire once on mount — useRef guard prevents double-fire (React Strict Mode / caseData ref changes)
  const didFetch = useRef(false);
  useEffect(() => {
    if (didFetch.current) return;

    // If no data, redirect to home
    if (!caseData.differential.length) {
      router.push("/");
      return;
    }

    didFetch.current = true;

    const fetchSummary = async () => {
      try {
        const response = await fetch("/api/summary", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_history: caseData.patientHistory,
            lab_values: caseData.labValues,
            final_differential: caseData.differential,
            debate_rounds: caseData.debateRounds,
          }),
        });

        if (!response.ok) {
          // Read actual error from backend
          let errorDetail = "Failed to generate summary";
          try {
            const errBody = await response.json();
            errorDetail = errBody.detail || errBody.error || errBody.message || errorDetail;
          } catch {
            // Response body wasn't JSON
          }
          throw new Error(errorDetail);
        }

        const data = await response.json();
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setIsLoading(false);
      }
    };

    fetchSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNewCase = () => {
    resetCase();
    router.push("/");
  };

  // Confidence to percentage mapping
  const confidenceToPercent = (conf: string): number => {
    const map: Record<string, number> = { high: 90, medium: 70, low: 50 };
    return map[conf.toLowerCase()] || 75;
  };

  // Parse "Diagnosis: reason" strings from ruled_out
  const parseRuledOut = (entry: string): { name: string; reason: string } => {
    const colonIdx = entry.indexOf(":");
    if (colonIdx > 0 && colonIdx < entry.length - 1) {
      return {
        name: entry.slice(0, colonIdx).trim(),
        reason: entry.slice(colonIdx + 1).trim(),
      };
    }
    return { name: entry, reason: "Excluded based on clinical evidence and debate reasoning." };
  };

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-white">
        <div className="text-center space-y-4">
          <Spinner size="lg" />
          <p className="text-muted animate-pulse">MedGemma is generating your diagnostic summary...</p>
        </div>
      </main>
    );
  }

  if (error || !summary) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6 bg-white">
        <Card className="p-6 max-w-md text-center bg-white border border-border shadow-sm">
          <h2 className="text-xl font-bold text-danger mb-4">Error</h2>
          <p className="text-muted mb-4">{error || "Unable to generate summary"}</p>
          <Button variant="solid" onPress={handleNewCase} className="bg-teal text-white hover:bg-teal/90">
            Start New Case
          </Button>
        </Card>
      </main>
    );
  }

  const confidence = confidenceToPercent(summary.confidence);

  return (
    <main className="min-h-screen flex flex-col items-center p-6 pb-20 bg-white pt-8">
      <div className="w-full max-w-3xl space-y-8">

        {/* Header */}
        <header className="flex items-center justify-between border-b border-border pb-6 mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-foreground">
              <span className="text-teal">Sturgeon</span> Summary
            </h1>
            <p className="text-muted mt-1 font-medium">Diagnostic Consensus Reached</p>
          </div>
          <Button 
            variant="bordered" 
            onPress={handleNewCase} 
            className="border-border text-foreground hover:border-teal hover:text-teal hover:bg-teal-light/30 transition-colors"
          >
            New Case
          </Button>
        </header>

        {/* Final Diagnosis Card */}
        <Card className="border-l-4 border-l-teal overflow-hidden bg-white border border-border shadow-sm">
          <div className="p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h2 className="text-sm font-medium text-teal uppercase tracking-wider mb-1">
                  Primary Diagnosis
                </h2>
                <h3 className="text-2xl font-bold text-foreground">{summary.final_diagnosis}</h3>
              </div>
              <div className="text-right">
                <div className="text-sm text-muted mb-1">Confidence ({summary.confidence})</div>
                <div className="text-2xl font-bold text-teal">
                  {confidence}%
                </div>
              </div>
            </div>

            {/* Confidence bar */}
            <div className="mb-6">
              <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-teal rounded-full transition-all duration-700"
                  style={{ width: `${confidence}%` }}
                />
              </div>
            </div>

            <Divider className="my-4" />

            <div className="space-y-6">
              {/* Clinical Reasoning - numbered steps with teal numbers */}
              <div>
                <h4 className="font-semibold text-foreground mb-3">Clinical Reasoning</h4>
                <ol className="space-y-2">
                  {summary.reasoning_chain.map((step, i) => (
                    <li key={i} className="flex gap-3 text-sm leading-relaxed">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-teal-light text-teal text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-muted">{step.replace(/^\d+[\.\)]\s*/, "")}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Next Steps */}
              <div>
                <h4 className="font-semibold text-foreground mb-3">Recommended Next Steps</h4>
                <Prose content={summary.next_steps.map(s => `- ${s}`).join("\n")} />
              </div>
            </div>
          </div>
        </Card>

        {/* Ruled Out Diagnoses */}
        {summary.ruled_out.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-foreground px-2">Ruled Out Differentials</h3>
            <div className="space-y-2">
              {summary.ruled_out.map((dx, idx) => {
                const parsed = parseRuledOut(dx);
                return (
                  <Card key={idx} className="p-4 bg-white border border-border shadow-sm">
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-red-100 text-danger text-xs font-bold flex items-center justify-center mt-0.5">
                        &times;
                      </span>
                      <div>
                        <h4 className="font-medium text-foreground line-through decoration-danger/40">{parsed.name}</h4>
                        <p className="text-sm text-muted mt-1 leading-relaxed">{parsed.reason}</p>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {/* Session Info */}
        <div className="text-center pt-8">
          <p className="text-xs text-muted uppercase tracking-widest">
            Session completed &middot; {caseData.debateRounds.length} debate rounds
          </p>
        </div>

      </div>
    </main>
  );
}
