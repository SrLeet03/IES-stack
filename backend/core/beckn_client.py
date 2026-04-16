"""
Beckn v2 protocol client for communicating through ONIX adapters.

Handles message construction, sending via ONIX BAP adapter, and
polling for async responses. This is the reusable transport layer —
use-case-specific logic lives in the rde/ or other use-case packages.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .models import BecknAction, BecknContext, BecknMessage

logger = logging.getLogger(__name__)

DEFAULT_ONIX_BAP_URL = "http://localhost:8081/bap/caller"
DEFAULT_MOCK_BPP_URL = "http://localhost:3002"
DEFAULT_TIMEOUT = 30.0
POLL_INTERVAL = 2.0
MAX_POLL_ATTEMPTS = 15


@dataclass
class ONIXConfig:
    """Configuration for connecting to ONIX BAP adapter and mock BPP."""

    bap_caller_url: str = DEFAULT_ONIX_BAP_URL
    mock_bpp_url: str = DEFAULT_MOCK_BPP_URL
    network_id: str = "nfh.global/testnet-deg"
    bap_id: str = "bap.example.com"
    bap_uri: str = "https://bap.example.com"
    bpp_id: str = "bpp.example.com"
    bpp_uri: str = "https://bpp.example.com"
    timeout: float = DEFAULT_TIMEOUT


class BecknClient:
    """
    Async client for Beckn v2 protocol over ONIX.

    Supports two response modes:
    - Direct: ONIX returns the response synchronously (rare)
    - Poll: Send request, then poll mock BPP's /api/responses endpoint
    """

    def __init__(self, config: ONIXConfig | None = None):
        self.config = config or ONIXConfig()
        self._http = httpx.AsyncClient(timeout=self.config.timeout)

    async def close(self) -> None:
        await self._http.aclose()

    def build_context(
        self,
        action: BecknAction,
        transaction_id: str | None = None,
        schema_context: list[str] | None = None,
    ) -> BecknContext:
        """Build a BecknContext with our participant identities."""
        ctx = BecknContext(
            action=action,
            network_id=self.config.network_id,
            bap_id=self.config.bap_id,
            bap_uri=self.config.bap_uri,
            schema_context=schema_context,
        )
        if transaction_id:
            ctx.transaction_id = transaction_id

        skip_bpp = action in (BecknAction.DISCOVER,)
        if not skip_bpp:
            ctx.bpp_id = self.config.bpp_id
            ctx.bpp_uri = self.config.bpp_uri

        return ctx

    async def send(self, message: BecknMessage) -> dict[str, Any]:
        """
        Send a Beckn message through ONIX BAP adapter.

        Returns the immediate ACK/NACK response from ONIX.
        The actual protocol response arrives asynchronously.
        """
        action = message.context.action.value
        url = f"{self.config.bap_caller_url}/{action}"
        payload = message.to_dict()

        logger.info("Sending %s to %s", action, url)
        logger.debug("Payload: %s", payload)

        try:
            resp = await self._http.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            logger.info("ACK received for %s", action)
            return result
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %s from ONIX: %s", e.response.status_code, e.response.text)
            raise
        except httpx.ConnectError:
            logger.error("Cannot connect to ONIX at %s", url)
            raise

    async def poll_response(
        self,
        transaction_id: str,
        expected_action: str | None = None,
        max_attempts: int = MAX_POLL_ATTEMPTS,
        interval: float = POLL_INTERVAL,
    ) -> dict[str, Any] | None:
        """
        Poll mock BPP's /api/responses endpoint for async responses.

        The mock BPP stores all sent on_* responses keyed by transaction ID.
        We poll until the expected action appears or we exhaust retries.
        """
        url = f"{self.config.mock_bpp_url}/api/responses/{transaction_id}"
        if expected_action:
            url += f"?action={expected_action}"

        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self._http.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    responses = data.get("responses", [])
                    if responses:
                        latest = responses[-1]
                        logger.info(
                            "Poll attempt %d/%d: got %s response",
                            attempt, max_attempts,
                            latest.get("action", "unknown"),
                        )
                        return latest.get("payload", latest)
                elif resp.status_code == 404:
                    logger.debug(
                        "Poll attempt %d/%d: no responses yet",
                        attempt, max_attempts,
                    )
                else:
                    logger.warning(
                        "Poll attempt %d/%d: HTTP %s",
                        attempt, max_attempts, resp.status_code,
                    )
            except httpx.ConnectError:
                logger.warning(
                    "Poll attempt %d/%d: cannot connect to mock BPP",
                    attempt, max_attempts,
                )

            if attempt < max_attempts:
                await asyncio.sleep(interval)

        logger.warning("Exhausted %d poll attempts for txn %s", max_attempts, transaction_id)
        return None

    async def send_and_poll(
        self,
        message: BecknMessage,
        expected_action: str | None = None,
        max_attempts: int = MAX_POLL_ATTEMPTS,
    ) -> dict[str, Any] | None:
        """Send a message and poll for the async response."""
        await self.send(message)
        return await self.poll_response(
            transaction_id=message.context.transaction_id,
            expected_action=expected_action,
            max_attempts=max_attempts,
        )

    async def get_catalog(self) -> dict[str, Any]:
        """Fetch the catalog directly from mock BPP's REST API."""
        url = f"{self.config.mock_bpp_url}/api/catalog"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Fetch transaction details from mock BPP."""
        url = f"{self.config.mock_bpp_url}/api/transactions/{transaction_id}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> dict[str, Any]:
        """Check mock BPP health."""
        url = f"{self.config.mock_bpp_url}/api/health"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()
