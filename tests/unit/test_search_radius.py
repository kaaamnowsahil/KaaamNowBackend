"""Admin-editable search distances and the anonymised available-worker map."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.config.settings import load_settings
from app.services.admin.admin_resources import ADMIN_RESOURCES
from app.services.catalog import catalog_service
from app.services.live_work.live_work_views import MAP_POINT_DECIMALS, blur_point


class _Conn:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    async def fetchrow(self, *_: object) -> dict[str, Any] | None:
        return self.row


async def test_env_values_apply_until_admin_saves() -> None:
    settings = load_settings()
    radii = await catalog_service.search_radii(_Conn(None))  # type: ignore[arg-type]
    assert radii.live_initial_km == settings.live_initial_radius_km
    assert radii.live_max_km == settings.live_max_radius_km
    assert radii.scheduled_notify_km == settings.scheduled_notify_radius_km
    assert radii.feed_km == settings.feed_radius_km
    assert radii.worker_max_shift_km == settings.worker_max_shift_distance_km


async def test_admin_row_overrides_env() -> None:
    row = {
        "live_initial_radius_km": Decimal("4.0"),
        "live_max_radius_km": Decimal("8.5"),
        "scheduled_notify_radius_km": Decimal("25.0"),
        "feed_radius_km": Decimal("12.0"),
        "worker_max_shift_distance_km": Decimal("40.0"),
    }
    radii = await catalog_service.search_radii(_Conn(row))  # type: ignore[arg-type]
    assert (radii.live_initial_km, radii.live_max_km) == (4.0, 8.5)
    assert radii.scheduled_notify_km == 25.0
    assert (radii.feed_km, radii.worker_max_shift_km) == (12.0, 40.0)


def test_radius_settings_are_audited_and_cannot_be_deleted() -> None:
    resource = next(r for r in ADMIN_RESOURCES if r.name == "search_radius_settings")
    assert resource.audited
    assert "delete" not in resource.operations
    assert "singleton" in resource.read_only


@pytest.mark.parametrize(
    ("lat", "lng"),
    [(12.844838328620611, 80.1993712630982), (28.6139391, 77.2090212), (-33.8688, 151.2093)],
)
def test_map_dots_are_blurred(lat: float, lng: float) -> None:
    blurred_lat, blurred_lng = blur_point(lat, lng)
    assert blurred_lat == round(lat, MAP_POINT_DECIMALS)
    assert blurred_lng == round(lng, MAP_POINT_DECIMALS)
    assert abs(blurred_lat - lat) <= 0.0005 and abs(blurred_lng - lng) <= 0.0005
