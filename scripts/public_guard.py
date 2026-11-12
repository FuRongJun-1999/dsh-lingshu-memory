"""Public text hygiene checks; not a proof of perfect secret detection."""
from __future__ import annotations
import pathlib
import re
ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".venv", ".pytest_cache", "artifacts", ".private"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".txt"}
# Patterns live in code; files are never printed when they contain a match.
POLICY_DENY = [("private_key", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
               ("github_token", r"(?:gh[pousr]_)[A-Za-z0-9]{30,}"),
               ("long_api_token", r"\bsk-[A-Za-z0-9]{24,}"),
               ("session_dump", r"(?m)^\s*<session-transcript>")]
PRIVACY_DENY = [("private_drive", r"[A-Za-z]:[\\/](?:Users|program|dsh-home|代码评审)[\\/]"),
                ("private_unix_home", r"/(?:home|Users)/[^/\s]+/"),
                ("secret_assignment", r'''(?i)(?:api_key|access_token|password)\s*[:=]\s*["'][A-Za-z0-9_-]{16,}["']''')]

def public_files():
    return sorted(p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP))

def main():
    errors = []
    files = public_files()
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix not in TEXT_SUFFIXES and p.name not in {"LICENSE", ".gitignore", ".gitattributes"}:
            errors.append((rel, "unapproved_file_type"))
            continue
        text = p.read_text(encoding="utf-8")
        if any(ord(c) < 32 and ord(c) not in (9, 10, 13) for c in text):
            errors.append((rel, "control_character"))
        for category, patterns in [("policy", POLICY_DENY), ("privacy", PRIVACY_DENY)]:
            for name, pattern in patterns:
                if re.search(pattern, text):
                    errors.append((rel, category + ":" + name))
        if p.suffix == ".md":
            for dest in re.findall(r"\]\(<([^>]+)>\)", text):
                if re.match(r"https?://", dest):
                    continue
                target = (p.parent / dest.split("#", 1)[0]).resolve()
                if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
                    errors.append((rel, "broken_local_link:" + dest))
    for rel, kind in errors:
        print("FAIL:", rel, kind)
    if not errors:
        print("PASS: content + privacy scans; local links;", len(files), "public candidates")
    return bool(errors)

if __name__ == "__main__":
    raise SystemExit(main())
