-- shift_assignments 1:1 attendance_records, 1:1 assignment_completion_codes; 1:N assignment_messages
SELECT kn_add_foreign_key('attendance_records', 'attendance_records_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('attendance_records', 'attendance_records_approved_by_fkey', 'approved_by_user_id', 'users', 'id', 'SET NULL');
SELECT kn_add_foreign_key('assignment_messages', 'assignment_messages_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('assignment_messages', 'assignment_messages_sender_fkey', 'sender_user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('assignment_completion_codes', 'assignment_completion_codes_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('assignment_completion_codes', 'assignment_completion_codes_shift_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
