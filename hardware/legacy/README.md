# legacy/

KiCad 4-era files that the KiCad 10 project no longer uses. They were moved
here with `git mv` (history kept, nothing deleted) on the `kicad10-build`
branch. The original upstream design is Henrik Forstén's
[Ttl/fmcw3](https://github.com/Ttl/fmcw3); this fork's `master`
(`e57ce3b`) is the untouched KiCad 4 original.

| File | What | Why unused |
|------|------|-----------|
| `fmcw3.pro` | KiCad 4 project file | Replaced by `fmcw3.kicad_pro`. |
| `fmcw3-cache.lib` | KiCad 4 schematic symbol cache | Not in `sym-lib-table`; KiCad 10 schematics embed their symbols. |
| `imu.sch` | KiCad 4 IMU sheet | No `imu` sheet in the KiCad 10 hierarchy (the root sheet lists fpga, if, mixer, power, rx, tx). |
| `fmcw3.bak`, `fmcw3.bck` | Backups of the `fmcw3` symbol library (from `libs/`) | Backups only; the live library is `libs/fmcw3.lib`. |
| `fmcw3_original_2017.pdf` | Schematic PDF exported by Eeschema in 2017 | Kept as the labelled original for comparison. The KiCad 10 export is `../fmcw3.pdf`. |

Each file above was checked to be unreferenced by the KiCad 10 sheets,
`fmcw3.kicad_pro`, `sym-lib-table` and `fp-lib-table` before it was moved.

## Deliberately not moved

- `fmcw3-rescue.lib`: holds the rescued symbol copies from the KiCad 4 to 10
  migration (219+ `fmcw3-rescue:*` symbols) and is in `sym-lib-table`; every sheet references it.
- `libs/fmcw3.lib` and `libs/fmcw3.dcm`, `fmcw3.pretty/`, `sym-lib-table`, `fp-lib-table`: in use.
- `report.txt` and `rescue-backup/` are local, gitignored migration leftovers and are not part of the branch.
