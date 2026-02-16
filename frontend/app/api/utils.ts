// Helper to pass through rate limit headers from backend to frontend
export function copyRateLimitHeaders(
  sourceHeaders: Headers,
  targetHeaders: Headers
): void {
  const rateLimitHeaders = [
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Window",
    "Retry-After",
  ];

  rateLimitHeaders.forEach((header) => {
    const value = sourceHeaders.get(header);
    if (value) {
      targetHeaders.set(header, value);
    }
  });
}
