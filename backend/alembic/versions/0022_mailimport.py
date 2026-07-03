"""Mail-Import für das Aufgabenmodul (Etappe 3)

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-03

Neue Tabellen:
  - mail_accounts          (IMAP-/Graph-Mailboxen, persönlich oder global,
                            Zugangsdaten Fernet-verschlüsselt in secret_enc)
  - mail_task_suggestions  (KI-Aufgabenvorschläge aus E-Mails, je Vorschlag
                            eine Zeile; Übernahme erzeugt ein Todo)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'mail_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('protocol', sa.String(length=10), nullable=False),
        sa.Column('imap_host', sa.String(length=255), nullable=True),
        sa.Column('imap_port', sa.Integer(), nullable=True),
        sa.Column('imap_ssl', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('imap_user', sa.String(length=255), nullable=True),
        sa.Column('graph_tenant_id', sa.String(length=100), nullable=True),
        sa.Column('graph_client_id', sa.String(length=100), nullable=True),
        sa.Column('graph_mailbox', sa.String(length=255), nullable=True),
        sa.Column('secret_enc', sa.Text(), nullable=True),
        sa.Column('folder', sa.String(length=300), nullable=False, server_default='INBOX'),
        sa.Column('auto_scan', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('scan_interval_minutes', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('last_scan_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_mail_accounts_owner', 'mail_accounts', ['owner_user_id'])

    op.create_table(
        'mail_task_suggestions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('mail_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', sa.String(length=500), nullable=False),
        sa.Column('subject', sa.String(length=1000), nullable=True),
        sa.Column('sender', sa.String(length=500), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('body_preview', sa.Text(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('priority', sa.String(length=30), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='offen'),
        sa.Column('todo_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_mail_suggestions_account', 'mail_task_suggestions', ['account_id'])
    op.create_index('ix_mail_suggestions_status', 'mail_task_suggestions', ['status'])
    op.create_index('ix_mail_suggestions_message', 'mail_task_suggestions',
                    ['account_id', 'message_id'])


def downgrade():
    op.drop_index('ix_mail_suggestions_message', table_name='mail_task_suggestions')
    op.drop_index('ix_mail_suggestions_status', table_name='mail_task_suggestions')
    op.drop_index('ix_mail_suggestions_account', table_name='mail_task_suggestions')
    op.drop_table('mail_task_suggestions')
    op.drop_index('ix_mail_accounts_owner', table_name='mail_accounts')
    op.drop_table('mail_accounts')
