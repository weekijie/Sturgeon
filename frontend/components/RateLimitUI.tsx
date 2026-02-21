"use client";

import { useMemo } from "react";

interface RateLimitInfo {
  limit: number;
  remaining: number;
  window: number;
  retryAfter?: number;
}

interface RateLimitUIProps {
  rateLimitInfo: RateLimitInfo | null;
  isRateLimited: boolean;
}

export function RateLimitStatus({ rateLimitInfo, isRateLimited }: RateLimitUIProps) {
  const countdown = useMemo(() => {
    if (!isRateLimited || !rateLimitInfo?.retryAfter) return 0;
    return Math.max(0, Math.floor(rateLimitInfo.retryAfter));
  }, [isRateLimited, rateLimitInfo?.retryAfter]);

  if (isRateLimited) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <svg
            className="w-5 h-5 text-amber-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="font-semibold text-amber-800">
            Rate Limit Exceeded
          </span>
        </div>
        <p className="text-sm text-amber-700 mb-2">
          You have made too many requests. Please wait before trying again.
        </p>
        {countdown > 0 && (
          <div className="flex items-center gap-2 text-amber-800">
            <span className="text-sm">Retry in:</span>
            <span className="font-mono font-bold text-lg">
              {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, "0")}
            </span>
          </div>
        )}
      </div>
    );
  }

  if (!rateLimitInfo) return null;

  const { limit, remaining, window } = rateLimitInfo;
  const percentage = (remaining / limit) * 100;
  
  let barColor = "bg-green-500";
  if (percentage < 30) barColor = "bg-red-500";
  else if (percentage < 60) barColor = "bg-yellow-500";

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-medium text-slate-600">
          API Quota
        </span>
        <span className="text-xs text-slate-500">
          {remaining} / {limit} remaining
        </span>
      </div>
      <div className="w-full bg-slate-200 rounded-full h-2">
        <div
          className={`${barColor} h-2 rounded-full transition-all duration-300`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 mt-1">
        Resets in {Math.ceil(window / 60)} minute{window > 60 ? 's' : ''}
      </p>
    </div>
  );
}

export function parseRateLimitHeaders(headers: Headers): RateLimitInfo | null {
  const limit = headers.get("X-RateLimit-Limit");
  const remaining = headers.get("X-RateLimit-Remaining");
  const window = headers.get("X-RateLimit-Window");
  const retryAfter = headers.get("Retry-After");

  if (!limit || !remaining || !window) return null;

  return {
    limit: parseInt(limit, 10),
    remaining: parseInt(remaining, 10),
    window: parseInt(window, 10),
    retryAfter: retryAfter ? parseInt(retryAfter, 10) : undefined,
  };
}

export function isRateLimitError(response: Response): boolean {
  return response.status === 429;
}
