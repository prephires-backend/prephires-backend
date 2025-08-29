# main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PyPDF2 import PdfReader
import io, time

from scoring import score_profile

app = FastAPI()

# CORS: allow your site + preview in builder
ALLOWED = [
    "https://www.prephires.com",
    "https://prephires.com",
    "https://*.hostinger.com",
    "*",  # keep while testing; tighten later to your domains
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
    t0 = time.time()
    data = score_profile(payload.dict())
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return data

@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    # Extract text from PDF then score it
    content = file.file.read()
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    all_text = "\n".join(pages)

    # very simple heuristic split
    lower = all_text.lower()
    def chunk(key):
        return all_text if key not in lower else all_text  # keep simple; scoring uses whole anyway

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
