"""
app.openclaw.config — Environment variable validation for OpenClaw integration.

Call validate_config() once at startup. Outside pytest, missing required vars
raise ValueError immediately so the app fails fast with a clear message.
"""

import logging
import os

logger = logging.getLogger(__name__)

PYTEST_RUNNING = bool(os.environ.get("PYTEST_RUNNING"))

# Read config from environment
OPENCLAW_API_KEY = os.environ.get("OPENCLAW_API_KEY", "")
OPENCLAW_TIMEOUT = int(os.environ.get("OPENCLAW_TIMEOUT", "30"))
OPENCLAW_ENABLED = os.environ.get("OPENCLAW_ENABLED", "true").lower() != "false"


def validate_config() -> dict:
    """
    Validate all OpenClaw environment variables.

    Returns a config dict with all values.
    Raises ValueError if a required var is missing outside pytest.
    Logs all values at DEBUG level.
    """
    global OPENCLAW_API_KEY

    api_key = os.environ.get("OPENCLAW_API_KEY", "")

    if not api_key:
        if PYTEST_RUNNING:
            api_key = "test_key"
            logger.debug("PYTEST_RUNNING detected — using dummy OPENCLAW_API_KEY")
        else:
            raise ValueError(
                "OPENCLAW_API_KEY is not set. "
                "Add it to your .env file or set OPENCLAW_ENABLED=false to skip OpenClaw."
            )

    timeout = int(os.environ.get("OPENCLAW_TIMEOUT", "30"))
    enabled = os.environ.get("OPENCLAW_ENABLED", "true").lower() != "false"

    config = {
        "api_key": api_key,
        "timeout": timeout,
        "enabled": enabled,
    }

    logger.debug(
        "OpenClaw config — enabled=%s timeout=%ds api_key=%s",
        enabled,
        timeout,
        f"{api_key[:4]}***" if api_key != "test_key" else "test_key",
    )

    return config
