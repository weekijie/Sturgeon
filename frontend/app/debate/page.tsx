"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Input } from "@heroui/react";
import { useCase, Diagnosis } from "../context/CaseContext";
import Prose from "../../components/Prose";

type Probability = "high" | "medium" | "low";

function ProbabilityBadge({ level }: { level: Probability }) {
  const colorClasses = {
    high: "bg-green-100 text-green-700 border border-green-200",
    medium: "bg-amber-100 text-amber-700 border border-amber-200",
    low: "bg-red-100 text-red-700 border border-red-200",
  };

  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${colorClasses[level]}`}>
      {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

interface Message {
  role: "user" | "ai" | "error";
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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

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
        // Try to read actual error details from response body
        let errorDetail = "Failed to get AI response";
        try {
          const errBody = await response.json();
          errorDetail = errBody.detail || errBody.error || errBody.message || errorDetail;
        } catch {
          // Response body wasn't JSON
        }
        throw new Error(errorDetail);
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
      const errorMessage = error instanceof Error ? error.message : "An unexpected error occurred.";
      setMessages((prev) => [...prev, { 
        role: "error", 
        content: errorMessage,
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    // Remove the last error message and retry with the last user message
    const lastUserMsg = [...messages].reverse().find(m => m.role === "user");
    if (lastUserMsg) {
      setMessages((prev) => prev.filter((_, i) => i !== prev.length - 1)); // remove error
      setInput(lastUserMsg.content);
    }
  };

  const handleEndSession = () => {
    router.push("/summary");
  };

  return (
    <main className="min-h-screen flex flex-col bg-white">
      {/* Header */}
      <header className="sticky top-[3px] z-50 border-b border-border bg-white px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              <span className="text-teal">Sturgeon</span> Diagnostic Debate
            </h1>
            {isOrchestrated && (
              <span className="text-[10px] font-medium text-teal bg-teal-light px-2 py-0.5 rounded-full border border-teal/20">
                Agentic Mode
              </span>
            )}
          </div>
          <Button 
            variant="bordered" 
            size="sm" 
            onPress={handleEndSession}
            className="border-border text-foreground hover:border-teal hover:text-teal hover:bg-teal-light/30 transition-colors"
          >
            End Session & Summarize
          </Button>
        </div>
      </header>

      {/* Main Content - Split Layout */}
      <div className="flex-1 flex max-w-7xl mx-auto w-full">
        {/* Left Panel - Differential Diagnoses */}
        <aside className="w-80 border-r border-border bg-surface p-4 overflow-y-auto h-[calc(100vh-52px-3px)] sticky top-[calc(52px+3px)]">
          {/* Uploaded Image Preview */}
          {caseData.imagePreviewUrl && (
            <div className="mb-4">
              <h2 className="text-xs font-bold text-muted uppercase tracking-widest mb-2 px-1">
                Medical Image
              </h2>
              <div className="rounded-lg border border-border overflow-hidden bg-white">
                <img
                  src={caseData.imagePreviewUrl}
                  alt="Uploaded medical image"
                  className="w-full object-contain max-h-48"
                />
              </div>
              {caseData.imageAnalysis && (
                <div className="mt-2 px-1">
                  <p className="text-[10px] text-teal font-medium uppercase tracking-wider">
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
                className={`p-3 bg-white border border-border shadow-sm cursor-default ${idx === 0 ? "border-l-4 border-l-teal" : ""}`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="font-medium text-sm leading-tight text-foreground">{dx.name}</h3>
                  <ProbabilityBadge level={dx.probability} />
                </div>
                {/* Supporting evidence */}
                {dx.supporting_evidence?.length > 0 && (
                  <div className="mb-1.5">
                    <p className="text-[10px] text-success font-medium uppercase tracking-wider mb-0.5">Supporting</p>
                    <ul className="text-xs text-muted leading-relaxed space-y-0.5">
                      {dx.supporting_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-success shrink-0">+</span> {ev}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {/* Against evidence */}
                {dx.against_evidence?.length > 0 && (
                  <div className="mb-1.5">
                    <p className="text-[10px] text-danger font-medium uppercase tracking-wider mb-0.5">Against</p>
                    <ul className="text-xs text-muted leading-relaxed space-y-0.5">
                      {dx.against_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-danger shrink-0">-</span> {ev}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {/* Suggested tests */}
                {dx.suggested_tests?.length > 0 && (
                  <div>
                    <p className="text-[10px] text-teal font-medium uppercase tracking-wider mb-0.5">Tests</p>
                    <p className="text-xs text-muted leading-relaxed">
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
                <div className="max-w-[70%]">
                  {/* Label */}
                  <p className={`text-[10px] font-medium uppercase tracking-wider mb-1 ${
                    msg.role === "user" ? "text-right text-muted" : msg.role === "error" ? "text-danger" : "text-teal"
                  }`}>
                    {msg.role === "user" ? "You" : msg.role === "error" ? "Error" : "Sturgeon AI"}
                  </p>

                  {msg.role === "error" ? (
                    /* Error message */
                    <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                      <p className="text-sm text-danger leading-relaxed">{msg.content}</p>
                      <button
                        onClick={handleRetry}
                        className="mt-2 text-xs font-semibold text-teal hover:text-teal/80 px-3 py-1 rounded-full bg-teal-light/50 hover:bg-teal-light transition-colors"
                      >
                        Retry
                      </button>
                    </div>
                  ) : msg.role === "user" ? (
                    /* User message */
                    <div className="bg-accent text-white rounded-xl px-4 py-3">
                      <p className="text-sm leading-relaxed break-words">{msg.content}</p>
                    </div>
                  ) : (
                    /* AI message */
                    <div className="bg-surface border-l-3 border-l-teal rounded-xl px-4 py-3">
                      <Prose content={msg.content} />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="max-w-[70%]">
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1 text-teal">
                    Sturgeon AI
                  </p>
                  <div className="bg-surface border-l-3 border-l-teal rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="dot-pulse">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    <span className="text-sm text-muted">
                      {isOrchestrated
                        ? "Gemini + MedGemma are reasoning..."
                        : "MedGemma is thinking..."}
                    </span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-4 bg-white">
            <div className="flex gap-3 max-w-4xl mx-auto">
              <Input
                className="flex-1"
                placeholder="Challenge the diagnosis..."
                value={input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
                onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && handleSend()}
                isDisabled={isLoading}
              />
              <Button 
                variant="solid" 
                onPress={handleSend} 
                isDisabled={isLoading || !input.trim()}
                className="bg-teal text-white hover:bg-teal/90 font-semibold px-6"
              >
                Send &rarr;
              </Button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
