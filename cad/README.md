# cad/

The 3D-printed enclosure.

What belongs here:

- `components.csv` — the measured size of every part, filled in by Electronics with calipers ([contract 3](../docs/ARCHITECTURE.md#3-electronics--cad-componentscsv))
- source models (base, lid, diffuser panel, tube adapter test piece)
- exported STL files sent to the print service
- separate lid/base variants for the ECG and pulse add-ons, if they are built

Design rules are in [`docs/ENCLOSURE.md`](../docs/ENCLOSURE.md). Nothing gets modelled until `components.csv` is filled in — never model from a photo or a datasheet.
