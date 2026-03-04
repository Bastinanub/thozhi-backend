from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.services.pdf import generate_pdf

router = APIRouter()   # ✅ THIS WAS MISSING


class ReportPayload(BaseModel):
    domain: str
    tool_used: str
    score: int
    interpretation: str
    summary: str
    recommendation: str
    disclaimer: str
    generated_at: str


@router.post("/generate-pdf")
def generate_report_pdf(report: ReportPayload):
    filename = "thozhi_report.pdf"
    path = generate_pdf(report.dict(), filename)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename
    )
