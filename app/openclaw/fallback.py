"""
app.openclaw.fallback — Reusable fallback decorator for OpenClaw calls.

Usage example:

    from app.openclaw.fallback import with_fallback
    from skills.amazon import AmazonSkill

    _amazon = AmazonSkill()

    def direct_amazon_search(query):
        return {"result": _amazon.run(query).summary, "skill": "amazon", "status": "ok"}

    @with_fallback(direct_amazon_search)
    def openclaw_amazon_search(query):
        return openclaw_wrapper.execute("amazon", query)

If openclaw_wrapper.execute raises any exception, direct_amazon_search(query)
is called transparently and FALLBACK_COUNT is incremented.
"""

import functools
import logging

logger = logging.getLogger(__name__)

FALLBACK_COUNT: int = 0


def with_fallback(fallback_func: callable):
    """
    Decorator factory. Wraps a function so that on any Exception,
    fallback_func is called with the same arguments.

    Logs a warning including the original exception message.
    Increments FALLBACK_COUNT each time the fallback is used.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            global FALLBACK_COUNT
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    "Primary %s failed (%s), using fallback %s",
                    func.__name__, e, fallback_func.__name__,
                )
                FALLBACK_COUNT += 1
                return fallback_func(*args, **kwargs)
        return wrapper
    return decorator
