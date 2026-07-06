#!/usr/bin/env python3
"""
bump_version.py – Hebt die Patch-Version in allen 6 Versions-Dateien an und
fügt einen Changelog-Eintrag hinzu. Wird vom pre-commit-Hook automatisch auf
Feature-Branches aufgerufen (einmal pro Branch), kann aber auch manuell mit
eigenem Titel laufen.

Aktualisierte Dateien (Formate wie auto_version.py):
  1. frontend/package.json
  2. backend/app/core/config.py
  3. docker-compose.yml
  4. docker-compose.local.yml
  5. frontend/src/data/changelog.js
  6. CHANGELOG.md

WICHTIG: Dieses Skript committet und pusht NICHT. Es ändert nur die Dateien.
Der pre-commit-Hook nimmt die Änderungen anschließend mit `git add` in den
laufenden Commit auf.

Nutzung:
  python3 scripts/bump_version.py                    # Titel aus Branch-Name
  python3 scripts/bump_version.py --title "Neues X"   # eigener Titel
  python3 scripts/bump_version.py --title "X" --update "Fix A" --update "Fix B"
  python3 scripts/bump_version.py --set 1.13.0        # exakte Zielversion
"""
import argparse
import json
import os
import re
import subprocess
import sys

# Verzeichnis dieses Skripts, damit die Update-Funktionen aus auto_version.py
# importiert werden können (gleiche Changelog-/Datei-Formate, keine Duplikate).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# auto_version.py importiert `requests` nur INNERHALB einer Funktion, daher ist
# der Import der reinen Update-Funktionen hier gefahrlos (nur stdlib nötig).
from auto_version import (  # noqa: E402
    update_package_json,
    update_config_py,
    update_docker_compose,
    update_changelog_js,
    update_changelog_md,
)


def repo_root() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    return out.stdout.strip() or os.getcwd()


def current_version() -> str:
    with open("frontend/package.json", encoding="utf-8") as f:
        return json.load(f)["version"]


def next_patch(version: str) -> str:
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{major}.{minor}.{patch + 1}"


def branch_name() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def title_from_branch(branch: str) -> str:
    """feature/aufgaben-outlook-flag -> 'Aufgaben outlook flag'"""
    name = re.sub(r"^(feature|fix|chore|docs|refactor|test)/", "", branch)
    name = name.replace("-", " ").replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else "Weiterentwicklung"


def main() -> int:
    parser = argparse.ArgumentParser(description="Version anheben (ohne Commit).")
    parser.add_argument("--title", help="Titel für den Changelog-Eintrag")
    parser.add_argument("--update", action="append", default=[],
                        help="Aktualisierungs-Eintrag (mehrfach möglich)")
    parser.add_argument("--feature", action="append", default=[],
                        help="Neu-Feature-Eintrag (mehrfach möglich)")
    parser.add_argument("--set", dest="exact",
                        help="Exakte Zielversion statt Patch+1 (z.B. 1.13.0)")
    args = parser.parse_args()

    os.chdir(repo_root())

    old = current_version()
    new = args.exact if args.exact else next_patch(old)

    branch = branch_name()
    titel = args.title or title_from_branch(branch)
    # Ohne explizite Einträge: den Titel als eine Aktualisierung eintragen,
    # damit die Timeline auf der Anmeldeseite einen sichtbaren Punkt bekommt.
    updates = args.update or ([titel] if not args.feature else [])
    features = args.feature

    print(f"  Version: {old} -> {new}   (Titel: {titel})")
    update_package_json(new)
    update_config_py(new)
    update_docker_compose("docker-compose.yml", new)
    update_docker_compose("docker-compose.local.yml", new)
    update_changelog_js(new, features, updates)
    update_changelog_md(new, titel, features, updates)
    print(f"  ✓ Version {new} in allen Dateien gesetzt (noch nicht committet).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
