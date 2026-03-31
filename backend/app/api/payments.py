"""
Payments API routes
Stripe subscriptions, billing portal, and contest entry fee payments.

Endpoints:
  POST   /payments/subscribe                       — start subscription checkout
  GET    /payments/subscription                    — current subscription status
  DELETE /payments/subscription                    — cancel at period end
  POST   /payments/subscription/reactivate         — undo pending cancellation
  GET    /payments/billing-portal                  — Stripe billing portal URL

  POST   /payments/contest/{contest_id}/create-intent  — PaymentIntent for entry fee
  POST   /payments/contest/{contest_id}/confirm        — confirm payment + enroll

  POST   /payments/webhook                         — Stripe webhook (no auth)
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.redis import get_redis_client
from app.core.security import limiter
from app.models.contest import Contest, ContestEntry, ContestPortfolio
from app.models.payment import PaymentTransaction, StripeCustomer, Subscription
from app.models.user import TierLevel, User
from app.services import stripe_service

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# REQUEST BODIES
# ---------------------------------------------------------------------------

class SubscribeRequest(BaseModel):
    tier: str  # pro | elite | valkyrie


class ConfirmContestPaymentRequest(BaseModel):
    payment_intent_id: str


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

_PAID_TIERS = {"pro", "elite", "valkyrie"}


def _require_stripe() -> None:
    """Raise 503 if Stripe is not configured."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not configured",
        )


async def _enroll_paid_contest(
    contest: Contest,
    user: User,
    payment_intent_id: str,
    session: AsyncSession,
) -> ContestEntry:
    """Create ContestPortfolio + ContestEntry for a paid contest.

    Idempotent: if the entry already exists with payment_status='paid' we
    return it unchanged. Raises HTTPException on business-rule violations.
    """
    now = datetime.now(timezone.utc)

    # Idempotency: already enrolled and paid
    existing_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest.id,
            ContestEntry.user_id == user.id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.payment_status == "paid":
            return existing
        # Entry exists but unpaid — update payment status
        existing.payment_status = "paid"
        existing.stripe_payment_intent_id = payment_intent_id
        await session.commit()
        return existing

    if contest.status != "upcoming":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Contest is not open for registration (status: {contest.status})",
        )

    if contest.registration_deadline:
        deadline = contest.registration_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration deadline has passed",
            )

    if (
        contest.max_participants is not None
        and contest.current_participants >= contest.max_participants
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contest is full",
        )

    portfolio = ContestPortfolio(
        contest_id=contest.id,
        user_id=user.id,
        cash_balance=contest.starting_balance,
        total_value=contest.starting_balance,
    )
    session.add(portfolio)
    await session.flush()  # populate portfolio.id

    entry = ContestEntry(
        contest_id=contest.id,
        user_id=user.id,
        contest_portfolio_id=portfolio.id,
        payment_status="paid",
        stripe_payment_intent_id=payment_intent_id,
    )
    session.add(entry)

    contest.current_participants += 1
    contest.updated_at = now

    await session.commit()
    logger.info(
        "Paid contest enrollment: user=%s contest=%s pi=%s",
        user.id, contest.id, payment_intent_id,
    )
    return entry


# ============================================================================
# SUBSCRIPTION ENDPOINTS
# ============================================================================

@router.post("/subscribe")
@limiter.limit("10/minute")
async def subscribe(
    request: Request,
    body: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Start a Stripe Checkout session for a subscription upgrade.

    Returns a checkout_url to redirect the user to Stripe's hosted page.
    """
    _require_stripe()

    if body.tier not in _PAID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(_PAID_TIERS))}",
        )

    try:
        checkout_url = await stripe_service.create_subscription_checkout(
            user_id=current_user.id,
            email=current_user.email,
            tier=body.tier,
            session=session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe error creating checkout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again.",
        )

    return {"checkout_url": checkout_url}


@router.get("/subscription")
@limiter.limit("60/minute")
async def get_subscription(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current user's active or trialing subscription, or free status."""
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(["active", "trialing"]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        return {
            "status": "free",
            "tier": "free",
            "cancel_at_period_end": False,
            "current_period_end": None,
        }

    return {
        "status": sub.status,
        "tier": sub.tier,
        "stripe_subscription_id": sub.stripe_subscription_id,
        "stripe_price_id": sub.stripe_price_id,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.delete("/subscription")
@limiter.limit("10/minute")
async def cancel_subscription(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Schedule the current subscription to cancel at end of billing period."""
    _require_stripe()

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(["active", "trialing"]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    if sub.cancel_at_period_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already scheduled for cancellation",
        )

    try:
        await stripe_service.cancel_subscription(sub.stripe_subscription_id)
    except stripe.error.StripeError as exc:
        logger.error("Stripe error cancelling subscription: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again.",
        )

    sub.cancel_at_period_end = True
    sub.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "message": "Subscription will cancel at period end",
        "ends_at": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.post("/subscription/reactivate")
@limiter.limit("10/minute")
async def reactivate_subscription(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Reactivate a subscription that was scheduled to cancel."""
    _require_stripe()

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(["active", "trialing"]),
            Subscription.cancel_at_period_end == True,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription pending cancellation found",
        )

    try:
        await stripe_service.reactivate_subscription(sub.stripe_subscription_id)
    except stripe.error.StripeError as exc:
        logger.error("Stripe error reactivating subscription: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again.",
        )

    sub.cancel_at_period_end = False
    sub.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {"message": "Subscription reactivated"}


@router.get("/billing-portal")
@limiter.limit("20/minute")
async def billing_portal(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return a Stripe Billing Portal URL for the current user."""
    _require_stripe()

    result = await session.execute(
        select(StripeCustomer).where(StripeCustomer.user_id == current_user.id)
    )
    customer_row = result.scalar_one_or_none()

    if not customer_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing account found. Subscribe first.",
        )

    try:
        portal_url = await stripe_service.create_billing_portal_session(
            customer_row.stripe_customer_id
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe error creating billing portal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again.",
        )

    return {"url": portal_url}


# ============================================================================
# CONTEST PAYMENT ENDPOINTS
# ============================================================================

@router.post("/contest/{contest_id}/create-intent")
@limiter.limit("20/minute")
async def create_contest_payment_intent(
    request: Request,
    contest_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a Stripe PaymentIntent for a paid contest entry fee.

    Returns client_secret for Stripe.js to confirm the payment on the frontend.
    """
    _require_stripe()

    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    if contest.type != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contest does not require payment",
        )

    if not contest.entry_fee or contest.entry_fee <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contest entry fee is not set",
        )

    # Check not already enrolled
    existing_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest_id,
            ContestEntry.user_id == current_user.id,
            ContestEntry.payment_status == "paid",
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already enrolled in this contest",
        )

    try:
        result = await stripe_service.create_contest_payment_intent(
            user_id=current_user.id,
            contest_id=contest_id,
            amount_cents=contest.entry_fee,
            email=current_user.email,
            session=session,
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe error creating payment intent: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again.",
        )

    return {
        "client_secret": result["client_secret"],
        "payment_intent_id": result["payment_intent_id"],
        "amount_cents": contest.entry_fee,
    }


@router.post("/contest/{contest_id}/confirm")
@limiter.limit("10/minute")
async def confirm_contest_payment(
    request: Request,
    contest_id: UUID,
    body: ConfirmContestPaymentRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Verify a PaymentIntent succeeded and enroll the user in the contest.

    Server-side confirmation: we retrieve the PaymentIntent from Stripe to
    check its status rather than trusting the client.
    """
    _require_stripe()

    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    # Retrieve PaymentIntent from Stripe to verify it actually succeeded
    try:
        pi = await stripe_service.retrieve_payment_intent(body.payment_intent_id)
    except stripe.error.StripeError as exc:
        logger.error("Stripe error retrieving payment intent: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify payment status",
        )

    if pi.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment not completed (status: {pi.status})",
        )

    # Verify the PaymentIntent was actually for this contest and this user
    pi_user_id = pi.metadata.get("user_id")
    pi_contest_id = pi.metadata.get("contest_id")
    if pi_user_id != str(current_user.id) or pi_contest_id != str(contest_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment intent does not match this contest or user",
        )

    # Enroll (idempotent)
    try:
        entry = await _enroll_paid_contest(
            contest=contest,
            user=current_user,
            payment_intent_id=body.payment_intent_id,
            session=session,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Contest enrollment failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Enrollment failed after payment. Contact support.",
        )

    # Log payment transaction (idempotent — skip if already logged)
    existing_tx_result = await session.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.stripe_payment_intent_id == body.payment_intent_id
        )
    )
    if not existing_tx_result.scalar_one_or_none():
        tx = PaymentTransaction(
            user_id=current_user.id,
            stripe_payment_intent_id=body.payment_intent_id,
            transaction_type="contest_entry",
            amount_cents=contest.entry_fee or 0,
            currency="usd",
            status="succeeded",
            contest_id=contest_id,
            description=f"Contest entry fee: {contest.name}",
        )
        session.add(tx)
        await session.commit()

    return {
        "contest_id": str(contest_id),
        "contest_name": contest.name,
        "entry_id": str(entry.id),
        "payment_status": entry.payment_status,
        "message": f"Successfully enrolled in '{contest.name}'",
    }


# ============================================================================
# WEBHOOK
# ============================================================================

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Stripe webhook receiver — no JWT auth, verified by Stripe signature.

    All handled events return HTTP 200. Any failure in event processing is
    logged but does NOT return a non-200 response (Stripe would retry).
    Signature errors return 400 immediately.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("Webhook received but STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured",
        )

    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(
            payload=body,
            sig_header=sig_header,
            webhook_secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    except Exception as exc:
        logger.error("Webhook payload parse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    event_type: str = event["type"]
    event_id: str = event["id"]
    logger.info("Webhook received: type=%s id=%s", event_type, event_id)

    # ---- Idempotency check via Redis ----
    redis = get_redis_client()
    if redis:
        idempotency_key = f"stripe:event:{event_id}"
        already_processed = await redis.set(idempotency_key, "1", nx=True, ex=86400)
        if not already_processed:
            logger.debug("Duplicate webhook event skipped: %s", event_id)
            return {"status": "ok"}

    # ---- Dispatch to handler ----
    try:
        data_object = event["data"]["object"]

        if event_type == "customer.subscription.created":
            await _handle_subscription_created(data_object, session)

        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(data_object, session)

        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(data_object, session)

        elif event_type == "invoice.payment_succeeded":
            await _handle_invoice_payment_succeeded(data_object, session)

        elif event_type == "invoice.payment_failed":
            await _handle_invoice_payment_failed(data_object, session)

        elif event_type == "payment_intent.succeeded":
            await _handle_payment_intent_succeeded(data_object, session)

        elif event_type == "payment_intent.payment_failed":
            await _handle_payment_intent_failed(data_object, session)

        else:
            logger.debug("Unhandled webhook event type: %s", event_type)

    except Exception as exc:
        # Log but return 200 so Stripe doesn't retry. Retries on DB errors
        # could cause duplicate processing; better to log and alert.
        logger.error(
            "Webhook handler error: type=%s id=%s error=%s",
            event_type, event_id, exc,
            exc_info=True,
        )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WEBHOOK HANDLERS — each is a separate async function for clarity
# ---------------------------------------------------------------------------

async def _get_user_id_from_stripe_customer(
    stripe_customer_id: str,
    session: AsyncSession,
) -> UUID | None:
    """Look up our user_id from a Stripe customer ID."""
    result = await session.execute(
        select(StripeCustomer).where(
            StripeCustomer.stripe_customer_id == stripe_customer_id
        )
    )
    row = result.scalar_one_or_none()
    return row.user_id if row else None


async def _handle_subscription_created(obj: dict, session: AsyncSession) -> None:
    stripe_customer_id = obj.get("customer")
    stripe_subscription_id = obj.get("id")

    user_id = await _get_user_id_from_stripe_customer(stripe_customer_id, session)
    if not user_id:
        logger.warning(
            "subscription.created: no user found for customer %s", stripe_customer_id
        )
        return

    # Determine tier from the first price item
    items = obj.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    tier = stripe_service.price_id_to_tier(price_id) if price_id else None
    if not tier:
        logger.warning(
            "subscription.created: unknown price_id=%s for subscription %s",
            price_id, stripe_subscription_id,
        )
        return

    now = datetime.now(timezone.utc)

    # Update user tier
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = TierLevel(tier)
        user.updated_at = now

    # Insert subscription row (skip if already exists — idempotent)
    existing_result = await session.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    if not existing_result.scalar_one_or_none():
        sub = Subscription(
            user_id=user_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=price_id,
            tier=tier,
            status=obj.get("status", "active"),
            current_period_start=datetime.fromtimestamp(
                obj["current_period_start"], tz=timezone.utc
            ) if obj.get("current_period_start") else None,
            current_period_end=datetime.fromtimestamp(
                obj["current_period_end"], tz=timezone.utc
            ) if obj.get("current_period_end") else None,
            cancel_at_period_end=obj.get("cancel_at_period_end", False),
        )
        session.add(sub)

    # Log transaction
    tx = PaymentTransaction(
        user_id=user_id,
        transaction_type="subscription_created",
        amount_cents=0,
        currency="usd",
        status="succeeded",
        description=f"Subscription created: {tier}",
        extra_data={"stripe_subscription_id": stripe_subscription_id},
    )
    session.add(tx)
    await session.commit()
    logger.info("Subscription created: user=%s tier=%s", user_id, tier)


async def _handle_subscription_updated(obj: dict, session: AsyncSession) -> None:
    stripe_subscription_id = obj.get("id")
    new_status = obj.get("status")

    result = await session.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning(
            "subscription.updated: subscription %s not found in DB",
            stripe_subscription_id,
        )
        return

    now = datetime.now(timezone.utc)
    sub.status = new_status
    sub.cancel_at_period_end = obj.get("cancel_at_period_end", False)
    sub.updated_at = now

    if obj.get("current_period_start"):
        sub.current_period_start = datetime.fromtimestamp(
            obj["current_period_start"], tz=timezone.utc
        )
    if obj.get("current_period_end"):
        sub.current_period_end = datetime.fromtimestamp(
            obj["current_period_end"], tz=timezone.utc
        )

    # If newly active, ensure user tier is up to date
    if new_status == "active":
        user_result = await session.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and sub.tier in _PAID_TIERS:
            user.tier = TierLevel(sub.tier)
            user.updated_at = now

    await session.commit()
    logger.info(
        "Subscription updated: stripe_id=%s status=%s", stripe_subscription_id, new_status
    )


async def _handle_subscription_deleted(obj: dict, session: AsyncSession) -> None:
    stripe_subscription_id = obj.get("id")

    result = await session.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning(
            "subscription.deleted: subscription %s not found in DB",
            stripe_subscription_id,
        )
        return

    now = datetime.now(timezone.utc)
    sub.status = "cancelled"
    sub.cancelled_at = now
    sub.updated_at = now

    # Downgrade user to free
    user_result = await session.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = TierLevel.FREE
        user.updated_at = now

    await session.commit()
    logger.info(
        "Subscription cancelled: stripe_id=%s user=%s", stripe_subscription_id, sub.user_id
    )


async def _handle_invoice_payment_succeeded(obj: dict, session: AsyncSession) -> None:
    stripe_customer_id = obj.get("customer")
    billing_reason = obj.get("billing_reason", "")

    user_id = await _get_user_id_from_stripe_customer(stripe_customer_id, session)
    if not user_id:
        return

    amount_paid = obj.get("amount_paid", 0)  # already in cents
    currency = obj.get("currency", "usd")
    stripe_charge_id = obj.get("charge")

    tx = PaymentTransaction(
        user_id=user_id,
        stripe_charge_id=stripe_charge_id,
        transaction_type="subscription_renewal",
        amount_cents=amount_paid,
        currency=currency,
        status="succeeded",
        description=f"Invoice payment succeeded ({billing_reason})",
        extra_data={"invoice_id": obj.get("id"), "billing_reason": billing_reason},
    )
    session.add(tx)
    await session.commit()
    logger.info("Invoice payment succeeded: user=%s amount=%d", user_id, amount_paid)


async def _handle_invoice_payment_failed(obj: dict, session: AsyncSession) -> None:
    stripe_customer_id = obj.get("customer")
    stripe_subscription_id = obj.get("subscription")

    user_id = await _get_user_id_from_stripe_customer(stripe_customer_id, session)
    if not user_id:
        return

    # Mark subscription past_due
    if stripe_subscription_id:
        result = await session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "past_due"
            sub.updated_at = datetime.now(timezone.utc)

    amount_due = obj.get("amount_due", 0)
    tx = PaymentTransaction(
        user_id=user_id,
        transaction_type="subscription_failed",
        amount_cents=amount_due,
        currency=obj.get("currency", "usd"),
        status="failed",
        description="Invoice payment failed",
        extra_data={"invoice_id": obj.get("id")},
    )
    session.add(tx)
    await session.commit()
    logger.warning(
        "Invoice payment failed: user=%s stripe_sub=%s", user_id, stripe_subscription_id
    )


async def _handle_payment_intent_succeeded(obj: dict, session: AsyncSession) -> None:
    pi_id = obj.get("id")
    metadata = obj.get("metadata", {})
    contest_id_str = metadata.get("contest_id")
    user_id_str = metadata.get("user_id")

    if not user_id_str:
        return

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        logger.warning("payment_intent.succeeded: invalid user_id in metadata: %s", user_id_str)
        return

    amount = obj.get("amount", 0)
    currency = obj.get("currency", "usd")

    # If this is a contest entry payment, ensure enrollment (webhook as fallback)
    if contest_id_str:
        try:
            contest_id = UUID(contest_id_str)
            contest_result = await session.execute(
                select(Contest).where(Contest.id == contest_id)
            )
            contest = contest_result.scalar_one_or_none()
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            if contest and user:
                await _enroll_paid_contest(
                    contest=contest,
                    user=user,
                    payment_intent_id=pi_id,
                    session=session,
                )
        except HTTPException:
            pass  # Already enrolled or contest not registerable — not a webhook error
        except Exception as exc:
            logger.error(
                "Webhook contest enrollment failed: pi=%s error=%s", pi_id, exc, exc_info=True
            )

    # Log transaction (skip if already logged by confirm endpoint)
    existing_result = await session.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.stripe_payment_intent_id == pi_id
        )
    )
    if not existing_result.scalar_one_or_none():
        tx = PaymentTransaction(
            user_id=user_id,
            stripe_payment_intent_id=pi_id,
            transaction_type="contest_entry",
            amount_cents=amount,
            currency=currency,
            status="succeeded",
            contest_id=UUID(contest_id_str) if contest_id_str else None,
            description="Contest entry fee payment",
        )
        session.add(tx)
        await session.commit()

    logger.info("PaymentIntent succeeded: pi=%s user=%s", pi_id, user_id)


async def _handle_payment_intent_failed(obj: dict, session: AsyncSession) -> None:
    pi_id = obj.get("id")
    metadata = obj.get("metadata", {})
    user_id_str = metadata.get("user_id")
    contest_id_str = metadata.get("contest_id")

    if not user_id_str:
        return

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return

    tx = PaymentTransaction(
        user_id=user_id,
        stripe_payment_intent_id=pi_id,
        transaction_type="contest_entry",
        amount_cents=obj.get("amount", 0),
        currency=obj.get("currency", "usd"),
        status="failed",
        contest_id=UUID(contest_id_str) if contest_id_str else None,
        description="Contest entry payment failed",
        extra_data={"last_payment_error": obj.get("last_payment_error")},
    )
    session.add(tx)
    await session.commit()
    logger.warning("PaymentIntent failed: pi=%s user=%s", pi_id, user_id)
