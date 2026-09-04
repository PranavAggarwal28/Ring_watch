# RingWatch

RingWatch is a local demo that finds suspicious groups of payment accounts. It
checks shared devices and IP addresses, gives each group a risk score, and uses
Gemini to explain the detected signals in plain language.

## What you need

- Python 3.10 or newer
- A Gemini API key for new AI explanations

## First-time setup

1. Open PowerShell in this project folder.
2. Install the required packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Create a file called `.env` in this folder. Add your Gemini key:

   ```text
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

## Run the web app

1. Start the app:

   ```powershell
   python app.py
   ```

2. Open this address in your browser:

   ```text
   http://127.0.0.1:5000
   ```

3. Sign in:

   ```text
   Email: employee@razorpay.com
   Password: razorpay123
   ```

4. Choose `transactions.csv`.
5. Press **Start security scan**.

The included demo CSV finds three suspicious clusters with scores **85**,
**100**, and **70**. The original CSV is never changed; the app saves uploaded
copies inside `uploads`.

## Original command-line report

The web app does not replace the original workflow. To create the original
HTML report, run:

```powershell
python detect_rings.py
python explain_rings.py
python generate_report.py
```

Then open `output/report.html` in a browser.

## If Gemini is unavailable

Check that `.env` has a valid `GEMINI_API_KEY` and that you are connected to
the internet. For the included demo CSV only, RingWatch can reuse the exact
genuine Gemini explanations already generated for that same evidence. A new
CSV still requires Gemini to create fresh explanations.
