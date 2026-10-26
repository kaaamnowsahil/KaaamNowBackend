-- shift_assignments 1:N shift_extensions
SELECT kn_add_foreign_key('shift_extensions', 'shift_extensions_assignment_id_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('shift_extensions', 'shift_extensions_requested_by_fkey', 'requested_by_user_id', 'users', 'id', 'SET NULL');
