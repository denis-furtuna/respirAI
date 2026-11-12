# cad/

The 3D-printed enclosure: a hand-held body, about 94 × 59 × 32 mm, that closes in two halves around the stethoscope chest piece. The diaphragm stands 5.6 mm proud of the chest-side face; the bell, the metal stem, the microphone, the XIAO, the battery and the switch are inside.

| File | What it is |
|---|---|
| `components.csv` | measured size of every part ([contract 3](../docs/ARCHITECTURE.md#3-electronics--cad-componentscsv)); the model reads its numbers from here |
| `case.py` | the model: parameters at the top, geometry below |
| `generate.py` | writes the STL files to `out/` |
| `check.py` | tests the model: collisions, holding, assembly, printability, exported files |
| `render.py` | writes shaded views and cross-sections to `out/` |
| `out/respirai-half-a.stl`, `out/respirai-half-b.stl` | the two parts to print |
| `out/respirai-assembly.stl` | everything in place, for looking at only |

## Changing and rebuilding

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python generate.py
.venv/Scripts/python check.py
.venv/Scripts/python render.py
```

Change a measurement in `components.csv` or a design choice at the top of `case.py`, then run the three scripts again. Do not send a file to the printer unless `check.py` ends with every check passed.

The model is built from meshes (manifold3d), so it exports STL but not STEP.

## Layout

Frame used in the code and the pictures: x runs along the metal stem (the chest piece axis is x = 0), y across the body (the halves meet at y = 0), z is the depth behind the diaphragm.

- **Chest piece.** Both halves close around its waist, between the big head (outside) and the small head (inside). It cannot move or turn once the body is shut.
- **Microphone.** Sits across the stem tip in a round pocket, port on the stem axis, 0.5 mm from the metal. The two rows of pins point away from the stem, one row toward each half.
- **XIAO.** Lies flat in half A, top side toward the chest, with the USB-C socket through the side wall and 0.35 mm proud of it. A rib on half B reaches across and backs the inner end of the board, so pushing a plug in cannot slide it.
- **Battery.** Flat against the palm-side wall, behind the chest piece. Its wires must leave at the XIAO end.
- **Switch.** In a pocket on the side wall of half B, slider through a 6 × 3 mm slot.
- **Three M3 × 12 screws** go in from half B and cut their own thread in 2.7 mm holes in half A.

## Printing

| Setting | Value |
|---|---|
| Material | PLA |
| Layer height | 0.2 mm |
| Perimeters | 3 |
| Infill | 20 % |
| Supports | none |
| Orientation | as exported: each half on its outer side wall, open side up |

About 25 cm³ of plastic per half.

## Putting it together

1. Stick a soft ring (0.5 mm, hole of 3 mm or more) on the stem tip, or run a thin bead of silicone around it. Keep the mic port clear.
2. Lay the chest piece into half A: waist in the collar, stem in its channel.
3. Slide the mic board into its pocket, port side against the stem tip, pin rows left and right. Put a 1 mm foam pad with a hole for the pins behind it.
4. Plug the wires onto the XIAO, then lower it into its channel until the USB-C socket is through the wall.
5. Lower the battery in behind the lips, wires toward the XIAO.
6. Glue the switch into its pocket in half B and wire it in series with the battery's + lead.
7. Close half B over half A and drive the three screws. Stop when they are snug: the thread is plastic.

## Not confirmed yet

These numbers are assumed in `case.py`, not measured. Check them on the real parts before ordering a print.

| What | Assumed | Why it matters |
|---|---|---|
| Stem position in the waist | centred in its 8.3 mm | sets the depth of the stem channel and the mic |
| Shape of the chest piece between its three diameters | plain steps | a cone behind the big head would need a wider collar |
| Diameter over the ribs at the stem tip | fits in 8.4 mm | the channel is 8.4 mm wide |
| Distance between the mic's two pin rows | 10 mm | width of the opening behind the mic |
| USB-C socket overhang past the XIAO board edge | 1.4 mm | how far the socket reaches through the wall |
| XIAO board thickness | up to 1.6 mm | slot that holds the board edge |
| Slide switch body and slider | 8.6 × 4.3 × 4 mm, slot 6 × 3 mm | pocket and slot |
| XIAO antenna | not modelled | it has to be stuck to a free wall near the XIAO |
| Fit clearances | 0.25 mm | depend on the printer; expect to adjust after the first print |
