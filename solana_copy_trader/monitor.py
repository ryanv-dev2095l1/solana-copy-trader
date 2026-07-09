import asyncio
from collections import deque
import json
import logging
from typing import Callable, Coroutine, Set
import websockets

from solana_copy_trader.types import SwapEvent
from solana_copy_trader.parser import parse_transaction_logs

log = logging.getLogger(__name__)


class WalletMonitor:
    """Subscribes to RPC logs for target wallets and triggers callbacks on swap events."""

    def __init__(
        self,
        ws_url: str,
        target_wallets: list[str],
        on_swap: Callable[[SwapEvent], Coroutine],
        max_cache_size: int = 5000,
    ):
        self.ws_url = ws_url
        self.target_wallets = set(target_wallets)
        self.on_swap = on_swap
        self._running = False
        self._seen_order = deque(maxlen=max_cache_size)
        self._seen_set: Set[str] = set()
        self._sub_ids: dict[int, str] = {}

    async def start(self):
        self._running = True
        backoff = 1.0

        while self._running:
            try:
                # Ping keepalive is crucial - public/helius endpoints drop quiet sockets after 30s
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=15,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024,
                ) as ws:
                    log.info("ws connected: %s", self.ws_url)
                    backoff = 1.0

                    req_id = 1
                    for wallet in self.target_wallets:
                        sub_req = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [wallet]},
                                {"commitment": "processed"}
                            ]
                        }
                        await ws.send(json.dumps(sub_req))
                        self._sub_ids[req_id] = wallet
                        req_id += 1

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._process_raw_msg(raw)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                log.warning("ws connection error (%s), retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

    async def stop(self):
        self._running = False

    async def _process_raw_msg(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Handle sub confirmation
        if "result" in data and isinstance(data["result"], int):
            sub_id = data["id"]
            w = self._sub_ids.get(sub_id, "unknown")
            log.debug("confirmed logs subscription #%d for %s", data["result"], w)
            return

        params = data.get("params", {})
        val = params.get("result", {}).get("value", {})
        sig = val.get("signature")
        logs = val.get("logs", [])
        err = val.get("err")

        if err is not None or not sig:
            return

        if sig in self._seen_set:
            return

        if len(self._seen_order) == self._seen_order.maxlen:
            oldest = self._seen_order.popleft()
            self._seen_set.discard(oldest)
        self._seen_order.append(sig)
        self._seen_set.add(sig)

        # print(f"[debug] raw sig {sig}")
        event = parse_transaction_logs(sig, logs, self.target_wallets)
        if event:
            log.info("detected %s swap for %s on tx %s", event.dex, event.wallet[:8], sig[:12])
            asyncio.create_task(self.on_swap(event))
