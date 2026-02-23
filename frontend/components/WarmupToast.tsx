"use client";

import { useEffect, useState } from "react";
import { Spinner, CloseButton } from "@heroui/react";
import { WarmupStatus } from "../lib/useWarmup";

interface WarmupToastProps {
  status: WarmupStatus;
  error?: string | null;
  autoStart?: boolean;
}

export function WarmupToast({ status, error, autoStart = true }: WarmupToastProps) {
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (status === "warming") {
      const resetTimer = setTimeout(() => setDismissed(false), 0);
      return () => clearTimeout(resetTimer);
    }

    if (status === "ready") {
      const hideTimer = setTimeout(() => setDismissed(true), 2000);
      return () => clearTimeout(hideTimer);
    }

    return undefined;
  }, [status]);

  if (dismissed || (status !== "warming" && status !== "ready" && status !== "error")) return null;

  const handleDismiss = () => {
    setDismissed(true);
  };

  const isWarming = status === "warming";
  const isError = status === "error";

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm animate-in slide-in-from-bottom-4 duration-300">
      <div
        className={`
          flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border
          ${isWarming 
            ? "bg-accent text-accent-foreground border-accent/20" 
            : isError
              ? "bg-warning text-warning-foreground border-warning/20"
              : "bg-success text-success-foreground border-success/20"
          }
        `}
      >
        {isWarming ? (
          <>
            <Spinner size="sm" color="current" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">AI warming up...</p>
                <p className="text-xs opacity-90">
                  {autoStart
                  ? "First load takes 2-3 minutes. Checking now, then near 2 minutes."
                  : "Warmup started on demand. Checking now, then near 2 minutes."}
                </p>
              </div>
            <CloseButton
              className="text-current opacity-70 hover:opacity-100"
              onPress={handleDismiss}
              aria-label="Dismiss"
            />
          </>
        ) : isError ? (
          <>
            <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M4.93 19h14.14c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.2 16c-.77 1.33.19 3 1.73 3z" />
            </svg>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">Warmup paused</p>
              <p className="text-xs opacity-90">{error || "Warmup checks paused to save credits. It will resume on analysis."}</p>
            </div>
            <CloseButton
              className="text-current opacity-70 hover:opacity-100"
              onPress={handleDismiss}
              aria-label="Dismiss"
            />
          </>
        ) : (
          <>
            <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-sm font-medium">AI ready!</p>
          </>
        )}
      </div>
    </div>
  );
}
