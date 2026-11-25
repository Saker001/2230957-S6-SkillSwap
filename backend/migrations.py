from sqlalchemy import Engine, inspect, text


def migrate_resource_ownership(engine: Engine) -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "skill_listings" in tables:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("skill_listings")
            }
            if "owner_id" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE skill_listings ADD COLUMN owner_id "
                        "INTEGER REFERENCES users(id) ON DELETE SET NULL"
                    )
                )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_skill_listings_owner_id "
                    "ON skill_listings (owner_id)"
                )
            )

        if "session_requests" in tables:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("session_requests")
            }
            if "learner_id" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE session_requests ADD COLUMN learner_id "
                        "INTEGER REFERENCES users(id) ON DELETE SET NULL"
                    )
                )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_session_requests_learner_id "
                    "ON session_requests (learner_id)"
                )
            )


def migrate_admin_user_fields(engine: Engine) -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "users" not in tables:
            return
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "is_banned" not in columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE")
            )
        if "ban_reason" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN ban_reason VARCHAR(500)"))
        if "banned_at" not in columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN banned_at TIMESTAMP WITH TIME ZONE")
            )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_users_is_banned ON users (is_banned)")
        )


def migrate_audit_event_client_metadata(engine: Engine) -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "audit_events" not in tables:
            return
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("audit_events")
        }
        if "ip_address" not in columns:
            connection.execute(
                text("ALTER TABLE audit_events ADD COLUMN ip_address VARCHAR(64)")
            )
        if "user_agent" not in columns:
            connection.execute(
                text("ALTER TABLE audit_events ADD COLUMN user_agent VARCHAR(500)")
            )
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("ALTER TABLE audit_events ALTER COLUMN target_id TYPE VARCHAR(254)")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_events_ip_address "
                "ON audit_events (ip_address)"
            )
        )
