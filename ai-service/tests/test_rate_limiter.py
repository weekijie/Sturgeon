"""
Tests for rate limiting functionality.

This module tests the RateLimiter class and RateLimitManager
to ensure proper rate limiting behavior across all endpoints.
"""

import time
import unittest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException, Request

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitManager,
    check_rate_limit,
    ENDPOINT_LIMITS
)


class TestRateLimiter(unittest.TestCase):
    """Test the RateLimiter class."""
    
    def test_init(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        self.assertEqual(limiter.max_requests, 5)
        self.assertEqual(limiter.window_seconds, 60)
        self.assertEqual(limiter.requests, {})
    
    def test_is_allowed_first_request(self):
        """Test that first request is always allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        allowed, remaining, retry_after = limiter.is_allowed("127.0.0.1")
        
        self.assertTrue(allowed)
        self.assertEqual(remaining, 4)  # 5 - 0 - 1 = 4
        self.assertEqual(retry_after, 0)
    
    def test_is_allowed_multiple_requests(self):
        """Test multiple requests within limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        # Make 3 requests
        for i in range(3):
            allowed, remaining, _ = limiter.is_allowed("127.0.0.1")
            self.assertTrue(allowed)
            self.assertEqual(remaining, 4 - i)
    
    def test_is_allowed_limit_exceeded(self):
        """Test that requests beyond limit are denied."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        # Make 3 allowed requests
        for _ in range(3):
            allowed, _, _ = limiter.is_allowed("127.0.0.1")
            self.assertTrue(allowed)
        
        # 4th request should be denied
        allowed, remaining, retry_after = limiter.is_allowed("127.0.0.1")
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreater(retry_after, 0)
    
    def test_is_allowed_different_ips(self):
        """Test that different IPs have separate limits."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        # Use up limit for IP1
        for _ in range(3):
            limiter.is_allowed("192.168.1.1")
        
        # IP1 should be blocked
        allowed, _, _ = limiter.is_allowed("192.168.1.1")
        self.assertFalse(allowed)
        
        # IP2 should still be allowed
        allowed, remaining, _ = limiter.is_allowed("192.168.1.2")
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)
    
    def test_window_expiration(self):
        """Test that old requests expire from window."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        
        # Use up limit
        limiter.is_allowed("127.0.0.1")
        limiter.is_allowed("127.0.0.1")
        
        # Should be blocked
        allowed, _, _ = limiter.is_allowed("127.0.0.1")
        self.assertFalse(allowed)
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should be allowed again
        allowed, remaining, _ = limiter.is_allowed("127.0.0.1")
        self.assertTrue(allowed)
        self.assertEqual(remaining, 1)
    
    def test_reset(self):
        """Test that reset clears rate limit for identifier."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        # Use up limit
        limiter.is_allowed("127.0.0.1")
        limiter.is_allowed("127.0.0.1")
        
        # Should be blocked
        allowed, _, _ = limiter.is_allowed("127.0.0.1")
        self.assertFalse(allowed)
        
        # Reset
        limiter.reset("127.0.0.1")
        
        # Should be allowed
        allowed, remaining, _ = limiter.is_allowed("127.0.0.1")
        self.assertTrue(allowed)
        self.assertEqual(remaining, 1)


class TestRateLimitConfig(unittest.TestCase):
    """Test the RateLimitConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        self.assertEqual(config.max_requests, 10)
        self.assertEqual(config.window_seconds, 60)
        self.assertIsNone(config.identifier_header)
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = RateLimitConfig(max_requests=5, window_seconds=30)
        self.assertEqual(config.max_requests, 5)
        self.assertEqual(config.window_seconds, 30)


class TestRateLimitManager(unittest.TestCase):
    """Test the RateLimitManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = RateLimitManager()
    
    def test_get_limiter_creates_new(self):
        """Test that get_limiter creates new limiter for unknown endpoint."""
        limiter = self.manager.get_limiter("test-endpoint")
        self.assertIsInstance(limiter, RateLimiter)
        self.assertEqual(limiter.max_requests, 10)  # Default
        self.assertEqual(limiter.window_seconds, 60)  # Default
    
    def test_get_limiter_uses_existing(self):
        """Test that get_limiter returns existing limiter."""
        limiter1 = self.manager.get_limiter("test-endpoint")
        limiter2 = self.manager.get_limiter("test-endpoint")
        self.assertIs(limiter1, limiter2)
    
    def test_get_limiter_uses_endpoint_config(self):
        """Test that get_limiter uses endpoint-specific configuration."""
        # analyze-image should have lower limit
        limiter = self.manager.get_limiter("analyze-image")
        self.assertEqual(limiter.max_requests, 5)
        self.assertEqual(limiter.window_seconds, 60)
        
        # debate-turn should have higher limit
        limiter = self.manager.get_limiter("debate-turn")
        self.assertEqual(limiter.max_requests, 20)
        self.assertEqual(limiter.window_seconds, 60)
    
    @patch('rate_limiter.RateLimiter')
    def test_check_rate_limit_allowed(self, mock_limiter_class):
        """Test that check_rate_limit allows requests within limit."""
        # Mock the limiter
        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (True, 4, 0)
        mock_limiter.max_requests = 5
        mock_limiter.window_seconds = 60
        mock_limiter_class.return_value = mock_limiter
        
        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        # Should not raise - returns tuple of (allowed, headers)
        allowed, headers = self.manager.check_rate_limit("test-endpoint", mock_request)
        
        self.assertTrue(allowed)
        self.assertEqual(headers["X-RateLimit-Limit"], "5")
        self.assertEqual(headers["X-RateLimit-Remaining"], "4")
        self.assertEqual(headers["X-RateLimit-Window"], "60")
        self.assertNotIn("Retry-After", headers)
    
    @patch('rate_limiter.RateLimiter')
    def test_check_rate_limit_denied(self, mock_limiter_class):
        """Test that check_rate_limit raises 429 when limit exceeded."""
        # Mock the limiter
        mock_limiter = MagicMock()
        mock_limiter.is_allowed.return_value = (False, 0, 30)
        mock_limiter.max_requests = 5
        mock_limiter.window_seconds = 60
        mock_limiter_class.return_value = mock_limiter
        
        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        # Should raise HTTPException
        with self.assertRaises(HTTPException) as context:
            self.manager.check_rate_limit("test-endpoint", mock_request)
        
        self.assertEqual(context.exception.status_code, 429)
        self.assertIn("Retry-After", context.exception.headers)
        self.assertEqual(context.exception.headers["Retry-After"], "30")
    
    def test_check_rate_limit_x_forwarded_for(self):
        """Test that X-Forwarded-For header is used for IP."""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        mock_request.client.host = "127.0.0.1"
        
        # Should use first IP from X-Forwarded-For
        limiter = self.manager.get_limiter("test")
        with patch.object(limiter, 'is_allowed') as mock_is_allowed:
            mock_is_allowed.return_value = (True, 4, 0)
            self.manager.check_rate_limit("test", mock_request)
            mock_is_allowed.assert_called_once_with("10.0.0.1")


class TestEndpointLimits(unittest.TestCase):
    """Test that endpoint limits are configured correctly."""
    
    def test_analyze_image_limit(self):
        """Test analyze-image has appropriate limits."""
        config = ENDPOINT_LIMITS["analyze-image"]
        self.assertEqual(config.max_requests, 5)
        self.assertEqual(config.window_seconds, 60)
    
    def test_extract_labs_file_limit(self):
        """Test extract-labs-file has appropriate limits."""
        config = ENDPOINT_LIMITS["extract-labs-file"]
        self.assertEqual(config.max_requests, 5)
        self.assertEqual(config.window_seconds, 60)
    
    def test_differential_limit(self):
        """Test differential has appropriate limits."""
        config = ENDPOINT_LIMITS["differential"]
        self.assertEqual(config.max_requests, 10)
        self.assertEqual(config.window_seconds, 60)
    
    def test_extract_labs_limit(self):
        """Test extract-labs has appropriate limits."""
        config = ENDPOINT_LIMITS["extract-labs"]
        self.assertEqual(config.max_requests, 15)
        self.assertEqual(config.window_seconds, 60)
    
    def test_debate_turn_limit(self):
        """Test debate-turn has appropriate limits."""
        config = ENDPOINT_LIMITS["debate-turn"]
        self.assertEqual(config.max_requests, 20)
        self.assertEqual(config.window_seconds, 60)
    
    def test_summary_limit(self):
        """Test summary has appropriate limits."""
        config = ENDPOINT_LIMITS["summary"]
        self.assertEqual(config.max_requests, 10)
        self.assertEqual(config.window_seconds, 60)
    
    def test_limits_match_cost(self):
        """Test that limits inversely correlate with endpoint cost."""
        # GPU-heavy endpoints should have lower limits
        expensive = ENDPOINT_LIMITS["analyze-image"].max_requests
        moderate = ENDPOINT_LIMITS["differential"].max_requests
        cheap = ENDPOINT_LIMITS["debate-turn"].max_requests
        
        self.assertLess(expensive, moderate)
        self.assertLess(moderate, cheap)


class TestCheckRateLimitFunction(unittest.TestCase):
    """Test the check_rate_limit convenience function."""
    
    @patch('rate_limiter.rate_limit_manager')
    def test_check_rate_limit_calls_manager(self, mock_manager):
        """Test that check_rate_limit delegates to manager."""
        mock_request = MagicMock()
        mock_manager.check_rate_limit.return_value = (True, {"X-RateLimit-Limit": "10"})
        
        headers = check_rate_limit("test-endpoint", mock_request)
        
        mock_manager.check_rate_limit.assert_called_once_with("test-endpoint", mock_request)
        self.assertEqual(headers["X-RateLimit-Limit"], "10")


if __name__ == "__main__":
    unittest.main()
