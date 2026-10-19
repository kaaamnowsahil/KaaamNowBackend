-- One line per paid worker ("4 × ₹150 = ₹600") plus one platform-fee line.
CREATE TABLE IF NOT EXISTS shift_invoice_lines (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id    UUID NOT NULL,
    assignment_id UUID,
    line_kind     VARCHAR(16) NOT NULL,
    description   VARCHAR(200) NOT NULL,
    minutes       INTEGER,
    rate_minor    BIGINT,
    amount_minor  BIGINT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT shift_invoice_lines_kind_chk CHECK (line_kind IN ('worker_pay', 'platform_fee')),
    CONSTRAINT shift_invoice_lines_amount_chk CHECK (amount_minor >= 0)
);

CREATE INDEX IF NOT EXISTS shift_invoice_lines_invoice_idx
    ON shift_invoice_lines (invoice_id, sort_order);
