"use client";

import { createContext, useContext, useState, ReactNode } from "react";

// Types matching FastAPI backend
export interface Diagnosis {
  name: string;
  probability: "high" | "medium" | "low";
  supporting_evidence: string[];
  against_evidence: string[];
  suggested_tests: string[];
}

export interface DebateRound {
  user_challenge: string;
  ai_response: string;
}

export interface ImageFinding {
  label: string;
  score: number;
}

export interface ImageAnalysis {
  image_type: string;
  image_type_confidence: number;
  modality: string;
  triage_findings: ImageFinding[];
  triage_summary: string;
  medgemma_analysis: string;
}

export interface LabValue {
  value: number | string;
  unit: string;
  reference: string;
  status: "normal" | "high" | "low";
}

export interface LabResults {
  lab_values: Record<string, LabValue>;
  abnormal_values: string[];
  raw_text?: string;
}

export interface CaseData {
  patientHistory: string;
  labValues: Record<string, unknown>;
  labResults: LabResults | null; // Structured lab extraction results
  differential: Diagnosis[];
  debateRounds: DebateRound[];
  imageAnalysis: ImageAnalysis | null;
  imagePreviewUrl: string | null; // data URL for image preview in debate
}

interface CaseContextType {
  caseData: CaseData;
  setPatientHistory: (history: string) => void;
  setLabValues: (labs: Record<string, unknown>) => void;
  setLabResults: (results: LabResults) => void;
  setDifferential: (diagnoses: Diagnosis[]) => void;
  addDebateRound: (round: DebateRound) => void;
  updateDifferential: (diagnoses: Diagnosis[]) => void;
  setImageAnalysis: (analysis: ImageAnalysis, previewUrl: string) => void;
  resetCase: () => void;
}

const defaultCaseData: CaseData = {
  patientHistory: "",
  labValues: {},
  labResults: null,
  differential: [],
  debateRounds: [],
  imageAnalysis: null,
  imagePreviewUrl: null,
};

const CaseContext = createContext<CaseContextType | null>(null);

export function CaseProvider({ children }: { children: ReactNode }) {
  const [caseData, setCaseData] = useState<CaseData>(defaultCaseData);

  const setPatientHistory = (history: string) => {
    setCaseData((prev) => ({ ...prev, patientHistory: history }));
  };

  const setLabValues = (labs: Record<string, unknown>) => {
    setCaseData((prev) => ({ ...prev, labValues: labs }));
  };

  const setLabResults = (results: LabResults) => {
    setCaseData((prev) => ({
      ...prev,
      labResults: results,
      labValues: results.lab_values, // Keep labValues in sync
    }));
  };

  const setDifferential = (diagnoses: Diagnosis[]) => {
    setCaseData((prev) => ({ ...prev, differential: diagnoses }));
  };

  const addDebateRound = (round: DebateRound) => {
    setCaseData((prev) => ({
      ...prev,
      debateRounds: [...prev.debateRounds, round],
    }));
  };

  const updateDifferential = (diagnoses: Diagnosis[]) => {
    setCaseData((prev) => ({ ...prev, differential: diagnoses }));
  };

  const setImageAnalysis = (analysis: ImageAnalysis, previewUrl: string) => {
    setCaseData((prev) => ({
      ...prev,
      imageAnalysis: analysis,
      imagePreviewUrl: previewUrl,
    }));
  };

  const resetCase = () => {
    setCaseData(defaultCaseData);
  };

  return (
    <CaseContext.Provider
      value={{
        caseData,
        setPatientHistory,
        setLabValues,
        setLabResults,
        setDifferential,
        addDebateRound,
        updateDifferential,
        setImageAnalysis,
        resetCase,
      }}
    >
      {children}
    </CaseContext.Provider>
  );
}

export function useCase() {
  const context = useContext(CaseContext);
  if (!context) {
    throw new Error("useCase must be used within a CaseProvider");
  }
  return context;
}
