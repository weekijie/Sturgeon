"use client";

import { useEffect, useState } from "react";
import { Spinner, CloseButton } from "@heroui/react";
import { WarmupStatus } from "../lib/useWarmup";

interface WarmupToastProps {
  status: WarmupStatus;
}

export function WarmupToast({ status }: WarmupToastProps) {
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

  if (dismissed || (status !== "warming" && status !== "ready")) return null;

  const handleDismiss = () => {
    setDismissed(true);
  };

  const isWarming = status === "warming";

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm animate-in slide-in-from-bottom-4 duration-300">
      <div
        className={`
          flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border
          ${isWarming 
            ? "bg-accent text-accent-foreground border-accent/20" 
            : "bg-success text-success-foreground border-success/20"
          }
        `}
      >
        {isWarming ? (
          <>
            <Spinner size="sm" color="current" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">AI warming up...</p>
              <p className="text-xs opacity-90">First load takes 2-3 minutes. Checking status with progressive backoff...</p>
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
