"""Register every HTTP router on the app."""

from __future__ import annotations

from fastapi import FastAPI

from app.routes.admin.account_deletion_router import router as admin_account_deletion_router
from app.routes.admin.admin_crud_router import router as admin_crud_router
from app.routes.attendance.attendance_router import business_router as attendance_business_router
from app.routes.attendance.attendance_router import worker_router as attendance_worker_router
from app.routes.auth.auth_router import router as auth_router
from app.routes.billing.billing_router import router as billing_router
from app.routes.billing.billing_router import webhook_router as payment_webhook_router
from app.routes.brand_assets_router import router as brand_assets_router
from app.routes.catalog.catalog_router import router as catalog_router
from app.routes.content.content_admin_router import router as content_admin_router
from app.routes.content.content_router import router as content_router
from app.routes.content.content_router import support_router
from app.routes.earnings.earnings_router import router as earnings_router
from app.routes.health_router import router as health_router
from app.routes.live_work.admin_live_work_router import router as admin_live_work_router
from app.routes.live_work.business_live_work_router import router as business_live_work_router
from app.routes.live_work.worker_live_work_router import router as worker_live_work_router
from app.routes.lookups.lookup_router import LOOKUP_ROUTERS
from app.routes.lookups.shift_filter_router import router as shift_filter_router
from app.routes.notifications.notifications_router import router as notifications_router
from app.routes.profiles.admin_verification_router import router as admin_verification_router
from app.routes.promos.promo_router import business_router as promo_business_router
from app.routes.promos.promo_router import worker_router as promo_worker_router
from app.routes.ratings.ratings_router import router as ratings_router
from app.routes.realtime.realtime_router import router as realtime_router
from app.routes.shifts.assignments_router import router as assignments_router
from app.routes.shifts.business_shifts_router import live_router as business_live_router
from app.routes.shifts.business_shifts_router import router as business_shifts_router
from app.routes.shifts.worker_shifts_router import live_router as worker_live_router
from app.routes.shifts.worker_shifts_router import router as worker_shifts_router
from app.routes.support.admin_override_router import router as admin_override_router
from app.routes.users.me_router import router as me_router

_ROUTERS = (
    health_router,
    brand_assets_router,
    auth_router,
    me_router,
    *LOOKUP_ROUTERS,
    shift_filter_router,
    admin_verification_router,
    admin_account_deletion_router,
    # Before admin_crud_router: its /admin/{resource} would swallow /admin/faqs and /admin/terms.
    content_admin_router,
    admin_override_router,
    admin_live_work_router,
    admin_crud_router,
    notifications_router,
    business_live_work_router,
    worker_live_work_router,
    business_shifts_router,
    business_live_router,
    worker_shifts_router,
    worker_live_router,
    assignments_router,
    attendance_worker_router,
    attendance_business_router,
    billing_router,
    payment_webhook_router,
    earnings_router,
    ratings_router,
    catalog_router,
    content_router,
    support_router,
    promo_business_router,
    promo_worker_router,
    realtime_router,
)


def register_routes(app: FastAPI) -> None:
    for router in _ROUTERS:
        app.include_router(router)
