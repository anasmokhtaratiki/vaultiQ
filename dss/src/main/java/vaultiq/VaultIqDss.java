package vaultiq;

import eu.europa.esig.dss.enumerations.DigestAlgorithm;
import eu.europa.esig.dss.enumerations.Indication;
import eu.europa.esig.dss.enumerations.SignatureLevel;
import eu.europa.esig.dss.enumerations.SignaturePackaging;
import eu.europa.esig.dss.model.DSSDocument;
import eu.europa.esig.dss.model.FileDocument;
import eu.europa.esig.dss.model.SignatureValue;
import eu.europa.esig.dss.model.ToBeSigned;
import eu.europa.esig.dss.service.http.commons.TimestampDataLoader;
import eu.europa.esig.dss.service.tsp.OnlineTSPSource;
import eu.europa.esig.dss.simplereport.SimpleReport;
import eu.europa.esig.dss.spi.DSSUtils;
import eu.europa.esig.dss.spi.x509.CommonTrustedCertificateSource;
import eu.europa.esig.dss.token.DSSPrivateKeyEntry;
import eu.europa.esig.dss.token.Pkcs12SignatureToken;
import eu.europa.esig.dss.validation.CommonCertificateVerifier;
import eu.europa.esig.dss.validation.SignedDocumentValidator;
import eu.europa.esig.dss.validation.reports.Reports;
import eu.europa.esig.dss.xades.XAdESSignatureParameters;
import eu.europa.esig.dss.xades.signature.XAdESService;

import java.io.File;
import java.security.KeyStore;
import java.util.List;

/**
 * VaultIQ DSS command line.
 *   sign-xades <p12> <tsaUrl> <inputFile> <outputXml>      (password in env VAULTIQ_P12_PASSWORD)
 *   verify <file> <trustPemsCsv> [detachedOriginal]        (prints a JSON report on stdout)
 */
public class VaultIqDss {

    public static void main(String[] a) throws Exception {
        if (a.length == 0) { usage(); return; }
        switch (a[0]) {
            case "sign-xades" -> signXades(a[1], a[2], a[3], a[4]);
            case "verify" -> verify(a[1], a.length > 2 ? a[2] : "", a.length > 3 ? a[3] : null);
            default -> usage();
        }
    }

    private static void usage() {
        System.err.println("usage: sign-xades <p12> <tsaUrl> <in> <out> | verify <file> <trustCsv> [original]");
        System.exit(2);
    }

    /** Detached XAdES-BASELINE-T over the input file, timestamped by an RFC 3161 TSA. */
    private static void signXades(String p12, String tsaUrl, String in, String out) throws Exception {
        String pwd = System.getenv("VAULTIQ_P12_PASSWORD");
        if (pwd == null || pwd.isEmpty()) throw new IllegalStateException("VAULTIQ_P12_PASSWORD not set");
        DSSDocument doc = new FileDocument(in);
        try (Pkcs12SignatureToken token = new Pkcs12SignatureToken(p12, new KeyStore.PasswordProtection(pwd.toCharArray()))) {
            DSSPrivateKeyEntry key = token.getKeys().get(0);
            XAdESSignatureParameters params = new XAdESSignatureParameters();
            params.setSignatureLevel(SignatureLevel.XAdES_BASELINE_T);
            params.setSignaturePackaging(SignaturePackaging.DETACHED);
            params.setDigestAlgorithm(DigestAlgorithm.SHA256);
            params.setSigningCertificate(key.getCertificate());
            params.setCertificateChain(key.getCertificateChain());

            XAdESService service = new XAdESService(new CommonCertificateVerifier());
            OnlineTSPSource tsp = new OnlineTSPSource(tsaUrl);
            tsp.setDataLoader(new TimestampDataLoader());
            service.setTspSource(tsp);

            ToBeSigned toSign = service.getDataToSign(doc, params);
            SignatureValue value = token.sign(toSign, params.getDigestAlgorithm(), key);
            service.signDocument(doc, params, value).save(out);
        }
    }

    private static void verify(String file, String trustCsv, String original) throws Exception {
        CommonCertificateVerifier verifier = new CommonCertificateVerifier();
        CommonTrustedCertificateSource trusted = new CommonTrustedCertificateSource();
        for (String t : trustCsv.split(",")) {
            if (!t.isBlank()) trusted.addCertificate(DSSUtils.loadCertificate(new File(t.trim())));
        }
        verifier.setTrustedCertSources(trusted);

        SignedDocumentValidator validator = SignedDocumentValidator.fromDocument(new FileDocument(file));
        validator.setCertificateVerifier(verifier);
        if (original != null) validator.setDetachedContents(List.of(new FileDocument(original)));

        Reports reports = validator.validateDocument();
        SimpleReport simple = reports.getSimpleReport();

        StringBuilder sigs = new StringBuilder();
        Indication worst = Indication.TOTAL_PASSED;
        for (String id : simple.getSignatureIdList()) {
            Indication ind = simple.getIndication(id);
            if (ind == Indication.TOTAL_FAILED) worst = Indication.TOTAL_FAILED;
            else if (ind != Indication.TOTAL_PASSED && worst != Indication.TOTAL_FAILED) worst = Indication.INDETERMINATE;
            if (sigs.length() > 0) sigs.append(',');
            sigs.append("{\"id\":").append(q(id))
                .append(",\"indication\":").append(q(String.valueOf(ind)))
                .append(",\"sub_indication\":").append(q(String.valueOf(simple.getSubIndication(id))))
                .append(",\"format\":").append(q(String.valueOf(simple.getSignatureFormat(id))))
                .append(",\"signed_by\":").append(q(simple.getSignedBy(id))).append('}');
        }
        if (sigs.length() == 0) worst = Indication.NO_SIGNATURE_FOUND;
        String verdict = worst == Indication.TOTAL_PASSED ? "VALID"
                : (worst == Indication.TOTAL_FAILED || worst == Indication.NO_SIGNATURE_FOUND) ? "INVALID" : "INDETERMINATE";
        System.out.println("{\"engine\":\"dss\",\"verdict\":\"" + verdict + "\",\"signatures\":[" + sigs + "]}");
    }

    private static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> b.append("\\\"");
                case '\\' -> b.append("\\\\");
                case '\n' -> b.append("\\n");
                case '\r' -> b.append("\\r");
                case '\t' -> b.append("\\t");
                default -> { if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c); }
            }
        }
        return b.append('"').toString();
    }
}
