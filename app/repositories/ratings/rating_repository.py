"""asyncpg persistence for ratings."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.ratings.rating_queries import (
    INSERT_RATING,
    LIST_RATINGS_FOR_ASSIGNMENT,
    LIST_RECENT_REVIEWS_FOR_USER,
)


async def insert_rating(
    conn: asyncpg.Connection,
    *,
    shift_id: UUID,
    assignment_id: UUID,
    direction: str,
    rater_user_id: UUID,
    ratee_user_id: UUID,
    stars: int,
    tags: list[str],
    review: str,
) -> asyncpg.Record | None:
    """Return None when this direction was already rated for the assignment."""
    return await conn.fetchrow(
        INSERT_RATING,
        shift_id,
        assignment_id,
        direction,
        rater_user_id,
        ratee_user_id,
        stars,
        tags,
        review,
    )


async def list_ratings_for_assignment(
    conn: asyncpg.Connection, assignment_id: UUID
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_RATINGS_FOR_ASSIGNMENT, assignment_id)


async def list_recent_reviews(
    conn: asyncpg.Connection, ratee_user_id: UUID, direction: str, limit: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_RECENT_REVIEWS_FOR_USER, ratee_user_id, direction, limit)
