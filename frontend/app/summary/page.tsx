"use client";

import { Card, Button, Divider, Accordion, AccordionItem } from "@heroui/react";
import { useState } from "react";

// Mock data
const finalDiagnosis = {
    name: "Type 2 Diabetes Mellitus",
    confidence: 92,
    reasoning: "The patient presents with the classic triad of polyuria, polydipsia, and unexplained weight loss. Lab results show significantly elevated HbA1c (8.2%) and fasting plasma glucose (142 mg/dL), both above diagnostic thresholds. The presence of metabolic syndrome markers further supports this diagnosis.",
    nextSteps: [
        "Initiate Metformin 500mg daily",
        "Refer to diabetes educator for lifestyle management",
        "Schedule dilated eye exam",
        "Repeat HbA1c in 3 months"
    ]
};

const ruledOut = [
    {
        id: "dx2",
        name: "Diabetes Insipidus",
        reasoning: "Ruled out due to normal urine specific gravity and no hypernatremia. The polyuria is osmotic secondary to glucosuria, not due to ADH deficiency or resistance."
    },
    {
        id: "dx3",
        name: "Hyperthyroidism",
        reasoning: "TSH and Free T4 were within normal limits, excluding thyroid dysfunction as the primary cause of weight loss and fatigue."
    }
];

export default function SummaryPage() {
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
                    <Button variant="bordered" onPress={() => window.location.href = "/"} className="hover:border-teal hover:text-teal transition-colors">
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
                                <h3 className="text-2xl font-bold">{finalDiagnosis.name}</h3>
                            </div>
                            <div className="text-right">
                                <div className="text-3xl font-bold text-teal">
                                    {finalDiagnosis.confidence}%
                                </div>
                                <div className="text-xs text-muted">Confidence</div>
                            </div>
                        </div>

                        <Divider className="my-4" />

                        <div className="space-y-4">
                            <div>
                                <h4 className="font-semibold mb-2">Clinical Reasoning</h4>
                                <p className="text-muted leading-relaxed">
                                    {finalDiagnosis.reasoning}
                                </p>
                            </div>

                            <div>
                                <h4 className="font-semibold mb-2">Recommended Next Steps</h4>
                                <ul className="list-disc list-inside space-y-1 text-muted">
                                    {finalDiagnosis.nextSteps.map((step, i) => (
                                        <li key={i}>{step}</li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    </div>
                </Card>

                {/* Ruled Out Diagnoses */}
                <div className="space-y-4">
                    <h3 className="text-lg font-semibold px-2">Ruled Out Differentials</h3>
                    <Accordion variant="splitted">
                        {ruledOut.map((dx) => (
                            <AccordionItem
                                key={dx.id}
                                title={
                                    <div className="flex items-center gap-2">
                                        <span className="line-through text-muted">{dx.name}</span>
                                    </div>
                                }
                            >
                                <div className="pb-2">
                                    <p className="text-sm text-muted leading-relaxed">
                                        {dx.reasoning}
                                    </p>
                                </div>
                            </AccordionItem>
                        ))}
                    </Accordion>
                </div>

                {/* Timeline / Audit Trail Placeholder */}
                <div className="text-center pt-8">
                    <p className="text-xs text-muted uppercase tracking-widest">
                        Session ID: #STG-2026-8A92
                    </p>
                </div>

            </div>
        </main>
    );
}
