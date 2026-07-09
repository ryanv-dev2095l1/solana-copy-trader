import asyncio
import base64
import logging
import time
import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from solana_copy_trader.config import Config
from solana_copy_trader.types import SwapEvent, ExecutedTrade
from solana_copy_trader.rpc import SolanaClient

log = logging.getLogger(__name__)

WSOL = "So11111111111111111111111111111111111111112"


class SwapExecutor:
    """Builds and submits Jupiter swap transactions following parsed target events."""

    def __init__(self, cfg: Config, client: SolanaClient, keypair: Keypair):
        self.cfg = cfg
        self.client = client
        self.keypair = keypair
        self._http = httpx.AsyncClient(
            base_url=cfg.jupiter_api_url,
            timeout=httpx.Timeout(6.0, connect=3.0),
            headers={"User-Agent": "solana-copy-trader/0.3"}
        )

    async def close(self):
        await self._http.aclose()

    async def execute_copy(self, event: SwapEvent) -> ExecutedTrade | None:
        t0 = time.monotonic()
        is_buy = event.input_mint == WSOL

        if is_buy:
            amount_in = int(self.cfg.copy_size_sol * 1e9)
        else:
            # FIXME: read actual token balance instead of blind assumption when selling
            amount_in = event.input_amount
            if amount_in <= 0:
                log.warning("invalid sell amount %d for %s", amount_in, event.output_mint[:8])
                return None

        quote = await self._fetch_quote_with_retry(event.input_mint, event.output_mint, amount_in)
        if not quote:
            return None

        swap_b64 = await self._build_swap(quote)
        if not swap_b64:
            return None

        raw = base64.b64decode(swap_b64)
        tx = VersionedTransaction.from_bytes(raw)
        sig = self.keypair.sign_message(bytes(tx.message))
        signed = VersionedTransaction.populate(tx.message, [sig])

        tx_sig = await self.client.send_raw_transaction(bytes(signed))
        if not tx_sig:
            return None

        elapsed_ms = (time.monotonic() - t0) * 1000
        log.info("tx sent in %.0fms: %s", elapsed_ms, tx_sig)

        # Wait for confirmation before returning
        confirmed = await self._wait_confirmation(tx_sig)
        out_amount = int(quote.get("outAmount", 0))

        return ExecutedTrade(
            source_tx=event.signature,
            executed_sig=tx_sig,
            input_mint=event.input_mint,
            output_mint=event.output_mint,
            amount_in=amount_in,
            amount_out=out_amount,
            confirmed=confirmed,
            latency_ms=elapsed_ms,
        )

    async def _fetch_quote_with_retry(self, in_mint: str, out_mint: str, amount: int) -> dict | None:
        slippages = [self.cfg.slippage_bps, self.cfg.slippage_bps * 2]
        for bps in slippages:
            try:
                resp = await self._http.get("/quote", params={
                    "inputMint": in_mint,
                    "outputMint": out_mint,
                    "amount": str(amount),
                    "slippageBps": bps,
                    "onlyDirectRoutes": "false",
                })
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 400:
                    log.debug("jup 400 with bps=%d, trying wider slippage", bps)
                    continue
            except httpx.RequestError as exc:
                log.warning("jupiter quote request failed: %s", exc)
                await asyncio.sleep(0.1)
        return None

    async def _build_swap(self, quote: dict) -> str | None:
        # Cap compute fee so we don't blow wallet on sudden network spikes
        fee_lamports = min(self.cfg.priority_fee_lamports, 2_000_000)
        payload = {
            "quoteResponse": quote,
            "userPublicKey": str(self.keypair.pubkey()),
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": {
                "autoMultiplier": 1.1,
                "maxLamports": fee_lamports,
            },
        }
        try:
            resp = await self._http.post("/swap", json=payload)
            if resp.status_code != 200:
                log.error("jup swap build error %d: %s", resp.status_code, resp.text)
                return None
            return resp.json().get("swapTransaction")
        except Exception as err:
            log.error("failed posting to jup /swap: %s", err)
            return None

    async def _wait_confirmation(self, sig: str, max_retries: int = 15) -> bool:
        for _ in range(max_retries):
            await asyncio.sleep(1.0)
            status = await self.client.get_signature_status(sig)
            if status in ("confirmed", "finalized"):
                return True
            if status == "failed":
                log.error("swap tx %s failed onchain", sig)
                return False
        log.warning("timeout waiting for tx %s confirmation", sig)
        return False
