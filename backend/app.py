# app.py - The final, robust backend application file
import os
import io
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import PyPDF2
from docx import Document
from fpdf import FPDF

load_dotenv()

# --- Configuration ---
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
except Exception as e:
    print(f"FATAL: Could not configure GenerativeModel. Is GOOGLE_API_KEY set? Error: {e}")
    model = None

app = Flask(__name__)
CORS(app)

# --- Helper Functions ---
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

# --- API Endpoints ---
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

    # Generalized prompts
    if lang == 'ar':
        prompt = f"""تصرف كخبير تدريب مهني ومدير موارد بشرية. حلل نص السيرة الذاتية التالي بعناية. يجب أن تكون إجابتك عبارة عن كائن JSON صالح واحد فقط. يجب أن يحتوي كائن JSON على هذه المفاتيح: "overall_score", "summary", "suggestions", "keyword_analysis". نص السيرة الذاتية: --- {cv_text} ---"""
    else:
        prompt = f"""Act as an expert career coach and HR manager. Analyze the following CV text. Your response MUST be ONLY a single, valid JSON object with these keys: "overall_score", "summary", "suggestions", "keyword_analysis". CV Text: --- {cv_text} ---"""

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
        json_start = raw_text.find('{')
        json_end = raw_text.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("No valid JSON object found in AI response.")
        clean_json_str = raw_text[json_start:json_end]
        parsed_json = json.loads(clean_json_str)
        return jsonify(parsed_json)
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        if 'raw_text' in locals():
            print(f"--- Full AI Response Was ---\n{raw_text}\n---")
        return jsonify({"error": "AI analysis failed."}), 500

@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf():
    try:
        data = request.get_json()
        summary = data.get('summary', 'No summary provided.')
        suggestions = data.get('suggestions', [])
        
        pdf = FPDF()
        pdf.add_page()
        
        font_path = 'DejaVuSans.ttf'
        if not os.path.exists(font_path):
             print(f"FATAL ERROR: Font file not found at path: {font_path}")
             return jsonify({"error": "Server is missing a required font file for PDF generation."}), 500
        
        pdf.add_font('DejaVu', '', font_path, uni=True)
        
        pdf.set_font('DejaVu', '', 16)
        pdf.cell(0, 10, 'Your AI-Generated CV Insights', 0, 1, 'C')
        pdf.ln(10)
        
        pdf.set_font('DejaVu', '', 14)
        pdf.cell(0, 10, 'Professional Summary', 0, 1)
        pdf.set_font('DejaVu', '', 12)
        pdf.multi_cell(0, 8, summary)
        pdf.ln(10)
        
        pdf.set_font('DejaVu', '', 14)
        pdf.cell(0, 10, 'Key Improvements Incorporated:', 0, 1)
        pdf.set_font('DejaVu', '', 12)
        for suggestion in suggestions:
            try:
                pdf.multi_cell(0, 8, f'- {suggestion}')
            except Exception as e:
                print(f"Warning: Could not render line in PDF: {suggestion}. Error: {e}")
                pdf.multi_cell(0, 8, f'- (Could not render one suggestion due to its length)')

        pdf_output_bytes = pdf.output(dest='S').encode('latin-1')
        
        return send_file(
            io.BytesIO(pdf_output_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='Careeri_Generated_CV.pdf'
        )
    except Exception as e:
        print(f"FATAL error in PDF generation: {e}")
        return jsonify({"error": "An unexpected error occurred while generating the PDF."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

---

### **Step 2: The Final Upload**

Now we will send this final, correct code to GitHub.

1.  Open your **Command Prompt** terminal in VS Code.
2.  Make sure you are in the main `cv-doctor` folder.
3.  Run these three commands one by one:

    ```cmd
    git add .
    ```
    ```cmd
    git commit -m "fix: Final attempt to fix syntax error in app.py"
    ```
    ```cmd
    git push
    

