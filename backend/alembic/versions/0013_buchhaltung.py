"""Buchhaltungsmodul: Debitor/Kreditor, Kontenplan EKR, Konto auf Artikel

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-04

Änderungen:
  1. Kontakte/Finanz-Tab: Debitornummer + Kreditornummer (idempotent)
  2. Neue Tabelle accounting_accounts (Kontenplan, vorbefüllt mit EKR)
  3. Artikel: Spalte erloes_konto (Erlöskonto-Nummer)
  4. invoice_positions: Spalte account_nr (überschreibbares Konto pro Position)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

# ─── EKR-Kontenplan (Auszug für Dienstleistungsunternehmen) ──────────────────
EKR_ACCOUNTS = [
    # (nr, name, typ, ust_code, beschreibung)
    # Umlaufvermögen / Forderungen
    ("2000", "Forderungen aus Lieferungen und Leistungen",  "aktiv",   None,  "Debitoren-Sammelkonto"),
    ("2700", "Kassa",                                        "aktiv",   None,  "Barkasse"),
    ("2800", "Bank",                                         "aktiv",   None,  "Bankkonto"),
    # Verbindlichkeiten
    ("3300", "Verbindlichkeiten aus Lieferungen und Leistungen", "passiv", None, "Kreditoren-Sammelkonto"),
    ("3500", "Umsatzsteuer 20%",                             "passiv",  "U20", "Umsatzsteuerverbindlichkeit 20%"),
    ("3510", "Umsatzsteuer 10%",                             "passiv",  "U10", "Umsatzsteuerverbindlichkeit 10%"),
    ("3520", "Umsatzsteuer 0% / befreit",                    "passiv",  "U00", "Steuerfreie Umsätze"),
    # Erlöse
    ("4000", "Erlöse 20% USt",                               "ertrag",  "U20", "Standarderlöse mit 20% Umsatzsteuer"),
    ("4020", "Erlöse 10% USt",                               "ertrag",  "U10", "Erlöse mit 10% Umsatzsteuer"),
    ("4040", "Erlöse steuerbefreit",                         "ertrag",  "U00", "Steuerfreie Erlöse (§ 6 UStG)"),
    ("4050", "Erlöse innergemeinschaftlich (IG)",             "ertrag",  "UIG", "Innergemeinschaftliche Lieferungen"),
    ("4060", "Erlöse Reverse Charge",                        "ertrag",  "URC", "Reverse Charge Leistungen"),
    # Aufwendungen (für spätere Erweiterung)
    ("5000", "Wareneinsatz / Materialaufwand",                "aufwand", None,  ""),
    ("6000", "Personalaufwand",                              "aufwand", None,  "Löhne und Gehälter"),
    ("6800", "Sonstige betriebliche Aufwendungen",           "aufwand", None,  ""),
    ("7200", "Miete und Pacht",                              "aufwand", None,  ""),
    ("7800", "Zinsen und ähnliche Aufwendungen",             "aufwand", None,  ""),
    ("9000", "Eröffnungsbilanzkonto",                        "neutral", None,  ""),
    ("9800", "Gewinn- und Verlustkonto",                     "neutral", None,  ""),
    ("9850", "Privatkonto",                                  "neutral", None,  "Entnahmen / Einlagen"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # 1. Kontakte: Debitornummer + Kreditornummer im Finanz-Tab
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             show_in_list, sort_order, placeholder, tab)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.fname, fd.fkey, 'text',
            false, false,
            fd.fsort::integer,
            fd.fplaceholder,
            'Finanz'
        FROM entity_types et,
        (VALUES
            ('Debitornummer',  'debitornummer',  '23', 'z.B. 10001'),
            ('Kreditornummer', 'kreditornummer', '24', 'z.B. 70001')
        ) AS fd(fname, fkey, fsort, fplaceholder)
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd2
              WHERE fd2.entity_type_id = et.id AND fd2.key = fd.fkey
          )
    """))

    # -------------------------------------------------------------------------
    # 2. Kontenplan-Tabelle
    # -------------------------------------------------------------------------
    op.create_table(
        'accounting_accounts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('nr', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('typ', sa.String(20), nullable=False),   # aktiv|passiv|ertrag|aufwand|neutral
        sa.Column('ust_code', sa.String(10), nullable=True),  # U20|U10|U00|UIG|URC
        sa.Column('beschreibung', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_default_erloes', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_accounting_accounts_nr', 'accounting_accounts', ['nr'])
    op.create_index('ix_accounting_accounts_typ', 'accounting_accounts', ['typ'])

    # EKR-Seed (nur wenn Tabelle noch leer)
    for nr, name, typ, ust_code, beschreibung in EKR_ACCOUNTS:
        ust_val = f"'{ust_code}'" if ust_code else "NULL"
        default_erloes = 'true' if nr == '4000' else 'false'
        conn.execute(sa.text(f"""
            INSERT INTO accounting_accounts (nr, name, typ, ust_code, beschreibung, is_default_erloes)
            VALUES ('{nr}', '{name}', '{typ}', {ust_val}, '{beschreibung}', {default_erloes})
            ON CONFLICT (nr) DO NOTHING
        """))

    # -------------------------------------------------------------------------
    # 3. Artikel: Erlöskonto-Spalte
    # -------------------------------------------------------------------------
    # entity_records hat kein festes Schema — Konto wird im JSONB-Feld 'data'
    # unter dem Key 'erloes_konto' gespeichert. Kein ALTER TABLE nötig.
    # (Wird als reguläres Stammdaten-Feld angelegt)

    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             show_in_list, sort_order, placeholder)
        SELECT
            gen_random_uuid(),
            et.id,
            'Erlöskonto', 'erloes_konto', 'text',
            false, false, 5,
            'z.B. 4000'
        FROM entity_types et
        WHERE et.slug = 'artikel'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd2
              WHERE fd2.entity_type_id = et.id AND fd2.key = 'erloes_konto'
          )
    """))

    # -------------------------------------------------------------------------
    # 4. invoice_positions: account_nr-Spalte
    # -------------------------------------------------------------------------
    op.add_column('invoice_positions',
        sa.Column('account_nr', sa.String(20), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_column('invoice_positions', 'account_nr')
    op.drop_table('accounting_accounts')
    conn.execute(sa.text("""
        DELETE FROM field_definitions
        WHERE key IN ('debitornummer', 'kreditornummer', 'erloes_konto')
    """))
