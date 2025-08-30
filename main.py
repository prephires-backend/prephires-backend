# main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PyPDF2 import PdfReader
import io, time

# if you have scoring.py in repo, else comment this out
from scoring import score_profile  

app = FastAPI()

# ✅ Robust but safe CORS: only allow your real domains
ALLOWED = [
    "https://www.prephires.com",
    "https://prephires.com",
    "https://*.hostinger.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
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
    return {"status": "ok", "version": "0.2.1"}

@app.post("/analyze")
def analyze(payload: AnalyzeReq):
    """Analyze pasted text fields"""
    t0 = time.time()
    try:
        data = score_profile(payload.dict())
    except Exception as e:
        return {"error": str(e)}
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return data

@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    """Analyze LinkedIn profile PDF"""
    try:
        content = file.file.read()
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        all_text = "\n".join(pages)

        fields = {
            "headline": "",
            "about": all_text[:1500],
            "experience": all_text[:4000],
            "skills": all_text[-1500:]
        }
        t0 = time.time()
        data = score_profile(fields)
        data["latency_ms"] = int((time.time() - t0) * 1000)
        data["_source"] = "pdf"
        return data
    except Exception as e:
        return {"error": f"PDF parse failed: {str(e)}"}

