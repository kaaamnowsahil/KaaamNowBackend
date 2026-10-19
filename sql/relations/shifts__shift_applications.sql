-- shifts 1:N shift_applications N:1 worker_profiles
SELECT kn_add_foreign_key('shift_applications', 'shift_applications_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('shift_applications', 'shift_applications_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
