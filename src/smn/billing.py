"""Stripe Billing — subscription management and usage-based invoicing.

Implements:
- Customer creation and subscription management.
- Usage record reporting for metered billing.
- Webhook handling for payment events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from smn.config import settings
from smn.models import Tenant

logger = logging.getLogger(__name__)


def _get_stripe():
    """Lazy-import stripe SDK to avoid import errors when not installed."""
    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        return stripe
    except ImportError:
        raise RuntimeError(
            "Stripe SDK not installed. Run: pip install stripe"
        )


async def create_customer(
    db: AsyncSession,
    tenant: Tenant,
    email: str | None = None,
) -> str:
    """Create a Stripe customer for a tenant. Returns the Stripe customer ID."""
    stripe = _get_stripe()

    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    customer = stripe.Customer.create(
        name=tenant.name,
        email=email,
        metadata={"tenant_id": tenant.id, "platform": "smn"},
    )

    await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant.id)
        .values(stripe_customer_id=customer.id)
    )
    await db.flush()

    logger.info("Created Stripe customer %s for tenant %s", customer.id, tenant.id)
    return customer.id


async def create_subscription(
    db: AsyncSession,
    tenant: Tenant,
    tier: str = "core",
) -> dict:
    """Create a subscription for the given tier. Returns subscription details."""
    stripe = _get_stripe()

    if not tenant.stripe_customer_id:
        raise ValueError("Tenant has no Stripe customer. Call create_customer first.")

    price_map = {
        "core": settings.stripe_price_id_core,
        "growth": settings.stripe_price_id_growth,
    }
    price_id = price_map.get(tier)
    if not price_id:
        raise ValueError(f"Unknown tier '{tier}' or no Stripe price configured.")

    items = [{"price": price_id}]

    # Add metered usage price if configured
    if settings.stripe_price_id_usage:
        items.append({"price": settings.stripe_price_id_usage})

    subscription = stripe.Subscription.create(
        customer=tenant.stripe_customer_id,
        items=items,
        metadata={"tenant_id": tenant.id, "tier": tier},
    )

    await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant.id)
        .values(
            stripe_subscription_id=subscription.id,
            plan_tier=tier,
        )
    )
    await db.flush()

    logger.info(
        "Created Stripe subscription %s (tier=%s) for tenant %s",
        subscription.id,
        tier,
        tenant.id,
    )

    return {
        "subscription_id": subscription.id,
        "status": subscription.status,
        "tier": tier,
        "current_period_end": datetime.fromtimestamp(
            subscription.current_period_end, tz=timezone.utc
        ).isoformat(),
    }


async def report_usage(
    tenant: Tenant,
    quantity: int,
    timestamp: int | None = None,
) -> dict | None:
    """Report metered usage to Stripe for a tenant.

    quantity: number of governed task executions to report.
    """
    stripe = _get_stripe()

    if not tenant.stripe_subscription_id:
        logger.warning("Tenant %s has no subscription — skipping usage report.", tenant.id)
        return None

    # Find the metered subscription item
    subscription = stripe.Subscription.retrieve(tenant.stripe_subscription_id)
    metered_item = None
    for item in subscription["items"]["data"]:
        if item["price"]["id"] == settings.stripe_price_id_usage:
            metered_item = item
            break

    if not metered_item:
        logger.warning("No metered price item found for tenant %s", tenant.id)
        return None

    ts = timestamp or int(datetime.now(timezone.utc).timestamp())

    usage_record = stripe.SubscriptionItem.create_usage_record(
        metered_item["id"],
        quantity=quantity,
        timestamp=ts,
        action="increment",
    )

    logger.info(
        "Reported %d usage units for tenant %s (subscription item %s)",
        quantity,
        tenant.id,
        metered_item["id"],
    )

    return {
        "usage_record_id": usage_record.id,
        "quantity": quantity,
        "timestamp": ts,
    }


async def get_billing_status(tenant: Tenant) -> dict:
    """Get the current billing status for a tenant."""
    stripe = _get_stripe()

    result = {
        "tenant_id": tenant.id,
        "plan_tier": tenant.plan_tier,
        "stripe_customer_id": tenant.stripe_customer_id,
        "stripe_subscription_id": tenant.stripe_subscription_id,
        "subscription_status": None,
        "current_period_end": None,
    }

    if tenant.stripe_subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(tenant.stripe_subscription_id)
            result["subscription_status"] = subscription.status
            result["current_period_end"] = datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            ).isoformat()
        except Exception as e:
            logger.error("Failed to retrieve subscription: %s", e)
            result["subscription_status"] = "error"

    return result


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Verify and parse a Stripe webhook event."""
    stripe = _get_stripe()

    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return event
