from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AlertNotifier(ABC):
    """Alert hook for RPA failures (portal redesigns without notice)."""

    @abstractmethod
    def alert(self, title: str, detail: str) -> None: ...


class LogNotifier(AlertNotifier):
    def alert(self, title: str, detail: str) -> None:
        logger.error("%s\n%s", title, detail)
