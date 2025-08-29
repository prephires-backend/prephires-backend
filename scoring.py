# scoring.py
import re
from typing import Dict

# Lightweight keyword bank (can extend anytime)
GLOBAL_KEYWORDS = [
    "leadership","team","strategy","growth","product","sales","marketing",
    "innovation","ai","data","analysis","management","customer","results",
    "experience","expert","stakeholder","project","revenue","kpi","okr",
    "python","sql","excel","communication","collaboration","problem solving"
]

def clean(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "")).strip()

def keyword_analysis(text: str) -> Dict:
    low = (text or "").lower()
    found = sorted({k for k in GLOBAL_KEYWORDS if k in low})
    score = round(100 * len(found) / len(GLOBAL_KEYWORDS)) if GLOBAL_KEYWORDS else 0
    return {
        "score": score,
        "found": found[:10],
        "total": len(GLOBAL_KEYWORDS)
    }

def section_score(text: str, min_len=40) -> int:
    """
    Very simple, transparent scoring:
    - length coverage (how substantive the section is)
    - basic signal words (action/results)
    """
    t = clean(text)
    if not t:
        return 0
    L = len(t)
    coverage = min(1.0, L / (min_len * 4))  # saturate after ~160 chars
    signals = sum(w in t.lower() for w in ["lead", "deliver", "improve", "increase",
                                           "optimize", "achieve", "reduced", "built",
                                           "launched", "managed", "results"])
    signal_ratio = min(1.0, signals / 5.0)
    raw = 60*coverage + 40*signal_ratio
    return max(0, min(100, round(raw)))

def overall_from_subs(subs: Dict[str, int], kw_bonus: int) -> int:
    weights = {"headline": 0.25, "about": 0.25, "experience": 0.35, "skills": 0.15}
    base = sum(subs.get(k,0)*w for k,w in weights.items())
    bonus = min(5, kw_bonus/10)   # tiny bump for keywords (max +5)
    return max(0, min(100, round(base + bonus)))

def score_profile(fields: Dict) -> Dict:
    headline   = fields.get("headline","")
    about      = fields.get("about","")
    experience = fields.get("experience","")
    skills     = fields.get("skills","")

    # Section scores
    sub_scores = {
        "headline":   section_score(headline,   min_len=20),
        "about":      section_score(about,      min_len=80),
        "experience": section_score(experience, min_len=120),
        "skills":     section_score(skills,     min_len=10),
    }

    # Keyword analysis (uses all text together)
    all_text = " ".join([headline, about, experience, skills])
    kw = keyword_analysis(all_text)

    overall = overall_from_subs(sub_scores, kw["score"])

    return {
        "overall_score": overall,
        "sub_scores": sub_scores,
        "keyword_analysis": kw,
        "version": "0.2.1",
    }
