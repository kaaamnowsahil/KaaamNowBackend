-- users 1:N terms_acceptances
SELECT kn_add_foreign_key('terms_acceptances', 'terms_acceptances_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
