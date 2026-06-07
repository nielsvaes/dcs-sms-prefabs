# dcs-sms-prefabs

The community **prefab catalog** for [dcs-sms](https://github.com/nielsvaes/dcs-sms).

A prefab is a saved chunk of a DCS mission — groups, statics, trigger zones,
map drawings — that you can drop into any mission as a ready-made building
block (a SAM site, a carrier group, an airbase defense layout…). The dcs-sms
Mission Editor mod has a **Community** tab that browses this repo over HTTPS and
imports prefabs into your library with one click.

This repo is the source that tab fetches from. The mod reads
[`index.json`](index.json) (a generated manifest) and downloads individual
`.prefab` files from [`prefabs/`](prefabs/).

## How it stays safe

Prefabs are **data, never code**. A `.prefab` is a Lua chunk that does nothing
but `return { … }` — a table of literals and nested tables. Both this repo's CI
and the in-DCS client parse them with a *parse-don't-execute* loader
([`tools/lua_prefab.py`](tools/lua_prefab.py), a port of the client's
`prefab_safe_load.lua`): anything that isn't pure data — a function call, an
identifier used as a value, an operator, an extra statement — is rejected
without ever running. CI fails closed, so a non-data file can't reach `main`.

Every entry in `index.json` also carries the **SHA-256** of the exact prefab
bytes. The client re-hashes each download and refuses any mismatch, so a file
can't be swapped or corrupted in transit.

## Layout

```
dcs-sms-prefabs/
├─ index.json                 # GENERATED manifest the client fetches (do not hand-edit)
├─ prefabs/
│  ├─ <name>.prefab           # the prefab data (Lua `return { … }`), served verbatim
│  └─ <name>.meta.json        # sidecar: human/attribution fields for <name>.prefab
├─ tools/
│  ├─ lua_prefab.py           # parse-don't-execute loader + count derivation
│  └─ gen_index.py            # regenerate index.json; --validate / --check modes
└─ .github/workflows/
   ├─ validate.yml            # PR gate: every prefab is pure data + has a sidecar
   └─ build-index.yml         # on merge to main: regenerate + commit index.json
```

## Contributing a prefab

1. Save a prefab in DCS with the dcs-sms ME mod (it writes a `.prefab` file into
   your library). Copy it into `prefabs/`. Use a lowercase, dash-separated
   filename with **no spaces** (the raw URL must be space-free) — e.g.
   `sa-10-ewr-ring.prefab`. The display name keeps its spaces; it comes from the
   prefab's own `meta.name`.
2. Add a sidecar `prefabs/<same-stem>.meta.json` with the attribution fields
   (see below).
3. Open a PR. **Don't touch `index.json`** — CI regenerates it on merge.

The validate workflow checks your prefab parses as pure data and your sidecar is
present and valid before the PR can merge.

### Sidecar format (`<name>.meta.json`)

Only the human/social fields live here; everything else is derived from the
prefab itself. Most fields default, so a sidecar is usually three lines:

```json
{
  "author": "Niels",
  "description": "Full S-300 site: search + track radars, 4 launchers, command post. Drops as a ready-to-fight ring.",
  "tags": ["sam", "ewr", "redfor"]
}
```

| Field         | Required | Notes |
|---------------|----------|-------|
| `author`      | yes      | Credit for the prefab. |
| `description` | yes      | One or two sentences shown in the detail panel. |
| `tags`        | no       | Lowercased, de-duplicated; powers tag filtering. |
| `name`        | no       | Display-name override; defaults to the prefab's `meta.name`. |
| `date`        | no       | `YYYY-MM-DD`; defaults to the prefab's `meta.created_utc`. |
| `likes`       | no       | Defaults to `0`. |

These are *derived* from the prefab and must **not** be put in the sidecar:
`theatre`, entity counts (`groups`/`statics`/`zones`/`drawings`/`airbases`),
`place_at_origin`, `sha256`, `path`.

## Regenerating the manifest

```sh
python tools/gen_index.py            # rewrite index.json from prefabs/ + sidecars
python tools/gen_index.py --validate # pure-data + sidecar gate only (what CI runs on PRs)
python tools/gen_index.py --check    # exit 1 if index.json is stale
```

(Use `python`, not `python3`. The tools are pure-stdlib — no dependencies.)

## Manifest schema (`index.json`, `schema: 1`)

```jsonc
{
  "schema": 1,
  "generated": "2026-06-07T12:00:00Z",
  "prefabs": [
    {
      "name": "SA-10 EWR ring",          // display name (from meta.name / sidecar)
      "author": "Niels",                 // sidecar
      "date": "2026-06-01",              // sidecar or meta.created_utc
      "theatre": "Caucasus",             // derived from meta.theatre
      "description": "Full S-300 site …", // sidecar
      "tags": ["sam", "ewr", "redfor"],  // sidecar (lowercased)
      "likes": 42,                       // sidecar (default 0)
      "groups": 7, "statics": 0,         // derived entity counts
      "zones": 1, "drawings": 0, "airbases": 0,
      "place_at_origin": false,          // derived from meta.place_at_origin
      "sha256": "<hex of the .prefab bytes>",
      "path": "prefabs/sa-10-ewr-ring.prefab"  // relative to the repo's raw base
    }
  ]
}
```

The client requires `schema == 1`, ignores unknown fields, and skips any entry
missing `name`, `path`, or `sha256`. `path` is resolved against the repo's
`raw.githubusercontent.com` base.
