"""Two-way ratings: each side rates the other once per assignment after check-out."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.catalog.catalog_route_strings import (
    DIRECTION_BUSINESS_TO_WORKER,
    DIRECTION_WORKER_TO_BUSINESS,
    RATING_TAGS,
)
from app.constants.notifications.notification_route_strings import KIND_RATING_RECEIVED
from app.constants.ratings.rating_route_strings import (
    MSG_ALREADY_RATED,
    MSG_INVALID_TAGS,
    MSG_RATING_NOT_ALLOWED,
)
from app.constants.shifts.shift_route_strings import ASG_WORKED_STATUSES
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict
from app.repositories.profiles import profile_repository
from app.repositories.ratings import rating_repository
from app.schemas.ratings.rating_schemas import AssignmentRatings, RatingCreate
from app.schemas.shifts.assignment_schemas import RatingView
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify
from app.services.shifts.assignment_service import PARTY_WORKER, load_context


def _direction(party: str) -> str:
    return DIRECTION_WORKER_TO_BUSINESS if party == PARTY_WORKER else DIRECTION_BUSINESS_TO_WORKER


def _view(row: asyncpg.Record) -> RatingView:
    return RatingView(
        direction=row["direction"],
        stars=row["stars"],
        tags=list(row["tags"]),
        review=row["review"],
        created_at=row["created_at"],
    )


async def list_ratings(user: AuthenticatedUser, assignment_id: UUID) -> AssignmentRatings:
    async with get_pool().acquire() as conn:
        ctx, party = await load_context(conn, assignment_id, user)
        rows = await rating_repository.list_ratings_for_assignment(conn, assignment_id)
    direction = _direction(party)
    return AssignmentRatings(
        items=[_view(r) for r in rows],
        can_rate=ctx["status"] in ASG_WORKED_STATUSES
        and not any(r["direction"] == direction for r in rows),
        my_direction=direction,
    )


async def rate(user: AuthenticatedUser, assignment_id: UUID, body: RatingCreate) -> RatingView:
    tags = list(dict.fromkeys(t.strip() for t in body.tags if t.strip()))
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            if ctx["status"] not in ASG_WORKED_STATUSES:
                raise conflict("rating_not_allowed", MSG_RATING_NOT_ALLOWED)
            direction = _direction(party)
            invalid = [t for t in tags if t not in RATING_TAGS[direction]]
            if invalid:
                raise bad_request("invalid_rating_tags", MSG_INVALID_TAGS, {"tags": invalid})
            worker_rates = party == PARTY_WORKER
            ratee_user_id = ctx["business_user_id"] if worker_rates else ctx["worker_user_id"]
            row = await rating_repository.insert_rating(
                conn,
                shift_id=ctx["shift_id"],
                assignment_id=assignment_id,
                direction=direction,
                rater_user_id=user.user_id,
                ratee_user_id=ratee_user_id,
                stars=body.stars,
                tags=tags,
                review=body.review.strip(),
            )
            if row is None:
                raise conflict("already_rated", MSG_ALREADY_RATED)
            if worker_rates:
                await profile_repository.recompute_business_rating(
                    conn, ctx["business_profile_id"], ratee_user_id
                )
            else:
                await profile_repository.recompute_worker_rating(
                    conn, ctx["worker_profile_id"], ratee_user_id
                )
            await notify(
                conn,
                ratee_user_id,
                KIND_RATING_RECEIVED,
                "You got a new rating",
                f"{body.stars}★ for {ctx['job_title']}",
                {"assignment_id": assignment_id, "shift_id": ctx["shift_id"]},
            )
    return _view(row)
