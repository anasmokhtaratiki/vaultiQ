"""VaultIQ API: KYC -> AI risk score -> loan PDF -> PAdES-T + XAdES-T -> compliance verification."""
import csv
import difflib
import hashlib
import hmac
import io
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import auth, config, db, kyc, pdf_generator, risk_engine, signer, verifier


@asynccontextmanager
async def lifespan(_):
    db.init()
    yield


app = FastAPI(title="VaultIQ", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


class LoanIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    amount: float = Field(gt=0, le=100_000)
    months: int = Field(ge=1, le=60)
    purpose: str = Field(default="", max_length=300)
    device_id: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    username: str
    password: str


def _loan_dict(row):
    d = dict(row)
    d["downloads"] = ({"pdf": f"/loans/{d['loan_id']}/download/pdf",
                       "xades": f"/loans/{d['loan_id']}/download/xades"}
                      if d["status"] == "SIGNED" else {})
    d.pop("pdf_path", None)
    d.pop("xades_path", None)
    return d


def _get_loan(conn, loan_id, claims):
    loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
    if loan is None:
        raise HTTPException(404, "Loan not found")
    if claims.get("role") != "admin" and str(loan["user_id"]) != str(claims["sub"]):
        raise HTTPException(403, "Not your loan")
    return loan


def run_pipeline(conn, loan_id, actor):
    """PDF generation -> PAdES-T (fallback PAdES-B) -> XAdES-T -> storage."""
    loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (loan["user_id"],)).fetchone()
    pdf = pdf_generator.render_loan_pdf(dict(loan), dict(user))
    db.audit(conn, "PDF_GENERATED", actor, loan_id, {"sha256": hashlib.sha256(pdf).hexdigest()})

    level = "PAdES-T"
    try:
        signed = signer.sign_pdf(pdf, with_timestamp=True)
    except Exception as exc:  # TSA unreachable: keep going, but record the downgrade
        db.audit(conn, "TSA_FAILED", actor, loan_id, {"error": type(exc).__name__})
        signed, level = signer.sign_pdf(pdf, with_timestamp=False), "PAdES-B"
    pdf_path, xml_path = signer.store(loan_id, signed)

    xades_path = None
    try:
        signer.sign_xades_t(pdf_path, xml_path)
        xades_path = str(xml_path)
    except Exception as exc:
        db.audit(conn, "XADES_FAILED", actor, loan_id, {"error": type(exc).__name__})

    conn.execute(
        "UPDATE loans SET status='SIGNED', signature_level=?, pdf_path=?, xades_path=? WHERE loan_id=?",
        (level, str(pdf_path), xades_path, loan_id))
    db.audit(conn, "DOCUMENT_SIGNED", actor, loan_id,
             {"level": level, "xades": bool(xades_path),
              "sha256": hashlib.sha256(signed).hexdigest()})


# ---------------------------------------------------------------- borrower flow
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/kyc")
def kyc_endpoint(file: UploadFile = File(...)):
    data = file.file.read(config.MAX_ID_IMAGE_BYTES + 1)
    with db.connect() as conn:
        try:
            claims = kyc.verify_identity(data, file.content_type, conn)
        except kyc.KYCError as exc:
            db.audit(conn, "KYC_REJECTED", "anonymous", None, {"code": exc.code})
            conn.commit()
            return JSONResponse(status_code=422, content={"code": exc.code, "message": exc.message})
        db.audit(conn, "KYC_VERIFIED", f"user:{claims['user_id']}")
    token = auth.issue_token(
        {"sub": str(claims["user_id"]), "user_id": claims["user_id"], "role": "borrower",
         "kyc_status": "verified", "risk_tier": "UNSCORED"}, config.USER_TOKEN_MINUTES)
    return {"token": token, "full_name": claims["full_name"], "id_masked": claims["id_masked"]}


@app.post("/loans")
def create_loan(body: LoanIn, claims=Depends(auth.require_borrower)):
    uid = int(claims["user_id"])
    actor = f"user:{uid}"
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
        ratio = difflib.SequenceMatcher(None, body.full_name.lower().strip(),
                                        user["full_name"].lower()).ratio()
        if ratio < 0.85:
            db.audit(conn, "IDENTITY_MISMATCH", actor, None, {"ratio": round(ratio, 2)})
            conn.commit()
            raise HTTPException(422, "Application name does not match the verified ID")

        velocity = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE user_id = ? AND created_at >= datetime('now','-1 day')",
            (uid,)).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO loans (user_id, amount, months, purpose, device_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'PENDING', ?)",
            (uid, body.amount, body.months, body.purpose, body.device_id, db.now()))
        loan_id = cur.lastrowid
        db.audit(conn, "LOAN_CREATED", actor, loan_id, {"amount": body.amount, "months": body.months})

        risk = risk_engine.score_application(
            {"full_name": user["full_name"], "dob": user["dob"]}, body.model_dump(),
            velocity, body.device_id)
        conn.execute("UPDATE loans SET trust_score=?, risk_tier=?, risk_narrative=? WHERE loan_id=?",
                     (risk["trust_score"], risk["risk_tier"], risk["risk_narrative"], loan_id))
        db.audit(conn, "RISK_SCORED", "risk-engine", loan_id,
                 {"score": risk["trust_score"], "tier": risk["risk_tier"], "decision": risk["decision"]})

        if risk["decision"] == "BLOCK":
            conn.execute("UPDATE loans SET status='REJECTED' WHERE loan_id=?", (loan_id,))
            db.audit(conn, "LOAN_BLOCKED", "risk-engine", loan_id)
            conn.commit()
            raise HTTPException(403, {"message": "Application rejected by risk engine",
                                      "trust_score": risk["trust_score"],
                                      "reason": risk["risk_narrative"]})
        if risk["decision"] == "MANUAL_REVIEW":
            conn.execute("UPDATE loans SET status='MANUAL_REVIEW' WHERE loan_id=?", (loan_id,))
            db.audit(conn, "MANUAL_REVIEW_REQUIRED", "risk-engine", loan_id)
        else:
            run_pipeline(conn, loan_id, actor)
        row = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
    result = _loan_dict(row)
    return JSONResponse(status_code=202 if row["status"] == "MANUAL_REVIEW" else 200, content=result)


@app.get("/loans/{loan_id}")
def get_loan(loan_id: int, claims=Depends(auth.current_claims)):
    with db.connect() as conn:
        return _loan_dict(_get_loan(conn, loan_id, claims))


@app.get("/loans/{loan_id}/download/{kind}")
def download(loan_id: int, kind: str, claims=Depends(auth.current_claims)):
    if kind not in ("pdf", "xades"):
        raise HTTPException(404, "Unknown artifact")
    with db.connect() as conn:
        loan = _get_loan(conn, loan_id, claims)
        path = loan["pdf_path"] if kind == "pdf" else loan["xades_path"]
        if loan["status"] != "SIGNED" or not path:
            raise HTTPException(404, "Artifact not available")
        db.audit(conn, "DOWNLOAD", f"{claims['role']}:{claims['sub']}", loan_id, {"kind": kind})
    real = Path(path).resolve()
    if not real.is_relative_to(config.VAULT.resolve()):  # path traversal guard
        raise HTTPException(403, "Forbidden path")
    media = "application/pdf" if kind == "pdf" else "application/xml"
    return FileResponse(real, media_type=media, filename=real.name)


# ---------------------------------------------------------------- admin flow
@app.post("/admin/login")
def admin_login(body: LoginIn):
    ok = (config.ADMIN_PASSWORD
          and hmac.compare_digest(body.username, config.ADMIN_USER)
          and hmac.compare_digest(body.password, config.ADMIN_PASSWORD))
    with db.connect() as conn:
        db.audit(conn, "ADMIN_LOGIN_OK" if ok else "ADMIN_LOGIN_FAILED", body.username[:50])
    if not ok:
        raise HTTPException(401, "Invalid credentials")
    return {"token": auth.issue_token({"sub": "admin", "role": "admin"}, config.ADMIN_TOKEN_MINUTES)}


@app.get("/admin/loans")
def admin_loans(_=Depends(auth.require_admin)):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM loans ORDER BY loan_id DESC LIMIT 200").fetchall()
        return [_loan_dict(r) for r in rows]


@app.post("/admin/loans/{loan_id}/approve")
def approve(loan_id: int, claims=Depends(auth.require_admin)):
    with db.connect() as conn:
        loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
        if loan is None or loan["status"] != "MANUAL_REVIEW":
            raise HTTPException(409, "Loan is not awaiting manual review")
        db.audit(conn, "MANUAL_APPROVED", "admin", loan_id)
        run_pipeline(conn, loan_id, "admin")
        return _loan_dict(conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone())


@app.post("/verify")
def verify_artifact(file: UploadFile = File(...), original: UploadFile | None = File(None),
                    _=Depends(auth.require_admin)):
    data = file.file.read(config.MAX_VERIFY_BYTES + 1)
    if not data or len(data) > config.MAX_VERIFY_BYTES:
        raise HTTPException(413, "Empty or too large")
    if data.startswith(b"%PDF"):
        kind = "pdf"
    elif data.lstrip().startswith(b"<"):
        kind = "xml"
    else:
        raise HTTPException(415, "Only PDF or XAdES XML artifacts are accepted")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ("artifact.pdf" if kind == "pdf" else "artifact.xml")
        target.write_bytes(data)
        orig_path = None
        if original is not None:
            name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(original.filename or "original.pdf"))
            orig_path = Path(tmp) / name   # DSS matches the detached file by name
            orig_path.write_bytes(original.file.read(config.MAX_VERIFY_BYTES))
        try:
            report = verifier.verify(target, kind, orig_path)
        except Exception as exc:
            raise HTTPException(500, f"Verification failed: {type(exc).__name__}")
    with db.connect() as conn:
        db.audit(conn, "VERIFIED", "admin", None,
                 {"sha256": hashlib.sha256(data).hexdigest(), "verdict": report.get("verdict")})
    return report


@app.get("/admin/audit/export")
def export_audit(_=Depends(auth.require_admin)):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rows[0].keys() if rows else ["id", "ts", "event", "actor", "loan_id", "detail", "prev_hash", "hash"])
    w.writerows([tuple(r) for r in rows])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit_log.csv"})
