"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Input, Spinner } from "@heroui/react";
import { useCase, Diagnosis } from "../context/CaseContext";

type Probability = "high" | "medium" | "low";

function ProbabilityBadge({ level }: { level: Probability }) {
  const colorClasses = {
    high: "bg-success/20 text-success",
    medium: "bg-warning/20 text-warning",
    low: "bg-danger/20 text-danger",
  };

  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${colorClasses[level]}`}>
      {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

interface Message {
  role: "user" | "ai";
  content: string;
}

export default function DebatePage() {
  const router = useRouter();
  const { caseData, addDebateRound, updateDifferential } = useCase();
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isOrchestrated, setIsOrchestrated] = useState(false);

  // Initialize with differential from context (run once on mount)
  const didInit = useRef(false);
  useEffect(() => {
    if (didInit.current) return;
    if (caseData.differential.length > 0) {
      didInit.current = true;
      setDiagnoses(caseData.differential);
      // Build initial AI message
      const hasImage = !!caseData.imageAnalysis;
      const primaryDx = caseData.differential[0]?.name || "unknown";
      let initMsg = `Based on the ${hasImage ? "uploaded medical image and " : ""}patient history, I've identified ${caseData.differential.length} potential diagnoses. The primary concern is **${primaryDx}**.`;
      
      if (hasImage && caseData.imageAnalysis) {
        initMsg += ` The ${caseData.imageAnalysis.image_type} (${caseData.imageAnalysis.modality}) has been analyzed using MedSigLIP triage and MedGemma interpretation.`;
      }
      
      initMsg += ` Challenge my reasoning or ask about specific aspects of the differential.`;
      
      setMessages([{ role: "ai", content: initMsg }]);
    } else {
      // No data, redirect back to upload
      router.push("/");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/debate-turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_history: caseData.patientHistory,
          lab_values: caseData.labValues,
          current_differential: diagnoses,
          previous_rounds: caseData.debateRounds,
          user_challenge: userMessage,
          session_id: sessionId,
          image_context: caseData.imageAnalysis?.triage_summary || null,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to get AI response");
      }

      const data = await response.json();

      // Track session and orchestration status
      if (data.session_id) {
        setSessionId(data.session_id);
      }
      setIsOrchestrated(data.orchestrated || false);

      // Clean ai_response: strip any JSON wrapper artifacts
      let aiText: string = data.ai_response || "I need more information to respond.";
      // Remove leading { "ai_response": " prefix if present
      const prefixMatch = aiText.match(/^\s*\{\s*"ai_response"\s*:\s*"?([\s\S]*)/);
      if (prefixMatch) {
        aiText = prefixMatch[1].replace(/"\s*,?\s*"(updated_differential|suggested_test|medgemma_query)[\s\S]*$/, "").replace(/["\s}]+$/, "");
      }

      // Add AI response to messages
      setMessages((prev) => [...prev, { role: "ai", content: aiText }]);
      
      // Update differential if changed
      if (data.updated_differential?.length > 0) {
        setDiagnoses(data.updated_differential);
        updateDifferential(data.updated_differential);
      }

      // Store debate round in context
      addDebateRound({
        user_challenge: userMessage,
        ai_response: data.ai_response,
      });
    } catch (error) {
      setMessages((prev) => [...prev, { 
        role: "ai", 
        content: "I apologize, but I encountered an error processing your challenge. Please try again." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEndSession = () => {
    router.push("/summary");
  };

  return (
    <main className="min-h-screen flex flex-col bg-background selection:bg-teal/30">
      {/* Header - Glassmorphism */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-background/80 backdrop-blur-md px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight">
              <span className="text-teal drop-shadow-sm">Sturgeon</span> Diagnostic Debate
            </h1>
            {isOrchestrated && (
              <span className="text-[10px] font-medium text-teal/70 bg-teal/10 px-2 py-0.5 rounded-full border border-teal/20">
                Agentic Mode
              </span>
            )}
          </div>
          <Button 
            variant="bordered" 
            size="sm" 
            onPress={handleEndSession}
            className="hover:border-success hover:text-success hover:bg-success/10 transition-colors"
          >
            End Session & Summarize
          </Button>
        </div>
      </header>

      {/* Main Content - Split Layout */}
      <div className="flex-1 flex max-w-7xl mx-auto w-full">
        {/* Left Panel - Differential Diagnoses */}
        <aside className="w-80 border-r border-border p-4 overflow-y-auto h-[calc(100vh-73px)] sticky top-[73px]">
          {/* Uploaded Image Preview */}
          {caseData.imagePreviewUrl && (
            <div className="mb-4">
              <h2 className="text-xs font-bold text-muted uppercase tracking-widest mb-2 px-1">
                Medical Image
              </h2>
              <div className="rounded-lg border border-border overflow-hidden">
                <img
                  src={caseData.imagePreviewUrl}
                  alt="Uploaded medical image"
                  className="w-full object-contain max-h-48"
                />
              </div>
              {caseData.imageAnalysis && (
                <div className="mt-2 px-1">
                  <p className="text-[10px] text-teal/70 font-medium uppercase tracking-wider">
                    {caseData.imageAnalysis.image_type}
                  </p>
                  <p className="text-[10px] text-muted">
                    {caseData.imageAnalysis.modality} — {(caseData.imageAnalysis.image_type_confidence * 100).toFixed(0)}% confidence
                  </p>
                </div>
              )}
            </div>
          )}

          <h2 className="text-xs font-bold text-muted uppercase tracking-widest mb-4 px-1">
            Differential Diagnoses
          </h2>
          <div className="space-y-3">
            {diagnoses.map((dx, idx) => (
              <Card
                key={idx}
                className="p-3 transition-all duration-300 hover:border-teal/50 hover:shadow-lg hover:shadow-teal/5 hover:-translate-y-0.5 cursor-default group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="font-medium text-sm leading-tight group-hover:text-teal transition-colors">{dx.name}</h3>
                  <ProbabilityBadge level={dx.probability} />
                </div>
                {/* Supporting evidence */}
                {dx.supporting_evidence?.length > 0 && (
                  <div className="mb-1.5">
                    <p className="text-[10px] text-success/70 font-medium uppercase tracking-wider mb-0.5">Supporting</p>
                    <ul className="text-xs text-muted leading-relaxed group-hover:text-foreground/80 transition-colors space-y-0.5">
                      {dx.supporting_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-success/50 shrink-0">+</span> {ev}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {/* Against evidence */}
                {dx.against_evidence?.length > 0 && (
                  <div className="mb-1.5">
                    <p className="text-[10px] text-danger/70 font-medium uppercase tracking-wider mb-0.5">Against</p>
                    <ul className="text-xs text-muted leading-relaxed group-hover:text-foreground/80 transition-colors space-y-0.5">
                      {dx.against_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-danger/50 shrink-0">-</span> {ev}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {/* Suggested tests */}
                {dx.suggested_tests?.length > 0 && (
                  <div>
                    <p className="text-[10px] text-teal/70 font-medium uppercase tracking-wider mb-0.5">Tests</p>
                    <p className="text-xs text-muted leading-relaxed group-hover:text-foreground/80 transition-colors">
                      {dx.suggested_tests.join(", ")}
                    </p>
                  </div>
                )}
              </Card>
            ))}
          </div>
        </aside>

        {/* Right Panel - Chat */}
        <section className="flex-1 flex flex-col">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[70%] rounded-2xl px-4 py-3 ${msg.role === "user"
                    ? "bg-accent text-accent-foreground"
                    : "bg-surface text-foreground"
                  }`}
                >
                  <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{msg.content}</p>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-surface rounded-2xl px-4 py-3 flex items-center gap-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted">
                    {isOrchestrated
                      ? "Gemini + MedGemma are reasoning..."
                      : "MedGemma is thinking..."}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-border p-4">
            <div className="flex gap-3 max-w-4xl mx-auto">
              <Input
                className="flex-1"
                placeholder="Challenge the diagnosis..."
                value={input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
                onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && handleSend()}
                isDisabled={isLoading}
              />
              <Button variant="solid" onPress={handleSend} isDisabled={isLoading || !input.trim()}>
                Send
              </Button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
