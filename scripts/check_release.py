"""Inspect a portable release folder without displaying any credential values."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from unified_scheduler.google_oauth import read_google_client_config
from unified_scheduler.providers.errors import ProviderError

CLIENT_RESOURCE = Path("_internal/unified_scheduler/resources/google-oauth-client.json")


def inspect_distribution(root: Path) -> list[str]:
    failures = []
    for required in ("UnifiedScheduler.exe", "LICENSE", "READ-ME.txt", "build-info.json",
                     "_internal/assets/unified_scheduler_simple.ico"):
        if not (root / required).is_file():
            failures.append(f"Missing distribution file: {required}")
    for path in root.rglob("*"):
        if path.is_symlink():
            failures.append(f"Unexpected symbolic link: {path.relative_to(root).as_posix()}")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = path.name.lower()
        if (any(part.lower() in {"local-config", ".git", ".venv", "secrets"} for part in relative.parts)
                or re.search(r"\.(?:sqlite3?|db)(?:-(?:wal|shm|journal))?$", name)
                or name.endswith((".ics", ".p12", ".pfx", ".key"))
                or name == ".env" or name.startswith(".env.")
                or re.fullmatch(r"(?:token.*|credentials|client_secret.*|oauth_client.*)\.json", name)):
            failures.append(f"Unexpected private/development file: {relative.as_posix()}")
        if name == "google-oauth-client.json":
            if relative != CLIENT_RESOURCE:
                failures.append(f"OAuth client is outside its designated resource: {relative.as_posix()}")
                continue
            try:
                normalized = read_google_client_config(path)
                if json.loads(path.read_text(encoding="utf-8-sig")) != normalized:
                    failures.append("OAuth client contains fields outside the normalized Desktop configuration.")
            except (ProviderError, OSError, ValueError):
                failures.append("Bundled Desktop OAuth client is invalid.")
    try:
        manifest = json.loads((root / "build-info.json").read_text(encoding="utf-8-sig"))
        included = (root / CLIENT_RESOURCE).is_file()
        if manifest.get("google_client_included") is not included:
            failures.append("Build manifest does not match the bundled Google client.")
    except (OSError, ValueError, AttributeError):
        failures.append("Build manifest is missing or invalid.")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    failures = inspect_distribution(args.directory)
    for failure in failures:
        print(failure)
    if failures:
        return 1
    print("Distribution structure and OAuth resource checks passed; manually review release contents too.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
