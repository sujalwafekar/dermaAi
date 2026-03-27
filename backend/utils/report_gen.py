"""
PDF report generator for DermaAI.
Uses fpdf2 to produce a clean, multi-page clinical summary.
"""
from fpdf import FPDF, XPos, YPos
from datetime import datetime
import base64
import io
import tempfile
import os


RISK_COLOR = {
    "Low":    (34, 197, 94),    # green
    "Medium": (234, 179,  8),   # amber
    "High":   (239, 68,  68),   # red
}

DISCLAIMER = (
    "DISCLAIMER: DermaAI is an AI-assisted screening tool for informational "
    "purposes only. It is NOT a substitute for professional medical diagnosis. "
    "Always consult a certified dermatologist for clinical evaluation and "
    "treatment guidance."
)

STATIC_NOTES = {
    "Low": (
        "The analyzed skin region shows minimal irregular patterns. "
        "No significant risk indicators were detected. Continue regular "
        "self-monitoring and annual dermatologist check-ups."
    ),
    "Medium": (
        "Moderate risk patterns were detected in the highlighted region. "
        "Some irregular pigmentation or texture may be present. A professional "
        "dermatologist consultation within 2-4 weeks is recommended."
    ),
    "High": (
        "Significant risk indicators detected in the highlighted region. "
        "Irregular borders, color variation, or asymmetry may be present. "
        "Please consult a dermatologist as soon as possible for a clinical evaluation."
    ),
}


class DermaReport(FPDF):
    def header(self):
        self.set_fill_color(15, 20, 40)
        self.rect(0, 0, 210, 28, "F")
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(100, 220, 255)
        self.set_y(7)
        self.cell(0, 10, "DermaAI  -  Skin Risk Analysis Report", align="C")
        self.set_text_color(150, 160, 180)
        self.set_font("Helvetica", "", 8)
        self.set_y(18)
        self.cell(0, 5, f"Generated: {datetime.now().strftime('%B %d, %Y  %H:%M')}", align="C")
        self.ln(14)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(200, 210, 230)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "I", 6.5)
        self.set_text_color(120, 130, 150)
        self.multi_cell(0, 4, DISCLAIMER, align="C")

    def section_header(self, title: str):
        """Draw a full-width section header bar."""
        self.set_fill_color(20, 30, 60)
        self.set_text_color(100, 220, 255)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, f"  {title}", align="L", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def section_row(self, label: str, value: str):
        """Draw a label + value row."""
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(60, 70, 100)
        self.cell(45, 6, label + ":", new_x=XPos.RIGHT, new_y=YPos.LAST)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 60)
        self.multi_cell(0, 6, value, align="L")


def b64_to_temp_png(b64_str: str) -> str:
    data = base64.b64decode(b64_str)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name


def generate_report(
    risk_level: str,
    confidence: float,
    heatmap_b64: str,
    original_b64: str,
    ai_insights: dict = None,
    prediction: str = "",
    urgency: str = "",
    advice: str = "",
) -> bytes:
    """
    Generate a PDF report and return raw bytes.
    ai_insights: optional dict with keys:
        condition_description, risk_explanation, next_steps, lifestyle_advice
    """
    pdf = DermaReport(orientation="P", unit="mm", format="A4")
    # Leave 22mm at bottom for footer
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    # ── Risk badge ─────────────────────────────────────────────────────────
    r, g, b = RISK_COLOR.get(risk_level, (100, 100, 100))
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 16, f"Risk Level:  {risk_level.upper()}", align="C", fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ── Quick stats row ────────────────────────────────────────────────────
    pdf.set_text_color(30, 30, 60)
    conf_pct = round(confidence * 100, 1)

    # Left: Confidence | Right: Prediction
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(235, 240, 255)
    pdf.cell(93, 9, f"Confidence:  {conf_pct}%", align="C", fill=True,
             new_x=XPos.RIGHT, new_y=YPos.LAST)
    pdf.cell(4, 9, "", new_x=XPos.RIGHT, new_y=YPos.LAST)  # spacer
    if prediction:
        pdf.cell(93, 9, f"Detected:  {prediction}", align="C", fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(93, 9, "", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # ── Separator ──────────────────────────────────────────────────────────
    pdf.set_draw_color(200, 210, 230)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(5)

    # ── Images: original + heatmap ─────────────────────────────────────────
    orig_path = b64_to_temp_png(original_b64) if original_b64 else None
    heat_path = b64_to_temp_png(heatmap_b64) if heatmap_b64 else None

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(60, 70, 90)
    pdf.set_x(15)
    pdf.cell(88, 5, "Original Image", align="C", new_x=XPos.RIGHT, new_y=YPos.LAST)
    pdf.set_x(107)
    pdf.cell(88, 5, "Grad-CAM Heatmap", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    img_y = pdf.get_y()
    if orig_path:
        pdf.image(orig_path, x=15, y=img_y, w=88, h=72)
        os.unlink(orig_path)
    if heat_path:
        pdf.image(heat_path, x=107, y=img_y, w=88, h=72)
        os.unlink(heat_path)
    else:
        # Draw placeholder box when heatmap isn't ready
        pdf.set_fill_color(230, 235, 245)
        pdf.rect(107, img_y, 88, 72, "F")
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(150, 160, 180)
        pdf.set_xy(107, img_y + 32)
        pdf.cell(88, 6, "Heatmap not available", align="C")

    pdf.set_y(img_y + 76)
    pdf.ln(4)

    # ── Confidence bar ─────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(60, 70, 90)
    pdf.cell(0, 5, "Risk Confidence Scale", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    bar_x = 30
    bar_w = 150
    bar_h = 7
    bar_y = pdf.get_y()

    # Gradient bar
    segments = 100
    for i in range(segments):
        ratio = i / segments
        rv = int(34  + (239 - 34)  * ratio)
        gv = int(197 + (68  - 197) * ratio)
        bv = int(94  + (68  - 94)  * ratio)
        pdf.set_fill_color(rv, gv, bv)
        pdf.rect(bar_x + (bar_w * i / segments), bar_y, bar_w / segments + 0.2, bar_h, "F")

    # White cursor marker
    marker_x = bar_x + bar_w * min(max(confidence, 0.0), 1.0)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(marker_x - 1, bar_y - 2, 2, bar_h + 4, "F")

    # -- Labels row (fixed Y below bar, no cursor conflict) --
    label_y = bar_y + bar_h + 2

    # "Low Risk" left label
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(34, 197, 94)
    pdf.set_xy(bar_x, label_y)
    pdf.cell(30, 4, "Low Risk", align="L")

    # "High Risk" right label
    pdf.set_text_color(239, 68, 68)
    pdf.set_xy(bar_x + bar_w - 28, label_y)
    pdf.cell(28, 4, "High Risk", align="R")

    # Confidence % -- positioned above bar slightly to avoid collision
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(30, 30, 60)
    # Clamp marker label to stay within page
    label_lx = min(max(marker_x - 8, bar_x), bar_x + bar_w - 16)
    pdf.set_xy(label_lx, bar_y - 6)
    pdf.cell(16, 5, f"{conf_pct}%", align="C")

    # Move cursor past everything
    pdf.set_y(label_y + 8)
    pdf.ln(4)

    # ── Separator ──────────────────────────────────────────────────────────
    pdf.set_draw_color(200, 210, 230)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(5)

    # ── Analysis Summary ───────────────────────────────────────────────────
    pdf.section_header("Analysis Summary")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(50, 60, 80)
    summary_text = STATIC_NOTES.get(risk_level, "")
    pdf.multi_cell(0, 6, summary_text, align="L")
    pdf.ln(3)

    if urgency:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(r, g, b)
        pdf.cell(0, 6, f"Urgency:  {urgency}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    if advice:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(60, 70, 100)
        pdf.multi_cell(0, 6, f"Clinical Advice:  {advice}", align="L")
    pdf.ln(4)

    # ── AI Clinical Analysis (if available) ────────────────────────────────
    if ai_insights and isinstance(ai_insights, dict):
        # May start on a new page if content pushed us there
        pdf.set_draw_color(200, 210, 230)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(5)
        pdf.section_header("AI Clinical Analysis  (Powered by Gemini)")

        sections = [
            ("Condition Description",  ai_insights.get("condition_description", "")),
            ("Risk Explanation",        ai_insights.get("risk_explanation", "")),
            ("Recommended Next Steps",  ai_insights.get("next_steps", "")),
            ("Lifestyle & Prevention",  ai_insights.get("lifestyle_advice", "")),
        ]

        for section_title, content in sections:
            if not content:
                continue
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(15, 20, 40)
            pdf.cell(0, 6, section_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(50, 60, 80)
            pdf.multi_cell(0, 5.5, content, align="L")
            pdf.ln(4)

    # Return bytes
    return bytes(pdf.output())
