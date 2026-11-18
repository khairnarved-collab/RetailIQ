import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Eye, EyeOff, KeyRound, Sparkles } from "lucide-react";
import AuthLayout from "@/layouts/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";

export function passwordProblems(pw: string): string | null {
  if (pw.length < 8) return "Use at least 8 characters";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Include at least one letter and one number";
  return null;
}

function PasswordInput({ id, value, onChange, autoComplete }: { id: string; value: string; onChange: (v: string) => void; autoComplete: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={autoComplete} required className="pr-10" />
      <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:text-foreground">
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent, creds?: [string, string]) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(...(creds ?? [email, password]));
      toast.success(`Welcome back, ${u.full_name.split(" ")[0]}!`);
      nav(loc.state?.from ?? "/app/dashboard", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Log in to RetailIQ" subtitle="Welcome back. Enter your details to continue."
      footer={<>New to RetailIQ? <Link to="/signup" className="font-medium text-primary hover:underline">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="space-y-2">
          <div className="flex items-center justify-between"><Label htmlFor="password">Password</Label>
            <Link to="/forgot-password" className="text-xs font-medium text-primary hover:underline">Forgot password?</Link></div>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
        </div>
        {error && <p role="alert" className="rounded-lg bg-critical/10 px-3 py-2 text-sm text-critical">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Log in</Button>
      </form>
      <div className="mt-6 rounded-xl border bg-muted/40 p-4">
        <p className="flex items-center gap-1.5 text-sm font-medium"><Sparkles className="h-4 w-4 text-primary" /> Demo accounts</p>
        <p className="mt-1 text-xs text-muted-foreground">Explore with the synthetic sample data. One click logs you in.</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" disabled={busy} onClick={(e) => submit(e, ["admin@retailiq.dev", "Admin@12345"])}>Admin demo</Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={(e) => submit(e, ["analyst@retailiq.dev", "Analyst@12345"])}>Analyst demo</Button>
        </div>
      </div>
    </AuthLayout>
  );
}

export function Signup() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = passwordProblems(password);
    if (p) return setError(p);
    if (password !== confirm) return setError("Passwords do not match");
    setBusy(true);
    setError(null);
    try {
      await register(name, email, password);
      toast.success("Account created. Welcome to RetailIQ!");
      nav("/app/dashboard", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="Start turning retail data into decisions."
      footer={<>Already have an account? <Link to="/login" className="font-medium text-primary hover:underline">Log in</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="name">Full name</Label>
          <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></div>
        <div className="space-y-2"><Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="space-y-2"><Label htmlFor="password">Password</Label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" />
          <p className="text-xs text-muted-foreground">At least 8 characters, with a letter and a number.</p></div>
        <div className="space-y-2"><Label htmlFor="confirm">Confirm password</Label>
          <PasswordInput id="confirm" value={confirm} onChange={setConfirm} autoComplete="new-password" /></div>
        {error && <p role="alert" className="rounded-lg bg-critical/10 px-3 py-2 text-sm text-critical">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Create account</Button>
        <p className="text-center text-xs text-muted-foreground">New accounts get the Analyst role. An admin can change roles.</p>
      </form>
    </AuthLayout>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ message: string; dev_reset_token?: string; dev_note?: string } | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try { setResult(await api.post("/auth/forgot-password", { email })); }
    catch (err) { toast.error((err as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Reset your password" subtitle="Enter your email and we'll create a reset link."
      footer={<Link to="/login" className="font-medium text-primary hover:underline">Back to log in</Link>}>
      {result ? (
        <div className="space-y-4">
          <p className="rounded-lg bg-success/10 px-3 py-2.5 text-sm">{result.message}</p>
          {result.dev_reset_token && (
            <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
              <p className="font-medium">Development mode</p>
              <p className="mt-1 text-xs text-muted-foreground">{result.dev_note}</p>
              <Button asChild className="mt-3 w-full"><Link to={`/reset-password?token=${encodeURIComponent(result.dev_reset_token)}`}><KeyRound /> Open reset link</Link></Button>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2"><Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
          <Button type="submit" className="w-full" loading={busy}>Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = passwordProblems(password);
    if (p) return setError(p);
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      toast.success("Password reset. Please log in.");
      nav("/login");
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Choose a new password" footer={<Link to="/login" className="font-medium text-primary hover:underline">Back to log in</Link>}>
      <form onSubmit={submit} className="space-y-4">
        {!params.get("token") && (
          <div className="space-y-2"><Label htmlFor="token">Reset token</Label>
            <Input id="token" value={token} onChange={(e) => setToken(e.target.value)} required /></div>
        )}
        <div className="space-y-2"><Label htmlFor="password">New password</Label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" /></div>
        {error && <p role="alert" className="rounded-lg bg-critical/10 px-3 py-2 text-sm text-critical">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Reset password</Button>
      </form>
    </AuthLayout>
  );
}
