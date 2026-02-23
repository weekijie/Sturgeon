"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionResultListLike {
  readonly length: number;
  [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLike;
}

interface SpeechRecognitionErrorEventLike extends Event {
  readonly error: string;
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onstart: ((event: Event) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: ((event: Event) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type BrowserWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

interface UseSpeechToTextOptions {
  lang?: string;
  continuous?: boolean;
  interimResults?: boolean;
  onFinalTranscript?: (text: string) => void;
}

interface UseSpeechToTextResult {
  isSupported: boolean;
  isRecording: boolean;
  interimTranscript: string;
  finalTranscript: string;
  error: string | null;
  startListening: () => void;
  stopListening: () => void;
  toggleListening: () => void;
  resetTranscript: () => void;
}

function mapSpeechError(errorCode: string): string {
  switch (errorCode) {
    case "not-allowed":
      return "Microphone permission denied.";
    case "no-speech":
      return "No speech detected. Please try again.";
    case "audio-capture":
      return "No microphone detected.";
    case "network":
      return "Speech recognition network error.";
    case "aborted":
      return "Voice input stopped.";
    default:
      return "Voice input failed. Please try again.";
  }
}

export function useSpeechToText({
  lang = "en-US",
  continuous = true,
  interimResults = true,
  onFinalTranscript,
}: UseSpeechToTextOptions = {}): UseSpeechToTextResult {
  const [isSupported] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const speechWindow = window as BrowserWindow;
    return Boolean(
      speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition,
    );
  });
  const [isRecording, setIsRecording] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const onFinalTranscriptRef = useRef(onFinalTranscript);

  useEffect(() => {
    onFinalTranscriptRef.current = onFinalTranscript;
  }, [onFinalTranscript]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const speechWindow = window as BrowserWindow;
    const SpeechRecognitionImpl =
      speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;

    if (!SpeechRecognitionImpl) {
      return;
    }

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = lang;
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setError(null);
      setIsRecording(true);
    };

    recognition.onresult = (event) => {
      let interim = "";
      const finalParts: string[] = [];

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0]?.transcript?.trim() ?? "";

        if (!transcript) {
          continue;
        }

        if (result.isFinal) {
          finalParts.push(transcript);
        } else {
          interim = `${interim}${transcript} `;
        }
      }

      setInterimTranscript(interim.trim());

      if (finalParts.length > 0) {
        const finalText = finalParts.join(" ").trim();
        setFinalTranscript((prev) =>
          prev ? `${prev} ${finalText}` : finalText,
        );
        if (onFinalTranscriptRef.current) {
          onFinalTranscriptRef.current(finalText);
        }
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== "aborted") {
        setError(mapSpeechError(event.error));
      }
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
      setInterimTranscript("");
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.onstart = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.abort();
      recognitionRef.current = null;
    };
  }, [lang, continuous, interimResults]);

  const startListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setError("Voice input is not supported in this browser.");
      return;
    }

    try {
      setError(null);
      recognition.start();
    } catch (startError) {
      const message =
        startError instanceof Error
          ? startError.message
          : "Unable to start voice input.";
      if (!message.toLowerCase().includes("already started")) {
        setError(message);
      }
    }
  }, []);

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }

    recognition.stop();
    setIsRecording(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (isRecording) {
      stopListening();
      return;
    }
    startListening();
  }, [isRecording, startListening, stopListening]);

  const resetTranscript = useCallback(() => {
    setInterimTranscript("");
    setFinalTranscript("");
    setError(null);
  }, []);

  return {
    isSupported,
    isRecording,
    interimTranscript,
    finalTranscript,
    error,
    startListening,
    stopListening,
    toggleListening,
    resetTranscript,
  };
}
