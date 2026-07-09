import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, List

logger = logging.getLogger("solana_copy_trader.metrics")


@dataclass
class MetricsTracker:
    start_time: float = field(default_factory=time.time)
    logs_received: int = 0
    swaps_detected: int = 0
    swaps_copied: int = 0
    swaps_failed: int = 0
    swaps_skipped: int = 0
    ws_reconnects: int = 0

    # rolling window of execution latencies in ms (last 500 copies)
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=500))

    def inc_logs(self):
        self.logs_received += 1

    def inc_detected(self):
        self.swaps_detected += 1

    def inc_copied(self):
        self.swaps_copied += 1

    def inc_failed(self):
        self.swaps_failed += 1

    def inc_skipped(self):
        self.swaps_skipped += 1

    def inc_reconnects(self):
        self.ws_reconnects += 1

    def record_latency(self, total_ms: float):
        if total_ms > 0:
            self.latency_samples.append(total_ms)

    def _percentile(self, data: List[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c >= len(sorted_data):
            return sorted_data[f]
        d0 = sorted_data[f] * (c - k)
        d1 = sorted_data[c] * (k - f)
        return d0 + d1

    def snapshot(self) -> Dict[str, Any]:
        uptime = int(time.time() - self.start_time)
        samples = list(self.latency_samples)
        p50 = round(self._percentile(samples, 50), 1)
        p95 = round(self._percentile(samples, 95), 1)
        
        return {
            "uptime_sec": uptime,
            "logs_received": self.logs_received,
            "swaps_detected": self.swaps_detected,
            "swaps_copied": self.swaps_copied,
            "swaps_failed": self.swaps_failed,
            "swaps_skipped": self.swaps_skipped,
            "ws_reconnects": self.ws_reconnects,
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "sample_count": len(samples),
        }

    def print_summary(self):
        s = self.snapshot()
        # FIXME: formatting breaks a bit if uptime spans days, format nicely later
        logger.info(
            "[stats] uptime: %ds | logs: %d | detected: %d | copied: %d | failed: %d | skipped: %d | p50: %sms | p95: %sms",
            s["uptime_sec"],
            s["logs_received"],
            s["swaps_detected"],
            s["swaps_copied"],
            s["swaps_failed"],
            s["swaps_skipped"],
            s["latency_p50_ms"],
            s["latency_p95_ms"],
        )
