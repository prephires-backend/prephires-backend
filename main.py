# main.py
import io
import os
import time
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import pdfplumber  # <- reliable PDF text extraction
# from PyPDF2 import PdfReader  # (not used anymore)

from scoring import score_profile

# -----------------------------------------------------------------------------
# App + CORS (robust & safe)
# -----------------------------------------------------------------------------
app = FastAPI(title="PrepHires Optimizer API", version="0.3.0")

# You can override allowed origins with an env var:
# ALLOWED_ORIGINS="https://www.prephires.com,https://prephires.com"
_env_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
ALLOWED = [o.strip() for o in _env_origins.split(",") if o.strip()] or [
    "https://www.prephires.com",
    "https://prephires.com",
]
# Allow common preview/subdomains via regex (CORS supports either list OR regex)
# If you host on Hostinger or use subdomains, this keeps you covered.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED if ALLOWED else [],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(prephires\.com|hostinger\.com)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class AnalyzeReq(BaseModel):
    headline: str = ""
    about: str = ""
    experience: str = ""
    education: str = ""
    skills: str = ""
    certs: str = ""
    recommendations: str = ""

# -----------------------------------------------------------------------------
# Global JSON error handler (frontend always gets JSON, never HTML)
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}

# -----------------------------------------------------------------------------
# Text Analyze
# -----------------------------------------------------------------------------
@app.post("/analyze")
def analyze(payload: AnalyzeReq):
    t0 = time.time()
    data = score_profile(payload.dict())
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "text"
    return data

# -----------------------------------------------------------------------------
# PDF Analyze (uses pdfplumber; returns real text for most PDFs)
# -----------------------------------------------------------------------------
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB safety cap

@app.post("/analyze_pdf")
def analyze_pdf(file: UploadFile = File(...)):
    # Guard: basic size cap (if Content-Length is missing, we still read but limit below)
    raw = file.file.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large (max 20MB).")

    # Extract text with pdfplumber
    all_text = ""
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                all_text += page.extract_text() or ""
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {e}")

    if not all_text.strip():
        # Return JSON with graceful message so frontend doesn't show 0s silently
        return {
            "error": "Could not extract text from PDF (try exporting again from LinkedIn).",
            "overall_score": 0,
            "sub_scores": {"headline": 0, "about": 0, "experience": 0, "skills": 0},
            "_source": "pdf",
            "latency_ms": 0,
            "version": app.version,
        }

    # Simple slicing – your scoring works on whole text anyway
    fields = {
        "headline": "",
        "about": all_text[:1500],
        "experience": all_text[:4000],
        "skills": all_text[-1500:],
    }

    t0 = time.time()
    data = score_profile(fields)
    data["latency_ms"] = int((time.time() - t0) * 1000)
    data["_source"] = "pdf"
    return data

# -----------------------------------------------------------------------------
# Optional: LinkedIn screenshot endpoint (requires Playwright + Chromium)
# Enable with env var ENABLE_SCREENSHOT=1
# Build step should have: `pip install -r requirements.txt && playwright install --with-deps chromium`
# -----------------------------------------------------------------------------
ENABLE_SCREENSHOT = os.getenv("ENABLE_SCREENSHOT", "1") in ("1", "true", "True")

try:
    from playwright.async_api import async_playwright  # type: ignore
except Exception:  # Playwright not installed – keep API but return 501
    async_playwright = None

@app.get("/screenshot")
async def screenshot_linkedin(url: str):
    if not ENABLE_SCREENSHOT or async_playwright is None:
        raise HTTPException(status_code=501, detail="Screenshot service not enabled.")

    # Very light input validation
    if "linkedin.com/in/" not in url:
        raise HTTPException(status_code=400, detail="Only LinkedIn profile URLs are allowed.")

    # Use a temp file so multiple requests won't clash
    with NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = tmp.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],  # Render compatibility
            )
            page = await browser.new_page(viewport={"width": 1200, "height": 900})
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Capture visible area (faster than full page)
            await page.screenshot(path=png_path, full_page=False)
            await browser.close()
        return FileResponse(png_path, media_type="image/png")
    except Exception as e:
        # Clean up temp file on failure
        try:
            if os.path.exists(png_path):
                os.remove(png_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {e}")
# --- optional screenshot endpoint (won't break deploys if Playwright is missing) ---
from fastapi import HTTPException

@app.get("/screenshot")
async def screenshot_linkedin(url: str):
    """
    Optional: takes a screenshot of the given LinkedIn profile URL.
    If Playwright isn't installed, return 501 so frontend can hide the image.
    """
    try:
        from playwright.async_api import async_playwright  # lazy import
    except Exception:
        # Playwright not available; keep API healthy
        raise HTTPException(status_code=501, detail="Screenshot service not enabled")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            path = "screenshot.png"
            await page.screenshot(path=path, full_page=True)
            await browser.close()
            from fastapi.responses import FileResponse
            return FileResponse(path, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screenshot error: {e}")

