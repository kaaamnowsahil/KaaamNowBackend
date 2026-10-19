-- users 1:N user_roles / refresh_tokens / user_devices
SELECT kn_add_foreign_key('user_roles', 'user_roles_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('refresh_tokens', 'refresh_tokens_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('user_devices', 'user_devices_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
