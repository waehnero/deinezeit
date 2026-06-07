"""E-Mail-Vorlagen pro Belegart

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-07

Neue Tabelle email_templates:
  - doc_type  (rechnung, angebot, auftragsbestaetigung, gutschrift, lieferschein)
  - subject   (Betreff-Vorlage mit Platzhaltern)
  - body_html (HTML-Body mit Platzhaltern)
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

DEFAULT_TEMPLATES = [
    (
        'rechnung',
        'Rechnung {nummer} von {firma}',
        '''<p>Sehr geehrte Damen und Herren,</p>
<p>anbei erhalten Sie unsere <strong>Rechnung {nummer}</strong> vom {datum}.</p>
<p>Bitte überweisen Sie den Betrag von <strong>{betrag}</strong> bis zum <strong>{faellig}</strong> auf das angegebene Konto.</p>
<p>Bei Fragen stehen wir Ihnen gerne zur Verfügung.</p>
<p>Mit freundlichen Grüßen<br>{firma}</p>''',
    ),
    (
        'angebot',
        'Angebot {nummer} von {firma}',
        '''<p>Sehr geehrte Damen und Herren,</p>
<p>vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser <strong>Angebot {nummer}</strong> vom {datum}.</p>
<p>Das Angebot gilt bis zum <strong>{faellig}</strong>.</p>
<p>Wir freuen uns auf Ihre Rückmeldung.</p>
<p>Mit freundlichen Grüßen<br>{firma}</p>''',
    ),
    (
        'auftragsbestaetigung',
        'Auftragsbestätigung {nummer} von {firma}',
        '''<p>Sehr geehrte Damen und Herren,</p>
<p>wir freuen uns, Ihnen die Annahme Ihres Auftrags mit unserer <strong>Auftragsbestätigung {nummer}</strong> vom {datum} zu bestätigen.</p>
<p>Bei Fragen stehen wir Ihnen gerne zur Verfügung.</p>
<p>Mit freundlichen Grüßen<br>{firma}</p>''',
    ),
    (
        'gutschrift',
        'Gutschrift {nummer} von {firma}',
        '''<p>Sehr geehrte Damen und Herren,</p>
<p>anbei erhalten Sie unsere <strong>Gutschrift {nummer}</strong> vom {datum} über <strong>{betrag}</strong>.</p>
<p>Mit freundlichen Grüßen<br>{firma}</p>''',
    ),
    (
        'lieferschein',
        'Lieferschein {nummer} von {firma}',
        '''<p>Sehr geehrte Damen und Herren,</p>
<p>anbei erhalten Sie unseren <strong>Lieferschein {nummer}</strong> vom {datum}.</p>
<p>Mit freundlichen Grüßen<br>{firma}</p>''',
    ),
]


def upgrade() -> None:
    op.create_table(
        'email_templates',
        sa.Column('doc_type',   sa.String(50),  primary_key=True),
        sa.Column('subject',    sa.Text,        nullable=False, server_default=''),
        sa.Column('body_html',  sa.Text,        nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    conn = op.get_bind()
    for doc_type, subject, body_html in DEFAULT_TEMPLATES:
        conn.execute(sa.text("""
            INSERT INTO email_templates (doc_type, subject, body_html)
            VALUES (:doc_type, :subject, :body_html)
            ON CONFLICT (doc_type) DO NOTHING
        """), {"doc_type": doc_type, "subject": subject, "body_html": body_html})


def downgrade() -> None:
    op.drop_table('email_templates')
