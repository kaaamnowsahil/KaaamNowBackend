-- users 1:N notifications / support_tickets
SELECT kn_add_foreign_key('notifications', 'notifications_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('support_tickets', 'support_tickets_user_id_fkey', 'user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('support_tickets', 'support_tickets_shift_id_fkey', 'shift_id', 'shifts', 'id', 'SET NULL');
