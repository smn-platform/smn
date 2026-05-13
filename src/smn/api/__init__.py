"""API package — FastAPI routers."""

from fastapi import APIRouter

from smn.api.admin import router as admin_router
from smn.api.agents import router as agents_router
from smn.api.audit import router as audit_router
from smn.api.auth import router as auth_router
from smn.api.billing import router as billing_router
from smn.api.health import router as health_router
from smn.api.policies import router as policies_router
from smn.api.streaming import router as streaming_router
from smn.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(agents_router, tags=["agents"])
api_router.include_router(tasks_router, tags=["tasks"])
api_router.include_router(streaming_router, tags=["streaming"])
api_router.include_router(policies_router, tags=["policies"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(billing_router, tags=["billing"])
api_router.include_router(admin_router, tags=["admin"])
