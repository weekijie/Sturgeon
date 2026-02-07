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

export interface CaseData {
  patientHistory: string;
  labValues: Record<string, unknown>;
  differential: Diagnosis[];
  debateRounds: DebateRound[];
}

interface CaseContextType {
  caseData: CaseData;
  setPatientHistory: (history: string) => void;
  setLabValues: (labs: Record<string, unknown>) => void;
  setDifferential: (diagnoses: Diagnosis[]) => void;
  addDebateRound: (round: DebateRound) => void;
  updateDifferential: (diagnoses: Diagnosis[]) => void;
  resetCase: () => void;
}

const defaultCaseData: CaseData = {
  patientHistory: "",
  labValues: {},
  differential: [],
  debateRounds: [],
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

  const resetCase = () => {
    setCaseData(defaultCaseData);
  };

  return (
    <CaseContext.Provider
      value={{
        caseData,
        setPatientHistory,
        setLabValues,
        setDifferential,
        addDebateRound,
        updateDifferential,
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
