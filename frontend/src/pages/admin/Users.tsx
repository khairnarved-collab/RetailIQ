import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Users as UsersIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmButton, ErrorState, LoadingState, PageHeader } from "@/components/common";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { Role, User } from "@/services/types";
import { fmtDateTime } from "@/utils/format";
import { passwordProblems } from "@/pages/AuthPages";

export default function AdminUsers() {
  const { user: me } = useAuth();
  const { data, isLoading, error, refetch } = useApiQuery<User[]>(["admin-users"], "/admin/users");
  const update = useApiMutation(({ id, ...b }: { id: number; role?: Role; is_active?: boolean }) => api.patch(`/admin/users/${id}`, b), [["admin-users"]], "User updated");
  const del = useApiMutation((id: number) => api.del(`/admin/users/${id}`), [["admin-users"]], "User deleted");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ full_name: "", email: "", password: "", role: "analyst" as Role });
  const create = useApiMutation(() => api.post("/admin/users", f), [["admin-users"]], "User created");

  return (
    <div className="animate-fade-in">
      <PageHeader title="User management" icon={<UsersIcon className="h-6 w-6 text-primary" />} description="Create accounts, change roles and deactivate access."
        actions={<Button onClick={() => setOpen(true)}><Plus /> Add user</Button>} />
      {isLoading ? <LoadingState /> : error || !data ? <ErrorState error={error} onRetry={refetch} /> : (
        <Card>
          <Table>
            <TableHeader><TableRow><TableHead>User</TableHead><TableHead>Role</TableHead><TableHead>Active</TableHead><TableHead>Last login</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{data.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="min-w-[14rem]"><p className="font-medium">{u.full_name}{u.id === me?.id && <span className="text-muted-foreground"> (you)</span>}</p><p className="text-xs text-muted-foreground">{u.email}</p></TableCell>
                <TableCell>
                  <Select value={u.role} disabled={u.id === me?.id} onValueChange={(v) => update.mutate({ id: u.id, role: v as Role })}>
                    <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="admin">Admin</SelectItem><SelectItem value="analyst">Analyst</SelectItem></SelectContent>
                  </Select>
                </TableCell>
                <TableCell><Switch checked={u.is_active} disabled={u.id === me?.id} onCheckedChange={(v) => update.mutate({ id: u.id, is_active: v })} aria-label="Active" /></TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">{fmtDateTime(u.last_login_at)}</TableCell>
                <TableCell className="text-right">{u.id !== me?.id && (
                  <ConfirmButton variant="ghost" size="icon" className="text-critical" aria-label="Delete user" title={`Delete ${u.full_name}?`}
                    description="This permanently removes the account." onConfirm={() => del.mutate(u.id)}><Trash2 /></ConfirmButton>
                )}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        </Card>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add user</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label htmlFor="un">Full name</Label><Input id="un" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></div>
            <div className="space-y-1.5"><Label htmlFor="ue">Email</Label><Input id="ue" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
            <div className="space-y-1.5"><Label htmlFor="up">Temporary password</Label><Input id="up" type="text" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Role</Label>
              <Select value={f.role} onValueChange={(v) => setF({ ...f, role: v as Role })}><SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="analyst">Analyst: upload data, dashboards, forecasts, reports</SelectItem><SelectItem value="admin">Admin: all of the above, plus users & settings</SelectItem></SelectContent></Select></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={create.isPending} onClick={() => {
              const p = passwordProblems(f.password); if (p) return toast.error(p);
              create.mutate(undefined, { onSuccess: () => { setOpen(false); setF({ full_name: "", email: "", password: "", role: "analyst" }); } });
            }}>Create user</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
