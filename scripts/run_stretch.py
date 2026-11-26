"""Stretch demos on top of a finished run (default runs/hr_policy):

1. factory vs hand-written baseline: score demos/hr_policy/handwritten_baseline_definition.json on the
   factory's eval set and compare case by case with the factory's final results;
2. regression mode: point the factory's final definition at demos/hr_policy_v2/docs (3 changed facts,
   see CHANGES.md), re-run the OLD eval set and report what broke.

    python scripts/run_stretch.py [runs/hr_policy]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from forgeai.runner import load_definition  # noqa: E402

run = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "runs/hr_policy")
final_def = load_definition(run / "agent_definition_final.json")
cards = json.loads((run / "scorecard.json").read_text(encoding="utf-8"))
final_iter = [c for c in cards if c["definition_version"] == final_def.version][-1]["iteration"]
final_results = (run / f"results_iter{final_iter}.json").relative_to(ROOT).as_posix()
evals = (run / "evals.json").relative_to(ROOT).as_posix()
print(f"final definition v{final_def.version} = results_iter{final_iter}.json")

reg_dir = run / "regression_docs_v2"
reg_dir.mkdir(exist_ok=True)
reg_def = final_def.model_copy(deep=True)
reg_def.documents_dir = "demos/hr_policy_v2/docs"
reg_def.description = "Final agent definition pointed at the updated documents (demos/hr_policy_v2, see CHANGES.md)"
(reg_dir / "agent_definition_docs_v2.json").write_text(reg_def.model_dump_json(indent=2), encoding="utf-8")

jobs = [
    ("demos/hr_policy/handwritten_baseline_definition.json", run / "handwritten_baseline",
     "Factory (final) vs hand-written baseline: cases where they differ"),
    ((reg_dir / "agent_definition_docs_v2.json").relative_to(ROOT).as_posix(), reg_dir,
     "Regression report: old eval set vs agent on updated policy documents"),
]
for definition, out, title in jobs:
    cmd = [sys.executable, "-m", "forgeai", "eval", "--definition", definition, "--evals", evals,
           "--out", out.relative_to(ROOT).as_posix(), "--compare", final_results, "--title", title]
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
