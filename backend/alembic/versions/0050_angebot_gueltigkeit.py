"""Verkauf: Gültigkeitsdatum am Angebot (A-17h)

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-08

Ein Angebot ohne Gültigkeitsfrist bindet einen unbefristet an Preise, die man
vor Monaten kalkuliert hat. Jede Vergleichssoftware weist die Frist auf dem
Angebot aus; DeineZeit hatte dafür kein Feld.

``valid_until`` gilt bewusst für den ganzen Beleg und nicht nur für Angebote —
die Spalte kostet nichts, und für eine Auftragsbestätigung mit Frist gibt es
denkbare Fälle. Ausgewertet wird sie vorerst nur beim Angebot.

**Bewusst NICHT umgesetzt: ein Status „abgelaufen".** Ein abgelaufenes Angebot
ist nicht abgelehnt — der Kunde meldet sich oft zwei Tage später doch. Würde
ein Hintergrundlauf es auf ``abgelehnt`` setzen, ginge der Unterschied zwischen
„hat abgesagt" und „hat sich nicht gemeldet" verloren, und der wird für die
Angebotsverfolgung noch gebraucht. Der Ablauf wird deshalb aus dem Datum
abgeleitet und angezeigt, nicht gespeichert.
"""
from alembic import op
import sqlalchemy as sa

revision = '0050'
down_revision = '0049'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('valid_until', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('invoices', 'valid_until')
