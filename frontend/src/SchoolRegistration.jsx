import { useState } from "react";
import { Alert, Button, Input, Select } from "./ui";
import "./pub.css";

const EMPTY = { school_name: "", proposed_school_code: "", school_type: "secondary", school_phone: "", county: "", administrator_name: "", administrator_username: "", administrator_email: "", administrator_phone: "", password: "", confirm_password: "", authorized: false };

export default function SchoolRegistration({ onBack, onSignIn }) {
  const [form, setForm] = useState(EMPTY), [error, setError] = useState(""), [busy, setBusy] = useState(false), [registration, setRegistration] = useState(null), [code, setCode] = useState(""), [verified, setVerified] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = async () => {
    setError(""); setBusy(true);
    const r = await fetch("/api/school-registration/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    const j = await r.json().catch(() => ({})); setBusy(false);
    if (!r.ok) return setError(j.errors ? Object.values(j.errors).join(" ") : (j.detail || "Could not submit registration."));
    setRegistration(j);
  };
  const verify = async () => {
    setError(""); setBusy(true);
    const r = await fetch("/api/school-registration/verify/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reference: registration.reference, code }) });
    const j = await r.json().catch(() => ({})); setBusy(false);
    if (!r.ok) return setError(j.detail || "Verification failed.");
    setVerified(true);
  };
  if (verified) return <div className="mu-pub"><div className="mu-pub-in"><div className="mu-pub-card"><h2>Email verified</h2><Alert kind="ok">Your school registration is ready for Marian review.</Alert><p>Keep reference <b>{registration.reference}</b>. You may use it to check the application status.</p><Button kind="teal" onClick={onSignIn}>Sign in</Button></div></div></div>;
  if (registration) return <div className="mu-pub"><div className="mu-pub-in"><Button kind="ghost" onClick={onBack}>← Back</Button><div className="mu-pub-card"><h2>Verify administrator email</h2><p>Enter the six-digit code sent to the administrator email. Reference: <b>{registration.reference}</b>.</p><Input label="Verification code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />{error && <Alert kind="err">{error}</Alert>}<Button kind="teal" busy={busy} disabled={code.length !== 6} onClick={verify}>Verify email</Button></div></div></div>;
  return <div className="mu-pub"><div className="mu-pub-in"><Button kind="ghost" onClick={onBack}>← Back</Button><div className="mu-pub-card"><h2>Register your school</h2><p>Submit your school for secure Marian review. An administrator email is required.</p><div className="mu-pub-form"><Input label="School name" value={form.school_name} onChange={set("school_name")} /><Input label="School code" value={form.proposed_school_code} onChange={set("proposed_school_code")} /><Select label="School type" value={form.school_type} onChange={set("school_type")}><option value="primary">Primary</option><option value="junior">Junior school</option><option value="secondary">Secondary</option><option value="combined">Combined / other</option></Select><Input label="School phone" value={form.school_phone} onChange={set("school_phone")} /><Input label="County" value={form.county} onChange={set("county")} /><Input label="Administrator name" value={form.administrator_name} onChange={set("administrator_name")} /><Input label="Administrator username" autoCapitalize="none" value={form.administrator_username} onChange={set("administrator_username")} /><Input label="Administrator email" type="email" value={form.administrator_email} onChange={set("administrator_email")} /><Input label="Administrator phone" value={form.administrator_phone} onChange={set("administrator_phone")} /><Input label="Password" type="password" value={form.password} onChange={set("password")} /><Input label="Confirm password" type="password" value={form.confirm_password} onChange={set("confirm_password")} /><label><input type="checkbox" checked={form.authorized} onChange={set("authorized")} /> I am authorized to register this school.</label>{error && <Alert kind="err">{error}</Alert>}<Button kind="teal" busy={busy} onClick={submit}>Submit registration</Button></div></div></div></div>;
}
