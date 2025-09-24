
# app.py - The final, stable, high-quality analysis version.
import os
import io
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import PyPDF2
from docx import Document

load_dotenv()

try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
except Exception as e:
    print(f"FATAL: Could not configure GenerativeModel. Is GOOGLE_API_KEY set? Error: {e}")
    model = None

app = Flask(__name__)
CORS(app)

def extract_text_from_pdf(file_stream):
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = "".join(page.extract_text() for page in reader.pages if page.extract_text())
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def extract_text_from_docx(file_stream):
    try:
        doc = Document(file_stream)
        text = "\n".join(para.text for para in doc.paragraphs)
        return text
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return ""

@app.route("/api/analyze", methods=["POST"])
def analyze_cv():
    if model is None:
        return jsonify({"error": "AI model is not configured on the server."}), 500
        
    if 'cv' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    lang = request.form.get('lang', 'en')
    file = request.files['cv']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_stream = io.BytesIO(file.read())
    cv_text = ""

    if file.filename.endswith('.pdf'):
        cv_text = extract_text_from_pdf(file_stream)
    elif file.filename.endswith('.docx'):
        cv_text = extract_text_from_docx(file_stream)
    else:
        return jsonify({"error": "Unsupported file type."}), 400

    if not cv_text or len(cv_text) < 50:
        return jsonify({"error": "Could not extract sufficient text."}), 400

    # This is the stable, high-quality prompt.
    if lang == 'ar':
        prompt = f"""
        تصرف كخبير تدريب مهني ومدير موارد بشرية. حلل نص السيرة الذاتية التالي بعناية.
        يجب أن تكون إجابتك عبارة عن كائن JSON صالح واحد فقط.
        يجب أن يحتوي كائن JSON على هذه المفاتيح:
        - "overall_score": عدد صحيح بين 0 و 100.
        - "summary": سلسلة نصية تحتوي على ملخص موجز.
        - "suggestions": مصفوفة من 3 إلى 5 **سلاسل نصية بسيطة**. كل سلسلة يجب أن تكون اقتراحًا واحدًا واضحًا وقابلًا للتنفيذ.
        - "keyword_analysis": سلسلة نصية واحدة تشرح استخدام الكلمات المفتاحية.

        نص السيرة الذاتية:
        ---
        {cv_text}
        ---
        """
    else:
        prompt = f"""
        Act as an expert career coach and HR manager. Analyze the following CV text.
        Your response MUST be ONLY a single, valid JSON object.
        The JSON object must have these keys:
        - "overall_score": An integer between 0 and 100.
        - "summary": A string containing a concise summary.
        - "suggestions": An array of 3 to 5 **simple strings**. Each string must be a clear, actionable suggestion.
        - "keyword_analysis": A single string explaining keyword usage.
        
        CV Text:
        ---
        {cv_text}
        ---
        """

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
        json_start = raw_text.find('{')
        json_end = raw_text.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("No valid JSON object found in AI response.")
        clean_json_str = raw_text[json_start:json_end]
        parsed_json = json.loads(clean_json_str)
        
        # This prevents the '[object Object]' error at the source.
        if 'suggestions' in parsed_json and isinstance(parsed_json['suggestions'], list):
            parsed_json['suggestions'] = [str(item) for item in parsed_json['suggestions']]
            
        return jsonify(parsed_json)
        
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        if 'raw_text' in locals():
            print(f"--- Full AI Response Was ---\n{raw_text}\n---")
        return jsonify({"error": "AI analysis failed."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)

