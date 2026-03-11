"""
agents/api_key_pool.py

API Key Pool with automatic rotation on failures.
Supports multiple keys per provider with cooldown tracking for exhausted keys.
"""

import os
import time
import threading
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum


class KeyStatus(Enum):
    """Status of an API key."""
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    INVALID = "invalid"


@dataclass
class APIKeyEntry:
    """Tracks an individual API key's status."""
    key: str
    status: KeyStatus = KeyStatus.HEALTHY
    last_failure_time: float = 0.0
    failure_count: int = 0
    cooldown_until: float = 0.0
    
    def is_available(self) -> bool:
        """Check if this key is currently available for use."""
        if self.status == KeyStatus.INVALID:
            return False
        if self.status == KeyStatus.HEALTHY:
            return True
        # Check if cooldown has expired
        return time.time() >= self.cooldown_until
    
    def mark_failed(self, status: KeyStatus, cooldown_seconds: float = 60.0):
        """Mark this key as failed with a cooldown period."""
        self.status = status
        self.last_failure_time = time.time()
        self.failure_count += 1
        self.cooldown_until = time.time() + cooldown_seconds
    
    def mark_healthy(self):
        """Mark this key as healthy after successful use."""
        self.status = KeyStatus.HEALTHY
        self.failure_count = 0


class APIKeyPool:
    """
    Manages a pool of API keys for a specific provider.
    
    Features:
    - Round-robin key selection
    - Automatic rotation on rate limits/quota exhaustion
    - Cooldown tracking for failed keys
    - Thread-safe operations
    
    Usage:
        pool = APIKeyPool.from_env("GROQ_API_KEYS")  # comma-separated keys
        # or
        pool = APIKeyPool(["key1", "key2", "key3"])
        
        key = pool.get_key()
        try:
            # use key...
            pool.mark_success(key)
        except RateLimitError:
            pool.mark_rate_limited(key)
            key = pool.get_key()  # try next key
    """
    
    # Cooldown durations in seconds
    RATE_LIMIT_COOLDOWN = 60.0      # 1 minute for rate limits
    QUOTA_EXHAUSTED_COOLDOWN = 3600.0  # 1 hour for quota exhaustion
    
    def __init__(self, api_keys: List[str]):
        """
        Initialize the key pool.
        
        Args:
            api_keys: List of API keys to manage.
        """
        if not api_keys:
            raise ValueError("At least one API key is required")
        
        # Filter out empty strings
        api_keys = [k.strip() for k in api_keys if k.strip()]
        if not api_keys:
            raise ValueError("At least one non-empty API key is required")
        
        self._keys: List[APIKeyEntry] = [APIKeyEntry(key=k) for k in api_keys]
        self._current_index: int = 0
        self._lock = threading.Lock()
    
    @classmethod
    def from_env(cls, env_var: str, fallback_single_key_var: Optional[str] = None) -> "APIKeyPool":
        """
        Create a key pool from environment variable.
        
        Supports comma-separated keys: KEY1,KEY2,KEY3
        
        Args:
            env_var: Environment variable containing comma-separated keys.
            fallback_single_key_var: Fallback env var for single key (backward compat).
            
        Returns:
            Configured APIKeyPool instance.
        """
        keys_str = os.getenv(env_var, "")
        
        if keys_str:
            keys = [k.strip() for k in keys_str.split(",") if k.strip()]
            if keys:
                return cls(keys)
        
        # Fallback to single key variable
        if fallback_single_key_var:
            single_key = os.getenv(fallback_single_key_var, "")
            if single_key:
                return cls([single_key])
        
        raise ValueError(f"No API keys found in {env_var}" + 
                        (f" or {fallback_single_key_var}" if fallback_single_key_var else ""))
    
    def get_key(self) -> str:
        """
        Get the next available API key.
        
        Uses round-robin selection, skipping keys that are in cooldown.
        
        Returns:
            An available API key.
            
        Raises:
            RuntimeError: If all keys are exhausted/in cooldown.
        """
        with self._lock:
            # Try each key starting from current index
            for _ in range(len(self._keys)):
                entry = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._keys)
                
                if entry.is_available():
                    return entry.key
            
            # All keys are in cooldown - find the one with shortest remaining cooldown
            soonest_available = min(self._keys, key=lambda e: e.cooldown_until)
            wait_time = soonest_available.cooldown_until - time.time()
            
            if wait_time > 0:
                raise RuntimeError(
                    f"All API keys are exhausted. Shortest cooldown expires in {wait_time:.0f}s. "
                    f"Key statuses: {self.get_status_summary()}"
                )
            
            # Cooldown just expired
            return soonest_available.key
    
    def mark_success(self, key: str):
        """Mark a key as successfully used."""
        with self._lock:
            entry = self._find_entry(key)
            if entry:
                entry.mark_healthy()
    
    def mark_rate_limited(self, key: str, cooldown_seconds: Optional[float] = None):
        """
        Mark a key as rate limited.
        
        Args:
            key: The API key that hit rate limits.
            cooldown_seconds: Custom cooldown duration (default: 60s).
        """
        with self._lock:
            entry = self._find_entry(key)
            if entry:
                cooldown = cooldown_seconds or self.RATE_LIMIT_COOLDOWN
                entry.mark_failed(KeyStatus.RATE_LIMITED, cooldown)
    
    def mark_quota_exhausted(self, key: str, cooldown_seconds: Optional[float] = None):
        """
        Mark a key as quota exhausted.
        
        Args:
            key: The API key that exhausted its quota.
            cooldown_seconds: Custom cooldown duration (default: 1 hour).
        """
        with self._lock:
            entry = self._find_entry(key)
            if entry:
                cooldown = cooldown_seconds or self.QUOTA_EXHAUSTED_COOLDOWN
                entry.mark_failed(KeyStatus.QUOTA_EXHAUSTED, cooldown)
    
    def mark_invalid(self, key: str):
        """Mark a key as permanently invalid (bad key, revoked, etc.)."""
        with self._lock:
            entry = self._find_entry(key)
            if entry:
                entry.status = KeyStatus.INVALID
    
    def _find_entry(self, key: str) -> Optional[APIKeyEntry]:
        """Find the entry for a given key."""
        for entry in self._keys:
            if entry.key == key:
                return entry
        return None
    
    def get_status_summary(self) -> Dict[str, int]:
        """Get a summary of key statuses."""
        summary = {status.value: 0 for status in KeyStatus}
        for entry in self._keys:
            summary[entry.status.value] += 1
        return summary
    
    def available_key_count(self) -> int:
        """Return the number of currently available keys."""
        return sum(1 for entry in self._keys if entry.is_available())
    
    def total_key_count(self) -> int:
        """Return the total number of keys in the pool."""
        return len(self._keys)
    
    def __len__(self) -> int:
        return len(self._keys)


def is_rate_limit_error(exception: Exception) -> bool:
    """
    Check if an exception indicates a rate limit error.
    
    Handles common patterns from OpenAI, Groq, Anthropic, etc.
    """
    error_str = str(exception).lower()
    
    # Check for common rate limit indicators
    rate_limit_patterns = [
        "rate limit",
        "rate_limit",
        "ratelimit",
        "too many requests",
        "429",
        "quota exceeded",
        "requests per minute",
        "tokens per minute",
        "rpm limit",
        "tpm limit",
    ]
    
    return any(pattern in error_str for pattern in rate_limit_patterns)


def is_quota_exhausted_error(exception: Exception) -> bool:
    """
    Check if an exception indicates quota/billing exhaustion.
    
    These are typically longer-term failures than rate limits.
    """
    error_str = str(exception).lower()
    
    quota_patterns = [
        "insufficient_quota",
        "quota exhausted",
        "billing",
        "payment required",
        "exceeded your current quota",
        "account has been deactivated",
        "credit",
    ]
    
    return any(pattern in error_str for pattern in quota_patterns)


def is_invalid_key_error(exception: Exception) -> bool:
    """Check if an exception indicates an invalid/revoked API key."""
    error_str = str(exception).lower()
    
    invalid_patterns = [
        "invalid api key",
        "invalid_api_key",
        "incorrect api key",
        "authentication failed",
        "unauthorized",
        "401",
        "api key not found",
    ]
    
    return any(pattern in error_str for pattern in invalid_patterns)
