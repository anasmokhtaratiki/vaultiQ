# VaultIQ DSS module

Small command-line wrapper around the EU Digital Signature Services (DSS 5.13) library.

```bash
cd dss && mvn package          # builds target/vaultiq-dss.jar (fat jar, Java 17)

# detached XAdES-BASELINE-T over a file, RFC 3161 timestamp from the TSA
VAULTIQ_P12_PASSWORD=... java -jar target/vaultiq-dss.jar sign-xades \
    ../certs/signer.p12 https://freetsa.org/tsr signed.pdf signed_xades.xml

# validation report as JSON (trust anchors = comma-separated PEM files)
java -jar target/vaultiq-dss.jar verify signed.pdf ../certs/ca.pem
java -jar target/vaultiq-dss.jar verify signed_xades.xml ../certs/ca.pem signed.pdf
```

The API calls this jar from `api/signer.py` and `api/verifier.py`. Without the jar, signing falls back to
PAdES only and verification falls back to pyHanko for PDFs.

Notes
- With a self-signed dev CA and no revocation data, DSS may report `INDETERMINATE` rather than `TOTAL_PASSED`; that is expected for the demo.
- To trust the timestamp authority chain, save the TSA root as `certs/tsa_ca.pem` (picked up automatically by the API).
