# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PyPDF2 import PdfReader
from playwright.async_api import async_playwright
import io, time

from scoring import score_profile

app = FastAPI()

# ---- Safer CORS ----
ALLOWED = [
    "https://www.prephires.com",
    "https://prephires.com",
    "https://*.hostinger.com",
    "*"  # keep for testing only, remove later
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_credentials=False,  # ✅ must be False if "*" is in list
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Data model ----
class AnalyzeReq(BaseModel):
    headline: str = ""
    about: str = ""
    experience: str = ""
    education: str = ""
    skills: str = ""
    certs: str = ""
    recommendations: str = ""

# ---- Healthcheck ----
@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}

# ---- Text analysis ----
@app.post("/analyze")
def analyze(payload: AnalyzeReq):
    t0 = time.time()
    data = score_profile(payload.dict())
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return data

# ---- Robust PDF analysis ----
MAX_PDF_BYTES = 15 * 1024 * 1024  # 15 MB

def _safe_read_pdf(file: UploadFile) -> bytes:
    b = file.file.read()
    if not b:
        raise HTTPException(status_code=400, detail="Empty PDF file.")
    if len(b) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large. Limit 15 MB.")
    return b

def _extract_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open PDF: {e}")
    text_chunks, any_text = [], False
    for page in getattr(reader, "pages", []):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        text_chunks.append(txt)
        if txt.strip():
            any_text = True
    if not any_text:
        raise HTTPException(status_code=422, detail="No text extracted (PDF may be image-only).")
    return "\n".join(text_chunks)

@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    t0 = time.time()
    pdf_bytes = _safe_read_pdf(file)
    all_text = _extract_text(pdf_bytes)

    fields = {
        "headline": "",
        "about": all_text[:2000],
        "experience": all_text[:6000],
        "skills": all_text[-2000:],
        "raw_text": all_text,
    }

    data = score_profile(fields)
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "pdf"

    # Add keyword analysis if missing
    if "keyword_analysis" not in data:
        kws = ["leadership","team","strategy","growth","product","sales","marketing",
               "innovation","ai","data","analysis","management","customer","results",
               "experience","expert","stakeholder","project"]
        lower = all_text.lower()
        found = [k for k in kws if k in lower]
        data["keyword_analysis"] = {
            "score": round(len(found)/len(kws)*100),
            "found": found[:6],
            "total": len(kws)
        }
    return data

# ---- LinkedIn Screenshot (Playwright) ----
@app.get("/screenshot")
async def screenshot_linkedin(url: str):
    """
    Capture screenshot of LinkedIn profile.
    Needs: playwright install --with-deps chromium
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=30000)
        path = "screenshot.png"
        await page.screenshot(path=path, full_page=True)
        await browser.close()
        return FileResponse(path, media_type="image/png")
