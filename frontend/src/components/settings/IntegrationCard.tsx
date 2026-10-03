import { Copy, KeyRound, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import type { ApiClientOut } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/hooks/useAuth";
import { useApiClientMutations, useApiClients, useIntegrationActions } from "@/hooks/useIntegration";
import { formatDateTime } from "@/lib/format";
import { showError } from "@/lib/forms";

/** FR-34 API keys for the payroll system: created here, shown once, revoked when no longer used. */
export function ApiKeysCard() {
  const { timezone } = useAuth();
  const clients = useApiClients();
  const { create, toggle, revoke } = useApiClientMutations();
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<ApiClientOut | null>(null);

  const add = async () => {
    try {
      const result = await create.mutateAsync(name.trim());
      setNewKey(result.data.api_key);
      setName("");
    } catch (error) {
      showError(error);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">API keys</CardTitle>
        <CardDescription>
          The payroll system reads finalised attendance from <code>GET /api/v1/integration/attendance?date=YYYY-MM-DD</code> with
          the <code>X-API-Key</code> header.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="api-client-name">New key for</Label>
            <Input id="api-client-name" placeholder="Payroll system" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button onClick={() => void add()} disabled={!name.trim() || create.isPending}>
            <Plus aria-hidden /> Create key
          </Button>
        </div>
        {(clients.data?.data.length ?? 0) > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Active</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.data?.data.map((client) => (
                <TableRow key={client.id}>
                  <TableCell className="font-medium">{client.name}</TableCell>
                  <TableCell className="font-mono text-xs">ft_{client.key_prefix}_…</TableCell>
                  <TableCell>{formatDateTime(client.last_used_at, timezone)}</TableCell>
                  <TableCell>
                    <Switch
                      aria-label={`${client.name} active`}
                      checked={client.is_active}
                      onCheckedChange={(active) => toggle.mutate({ id: client.id, active }, { onError: showError })}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" aria-label={`Revoke ${client.name}`} onClick={() => setRevoking(client)}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <Dialog open={newKey !== null} onOpenChange={(open) => !open && setNewKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="size-5" aria-hidden /> Copy the API key now
            </DialogTitle>
            <DialogDescription>It is shown only once. FaceTrack keeps only a hash; a lost key must be replaced.</DialogDescription>
          </DialogHeader>
          <Input readOnly value={newKey ?? ""} className="font-mono text-xs" onFocus={(e) => e.target.select()} />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                void navigator.clipboard?.writeText(newKey ?? "").then(() => toast.success("Copied."));
              }}
            >
              <Copy aria-hidden /> Copy
            </Button>
            <Button onClick={() => setNewKey(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke the key for ${revoking?.name ?? ""}?`}
        description="Requests with this key stop working at once. This cannot be undone."
        confirmLabel="Revoke key"
        pending={revoke.isPending}
        onConfirm={async () => {
          if (!revoking) return;
          try {
            await revoke.mutateAsync(revoking.id);
            setRevoking(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </Card>
  );
}

/** Manual runs of the scheduled integrations (FR-12, FR-35). */
export function IntegrationActionsCard() {
  const { push, sync } = useIntegrationActions();
  const [date, setDate] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Run now</CardTitle>
        <CardDescription>
          The payroll push and HR sync also run daily at the times above. A push without a date sends every finalised day
          changed since the last delivery.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="push-date">Resend one work date (optional)</Label>
          <Input id="push-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <Button variant="outline" onClick={() => push.mutate(date || null, { onError: showError })} disabled={push.isPending}>
          <Send aria-hidden /> Push to payroll
        </Button>
        <Button variant="outline" onClick={() => sync.mutate(undefined, { onError: showError })} disabled={sync.isPending}>
          <RefreshCw aria-hidden /> Sync from HR
        </Button>
        <StatusBadge tone="info" label="Results appear in the audit log" />
      </CardContent>
    </Card>
  );
}
