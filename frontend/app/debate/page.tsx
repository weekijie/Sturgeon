"use client";

import { useState } from "react";
import { Card, Button, Input } from "@heroui/react";

// Mock data for demonstration
const mockDiagnoses = [
    { id: 1, name: "Type 2 Diabetes Mellitus", probability: "high", reasoning: "Elevated HbA1c (8.2%), fasting glucose 142 mg/dL, polyuria symptoms" },
    { id: 2, name: "Metabolic Syndrome", probability: "medium", reasoning: "Central obesity, elevated triglycerides, low HDL" },
    { id: 3, name: "Chronic Kidney Disease Stage 2", probability: "low", reasoning: "Slightly elevated creatinine, needs confirmation with GFR calculation" },
];

const mockMessages = [
    { role: "ai", content: "Based on the lab results, I've identified 3 potential diagnoses. The primary concern is Type 2 Diabetes Mellitus given the elevated HbA1c and fasting glucose levels." },
    { role: "user", content: "What about the kidney function? The creatinine is borderline." },
    { role: "ai", content: "Good observation. The creatinine of 1.3 mg/dL is mildly elevated, but we need to calculate the eGFR to properly stage any kidney involvement. In diabetic patients, monitoring kidney function is critical." },
];

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

export default function DebatePage() {
    const [messages, setMessages] = useState(mockMessages);
    const [input, setInput] = useState("");
    const [diagnoses] = useState(mockDiagnoses);

    const handleSend = () => {
        if (!input.trim()) return;

        setMessages([...messages, { role: "user", content: input }]);
        setInput("");

        // Simulate AI response
        setTimeout(() => {
            setMessages(prev => [...prev, {
                role: "ai",
                content: "That's an interesting point. Let me reconsider the differential based on your challenge..."
            }]);
        }, 1000);
    };

    return (
        <main className="min-h-screen flex flex-col bg-background selection:bg-teal/30">
            {/* Header - Glassmorphism */}
            <header className="sticky top-0 z-50 border-b border-white/10 bg-background/80 backdrop-blur-md px-6 py-4 shadow-sm">
                <div className="flex items-center justify-between max-w-7xl mx-auto">
                    <h1 className="text-xl font-bold tracking-tight">
                        <span className="text-teal drop-shadow-sm">Sturgeon</span> Diagnostic Debate
                    </h1>
                    <Button variant="bordered" size="sm" className="hover:border-danger hover:text-danger hover:bg-danger/10 transition-colors">
                        End Session
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
                        {diagnoses.map((dx) => (
                            <Card
                                key={dx.id}
                                className="p-3 transition-all duration-300 hover:border-teal/50 hover:shadow-lg hover:shadow-teal/5 hover:-translate-y-0.5 cursor-default group"
                            >
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <h3 className="font-medium text-sm leading-tight group-hover:text-teal transition-colors">{dx.name}</h3>
                                    <ProbabilityBadge level={dx.probability as Probability} />
                                </div>
                                <p className="text-xs text-muted leading-relaxed group-hover:text-foreground/80 transition-colors">
                                    {dx.reasoning}
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
                            />
                            <Button variant="solid" onPress={handleSend}>
                                Send
                            </Button>
                        </div>
                    </div>
                </section>
            </div>
        </main>
    );
}
