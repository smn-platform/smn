"""Billing API — subscription management and webhook handling."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from smn.auth import get_current_tenant
from smn.billing import (
    create_customer,
    create_subscription,
    get_billing_status,
    verify_webhook_signature,
)
from smn.db import get_db
from smn.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing")


# ── Schemas ──────────────────────────────────────────────────────


class CustomerCreate(BaseModel):
    email: str | None = None


class SubscriptionCreate(BaseModel):
    tier: Literal["core", "growth", "enterprise"] = "core"


class BillingStatus(BaseModel):
    tenant_id: str
    plan_tier: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_status: str | None
    current_period_end: str | None


class CustomerResponse(BaseModel):
    stripe_customer_id: str


class SubscriptionResponse(BaseModel):
    subscription_id: str | None = None
    status: str | None = None
    tier: str | None = None


# ── Endpoints ────────────────────────────────────────────────────


@router.post("/customer", response_model=CustomerResponse, status_code=201)
async def setup_customer(
    body: CustomerCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe customer for the authenticated tenant."""
    customer_id = await create_customer(db, tenant, body.email)
    await db.commit()
    return CustomerResponse(stripe_customer_id=customer_id)


@router.post("/subscribe", response_model=SubscriptionResponse, status_code=201)
async def subscribe(
    body: SubscriptionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a subscription for the authenticated tenant."""
    result = await create_subscription(db, tenant, body.tier)
    await db.commit()
    return result


@router.get("/status", response_model=BillingStatus)
async def billing_status(
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get billing status for the authenticated tenant."""
    return await get_billing_status(tenant)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook events.

    This endpoint does NOT require API key auth — it uses Stripe signature verification.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(400, "Invalid webhook signature.")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "customer.subscription.updated":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id:
            logger.info("Subscription updated for tenant %s: %s", tenant_id, data.get("status"))

    elif event_type == "customer.subscription.deleted":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id:
            logger.info("Subscription cancelled for tenant %s", tenant_id)

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        logger.warning("Payment failed for customer %s", customer_id)

    elif event_type == "invoice.paid":
        customer_id = data.get("customer")
        logger.info("Invoice paid for customer %s", customer_id)

    return {"status": "ok"}
