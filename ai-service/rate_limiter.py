"""
Rate Limiting Module for Sturgeon AI Service

Provides IP-based rate limiting for all API endpoints to prevent abuse.
Uses a sliding window algorithm with per-endpoint configurable limits.
"""

import time
from collections import defaultdict
from typing import Tuple, Optional
from fastapi import HTTPException, Request
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple rate limiter to prevent abuse.
    Tracks requests per IP with sliding window.
    """
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)  # IP -> list of timestamps
    
    def is_allowed(self, identifier: str) -> Tuple[bool, int, int]:
        """
        Check if request is allowed for given identifier.
        
        Args:
            identifier: IP address or other unique identifier
            
        Returns:
            Tuple of (is_allowed, requests_remaining, retry_after_seconds)
            retry_after_seconds is 0 if allowed, otherwise seconds until next request allowed
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[identifier] = [
            ts for ts in self.requests[identifier] 
            if ts > window_start
        ]
        
        # Check limit
        current_count = len(self.requests[identifier])
        if current_count >= self.max_requests:
            # Calculate retry-after time
            if self.requests[identifier]:
                oldest_request = min(self.requests[identifier])
                retry_after = int(oldest_request + self.window_seconds - now) + 1
            else:
                retry_after = self.window_seconds
            return False, 0, retry_after
        
        # Record this request
        self.requests[identifier].append(now)
        
        return True, self.max_requests - current_count - 1, 0
    
    def reset(self, identifier: str):
        """Reset rate limit for identifier."""
        if identifier in self.requests:
            del self.requests[identifier]


class RateLimitConfig:
    """Configuration for endpoint-specific rate limits."""
    
    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        identifier_header: Optional[str] = None
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.identifier_header = identifier_header


# Endpoint-specific rate limit configurations
# More expensive endpoints (GPU-heavy) get lower limits
ENDPOINT_LIMITS = {
    # Image analysis is expensive - 5 per minute
    "analyze-image": RateLimitConfig(max_requests=5, window_seconds=60),
    
    # File uploads with PDF processing - 5 per minute
    "extract-labs-file": RateLimitConfig(max_requests=5, window_seconds=60),
    
    # Differential generation - moderate cost - 10 per minute
    "differential": RateLimitConfig(max_requests=10, window_seconds=60),
    
    # Lab extraction from text - 15 per minute
    "extract-labs": RateLimitConfig(max_requests=15, window_seconds=60),
    
    # Debate turns are chat-like - 20 per minute
    "debate-turn": RateLimitConfig(max_requests=20, window_seconds=60),
    
    # Summary generation - 10 per minute
    "summary": RateLimitConfig(max_requests=10, window_seconds=60),
}


class RateLimitManager:
    """Manages rate limiters for all endpoints."""
    
    def __init__(self):
        self.limiters: dict[str, RateLimiter] = {}
        
    def get_limiter(self, endpoint: str) -> RateLimiter:
        """Get or create rate limiter for an endpoint."""
        if endpoint not in self.limiters:
            config = ENDPOINT_LIMITS.get(endpoint, RateLimitConfig())
            self.limiters[endpoint] = RateLimiter(
                max_requests=config.max_requests,
                window_seconds=config.window_seconds
            )
        return self.limiters[endpoint]
    
    def check_rate_limit(self, endpoint: str, request: Request) -> Tuple[bool, dict]:
        """
        Check if request is within rate limit for endpoint.
        
        Args:
            endpoint: Endpoint identifier (e.g., "analyze-image")
            request: FastAPI request object
            
        Returns:
            Tuple of (allowed, headers_dict)
            If not allowed, raises HTTPException with 429 status
        """
        limiter = self.get_limiter(endpoint)
        
        # Get client IP
        # Check X-Forwarded-For header first (for proxies/load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        allowed, remaining, retry_after = limiter.is_allowed(client_ip)
        
        # Build headers
        headers = {
            "X-RateLimit-Limit": str(limiter.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Window": str(limiter.window_seconds),
        }
        
        if not allowed:
            headers["Retry-After"] = str(retry_after)
            logger.warning(
                f"Rate limit exceeded for {endpoint} from {client_ip}. "
                f"Limit: {limiter.max_requests}/{limiter.window_seconds}s. "
                f"Retry after: {retry_after}s"
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers=headers
            )
        
        return True, headers


# Global rate limit manager instance
rate_limit_manager = RateLimitManager()


def check_rate_limit(endpoint: str, request: Request) -> dict:
    """
    Convenience function to check rate limit and return headers.
    
    Args:
        endpoint: Endpoint identifier
        request: FastAPI request object
        
    Returns:
        Dictionary of rate limit headers to include in response
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    _, headers = rate_limit_manager.check_rate_limit(endpoint, request)
    return headers
