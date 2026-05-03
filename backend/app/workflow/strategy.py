"""
Strategy pattern — swaps P0/P1/P2 alert behaviour at runtime without if/else chains.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("ims.strategy")


class AlertStrategy(ABC):
    """Base class for severity-based alerting strategies."""

    @abstractmethod
    def severity(self) -> str: ...

    @abstractmethod
    async def alert(self, work_item: dict) -> dict: ...


class P0Strategy(AlertStrategy):
    """Critical — immediate page to on-call engineer."""

    def severity(self) -> str:
        return "P0"

    async def alert(self, work_item: dict) -> dict:
        logger.critical("🚨 P0 ALERT: %s — paging on-call NOW", work_item.get("title"))
        return {
            "severity": "P0",
            "action": "PAGE_ONCALL",
            "urgency": "immediate",
            "message": f"CRITICAL: {work_item.get('title')} — immediate response required",
        }


class P1Strategy(AlertStrategy):
    """High — notify team within 5 minutes."""

    def severity(self) -> str:
        return "P1"

    async def alert(self, work_item: dict) -> dict:
        logger.warning("⚠️ P1 ALERT: %s — notifying team", work_item.get("title"))
        return {
            "severity": "P1",
            "action": "NOTIFY_TEAM",
            "urgency": "5_minutes",
            "message": f"HIGH: {work_item.get('title')} — team notification sent",
        }


class P2Strategy(AlertStrategy):
    """Medium — batch into hourly digest."""

    def severity(self) -> str:
        return "P2"

    async def alert(self, work_item: dict) -> dict:
        logger.info("📋 P2 ALERT: %s — batched for hourly digest", work_item.get("title"))
        return {
            "severity": "P2",
            "action": "BATCH_DIGEST",
            "urgency": "hourly",
            "message": f"MEDIUM: {work_item.get('title')} — added to hourly digest",
        }


# ── Strategy registry ────────────────────────────────────────────────────────

_STRATEGIES: dict[str, AlertStrategy] = {
    "P0": P0Strategy(),
    "P1": P1Strategy(),
    "P2": P2Strategy(),
}


async def execute_alert(work_item: dict) -> dict:
    """
    Select and execute the alerting strategy based on severity.
    Falls back to P2 for unknown severity levels.
    """
    severity = work_item.get("severity", "P2")
    strategy = _STRATEGIES.get(severity, _STRATEGIES["P2"])
    return await strategy.alert(work_item)
