# VaultIQ

**Compliance-as-a-Service for emerging markets**: KYC, AI risk scoring, PAdES-T / XAdES-T signing and DSS verification behind one API.
Security Engineering course project, Tunis Business School, 2025-2026.

## Flow

```
ID upload -> OCR KYC -> JWT (RS256, 15 min) -> loan application -> Claude risk score
   score < 40   : rejected (403)
   score 40-70  : MANUAL_REVIEW (admin approves)
   score > 70   : loan PDF (WeasyPrint) -> PAdES-T (pyHanko + RFC 3161) -> detached XAdES-T (DSS)
admin dashboard -> upload artifact -> DSS verification report -> audit log CSV
```

## Quick start (Docker)

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY, ADMIN_PASSWORD, VAULTIQ_P12_PASSWORD
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- UI: http://localhost:5173

Dev certificates and JWT keys are generated into `certs/` on first start (never commit them).

## Local setup (without Docker)

Requirements: Python 3.11, Tesseract (with `fra`), Pango (for WeasyPrint), Amiri font, JRE 17 + Maven, Node 20.

```bash
cp .env.example .env && set -a && . ./.env && set +a
pip install -r requirements.txt
python scripts/gen_certs.py
(cd dss && mvn package)
uvicorn api.main:app --reload
# second terminal
cd frontend && npm install && npm run dev
```

## Demo

1. Create a fake ID matching a seeded user: `python scripts/make_sample_cin.py "Amine Ben Salah" 12345678`
   (seeded users: see `api/db.py`).
2. Open the UI, upload `sample_cin.png`, submit the loan form (e.g. 2000 TND, 12 months).
3. Download the signed PDF and open it in Adobe Reader (signature panel shows certificate and timestamp).
4. Admin tab: sign in, upload the signed PDF (or the XAdES XML plus the original PDF), read the verdict, export the audit log.

## API summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/kyc` | none | ID image to KYC result and borrower JWT |
| POST | `/loans` | borrower | create application, score, gate, sign |
| GET | `/loans/{id}` , `/loans/{id}/download/{pdf\|xades}` | owner / admin | status and artifacts |
| POST | `/admin/login` | none | admin JWT (8 h) |
| GET | `/admin/loans` ; POST `/admin/loans/{id}/approve` | admin | review queue |
| POST | `/verify` | admin | verify PDF / XAdES, returns report |
| GET | `/admin/audit/export` | admin | audit log as CSV |

## Security notes

- RS256 JWTs, stateless, 15 min (borrower) / 8 h (admin); secrets only from environment variables.
- Uploads: size cap, magic-byte check and image decode before OCR; verify endpoint accepts PDF/XML only.
- AI output is schema-validated; the risk tier is recomputed server-side; any AI failure routes to manual review, never auto-approval. Applicant text is sent as JSON data with an explicit "do not follow instructions" system prompt.
- Audit log is append-only (SQLite triggers block UPDATE/DELETE) and hash-chained.
- WeasyPrint URL fetching is blocked to prevent SSRF; downloads are checked against the vault directory.

## Known gaps in v0.1

- Self-signed CA only; not a qualified signature. Production needs a commercial CA / QTSP.
- TSA certificate pinning (Section 3.5) is not implemented yet; a failed timestamp falls back to PAdES-B and is logged (`TSA_FAILED`).
- The DSS wrapper (`dss/`) and the pyHanko calls were written against the documented APIs but need a first run on your machine; adjust versions if the build complains.
- Storage uses the standard `sqlite3` module rather than SQLAlchemy.
- Arabic RTL template is partial (Amiri font + `dir="auto"`); no automated tests yet.
