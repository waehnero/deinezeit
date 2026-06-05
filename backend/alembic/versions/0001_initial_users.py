"""Initial: Benutzer, WebAuthn, Sessions

Revision ID: 0001
Revises:
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PgEnum

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Benutzer-Rollen Enum anlegen
    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'employee')")
    userrole = PgEnum('admin', 'employee', name='userrole', create_type=False)

    # Benutzer-Tabelle
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', userrole, nullable=False, server_default='employee'),
        sa.Column('language', sa.String(10), nullable=False, server_default='de'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('totp_secret', sa.String(64), nullable=True),
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # WebAuthn Credentials (Face ID / Passkeys)
    op.create_table(
        'webauthn_credentials',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('credential_id', sa.Text(), nullable=False, unique=True),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('sign_count', sa.String(20), nullable=False, server_default='0'),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )

    # User Sessions (Refresh Tokens)
    op.create_table(
        'user_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )


def downgrade() -> None:
    op.drop_table('user_sessions')
    op.drop_table('webauthn_credentials')
    op.drop_table('users')
    op.execute("DROP TYPE userrole")
