<div align="center">

# 🥥 DCS-SMS Prefabs

### The community stash of ready-made DCS building blocks.

SAM sites. EWR rings. Carrier groups. Fortified artillery bases. Whole airbase
defense layouts. All built by the community, all a click away.

<br>

[![Join the Coconut Cockpit Discord](https://img.shields.io/badge/Discord-Join%20the%20Coconut%20Cockpit-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/mFFXYmet)

[![Discord members](https://img.shields.io/discord/1501529032817115266?logo=discord&logoColor=white&label=members&color=5865F2)](https://discord.gg/mFFXYmet)
&nbsp;
[![Prefabs in catalog](https://img.shields.io/github/directory-file-count/nielsvaes/dcs-sms-prefabs/prefabs?type=file&extension=prefab&label=prefabs%20in%20catalog&logo=github)](prefabs/)

</div>

---

## What is this?

This is the **community prefab catalog** for
[dcs-sms](https://github.com/nielsvaes/dcs-sms) — a pile of prefabs that DCS
players have built and shared with everyone else.

A **prefab** is a saved chunk of a DCS mission — groups, statics, trigger zones,
map drawings — bundled up as a ready-made building block you can drop into *any*
mission. Instead of placing forty units by hand every time you want a Syrian
artillery position or an early-warning radar site, you grab one someone already
made and drop it in.

It's the LEGO bin for your missions, stocked by the community.

## Getting prefabs into your missions

If you have the **dcs-sms** Mission Editor mod installed, open its **Community**
tab. It reads straight from this repo, shows you everything in the catalog, and
imports any prefab into your library with one click. That's the whole flow —
browse, click, done.

## 💛 Share your own — come hang out in the Discord!

Here's the fun part: **this catalog is filled by you.**

We don't want you opening pull requests or wrestling with Git. We've got a much
nicer way. Built something cool in the Mission Editor — a nasty SAM trap, a
detailed FARP, a coastline bristling with air defense? **Post it in the
[Coconut Cockpit Discord](https://discord.gg/mFFXYmet)** and our friendly bot
picks it up, checks it over, and adds it to this catalog for everyone to enjoy.

No gatekeeping, no hoops. Just share the stuff you're proud of.

<div align="center">

### 👉 [**Join the Coconut Cockpit Discord →**](https://discord.gg/mFFXYmet) 👈

Drop your prefabs, swap ideas, show off your missions, and meet other
DCS folks who like building cool things.

[![Join the Coconut Cockpit Discord](https://img.shields.io/badge/Discord-discord.gg%2FmFFXYmet-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/mFFXYmet)

</div>

## What's already in here?

A growing collection of community submissions — air defense emplacements,
early-warning radar sites, fortified bases, and more, across multiple theatres.
Browse them all in [`prefabs/`](prefabs/), or just open the **Community** tab in
the mod and see them with descriptions and previews. And yes — **your** prefab
could be the next one on the list. 😉

---

<details>
<summary><b>🔧 Under the hood</b> — how the catalog works (for the curious & for maintainers)</summary>

<br>

The friendly stuff above is all most people need. Everything below is the
nuts-and-bolts of how the catalog is structured and kept safe. The Discord bot
handles all of this automatically when you submit — you don't have to.

### How it stays safe

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

### Layout

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

### Contributing a prefab by hand

Most people should just post in the [Discord](https://discord.gg/mFFXYmet) and
let the bot do this. But if you'd rather do it yourself:

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

### Regenerating the manifest

```sh
python tools/gen_index.py            # rewrite index.json from prefabs/ + sidecars
python tools/gen_index.py --validate # pure-data + sidecar gate only (what CI runs on PRs)
python tools/gen_index.py --check    # exit 1 if index.json is stale
```

(Use `python`, not `python3`. The tools are pure-stdlib — no dependencies.)

### Manifest schema (`index.json`, `schema: 1`)

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

</details>
