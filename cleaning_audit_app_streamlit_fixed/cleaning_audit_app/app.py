from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, abort
import os
import uuid
import urllib.request
import re
from datetime import datetime

app = Flask(__name__)

# ===== 監査ログイン（初期パスワード固定）=====
# ※要件どおり初期パスワードは 1111
AUDITOR_PASSWORD = "1111"
# Cloud Runでは環境変数でSECRET_KEYを渡すのが推奨。未設定時は簡易キー。
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# 送信先（任意）: 環境変数で指定
# 例: AUDITOR_ENDPOINT=https://xxxxx.a.run.app/api/receive_report
AUDITOR_ENDPOINT = os.environ.get("AUDITOR_ENDPOINT", "").strip()

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/report")
def api_report():
    data = request.get_json(silent=True) or {}
    report_id = uuid.uuid4().hex[:12]
    filename = f"cleaning_report_{report_id}.txt"
    filepath = os.path.join(REPORTS_DIR, filename)

    # ===== テキスト化（監査側で読み込みやすい形式）=====
    lines = []
    lines.append("CLEANING_REPORT_V1")
    lines.append(f"report_id: {report_id}")
    lines.append(f"roomId: {data.get('roomId','')}")
    lines.append(f"cleanerId: {data.get('cleanerId','')}")
    lines.append(f"startedAt: {data.get('startedAt','')}")
    lines.append(f"finishedAt: {data.get('finishedAt','')}")
    lines.append(f"durationSeconds: {data.get('durationSeconds','')}")
    lines.append(f"totalScore: {data.get('totalScore','')}")
    lines.append("")
    lines.append("tasks:")
    tasks = data.get("tasks") or {}
    for tid, tinfo in tasks.items():
        status = (tinfo or {}).get("status","")
        score = (tinfo or {}).get("score","")
        checkedAt = (tinfo or {}).get("checkedAt","")
        notes = (tinfo or {}).get("notes","")
        lines.append(f"- id: {tid}")
        lines.append(f"  status: {status}")
        lines.append(f"  score: {score}")
        lines.append(f"  checkedAt: {checkedAt}")
        lines.append(f"  notes: {notes}")
    text = "\n".join(lines) + "\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

    # ===== 外部送信（任意：旧仕様互換）=====
    sent = False
    send_error = ""
    if AUDITOR_ENDPOINT:
        try:
            payload = json_bytes({"filename": filename, "content": text})
            req = urllib.request.Request(
                AUDITOR_ENDPOINT,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                _ = resp.read()
            sent = True
        except Exception as e:
            send_error = str(e)

    return jsonify({
        "ok": True,
        "report_id": report_id,
        "filename": filename,
        "download_url": f"/reports/{filename}",
        "sent_to_auditor": sent,
        "send_error": send_error,
    })

@app.get("/reports/<path:filename>")
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)

# ===== 監査機能（統合）=====

def _auditor_logged_in() -> bool:
    return bool(session.get("auditor_ok"))

def _require_auditor_login():
    if not _auditor_logged_in():
        return redirect(url_for("auditor_login", next=request.path))
    return None

@app.get("/auditor/login")
def auditor_login():
    return render_template("auditor_login.html", error="")

@app.post("/auditor/login")
def auditor_login_post():
    pw = (request.form.get("password") or "").strip()
    if pw == AUDITOR_PASSWORD:
        session["auditor_ok"] = True
        next_url = request.args.get("next") or "/auditor"
        return redirect(next_url)
    return render_template("auditor_login.html", error="パスワードが違います。")

@app.get("/auditor/logout")
def auditor_logout():
    session.pop("auditor_ok", None)
    return redirect("/")

@app.get("/auditor")
def auditor_index():
    gate = _require_auditor_login()
    if gate:
        return gate

    reports = []
    for fn in sorted(os.listdir(REPORTS_DIR), reverse=True):
        if not fn.endswith(".txt"):
            continue
        path = os.path.join(REPORTS_DIR, fn)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            mtime = ""
        meta = parse_meta(path)
        reports.append({"filename": fn, "mtime": mtime, **meta})
    return render_template("auditor_index.html", reports=reports)

@app.get("/auditor/reports/<path:filename>")
def auditor_view_report(filename):
    gate = _require_auditor_login()
    if gate:
        return gate

    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.isfile(path):
        abort(404)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    meta = parse_meta(path)
    return render_template("auditor_report.html", filename=filename, text=text, meta=meta)

@app.get("/auditor/download/<path:filename>")
def auditor_download(filename):
    gate = _require_auditor_login()
    if gate:
        return gate
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)

# 旧：外部から受信したい場合の互換API（統合後も利用可）
@app.post("/api/receive_report")
def receive_report():
    data = request.get_json(silent=True) or {}
    filename = (data.get("filename") or "").strip()
    content = data.get("content") or ""

    if not filename or not filename.endswith(".txt"):
        filename = f"cleaning_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    path = os.path.join(REPORTS_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"ok": True, "saved_as": filename, "view_url": f"/auditor/reports/{filename}"})

def parse_meta(path):
    meta = {"roomId":"", "cleanerId":"", "totalScore":"", "finishedAt":""}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                line=line.strip()
                if line.startswith("roomId:"):
                    meta["roomId"]=line.split(":",1)[1].strip()
                elif line.startswith("cleanerId:"):
                    meta["cleanerId"]=line.split(":",1)[1].strip()
                elif line.startswith("totalScore:"):
                    meta["totalScore"]=line.split(":",1)[1].strip()
                elif line.startswith("finishedAt:"):
                    meta["finishedAt"]=line.split(":",1)[1].strip()
    except Exception:
        pass
    return meta

def json_bytes(obj):
    import json
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
