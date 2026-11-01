import { useEffect, useState, type FormEvent } from "react";
import { Activity, ArrowRight, ArrowUpRight, BrainCircuit, ChartNoAxesCombined, ChevronRight, CircleHelp, CreditCard, Eye, EyeOff, Fingerprint, LayoutDashboard, LogOut, Menu, ScrollText, Shield, ShieldCheck, SlidersHorizontal, Users, X } from "lucide-react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, errorMessage, session } from "./api";
import { Notice, Status } from "./components";
import type { Role, User } from "./types";
import { OverviewPage, RiskPage } from "./pages/Analytics";
import { TransactionsPage } from "./pages/Transactions";
import { ModelsPage } from "./pages/Models";
import { AlertsPage, AuditPage, RulesPage, UsersPage } from "./pages/Operations";

const navigation = [
  { to: "/", title: "Overview", icon: LayoutDashboard, roles: ["admin", "analyst", "viewer"] },
  { to: "/transactions", title: "Transactions", icon: CreditCard, roles: ["admin", "analyst", "viewer"] },
  { to: "/alerts", title: "Fraud alerts", icon: Shield, roles: ["admin", "analyst"] },
  { to: "/analytics", title: "Risk analytics", icon: ChartNoAxesCombined, roles: ["admin", "analyst", "viewer"] },
  { to: "/models", title: "Model studio", icon: BrainCircuit, roles: ["admin", "analyst", "viewer"] },
  { to: "/rules", title: "Detection rules", icon: SlidersHorizontal, roles: ["admin"] },
  { to: "/users", title: "Team members", icon: Users, roles: ["admin"] },
  { to: "/audit", title: "Audit trail", icon: ScrollText, roles: ["admin"] },
];

function Brand() {
  return <div className="brand"><div className="brand-mark"><Activity size={23} /></div><div>foresight<span>RISK INTELLIGENCE</span></div></div>;
}

function Login({ onLogin, notice }: { onLogin: (user: User) => void; notice: string }) {
  const [register, setRegister] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setMessage(""); setBusy(true);
    const form = new FormData(event.currentTarget);
    const credentials = { email: String(form.get("email")), password: String(form.get("password")) };
    try {
      if (register) {
        await api<User>("/api/auth/register", { method: "POST", body: JSON.stringify({ ...credentials, full_name: form.get("full_name") }) });
        setRegister(false);
        setMessage("Your viewer account is ready. Sign in to continue. An administrator can grant analyst access for training.");
      } else {
        const result = await api<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify(credentials) });
        session.set(result.access_token);
        try {
          const user = await api<User>("/api/auth/me");
          if (!user.is_active) throw new Error("Your account is inactive. Contact your administrator.");
          onLogin(user);
        } catch (failure) { session.clear(); throw failure; }
      }
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  async function handleGoogleLogin() {
    setError(""); setBusy(true);
    try {
      const googleData = {
        email: "user@gmail.com",
        full_name: "Google User",
        token: "mock_google_token"
      };
      const result = await api<{ access_token: string }>("/api/auth/google", { method: "POST", body: JSON.stringify(googleData) });
      session.set(result.access_token);
      const user = await api<User>("/api/auth/me");
      if (!user.is_active) throw new Error("Your account is inactive. Contact your administrator.");
      onLogin(user);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <div className="login-layout"><aside className="login-hero"><Brand /><div className="hero-copy"><div className="pill"><span className="dot" />THE CLARITY TO ACT</div><h1>See the risk.<br />Stay a step<br /><em>ahead.</em></h1><p>A connected workspace for financial intelligence, fraud operations, and explainable machine learning.</p><div className="hero-grid"><div><ShieldCheck /><strong>Intelligent detection</strong><span>Rules and models, working together.</span></div><div><Fingerprint /><strong>Accountable decisions</strong><span>A clear trail behind every action.</span></div></div></div><small>FORESIGHT / FINANCIAL RISK OPERATIONS</small></aside><main className="login-main"><div className="login-form"><div className="eyebrow">YOUR OPERATIONS, IN FOCUS</div><h2>{register ? "Create your account" : "Welcome back."}</h2><p>{register ? "Start with read-only access to your risk workspace." : "Sign in to your financial intelligence workspace."}</p>{notice && <Notice error>{notice}</Notice>}{message && <Notice>{message}</Notice>}{error && <Notice error>{error}</Notice>}<form onSubmit={submit}>{register && <label>Full name<input name="full_name" autoComplete="name" required maxLength={255} placeholder="Your full name" /></label>}<label>Email address<input name="email" type="email" autoComplete="username" required placeholder="you@company.com" /></label><label>Password<div className="password-input-wrapper"><input name="password" type={showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 8 : 1} maxLength={128} placeholder="Enter your password" /><button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label><button className="button primary wide" disabled={busy}>{busy ? "Please wait..." : register ? "Create account" : "Sign in to workspace"}<ArrowRight size={17} /></button></form><div className="divider"><span>or</span></div><button className="button secondary wide google-login" disabled={busy} onClick={handleGoogleLogin}>Continue with Google</button><div className="login-switch">{register ? "Already have an account?" : "New to the platform?"} <button className="text-button" onClick={() => { setRegister(!register); setError(""); }}>{register ? "Sign in" : "Create an account"}</button></div><div className="security-note"><ShieldCheck size={16} />Secure access. Role-based permissions.</div></div></main></div>;
}

function Restricted({ role, allowed, children }: { role: Role; allowed: Role[]; children: React.ReactNode }) {
  return allowed.includes(role) ? children : <Notice error>This section is restricted to {allowed.join(" and ")} accounts. Ask your administrator to update your role.</Notice>;
}

export default function App() {
  const [user, setUser] = useState<User>();
  const [loading, setLoading] = useState(Boolean(session.get()));
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [menu, setMenu] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const location = useLocation();
  useEffect(() => {
    let active = true;
    if (session.get()) {
      setLoading(true); setError("");
      api<User>("/api/auth/me").then((value) => {
        if (!value.is_active) { session.clear(); throw new Error("Your account is inactive. Contact your administrator."); }
        if (active) setUser(value);
      }).catch((failure) => { if (active) setError(errorMessage(failure)); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [attempt]);
  useEffect(() => {
    function expired() { setUser(undefined); setNotice("Your session expired. Please sign in again."); }
    globalThis.addEventListener("session-expired", expired);
    return () => globalThis.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => { setMenu(false); }, [location.pathname]);
  if (loading) return <Status loading error="" retry={() => {}} />;
  if (!user && error && session.get()) return <div className="connection-error"><Status loading={false} error={error} retry={() => setAttempt(attempt + 1)} /><button className="button secondary" onClick={() => { session.clear(); setError(""); }}>Back to sign in</button></div>;
  if (!user) return <Login onLogin={setUser} notice={notice || error} />;
  const current = navigation.find((item) => item.to === location.pathname);
  function confirmAndLogout() { setConfirmLogout(true); }
  function logout() { session.clear(); setUser(undefined); setError(""); setNotice(""); setConfirmLogout(false); }
  return <div className="app-shell">
    {menu && <button className="sidebar-overlay" aria-label="Close navigation overlay" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? "open" : ""}`}><Link to="/" className="brand-link"><Brand /></Link><button className="mobile-close icon-button" onClick={() => setMenu(false)} aria-label="Close navigation"><X /></button><Link to={user.role === "viewer" ? "/" : "/alerts"} className="workspace-label" title={user.role === "viewer" ? "Open overview" : "Open fraud review queue"} onClick={() => setMenu(false)}><div className="workspace-icon"><ShieldCheck size={18} /></div><div>Fraud operations<small>{user.role === "viewer" ? "Risk overview" : "Review queue & alerts"}</small></div><ChevronRight size={15} /></Link><div className="nav-label">WORKSPACE</div><nav>{navigation.filter((item) => item.roles.includes(user.role)).map(({ to, title, icon: Icon }) => <NavLink to={to} end={to === "/"} key={to}><Icon size={19} /><span>{title}</span></NavLink>)}</nav><div className="sidebar-bottom"><div className="sidebar-callout"><BrainCircuit size={23} /><strong>From signals to decisions.</strong><p>Train, evaluate, and compare fraud detection models.</p><Link to="/models">Explore model studio <ArrowUpRight size={15} /></Link></div><div className="user-profile"><div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div><div><strong>{user.full_name}</strong><small>{user.role} account</small></div></div></div></aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenu(true)}><Menu /></button><span>Workspace</span><ChevronRight size={13} /><strong>{current?.title || "Not found"}</strong></div><div className="topbar-right"><span className="workspace-status"><span className="dot" />Authenticated workspace</span><a href="/backend/api/docs" target="_blank" rel="noreferrer" title="API documentation" className="icon-button" aria-label="API documentation"><CircleHelp size={19} /></a><div className="profile-menu"><button className="avatar small" onClick={() => setProfileOpen(!profileOpen)} aria-label="User profile">{user.full_name.slice(0, 1).toUpperCase()}</button>{profileOpen && <div className="profile-dropdown"><button className="menu-item" onClick={() => { setProfileOpen(false); }}><strong>{user.full_name}</strong><span>{user.email}</span></button><hr /><button className="menu-item" onClick={() => { setProfileOpen(false); confirmAndLogout(); }}><LogOut size={16} />Sign out</button></div>}</div></div></header>
      <main className="main-content"><Routes>
        <Route path="/" element={<OverviewPage user={user} />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/analytics" element={<RiskPage />} />
        <Route path="/models" element={<ModelsPage user={user} />} />
        <Route path="/alerts" element={<Restricted role={user.role} allowed={["admin", "analyst"]}><AlertsPage /></Restricted>} />
        <Route path="/rules" element={<Restricted role={user.role} allowed={["admin"]}><RulesPage user={user} /></Restricted>} />
        <Route path="/users" element={<Restricted role={user.role} allowed={["admin"]}><UsersPage user={user} /></Restricted>} />
        <Route path="/audit" element={<Restricted role={user.role} allowed={["admin"]}><AuditPage /></Restricted>} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<div className="state"><h1>Page not found</h1><Link to="/">Return to overview</Link></div>} />
      </Routes></main><footer className="footer"><span>FORESIGHT <span className="muted">/ Risk intelligence, made clear.</span></span><span>Financial Risk & Fraud Detection</span></footer>
    </div>
    {confirmLogout && <div className="modal-backdrop"><section role="dialog" aria-modal="true" className="modal logout-confirm"><header><h2>Confirm sign out</h2></header><div className="modal-body"><p>Are you sure you want to sign out?</p></div><div className="modal-actions"><button className="button secondary" onClick={() => setConfirmLogout(false)}>Cancel</button><button className="button primary" onClick={logout}>Sign out</button></div></section></div>}
  </div>;
}
