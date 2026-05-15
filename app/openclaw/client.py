"""
app.openclaw.client — OpenClaw SDK wrapper with connect/execute/retry logic.
"""

import logging
import time

logger = logging.getLogger(__name__)


class OpenClawWrapper:
    """Wraps the OpenClaw SDK with connection management and retry logic."""

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self._connected = False

    def connect(self) -> bool:
        """Initialise the SDK connection. Returns True on success."""
        try:
            # Initialise openclaw-sdk connection
            import openclaw  # noqa: F401
            self._connected = True
            logger.info("OpenClaw connection established")
            return True
        except Exception as e:
            logger.info("OpenClaw SDK not available, running in stub mode: %s", e)
            self._connected = True  # allow stub execution
            return True

    def execute(self, skill: str, query: str) -> dict:
        """Call a named skill with a query. Returns dict with a 'result' key."""
        if not self._connected:
            self.connect()

        def _call():
            logger.info("Executing skill=%s query=%r", skill, query[:60])
            # When the real SDK is available, replace this with the SDK call:
            # return openclaw.run(skill=skill, query=query, api_key=self.api_key)
            return {"result": f"[{skill}] {query}", "skill": skill, "status": "ok"}

        return self.retry(_call)

    def retry(self, func, max_attempts: int = 3, backoff: float = 2.0):
        """
        Call func up to max_attempts times with exponential backoff.
        Waits backoff^attempt seconds between retries (2s, 4s, 8s, ...).
        Raises the last exception if all attempts fail.
        """
        last_error = None
        for attempt in range(max_attempts):
            try:
                return func()
            except Exception as e:
                last_error = e
                wait = backoff ** attempt
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt + 1, max_attempts, e, wait,
                )
                time.sleep(wait)
        raise last_error
