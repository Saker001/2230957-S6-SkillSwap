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
