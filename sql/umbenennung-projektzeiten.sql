-- Benennt den Stammdaten-Typ "Projekte" in "Projektzeiten" um (Name + Slug).
-- Reine Datenänderung, nicht Teil einer Alembic-Migration.
--
-- Ausführen (auf dem Server, im Projektverzeichnis):
--   docker compose exec -T db psql -U deinezeit -f /opt/deinezeit/sql/umbenennung-projektzeiten.sql
--
-- Erwartete Ausgabe: UPDATE 1
--
-- Hinweis: Bestehende Zeiteinträge bleiben unberührt, da sie die Projekt-ID
-- (nicht den Slug) speichern. Der Frontend-Code referenziert bereits den
-- neuen Slug "projektzeiten".

UPDATE entity_types
SET name = 'Projektzeiten',
    slug = 'projektzeiten'
WHERE slug = 'projekte';

-- Kontrolle:
-- SELECT name, slug FROM entity_types WHERE slug = 'projektzeiten';
