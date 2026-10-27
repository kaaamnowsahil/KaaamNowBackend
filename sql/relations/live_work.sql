-- Live Work: shifts 1:1 live_booking_pricing; shift_assignments 1:1 live_arrival_codes;
-- shift_assignments 1:N live_extensions; shifts 1:N live_refunds N:1 payments.
SELECT kn_add_foreign_key('live_booking_pricing', 'live_booking_pricing_shift_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_booking_pricing', 'live_booking_pricing_business_fkey', 'business_profile_id', 'business_profiles', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_arrival_codes', 'live_arrival_codes_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_arrival_codes', 'live_arrival_codes_shift_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_extensions', 'live_extensions_shift_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_extensions', 'live_extensions_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_extensions', 'live_extensions_invoice_fkey', 'invoice_id', 'shift_invoices', 'id', 'SET NULL');
SELECT kn_add_foreign_key('live_refunds', 'live_refunds_shift_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_refunds', 'live_refunds_payment_fkey', 'payment_id', 'payments', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('live_refunds', 'live_refunds_invoice_fkey', 'invoice_id', 'shift_invoices', 'id', 'RESTRICT');
