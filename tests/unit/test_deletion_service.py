from app.services.users.deletion_service import _blockers


def test_deletion_blockers_are_descriptive_and_omit_clear_categories() -> None:
    assert _blockers(
        {
            "active_shifts": 2,
            "active_bookings": 0,
            "pending_payments": 1,
            "open_complaints": 0,
            "pending_verification_reviews": 0,
        }
    ) == ["2 active shifts", "1 pending payment"]
