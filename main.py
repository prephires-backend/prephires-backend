# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import io, time

# --- PDF libs (two paths; we try pdfplumber first, then PyPDF2) ---
import pdfplumber
from PyPDF2 import PdfReader

# --- Try to use your existing scoring.py; fall back to a simple scorer if missing ---
try:
    from scoring import score_profile as _score_profile
except Exception:
    def _score_profile(fields: dict):
        # Fallback heuristic so backend never crashes if scoring.py is absent
        txt = " ".join([
            fields.get("headline",""), fields.get("about",""),
            fields.get("experience",""), fields.get("skills","")
        ]).lower()

        # naive subs
        def clamp(x): return max(0, min(100, int(x)))
        head = clamp(30 + (10 if len(fields.get("headline","")) > 20 else 0))
        about = clamp(40 + min(len(fields.get("about","")) // 60, 40))
        exp   = clamp(35 + min(len(fields.get("experience","")) // 100, 50))
        skills= clamp(30 + min(len(fields.get("skills","")) // 25, 55))

        # simple keyword sniff
        base_kw = ["leadership","team","strategy","growth","product","sales",
                   "marketing","innovation","ai","data","analysis","management",
                   "customer","results","experience","stakeholder","project"]
        found = [k for k in base_kw if k in txt]
        kw_score = clamp(int(len(found) / max(1, len(base_kw)) * 100))

        overall = clamp(int((head+about+exp+skills)/4))
        return {
            "overall_score": overall,
            "sub_scores": {
                "headline": head,
                "about": about,
                "experience": exp,
                "skills": skills
            },
            "keyword_analysis": {
                "score": kw_score,
                "found": found[:6],
                "total": len(base_kw)
            },
            "version": "fallback-1.0"
        }

# ---------- FastAPI app ----------
app = FastAPI(title="PrepHires Backend", version="0.2.2")

# ---------- CORS (robust & safe) ----------
ALLOWED_ORIGINS = [
    "https://www.prephires.com",
    "https://prephires.com",
]
# allow *.hostinger.com via regex; no wildcard "*" in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.hostinger\.com",
    allow_credentials=False,        # keep false unless you really need cookies
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ---------- Models ----------
class AnalyzeReq(BaseModel):
    headline: str = ""
    about: str = ""
    experience: str = ""
    education: str = ""
    skills: str = ""
    certs: str = ""
    recommendations: str = ""

# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.2"}

# ---------- Analyze pasted text ----------
@app.post("/analyze")
def analyze(payload: AnalyzeReq):
    t0 = time.time()
    try:
        data = _score_profile(payload.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scoring_error: {e}")
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return JSONResponse(data)

# ---------- Analyze PDF (robust) ----------
@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    # 1) read content into memory
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty PDF")

    # 2) try pdfplumber first
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        text = ""

    # 3) fallback to PyPDF2 if needed
    if not text.strip():
        try:
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages:
                try:
                    text += (page.extract_text() or "") + "\n"
                except Exception:
                    pass
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF parse failed: {e}")

    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF. Try another file.")

    # 4) basic field splits (simple, safe)
    fields = {
        "headline": "",
        "about": text[:1500],
        "experience": text[:4000],
        "skills": text[-1500:]
    }

    # 5) score
    t0 = time.time()
    try:
        data = _score_profile(fields)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scoring_error: {e}")

    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "pdf"
    return JSONResponse(data)
