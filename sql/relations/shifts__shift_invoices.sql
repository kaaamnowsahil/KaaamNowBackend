-- shifts 1:1 shift_invoices 1:N shift_invoice_lines; shift_invoices 1:N payments
SELECT kn_add_foreign_key('shift_invoices', 'shift_invoices_shift_id_fkey', 'shift_id', 'shifts', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_invoices', 'shift_invoices_business_fkey', 'business_profile_id', 'business_profiles', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_invoices', 'shift_invoices_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_invoice_lines', 'shift_invoice_lines_invoice_fkey', 'invoice_id', 'shift_invoices', 'id', 'CASCADE');
SELECT kn_add_foreign_key('shift_invoice_lines', 'shift_invoice_lines_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('payments', 'payments_invoice_id_fkey', 'invoice_id', 'shift_invoices', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('payments', 'payments_business_fkey', 'business_profile_id', 'business_profiles', 'id', 'RESTRICT');
