"""Anzahlungs-, Teil- und Schlussrechnung (C-10)

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-09

Im Projektgeschäft wird nicht einmal am Ende abgerechnet, sondern in Stufen:
Anzahlung vor Baubeginn, Teilrechnungen nach Baufortschritt, am Schluss eine
Schlussrechnung über die Gesamtleistung, von der alles bereits Fakturierte
wieder abgezogen wird.

**Warum ein Feld und keine eigene Belegart** (Entscheidung Oliver): Im Code
steht an sieben Stellen ``doc_type not in ("rechnung", "gutschrift")`` — bei
Zahlungen, in der UVA, im Buchungsjournal, beim Mahnwesen. Eine neue Belegart
wäre dort überall stillschweigend herausgefallen; eine Anzahlungsrechnung, die
nicht in der UVA landet, ist ein Steuerfehler, der niemandem auffällt. Die
Abrechnungsstufe ist deshalb eine Eigenschaft der Rechnung, kein neuer Typ.
``NULL`` = gewöhnliche Rechnung, also das bisherige Verhalten.

**Der Strang** (``chain_id``) hält zusammen, was zu einem Bauvorhaben gehört.
Bewusst nicht über ``project_id``: Zwei Bauabschnitte desselben Projekts
würden sich sonst vermischen, und ohne gepflegtes Projekt gäbe es gar keine
Schlussrechnung. Der erste Beleg des Strangs zeigt auf sich selbst — dann ist
„alle Belege des Strangs" eine einzige Abfrage statt einer Sonderbehandlung
für den Kopf.

Der Abzug in der Schlussrechnung entsteht als **Positionen** vom neuen Typ
``advance_deduction`` — je Steuersatz eine Zeile mit negativem Betrag. Dafür
braucht es keine neue Spalte: Die vorhandene Positionszeile trägt Steuersatz
und Betrag bereits, und alle Auswerter (Summen, MwSt.-Aufschlüsselung,
BMD-Export) rechnen damit automatisch richtig. Eine einzelne Sammelzeile wäre
bei gemischten Steuersätzen falsch — die Aufschlüsselung auf dem Beleg ginge
nicht mehr auf.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None


def upgrade():
    # anzahlung | teil | schluss — NULL = gewöhnliche Rechnung
    op.add_column('invoices', sa.Column('billing_stage', sa.String(20), nullable=True))

    # Kopf des Abrechnungsstrangs; der Kopf selbst zeigt auf sich.
    op.add_column('invoices', sa.Column('chain_id', postgresql.UUID(as_uuid=True),
                                        nullable=True))
    op.create_foreign_key('fk_invoices_chain', 'invoices', 'invoices',
                          ['chain_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_invoices_chain_id', 'invoices', ['chain_id'])

    # Anteil der Anzahlung, wie er angefordert wurde — nur zur Anzeige auf dem
    # Beleg („Anzahlung 30 % der Auftragssumme"). Gerechnet wird mit dem
    # Betrag, nicht mit dem Prozentsatz: Wird das Angebot später geändert,
    # bliebe eine nachgerechnete Prozentzahl sonst nicht bei dem, was der
    # Kunde tatsächlich bekommen hat.
    op.add_column('invoices', sa.Column('advance_percent', sa.Numeric(5, 2), nullable=True))


def downgrade():
    op.drop_column('invoices', 'advance_percent')
    op.drop_index('ix_invoices_chain_id', table_name='invoices')
    op.drop_constraint('fk_invoices_chain', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'chain_id')
    op.drop_column('invoices', 'billing_stage')
