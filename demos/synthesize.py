"""Build the demo document sets.

    python demos/synthesize.py                 # render PDFs + CSV from the committed sources
    python demos/synthesize.py --regenerate    # ALSO re-synthesise the texts with llm() from demos/synth_prompts

How the committed demo data was produced (honest provenance):
* The Markdown sources in demos/*/source/ were LLM-synthesised from the prompts in demos/synth_prompts/
  (drafted with an LLM assistant, then checked so that cross-references and part numbers are consistent).
  `--regenerate` re-creates them with ForgeAI's own llm() and the same prompts, so the data is reproducible
  with any backend (the result will differ in wording).
* The catalogue CSV is expanded deterministically (seed 2025) from the part families below, which follow
  demos/synth_prompts/spares_catalogue_families.md, so part numbers match the supplier PDFs.
* PDFs are rendered from the Markdown with reportlab.

This is DEMO data tooling only; nothing here is imported by the factory.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

# (prefix, base number, description, category, price range USD, lead time days, supplier)
FAMILIES = [
    ("ME", 1040, "Fuel injector nozzle set (2 pcs)", "Main Engine", (380, 520), (10, 21), "SUP-A"),
    ("ME", 1060, "Exhaust valve spindle", "Main Engine", (2400, 3200), (30, 45), "SUP-A"),
    ("ME", 1080, "Piston ring set", "Main Engine", (900, 1300), (14, 28), "SUP-A"),
    ("ME", 1100, "Main bearing shell", "Main Engine", (1500, 2100), (21, 35), "SUP-B"),
    ("ME", 1120, "Cylinder liner O-ring kit", "Main Engine", (160, 240), (7, 14), "SUP-B"),
    ("ME", 1140, "Fuel pump plunger and barrel", "Main Engine", (2100, 2900), (28, 42), "SUP-B"),
    ("ME", 1160, "Starting air valve overhaul kit", "Main Engine", (480, 690), (14, 21), "SUP-B"),
    ("AE", 1500, "Turbocharger cartridge for auxiliary engine", "Auxiliary Engine", (3800, 5200), (21, 35), "SUP-A"),
    ("AE", 1520, "Lube oil cooler gasket kit", "Auxiliary Engine", (120, 180), (5, 10), "SUP-A"),
    ("AE", 1540, "Auxiliary engine fuel injection pump", "Auxiliary Engine", (1700, 2400), (21, 35), "SUP-B"),
    ("AE", 1560, "Cylinder head gasket", "Auxiliary Engine", (90, 140), (5, 10), "SUP-B"),
    ("PU", 2200, "Ballast pump impeller", "Pumps", (650, 900), (14, 21), "SUP-A"),
    ("PU", 2240, "Fuel oil transfer pump mechanical seal", "Pumps", (280, 420), (7, 14), "SUP-A"),
    ("PU", 2260, "Bilge pump diaphragm kit", "Pumps", (110, 170), (5, 10), "SUP-B"),
    ("PU", 2280, "Fresh water generator pump shaft", "Pumps", (380, 560), (14, 28), "SUP-B"),
    ("VL", 3100, "Butterfly valve DN150 with gear operator", "Valves", (420, 610), (10, 21), "SUP-A"),
    ("VL", 3120, "Globe valve DN50 bronze", "Valves", (210, 320), (7, 14), "SUP-B"),
    ("VL", 3140, "Safety relief valve 10 bar", "Valves", (340, 480), (10, 21), "SUP-B"),
    ("VL", 3160, "Quick-closing valve actuator", "Valves", (880, 1200), (21, 35), "SUP-C"),
    ("FL", 4000, "Fuel oil filter element", "Filters", (45, 80), (3, 7), "SUP-A"),
    ("FL", 4020, "Lube oil automatic filter candle set", "Filters", (310, 460), (10, 14), "SUP-A"),
    ("FL", 4040, "Sea water strainer basket", "Filters", (160, 240), (7, 14), "SUP-B"),
    ("FL", 4060, "Engine air intake filter", "Filters", (70, 120), (5, 10), "SUP-C"),
    ("EL", 5000, "Alternator AVR card", "Electrical", (650, 950), (10, 21), "SUP-A"),
    ("EL", 5100, "Main switchboard circuit breaker 630A", "Electrical", (1900, 2600), (21, 35), "SUP-B"),
    ("EL", 5120, "LED floodlight 150W", "Electrical", (180, 260), (7, 14), "SUP-B"),
    ("EL", 5140, "Shore connection cable reel", "Electrical", (2300, 3300), (35, 60), "SUP-B"),
    ("DK", 6000, "Mooring winch brake lining set", "Deck Machinery", (540, 780), (14, 28), "SUP-A"),
    ("DK", 6020, "Hatch cover hydraulic cylinder seal kit", "Deck Machinery", (260, 380), (14, 21), "SUP-B"),
    ("DK", 6040, "Windlass gearbox bearing", "Deck Machinery", (720, 990), (21, 35), "SUP-B"),
    ("DK", 6060, "Crane slewing ring seal", "Deck Machinery", (1300, 1800), (28, 42), "SUP-C"),
    ("SF", 7000, "SOLAS immersion suit", "Safety Equipment", (260, 340), (5, 10), "SUP-A"),
    ("SF", 7020, "Lifejacket with light", "Safety Equipment", (48, 75), (3, 7), "SUP-A"),
    ("SF", 7040, "CO2 fire extinguisher 6 kg", "Safety Equipment", (140, 190), (5, 10), "SUP-A"),
    ("SF", 7060, "EEBD emergency escape breathing device", "Safety Equipment", (390, 520), (10, 14), "SUP-C"),
    ("NV", 8000, "Gyro compass sensor module", "Navigation", (2900, 3900), (30, 45), "SUP-A"),
    ("NV", 8020, "ECDIS display unit", "Navigation", (5200, 6900), (35, 60), "SUP-B"),
    ("NV", 8040, "VHF radio handset", "Navigation", (240, 330), (7, 14), "SUP-C"),
]
VESSEL_CLASSES = ["Bulk Carrier", "Container Feeder", "Product Tanker", "Offshore Supply Vessel"]


def build_catalogue(path: Path, seed: int = 2025) -> int:
    rng = random.Random(seed)
    rows = []
    for prefix, base, desc, cat, (pmin, pmax), (lmin, lmax), sup in FAMILIES:
        for k, vc in enumerate(VESSEL_CLASSES):
            stock = rng.choice([0, 0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 24, 30, 40])
            rows.append({
                "part_no": f"{prefix}-{base + k}", "description": desc, "category": cat,
                "unit_price_usd": f"{rng.uniform(pmin, pmax):.2f}", "stock": stock,
                "lead_time_days": rng.randint(lmin, lmax) if stock == 0 else rng.randint(1, max(2, lmin // 3)),
                "supplier_id": sup, "vessel_class": vc})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = []
    bullets: list = []

    def flush_bullets() -> None:
        nonlocal bullets
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(b, styles["BodyText"])) for b in bullets],
                                      bulletType="bullet", leftIndent=14))
            bullets = []

    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            flush_bullets()
            continue
        if line.startswith("# "):
            flush_bullets()
            story += [Paragraph(esc(line[2:]), styles["Title"]), Spacer(1, 6)]
        elif line.startswith("## "):
            flush_bullets()
            story += [Spacer(1, 6), Paragraph(esc(line[3:]), styles["Heading2"])]
        elif re.match(r"^(-|\d+\.)\s", line):
            bullets.append(esc(re.sub(r"^(-|\d+\.)\s", "", line)))
        else:
            flush_bullets()
            story += [Paragraph(esc(line), styles["BodyText"]), Spacer(1, 4)]
    flush_bullets()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title=md_path.stem).build(story)


HR_DOCS = {
    "leave_policy": ("Leave Policy for Shore Staff", "HR-POL-01",
                     "annual, sick, casual, maternity/paternity, bereavement, marriage leave, public holidays, "
                     "leave without pay, compensatory time off, unauthorised absence, contacts",
                     "Code of Conduct HR-POL-02 (notice periods, disciplinary); Travel and Expenses HR-POL-03 (weekend travel comp-off)"),
    "code_of_conduct": ("Code of Conduct for Shore Staff", "HR-POL-02",
                        "working hours and hybrid work, dress code and site safety, gifts and hospitality, conflicts "
                        "of interest, data protection, IT use, anti-bribery, disciplinary procedure, grievances, "
                        "harassment, resignation notice periods",
                        "Leave Policy HR-POL-01 (unauthorised absence, leave encashment); Travel and Expenses HR-POL-03 (client hospitality)"),
    "travel_and_expenses_policy": ("Travel and Expenses Policy", "HR-POL-03",
                                   "travel approval, booking and class of travel, hotel limits, per diem, weekend "
                                   "travel comp-off, ground transport, expense claims and advances, client "
                                   "hospitality, non-reimbursable items, corporate cards, insurance, contacts",
                                   "Leave Policy HR-POL-01 (comp-off); Code of Conduct HR-POL-02 (gifts and hospitality)"),
}


def regenerate_texts() -> None:
    """Re-synthesise the Markdown sources with ForgeAI's llm() and the committed prompts."""
    from forgeai.llm import llm
    tmpl = (ROOT / "synth_prompts" / "hr_policy_document.md").read_text(encoding="utf-8")
    for name, (title, code, sections, refs) in HR_DOCS.items():
        prompt = (tmpl.replace("{{title}}", title).replace("{{code}}", code).replace("{{sections}}", sections)
                  .replace("{{cross_refs}}", refs))
        (ROOT / "hr_policy" / "source" / f"{name}.md").write_text(llm(prompt, temperature=0.5, max_tokens=3000),
                                                                  encoding="utf-8")
        print("regenerated", name)
    tmpl = (ROOT / "synth_prompts" / "supplier_terms_document.md").read_text(encoding="utf-8")
    sup = {"supplier_terms_a": ("Anchorline Marine Supplies", "SUP-A", "Rotterdam and Singapore", "Bluefin Ship Spares"),
           "supplier_terms_b": ("Bluefin Ship Spares", "SUP-B", "Piraeus and Fujairah", "Anchorline Marine Supplies")}
    for name, (sname, sid, wh, other) in sup.items():
        parts = ", ".join(f"{p}-{b + k}" for p, b, *_rest, s in FAMILIES if s == sid for k in range(2))
        prompt = (tmpl.replace("{{supplier_name}}", sname).replace("{{supplier_id}}", sid)
                  .replace("{{warehouses}}", wh).replace("{{series}}", "ME, AE, PU, VL, FL, EL, DK, SF, NV")
                  .replace("{{part_numbers}}", parts).replace("{{other_supplier}}", other))
        (ROOT / "ship_spares" / "source" / f"{name}.md").write_text(llm(prompt, temperature=0.5, max_tokens=2500),
                                                                    encoding="utf-8")
        print("regenerated", name)


REGRESSION_CHANGES = [  # (file, old text, new text): a "policy update" for the regression-mode demo
    ("leave_policy", "are entitled to 21 working days of paid annual leave", "are entitled to 22 working days of paid annual leave"),
    ("leave_policy", "a maximum of 10 unused annual leave days", "a maximum of 8 unused annual leave days"),
    ("travel_and_expenses_policy", "International travel: USD 60 per day.", "International travel: USD 70 per day."),
]


def build_regression_set() -> None:
    """demos/hr_policy_v2: the same HR documents after a policy update (3 facts changed)."""
    src, dst = ROOT / "hr_policy" / "source", ROOT / "hr_policy_v2"
    (dst / "source").mkdir(parents=True, exist_ok=True)
    texts = {p.stem: p.read_text(encoding="utf-8") for p in src.glob("*.md")}
    for name, old, new in REGRESSION_CHANGES:
        assert old in texts[name], f"regression change not found in {name}: {old}"
        texts[name] = texts[name].replace(old, new)
    for name, text in texts.items():
        (dst / "source" / f"{name}.md").write_text(text, encoding="utf-8")
        md_to_pdf(dst / "source" / f"{name}.md", dst / "docs" / f"{name}.pdf")
    (dst / "CHANGES.md").write_text("# Policy update used for the regression-mode demo\n\n" + "\n".join(
        f"- `{n}`: \"{o}\" -> \"{w}\"" for n, o, w in REGRESSION_CHANGES) + "\n", encoding="utf-8")
    print(f"built {dst} with {len(REGRESSION_CHANGES)} changed facts")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true", help="re-synthesise texts with the LLM first")
    ap.add_argument("--regression", action="store_true", help="also build demos/hr_policy_v2 (changed policies)")
    args = ap.parse_args()
    if args.regenerate:
        regenerate_texts()
    if args.regression:
        build_regression_set()
    for name in HR_DOCS:
        md_to_pdf(ROOT / "hr_policy" / "source" / f"{name}.md", ROOT / "hr_policy" / "docs" / f"{name}.pdf")
    for name in ("supplier_terms_a", "supplier_terms_b"):
        md_to_pdf(ROOT / "ship_spares" / "source" / f"{name}.md", ROOT / "ship_spares" / "docs" / f"{name}.pdf")
    n = build_catalogue(ROOT / "ship_spares" / "docs" / "spares_catalogue.csv")
    print(f"rendered 5 PDFs and a catalogue with {n} rows")


if __name__ == "__main__":
    main()
