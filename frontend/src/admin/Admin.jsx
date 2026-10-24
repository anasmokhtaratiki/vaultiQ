import { useState } from "react";
import { request, errText } from "../api.js";

const card = "bg-white border rounded-lg p-5 mb-4";
const input = "border rounded px-3 py-2 w-full";
const primary = "bg-slate-900 text-white rounded px-4 py-2 disabled:opacity-50";
const verdictStyle = { VALID: "bg-green-100 text-green-800", INDETERMINATE: "bg-amber-100 text-amber-800", INVALID: "bg-red-100 text-red-800" };

export default function Admin() {
  const [token, setToken] = useState(null);
  const [cred, setCred] = useState({ username: "admin", password: "" });
  const [loans, setLoans] = useState([]);
  const [file, setFile] = useState(null);
  const [original, setOriginal] = useState(null);
  const [report, setReport] = useState(null);
  const [msg, setMsg] = useState(null);

  const guard = async (fn) => { setMsg(null); try { await fn(); } catch (e) { setMsg(errText(e)); } };
  const refresh = (t = token) => guard(async () => setLoans((await request("/admin/loans", { token: t })).body));

  const login = () => guard(async () => {
    const { body } = await request("/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred) });
    setToken(body.token); await refresh(body.token);
  });
  const approve = (id) => guard(async () => { await request(`/admin/loans/${id}/approve`, { method: "POST", token }); await refresh(); });
  const verify = () => guard(async () => {
    const fd = new FormData(); fd.append("file", file); if (original) fd.append("original", original);
    setReport((await request("/verify", { method: "POST", token, body: fd })).body);
  });
  const exportCsv = () => guard(async () => {
    const { body } = await request("/admin/audit/export", { token });
    const a = document.createElement("a"); a.href = URL.createObjectURL(body); a.download = "audit_log.csv"; a.click();
  });

  if (!token) {
    return (
      <section className={card}>
        <h2 className="font-semibold mb-2">Admin login</h2>
        <div className="grid gap-3">
          <input className={input} value={cred.username} onChange={(e) => setCred({ ...cred, username: e.target.value })} />
          <input className={input} type="password" placeholder="Password" value={cred.password} onChange={(e) => setCred({ ...cred, password: e.target.value })} />
          <button className={primary} onClick={login}>Sign in</button>
        </div>
        {msg && <p className="mt-3 text-sm text-red-700">{msg}</p>}
      </section>
    );
  }

  return (
    <div>
      {msg && <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">{msg}</p>}

      <section className={card}>
        <div className="flex justify-between mb-2">
          <h2 className="font-semibold">Loans</h2>
          <div className="flex gap-2">
            <button className="border rounded px-3 py-1 text-sm" onClick={() => refresh()}>Refresh</button>
            <button className="border rounded px-3 py-1 text-sm" onClick={exportCsv}>Export audit log (CSV)</button>
          </div>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-slate-500"><th>#</th><th>Amount</th><th>Score</th><th>Status</th><th>Level</th><th></th></tr></thead>
          <tbody>
            {loans.map((l) => (
              <tr key={l.loan_id} className="border-t">
                <td>{l.loan_id}</td><td>{l.amount}</td><td>{l.trust_score ?? "-"}</td><td>{l.status}</td><td>{l.signature_level ?? "-"}</td>
                <td>{l.status === "MANUAL_REVIEW" && <button className="underline" onClick={() => approve(l.loan_id)}>Approve</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={card}>
        <h2 className="font-semibold mb-2">Verify a signed artifact</h2>
        <label className="text-sm">Signed PDF or XAdES XML</label>
        <input className="block mb-2" type="file" accept=".pdf,.xml" onChange={(e) => setFile(e.target.files[0])} />
        <label className="text-sm">Original signed PDF (only for detached XAdES)</label>
        <input className="block mb-3" type="file" accept=".pdf" onChange={(e) => setOriginal(e.target.files[0])} />
        <button className={primary} disabled={!file} onClick={verify}>Verify</button>

        {report && (
          <div className="mt-4 text-sm">
            <span className={`px-2 py-1 rounded font-semibold ${verdictStyle[report.verdict] || ""}`}>{report.verdict}</span>
            <span className="ml-2 text-slate-500">engine: {report.engine}</span>
            {report.message && <p className="mt-2">{report.message}</p>}
            <pre className="mt-3 bg-slate-100 rounded p-3 overflow-auto text-xs">{JSON.stringify(report.signatures, null, 2)}</pre>
          </div>
        )}
      </section>
    </div>
  );
}
