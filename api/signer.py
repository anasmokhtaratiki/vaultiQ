"""Signature engine: PAdES-B / PAdES-T via pyHanko, detached XAdES-T via the DSS CLI."""
import io
import os
import subprocess
from datetime import datetime, timezone

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata, PdfSigner

from . import config

FIELD = "VaultIQSignature"


def _simple_signer():
    return signers.SimpleSigner.load(
        str(config.CERTS / "signer_key.pem"),
        str(config.CERTS / "signer_cert.pem"),
        ca_chain_files=(str(config.CERTS / "ca.pem"),),
        key_passphrase=None,
    )


def sign_pdf(pdf_bytes, with_timestamp):
    """PAdES-B (with_timestamp=False) or PAdES-T (RFC 3161 signature timestamp embedded)."""
    meta = PdfSignatureMetadata(
        field_name=FIELD, md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason="Loan agreement", location="Tunis",
    )
    tsa = timestamps.HTTPTimeStamper(config.TSA_URL, timeout=15) if with_timestamp else None
    pdf_signer = PdfSigner(
        meta, signer=_simple_signer(), timestamper=tsa,
        new_field_spec=fields.SigFieldSpec(sig_field_name=FIELD),
    )
    out = io.BytesIO()
    pdf_signer.sign_pdf(IncrementalPdfFileWriter(io.BytesIO(pdf_bytes)), output=out)
    return out.getvalue()


def sign_xades_t(source_pdf_path, out_xml_path):
    """Detached XAdES-T over the signed PDF using the DSS CLI (dss/ module)."""
    if not config.DSS_JAR.exists():
        raise FileNotFoundError(f"DSS jar not built: {config.DSS_JAR} (run `mvn package` in dss/)")
    env = {"PATH": os.environ.get("PATH", ""), "VAULTIQ_P12_PASSWORD": config.P12_PASSWORD or ""}
    subprocess.run(
        ["java", "-jar", str(config.DSS_JAR), "sign-xades",
         str(config.CERTS / "signer.p12"), config.TSA_URL, str(source_pdf_path), str(out_xml_path)],
        env=env, check=True, capture_output=True, timeout=90,
    )


def store(loan_id, signed_pdf):
    """Write artifacts under vault/signed/{loan_id}/ (loan_id is always an int)."""
    folder = config.VAULT / str(int(loan_id))
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdf_path = folder / f"{ts}_signed.pdf"
    pdf_path.write_bytes(signed_pdf)
    return pdf_path, folder / f"{ts}_xades.xml"
