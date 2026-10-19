-- shift_assignments 1:N ratings (max one per direction)
SELECT kn_add_foreign_key('ratings', 'ratings_shift_id_fkey', 'shift_id', 'shifts', 'id', 'CASCADE');
SELECT kn_add_foreign_key('ratings', 'ratings_assignment_fkey', 'assignment_id', 'shift_assignments', 'id', 'CASCADE');
SELECT kn_add_foreign_key('ratings', 'ratings_rater_fkey', 'rater_user_id', 'users', 'id', 'CASCADE');
SELECT kn_add_foreign_key('ratings', 'ratings_ratee_fkey', 'ratee_user_id', 'users', 'id', 'CASCADE');
