import { useState } from "react";
import Borrower from "./borrower/Borrower.jsx";
import Admin from "./admin/Admin.jsx";

export default function App() {
  const [tab, setTab] = useState("borrower");
  const btn = (id, label) => (
    <button onClick={() => setTab(id)}
      className={`px-4 py-2 rounded-md text-sm font-medium ${tab === id ? "bg-slate-900 text-white" : "bg-white border"}`}>
      {label}
    </button>
  );
  return (
    <div className="max-w-3xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">VaultIQ</h1>
        <p className="text-sm text-slate-500">Compliance-as-a-Service for emerging markets</p>
        <div className="flex gap-2 mt-4">{btn("borrower", "Borrower")}{btn("admin", "Compliance dashboard")}</div>
      </header>
      {tab === "borrower" ? <Borrower /> : <Admin />}
    </div>
  );
}
