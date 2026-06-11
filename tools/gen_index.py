#!/usr/bin/env python
"""gen_index.py — regenerate index.json from prefabs/ + sidecar metadata.

The catalog's manifest (`index.json`) is a BUILD ARTIFACT. It is never
hand-edited and never committed by contributors: a `.prefab` file plus its
`<name>.meta.json` sidecar are the only things a contribution (or the future
Discord bot) adds, and CI regenerates `index.json` on merge to `main`. That
keeps contributor PRs conflict-free — they never touch the shared manifest.

For each `prefabs/*.prefab` this:
  1. Reads the EXACT file bytes and computes their SHA-256 (the client rejects
     any download whose hash doesn't match the manifest — so this must be the
     hash of the bytes raw.githubusercontent.com will serve).
  2. Parses the prefab as pure data (lua_prefab — never executed) and derives
     the entity counts / theatre / place_at_origin, mirroring what the ME
     prefab library shows.
  3. Merges the human/Discord fields (author, description, tags, likes, date)
     from the sibling `<stem>.meta.json` sidecar. Most fields auto-default, so
     a hand-written sidecar is often just {author, description, tags}.
  4. Emits a schema-1 manifest matching the ME client's community_manifest.lua.

Usage:
    python tools/gen_index.py              # regenerate index.json
    python tools/gen_index.py --check      # exit 1 if index.json is stale
    python tools/gen_index.py --validate   # parse + sidecar gate only (no write)

Use `python` (not `python3`) on Windows.
"""

import argparse
import datetime
import glob
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lua_prefab  # noqa: E402

SCHEMA = 1
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFABS_DIR = os.path.join(REPO_ROOT, "prefabs")
INDEX_PATH = os.path.join(REPO_ROOT, "index.json")

# Field order mirrors the demo manifest so diffs read naturally.
_ENTRY_ORDER = [
    "name", "author", "date", "theatre", "description", "tags", "likes",
    "groups", "statics", "zones", "drawings", "airbases", "required_modules",
    "place_at_origin", "sha256", "path",
]


class BuildError(Exception):
    pass


def _sha256_hex(data):
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _sidecar_path(prefab_path):
    return prefab_path[: -len(".prefab")] + ".meta.json"


def _load_sidecar(prefab_path):
    """Load the required <stem>.meta.json sidecar. Raises BuildError if it is
    missing or malformed — every catalog prefab must carry attribution."""
    sc = _sidecar_path(prefab_path)
    base = os.path.basename(prefab_path)
    if not os.path.isfile(sc):
        raise BuildError("%s: missing sidecar %s" % (base, os.path.basename(sc)))
    try:
        with io.open(sc, "r", encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise BuildError("%s: invalid JSON sidecar (%s)" % (os.path.basename(sc), e))
    if not isinstance(data, dict):
        raise BuildError("%s: sidecar must be a JSON object" % os.path.basename(sc))
    author = data.get("author")
    if not isinstance(author, str) or author.strip() == "":
        raise BuildError("%s: sidecar requires a non-empty 'author'" % os.path.basename(sc))
    desc = data.get("description")
    if not isinstance(desc, str) or desc.strip() == "":
        raise BuildError(
            "%s: sidecar requires a non-empty 'description'" % os.path.basename(sc)
        )
    return data


def _clean_tags(raw):
    out = []
    seen = set()
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, str):
                t = t.strip().lower()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
    return out


def build_entry(prefab_path):
    """Build one manifest entry from a prefab file + its sidecar.
    Raises BuildError / PrefabError on any problem."""
    fname = os.path.basename(prefab_path)
    with io.open(prefab_path, "rb") as f:
        raw_bytes = f.read()
    sha = _sha256_hex(raw_bytes)

    parsed = lua_prefab.parse(raw_bytes.decode("utf-8"))
    derived = lua_prefab.derive(parsed)
    sidecar = _load_sidecar(prefab_path)

    # name: sidecar override > prefab meta.name > filename stem
    name = sidecar.get("name")
    if not (isinstance(name, str) and name.strip()):
        name = derived["name"]
    if not (isinstance(name, str) and name.strip()):
        name = fname[: -len(".prefab")]

    # date: sidecar override > prefab created_utc (date part) > ""
    date = sidecar.get("date")
    if not (isinstance(date, str) and date.strip()):
        created = derived["created_utc"]
        date = created[:10] if isinstance(created, str) and created else ""

    likes = sidecar.get("likes", 0)
    if not isinstance(likes, (int, float)) or isinstance(likes, bool):
        likes = 0

    entry = {
        "name": name,
        "author": sidecar["author"],
        "date": date,
        "theatre": derived["theatre"],
        "description": sidecar["description"],
        "tags": _clean_tags(sidecar.get("tags")),
        "likes": int(likes),
        "groups": derived["groups"],
        "statics": derived["statics"],
        "zones": derived["zones"],
        "drawings": derived["drawings"],
        "airbases": derived["airbases"],
        "required_modules": derived["required_modules"],
        "place_at_origin": derived["place_at_origin"],
        "sha256": sha,
        "path": "prefabs/" + fname,
    }
    # Re-key into the canonical field order.
    return {k: entry[k] for k in _ENTRY_ORDER}


def build_entries():
    """Build all entries, sorted by path for stable diffs. Raises on the first
    bad prefab/sidecar (CI fails closed)."""
    paths = sorted(glob.glob(os.path.join(PREFABS_DIR, "*.prefab")))
    entries = []
    for p in paths:
        try:
            entries.append(build_entry(p))
        except (BuildError, lua_prefab.PrefabError) as e:
            raise BuildError(str(e))
    entries.sort(key=lambda e: e["path"])
    return entries


def _load_existing():
    if not os.path.isfile(INDEX_PATH):
        return None
    try:
        with io.open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return None


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_manifest():
    """Build the full manifest dict. Preserves the existing `generated`
    timestamp when the entry set is unchanged, so unrelated pushes don't
    churn the file (and CI doesn't commit-loop)."""
    entries = build_entries()
    existing = _load_existing()
    generated = _now_iso()
    if isinstance(existing, dict) and existing.get("prefabs") == entries:
        generated = existing.get("generated", generated)
    return {"schema": SCHEMA, "generated": generated, "prefabs": entries}


def _dump(manifest):
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def cmd_generate():
    manifest = build_manifest()
    with io.open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(_dump(manifest))
    print("wrote %s (%d prefab(s))" % (
        os.path.relpath(INDEX_PATH, REPO_ROOT), len(manifest["prefabs"])))
    return 0


def cmd_check():
    """Exit 1 if index.json's entry set differs from a fresh build (ignoring
    the `generated` timestamp). Validates prefabs/sidecars as a side effect."""
    fresh = build_entries()
    existing = _load_existing()
    if not isinstance(existing, dict):
        print("index.json missing or unparseable; run gen_index.py", file=sys.stderr)
        return 1
    if existing.get("schema") != SCHEMA:
        print("index.json schema != %d" % SCHEMA, file=sys.stderr)
        return 1
    if existing.get("prefabs") != fresh:
        print("index.json is STALE — run `python tools/gen_index.py`", file=sys.stderr)
        return 1
    print("index.json is up to date (%d prefab(s))" % len(fresh))
    return 0


def cmd_validate():
    """Pure-data + sidecar gate. Parses every prefab and loads every sidecar;
    exits 1 on the first failure. No write, no freshness check (the manifest is
    generated on main, so contributor PRs never carry it)."""
    paths = sorted(glob.glob(os.path.join(PREFABS_DIR, "*.prefab")))
    if not paths:
        print("no prefabs found under prefabs/", file=sys.stderr)
        return 1
    ok = True
    for p in paths:
        rel = os.path.relpath(p, REPO_ROOT)
        try:
            build_entry(p)
            print("ok   %s" % rel)
        except (BuildError, lua_prefab.PrefabError) as e:
            ok = False
            print("FAIL %s: %s" % (rel, e), file=sys.stderr)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regenerate index.json from prefabs/.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true",
                   help="exit 1 if index.json is stale (no write)")
    g.add_argument("--validate", action="store_true",
                   help="parse + sidecar gate only (no write, no freshness check)")
    args = ap.parse_args(argv)
    try:
        if args.check:
            return cmd_check()
        if args.validate:
            return cmd_validate()
        return cmd_generate()
    except BuildError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
