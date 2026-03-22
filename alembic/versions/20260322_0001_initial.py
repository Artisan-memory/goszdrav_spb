"""Initial schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260322_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.UniqueConstraint("telegram_id", name="uq_telegram_users_telegram_id"),
    )
    op.create_index("ix_telegram_users_telegram_id", "telegram_users", ["telegram_id"], unique=False)

    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name_encrypted", sa.Text(), nullable=True),
        sa.Column("email_encrypted", sa.Text(), nullable=True),
        sa.Column("birth_date_encrypted", sa.Text(), nullable=True),
        sa.Column("district_code", sa.String(length=64), nullable=True),
        sa.Column("organization_external_id", sa.String(length=128), nullable=True),
        sa.Column("organization_label", sa.String(length=255), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_district_code", "user_profiles", ["district_code"], unique=False)

    op.create_table(
        "watch_targets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("district_code", sa.String(length=64), nullable=False),
        sa.Column("organization_external_id", sa.String(length=128), nullable=True),
        sa.Column("organization_label", sa.String(length=255), nullable=False),
        sa.Column("specialty_external_id", sa.String(length=128), nullable=True),
        sa.Column("specialty_label", sa.String(length=255), nullable=False),
        sa.Column("doctor_external_id", sa.String(length=128), nullable=True),
        sa.Column("doctor_label", sa.String(length=255), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default=sa.text("'notify'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("latest_result_status", sa.String(length=32), nullable=True),
        sa.Column("latest_result_summary", sa.Text(), nullable=True),
        sa.Column("latest_result_url", sa.String(length=1024), nullable=True),
        sa.Column("last_seen_slots_count", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_watch_targets_user_id", "watch_targets", ["user_id"], unique=False)
    op.create_index("ix_watch_targets_district_code", "watch_targets", ["district_code"], unique=False)

    op.create_table(
        "scrape_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("watch_target_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("slots_count", sa.Integer(), nullable=True),
        sa.Column("result_url", sa.String(length=1024), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "happened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["watch_target_id"], ["watch_targets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scrape_events_watch_target_id", "scrape_events", ["watch_target_id"], unique=False)
    op.create_index("ix_scrape_events_happened_at", "scrape_events", ["happened_at"], unique=False)

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("watch_target_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("direct_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watch_target_id"], ["watch_targets.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_user_notifications_watch_target_id",
        "user_notifications",
        ["watch_target_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_telegram_user_id",
        "user_notifications",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index("ix_user_notifications_fingerprint", "user_notifications", ["fingerprint"], unique=False)
    op.create_index("ix_user_notifications_sent_at", "user_notifications", ["sent_at"], unique=False)

    op.create_table(
        "booking_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("watch_target_id", sa.BigInteger(), nullable=False),
        sa.Column("scrape_event_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("slot_time", sa.String(length=32), nullable=True),
        sa.Column("direct_url", sa.String(length=1024), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(["scrape_event_id"], ["scrape_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["watch_target_id"], ["watch_targets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_booking_attempts_watch_target_id", "booking_attempts", ["watch_target_id"], unique=False)
    op.create_index("ix_booking_attempts_scrape_event_id", "booking_attempts", ["scrape_event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_booking_attempts_scrape_event_id", table_name="booking_attempts")
    op.drop_index("ix_booking_attempts_watch_target_id", table_name="booking_attempts")
    op.drop_table("booking_attempts")
    op.drop_index("ix_user_notifications_sent_at", table_name="user_notifications")
    op.drop_index("ix_user_notifications_fingerprint", table_name="user_notifications")
    op.drop_index("ix_user_notifications_telegram_user_id", table_name="user_notifications")
    op.drop_index("ix_user_notifications_watch_target_id", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_index("ix_scrape_events_happened_at", table_name="scrape_events")
    op.drop_index("ix_scrape_events_watch_target_id", table_name="scrape_events")
    op.drop_table("scrape_events")
    op.drop_index("ix_watch_targets_district_code", table_name="watch_targets")
    op.drop_index("ix_watch_targets_user_id", table_name="watch_targets")
    op.drop_table("watch_targets")
    op.drop_index("ix_user_profiles_district_code", table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_index("ix_telegram_users_telegram_id", table_name="telegram_users")
    op.drop_table("telegram_users")
