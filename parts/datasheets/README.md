# fmcw3 datasheet library

Local copies of the vendor datasheets for every sourced part on the board and
for every substitute candidate considered in
`docs/hardware/fmcw3/substitutes.md` (Falcon repo). Only `manifest.csv`,
`fetch.py`, this README and `.gitignore` are tracked. The PDFs are
vendor-copyrighted and are **gitignored**: this repo is public, never commit
them.

## Use

```
python3 hardware/fmcw3/parts/datasheets/fetch.py
```

Stdlib only, no credentials. It downloads whatever is missing, validates it
(`%PDF-` magic for PDFs; bot-challenge pages are rejected), and writes
`sha256`, `retrieved` and `status` back to `manifest.csv`. It is idempotent.
For anything it cannot get it prints a "pull by hand" list: save each URL in a
browser to `parts/datasheets/<local_filename>` exactly as listed, then re-run;
the row becomes `manual`.

## manifest.csv

| column | meaning |
|---|---|
| `MPN` | manufacturer part number(s) covered (`;`-separated when one datasheet covers several) |
| `key` | short citation key used in `substitutes.md` (blank when the memo has none) |
| `refs` | schematic refs using this part (blank for substitute candidates) |
| `url` | canonical vendor URL; this is what goes in the schematic `Datasheet` field |
| `local_filename` | file name under this directory |
| `sha256`, `retrieved` | of the local file, date first obtained |
| `status` | `fetched` (downloaded), `manual` (dropped in by hand), `unreachable` (still to pull) |
| `mirrors` | `|`-separated fallback URLs (distributor copies; may be an older revision, see `notes`) |
| `notes` | role of the row, caveats |

Generic passives (spec only, no MPN) have no row. TI URLs are the stable
`ti.com/lit/ds/symlink/<part>.pdf` form rather than the tracking redirector
DigiKey supplies.
