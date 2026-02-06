"use client";

import { useState } from "react";
import { Card, Button, TextField, Chip } from "@heroui/react";

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
    const colorMap = {
        high: "success",
        medium: "warning",
        low: "danger",
    } as const;

    return (
        <Chip variant={colorMap[level]} size="sm">
            {level.charAt(0).toUpperCase() + level.slice(1)}
        </Chip>
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
        <main className="min-h-screen flex flex-col">
            {/* Header */}
            <header className="border-b border-border px-6 py-4">
                <div className="flex items-center justify-between max-w-7xl mx-auto">
                    <h1 className="text-xl font-bold">
                        <span className="text-teal">Sturgeon</span> Diagnostic Debate
                    </h1>
                    <Button variant="secondary" size="sm">
                        End Session
                    </Button>
                </div>
            </header>

            {/* Main Content - Split Layout */}
            <div className="flex-1 flex max-w-7xl mx-auto w-full">
                {/* Left Panel - Differential Diagnoses */}
                <aside className="w-80 border-r border-border p-4 overflow-y-auto">
                    <h2 className="text-sm font-semibold text-muted uppercase tracking-wide mb-4">
                        Differential Diagnoses
                    </h2>
                    <div className="space-y-3">
                        {diagnoses.map((dx) => (
                            <Card key={dx.id} className="p-3">
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <h3 className="font-medium text-sm leading-tight">{dx.name}</h3>
                                    <ProbabilityBadge level={dx.probability as Probability} />
                                </div>
                                <p className="text-xs text-muted leading-relaxed">
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
                            <TextField
                                className="flex-1"
                                placeholder="Challenge the diagnosis..."
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                            />
                            <Button variant="primary" onPress={handleSend}>
                                Send
                            </Button>
                        </div>
                    </div>
                </section>
            </div>
        </main>
    );
}
