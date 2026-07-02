from __future__ import annotations

import os


def premium_for_all() -> bool:
    """While there is no billing, everyone gets premium (the AI coach).

    Set ``PREMIUM_FOR_ALL=false`` once a real payment flow exists to enforce the
    per-user ``User.is_premium`` flag instead. All of the tier plumbing (the
    column, the /assistant gating, the UI locks) stays in place either way, so
    turning this off is the only change needed to switch to paid premium.
    """
    return os.getenv("PREMIUM_FOR_ALL", "true").lower() == "true"


def is_premium_user(user) -> bool:
    """Effective premium status for a user, honoring the PREMIUM_FOR_ALL switch."""
    if premium_for_all():
        return True
    return bool(getattr(user, "is_premium", False))
