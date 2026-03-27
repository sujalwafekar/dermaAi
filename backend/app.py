"""
DermaAI — Flask Backend
========================
Endpoints:
  POST /api/analyze          → fast prediction (heatmap async via job_id)
  GET  /api/heatmap/<job_id> → poll for GradCAM heatmap
  GET  /api/dermatologists   → nearby dermatologist data
  POST /api/report           → generate + download PDF report
  POST /api/chat             → chatbot (Gemini → NVIDIA → Ollama fallback)
  GET  /                     → serve frontend index.html
"""

import os

# Disable torch dynamo/compiler — prevents torchvision import errors on some PyTorch versions
os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["TORCH_COMPILE_BACKEND"] = "eager"

import uuid
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from dotenv import load_dotenv

from model.model_loader import load_model, predict, CLASSES
from utils.gradcam import GradCAM, overlay_heatmap, image_to_b64
from utils.predictor import preprocess_image
from utils.report_gen import generate_report

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

ALLOWED_EXTENSIONS    = {"png", "jpg", "jpeg", "bmp", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # 10 MB

# ──────────────────────────────────────────────────────────────────────────────
# Load model once at startup
# ──────────────────────────────────────────────────────────────────────────────
print("⏳  Loading DenseNet121 skin-cancer model …")
model  = load_model()
device = next(model.parameters()).device
gradcam_engine = GradCAM(model)
print("✅  DenseNet121 model ready.")

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────────────────────────────────────
# Frontend serving
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ──────────────────────────────────────────────────────────────────────────────
# Async GradCAM  (background thread + poll endpoint)
# ──────────────────────────────────────────────────────────────────────────────
_heatmap_jobs: dict = {}   # job_id → { status, heatmap_b64 }

def _run_gradcam(job_id: str, tensor, pil_img, class_idx):
    try:
        tensor_grad = tensor.clone().requires_grad_(True)
        heatmap     = gradcam_engine.generate(tensor_grad, class_idx=class_idx)
        heatmap_b64 = overlay_heatmap(heatmap, pil_img)
        _heatmap_jobs[job_id] = {"status": "done", "heatmap_b64": heatmap_b64}
    except Exception as e:
        _heatmap_jobs[job_id] = {"status": "error", "error": str(e)}


@app.route("/api/heatmap/<job_id>", methods=["GET"])
def get_heatmap(job_id):
    """Frontend polls this until status == 'done'."""
    job = _heatmap_jobs.get(job_id)
    if not job:
        return jsonify({"status": "pending"}), 202
    return jsonify(job)


# ──────────────────────────────────────────────────────────────────────────────
# API: Analyze image  (fast — prediction only, heatmap is async)
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/analyze", methods=["POST"])
def analyze():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type. Use PNG, JPG, JPEG, BMP, or WEBP."}), 400

    try:
        file_bytes = file.read()

        # 1. Preprocess
        pil_img, tensor = preprocess_image(file_bytes)
        tensor = tensor.to(device)

        # 2. Fast prediction — no backward pass, sub-second
        result = predict(pil_img, model, device)

        # 3. Encode original image
        original_b64 = image_to_b64(pil_img)

        # 4. Kick off GradCAM in background (non-blocking)
        job_id    = str(uuid.uuid4())
        class_idx = CLASSES.index(result["prediction"]) if not result["is_uncertain"] else None
        _heatmap_jobs[job_id] = {"status": "pending"}
        threading.Thread(
            target=_run_gradcam,
            args=(job_id, tensor.detach(), pil_img, class_idx),
            daemon=True,
        ).start()

        # 5. Return prediction immediately
        return jsonify({
            "risk_level"     : result["risk_level"],
            "confidence"     : result["confidence"],
            "prediction"     : result["prediction"],
            "all_probs"      : result["all_probs"],
            "urgency"        : result["urgency"],
            "message"        : result["message"],
            "advice"         : result["advice"],
            "is_uncertain"   : result["is_uncertain"],
            "original_b64"   : original_b64,
            "heatmap_b64"    : None,      # arrives via polling
            "heatmap_job_id" : job_id,
        })

    except Exception as e:
        app.logger.exception("Error during analysis")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


# ──────────────────────────────────────────────────────────────────────────────
# API: Nearby dermatologists
# ──────────────────────────────────────────────────────────────────────────────
MOCK_DERMATOLOGISTS = [
    {
        "name": "Dr. Niteen Dhepe — Skin & Laser Clinic",
        "address": "301, Arenja Corner, Sector 17, Vashi, Navi Mumbai",
        "phone": "+91 22 2789 0000",
        "rating": 4.8, "distance": "1.2 km",
        "lat": 19.0748, "lng": 72.9980,
        "open": True, "specialty": "Dermatology & Cosmetology",
    },
    {
        "name": "Kokilaben Dhirubhai Ambani Hospital — Dermatology",
        "address": "Rao Saheb, Achutrao Patwardhan Marg, Andheri West, Mumbai",
        "phone": "+91 22 3066 1000",
        "rating": 4.7, "distance": "2.1 km",
        "lat": 19.1390, "lng": 72.8284,
        "open": True, "specialty": "Dermato-oncology",
    },
    {
        "name": "Lilavati Hospital — Skin Dept.",
        "address": "A-791, Bandra Reclamation, Bandra West, Mumbai 400050",
        "phone": "+91 22 2675 1000",
        "rating": 4.6, "distance": "3.0 km",
        "lat": 19.0544, "lng": 72.8310,
        "open": True, "specialty": "Skin Cancer & Biopsy",
    },
    {
        "name": "Breach Candy Hospital — Dermatology",
        "address": "60-A, Bhulabhai Desai Rd, Breach Candy, Mumbai 400026",
        "phone": "+91 22 2367 1888",
        "rating": 4.5, "distance": "3.8 km",
        "lat": 18.9677, "lng": 72.8076,
        "open": True, "specialty": "Clinical Dermatology",
    },
    {
        "name": "Hinduja Hospital — Skin & Cosmetology",
        "address": "Veer Savarkar Marg, Mahim West, Mumbai 400016",
        "phone": "+91 22 2445 2222",
        "rating": 4.6, "distance": "4.5 km",
        "lat": 19.0454, "lng": 72.8395,
        "open": True, "specialty": "Skin Screening & Mole Mapping",
    },
]


@app.route("/api/dermatologists", methods=["GET"])
def dermatologists():
    return jsonify({"results": MOCK_DERMATOLOGISTS})


# ──────────────────────────────────────────────────────────────────────────────
# API: Model status / debug (useful for verifying HF deployment)
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/model-status", methods=["GET"])
def model_status():
    """
    Returns current model health — hit this on Hugging Face to verify weights loaded.
    No auth needed; read-only; no PII.
    """
    import torch
    from model.model_loader import CLASSES

    status = {"ok": False, "classes": CLASSES}

    try:
        # Run a fresh sanity inference
        _noise = torch.rand(1, 3, 224, 224, device=device)
        with torch.no_grad():
            _probs = torch.softmax(model(_noise), dim=1)[0]
        all_probs = {cls: round(_probs[i].item(), 4) for i, cls in enumerate(CLASSES)}
        top_cls   = CLASSES[_probs.argmax().item()]
        top_p     = round(_probs.max().item(), 4)

        degenerate = (top_cls == "No Cancer" and top_p > 0.85)
        status.update({
            "ok"         : not degenerate,
            "warning"    : "Model predicts No Cancer with very high confidence on random noise — weights may not have loaded correctly." if degenerate else None,
            "noise_probs": all_probs,
            "noise_top"  : {"class": top_cls, "confidence": top_p},
        })
    except Exception as e:
        status["error"] = str(e)

    return jsonify(status), 200 if status["ok"] else 500


# ──────────────────────────────────────────────────────────────────────────────
# API: Generate PDF report
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/report", methods=["POST"])
def report():
    data = request.get_json(force=True)
    heatmap_b64  = data.get("heatmap_b64") or ""
    original_b64 = data.get("original_b64", "")

    for field in ["risk_level", "confidence", "original_b64"]:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        pdf_bytes = generate_report(
            risk_level   = data["risk_level"],
            confidence   = float(data["confidence"]),
            heatmap_b64  = heatmap_b64,
            original_b64 = original_b64,
            ai_insights  = data.get("ai_insights"),       # NEW
            prediction   = data.get("prediction", ""),    # NEW
            urgency      = data.get("urgency", ""),       # NEW
            advice       = data.get("advice", ""),        # NEW
        )

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "attachment; filename=DermaAI_Report.pdf"
        return response

    except Exception as e:
        app.logger.exception("Error generating report")
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500


# ──────────────────────────────────────────────────────────────────────────────
# API: AI Insights Enrichment  (Gemini structured clinical analysis)
# ──────────────────────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")


@app.route("/api/enrich", methods=["POST"])
def enrich():
    """Send model results to Gemini to get structured clinical insights."""
    data       = request.get_json(force=True)
    risk_level = data.get("risk_level", "Unknown")
    prediction = data.get("prediction", "Unknown")
    confidence = float(data.get("confidence", 0)) * 100

    prompt = f"""You are a clinical dermatology assistant AI. A patient's skin lesion image was analyzed by a deep learning model.

Model Results:
- Detected condition: {prediction}
- Risk level: {risk_level}
- Model confidence: {confidence:.1f}%

Provide a structured clinical response in JSON format with EXACTLY these 4 keys:
1. "condition_description": A 2-3 sentence plain-English description of what {prediction} is, its characteristics, and how common it is.
2. "risk_explanation": A 2-3 sentence explanation of what a {risk_level} risk level means clinically for this specific condition.
3. "next_steps": 3-4 specific, actionable clinical next steps the patient should take, as a single paragraph.
4. "lifestyle_advice": 2-3 specific lifestyle and prevention tips relevant to this condition (sun protection, self-exam frequency, etc.).

Return ONLY valid JSON — no markdown, no extra text, just the JSON object."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=25)
        if resp.status_code == 200:
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            import json as _json
            insights = _json.loads(raw)
            return jsonify({"insights": insights})
        app.logger.warning(f"Gemini enrich failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        app.logger.error(f"Enrich error: {e}")

    # Fallback — return None so frontend shows static notes
    return jsonify({"insights": None}), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    data         = request.get_json(force=True)
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    configs = [
        {
            "name": "Gemini",
            "url": f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
            "headers": {"Content-Type": "application/json"},
            "payload": {"contents": [{"parts": [{"text": user_message}]}]},
        },
        {
            "name": "NVIDIA NIM (Kimi)",
            "url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            "payload": {
                "model": "moonshotai/kimi-k2.5",
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": 16384, "temperature": 1.0, "top_p": 1.0,
            },
        },
        {
            "name": "Ollama",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}", "Content-Type": "application/json"},
            "payload": {
                "model": "deepseek/deepseek-r1:free",
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": 16384, "temperature": 1.0,
            },
        },
    ]

    for api in configs:
        app.logger.info(f"Attempting chat with: {api['name']}")
        try:
            resp = requests.post(api["url"], headers=api["headers"], json=api["payload"], timeout=30)
            if resp.status_code == 200:
                rj = resp.json()
                try:
                    if api["name"] == "Gemini":
                        reply = rj["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        reply = rj["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    reply = "Sorry, received an unexpected response format."
                return jsonify({"reply": reply, "provider": api["name"]})
            app.logger.warning(f"{api['name']} failed: {resp.status_code}")
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Connection error with {api['name']}: {e}")

    return jsonify({"error": "All AI providers failed. Please try again later."}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
