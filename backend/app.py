# app.py - The main backend application file
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
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
app = Flask(__name__)
CORS(app)

def extract_text_from_pdf(file_stream):
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def extract_text_from_docx(file_stream):
    try:
        doc = Document(file_stream)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return ""

@app.route("/api/analyze", methods=["POST"])
def analyze_cv():
    if 'cv' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    # --- NEW: Get the language from the request ---
    lang = request.form.get('lang', 'en') # Default to 'en' if not provided

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

    # --- NEW: Choose the prompt based on the language ---
    if lang == 'ar':
        prompt = f"""
        تصرف كخبير تدريب مهني ومدير موارد بشرية أردني متخصص في سوق العمل الأردني.
        حلل نص السيرة الذاتية التالي بعناية.

        يجب أن تكون إجابتك عبارة عن كائن JSON صالح واحد فقط ولا شيء آخر. لا تضف أي نص توضيحي قبل أو بعد كائن JSON.
        يجب أن يحتوي كائن JSON على هذه المفاتيح وأنواع البيانات بالضبط:
        - "overall_score": عدد صحيح بين 0 و 100.
        - "summary": سلسلة نصية تحتوي على ملخص موجز من 2-3 جمل.
        - "suggestions": مصفوفة من 3 إلى 5 سلاسل نصية، كل منها اقتراح عملي قابل للتنفيذ.
        - "keyword_analysis": سلسلة نصية تشرح استخدام الكلمات المفتاحية.

        نص السيرة الذاتية:
        ---
        {cv_text}
        ---
        """
    else: # Default to English
        prompt = f"""
        Act as an expert Jordanian career coach and HR manager reviewing a CV for the Jordanian job market.
        
        Your response MUST be ONLY a single, valid JSON object and nothing else.
        The JSON object must have these exact keys and data types:
        - "overall_score": An integer between 0 and 100.
        - "summary": A string containing a concise 2-3 sentence summary.
        - "suggestions": An array of 3 to 5 strings, each being an actionable suggestion.
        - "keyword_analysis": A string explaining keyword usage.

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
            raise ValueError("No valid JSON object found in the AI response.")
            
        clean_json_str = raw_text[json_start:json_end]
        parsed_json = json.loads(clean_json_str)
        return jsonify(parsed_json)

    except Exception as e:
        print(f"An error occurred: {e}")
        if 'raw_text' in locals():
            print(f"--- Full AI Response Was --- \n{raw_text}\n--------------------------")
        return jsonify({"error": "AI analysis failed."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)

