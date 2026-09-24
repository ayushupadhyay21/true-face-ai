"""Presentation attack detection metrics (ISO/IEC 30107-3 terminology).

Convention: positive class = ATTACK (what PAD is trying to detect).
  TP = attack classified as attack      FN = attack classified as bona fide
  TN = bona fide classified bona fide   FP = bona fide classified as attack
APCER(species) = FN_species / attacks_species     (per attack type, PAI species)
BPCER          = FP / bona_fide
ACER           = (max_species APCER + BPCER) / 2  (OULU-NPU protocol convention)
"""
from __future__ import annotations

BONA_FIDE = "BONA_FIDE"


def pad_metrics(samples: list[dict]) -> dict:
    """samples: [{"category": str, "is_live": bool}] -> metrics dict."""
    bona = [s for s in samples if s["category"] == BONA_FIDE]
    attacks = [s for s in samples if s["category"] != BONA_FIDE]
    tp = sum(not s["is_live"] for s in attacks)
    fn = sum(s["is_live"] for s in attacks)
    tn = sum(s["is_live"] for s in bona)
    fp = sum(not s["is_live"] for s in bona)
    per_species = {}
    for cat in sorted({s["category"] for s in attacks}):
        group = [s for s in attacks if s["category"] == cat]
        per_species[cat] = {"n": len(group), "accepted_as_live": sum(s["is_live"] for s in group),
                            "apcer": sum(s["is_live"] for s in group) / len(group)}
    bpcer = fp / len(bona) if bona else None
    max_apcer = max((v["apcer"] for v in per_species.values()), default=None)
    acer = (max_apcer + bpcer) / 2 if bpcer is not None and max_apcer is not None else None
    return {"TP": tp, "TN": tn, "FP": fp, "FN": fn, "n_bona_fide": len(bona), "n_attack": len(attacks),
            "BPCER": bpcer, "APCER_per_species": per_species, "APCER_max": max_apcer,
            "APCER_overall": fn / len(attacks) if attacks else None, "ACER": acer}
