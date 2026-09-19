"""Citizen notification hooks: SMS / voice call / in-app.

The Escalation Watchdog must tell the citizen what happened and that their
complaint has been escalated — without them having to check the app. Real SMS
and voice-call gateways (Twilio, MSG91, MSGIndia, etc.) need credentials; this
module defines the pluggable interface plus a log/simulator implementation so
the flow is end-to-end testable now and can be pointed at a real gateway later.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class CitizenNotifier(ABC):
    @abstractmethod
    def send_sms(self, phone: str, text: str) -> None: ...

    @abstractmethod
    def make_call(self, phone: str, say: str) -> None: ...


class LogNotifier(CitizenNotifier):
    """Default: log SMS/call content. Swap in a real gateway via env."""

    def send_sms(self, phone: str, text: str) -> None:
        logger.info("SMS to %s:\n%s", phone, text)

    def make_call(self, phone: str, say: str) -> None:
        logger.info("Call to %s (TTS):\n%s", phone, say)


class CompositeNotifier(CitizenNotifier):
    """Fan out to several backends (e.g. SMS gateway + app push)."""

    def __init__(self, *notifiers: CitizenNotifier):
        self._notifiers = list(notifiers)

    def send_sms(self, phone: str, text: str) -> None:
        for n in self._notifiers:
            n.send_sms(phone, text)

    def make_call(self, phone: str, say: str) -> None:
        for n in self._notifiers:
            n.make_call(phone, say)


def get_notifier() -> CitizenNotifier:
    return LogNotifier()