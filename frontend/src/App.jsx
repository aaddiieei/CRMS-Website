import { useState, createElement } from "react"; import { NavLink, Navigate, Route, Routes } from "react-router-dom"; import { useAuth } from "./context/AuthContext"; import { errMsg } from "./services/api";
import * as P from "./pages/Pages.jsx";
const A = "ADMIN", G = "COLLECTION_AGENT", B = "BRANCH_MANAGER", C = "COMPANY_ADMIN";
const NAV = [["/", "Dashboard", P.Dashboard, [A, G, B, C]], ["/customers", "Customers", P.Customers, [A, G, B, C]], ["/loans", "Loans", P.Loans, [A, G, B, C]],
  ["/collect", "Agent Collection", P.Collect, [A, G]], ["/reconciliation", "Branch Reconciliation", P.Reconciliation, [A, B, C]],
  ["/deposits", "Bank Deposits", P.Deposits, [A, B, C]], ["/settlements", "Settlement", P.Settlements, [A, B, C]], ["/reports", "Reports", P.Reports, [A, B, C]]];
function Login() {
  const { login } = useAuth(); const [u, setU] = useState(""), [p, setP] = useState(""), [e, setE] = useState("");
  return <div className="login"><form onSubmit={async ev => { ev.preventDefault(); try { await login(u, p); } catch (x) { setE(x.response?.status === 401 ? "Invalid username or password." : errMsg(x)); } }}>
    <h1>CMRS</h1><p className="muted">Cash Management & Reconciliation System</p><input placeholder="Username" value={u} onChange={x => setU(x.target.value)} required />
    <input type="password" placeholder="Password" value={p} onChange={x => setP(x.target.value)} required />{e && <div className="msg bad">{e}</div>}<button>Login</button></form></div>;
}
export default function App() {
  const { user, loading, logout } = useAuth(), [open, setOpen] = useState(false);
  if (loading) return <p style={{ padding: 20 }}>Loading…</p>;
  if (!user) return <Routes><Route path="/login" element={<Login />} /><Route path="*" element={<Navigate to="/login" />} /></Routes>;
  const nav = NAV.filter(n => n[3].includes(user.role));
  return <div className="app"><header><button className="menu" onClick={() => setOpen(!open)}>☰</button><b>CMRS</b><span className="grow" />
    <span>{user.first_name || user.username} · {user.role.replace("_", " ")}</span><button onClick={logout}>Logout</button></header>
    <div className="body"><nav className={open ? "open" : ""}>{nav.map(n => <NavLink key={n[0]} to={n[0]} end onClick={() => setOpen(false)}>{n[1]}</NavLink>)}</nav>
      <main><Routes>{nav.map(n => <Route key={n[0]} path={n[0]} element={createElement(n[2])} />)}<Route path="/login" element={<Navigate to="/" />} /><Route path="*" element={<p>Page not found or not permitted for your role.</p>} /></Routes></main></div></div>;
}
