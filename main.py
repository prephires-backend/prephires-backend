# main.py  (NO screenshot endpoint)
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import io, time, logging

from scoring import score_profile

app = FastAPI()
log = logging.getLogger("prephires")
logging.basicConfig(level=logging.INFO)

# Strict + safe CORS for your domains (no "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.prephires.com", "https://prephires.com"],
    allow_origin_regex=r"https://.*\.hostinger\.com",
    allow_credentials=True,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["*"],
)

class AnalyzeReq(BaseModel):
    headline: str = ""
    about: str = ""
    experience: str = ""
    education: str = ""
    skills: str = ""
    certs: str = ""
    recommendations: str = ""

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.3"}

@app.post("/analyze")
def analyze(payload: AnalyzeReq):
    t0 = time.time()
    data = score_profile(payload.model_dump())
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return data

# ---------- Robust PDF text extraction ----------
def extract_text_from_pdf(content: bytes) -> str:
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            chunks = []
            for pg in pdf.pages:
                try:
                    chunks.append(pg.extract_text() or "")
                except Exception:
                    chunks.append("")
            text = "\n".join(chunks).strip()
    except Exception as e:
        log.warning(f"pdfplumber failed: {e}")

    if not text:
        try:
            from PyPDF2 import PdfReader
            rd = PdfReader(io.BytesIO(content))
            chunks = []
            for pg in rd.pages:
                try:
                    chunks.append(pg.extract_text() or "")
                except Exception:
                    chunks.append("")
            text = "\n".join(chunks).strip()
        except Exception as e:
            log.warning(f"PyPDF2 failed: {e}")

    return text or ""

@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    t0 = time.time()
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload")

    all_text = extract_text_from_pdf(content)
    log.info(f"PDF bytes={len(content)}, extracted_chars={len(all_text)}")

    if len(all_text) < 40:
        # Return a clear note so the frontend can show it
        data = score_profile({"headline":"","about":"","experience":"","skills":""})
        data["_source"] = "pdf"
        data["latency_ms"] = int((time.time() - t0) * 1000)
        data["_note"] = "No extractable text found in PDF (likely image-only). Please paste text or export the LinkedIn PDF directly from the browser."
        return data

    fields = {
        "headline": "",
        "about": all_text[:2000],
        "experience": all_text[:6000],
        "skills": all_text[-2000:]
    }
    data = score_profile(fields)
    data["_source"] = "pdf"
    data["latency_ms"] = int((time.time() - t0) * 1000)
    return data
