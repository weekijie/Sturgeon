"use client";

import { Card, Button, Divider, Accordion, AccordionItem, Spinner } from "@heroui/react";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCase } from "../context/CaseContext";

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

  useEffect(() => {
    const fetchSummary = async () => {
      // If no data, redirect to home
      if (!caseData.differential.length) {
        router.push("/");
        return;
      }

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
          throw new Error("Failed to generate summary");
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
  }, [caseData, router]);

  const handleNewCase = () => {
    resetCase();
    router.push("/");
  };

  // Confidence to percentage mapping
  const confidenceToPercent = (conf: string): number => {
    const map: Record<string, number> = { high: 90, medium: 70, low: 50 };
    return map[conf.toLowerCase()] || 75;
  };

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <Spinner size="lg" />
          <p className="text-muted">MedGemma is generating your diagnostic summary...</p>
        </div>
      </main>
    );
  }

  if (error || !summary) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6">
        <Card className="p-6 max-w-md text-center">
          <h2 className="text-xl font-bold text-danger mb-4">Error</h2>
          <p className="text-muted mb-4">{error || "Unable to generate summary"}</p>
          <Button variant="solid" onPress={handleNewCase}>
            Start New Case
          </Button>
        </Card>
      </main>
    );
  }

  const confidence = confidenceToPercent(summary.confidence);

  return (
    <main className="min-h-screen flex flex-col items-center p-6 pb-20">
      <div className="w-full max-w-3xl space-y-8">

        {/* Header */}
        <header className="flex items-center justify-between border-b border-white/10 pb-6 mb-8 bg-background/80 backdrop-blur-md -mx-6 px-6 pt-6 sticky top-0 z-10">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="text-teal drop-shadow-sm">Sturgeon</span> Summary
            </h1>
            <p className="text-muted mt-1 font-medium">Diagnostic Consensus Reached</p>
          </div>
          <Button variant="bordered" onPress={handleNewCase} className="hover:border-teal hover:text-teal transition-colors">
            New Case
          </Button>
        </header>

        {/* Final Diagnosis Card */}
        <Card className="border-l-4 border-l-teal overflow-hidden">
          <div className="p-6 bg-surface">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h2 className="text-sm font-medium text-teal uppercase tracking-wider mb-1">
                  Primary Diagnosis
                </h2>
                <h3 className="text-2xl font-bold">{summary.final_diagnosis}</h3>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-teal">
                  {confidence}%
                </div>
                <div className="text-xs text-muted">Confidence ({summary.confidence})</div>
              </div>
            </div>

            <Divider className="my-4" />

            <div className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">Clinical Reasoning</h4>
                <ul className="list-disc list-inside space-y-1 text-muted">
                  {summary.reasoning_chain.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h4 className="font-semibold mb-2">Recommended Next Steps</h4>
                <ul className="list-disc list-inside space-y-1 text-muted">
                  {summary.next_steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </Card>

        {/* Ruled Out Diagnoses */}
        {summary.ruled_out.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold px-2">Ruled Out Differentials</h3>
            <Accordion variant="splitted">
              {summary.ruled_out.map((dx, idx) => (
                <AccordionItem
                  key={idx}
                  title={
                    <div className="flex items-center gap-2">
                      <span className="line-through text-muted">{dx}</span>
                    </div>
                  }
                >
                  <div className="pb-2">
                    <p className="text-sm text-muted leading-relaxed">
                      Excluded based on clinical evidence and debate reasoning.
                    </p>
                  </div>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        )}

        {/* Session Info */}
        <div className="text-center pt-8">
          <p className="text-xs text-muted uppercase tracking-widest">
            Session completed • {caseData.debateRounds.length} debate rounds
          </p>
        </div>

      </div>
    </main>
  );
}
