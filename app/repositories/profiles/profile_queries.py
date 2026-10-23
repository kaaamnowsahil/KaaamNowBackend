"""SQL for business_profiles, worker_profiles, worker_work_categories, worker_locations."""

from __future__ import annotations

ENSURE_BUSINESS_PROFILE = """
INSERT INTO business_profiles (user_id) VALUES ($1)
ON CONFLICT (user_id) DO NOTHING
"""

ENSURE_WORKER_PROFILE = """
INSERT INTO worker_profiles (user_id) VALUES ($1)
ON CONFLICT (user_id) DO NOTHING
"""

_BUSINESS_COLUMNS = """
bp.id, bp.user_id, bp.business_name, bp.category_id, wc.slug AS category_slug,
wc.name AS category_name, bp.logo_url, bp.address_text, bp.locality, bp.latitude, bp.longitude,
bp.verification_status, bp.verification_note, bp.verified_at, bp.rating_avg, bp.rating_count,
u.phone, u.full_name AS owner_name, bp.contact_name, bp.email, bp.business_type_id,
bt.slug AS business_type_slug, bt.name AS business_type_name, bp.created_at, bp.updated_at
"""

GET_BUSINESS_PROFILE_BY_USER = f"""
SELECT {_BUSINESS_COLUMNS}
FROM business_profiles bp
JOIN users u ON u.id = bp.user_id
LEFT JOIN work_categories wc ON wc.id = bp.category_id
LEFT JOIN business_types bt ON bt.id = bp.business_type_id
WHERE bp.user_id = $1
"""

GET_BUSINESS_PROFILE_BY_ID = f"""
SELECT {_BUSINESS_COLUMNS}
FROM business_profiles bp
JOIN users u ON u.id = bp.user_id
LEFT JOIN work_categories wc ON wc.id = bp.category_id
LEFT JOIN business_types bt ON bt.id = bp.business_type_id
WHERE bp.id = $1
"""

UPDATE_BUSINESS_PROFILE = """
UPDATE business_profiles SET
    business_name = COALESCE($2, business_name),
    category_id = COALESCE($3, category_id),
    address_text = COALESCE($4, address_text),
    locality = COALESCE($5, locality),
    latitude = COALESCE($6, latitude),
    longitude = COALESCE($7, longitude),
    contact_name = COALESCE($8, contact_name),
    email = COALESCE($9, email),
    business_type_id = COALESCE($10, business_type_id),
    updated_at = now()
WHERE user_id = $1
"""

REPLACE_BUSINESS_LOGO_URL = """
UPDATE business_profiles bp SET logo_url = $2, updated_at = now()
FROM (SELECT id, logo_url FROM business_profiles WHERE user_id = $1 FOR UPDATE) previous
WHERE bp.id = previous.id
RETURNING previous.logo_url
"""

_WORKER_COLUMNS = """
wp.id, wp.user_id, u.full_name, u.email, u.photo_url, u.phone, wp.age, wp.address_text,
wp.locality,
wp.latitude, wp.longitude, wp.verification_status, wp.verification_note, wp.verified_at,
wp.is_available, wp.availability_changed_at, wp.rating_avg, wp.rating_count,
wp.completed_shift_count, wp.created_at, wp.updated_at,
COALESCE(
    (SELECT array_agg(wc.slug ORDER BY wc.sort_order)
     FROM worker_work_categories wwc JOIN work_categories wc ON wc.id = wwc.category_id
     WHERE wwc.worker_profile_id = wp.id),
    ARRAY[]::varchar[]
) AS category_slugs
"""

GET_WORKER_PROFILE_BY_USER = f"""
SELECT {_WORKER_COLUMNS}
FROM worker_profiles wp JOIN users u ON u.id = wp.user_id
WHERE wp.user_id = $1
"""

GET_WORKER_PROFILE_BY_ID = f"""
SELECT {_WORKER_COLUMNS}
FROM worker_profiles wp JOIN users u ON u.id = wp.user_id
WHERE wp.id = $1
"""

UPDATE_WORKER_PROFILE = """
UPDATE worker_profiles SET
    address_text = COALESCE($2, address_text),
    locality = COALESCE($3, locality),
    latitude = COALESCE($4, latitude),
    longitude = COALESCE($5, longitude),
    age = COALESCE($6, age),
    updated_at = now()
WHERE user_id = $1
"""

DELETE_WORKER_CATEGORIES = "DELETE FROM worker_work_categories WHERE worker_profile_id = $1"

INSERT_WORKER_CATEGORIES = """
INSERT INTO worker_work_categories (worker_profile_id, category_id)
SELECT $1, unnest($2::uuid[])
ON CONFLICT DO NOTHING
"""

SET_WORKER_AVAILABILITY = """
UPDATE worker_profiles SET is_available = $2, availability_changed_at = $3, updated_at = now()
WHERE id = $1
"""

UPSERT_WORKER_LOCATION = """
INSERT INTO worker_locations (worker_profile_id, latitude, longitude, accuracy_m, recorded_at)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (worker_profile_id) DO UPDATE SET
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    accuracy_m = EXCLUDED.accuracy_m,
    recorded_at = EXCLUDED.recorded_at
"""

DELETE_WORKER_LOCATION = "DELETE FROM worker_locations WHERE worker_profile_id = $1"

GET_WORKER_LOCATION = """
SELECT latitude, longitude, accuracy_m, recorded_at FROM worker_locations
WHERE worker_profile_id = $1
"""

LIST_VERIFICATIONS_WORKERS = f"""
SELECT {_WORKER_COLUMNS}
FROM worker_profiles wp JOIN users u ON u.id = wp.user_id
WHERE wp.verification_status = $1
ORDER BY wp.created_at
LIMIT $2 OFFSET $3
"""

LIST_VERIFICATIONS_BUSINESSES = f"""
SELECT {_BUSINESS_COLUMNS}
FROM business_profiles bp
JOIN users u ON u.id = bp.user_id
LEFT JOIN work_categories wc ON wc.id = bp.category_id
LEFT JOIN business_types bt ON bt.id = bp.business_type_id
WHERE bp.verification_status = $1
ORDER BY bp.created_at
LIMIT $2 OFFSET $3
"""

SET_WORKER_VERIFICATION = """
UPDATE worker_profiles SET verification_status = $2::varchar, verification_note = $3,
    verified_at = CASE WHEN $2::varchar = 'verified' THEN $4 ELSE NULL END,
    verified_by_user_id = $5, updated_at = now()
WHERE id = $1
RETURNING user_id
"""

SET_BUSINESS_VERIFICATION = """
UPDATE business_profiles SET verification_status = $2::varchar, verification_note = $3,
    verified_at = CASE WHEN $2::varchar = 'verified' THEN $4 ELSE NULL END,
    verified_by_user_id = $5, updated_at = now()
WHERE id = $1
RETURNING user_id
"""

RECOMPUTE_WORKER_RATING = """
UPDATE worker_profiles wp SET
    rating_avg = COALESCE(agg.avg_stars, 0), rating_count = agg.n, updated_at = now()
FROM (
    SELECT round(avg(stars)::numeric, 2) AS avg_stars, count(*) AS n
    FROM ratings WHERE ratee_user_id = $2 AND direction = 'business_to_worker'
) agg
WHERE wp.user_id = $2 AND wp.id = $1
"""

RECOMPUTE_BUSINESS_RATING = """
UPDATE business_profiles bp SET
    rating_avg = COALESCE(agg.avg_stars, 0), rating_count = agg.n, updated_at = now()
FROM (
    SELECT round(avg(stars)::numeric, 2) AS avg_stars, count(*) AS n
    FROM ratings WHERE ratee_user_id = $2 AND direction = 'worker_to_business'
) agg
WHERE bp.user_id = $2 AND bp.id = $1
"""

INCREMENT_COMPLETED_SHIFTS = """
UPDATE worker_profiles SET completed_shift_count = completed_shift_count + 1, updated_at = now()
WHERE id = ANY($1::uuid[])
"""
