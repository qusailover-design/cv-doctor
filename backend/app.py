# app.py — detailed ATS-grade analysis + CV enhancement endpoint
import os, io, json, re
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import PyPDF2
from docx import Document

load_dotenv()

# --- Gemini setup ---
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")
except Exception as e:
    print(f"FATAL: Could not configure GenerativeModel. Is GOOGLE_API_KEY set? Error: {e}")
    model = None

app = Flask(__name__)
CORS(app)  # allow Netlify origin; simple for now

# ---------- Helpers ----------
def extract_text_from_pdf(file_stream: io.BytesIO) -> str:
    try:
        reader = PyPDF2.PdfReader(file_stream)
        pages = []
        for p in reader.pages:
            try:
                t = p.extract_text() or ""
                pages.append(t)
            except Exception:
                continue
        return "\n".join(pages).strip()
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def extract_text_from_docx(file_stream: io.BytesIO) -> str:
    try:
        doc = Document(file_stream)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return ""

def read_cv_text_from_request(files, filename) -> str:
    file_stream = io.BytesIO(files.read())
    if filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(file_stream)
    if filename.lower().endswith(".docx"):
        return extract_text_from_docx(file_stream)
    return ""

def best_effort_json(text: str):
    """Pull the first {...} JSON object out of an LLM response."""
    if not text:
        raise ValueError("Empty model response")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    candidate = text[start:end + 1]
    return json.loads(candidate)

# ---------- Prompts ----------
def analysis_prompt(cv_text: str, lang: str) -> str:
    if lang == "ar":
        return f"""
أنت خبير توظيف وATS. حلّل السيرة الذاتية التالية بدقة كبيرة وأعد JSON صالحاً فقط.

قم بالإرجاع كائن JSON واحد بالمفاتيح الآتية (بدقة):
- overall_score: عدد صحيح 0..100
- ats_score: عدد صحيح 0..100
- readability_score: عدد صحيح 0..100
- summary: نص موجز يصف الملف المهني
- section_scores: كائن به مفاتيح [header, summary, experience, skills, education, projects] كل قيمة 0..100
- keyword_analysis: كائن يحتوي:
    - present: مصفوفة كلمات موجودة
    - missing: مصفوفة كلمات ناقصة
    - density_comment: نص تعليقي قصير
- gaps: مصفوفة قضايا أو ثغرات
- achievements_to_quantify: مصفوفة إنجازات تحتاج أرقام
- red_flags: مصفوفة (إن وجدت) وإلا مصفوفة فارغة
- suggestions: مصفوفة من 4 إلى 7 نصائح بسيطة قابلة للتنفيذ (سلاسل نصية فقط)

نص السيرة الذاتية:
---
{cv_text}
---"""
    else:
        return f"""
You are an ATS and recruiting expert. Analyze the CV below and return a SINGLE valid JSON object.

Return exactly these keys:
- overall_score: integer 0..100
- ats_score: integer 0..100
- readability_score: integer 0..100
- summary: concise string
- section_scores: object with keys [header, summary, experience, skills, education, projects], values 0..100
- keyword_analysis: object with:
    - present: array of strings
    - missing: array of strings
    - density_comment: string
- gaps: array of strings
- achievements_to_quantify: array of strings
- red_flags: array of strings (empty if none)
- suggestions: array of 4–7 simple strings (each is a single suggestion)

CV TEXT:
---
{cv_text}
---"""

def enhance_prompt(cv_text: str, lang: str, target_role: str, job_desc: str, tone: str, template_style: str) -> str:
    base = f"""
You are a career coach and expert résumé writer. Rewrite the CV to be ATS-friendly,
quantified, and aligned to the target role.

Constraints:
- One column ATS layout, clear section headings
- Bullet points follow STAR and include metrics where reasonable
- Keep content truthful; infer only phrasing, not fake facts
- Language: {"Arabic" if lang=="ar" else "English"}
- Tone: {tone or "Professional and concise"}
- Template style: {template_style or "Modern-ATS"}

Inputs:
TARGET ROLE: {target_role or "General"}
JOB DESCRIPTION (optional): {job_desc or "N/A"}
CURRENT CV:
---
{cv_text}
---

Return ONLY a JSON object with:
- title: string (document title)
- summary: string (re-written professional summary)
- keywords: array of strings (role-aligned)
- sections: object with keys: Contact, Summary, Experience, Skills, Education, Projects, Certifications (omit a key if not applicable)
  Where Experience is an array of objects: role, company, period, location (optional), bullets (array of strings)
- enhanced_cv_md: a single Markdown string containing the full CV, ready to render (use headings, bold, lists)
"""
    return base

# ---------- Routes ----------
@app.route("/api/analyze", methods=["POST"])
def analyze_cv():
    if model is None:
        return jsonify({"error": "AI model is not configured on the server."}), 500

    if "cv" not in request.files:
        return jsonify({"error": "No file part"}), 400

    lang = request.form.get("lang", "en")
    file = request.files["cv"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    cv_text = read_cv_text_from_request(file, file.filename)
    if not cv_text or len(cv_text) < 50:
        return jsonify({"error": "Could not extract sufficient text."}), 400

    try:
        prompt = analysis_prompt(cv_text, lang)
        resp = model.generate_content(prompt)
        parsed = best_effort_json(resp.text)

        # Maintain backward-compat fields your frontend already uses:
        # - overall_score
        # - summary
        # - suggestions
        # - keyword_analysis (string in old version). We’ll keep object and also add a string fallback.
        if isinstance(parsed.get("keyword_analysis"), dict):
            ka = parsed["keyword_analysis"]
            parsed["keyword_analysis_text"] = (
                f'Present: {", ".join(ka.get("present", []))} | '
                f'Missing: {", ".join(ka.get("missing", []))} | '
                f'{ka.get("density_comment","")}'
            )

        return jsonify(parsed)
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        return jsonify({"error": "AI analysis failed."}), 500

@app.route("/api/enhance", methods=["POST"])
def enhance_cv():
    if model is None:
        return jsonify({"error": "AI model is not configured on the server."}), 500

    if "cv" not in request.files:
        return jsonify({"error": "No file part"}), 400

    lang = request.form.get("lang", "en")
    target_role = request.form.get("target_role", "")
    job_desc = request.form.get("job_desc", "")
    tone = request.form.get("tone", "Professional and concise")
    template_style = request.form.get("template_style", "Modern-ATS")

    file = request.files["cv"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    cv_text = read_cv_text_from_request(file, file.filename)
    if not cv_text or len(cv_text) < 50:
        return jsonify({"error": "Could not extract sufficient text."}), 400

    try:
        prompt = enhance_prompt(cv_text, lang, target_role, job_desc, tone, template_style)
        resp = model.generate_content(prompt)
        parsed = best_effort_json(resp.text)

        # guard fields expected by frontend
        if "enhanced_cv_md" not in parsed:
            raise ValueError("Missing 'enhanced_cv_md' in model output")

        # Suggest a default filename
        parsed.setdefault("file_name", "Careeri_Enhanced_CV.pdf")
        return jsonify(parsed)
    except Exception as e:
        print(f"Enhancement error: {e}")
        return jsonify({"error": "AI enhancement failed."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
