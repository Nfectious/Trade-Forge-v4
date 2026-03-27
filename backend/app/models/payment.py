"""
Payment models: StripeCustomer, Subscription, PaymentTransaction
Maps to: stripe_customers, subscriptions, payment_transactions (migration 005)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class StripeCustomer(SQLModel, table=True):
    """Maps our user_id to a Stripe customer_id. One row per paying user."""
    __tablename__ = "stripe_customers"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    stripe_customer_id: str = Field(max_length=100, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Subscription(SQLModel, table=True):
    """Tracks the lifecycle of a Stripe subscription for a user."""
    __tablename__ = "subscriptions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")

    stripe_subscription_id: Optional[str] = Field(
        default=None, max_length=100, unique=True
    )
    stripe_price_id: Optional[str] = Field(default=None, max_length=100)

    tier: str = Field(max_length=20)       # pro | elite | valkyrie
    status: str = Field(max_length=20)     # active | trialing | past_due | cancelled | incomplete

    current_period_start: Optional[datetime] = Field(default=None)
    current_period_end: Optional[datetime] = Field(default=None)
    cancel_at_period_end: bool = Field(default=False)
    cancelled_at: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PaymentTransaction(SQLModel, table=True):
    """Immutable log of every real-money event (subscriptions, contest entries, refunds)."""
    __tablename__ = "payment_transactions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")

    stripe_payment_intent_id: Optional[str] = Field(default=None, max_length=100)
    stripe_charge_id: Optional[str] = Field(default=None, max_length=100)

    # transaction_type: subscription_created | subscription_renewal |
    #                   subscription_failed | contest_entry | refund
    transaction_type: str = Field(max_length=30)
    amount_cents: int                          # always positive; sign determined by type
    currency: str = Field(default="usd", max_length=3)
    status: str = Field(max_length=20)        # succeeded | failed | refunded

    contest_id: Optional[UUID] = Field(default=None, foreign_key="contests.id")
    description: Optional[str] = Field(default=None)

    # Maps to JSONB column "metadata" — attribute renamed to avoid SQLAlchemy clash
    extra_data: Optional[dict] = Field(
        default=None,
        sa_column=Column("metadata", JSONB, nullable=True),
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
