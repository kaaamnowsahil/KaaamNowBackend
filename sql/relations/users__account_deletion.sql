SELECT kn_add_foreign_key(
    'account_deletion_requests', 'account_deletion_requests_user_fkey',
    'user_id', 'users', 'id', 'RESTRICT'
);
SELECT kn_add_foreign_key(
    'account_deletion_holds', 'account_deletion_holds_request_fkey',
    'request_id', 'account_deletion_requests', 'id', 'CASCADE'
);
SELECT kn_add_foreign_key(
    'account_deletion_holds', 'account_deletion_holds_actor_fkey',
    'created_by', 'users', 'id', 'SET NULL'
);
SELECT kn_add_foreign_key(
    'account_deletion_events', 'account_deletion_events_request_fkey',
    'request_id', 'account_deletion_requests', 'id', 'CASCADE'
);
SELECT kn_add_foreign_key(
    'account_deletion_events', 'account_deletion_events_actor_fkey',
    'actor_user_id', 'users', 'id', 'SET NULL'
);
