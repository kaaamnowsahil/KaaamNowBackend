-- Two-way ratings after a shift (Figma "Business rates Worker" / "Worker rates Business").
CREATE TABLE IF NOT EXISTS ratings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id      UUID NOT NULL,
    assignment_id UUID NOT NULL,
    direction     VARCHAR(24) NOT NULL,
    rater_user_id UUID NOT NULL,
    ratee_user_id UUID NOT NULL,
    stars         SMALLINT NOT NULL,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    review        VARCHAR(1000) NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ratings_assignment_direction_uid UNIQUE (assignment_id, direction),
    CONSTRAINT ratings_direction_chk
        CHECK (direction IN ('business_to_worker', 'worker_to_business')),
    CONSTRAINT ratings_stars_chk CHECK (stars BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS ratings_ratee_idx ON ratings (ratee_user_id, created_at DESC);
