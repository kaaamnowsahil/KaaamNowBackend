-- users 1:1 worker_profiles; worker_profiles N:M work_categories; worker_profiles 1:1 worker_locations
SELECT kn_add_foreign_key('worker_profiles', 'worker_profiles_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('worker_profiles', 'worker_profiles_verified_by_fkey', 'verified_by_user_id', 'users', 'id', 'SET NULL');
SELECT kn_add_foreign_key('worker_work_categories', 'worker_work_categories_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
SELECT kn_add_foreign_key('worker_work_categories', 'worker_work_categories_category_fkey', 'category_id', 'work_categories', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('worker_locations', 'worker_locations_worker_fkey', 'worker_profile_id', 'worker_profiles', 'id', 'CASCADE');
