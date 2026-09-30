# Repository layout and branches (davidmhunt fork)

| Path | What |
|------|------|
| `hardware/` | The KiCad 10 project: `fmcw3.kicad_pro`, root schematic `fmcw3.kicad_sch` and its sheets (fpga, adc, usb, if, mixer, power, rx, tx), `fmcw3.kicad_pcb`, symbol and footprint libraries (`fmcw3-rescue.lib`, `libs/`, `fmcw3.pretty/`) and lib tables. `fmcw3.pdf` is the KiCad 10 schematic export. |
| `hardware/legacy/` | KiCad 4 leftovers, including the 2017 schematic PDF (`fmcw3_original_2017.pdf`); see its README. |
| `parts/` | BOM, part list and DigiKey availability check for building the board as-is; see its README. |
| `fpga/`, `pc/`, `openocd/` | Upstream FPGA sources, PC-side SAR processing, and OpenOCD config (untouched). |

`fmcw3-rescue.lib` holds the rescued symbol copies from the KiCad 4 to 10
migration and is still referenced by every sheet.

| Branch | Purpose |
|--------|---------|
| `master` | The original upstream design (KiCad 4). |
| `kicad10-migration` | Pure KiCad 4 to 10 migration, no other changes. |
| `kicad10-build` | Build/source base: migration plus the `legacy/` split, `parts/` sourcing tooling and this README. |

# Original upstream README

# 6 GHz two RX channel FMCW radar design files.

For more information see: https://hforsten.com/third-version-of-homemade-6-ghz-fmcw-radar.html

## SAR image formation steps:

Compile Tensorflow custom operations in `pc/sar/sar_op`. See `BUILDING` file in
that directory for the instructions.

`pc/sar/process_sweeps.py` is used to slice the correct time from the measurement file.

`./process_sweeps.py <log file> <start time> <end time> [decimation factor]`

It writes `sweeps.p` file with the data in the format the image formation scripts know how to read.
To form the SAR image run `./backprojection_tf.py sweeps.p` or `./omegak_tf.py sweeps.p`.
Some variables related to the image formation can be found on the top of the image formation scripts.

Example data can be downloaded from: https://hforsten.com/fmcw3/parking_lot_sar.log

Use start and end times of 20 and 136 for it. Decimation factor should be 1 or
2 for backprojection and 2 for omega-k.
