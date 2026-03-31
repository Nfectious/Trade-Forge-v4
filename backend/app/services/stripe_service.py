"""
Stripe Service
Thin async wrapper around the Stripe Python SDK.

All Stripe SDK calls are synchronous; we run them in asyncio.to_thread() so
they never block the FastAPI event loop.

Convention:
  - get_or_create_customer() is the only function that touches the DB directly.
  - All other functions take an AsyncSession only when they need to record
    something to the DB (e.g., upsert a StripeCustomer row).
  - Callers (payments.py) own DB writes for subscriptions and transactions.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import stripe
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.payment import StripeCustomer

logger = logging.getLogger(__name__)

# Set the API key once at import time; remains None if not configured.
# Supports both STRIPE_SECRET_KEY (preferred) and STRIPE_RESTRICTED_KEY (legacy).
stripe.api_key = settings.stripe_secret_key

# ---------------------------------------------------------------------------
# TIER → PRICE ID MAPPING
# ---------------------------------------------------------------------------

_TIER_TO_PRICE: dict[str, str | None] = {
    "pro": settings.STRIPE_PRICE_ID_PRO,
    "elite": settings.STRIPE_PRICE_ID_ELITE,
    "valkyrie": settings.STRIPE_PRICE_ID_VALKYRIE,
}

_PRICE_TO_TIER: dict[str, str] = {}
for _tier, _price_id in _TIER_TO_PRICE.items():
    if _price_id:
        _PRICE_TO_TIER[_price_id] = _tier


def price_id_to_tier(price_id: str) -> str | None:
    """Map a Stripe price ID back to our tier string. Returns None if unknown."""
    return _PRICE_TO_TIER.get(price_id)


# ---------------------------------------------------------------------------
# CUSTOMER
# ---------------------------------------------------------------------------

async def get_or_create_customer(
    user_id: UUID,
    email: str,
    session: AsyncSession,
) -> str:
    """Return the Stripe customer ID for a user, creating one if needed.

    Persists a row to stripe_customers on first creation.
    """
    result = await session.execute(
        select(StripeCustomer).where(StripeCustomer.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing.stripe_customer_id

    # Create customer in Stripe (blocking call → thread pool)
    customer = await asyncio.to_thread(
        lambda: stripe.Customer.create(
            email=email,
            metadata={"user_id": str(user_id)},
        )
    )

    row = StripeCustomer(
        user_id=user_id,
        stripe_customer_id=customer.id,
    )
    session.add(row)
    await session.commit()

    logger.info("Stripe customer created: user=%s customer=%s", user_id, customer.id)
    return customer.id


# ---------------------------------------------------------------------------
# SUBSCRIPTIONS
# ---------------------------------------------------------------------------

async def create_subscription_checkout(
    user_id: UUID,
    email: str,
    tier: str,
    session: AsyncSession,
) -> str:
    """Create a Stripe Checkout session for a subscription upgrade.

    Returns the checkout session URL to redirect the user to.
    Raises ValueError if tier is unrecognised or price ID is not configured.
    """
    price_id = _TIER_TO_PRICE.get(tier)
    if not price_id:
        raise ValueError(f"No Stripe price ID configured for tier '{tier}'")

    customer_id = await get_or_create_customer(user_id, email, session)
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    checkout_session = await asyncio.to_thread(
        lambda: stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{frontend_url}/dashboard?subscription=success",
            cancel_url=f"{frontend_url}/pricing?subscription=cancelled",
            metadata={"user_id": str(user_id), "tier": tier},
        )
    )

    logger.info(
        "Checkout session created: user=%s tier=%s session=%s",
        user_id, tier, checkout_session.id,
    )
    return checkout_session.url


async def cancel_subscription(stripe_subscription_id: str) -> None:
    """Schedule the subscription to cancel at the end of the current billing period."""
    await asyncio.to_thread(
        lambda: stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
    )
    logger.info("Subscription scheduled for cancellation: %s", stripe_subscription_id)


async def reactivate_subscription(stripe_subscription_id: str) -> None:
    """Undo a pending cancellation — subscription resumes at period end."""
    await asyncio.to_thread(
        lambda: stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=False,
        )
    )
    logger.info("Subscription reactivated: %s", stripe_subscription_id)


# ---------------------------------------------------------------------------
# BILLING PORTAL
# ---------------------------------------------------------------------------

async def create_billing_portal_session(stripe_customer_id: str) -> str:
    """Return a Stripe Billing Portal URL for the given customer.

    The user lands back on the frontend after managing their subscription.
    """
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    portal_session = await asyncio.to_thread(
        lambda: stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=f"{frontend_url}/dashboard",
        )
    )
    return portal_session.url


# ---------------------------------------------------------------------------
# CONTEST PAYMENT INTENTS
# ---------------------------------------------------------------------------

async def create_contest_payment_intent(
    user_id: UUID,
    contest_id: UUID,
    amount_cents: int,
    email: str,
    session: AsyncSession,
) -> dict:
    """Create a Stripe PaymentIntent for a paid contest entry fee.

    Returns a dict with client_secret and payment_intent_id so the frontend
    can confirm the payment with Stripe.js.
    """
    customer_id = await get_or_create_customer(user_id, email, session)

    pi = await asyncio.to_thread(
        lambda: stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            customer=customer_id,
            metadata={
                "user_id": str(user_id),
                "contest_id": str(contest_id),
            },
            automatic_payment_methods={"enabled": True},
        )
    )

    logger.info(
        "PaymentIntent created: user=%s contest=%s pi=%s amount_cents=%d",
        user_id, contest_id, pi.id, amount_cents,
    )
    return {"client_secret": pi.client_secret, "payment_intent_id": pi.id}


async def retrieve_payment_intent(payment_intent_id: str) -> stripe.PaymentIntent:
    """Retrieve a PaymentIntent from Stripe (for server-side confirmation check)."""
    return await asyncio.to_thread(
        lambda: stripe.PaymentIntent.retrieve(payment_intent_id)
    )


# ---------------------------------------------------------------------------
# REFUNDS
# ---------------------------------------------------------------------------

async def refund_payment_intent(payment_intent_id: str) -> None:
    """Issue a full refund against a PaymentIntent."""
    await asyncio.to_thread(
        lambda: stripe.Refund.create(payment_intent=payment_intent_id)
    )
    logger.info("Refund issued for PaymentIntent: %s", payment_intent_id)


# ---------------------------------------------------------------------------
# WEBHOOK HELPERS
# ---------------------------------------------------------------------------

def construct_webhook_event(
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> stripe.Event:
    """Verify and parse a Stripe webhook event.

    Raises stripe.error.SignatureVerificationError on bad signature.
    This is synchronous (pure crypto + JSON parse) — safe to call directly.
    """
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
