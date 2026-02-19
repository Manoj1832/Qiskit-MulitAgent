# 🚀 Quick Start Test Guide (Beginner)

Follow these steps exactly to test the SWE-Agent Chrome Copilot.

## 1. Backend Setup (The Brain)

Open your terminal and run these commands one by one:

```bash
# 1. Go to the project folder
cd /home/Desktop/IBM-SWE_BENCH

# 2. Go to the backend folder
cd packages/backend

# 3. Create a python environment (sandbox)
python3 -m venv venv

# 4. Activate the environment (Mac/Linux)
source venv/bin/activate
# (You should see (venv) in your prompt now)

# 5. Install dependencies (libraries)
pip install -r requirements.txt

# 6. Create configuration file
cp .env.example .env

# 7. IMPORTANT: Edit the .env file now!
# Add your GEMINI_API_KEY inside .env
# nano .env  (or use your text editor)

# 8. Start the server
python main.py
```

**Result:** You should see `Uvicorn running on http://0.0.0.0:8000`.  
**Do not close this terminal.**

---

## 2. Chrome Extension Setup (The UI)

1. Open **Google Chrome**.
2. URL bar: Type `chrome://extensions` and hit Enter.
3. Top Right: Toggle **Developer mode** to **ON**.
4. Top Left: Click **Load unpacked**.
5. File Dialog:
   - Navigate to `/home/manoj/Desktop/IBM-SWE_BENCH/packages/extension`.
   - Click **Select Folder**.

**Result:** You will see the "SWE-Agent Chrome Copilot" extension card.

---

## 3. How to Test

1. Go to **GitHub** in Chrome.
2. Open any **Pull Request** (e.g., in one of your repos or a public one).
3. Click the **SWE-Agent icon** in your browser toolbar.
4. Click the **"Review"** tab.
5. Click **"Run Review"**.

**Result:** The AI will analyze the code changes and show you a review score and comments!
