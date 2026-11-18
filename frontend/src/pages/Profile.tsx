import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { KeyRound, ShieldCheck, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { PageHeader } from "@/components/common";
import { initials } from "@/layouts/AppLayout";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { User } from "@/services/types";
import { fmtDateTime } from "@/utils/format";
import { passwordProblems } from "@/pages/AuthPages";

export default function Profile() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [title, setTitle] = useState(user?.job_title ?? "");
  const [savingP, setSavingP] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [savingPw, setSavingPw] = useState(false);

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setSavingP(true);
    try { setUser(await api.patch<User>("/auth/me", { full_name: name, job_title: title })); toast.success("Profile updated"); }
    catch (err) { toast.error((err as Error).message); } finally { setSavingP(false); }
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault();
    const p = passwordProblems(pw.next);
    if (p) return toast.error(p);
    if (pw.next !== pw.confirm) return toast.error("New passwords do not match");
    setSavingPw(true);
    try { await api.post("/auth/change-password", { current_password: pw.current, new_password: pw.next }); toast.success("Password changed"); setPw({ current: "", next: "", confirm: "" }); }
    catch (err) { toast.error((err as Error).message); } finally { setSavingPw(false); }
  };
  if (!user) return null;
  return (
    <div className="mx-auto max-w-3xl animate-fade-in">
      <PageHeader title="Your profile" />
      <Card className="mb-5"><CardContent className="flex items-center gap-4 p-5">
        <Avatar className="h-14 w-14"><AvatarFallback className="text-lg">{initials(user.full_name)}</AvatarFallback></Avatar>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{user.full_name}</p>
          <p className="truncate text-sm text-muted-foreground">{user.email}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant={user.role === "admin" ? "default" : "secondary"}><ShieldCheck />{user.role}</Badge>
            Member since {fmtDateTime(user.created_at)}
          </div>
        </div>
      </CardContent></Card>
      <div className="grid gap-5 md:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><UserCog className="h-4 w-4" /> Details</CardTitle></CardHeader>
          <CardContent><form onSubmit={saveProfile} className="space-y-3">
            <div className="space-y-1.5"><Label htmlFor="n">Full name</Label><Input id="n" value={name} onChange={(e) => setName(e.target.value)} minLength={2} required /></div>
            <div className="space-y-1.5"><Label htmlFor="t">Job title</Label><Input id="t" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Business Analyst" /></div>
            <div className="space-y-1.5"><Label>Email</Label><Input value={user.email} disabled /></div>
            <Button type="submit" loading={savingP}>Save changes</Button>
          </form></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Change password</CardTitle>
          <CardDescription>At least 8 characters with a letter and a number.</CardDescription></CardHeader>
          <CardContent><form onSubmit={changePw} className="space-y-3">
            <div className="space-y-1.5"><Label htmlFor="c">Current password</Label><Input id="c" type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} required /></div>
            <div className="space-y-1.5"><Label htmlFor="p1">New password</Label><Input id="p1" type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required /></div>
            <div className="space-y-1.5"><Label htmlFor="p2">Confirm new password</Label><Input id="p2" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} required /></div>
            <Button type="submit" loading={savingPw}>Update password</Button>
          </form></CardContent></Card>
      </div>
    </div>
  );
}
