"""Routes the carrier board with Freerouting, then fills the ground planes.

    D:/KiCad/bin/python.exe pcb/route.py <java.exe> <freerouting.jar>

Exports the board generate.py made to Specctra DSN, lets Freerouting route every connection on both layers, imports
the result and fills the GND zones. Check it afterwards with KiCad's DRC (check.py does that).
"""
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PCB = HERE / "respirai-carrier.kicad_pcb"
DSN, SES = HERE / "build" / "respirai-carrier.dsn", HERE / "build" / "respirai-carrier.ses"


def main():
    java, jar = sys.argv[1], sys.argv[2]
    DSN.parent.mkdir(exist_ok=True)
    board = pcbnew.LoadBoard(str(PCB))
    for track in list(board.GetTracks()):   # start from a clean board every time
        board.Remove(track)
    if not pcbnew.ExportSpecctraDSN(board, str(DSN)):
        sys.exit("DSN export failed")
    SES.unlink(missing_ok=True)
    subprocess.run([java, "-jar", jar, "-de", str(DSN), "-do", str(SES), "-mp", "40", "--gui.enabled=false"],
                   check=False, timeout=900)
    if not SES.exists():
        sys.exit("Freerouting wrote no session file")
    if not pcbnew.ImportSpecctraSES(board, str(SES)):
        sys.exit("SES import failed")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    tracks = list(board.GetTracks())
    vias = sum(1 for t in tracks if t.GetClass() == "PCB_VIA")
    print(f"routed: {len(tracks) - vias} track segments, {vias} vias")


if __name__ == "__main__":
    main()
