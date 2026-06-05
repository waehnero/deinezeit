#!/usr/bin/env python3
"""
auto_version.py
===============
Analysiert alle Commits seit dem letzten Versions-Bump, bestimmt den
nächsten Versions-Typ und aktualisiert alle 6 Versions-Dateien im Projekt.

Optionale Umgebungsvariable:
  ANTHROPIC_API_KEY  — wenn gesetzt, werden Commit-Messages via Claude API
                       in saubere Changelog-Einträge umgewandelt.

Dateien die aktualisiert werden:
  1. frontend/package.json
  2. backend/app/core/config.py
  3. docker-compose.yml
  4. docker-compose.local.yml
  5. frontend/src/data/changelog.js
  6. CHANGELOG.md
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def run(cmd: list, check: bool = False) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        print(f"  FEHLER bei: {' '.join(cmd)}")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def get_current_version() -> str:
    """Liest die aktuelle Version aus CHANGELOG.md (immer im Repo vorhanden)."""
    with open("CHANGELOG.md", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^## \[(\d+\.\d+\.\d+)\]', line)
            if m:
                return m.group(1)
    return "0.0.0"


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def get_commits_since_last_bump() -> list:
    """
    Alle Commits seit dem letzten 'chore: Version'-Commit.
    SHA-1 Hashes sind immer exakt 40 Zeichen — daher sicheres Splitting bei Position 40.
    """
    log = run(["git", "log", "--format=%H %s", "HEAD"], check=True)
    commits = []
    for line in log.splitlines():
        line = line.strip()
        if len(line) < 42:  # 40 (Hash) + 1 (Leerzeichen) + 1 (min. Subject)
            continue
        hash_ = line[:40]
        subject = line[41:].strip()
        if subject.startswith("chore: Version"):
            break  # Ab hier ist alles bereits versioniert
        commits.append({"hash": hash_, "subject": subject})
    return commits


def determine_bump_type(commits: list) -> str:
    subjects = [c["subject"] for c in commits]
    if any("BREAKING" in s for s in subjects):
        return "major"
    if any(s.startswith("feat:") for s in subjects):
        return "minor"
    return "patch"


def categorize_commits(commits: list) -> tuple:
    """Gibt (features, updates) zurück — direkt aus Commit-Messages."""
    features, updates = [], []
    for c in commits:
        s = c["subject"]
        if s.startswith("feat:"):
            features.append(s[5:].strip())
        elif s.startswith(("fix:", "refactor:", "perf:")):
            updates.append(re.sub(r"^[a-z]+:\s*", "", s).strip())
    return features, updates


def improve_with_claude(commits: list, new_version: str) -> tuple:
    """
    Nutzt die Claude API um aus Commit-Messages saubere Changelog-Einträge
    und einen passenden Versions-Titel zu generieren.
    Gibt (titel, features, updates) zurück oder (None, None, None) bei Fehler.
    """
    try:
        import requests
    except ImportError:
        return None, None, None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, None, None

    commit_text = "\n".join(f"- {c['subject']}" for c in commits)

    prompt = (
        'Du bist ein technischer Redakteur für ein deutschsprachiges Software-Produkt namens "DeineZeit" '
        "(eine Business-App für Zeiterfassung, Stammdaten, Rechnungen und Buchhaltung).\n\n"
        f"Hier sind die Git-Commit-Messages seit dem letzten Release (neue Version wird {new_version}):\n\n"
        f"{commit_text}\n\n"
        "Erstelle daraus:\n"
        "1. Einen kurzen deutschen Versions-Titel (2-5 Woerter, beschreibt das Hauptthema)\n"
        '2. Eine Liste neuer Features (aus "feat:"-Commits) - jedes als praegnanter deutscher Satz\n'
        '3. Eine Liste von Verbesserungen/Bugfixes (aus "fix:", "refactor:", "perf:"-Commits) - jedes als praegnanter deutscher Satz\n\n'
        "Antworte ausschliesslich als gueltiges JSON:\n"
        '{"titel": "...", "features": ["...", "..."], "updates": ["...", "..."]}\n\n'
        "Nur JSON, kein Text davor oder danach. Leere Arrays wenn keine Eintraege vorhanden."
    )

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"  Claude API Fehler ({response.status_code}) — Fallback auf Commit-Messages")
            return None, None, None

        raw = response.json()["content"][0]["text"].strip()
        # JSON-Block aus der Antwort extrahieren (falls doch etwas drumherum ist)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return None, None, None
        data = json.loads(json_match.group())
        return data.get("titel", ""), data.get("features", []), data.get("updates", [])

    except Exception as e:
        print(f"  Claude API Ausnahme: {e} — Fallback auf Commit-Messages")
        return None, None, None


# ─── Dateien aktualisieren ────────────────────────────────────────────────────

def update_package_json(version: str):
    path = "frontend/package.json"
    if not os.path.exists(path):
        print(f"  ⚠ {path} nicht im Repo — übersprungen")
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = version
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  ✓ {path}")


def update_config_py(version: str):
    path = "backend/app/core/config.py"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'(APP_VERSION:\s*str\s*=\s*")[^"]+(")',
        rf"\g<1>{version}\g<2>",
        content,
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  ✓ {path}")


def update_docker_compose(path: str, version: str):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r"(APP_VERSION: \$\{APP_VERSION:-)[^}]+(})",
        rf"\g<1>{version}\g<2>",
        content,
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  ✓ {path}")


def update_changelog_js(version: str, features: list, updates: list):
    path = "frontend/src/data/changelog.js"
    if not os.path.exists(path):
        print(f"  ⚠ {path} nicht im Repo — übersprungen")
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()

    today = datetime.now()
    months = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]
    # Echte Umlaute für den Output
    month_display = ["Januar", "Februar", "März", "April", "Mai", "Juni",
                     "Juli", "August", "September", "Oktober", "November", "Dezember"]

    def escape_js(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def js_array(items: list) -> str:
        if not items:
            return "[]"
        lines = "\n" + "".join(f"      '{escape_js(i)}',\n" for i in items) + "    "
        return f"[{lines}]"

    new_entry = (
        "  {\n"
        f"    version: '{version}',\n"
        f"    day: '{today.day:02d}',\n"
        f"    month: '{month_display[today.month - 1]}',\n"
        f"    year: '{today.year}',\n"
        f"    features: {js_array(features)},\n"
        f"    updates: {js_array(updates)},\n"
        "  },\n"
    )

    # Flexibel: findet "export const changelog = [" unabhängig von Zeilenenden
    content = re.sub(
        r"(export const changelog\s*=\s*\[)\s*\n",
        lambda m: m.group(0) + new_entry,
        content,
        count=1,
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  ✓ {path}")


def update_changelog_md(version: str, titel: str, features: list, updates: list):
    path = "CHANGELOG.md"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")

    neu_section = ""
    if features:
        neu_section = "\n\n### Neu\n" + "\n".join(f"- {f}" for f in features)

    akt_section = ""
    if updates:
        akt_section = "\n\n### Aktualisierungen\n" + "\n".join(f"- {u}" for u in updates)

    new_entry = f"\n## [{version}] – {today} – {titel}{neu_section}{akt_section}\n\n---\n"

    # Nach dem ersten "---" einfügen
    insert_marker = "---\n"
    idx = content.find(insert_marker)
    if idx == -1:
        # Fallback: einfach nach der ersten Zeile einfügen
        idx = content.find("\n") + 1
    else:
        idx += len(insert_marker)
    content = content[:idx] + new_entry + content[idx:]

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  ✓ {path}")


def git_commit(version: str, titel: str):
    candidates = [
        "frontend/package.json",
        "backend/app/core/config.py",
        "docker-compose.yml",
        "docker-compose.local.yml",
        "frontend/src/data/changelog.js",
        "CHANGELOG.md",
    ]
    files = [f for f in candidates if os.path.exists(f)]
    run(["git", "add"] + files, check=True)
    result = subprocess.run(
        ["git", "commit", "-m", f"chore: Version {version} — {titel}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # Kein Fehler wenn nichts zu committen (already up to date)
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            print("  ℹ Keine Änderungen zu committen.")
        else:
            print(f"  FEHLER beim Commit: {result.stderr}")
            sys.exit(1)
    else:
        print(f"  ✓ git commit: chore: Version {version} — {titel}")


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    # Immer vom Repo-Root aus arbeiten (scripts/ ist eine Ebene tiefer)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)
    print(f"  Arbeitsverzeichnis: {repo_root}")

    print("\n══════════════════════════════════════════")
    print("  DeineZeit  —  Auto-Version")
    print("══════════════════════════════════════════\n")

    # 1. Commits sammeln
    commits = get_commits_since_last_bump()
    if not commits:
        print("  Keine neuen Commits seit dem letzten Versions-Bump. Abbruch.")
        sys.exit(0)

    print(f"  {len(commits)} neue Commit(s) gefunden:")
    for c in commits:
        print(f"    • {c['subject']}")
    print()

    # 2. Bump-Typ und neue Version ermitteln
    bump = determine_bump_type(commits)
    current = get_current_version()
    new_version = bump_version(current, bump)
    print(f"  Bump-Typ: {bump}  ({current} -> {new_version})\n")

    # 3. Changelog-Inhalt generieren
    titel, features, updates = improve_with_claude(commits, new_version)

    if not titel:  # Fallback: direkt aus Commit-Messages
        print("  Generiere Changelog aus Commit-Messages …")
        features, updates = categorize_commits(commits)
        feat_subjects = [c["subject"][5:].strip() for c in commits if c["subject"].startswith("feat:")]
        titel = feat_subjects[0] if feat_subjects else re.sub(r"^[a-z]+:\s*", "", commits[0]["subject"]).strip()
    else:
        print("  Claude API: Beschreibungen generiert")

    print(f"  Titel:    {titel}")
    print(f"  Features: {len(features)}")
    print(f"  Updates:  {len(updates)}")
    print()

    # 4. Alle Dateien aktualisieren
    print("  Dateien aktualisieren:")
    update_package_json(new_version)
    update_config_py(new_version)
    update_docker_compose("docker-compose.yml", new_version)
    update_docker_compose("docker-compose.local.yml", new_version)
    update_changelog_js(new_version, features or [], updates or [])
    update_changelog_md(new_version, titel, features or [], updates or [])

    # 5. Git-Commit erstellen
    print("\n  Git-Commit erstellen:")
    git_commit(new_version, titel)

    print(f"\n  Version {new_version} erfolgreich erstellt.\n")


if __name__ == "__main__":
    main()
