"""Anmeldung härten: widerrufbare Sitzungen, Kontosperre, Prüfpfad

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-17

Erste Etappe der Sicherheits-Überarbeitung. Sie schafft die Grundlagen, die
dem Anmeldeprozess bisher fehlten:

1. **Sitzungen werden widerrufbar.** ``user_sessions`` wurde beim Anmelden
   beschrieben, aber nie gelesen — es gab weder ``/auth/refresh`` noch
   ``/auth/logout``. Ein ausgestellter Refresh-Token war damit sieben Tage
   lang unwiderruflich gültig, auch nach einem Passwortwechsel oder wenn ein
   Gerät verloren ging. Neu: ``revoked_at``/``revoked_reason``,
   ``last_used_at`` für die Übersicht „Hier bist du angemeldet",
   ``replaced_by_id`` für die Token-Rotation und ein Index auf
   ``refresh_token_hash`` (der Wert wird künftig bei jedem Erneuern
   nachgeschlagen — ohne Index wäre das ein Full-Scan auf einer Tabelle, die
   mit jeder Anmeldung wächst).

2. **Kontosperre bei Fehlversuchen.** Bisher schützte nur ein Rate-Limit von
   10 Anfragen pro Minute *pro IP-Adresse*. Wer über mehrere Adressen
   verteilt, konnte beliebig weiterprobieren, und niemand hätte es gemerkt.
   Neu in ``users``: ``failed_login_count``, ``locked_until``,
   ``last_login_at``, ``password_changed_at``.

3. **Prüfpfad ``auth_events``.** Wer sich wann von wo angemeldet hat und
   welche Versuche scheiterten, war nirgends nachvollziehbar. Eine
   Kontoübernahme wäre unbemerkt und im Nachhinein unbelegbar geblieben.

4. **WebAuthn-Challenges in der Datenbank.** Sie lagen in einem Dict im
   Prozessspeicher — das funktioniert nur mit genau einem Worker und
   überlebt keinen Neustart. Mit mehreren Workern scheitert die
   Passkey-Anmeldung sporadisch mit „Challenge abgelaufen", obwohl nichts
   abgelaufen ist.

5. **Einmal-Codes für 2FA** (``totp_recovery_codes``). Ohne sie sperrt der
   Verlust des Authenticator-Geräts den Benutzer endgültig aus.

6. **Token für „Passwort vergessen"** (``password_reset_tokens``). Die Seite
   ``ForgotPasswordPage.jsx`` existierte im Frontend, im Backend fehlte der
   zugehörige Endpunkt vollständig — sie lief ins Leere.

7. **``users.totp_secret`` wird verschlüsselt** (siehe ``core/crypto.py``).
   Deshalb ``String(64)`` → ``Text``: ein Fernet-Token ist länger als das
   Base32-Secret. Der Backfill unten verschlüsselt Bestandswerte. Er ist
   absichtlich fehlertolerant — schlägt er fehl, bleiben die Werte im
   Klartext lesbar und funktionsfähig, und eine misslungene Verschlüsselung
   hindert niemanden am Anmelden.

Rückbau (``downgrade``) verwirft die Prüfpfad-Einträge und die Einmal-Codes.
Das ist unvermeidlich, weil es die Tabellen vorher nicht gab. Die
Verschlüsselung des TOTP-Secrets wird beim Rückbau **nicht** rückgängig
gemacht: die Spalte wird nur wieder gekürzt, und ein Fernet-Token passt nicht
in 64 Zeichen. Wer wirklich zurück muss, deaktiviert vorher 2FA für die
betroffenen Benutzer — deshalb steht dort eine sprechende Fehlermeldung
statt eines abgeschnittenen Werts.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. users: Anmeldeschutz ───────────────────────────────────────────────
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(),
                                     nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until',
                                     sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_login_at',
                                     sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_changed_at',
                                     sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('totp_secret_pending', sa.Text(),
                                     nullable=True))
    op.add_column('users', sa.Column('totp_pending_at',
                                     sa.DateTime(timezone=True), nullable=True))

    # totp_secret: String(64) → Text, damit das Fernet-Token hineinpasst.
    op.alter_column('users', 'totp_secret',
                    existing_type=sa.String(length=64),
                    type_=sa.Text(), existing_nullable=True)

    # ── 2. user_sessions: widerrufbar machen ──────────────────────────────────
    op.add_column('user_sessions', sa.Column('last_used_at',
                                             sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_sessions', sa.Column('revoked_at',
                                             sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_sessions', sa.Column('revoked_reason',
                                             sa.String(length=30), nullable=True))
    op.add_column('user_sessions', sa.Column('replaced_by_id',
                                             postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('user_sessions', sa.Column('device_label',
                                             sa.String(length=100), nullable=True))
    op.create_foreign_key('fk_user_sessions_replaced_by', 'user_sessions',
                          'user_sessions', ['replaced_by_id'], ['id'],
                          ondelete='SET NULL')
    op.create_index('ix_user_sessions_refresh_token_hash', 'user_sessions',
                    ['refresh_token_hash'])
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])

    # Bestandssitzungen: Es gab bis hierher keinen Weg, einen Refresh-Token
    # einzulösen — das Frontend hat ihn gespeichert und nie verwendet. Die
    # vorhandenen Zeilen sind also durchweg toter Ballast. Sie werden entwertet,
    # damit sie nicht plötzlich gültige, nie überprüfte Sitzungen darstellen,
    # sobald /auth/refresh existiert.
    op.execute("""
        UPDATE user_sessions
           SET revoked_at = NOW(), revoked_reason = 'migration'
         WHERE revoked_at IS NULL
    """)

    # ── 3. Prüfpfad ───────────────────────────────────────────────────────────
    op.create_table(
        'auth_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('event', sa.String(length=40), nullable=False),
        sa.Column('email_attempted', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('detail', sa.String(length=200), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_auth_events_user_created', 'auth_events',
                    ['user_id', 'created_at'])
    op.create_index('ix_auth_events_event_created', 'auth_events',
                    ['event', 'created_at'])

    # ── 4. WebAuthn-Challenges ────────────────────────────────────────────────
    op.create_table(
        'webauthn_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('scope', sa.String(length=320), nullable=False, unique=True),
        sa.Column('challenge', sa.LargeBinary(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_webauthn_challenges_scope', 'webauthn_challenges',
                    ['scope'], unique=True)

    # ── 5. Einmal-Codes für 2FA ───────────────────────────────────────────────
    op.create_table(
        'totp_recovery_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_totp_recovery_codes_user_id', 'totp_recovery_codes',
                    ['user_id'])

    # ── 6. Passwort-Zurücksetzung ─────────────────────────────────────────────
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_password_reset_tokens_token_hash',
                    'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index('ix_password_reset_tokens_user_id',
                    'password_reset_tokens', ['user_id'])

    # ── 7. Bestehende TOTP-Secrets verschlüsseln ──────────────────────────────
    # Fehlertolerant: Ohne SECRET_KEY oder cryptography-Bibliothek bleiben die
    # Werte im Klartext. Das ist der Zustand von vorher, also kein Rückschritt,
    # und core/crypto.entschluesseln() liest Klartext weiterhin. Ein Abbruch
    # der Migration wäre hier der schlechtere Ausgang: Der Server käme nicht
    # hoch, weil entrypoint.sh vor dem Start `alembic upgrade head` ausführt.
    try:
        from app.core.crypto import verschluesseln, ist_verschluesselt

        bind = op.get_bind()
        zeilen = bind.execute(sa.text(
            "SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL"
        )).fetchall()
        anzahl = 0
        for zeile in zeilen:
            if ist_verschluesselt(zeile.totp_secret):
                continue
            bind.execute(
                sa.text("UPDATE users SET totp_secret = :s WHERE id = :i"),
                {"s": verschluesseln(zeile.totp_secret), "i": zeile.id},
            )
            anzahl += 1
        if anzahl:
            print(f"[0054] {anzahl} TOTP-Secret(s) verschlüsselt.")
    except Exception as e:                                   # noqa: BLE001
        print("[0054] TOTP-Secrets bleiben unverschlüsselt "
              f"({type(e).__name__}: {e}). Sie werden beim nächsten Speichern "
              "der 2FA-Einstellungen automatisch verschlüsselt.")


def downgrade():
    op.drop_index('ix_password_reset_tokens_user_id',
                  table_name='password_reset_tokens')
    op.drop_index('ix_password_reset_tokens_token_hash',
                  table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')

    op.drop_index('ix_totp_recovery_codes_user_id',
                  table_name='totp_recovery_codes')
    op.drop_table('totp_recovery_codes')

    op.drop_index('ix_webauthn_challenges_scope',
                  table_name='webauthn_challenges')
    op.drop_table('webauthn_challenges')

    op.drop_index('ix_auth_events_event_created', table_name='auth_events')
    op.drop_index('ix_auth_events_user_created', table_name='auth_events')
    op.drop_table('auth_events')

    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_index('ix_user_sessions_refresh_token_hash',
                  table_name='user_sessions')
    op.drop_constraint('fk_user_sessions_replaced_by', 'user_sessions',
                       type_='foreignkey')
    op.drop_column('user_sessions', 'device_label')
    op.drop_column('user_sessions', 'replaced_by_id')
    op.drop_column('user_sessions', 'revoked_reason')
    op.drop_column('user_sessions', 'revoked_at')
    op.drop_column('user_sessions', 'last_used_at')

    # Verschlüsselte Secrets passen nicht zurück in String(64). Lieber ein
    # klarer Abbruch als ein abgeschnittenes Secret, das aussieht wie ein
    # funktionierender zweiter Faktor, aber keiner mehr ist.
    bind = op.get_bind()
    zu_lang = bind.execute(sa.text(
        "SELECT COUNT(*) FROM users "
        " WHERE totp_secret IS NOT NULL AND LENGTH(totp_secret) > 64"
    )).scalar()
    if zu_lang:
        raise RuntimeError(
            f"Rückbau abgebrochen: {zu_lang} Benutzer haben ein verschlüsseltes "
            "TOTP-Secret, das nicht in die alte Spalte passt. Bitte vorher für "
            "diese Benutzer 2FA deaktivieren (Benutzerverwaltung) und den "
            "Rückbau erneut starten."
        )
    op.alter_column('users', 'totp_secret',
                    existing_type=sa.Text(),
                    type_=sa.String(length=64), existing_nullable=True)

    op.drop_column('users', 'totp_pending_at')
    op.drop_column('users', 'totp_secret_pending')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_count')
