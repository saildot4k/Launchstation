"""Generate opt-in developer profiles without changing saved user settings."""
from pathlib import Path
import argparse

def configure(source, stage):
    stages = {"profile": (0, 0), "vu0": (1, 0), "vu1": (0, 1), "both": (1, 1), "vu1-reference": (0, 1)}
    if stage not in stages:
        raise ValueError("Unknown VU stage")
    anchor = "      - WLE_PS2BUILD"
    if source.count(anchor) != 1:
        raise ValueError("Expected exactly one application defines list")
    vu0, vu1 = stages[stage]
    reference = int(stage == "vu1-reference")
    return source.replace(anchor, anchor + f"\n      - DASH_PROFILE=1\n      - DASH_VU0={vu0}\n      - DASH_VU1={vu1}\n      - DASH_VU1_REFERENCE={reference}", 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("profile", "vu0", "vu1", "both", "vu1-reference"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / f".ps2-vu-{args.stage}.yaml"
    output.write_text(configure((root / "ps2.yaml").read_text(), args.stage))
    print(output.name)
