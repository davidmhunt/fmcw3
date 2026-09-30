# parts/

Sourcing tooling for building the fmcw3 board as-is.

| File | What |
|------|------|
| `bom_pcb.csv` | BOM grouped by value and footprint, exported from the KiCad 10 project (`Refs, Value, Footprint, MPN, DNP, Qty`). |
| `parts.csv` | Hand-curated list of the parts to look up: `refs, qty, value, search_term, notes`. Input to `check_digikey.py`. |
| `check_digikey.py` | Queries the DigiKey API for stock and lifecycle of each `parts.csv` row. `python parts/check_digikey.py [--boards N]`. |
| `availability.csv` | Output of the last `check_digikey.py` run (a dated snapshot, regenerate before ordering). |

`check_digikey.py` reads credentials from `.digikey.env` at the repo root
(one level above this folder). That file is gitignored; never commit it.
