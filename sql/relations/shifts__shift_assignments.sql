-- shifts 1:N shift_assignments N:1 worker_profiles (source: dispatch or application)
SELECT kn_add_foreign_key('shift_assignments', 'shift_assignments_shift_id_fkey', 'shift_id', 'shifts', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_assignments', 'shift_assignments_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('shift_assignments', 'shift_assignments_dispatch_fkey', 'dispatch_id', 'live_dispatches', 'id', 'SET NULL');
SELECT kn_add_foreign_key('shift_assignments', 'shift_assignments_application_fkey', 'application_id', 'shift_applications', 'id', 'SET NULL');
SELECT kn_add_foreign_key('shift_assignments', 'shift_assignments_cancelled_by_fkey', 'cancelled_by_user_id', 'users', 'id', 'SET NULL');
