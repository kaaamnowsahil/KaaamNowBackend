-- business_profiles 1:N shifts; work_categories 1:N shifts; shifts 1:N shift_status_history
SELECT kn_add_foreign_key('shifts', 'shifts_business_profile_id_fkey', 'business_profile_id', 'business_profiles', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shifts', 'shifts_category_id_fkey', 'category_id', 'work_categories', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_status_history', 'shift_status_history_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('shift_status_history', 'shift_status_history_actor_fkey', 'actor_user_id', 'users', 'id', 'SET NULL');
