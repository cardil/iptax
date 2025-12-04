"""Cache management for iptax.

This package contains cache managers for different types of data:
- history: Tracks report generation history
- inflight: Stores in-progress reports during collection/review
"""

from .history import HistoryManager, get_history_manager, get_history_path
from .inflight import InFlightCache, get_inflight_cache, get_inflight_cache_dir

__all__ = [
    "HistoryManager",
    "InFlightCache",
    "get_history_manager",
    "get_history_path",
    "get_inflight_cache",
    "get_inflight_cache_dir",
]
