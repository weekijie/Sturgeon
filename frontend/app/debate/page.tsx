"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, Button, TextArea, Chip } from "@heroui/react";
import { useCase, Diagnosis, Citation } from "../context/CaseContext";
import Prose from "../../components/Prose";
import { RateLimitStatus, parseRateLimitHeaders, isRateLimitError } from "../../components/RateLimitUI";
import { useSpeechToText } from "../../lib/useSpeechToText";

type Probability = "high" | "medium" | "low";
type TimelineStage = "idle" | "retrieving" | "reasoning" | "finalizing";

const CHALLENGE_MAX_CHARS = 5000;

function appendWithSpacing(currentText: string, incomingText: string, maxChars: number): string {
  const normalizedCurrent = currentText.trim();
  const normalizedIncoming = incomingText.trim();

  if (!normalizedIncoming) {
    return currentText;
  }

  const combined = normalizedCurrent
    ? `${normalizedCurrent} ${normalizedIncoming}`
    : normalizedIncoming;

  return combined.slice(0, maxChars);
}

function createMessageId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

interface ActiveStreamState {
  messageId: string;
  fullText: string;
  timeoutId: number | null;
  resolve: (() => void) | null;
}

function ClipboardIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M9 4h6m-5 0h4a2 2 0 0 1 2 2v1h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-1H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h2V6a2 2 0 0 1 2-2Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="m5 12 4 4 10-10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// 1H: Probability bar with percentage
function ProbabilityBar({ level, previousLevel }: { level: Probability; previousLevel?: Probability }) {
  const percentMap: Record<Probability, number> = { high: 85, medium: 55, low: 25 };
  const colorMap: Record<Probability, string> = {
    high: "bg-green-500",
    medium: "bg-amber-500",
    low: "bg-red-400",
  };
  const percent = percentMap[level] || 55;
  const prevPercent = previousLevel ? percentMap[previousLevel] : undefined;
  const changed = prevPercent !== undefined && prevPercent !== percent;
  const increased = changed && percent > (prevPercent ?? 0);

  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorMap[level]} ${changed ? (increased ? "ring-2 ring-green-300" : "ring-2 ring-red-300") : ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className={`text-[10px] font-semibold w-8 text-right ${
        level === "high" ? "text-green-600" : level === "medium" ? "text-amber-600" : "text-red-500"
      }`}>
        {level.charAt(0).toUpperCase() + level.slice(1)}
      </span>
    </div>
  );
}

// 1B: Suggested challenge prompts
const SUGGESTED_PROMPTS = [
  "What test would help differentiate these diagnoses?",
  "What evidence argues against the top diagnosis?",
  "Could this be an autoimmune condition instead?",
  "What if we consider the patient's demographics?",
  "Summarize the key findings supporting your leading diagnosis",
];

// Guideline Badge Component
function GuidelineBadge({ hasGuidelines }: { hasGuidelines: boolean }) {
  if (!hasGuidelines) return null;
  
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-800 mt-2">
      Clinical Guidelines Referenced
    </span>
  );
}

interface Message {
  id: string;
  role: "user" | "ai" | "error";
  content: string;
  citations?: Citation[];
  has_guidelines?: boolean;
  is_streaming?: boolean;
}

export default function DebatePage() {
  const router = useRouter();
  const { caseData, addDebateRound, updateDifferential, setSessionId: persistSessionId } = useCase();
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [previousDiagnoses, setPreviousDiagnoses] = useState<Diagnosis[]>([]); // 1H: track changes
  const [isOrchestrated, setIsOrchestrated] = useState(false);
  const [suggestedTest, setSuggestedTest] = useState<string | null>(null);
  const [hasMounted, setHasMounted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false); // 1F: mobile sidebar toggle
  const [rateLimitInfo, setRateLimitInfo] = useState<{ limit: number; remaining: number; window: number; retryAfter?: number } | null>(null);
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [timelineStage, setTimelineStage] = useState<TimelineStage>("idle");
  const [isStreamingResponse, setIsStreamingResponse] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stageTimerRef = useRef<number | null>(null);
  const activeStreamRef = useRef<ActiveStreamState | null>(null);

  const {
    isSupported: isVoiceSupported,
    isRecording: isVoiceRecording,
    interimTranscript,
    error: voiceError,
    toggleListening: toggleVoiceInput,
    stopListening: stopVoiceInput,
    resetTranscript: resetVoiceTranscript,
  } = useSpeechToText({
    onFinalTranscript: (transcript: string) => {
      setInput((prev) => appendWithSpacing(prev, transcript, CHALLENGE_MAX_CHARS));
    },
  });

  const clearStageTimer = useCallback(() => {
    if (stageTimerRef.current !== null) {
      window.clearTimeout(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  }, []);

  const clearActiveStreamTimeout = useCallback(() => {
    const activeStream = activeStreamRef.current;
    if (!activeStream || activeStream.timeoutId === null) {
      return;
    }

    window.clearTimeout(activeStream.timeoutId);
    activeStream.timeoutId = null;
  }, []);

  const completeActiveStream = useCallback(() => {
    const activeStream = activeStreamRef.current;
    if (!activeStream) {
      return;
    }

    clearActiveStreamTimeout();
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === activeStream.messageId
          ? { ...msg, content: activeStream.fullText, is_streaming: false }
          : msg,
      ),
    );
    setIsStreamingResponse(false);

    const done = activeStream.resolve;
    activeStreamRef.current = null;
    if (done) {
      done();
    }
  }, [clearActiveStreamTimeout]);

  // Hydration guard: localStorage data isn't available during SSR
  useEffect(() => setHasMounted(true), []);

  // Auto-scroll to latest message without per-token smooth scroll jank
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  useEffect(() => {
    return () => {
      clearStageTimer();
      clearActiveStreamTimeout();
      stopVoiceInput();
    };
  }, [clearActiveStreamTimeout, clearStageTimer, stopVoiceInput]);

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
        if (caseData.imageAnalysis.modality === "uncertain") {
          initMsg += ` The uploaded medical image has been analyzed using MedGemma interpretation.`;
        } else {
          initMsg += ` The ${caseData.imageAnalysis.image_type} (${caseData.imageAnalysis.modality}) has been analyzed using MedSigLIP triage and MedGemma interpretation.`;
        }
      }
      
      initMsg += ` Challenge my reasoning or ask about specific aspects of the differential.`;
      
      // Reconstruct messages from persisted debate rounds (survives page refresh)
      const restoredMessages: Message[] = [{ id: createMessageId(), role: "ai", content: initMsg }];
      if (caseData.debateRounds.length > 0) {
        for (const round of caseData.debateRounds) {
          restoredMessages.push({ id: createMessageId(), role: "user", content: round.user_challenge });
          restoredMessages.push({ 
            id: createMessageId(),
            role: "ai", 
            content: round.ai_response,
            citations: round.citations,
            has_guidelines: round.has_guidelines
          });
        }
      }
      
      setMessages(restoredMessages);
    } else {
      // No data, redirect back to upload
      router.push("/");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const streamAiMessage = useCallback(
    (messageId: string, fullText: string) =>
      new Promise<void>((resolve) => {
        completeActiveStream();

        if (!fullText) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === messageId
                ? { ...msg, content: fullText, is_streaming: false }
                : msg,
            ),
          );
          setIsStreamingResponse(false);
          resolve();
          return;
        }

        const totalChars = fullText.length;
        const targetCharsPerSecond = 60;
        const minDurationMs = 700;
        const maxDurationMs = 7000;
        const desiredDurationMs = Math.max(
          minDurationMs,
          Math.min(maxDurationMs, (totalChars / targetCharsPerSecond) * 1000),
        );

        const streamState: ActiveStreamState = {
          messageId,
          fullText,
          timeoutId: null,
          resolve,
        };
        activeStreamRef.current = streamState;

        let cursor = 0;
        let pauseBudgetMs = 0;
        const startAt = performance.now();

        const renderChunk = () => {
          const activeStream = activeStreamRef.current;
          if (!activeStream || activeStream.messageId !== messageId) {
            resolve();
            return;
          }

          const elapsedMs = performance.now() - startAt - pauseBudgetMs;
          const progress = Math.max(0, Math.min(1, elapsedMs / desiredDurationMs));
          const targetCursor = Math.max(
            cursor + 2,
            Math.min(totalChars, Math.floor(progress * totalChars)),
          );

          const nextText = fullText.slice(0, targetCursor);
          const appended = fullText.slice(cursor, targetCursor);
          const punctuationMatches = appended.match(/[,.!?;:]/g);
          if (punctuationMatches?.length) {
            pauseBudgetMs += Math.min(90, punctuationMatches.length * 20);
          }

          cursor = targetCursor;

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === messageId ? { ...msg, content: nextText } : msg,
            ),
          );

          if (cursor >= totalChars) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === messageId
                  ? { ...msg, content: fullText, is_streaming: false }
                  : msg,
              ),
            );
            clearActiveStreamTimeout();
            activeStreamRef.current = null;
            setIsStreamingResponse(false);
            resolve();
            return;
          }

          const delay = appended.match(/[,.!?]/)
            ? 55
            : appended.match(/[;:]/)
              ? 48
              : 35;
          streamState.timeoutId = window.setTimeout(renderChunk, delay);
        };

        setIsStreamingResponse(true);
        renderChunk();
      }),
    [clearActiveStreamTimeout, completeActiveStream],
  );

  const handleCopyMessage = useCallback(async (messageId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      window.setTimeout(() => {
        setCopiedMessageId((prev) => (prev === messageId ? null : prev));
      }, 1500);
    } catch (copyError) {
      console.error("Failed to copy message", copyError);
    }
  }, []);

  const doSend = async (userMessage: string) => {
    completeActiveStream();
    stopVoiceInput();
    resetVoiceTranscript();
    setMessages((prev) => [...prev, { id: createMessageId(), role: "user", content: userMessage }]);
    setIsLoading(true);
    setTimelineStage("retrieving");
    clearStageTimer();
    stageTimerRef.current = window.setTimeout(() => {
      setTimelineStage((prev) => (prev === "retrieving" ? "reasoning" : prev));
    }, 900);

    try {
      const imageContext = caseData.imageAnalysis
        ? [
            caseData.imageAnalysis.triage_summary || "Image analysis available.",
            `MedGemma summary: ${caseData.imageAnalysis.medgemma_analysis.slice(0, 600)}`,
          ].join("\n")
        : null;

      const response = await fetch("/api/debate-turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_history: caseData.patientHistory,
          lab_values: caseData.labValues,
          current_differential: diagnoses,
          previous_rounds: caseData.debateRounds,
          user_challenge: userMessage,
          session_id: caseData.sessionId,
          image_context: imageContext,
        }),
      });

      // Capture rate limit info from headers
      const rateInfo = parseRateLimitHeaders(response.headers);
      if (rateInfo) setRateLimitInfo(rateInfo);

      if (!response.ok) {
        // Try to read actual error details from response body
        let errorDetail = "Failed to get AI response";
        try {
          const errBody = await response.json();
          errorDetail = errBody.detail || errBody.error || errBody.message || errorDetail;
        } catch {
          // Response body wasn't JSON
        }
        
        if (isRateLimitError(response)) {
          setIsRateLimited(true);
        }
        
        throw new Error(errorDetail);
      }

      const data = await response.json();

      // Track session and orchestration status
      if (data.session_id) {
        persistSessionId(data.session_id);
      }
      setIsOrchestrated(data.orchestrated || false);

      // Track suggested test
      if (data.suggested_test) {
        setSuggestedTest(data.suggested_test);
      }

      // Clean ai_response: strip any JSON wrapper artifacts
      let aiText: string = data.ai_response || "I need more information to respond.";
      // Remove leading { "ai_response": " prefix if present
      const prefixMatch = aiText.match(/^\s*\{\s*"ai_response"\s*:\s*"?([\s\S]*)/);
      if (prefixMatch) {
        aiText = prefixMatch[1].replace(/"?\s*,?\s*"(updated_differential|suggested_test|medgemma_query)[\s\S]*$/, "").replace(/["\s}]+$/, "");
      }

      // RAG: Extract citations from response
      const citations: Citation[] = data.citations || [];
      const hasGuidelines = data.has_guidelines || false;

      setTimelineStage("finalizing");
      clearStageTimer();

      const aiMessageId = createMessageId();
      setMessages((prev) => [
        ...prev,
        {
          id: aiMessageId,
          role: "ai",
          content: "",
          citations,
          has_guidelines: hasGuidelines,
          is_streaming: true,
        },
      ]);

      await streamAiMessage(aiMessageId, aiText);
      
      // 1H: Track previous differential for change highlighting
      if (data.updated_differential?.length > 0) {
        setPreviousDiagnoses(diagnoses);
        setDiagnoses(data.updated_differential);
        updateDifferential(data.updated_differential);
      }

      // Store debate round in context (with RAG citations)
      addDebateRound({
        user_challenge: userMessage,
        ai_response: aiText,
        citations,
        has_guidelines: hasGuidelines
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "An unexpected error occurred.";
      setMessages((prev) => [...prev, {
        id: createMessageId(),
        role: "error",
        content: errorMessage,
      }]);
    } finally {
      clearStageTimer();
      setTimelineStage("idle");
      setIsStreamingResponse(false);
      setIsLoading(false);
    }
  };

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    const userMessage = input.trim();
    setInput("");
    doSend(userMessage);
  };

  // 1B: Handle suggested prompt click
  const handleSuggestedPrompt = (prompt: string) => {
    if (isLoading) return;
    doSend(prompt);
  };

  const handleRetry = () => {
    // Find the last user message, remove it + the error, then re-send
    const reversed = [...messages].reverse();
    const lastUserMsg = reversed.find(m => m.role === "user");
    if (!lastUserMsg) return;
    
    const lastUserIdx = messages.length - 1 - reversed.indexOf(lastUserMsg);
    // Remove from lastUserIdx onward (user msg + error msg)
    const cleaned = messages.slice(0, lastUserIdx);
    setMessages(cleaned);
    
    // Re-send after state update
    setTimeout(() => doSend(lastUserMsg.content), 0);
  };

  const handleEndSession = () => {
    router.push("/summary");
  };

  // Helper: find previous probability for a diagnosis name
  const getPreviousLevel = (name: string): Probability | undefined => {
    const prev = previousDiagnoses.find(d => d.name === name);
    return prev?.probability;
  };

  return (
    <main className="h-[100dvh] overflow-hidden flex flex-col bg-white">
      {/* Header */}
      <header className="shrink-0 z-50 border-b border-border bg-white px-4 md:px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            {/* 1F: Mobile sidebar toggle */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="md:hidden text-muted hover:text-foreground p-1"
              aria-label="Toggle sidebar"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <h1 className="text-lg md:text-xl font-bold tracking-tight text-foreground">
              <span className="text-teal">Sturgeon</span> <span className="hidden sm:inline">Diagnostic</span> Debate
            </h1>
            {isOrchestrated && (
              <span className="text-[10px] font-medium text-teal bg-teal-light px-2 py-0.5 rounded-full border border-teal/20 hidden sm:inline">
                Agentic Mode
              </span>
            )}
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            onPress={handleEndSession}
            className="border-border text-foreground hover:border-teal hover:text-teal hover:bg-teal-light/30 transition-colors text-xs md:text-sm"
          >
            <span className="hidden sm:inline">End Session & </span>Summarize
          </Button>
        </div>
      </header>

      {/* Main Content - Split Layout */}
      <div className="flex-1 min-h-0 overflow-hidden flex max-w-7xl mx-auto w-full relative">
        {/* 1F: Mobile sidebar overlay */}
        {sidebarOpen && (
          <div 
            className="fixed inset-0 bg-black/30 z-30 md:hidden" 
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Left Panel - Differential Diagnoses */}
        <aside className={`
          w-[85vw] max-w-[320px] md:w-80 border-r border-border bg-surface p-4 pt-6 md:pt-4 overflow-y-auto 
          fixed md:relative z-40 md:z-auto top-[55px] bottom-0 left-0 md:top-0 md:bottom-0 md:left-0 md:h-full
          transition-transform duration-200 ease-in-out
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}>
          {/* Uploaded Image Preview */}
          {hasMounted && caseData.imagePreviewUrl && (
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
                    {caseData.imageAnalysis.modality === "uncertain"
                      ? "Medical Image"
                      : caseData.imageAnalysis.image_type}
                  </p>
                  <p className="text-[10px] text-muted">
                    {caseData.imageAnalysis.modality === "uncertain"
                      ? "MedGemma direct analysis"
                      : `${caseData.imageAnalysis.modality} — ${(caseData.imageAnalysis.image_type_confidence * 100).toFixed(0)}% confidence`}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Lab Values */}
          {hasMounted && caseData.labResults && Object.keys(caseData.labResults.lab_values).length > 0 && (
            <div className="mb-4">
              <h2 className="text-xs font-bold text-muted uppercase tracking-widest mb-2 px-1">
                Lab Values
                {caseData.labResults.abnormal_values.length > 0 && (
                  <span className="ml-2 text-danger font-semibold normal-case tracking-normal">
                    ({caseData.labResults.abnormal_values.length} abnormal)
                  </span>
                )}
              </h2>
              <div className="rounded-lg border border-border bg-white p-2.5 space-y-1">
                {Object.entries(caseData.labResults.lab_values).map(([testName, details]) => {
                  const lab = details as { value?: number | string; unit?: string; reference?: string; status?: string };
                  const isAbnormal = lab.status === "high" || lab.status === "low";
                  return (
                    <div
                      key={testName}
                      className={`flex items-center justify-between py-1 px-1.5 rounded text-xs ${isAbnormal ? "bg-red-50/70" : ""}`}
                    >
                      <span className={`font-medium truncate mr-2 ${isAbnormal ? "text-danger" : "text-foreground"}`}>
                        {testName}
                      </span>
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className={isAbnormal ? "text-danger font-semibold" : "text-muted"}>
                          {lab.value ?? "—"} {lab.unit ?? ""}
                        </span>
                        {lab.status && (
                          <Chip
                            size="sm"
                            variant="soft"
                            color={
                              lab.status === "high" ? "danger"
                              : lab.status === "low" ? "warning"
                              : "success"
                            }
                            className="min-w-[20px] h-4 text-[9px]"
                          >
                            {lab.status === "high" ? "H" : lab.status === "low" ? "L" : "N"}
                          </Chip>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
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
                <div className="flex items-start justify-between gap-2 mb-1">
                  <h3 className="font-medium text-sm leading-tight text-foreground">{dx.name}</h3>
                </div>
                {/* 1H: Probability bar */}
                <div className="mb-2">
                  <ProbabilityBar level={dx.probability} previousLevel={getPreviousLevel(dx.name)} />
                </div>
                {/* 1H: Collapsible evidence sections */}
                {dx.supporting_evidence?.length > 0 && (
                  <details className="mb-1">
                    <summary className="text-[10px] text-success font-medium uppercase tracking-wider cursor-pointer select-none hover:text-success/80">
                      Supporting ({dx.supporting_evidence.length})
                    </summary>
                    <ul className="text-xs text-muted leading-relaxed space-y-0.5 mt-1 ml-2">
                      {dx.supporting_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-success shrink-0">+</span> {ev}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {dx.against_evidence?.length > 0 && (
                  <details className="mb-1">
                    <summary className="text-[10px] text-danger font-medium uppercase tracking-wider cursor-pointer select-none hover:text-danger/80">
                      Against ({dx.against_evidence.length})
                    </summary>
                    <ul className="text-xs text-muted leading-relaxed space-y-0.5 mt-1 ml-2">
                      {dx.against_evidence.map((ev, i) => (
                        <li key={i} className="flex gap-1"><span className="text-danger shrink-0">-</span> {ev}</li>
                      ))}
                    </ul>
                  </details>
                )}
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
        <section className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
          {/* Rate Limit Status */}
          {(rateLimitInfo || isRateLimited) && (
            <div className="px-3 sm:px-4 md:px-6 pt-3">
              <RateLimitStatus rateLimitInfo={rateLimitInfo} isRateLimited={isRateLimited} />
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4 md:p-6 space-y-4 min-h-0">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className="max-w-[92%] sm:max-w-[85%] md:max-w-[70%] min-w-0">
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
                      <p className="text-sm leading-relaxed wrap-break-word">{msg.content}</p>
                    </div>
                    ) : (
                      /* AI message */
                      <div className="group relative bg-surface border-l-3 border-l-teal rounded-xl px-4 py-3 pr-11">
                        {msg.is_streaming ? (
                          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{msg.content}</p>
                        ) : (
                          <Prose content={msg.content} />
                        )}
                        <div className="absolute bottom-2 right-2 flex items-center gap-1">
                          {copiedMessageId === msg.id && (
                            <span className="text-[10px] text-teal font-medium">Copied</span>
                          )}
                          <Button
                            isIconOnly
                            size="sm"
                            variant="outline"
                            onPress={() => handleCopyMessage(msg.id, msg.content)}
                            aria-label="Copy response"
                            className={`h-7 w-7 min-w-7 rounded-md border transition-opacity ${
                              copiedMessageId === msg.id
                                ? "border-teal/40 text-teal bg-teal-light/60 opacity-100"
                                : "border-border/70 bg-white/85 text-foreground/80 opacity-75 md:opacity-35 md:group-hover:opacity-90 md:group-focus-within:opacity-90"
                            }`}
                          >
                            {copiedMessageId === msg.id ? (
                              <CheckIcon className="h-3.5 w-3.5" />
                            ) : (
                              <ClipboardIcon className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        </div>
                        
                      {/* RAG: Guideline badge and citations */}
                      {msg.has_guidelines && msg.citations && msg.citations.filter((c) => (c.url || "").startsWith("https://") || (c.url || "").startsWith("http://")).length > 0 && (
                        <div className="mt-3 pt-3 border-t border-teal/20">
                          <GuidelineBadge hasGuidelines={msg.has_guidelines} />
                          <div className="mt-2 space-y-1">
                            {msg.citations.map((citation, i) => (
                              (() => {
                                const url = (citation.url || "").trim();
                                const isValidUrl = url.startsWith("https://") || url.startsWith("http://");

                                if (!isValidUrl) return null;

                                return (
                                  <a
                                    key={i}
                                    href={url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-teal-600 hover:text-teal-800 underline block"
                                  >
                                    {citation.text}
                                  </a>
                                );
                              })()
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && !isStreamingResponse && (
              <div className="flex justify-start">
                <div className="max-w-[85%] md:max-w-[70%]">
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
          <div className="border-t border-border p-3 md:p-4 bg-white">
            {/* Suggested test banner */}
            {suggestedTest && !isLoading && (
              <div className="max-w-4xl mx-auto mb-3 px-3 py-2 bg-teal-light/40 border border-teal/20 rounded-lg flex items-center gap-2">
                <span className="text-teal text-xs font-bold uppercase tracking-wider shrink-0">Suggested Test</span>
                <span className="text-sm text-foreground">{suggestedTest}</span>
              </div>
            )}

            {/* 1B: Suggested challenge prompts */}
            {!isLoading && messages.length > 0 && (
              <div className="max-w-4xl mx-auto mb-3 overflow-hidden">
                <div
                  className="flex gap-2 overflow-x-auto pb-2 px-1 snap-x snap-mandatory scrollbar-thin scrollbar-thumb-teal/30 scrollbar-track-transparent hover:scrollbar-thumb-teal/50"
                  style={{ WebkitOverflowScrolling: "touch" }}
                >
                  {SUGGESTED_PROMPTS.map((prompt, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestedPrompt(prompt)}
                      className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-teal/30 text-teal hover:bg-teal hover:text-white transition-colors whitespace-nowrap snap-start"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {(isLoading || isStreamingResponse) && timelineStage !== "idle" && (
              <div className="max-w-4xl mx-auto mb-2 flex items-center gap-2 text-[10px] text-muted">
                {([
                  ["retrieving", "retrieving guidelines"],
                  ["reasoning", "reasoning"],
                  ["finalizing", "finalizing"],
                ] as const).map(([stage, label], index) => {
                  const order: TimelineStage[] = ["retrieving", "reasoning", "finalizing"];
                  const activeIndex = order.indexOf(timelineStage);
                  const complete = index < activeIndex;
                  const active = index === activeIndex;
                  const showConnector = index < order.length - 1;

                  return (
                    <div key={stage} className="flex items-center gap-2">
                      <span
                        className={`h-1.5 w-1.5 rounded-full transition-colors ${
                          active
                            ? "bg-teal"
                            : complete
                              ? "bg-teal/45"
                              : "bg-border"
                        }`}
                      />
                      <span
                        className={`tracking-wide ${
                          active ? "text-foreground" : complete ? "text-muted" : "text-muted/80"
                        }`}
                      >
                        {label}
                      </span>
                      {showConnector && <span className="h-px w-3 bg-border" />}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="max-w-4xl mx-auto space-y-2">
              <TextArea
                aria-label="Challenge the diagnosis"
                className="w-full"
                placeholder="Challenge the diagnosis..."
                value={input}
                rows={3}
                maxLength={CHALLENGE_MAX_CHARS}
                disabled={isLoading}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                  setInput(e.target.value.slice(0, CHALLENGE_MAX_CHARS));
                }}
                onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />

              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2 text-xs text-muted">
                  <span className={input.length > CHALLENGE_MAX_CHARS * 0.9 ? "text-warning" : "text-muted"}>
                    {input.length}/{CHALLENGE_MAX_CHARS}
                  </span>
                  {isVoiceRecording && (
                    <span className="text-teal font-medium">Listening...</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {isVoiceSupported && (
                    <Button
                      variant="outline"
                      size="sm"
                      onPress={toggleVoiceInput}
                      isDisabled={isLoading}
                      className={isVoiceRecording ? "border-teal text-teal" : ""}
                    >
                      {isVoiceRecording ? "Stop Mic" : "Voice"}
                    </Button>
                  )}

                  {input.length > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      onPress={() => {
                        setInput("");
                        resetVoiceTranscript();
                      }}
                      isDisabled={isLoading}
                    >
                      Clear
                    </Button>
                  )}

                  <Button
                    variant="primary"
                    onPress={handleSend}
                    isDisabled={isLoading || !input.trim()}
                    className="bg-teal text-white hover:bg-teal/90 font-semibold px-3 sm:px-4 md:px-6 rounded-lg shrink-0"
                  >
                    <span className="hidden sm:inline">Send</span>
                    <span className="sm:hidden">→</span>
                  </Button>
                </div>
              </div>

              {interimTranscript && (
                <p className="text-xs text-muted">Live transcript: {interimTranscript}</p>
              )}
              {voiceError && <p className="text-xs text-warning">Voice input: {voiceError}</p>}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
