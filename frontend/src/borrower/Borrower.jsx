import { useState } from "react";
import { request, errText } from "../api.js";

const card = "bg-white border rounded-lg p-5 mb-4";
const input = "border rounded px-3 py-2 w-full";
const primary = "bg-slate-900 text-white rounded px-4 py-2 disabled:opacity-50";

export default function Borrower() {
  const [token, setToken] = useState(() => sessionStorage.getItem("vq_token"));
  const [who, setWho] = useState(null);
  const [form, setForm] = useState({ full_name: "", amount: 2000, months: 12, purpose: "" });
  const [loan, setLoan] = useState(null);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(fn) {
    setBusy(true); setMsg(null);
    try { await fn(); } catch (e) { setMsg(errText(e)); } finally { setBusy(false); }
  }

  const uploadId = (file) => run(async () => {
    const fd = new FormData(); fd.append("file", file);
    const { body } = await request("/auth/kyc", { method: "POST", body: fd });
    sessionStorage.setItem("vq_token", body.token);
    setToken(body.token); setWho(body);
    setForm((f) => ({ ...f, full_name: body.full_name }));
  });

  const submit = () => run(async () => {
    const { body, status } = await request("/loans", {
      method: "POST", token, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, amount: Number(form.amount), months: Number(form.months) }),
    });
    setLoan(body);
    if (status === 202) setMsg("Your application needs a manual review by an administrator.");
    if (body.downloads?.pdf) {
      const pdf = await request(body.downloads.pdf, { token });
      setPdfUrl(URL.createObjectURL(pdf.body));
    }
  }).catch(() => {});

  const download = (path, name) => run(async () => {
    const { body } = await request(path, { token });
    const a = document.createElement("a"); a.href = URL.createObjectURL(body); a.download = name; a.click();
  });

  const badge = loan && (loan.risk_tier === "LOW" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800");

  return (
    <div>
      <section className={card}>
        <h2 className="font-semibold mb-2">1. Verify your identity</h2>
        <input type="file" accept="image/jpeg,image/png" disabled={busy}
               onChange={(e) => e.target.files[0] && uploadId(e.target.files[0])} />
        {who && <p className="mt-2 text-sm text-green-700">KYC verified: {who.full_name} ({who.id_masked})</p>}
        {token && !who && <p className="mt-2 text-sm text-green-700">KYC session active</p>}
      </section>

      <section className={card}>
        <h2 className="font-semibold mb-2">2. Loan request</h2>
        <div className="grid gap-3">
          <input className={input} placeholder="Full name" value={form.full_name}
                 onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <input className={input} type="number" min="1" placeholder="Amount (TND)" value={form.amount}
                   onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            <input className={input} type="number" min="1" max="60" placeholder="Months" value={form.months}
                   onChange={(e) => setForm({ ...form, months: e.target.value })} />
          </div>
          <input className={input} placeholder="Purpose" maxLength={300} value={form.purpose}
                 onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
          <button className={primary} disabled={!token || busy} onClick={submit}>
            {busy ? "Working..." : "Submit application"}
          </button>
        </div>
      </section>

      {msg && <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">{msg}</p>}

      {loan && (
        <section className={card}>
          <h2 className="font-semibold mb-2">3. Result</h2>
          <p className="text-sm">Loan #{loan.loan_id} · status <b>{loan.status}</b></p>
          {loan.trust_score != null && (
            <p className="mt-1 text-sm">Trust score <b>{loan.trust_score}</b>{" "}
              <span className={`px-2 py-0.5 rounded text-xs ${badge}`}>{loan.risk_tier}</span></p>
          )}
          {loan.risk_narrative && <p className="mt-1 text-sm text-slate-600">{loan.risk_narrative}</p>}
          {loan.signature_level && <p className="mt-1 text-sm">Signature level: {loan.signature_level}</p>}
          {loan.downloads?.pdf && (
            <div className="mt-3 flex gap-2">
              <button className={primary} onClick={() => download(loan.downloads.pdf, `loan_${loan.loan_id}_signed.pdf`)}>Download signed PDF</button>
              <button className="border rounded px-4 py-2" onClick={() => download(loan.downloads.xades, `loan_${loan.loan_id}_xades.xml`)}>Download XAdES-T</button>
            </div>
          )}
          {pdfUrl && <iframe title="Signed agreement" src={pdfUrl} className="w-full h-96 mt-4 border rounded" />}
        </section>
      )}
    </div>
  );
}
