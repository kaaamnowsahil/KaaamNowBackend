-- cancellation_policies 1:N tiers; shifts / assignments 1:N cancellation_charges;
-- worker_profiles 1:N worker_strikes; users 1:N owned promo codes.
SELECT kn_add_foreign_key('cancellation_policy_tiers', 'cancellation_policy_tiers_policy_fkey', 'policy_version', 'cancellation_policies', 'version', 'CASCADE');
SELECT kn_add_foreign_key('cancellation_charges', 'cancellation_charges_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('cancellation_charges', 'cancellation_charges_assignment_id_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('cancellation_charges', 'cancellation_charges_voucher_fkey', 'voucher_promo_id', 'promo_codes', 'id', 'SET NULL');
SELECT kn_add_foreign_key('worker_strikes', 'worker_strikes_worker_profile_id_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
SELECT kn_add_foreign_key('worker_strikes', 'worker_strikes_assignment_id_fkey', 'assignment_id', 'shift_assignments', 'id', 'SET NULL');
SELECT kn_add_foreign_key('promo_codes', 'promo_codes_owner_user_id_fkey', 'owner_user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('promo_codes', 'promo_codes_source_shift_id_fkey', 'source_shift_id', 'shifts', 'id', 'SET NULL');
SELECT kn_add_foreign_key('promo_redemptions', 'promo_redemptions_promo_code_id_fkey', 'promo_code_id', 'promo_codes', 'id', 'CASCADE');
SELECT kn_add_foreign_key('promo_redemptions', 'promo_redemptions_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('promo_redemptions', 'promo_redemptions_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('promo_redemptions', 'promo_redemptions_assignment_id_fkey', 'assignment_id', 'shift_assignments', 'id', 'SET NULL');
SELECT kn_add_foreign_key('shifts', 'shifts_promo_code_id_fkey', 'promo_code_id', 'promo_codes', 'id', 'SET NULL');
SELECT kn_add_foreign_key('admin_overrides', 'admin_overrides_assignment_id_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('admin_overrides', 'admin_overrides_ticket_fkey', 'support_ticket_id', 'support_tickets', 'id', 'SET NULL');
SELECT kn_add_foreign_key('admin_overrides', 'admin_overrides_admin_user_id_fkey', 'admin_user_id', 'users', 'id', 'SET NULL');
