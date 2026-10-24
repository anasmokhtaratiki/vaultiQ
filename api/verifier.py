"""Compliance verification. Uses the EU DSS CLI when built, else a pyHanko fallback for PDFs."""
import json
import subprocess

from . import config


def _trust_files():
    files = [config.CERTS / "ca.pem", config.CERTS / "tsa_ca.pem"]  # tsa_ca.pem optional
    return ",".join(str(f) for f in files if f.exists())


def _verify_dss(path, original=None):
    cmd = ["java", "-jar", str(config.DSS_JAR), "verify", str(path), _trust_files()]
    if original:
        cmd.append(str(original))
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-300:] or "DSS failed")
    return json.loads(res.stdout)


def _verify_pyhanko(path):
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    root = load_cert_from_pemder(str(config.CERTS / "ca.pem"))
    vc = ValidationContext(trust_roots=[root], allow_fetching=False)
    with open(path, "rb") as fh:
        sigs = PdfFileReader(fh).embedded_signatures
        if not sigs:
            return {"engine": "pyhanko", "verdict": "INVALID", "signatures": [],
                    "message": "No signature found"}
        out = []
        for sig in sigs:
            st = validate_pdf_signature(sig, vc)
            out.append({
                "signer": sig.signer_cert.subject.human_friendly,
                "hash_intact": bool(st.intact), "signature_valid": bool(st.valid),
                "chain_trusted": bool(st.trusted),
                "has_timestamp": st.timestamp_validity is not None,
                "level": "PAdES-T" if st.timestamp_validity is not None else "PAdES-B",
            })
    ok = all(s["hash_intact"] and s["signature_valid"] and s["chain_trusted"] for s in out)
    broken = any(not (s["hash_intact"] and s["signature_valid"]) for s in out)
    return {"engine": "pyhanko", "verdict": "VALID" if ok else ("INVALID" if broken else "INDETERMINATE"),
            "signatures": out}


def verify(path, kind, original=None):
    """kind: 'pdf' or 'xml'. Returns a normalised report (no PII beyond signer certificate CN)."""
    if config.DSS_JAR.exists():
        return _verify_dss(path, original)
    if kind == "pdf":
        return _verify_pyhanko(path)
    return {"engine": "none", "verdict": "INDETERMINATE", "signatures": [],
            "message": "XAdES verification needs the DSS jar (run `mvn package` in dss/)"}
