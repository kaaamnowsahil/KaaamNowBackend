-- Worker "Work type" chips (many-to-many with work_categories).
CREATE TABLE IF NOT EXISTS worker_work_categories (
    worker_profile_id UUID NOT NULL,
    category_id       UUID NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT worker_work_categories_pk PRIMARY KEY (worker_profile_id, category_id)
);

CREATE INDEX IF NOT EXISTS worker_work_categories_category_idx
    ON worker_work_categories (category_id);
