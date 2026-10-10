import { useEffect, useState, useCallback } from "react"; import api, { errMsg, inr, list } from "../services/api";
export const Badge = ({ s }) => <span className={`badge b-${String(s).toLowerCase()}`}>{String(s).replace("_", " ")}</span>;
export function useFetch(url, params) {
  const [data, set] = useState([]), [err, setErr] = useState(""); const key = JSON.stringify(params);
  const load = useCallback(() => api.get(url, { params }).then(r => set(list(r.data))).catch(e => setErr(errMsg(e))), [url, key]);
  useEffect(() => { load(); }, [load]); return [data, load, err];
}
export const Msg = ({ m }) => m ? <div className={`msg ${m.ok ? "ok" : "bad"}`}>{m.text}</div> : null;
export function Table({ rows, cols, actions }) {
  const cell = (r, k) => { const v = typeof k === "function" ? k(r) : r[k];
    return typeof k === "string" && /amount|difference|received|total|expected|principal|outstanding/.test(k) ? inr(v) : typeof k === "string" && /status$/.test(k) ? <Badge s={v} /> : v; };
  return <div className="tbl"><table><thead><tr>{cols.map(c => <th key={c[0]}>{c[0]}</th>)}{actions && <th></th>}</tr></thead>
    <tbody>{rows.length ? rows.map(r => <tr key={r.id}>{cols.map(c => <td key={c[0]}>{cell(r, c[1])}</td>)}{actions && <td className="act">{actions(r)}</td>}</tr>)
      : <tr><td colSpan={cols.length + 1} className="muted">No records found.</td></tr>}</tbody></table></div>;
}
export const Filters = ({ f, setF, statuses = [] }) => <div className="filters">
  <input type="date" value={f.date || ""} onChange={e => setF({ ...f, date: e.target.value })} />
  <select value={f.status || ""} onChange={e => setF({ ...f, status: e.target.value })}><option value="">All statuses</option>{statuses.map(s => <option key={s}>{s}</option>)}</select>
  <input placeholder="Branch ID" size="8" value={f.branch || ""} onChange={e => setF({ ...f, branch: e.target.value })} />
  <input placeholder="Agent ID" size="8" value={f.agent || ""} onChange={e => setF({ ...f, agent: e.target.value })} /></div>;
