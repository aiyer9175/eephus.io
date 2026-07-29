"""Recon scratch: MLB projections module. Read-only measurements."""
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / ".cache" / "fa_corpus.pkl"


def corpus():
    with open(CORPUS, "rb") as fh:
        return pickle.load(fh)


def payload():
    return json.loads((ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    c = corpus()
    print("corpus first/last", c["first"], c["last"],
          "hit rows", len(c["hit"]), "pit rows", len(c["pit"]))
