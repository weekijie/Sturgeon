"use client";

import { useState, useEffect } from "react";
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

  // Initialize with differential from context
  useEffect(() => {
    if (caseData.differential.length > 0) {
      setDiagnoses(caseData.differential);
      // Add initial AI message
      setMessages([{
        role: "ai",
        content: `Based on the patient history, I've identified ${caseData.differential.length} potential diagnoses. The primary concern is ${caseData.differential[0]?.name || "unknown"}. Challenge my reasoning or ask about specific aspects of the differential.`
      }]);
    } else {
      // No data, redirect back to upload
      router.push("/");
    }
  }, [caseData.differential, router]);

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
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to get AI response");
      }

      const data = await response.json();

      // Add AI response to messages
      setMessages((prev) => [...prev, { role: "ai", content: data.ai_response }]);
      
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
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-teal drop-shadow-sm">Sturgeon</span> Diagnostic Debate
          </h1>
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
                <p className="text-xs text-muted leading-relaxed group-hover:text-foreground/80 transition-colors">
                  {dx.supporting_evidence?.slice(0, 2).join(". ") || "No evidence provided"}
                </p>
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
                  <p className="text-sm leading-relaxed">{msg.content}</p>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-surface rounded-2xl px-4 py-3 flex items-center gap-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted">MedGemma is thinking...</span>
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
