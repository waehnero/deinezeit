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

def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def get_current_version() -> str:
    with open("frontend/package.json", encoding="utf-8") as f:
        return json.load(f)["version"]


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def get_commits_since_last_bump() -> list[dict]:
    """Alle Commits seit dem letzten 'chore: Version'-Commit."""
    log = run(["git", "log", "--format=%H\t%s\t%b", "HEAD"])
    commits = []
    for line in log.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        hash_ = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""

        if subject.startswith("chore: Version"):
            break  # Ab hier ist alles bereits versioniert
        commits.append({"hash": hash_, "subject": subject, "body": body})
    return commits


def determine_bump_type(commits: list[dict]) -> str:
    subjects = [c["subject"] for c in commits]
    if any("BREAKING" in s for s in subjects):
        return "major"
    if any(s.startswith("feat:") for s in subjects):
        return "minor"
    return "patch"


def categorize_commits(commits: list[dict]) -> tuple[list[str], list[str]]:
    """Gibt (features, updates) zurück — direkt aus Commit-Messages."""
    features, updates = [], []
    for c in commits:
        s = c["subject"]
        if s.startswith("feat:"):
            features.append(s[5:].strip())
        elif s.startswith("fix:") or s.startswith("refactor:") or s.startswith("perf:"):
            updates.append(re.sub(r"^[a-z]+:\s*", "", s).strip())
    return features, updates


def improve_with_claude(
    commits: list[dict], new_version: str
) -> tuple[str, list[str], list[str]]:
    """
    Nutzt die Claude API um aus Commit-Messages saubere Changelog-Einträge
    und einen passenden Versions-Titel zu generieren.
    Gibt (titel, features, updates) zurück.
    """
    import requests

    api_key = os.environ["ANTHROPIC_API_KEY"]
    commit_text = "\n".join(
        f"- {c['subject']}" + (f"\n  {c['body']}" if c["body"].strip() else "")
        for c in commits
    )

    prompt = f"""Du bist ein technischer Redakteur für ein deutschsprachiges Software-Produkt namens "DeineZeit" (eine Business-App für Zeiterfassung, Stammdaten, Rechnungen und Buchhaltung).

Hier sind die Git-Commit-Messages seit dem letzten Release (Version {new_version}):

{commit_text}

Erstelle daraus:
1. Einen kurzen deutschen Versions-Titel (2–5 Wörter, beschreibt das Hauptthema)
2. Eine Liste neuer Features (aus "feat:"-Commits) — jedes als prägnanter deutscher Satz
3. Eine Liste von Verbesserungen/Bugfixes (aus "fix:", "refactor:", "perf:"-Commits) — jedes als prägnanter deutscher Satz

Antworte ausschließlich als gültiges JSON in diesem Format:
{{
  "titel": "...",
  "features": ["...", "..."],
  "updates": ["...", "..."]
}}

Regeln:
- Keine Markdown-Formatierung
- Nur JSON, kein Text davor oder danach
- Technische Details weglassen, Nutzen hervorheben
- Leere Arrays wenn keine Einträge vorhanden
"""

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
        print(f"  Claude API Fehler ({response.status_code}) — verwende Commit-Messages direkt")
        return None, None, None

    raw = response.json()["content"][0]["text"].strip()
    data = json.loads(raw)
    return data.get("titel", ""), data.get("features", []), data.get("updates", [])


# ─── Dateien aktualisieren ────────────────────────────────────────────────────

def update_package_json(version: str):
    path = "frontend/package.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
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
    with open(path, "w", encoding="utf-8") as f:
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
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ {path}")


def update_changelog_js(version: str, features: list[str], updates: list[str]):
    path = "frontend/src/data/changelog.js"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    today = datetime.now()
    months = ["Januar","Februar","März","April","Mai","Juni",
              "Juli","August","September","Oktober","November","Dezember"]

    def js_list(items):
        if not items:
            return ""
        return "\n" + "\n".join(f"      '{i.replace(chr(39), chr(92)+chr(39))}',\n" for i in items)

    new_entry = f"""  {{
    version: '{version}',
    day: '{today.day:02d}',
    month: '{months[today.month - 1]}',
    year: '{today.year}',
    features: [{js_list(features)}    ],
    updates: [{js_list(updates)}    ],
  }},
"""

    content = re.sub(
        r"(export const changelog = \[\n)",
        r"\g<1>" + new_entry,
        content,
        count=1,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ {path}")


def update_changelog_md(version: str, titel: str, features: list[str], updates: list[str]):
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
    idx = content.index(insert_marker) + len(insert_marker)
    content = content[:idx] + new_entry + content[idx:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ {path}")


def git_commit(version: str, titel: str):
    files = [
        "frontend/package.json",
        "backend/app/core/config.py",
        "docker-compose.yml",
        "docker-compose.local.yml",
        "frontend/src/data/changelog.js",
        "CHANGELOG.md",
    ]
    run(["git", "add"] + files)
    run(["git", "commit", "-m", f"chore: Version {version} — {titel}"])
    print(f"  ✓ git commit: chore: Version {version} — {titel}")


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
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
    print(f"  Bump-Typ: {bump}  ({current} → {new_version})\n")

    # 3. Changelog-Inhalt generieren
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    titel, features, updates = None, None, None

    if api_key:
        print("  Claude API verfügbar — generiere Beschreibungen …")
        titel, features, updates = improve_with_claude(commits, new_version)

    if not titel:  # Fallback: direkt aus Commit-Messages
        print("  Verwende Commit-Messages direkt …")
        features, updates = categorize_commits(commits)
        # Titel = erste feat-Message oder erste Commit-Message (gekürzt)
        feat_commits = [c["subject"][5:].strip() for c in commits if c["subject"].startswith("feat:")]
        titel = feat_commits[0] if feat_commits else re.sub(r"^[a-z]+:\s*", "", commits[0]["subject"]).strip()

    print(f"  Titel: {titel}")
    if features:
        print(f"  Features ({len(features)}): {', '.join(features[:2])}{'…' if len(features) > 2 else ''}")
    if updates:
        print(f"  Updates ({len(updates)}): {', '.join(updates[:2])}{'…' if len(updates) > 2 else ''}")
    print()

    # 4. Alle Dateien aktualisieren
    print("  Dateien aktualisieren:")
    update_package_json(new_version)
    update_config_py(new_version)
    update_docker_compose("docker-compose.yml", new_version)
    update_docker_compose("docker-compose.local.yml", new_version)
    update_changelog_js(new_version, features, updates)
    update_changelog_md(new_version, titel, features, updates)

    # 5. Git-Commit erstellen
    print("\n  Git-Commit erstellen:")
    git_commit(new_version, titel)

    print(f"\n  ✓ Version {new_version} erfolgreich erstellt.\n")


if __name__ == "__main__":
    main()
