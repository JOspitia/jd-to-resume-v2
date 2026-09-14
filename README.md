<div align="center">
  <h1>✨ Resume Tailor AI</h1>
  <p><strong>Perfect Your Resume. Beat the ATS. 🚀</strong></p>
  <p>Stop starting from scratch. Let an intelligent AI agent perfectly craft your master resume into an optimized PDF precisely tailored to any job description you encounter.</p>

  <p>
    <img src="https://img.shields.io/badge/Frontend-React%20%2B%20Vite-blue?style=for-the-badge&logo=react" alt="React" />
    <img src="https://img.shields.io/badge/UI-Tailwind%20%2B%20Shadcn-38bdf8?style=for-the-badge&logo=tailwind-css" alt="Tailwind CSS" />
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
  </p>
  <p>
    <img src="https://img.shields.io/badge/AI_Engine-Google_Gemini-FF5E00?style=for-the-badge&logo=google" alt="Gemini AI" />
    <img src="https://img.shields.io/badge/PDF_Rendering-Playwright-2EAD33?style=for-the-badge&logo=playwright" alt="Playwright" />
    <img src="https://img.shields.io/badge/Style-Neo--Brutalism-black?style=for-the-badge" alt="Neo-Brutalism" />
  </p>
</div>

<br/>

## 🎯 What is it?
**Resume Tailor AI** is a fully open-source, local-friendly full-stack application. It extracts text from your existing PDF resume, matches it dynamically against any copied/pasted Job Description using the Google Gemini LLM, and flawlessly renders it back into an ATS-destroying PDF format.

Complete with a modern, high-contrast **Neo-Brutalism web interface** and real-time streaming progress bars so you never wonder what the AI is thinking!

## ⚡ Core Features
- **AI-Powered Keyword Extraction**: Integrates seamlessly with `Google Gemini Flash` to ensure you hit all technical keywords.
- **Flawless Formatting**: Uses `Playwright` to render modern HTML/CSS Jinja templates natively into PDFs without heavy system dependencies (goodbye GTK+ errors).
- **Custom Context Injection**: Feed it your Target Role, GitHub link, and LinkedIn URLs to effortlessly sprinkle them into your final PDF.
- **Neo-Brutalism React UI**: Designed edge-to-edge taking inspiration from top-tier modern SAAS utilities—giving you a premium local experience.

<br/>

## 🛠️ Step-by-Step Setup

Want to run this yourself? It's easy. Since this is a full-stack dual-application, you will need to open two terminals (one for the Backend API, one for the Frontend Web App).

### 1. Prerequisites
Make sure you have installed:
- [Node.js](https://nodejs.org/) (for the frontend)
- [Python 3.10+](https://www.python.org/) (for the backend API)
- A free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/app/apikey)

---

### 2. Backend Setup (FastAPI + AI Engine)

Open your first terminal and navigate into the `backend/` folder:

```bash
cd backend
```

**Step 2A: Create a Virtual Environment & Install Dependencies**
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```
```bash
pip install -r requirements.txt
```

**Step 2B: Install Playwright Browsers**
The backend uses Playwright to render your PDF. Install its underlying Chromium engine seamlessly:
```bash
playwright install chromium
```

**Step 2C: Add your API Key**
Create a new file named `.env` right inside the `backend/` folder, and add your key:
```env
GEMINI_API_KEY=YOUR_API_KEY_HERE
```

**Step 2D: Run the API!**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
*(Your backend is now safely listening on port 8000!)*

---

### 3. Frontend Setup (React Web UI)

Open a **new/second terminal** and navigate into the `frontend/` folder:

```bash
cd frontend
```

**Step 3A: Install Node modules**
```bash
npm install
```

**Step 3B: Start the Application!**
```bash
npm run dev
```

🚀 Open your browser to `http://localhost:5173/` and enjoy!

<br />

## 📁 Repository Structure
```
jd-to-resume-pdf/
├── backend/                  # Powered by FastAPI
│   ├── main.py               # Application & Streaming API logic
│   ├── knowledge_base.txt    # Developer context for AI tailoring
│   ├── requirements.txt      # Python Dependencies
│   └── .env                  # Secret keys (ignored by git)
│
├── frontend/                 # Powered by Vite + React
│   ├── src/                  
│   │   ├── ...               # React Components & Logic
│   └── package.json          # Node Dependencies
│
├── sample-pdfs/              # Provided resume templates for testing
│   ├── jakes-resume.pdf
│   └── resume-template-...pdf
│
├── assets/                   # Local personal data (git ignored)
│
├── .gitignore
└── README.md
```

## 🤝 Open Source
Because no product is complete without a buzzword-filled feature list. 
Feel free to fork, customize your own HTML templates using Jinja inside `main.py`, or modify the AI System Prompt to meet your specific career industry.

Enjoy saving hours on your job applications!
