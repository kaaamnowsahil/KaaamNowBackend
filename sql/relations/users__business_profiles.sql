-- users 1:N business_profiles (one primary); business_types 1:N business_profiles;
-- work_categories 1:N business_profiles (legacy category)
SELECT kn_add_foreign_key('business_profiles', 'business_profiles_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('business_profiles', 'business_profiles_category_id_fkey', 'category_id', 'work_categories', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('business_profiles', 'business_profiles_business_type_id_fkey', 'business_type_id', 'business_types', 'id', 'RESTRICT');
SELECT kn_add_foreign_key('business_profiles', 'business_profiles_verified_by_fkey', 'verified_by_user_id', 'users', 'id', 'SET NULL');
SELECT kn_add_foreign_key('business_profile_types', 'business_profile_types_profile_fkey', 'business_profile_id', 'business_profiles', 'id', 'CASCADE');
SELECT kn_add_foreign_key('business_profile_types', 'business_profile_types_type_fkey', 'business_type_id', 'business_types', 'id', 'RESTRICT');
