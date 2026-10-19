-- worker_profiles 1:N payout_accounts / withdrawals / earning_ledger_entries
SELECT kn_add_foreign_key('payout_accounts', 'payout_accounts_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
SELECT kn_add_foreign_key('withdrawals', 'withdrawals_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('withdrawals', 'withdrawals_payout_account_fkey', 'payout_account_id', 'payout_accounts', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('earning_ledger_entries', 'earning_ledger_entries_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('earning_ledger_entries', 'earning_ledger_entries_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('earning_ledger_entries', 'earning_ledger_entries_invoice_fkey', 'invoice_id', 'shift_invoices', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('earning_ledger_entries', 'earning_ledger_entries_withdrawal_fkey', 'withdrawal_id', 'withdrawals', 'id', 'RESTRICT');
