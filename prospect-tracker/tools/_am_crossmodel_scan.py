"""Cross-model map scanner. Read-only. Builds:
   model_id -> {surface, verdict, eval_artifact, code refs, artifact refs, served?}
"""
import json, os, re, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

reg = json.load(open("data/model_registry.json"))
models = reg["models"]

SKIP_DIRS = {"__pycache__", ".git", ".cache", "node_modules"}
FILES = []
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if any(s in p.parts for s in SKIP_DIRS):
        continue
    if p.suffix.lower() in {".py", ".js", ".html", ".yaml", ".yml", ".md", ".txt"}:
        FILES.append(p)

TEXT = {}
for p in FILES:
    try:
        TEXT[p] = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass

def refs(token):
    out = []
    for p, t in TEXT.items():
        if token in t:
            out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return out

CODE_EXT = {".py", ".js", ".html"}
rows = []
for m in models:
    mid = m["model_id"]
    ea = m.get("eval_artifact") or ""
    art_base = os.path.basename(ea) if ea else ""
    r_id = refs(mid)
    r_art = refs(art_base) if art_base else []
    def split(rs):
        code = [x for x in rs if Path(x).suffix in CODE_EXT and not Path(x).name.startswith("test_")
                and not x.startswith("tools/") and not x.startswith("docs/")]
        tools = [x for x in rs if x.startswith("tools/")]
        docs = [x for x in rs if x.startswith("docs/") or Path(x).suffix == ".md"]
        return code, tools, docs
    c_id, t_id, d_id = split(r_id)
    c_art, t_art, d_art = split(r_art)
    rows.append({
        "model_id": mid, "surface": m.get("surface") or "", "verdict": m.get("verdict") or "",
        "eval_artifact": ea, "artifact_exists": bool(ea and os.path.exists(ea)),
        "prod_code_refs": sorted(set(c_id + c_art)),
        "tool_refs": sorted(set(t_id + t_art)),
        "doc_refs": sorted(set(d_id + d_art)),
    })

json.dump(rows, open("data/_am_crossmodel_map.json", "w"), indent=1)
orphans = [r for r in rows if not r["prod_code_refs"]]
print("TOTAL", len(rows), "NO-PROD-CODE-REF", len(orphans))
for r in orphans:
    print("  ORPHAN %-38s %-11s %s" % (r["model_id"], r["verdict"], r["surface"][:44]))
