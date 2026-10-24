"""Generate dev-only keys: self-signed CA, signer cert (PEM + PKCS#12) and the JWT RS256 key pair.
Idempotent: existing files are kept. Needs VAULTIQ_P12_PASSWORD in the environment."""
import datetime
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERTS = Path(os.environ.get("VAULTIQ_CERTS", Path(__file__).resolve().parent.parent / "certs"))
CERTS.mkdir(parents=True, exist_ok=True)


def write(name, data, mode=0o644):
    p = CERTS / name
    p.write_bytes(data)
    os.chmod(p, mode)


def pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VaultIQ (dev)"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


if (CERTS / "signer.p12").exists() and (CERTS / "jwt_private.pem").exists():
    print("certs already present, nothing to do")
    sys.exit(0)

pwd = os.environ.get("VAULTIQ_P12_PASSWORD")
if not pwd:
    sys.exit("Set VAULTIQ_P12_PASSWORD (see .env.example)")

now = datetime.datetime.now(datetime.timezone.utc)
ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
ca = (x509.CertificateBuilder().subject_name(name("VaultIQ Dev Root CA")).issuer_name(name("VaultIQ Dev Root CA"))
      .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
      .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
      .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
      .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                   content_commitment=False, key_encipherment=False, data_encipherment=False,
                                   key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
      .sign(ca_key, hashes.SHA256()))

leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
leaf = (x509.CertificateBuilder().subject_name(name("VaultIQ Document Signer")).issuer_name(ca.subject)
        .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .sign(ca_key, hashes.SHA256()))

pem = serialization.Encoding.PEM
write("ca.pem", ca.public_bytes(pem))
write("signer_cert.pem", leaf.public_bytes(pem))
write("signer_key.pem", pem_key(leaf_key), 0o600)
write("signer.p12", pkcs12.serialize_key_and_certificates(
    b"vaultiq-signer", leaf_key, leaf, [ca], serialization.BestAvailableEncryption(pwd.encode())), 0o600)

jwt_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
write("jwt_private.pem", pem_key(jwt_key), 0o600)
write("jwt_public.pem", jwt_key.public_key().public_bytes(
    pem, serialization.PublicFormat.SubjectPublicKeyInfo))
print(f"generated dev certificates in {CERTS}")
