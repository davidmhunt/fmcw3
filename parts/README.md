# parts/

Sourcing tooling for building the fmcw3 board as-is. Every BOM group of the
KiCad 10 project has a row, with a status.

| File | What |
|------|------|
| `bom_pcb.csv` | BOM grouped by value and footprint, exported from the KiCad 10 project (`Refs, Value, Footprint, MPN, DNP, Qty`). Input to `gen_parts_csv.py`. |
| `gen_parts_csv.py` | Builds `parts.csv` from `bom_pcb.csv` plus the schematic netlist (`kicad-cli`, read-only). Holds the curated exact-MPN table and the inference rules. Re-running it overwrites `parts.csv`. |
| `parts.csv` | One row per BOM group (split where needed: RF-path members, rail-voltage classes). `kind` = `mpn` (exact part, looked up), `generic` (spec only, no MPN), `dnp`, `nopart` (via, test point, hole, printed coupler). |
| `check_digikey.py` | Looks up every `kind=mpn` row on DigiKey and writes `availability.csv` and `fields_to_apply.csv`. `python parts/check_digikey.py [--boards N]` from the repo root. |
| `availability.csv` | Output of the last run (a dated snapshot, regenerate before ordering). `status` is never blank: Active / Obsolete / NFND / No-result / needs-David / generic-spec-only / DNP / no-part. `dk_status` keeps DigiKey's own text. |
| `fields_to_apply.csv` | One row per schematic ref, for the Hardware step that writes symbol fields: Manufacturer, MPN, DigiKey PN, Status, plus spec fields for generic passives. |
| `suffix_decisions.csv` | How each fuzzy part-number suffix was resolved, with datasheet URL and page, or the candidate list for `needs-David`. |

Spec fields for generic passives: value and package come from the schematic
(value, footprint). Tolerance and dielectric are not in the schematic and are
written as `unspecified`; `tolerance_hint` and `dielectric_hint` in
`parts.csv` are suggestions only. `voltage` is an inferred minimum
(1.5x the highest supply rail on the part's nets, rounded up to a standard
rating; 12 V input taken as 15 V); it is always labelled inferred. No generic
passive carries an MPN.

`check_digikey.py` reads credentials from `.digikey.env` at the repo root
(one level above this folder). That file is gitignored; never commit it.
