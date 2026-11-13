"""Local web interface for the RingWatch fraud-risk pipeline."""
from pathlib import Path
from uuid import uuid4
import os

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from explain_rings import run_pipeline

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output" / "web_scans"
REQUIRED_COLUMNS = {"account_id", "device_id", "ip_address", "amount", "timestamp"}
DEMO_EMAIL = "demo@ringwatch.com"
DEMO_PASSWORD = "ringwatch123"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "ringwatch-demo-session-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def logged_in():
    return bool(session.get("employee"))


@app.route("/")
def index():
    return redirect(url_for("dashboard") if logged_in() else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        if data.get("email", "").strip().lower() == DEMO_EMAIL and data.get("password") == DEMO_PASSWORD:
            session.clear()
            session["employee"] = DEMO_EMAIL
            return jsonify({"ok": True, "redirect": url_for("dashboard")})
        return jsonify({"ok": False, "error": "Use the RingWatch demo credentials shown on the login page."}), 401
    if logged_in():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect(url_for("login"))
    return render_template("dashboard.html", employee=session["employee"])


@app.post("/upload")
def upload():
    if not logged_in():
        return jsonify({"error": "Please sign in to upload data."}), 401
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Choose a CSV transaction file first."}), 400
    if Path(file.filename).suffix.lower() != ".csv":
        return jsonify({"error": "Only CSV files are supported."}), 400

    UPLOAD_DIR.mkdir(exist_ok=True)
    saved_name = f"{uuid4().hex}_{secure_filename(file.filename)}"
    saved_path = UPLOAD_DIR / saved_name
    file.save(saved_path)
    try:
        frame = pd.read_csv(saved_path)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if frame.empty:
            raise ValueError("The CSV has no transaction rows.")
        if missing:
            raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        return jsonify({"error": f"Invalid transaction CSV: {exc}"}), 400

    session["upload_path"] = str(saved_path)
    session["upload_name"] = secure_filename(file.filename)
    return jsonify({"ok": True, "filename": session["upload_name"], "transactions": len(frame)})


@app.post("/scan")
def scan():
    if not logged_in():
        return jsonify({"error": "Please sign in to start a scan."}), 401
    upload_path = Path(session.get("upload_path", ""))
    if not upload_path.is_file() or UPLOAD_DIR not in upload_path.parents:
        return jsonify({"error": "Upload a valid CSV before starting a security scan."}), 400
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        results = run_pipeline(str(upload_path), str(OUTPUT_DIR / f"{uuid4().hex}.json"))
        total_transactions = len(pd.read_csv(upload_path))
        scores = [item["severity_score"] for item in results]
        return jsonify({
            "ok": True,
            "summary": {
                "total_transactions": total_transactions,
                "suspicious_transactions": sum(item["transaction_count"] for item in results),
                "suspicious_clusters": len(results),
                "high_risk": sum(score >= 90 for score in scores),
                "average_risk": round(sum(scores) / len(scores), 1) if scores else None,
            },
            "results": results,
        })
    except Exception as exc:
        app.logger.exception("Pipeline scan failed")
        return jsonify({"error": "The security scan could not complete. Check the server Gemini configuration and transaction data, then try again."}), 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "CSV files must be 10 MB or smaller."}), 413


if __name__ == "__main__":
    app.run(debug=True)
