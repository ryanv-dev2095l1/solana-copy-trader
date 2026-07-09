import asyncio
import logging
import time
from typing import Any, Optional
import httpx

logger = logging.getLogger(__name__)


class RpcClient:
    """Thin JSON-RPC wrapper for Solana node interactions."""

    def __init__(self, endpoint: str, commitment: str = "confirmed", timeout: float = 10.0):
        self.endpoint = endpoint
        self.commitment = commitment
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._req_id = 0
        self._cached_blockhash: Optional[str] = None
        self._blockhash_updated_at = 0.0
        self._last_latency_ms: float = 0.0

    async def start(self):
        if not self._client:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=limits,
                headers={"Content-Type": "application/json"},
            )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _call(self, method: str, params: list[Any], retries: int = 3) -> dict[str, Any]:
        if not self._client:
            await self.start()
        assert self._client is not None

        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }

        attempt = 0
        backoff = 0.2
        while True:
            attempt += 1
            t0 = time.perf_counter()
            try:
                resp = await self._client.post(self.endpoint, json=payload)
                # print(f"DEBUG rpc response: {resp.status_code}")
                if resp.status_code == 429:
                    if attempt >= retries:
                        resp.raise_for_status()
                    # TODO: add fallback rpc pool rotation when primary 429s too hard
                    logger.warning("rpc rate limit (429), backing off %.2fs", backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                resp.raise_for_status()
                self._last_latency_ms = (time.perf_counter() - t0) * 1000
                body = resp.json()
                if "error" in body:
                    raise RuntimeError(f"RPC error ({method}): {body['error']}")
                return body.get("result")
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                if attempt >= retries:
                    raise exc
                logger.debug("rpc connection flake (%s), retry %d", exc, attempt)
                await asyncio.sleep(backoff)
                backoff *= 1.5

    async def health_check(self) -> bool:
        try:
            res = await self._call("getHealth", [])
            return res == "ok"
        except Exception as e:
            logger.warning("rpc health check failed: %s", e)
            return False

    async def get_slot(self) -> int:
        return await self._call("getSlot", [{"commitment": self.commitment}])

    async def get_latest_blockhash(self, force_refresh: bool = False) -> str:
        now = time.monotonic()
        # blockhashes last ~150 slots (~60s), cache for 2s to save spamming during rapid signals
        if not force_refresh and self._cached_blockhash and (now - self._blockhash_updated_at < 2.0):
            return self._cached_blockhash

        res = await self._call("getLatestBlockhash", [{"commitment": self.commitment}])
        bh = res["value"]["blockhash"]
        self._cached_blockhash = bh
        self._blockhash_updated_at = now
        return bh

    async def get_transaction(self, signature: str) -> Optional[dict[str, Any]]:
        opts = {
            "encoding": "jsonParsed",
            "commitment": self.commitment,
            "maxSupportedTransactionVersion": 0,
        }
        try:
            return await self._call("getTransaction", [signature, opts])
        except Exception as e:
            logger.error("failed to fetch tx %s: %s", signature, e)
            return None

    async def get_signature_statuses(self, signatures: list[str]) -> list[Optional[dict[str, Any]]]:
        res = await self._call("getSignatureStatuses", [signatures, {"searchTransactionHistory": False}])
        if not res or "value" not in res:
            return [None] * len(signatures)
        return res["value"]

    async def poll_confirmation(self, signature: str, timeout_sec: float = 30.0, poll_interval: float = 0.8) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            statuses = await self.get_signature_statuses([signature])
            if statuses and statuses[0]:
                st = statuses[0]
                if st.get("err") is not None:
                    logger.warning("tx %s confirmed with error: %s", signature, st["err"])
                    return False
                level = st.get("confirmationStatus")
                if level in ("confirmed", "finalized"):
                    return True
            await asyncio.sleep(poll_interval)
        return False

    async def send_raw_tx(self, raw_tx_base64: str, skip_preflight: bool = True) -> str:
        opts = {
            "encoding": "base64",
            "skipPreflight": skip_preflight,
            "preflightCommitment": self.commitment,
            "maxRetries": 0,
        }
        return await self._call("sendTransaction", [raw_tx_base64, opts])
