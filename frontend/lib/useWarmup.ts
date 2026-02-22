"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const INITIAL_POLL_DELAY = 0; // Immediate first ping to trigger cold start
const POLL_INTERVALS = [20000, 30000, 45000]; // Backoff: 20s → 30s → 45s (cap)
const MAX_BACKOFF_INDEX = POLL_INTERVALS.length - 1;
const REQUEST_TIMEOUT = 15000; // 15s timeout per request

export type WarmupStatus = "idle" | "warming" | "ready" | "error";

interface UseWarmupResult {
  status: WarmupStatus;
  isWarming: boolean;
  isReady: boolean;
  error: string | null;
  startWarmup: () => void;
}

export function useWarmup(autoStart = true): UseWarmupResult {
  const [status, setStatus] = useState<WarmupStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const backoffIndexRef = useRef(0);
  const mountedRef = useRef(true);

  const checkHealth = useCallback(async (): Promise<boolean> => {
    if (inFlightRef.current) {
      return false;
    }
    
    inFlightRef.current = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
    
    try {
      const response = await fetch("/api/health", {
        method: "GET",
        signal: controller.signal,
      });

      if (response.ok) {
        const data = await response.json();
        return data.status === "healthy";
      }
      return false;
    } catch {
      return false;
    } finally {
      clearTimeout(timeoutId);
      inFlightRef.current = false;
    }
  }, []);

  const startWarmup = useCallback(() => {
    if (status !== "idle") return;
    setStatus("warming");
    setError(null);
    backoffIndexRef.current = 0;
  }, [status]);

  useEffect(() => {
    mountedRef.current = true;
    
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (status !== "warming") return;

    let timeoutId: NodeJS.Timeout;

    const poll = async () => {
      const isHealthy = await checkHealth();
      
      if (!mountedRef.current) return;

      if (isHealthy) {
        setStatus("ready");
        return;
      }

      const interval = POLL_INTERVALS[backoffIndexRef.current];
      if (backoffIndexRef.current < MAX_BACKOFF_INDEX) {
        backoffIndexRef.current++;
      }

      timeoutId = setTimeout(poll, interval);
    };

    if (INITIAL_POLL_DELAY === 0) {
      poll();
    } else {
      timeoutId = setTimeout(poll, INITIAL_POLL_DELAY);
    }

    return () => {
      clearTimeout(timeoutId);
    };
  }, [status, checkHealth]);

  useEffect(() => {
    if (autoStart) {
      startWarmup();
    }
  }, [autoStart, startWarmup]);

  return {
    status,
    isWarming: status === "warming",
    isReady: status === "ready",
    error,
    startWarmup,
  };
}
