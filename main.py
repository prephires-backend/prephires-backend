# main.py  — FastAPI backend for PrepHires Optimizer
import os, time, math
from typing import Optional, Dict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Try to use your scoring.py if present; otherwise fall back to a simple scorer
def _simple_score(text: str) -> Dict[str, float]:
    """Very simple fallback scoring so the API always works.
       If you have scoring.py, we'll use that instead (see try/except below)."""
    text = (text or "").lower()
    length_score = min(100, len(text) / 20)                    # more content => higher
    keyword_hits = sum(text.count(k) for k in
                       ["linkedin", "experience", "about", "skills",
                        "achieved", "increased", "reduced", "built",
                        "marketing", "sales", "engineering", "hr"])
    keyword_score = min(100, keyword_hits * 12)
    structure_score = 100 if any(h in text for h in ["about", "experience", "education"]) else 40
    overall = round(0.45*length_score + 0.35*keyword_score + 0.20*structure_score, 1)
    return {
        "overall": max(0, min(100, overall)),
        "subs": {
            "headline": max(30.0, min(100.0, length_score)),
            "about": max(30.0, min(100.0, keyword_score)),
            "experience": max(30.0, min(100.0, structure_score)),
            "skills": max(30.0, min(100.0, keyword_score * 0.9)),
        }
    }

try:
    # If your repo has scoring.py with a function score(text)->(overall, subdict), use it.
    from scoring import score as ph_score  # adjust if your function is named differently
    def SCORE_ENGINE(text: str):
        ov, subs = ph_score(text)
        return {"overall": ov, "subs": subs}
except Exception:
    # Fallback
    def SCORE_ENGINE(text: str):
        return _simple_score(text)

# --------- FastAPI app + CORS ----------
app = FastAPI(title="PrepHires Optimizer", version="0.2.0")

ALLOWED_ORIGINS = [
    "https://prephires.com",
    "https://www.prephires.com",
    # add any staging/editor domains here if you test from them:
    # "https://*.hostinger.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # for quick testing you can use ["*"], then tighten later
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Models ----------
class ProfilePayload(BaseModel):
    headline: Optional[str] = ""
    about: Optional[str] = ""
    experience: Optional[str] = ""
    education: Optional[str] = ""
    skills: Optional[str] = ""
    certs: Optional[str] = ""
    recommendations: Optional[str] = ""

# --------- Routes ----------
@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}

@app.post("/analyze")
def analyze(payload: ProfilePayload):
    start = time.time()
    text = "\n\n".join([
        payload.headline or "",
        payload.about or "",
        payload.experience or "",
        payload.education or "",
        payload.skills or "",
        payload.certs or "",
        payload.recommendations or "",
    ])
    res = SCORE_ENGINE(text)
    return {
        "overall_score": res["overall"],
        "sub_scores": res["subs"],
        "version": app.version,
        "latency_ms": int((time.time() - start) * 1000),
    }

@app.post("/analyze_pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    start = time.time()
    try:
        from PyPDF2 import PdfReader
        import io
        content = await file.read()
        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            txt = page.extract_text() or ""
            text += txt + "\n"
        if not text.strip():
            raise ValueError("Could not extract text from PDF (image-only or empty).")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF read error: {e}")

    res = SCORE_ENGINE(text)
    return {
        "overall_score": res["overall"],
        "sub_scores": res["subs"],
        "version": app.version,
        "latency_ms": int((time.time() - start) * 1000),
    }

