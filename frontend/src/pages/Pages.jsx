import { useState, useEffect } from "react"; import api, { errMsg, inr, list } from "../services/api"; import { useAuth } from "../context/AuthContext";
import { Table, Filters, Msg, Badge, useFetch } from "../components/ui";

const run = async (fn, setM, done) => { try { const r = await fn(); setM({ ok: true, text: "Done." }); done && done(r); } catch (e) { setM({ ok: false, text: errMsg(e) }); } };
const Form = ({ fields, onSubmit, label }) => {
  const [v, setV] = useState({});
  return <form className="form" onSubmit={e => { e.preventDefault(); onSubmit(v, () => setV({})); }}>
    {fields.map(([k, p, t]) =>
      <input key={k} type={t || "text"} step={t === "number" ? "0.01" : undefined} placeholder={p} value={v[k] || ""} onChange={e => setV({ ...v, [k]: e.target.value })} required />)}
    <button>{label}</button>
  </form>;
};

export function Dashboard() {
  const { user } = useAuth(); const kind = { ADMIN: "admin", COLLECTION_AGENT: "agent", BRANCH_MANAGER: "branch", COMPANY_ADMIN: "company" }[user.role];
  const [f, setF] = useState({}), [d, setD] = useState(null), [err, setErr] = useState("");
  useEffect(() => { if (kind) api.get(`/dashboard/${kind}/`, { params: f }).then(r => setD(r.data)).catch(e => setErr(errMsg(e))); }, [kind, JSON.stringify(f)]);
  if (err) return <Msg m={{ text: err }} />; if (!d) return <p>Loading…</p>;
  const cards = [["Expected Collections", "expected_collections"], ["Total Collected", "total_collected"], ["Cash With Agents", "cash_with_agents"], ["Cash At Branches", "cash_at_branches"],
    ["Bank Deposited", "bank_deposited"], ["Settled Amount", "settled_amount"], ["Outstanding Amount", "outstanding_amount"], ["Discrepancies", "discrepancies"]];
  return <><h2>CMRS Dashboard</h2><Filters f={f} setF={setF} statuses={["COLLECTED", "SUBMITTED", "BRANCH_RECEIVED", "DEPOSITED", "SETTLED"]} />
    <div className="cards">{cards.map(([l, k]) => <div className="card" key={k}><small>{l}</small><b>{inr(d[k])}</b></div>)}</div>
    <h3>Recent Collections</h3><Table rows={d.recent_collections || []} cols={[["Customer", "customer_name"], ["Agent", "agent_name"], ["Amount", "amount"], ["Status", "status"]]} />
    <h3>Recent Reconciliations</h3><Table rows={d.recent_reconciliations || []} cols={[["Agent", "agent_name"], ["Expected", "expected_amount"], ["Received", "received_amount"], ["Difference", "difference"], ["Status", "status"]]} /></>;
}

export function Customers() {
  const { user } = useAuth(); const [q, setQ] = useState(""), [rows, load] = useFetch("/customers/", { search: q }), [m, setM] = useState(), [sel, setSel] = useState();
  const can = user.role === "ADMIN" || user.role === "BRANCH_MANAGER";
  return <><h2>Customers</h2><input placeholder="Search name / code / phone" value={q} onChange={e => setQ(e.target.value)} /><Msg m={m} />
    {can && <Form label="Add customer" fields={[["full_name", "Full name"], ["phone", "Phone"], ["email", "Email", "email"], ["address", "Address"], ...(user.role === "ADMIN" ? [["branch", "Branch ID", "number"]] : [])]}
      onSubmit={(v, reset) => run(() => api.post("/customers/", v), setM, () => { load(); reset(); })} />}
    <Table rows={rows} cols={[["ID", "id"], ["Code", "customer_code"], ["Name", "full_name"], ["Phone", "phone"], ["Branch", "branch_name"]]} actions={r => <button onClick={() => setSel(r)}>Details</button>} />
    {sel && <div className="modal" onClick={() => setSel()}><div className="box" onClick={e => e.stopPropagation()}><h3>{sel.full_name}</h3><p>ID: {sel.id} · Code: {sel.customer_code} · {sel.phone}<br />{sel.email}<br />{sel.address}</p><button onClick={() => setSel()}>Close</button></div></div>}</>;
}

export function Loans() {
  const { user } = useAuth(); const [rows, load] = useFetch("/loans/"), [m, setM] = useState(), [sel, setSel] = useState(), [sch, setSch] = useState([]), [rep, setRep] = useState([]);
  const open = async l => { setSel(l); setSch(list((await api.get(`/loans/${l.id}/schedule/`)).data)); setRep(list((await api.get(`/loans/${l.id}/repayments/`)).data)); };
  const can = user.role === "ADMIN" || user.role === "BRANCH_MANAGER";
  return <><h2>Loans</h2><Msg m={m} />
    {can && <Form label="Create loan" fields={[["customer", "Customer ID", "number"], ["principal_amount", "Principal", "number"], ["interest_amount", "Interest", "number"], ["start_date", "Start", "date"], ["end_date", "End", "date"], ["installments", "Installments", "number"]]}
      onSubmit={(v, reset) => run(() => api.post("/loans/", v), setM, () => { load(); reset(); })} />}
    <Table rows={rows} cols={[["Loan", "loan_number"], ["Customer", "customer_name"], ["Principal", "principal_amount"], ["Outstanding", "outstanding_amount"], ["Status", "status"]]} actions={r => <button onClick={() => open(r)}>View</button>} />
    {sel && <div className="box inline"><h3>{sel.loan_number} — outstanding {inr(sel.outstanding_amount)}</h3><h4>Repayment schedule</h4>
      <Table rows={sch} cols={[["Due date", "due_date"], ["Due", "due_amount"], ["Paid", "paid_amount"], ["Remaining", "remaining_amount"], ["Status", "status"]]} />
      <h4>Repayment history</h4><Table rows={rep} cols={[["Receipt", "receipt_number"], ["Date", "payment_date"], ["Amount", "amount"], ["Status", "status"]]} /></div>}</>;
}

export function Collect() {
  const [loans, loadLoans] = useFetch("/loans/", { status: "ACTIVE" }), [today, load] = useFetch("/agent/collections/today/"), [m, setM] = useState(), [loan, setLoan] = useState(""), [amt, setAmt] = useState(""), [mode, setMode] = useState("CASH");
  const [data, setData] = useState({ results: [], total: 0 });
  useEffect(() => { api.get("/agent/collections/today/").then(r => setData(r.data)); }, [m]);
  const pay = async (extra = {}) => {
    try {
      await api.post("/collections/", { loan, amount: amt, payment_mode: mode, ...extra });
      setM({ ok: true, text: "Payment recorded." });
      setAmt("");
      loadLoans();
      load();
    } catch (e) {
      const t = errMsg(e);
      setM({ ok: false, text: t });
      if (t.startsWith("Payment exceeds") && confirm(t + " Record as over-collection (flagged)?")) pay({ ...extra, allow_over: true });
      else if (t.startsWith("Duplicate collection") && confirm(t + " Record anyway?")) pay({ ...extra, confirm_duplicate: true });
    }
  };
  return <><h2>Agent Collection</h2><Msg m={m} />
    <form className="form" onSubmit={e => { e.preventDefault(); pay(); }}><select required value={loan} onChange={e => setLoan(e.target.value)}><option value="">Select customer loan…</option>
      {loans.map(l => <option key={l.id} value={l.id}>{l.customer_name} — {l.loan_number} (due {inr(l.outstanding_amount)})</option>)}</select>
      <input required type="number" step="0.01" placeholder="Amount" value={amt} onChange={e => setAmt(e.target.value)} />
      <select value={mode} onChange={e => setMode(e.target.value)}><option>CASH</option><option>UPI</option><option>CHEQUE</option></select><button>Record payment</button></form>
    <h3>Today's collections — {inr(data.total)}</h3><Table rows={data.results || []} cols={[["Receipt", "receipt_number"], ["Customer", "customer_name"], ["Amount", "amount"], ["Flag", "flag"], ["Status", "status"]]} />
    <button onClick={() => run(() => api.post("/cash-submissions/"), setM, () => { load(); loadLoans(); })}>Submit cash to branch</button></>;
}

export function Reconciliation() {
  const [f, setF] = useState({}), [rows, load] = useFetch("/reconciliation/", f), [m, setM] = useState();
  const act = (r, a, body) => run(() => api.post(`/cash-submissions/${r.cash_submission}/${a}/`, body), setM, load);
  return <><h2>Branch Reconciliation</h2><Filters f={f} setF={setF} statuses={["PENDING", "MATCHED", "DISCREPANCY", "APPROVED", "REJECTED"]} /><Msg m={m} />
    <Table rows={rows} cols={[["Submission", "submission_number"], ["Agent", "agent_name"], ["Expected", "expected_amount"], ["Received", "received_amount"], ["Difference", "difference"], ["Status", "status"]]}
      actions={r => ["PENDING", "MATCHED", "DISCREPANCY"].includes(r.status) && <>
        <button onClick={() => {
          const v = prompt("Cash actually received (₹):", r.received_amount && Number(r.received_amount) > 0 ? r.received_amount : r.expected_amount);
          if (v !== null && v.trim() !== "") act(r, "verify", { received_amount: v.trim() });
        }}>Verify</button>
        {r.status !== "PENDING" && <button onClick={() => {
          let remarks = "";
          if (Number(r.difference) !== 0) {
            const res = prompt("Remarks for discrepancy:", r.remarks || "");
            if (res === null) return;
            remarks = res.trim();
          }
          act(r, "approve", { remarks });
        }}>Approve</button>}
        <button className="danger" onClick={() => {
          const res = prompt("Reason for rejection:");
          if (res !== null && res.trim() !== "") act(r, "reject", { remarks: res.trim() });
        }}>Reject</button></>} /></>;
}

export function Deposits() {
  const { user } = useAuth(); const [rows, load] = useFetch("/deposits/"), [recs, loadRecs] = useFetch("/reconciliation/", { status: "APPROVED" }), [m, setM] = useState();
  const free = recs.filter(r => !rows.some(d => d.reconciliation === r.id)), [v, setV] = useState({});
  const reloadAll = () => { load(); loadRecs(); setV({}); };
  return <><h2>Bank Deposits</h2><Msg m={m} />
    {user.role === "BRANCH_MANAGER" && <form className="form" onSubmit={e => { e.preventDefault(); run(() => api.post("/deposits/", v), setM, reloadAll); }}>
      <select required value={v.reconciliation || ""} onChange={e => { const r = recs.find(x => String(x.id) === e.target.value); setV({ ...v, reconciliation: e.target.value, amount: r?.received_amount }); }}>
        <option value="">Approved reconciliation…</option>{free.map(r => <option key={r.id} value={r.id}>{r.submission_number} — {inr(r.received_amount)}</option>)}
      </select>
      <input required placeholder="Bank" value={v.bank_name || ""} onChange={e => setV({ ...v, bank_name: e.target.value })} />
      <input required type="number" step="0.01" placeholder="Amount" value={v.amount || ""} onChange={e => setV({ ...v, amount: e.target.value })} />
      <input required type="date" value={v.deposit_date || ""} onChange={e => setV({ ...v, deposit_date: e.target.value })} />
      <input required placeholder="Transaction reference" value={v.transaction_reference || ""} onChange={e => setV({ ...v, transaction_reference: e.target.value })} />
      <button>Create deposit</button></form>}
    <Table rows={rows} cols={[["Deposit", "deposit_number"], ["Bank", "bank_name"], ["Amount", "amount"], ["Date", "deposit_date"], ["Reference", "transaction_reference"], ["Status", "status"]]} /></>;
}

export function Settlements() {
  const { user } = useAuth(); const [rows, load] = useFetch("/settlements/"), [m, setM] = useState();
  return <><h2>Settlement</h2><Msg m={m} /><Table rows={rows} cols={[["Deposit", "deposit_number"], ["Reference", "transaction_reference"], ["Settlement amount", "settlement_amount"], ["Status", "status"], ["Settled on", r => r.settlement_date || "—"]]}
    actions={r => ["ADMIN", "COMPANY_ADMIN"].includes(user.role) && r.status === "PENDING" && <><button onClick={() => run(() => api.post(`/settlements/${r.id}/settle/`), setM, load)}>Settle</button>
      <button className="danger" onClick={() => {
        const res = prompt("Failure reason:");
        if (res !== null && res.trim() !== "") run(() => api.post(`/settlements/${r.id}/fail/`, { remarks: res.trim() }), setM, load);
      }}>Fail</button></>} /></>;
}

export function Reports() {
  const [f, setF] = useState({}), [rows] = useFetch("/collections/", f), total = rows.reduce((s, r) => s + Number(r.amount), 0);
  return <><h2>Reports — Collections</h2><Filters f={f} setF={setF} statuses={["COLLECTED", "SUBMITTED", "BRANCH_RECEIVED", "DEPOSITED", "SETTLED"]} /><p>Total: <b>{inr(total)}</b></p>
    <Table rows={rows} cols={[["Receipt", "receipt_number"], ["Date", "payment_date"], ["Customer", "customer_name"], ["Agent", "agent_name"], ["Amount", "amount"], ["Status", "status"]]} /></>;
}
