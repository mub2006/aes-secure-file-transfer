from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, abort
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("AES_TRANSFER_DATA", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "encrypted"
DB_PATH = DATA_DIR / "transfers.sqlite3"
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", 100 * 1024 * 1024))
DEFAULT_EXPIRY_HOURS = int(os.environ.get("TRANSFER_EXPIRY_HOURS", 24))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + 1024 * 1024
app.config["JSON_SORT_KEYS"] = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                original_size INTEGER NOT NULL,
                encrypted_size INTEGER NOT NULL,
                nonce_b64 TEXT NOT NULL,
                algorithm TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at REAL NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_transfer(transfer_id: str):
    with db_connect() as conn:
        return conn.execute(
            "SELECT * FROM transfers WHERE transfer_id = ?", (transfer_id,)
        ).fetchone()


def authorize(row, token: str) -> bool:
    if not row or not token:
        return False
    if row["expires_at"] < time.time():
        return False
    return secrets.compare_digest(row["token_hash"], token_digest(token))


@app.get("/")
def index():
    return render_template("index.html", max_file_mb=MAX_FILE_BYTES // (1024 * 1024))


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "AES Secure File Transfer", "max_file_bytes": MAX_FILE_BYTES})


@app.post("/api/transfers")
def create_transfer():
    if "file" not in request.files:
        return jsonify({"error": "Encrypted payload is missing."}), 400

    encrypted_file = request.files["file"]
    if not encrypted_file or not encrypted_file.filename:
        return jsonify({"error": "No encrypted payload was selected."}), 400

    try:
        metadata = json.loads(request.form.get("metadata", "{}"))
    except json.JSONDecodeError:
        return jsonify({"error": "Transfer metadata is invalid."}), 400

    required = ("original_name", "mime_type", "original_size", "nonce", "algorithm")
    if any(key not in metadata for key in required):
        return jsonify({"error": "Required encryption metadata is missing."}), 400
    if metadata.get("algorithm") != "AES-256-GCM":
        return jsonify({"error": "Unsupported encryption algorithm."}), 400

    try:
        original_size = int(metadata["original_size"])
    except (TypeError, ValueError):
        return jsonify({"error": "Original file size is invalid."}), 400

    if original_size < 0 or original_size > MAX_FILE_BYTES:
        return jsonify({"error": f"Original file must be between 0 and {MAX_FILE_BYTES // (1024 * 1024)} MB."}), 413

    # Read at most the configured encrypted size plus a small GCM tag allowance.
    encrypted_bytes = encrypted_file.read(MAX_FILE_BYTES + 32)
    if len(encrypted_bytes) > MAX_FILE_BYTES + 16:
        return jsonify({"error": "Encrypted payload exceeds the configured size limit."}), 413
    if len(encrypted_bytes) < 16:
        return jsonify({"error": "Encrypted payload is too small to contain a GCM tag."}), 400

    nonce = metadata.get("nonce", "")
    if not isinstance(nonce, str) or len(nonce) < 12:
        return jsonify({"error": "Nonce metadata is invalid."}), 400

    transfer_id = uuid.uuid4().hex[:12].upper()
    access_token = secrets.token_urlsafe(24)
    stored_name = f"{uuid.uuid4().hex}.bin"
    target = UPLOAD_DIR / stored_name
    target.write_bytes(encrypted_bytes)

    created_at = utc_now()
    expires_at = time.time() + DEFAULT_EXPIRY_HOURS * 3600
    original_name = secure_filename(str(metadata["original_name"])) or "download"
    mime_type = str(metadata["mime_type"])[:200] or "application/octet-stream"

    try:
        with db_connect() as conn:
            conn.execute("""
                INSERT INTO transfers (
                    transfer_id, token_hash, stored_name, original_name, mime_type,
                    original_size, encrypted_size, nonce_b64, algorithm, created_at,
                    expires_at, downloads
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                transfer_id, token_digest(access_token), stored_name, original_name,
                mime_type, original_size, len(encrypted_bytes), nonce,
                "AES-256-GCM", created_at, expires_at
            ))
            conn.commit()
    except Exception:
        target.unlink(missing_ok=True)
        raise

    return jsonify({
        "transfer_id": transfer_id,
        "access_token": access_token,
        "created_at": created_at,
        "expires_in_hours": DEFAULT_EXPIRY_HOURS,
        "encrypted_size": len(encrypted_bytes)
    }), 201


@app.get("/api/transfers/<transfer_id>")
def download_transfer(transfer_id):
    row = get_transfer(transfer_id.upper())
    token = request.headers.get("X-Transfer-Token", "")
    if not authorize(row, token):
        return jsonify({"error": "Transfer not found, expired, or access token is incorrect."}), 403

    path = UPLOAD_DIR / row["stored_name"]
    if not path.is_file():
        return jsonify({"error": "Encrypted file is no longer available on the server."}), 404

    with db_connect() as conn:
        conn.execute(
            "UPDATE transfers SET downloads = downloads + 1 WHERE transfer_id = ?",
            (transfer_id.upper(),)
        )
        conn.commit()

    response = send_file(
        path,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"{transfer_id.upper()}.aes"
    )
    response.headers["X-Original-Name"] = row["original_name"]
    response.headers["X-Original-Mime"] = row["mime_type"]
    response.headers["X-Original-Size"] = str(row["original_size"])
    response.headers["X-Nonce"] = row["nonce_b64"]
    response.headers["X-Encryption-Algorithm"] = row["algorithm"]
    response.headers["X-Encrypted-Size"] = str(row["encrypted_size"])
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/transfers/<transfer_id>/status")
def transfer_status(transfer_id):
    row = get_transfer(transfer_id.upper())
    token = request.headers.get("X-Transfer-Token", "")
    if not authorize(row, token):
        return jsonify({"error": "Transfer not found, expired, or access token is incorrect."}), 403
    return jsonify({
        "transfer_id": row["transfer_id"],
        "original_name": row["original_name"],
        "original_size": row["original_size"],
        "encrypted_size": row["encrypted_size"],
        "created_at": row["created_at"],
        "expires_at": datetime.fromtimestamp(row["expires_at"], timezone.utc).isoformat(),
        "downloads": row["downloads"],
        "algorithm": row["algorithm"]
    })


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": f"Request is too large. Maximum original file size is {MAX_FILE_BYTES // (1024 * 1024)} MB."}), 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found."}), 404
    return "Page not found", 404


init_db()

if __name__ == "__main__":
    # Local development only. Use a production WSGI server and HTTPS for deployment.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
