-- shifts 1:N live_dispatches N:1 worker_profiles
SELECT kn_add_foreign_key('live_dispatches', 'live_dispatches_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('live_dispatches', 'live_dispatches_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
