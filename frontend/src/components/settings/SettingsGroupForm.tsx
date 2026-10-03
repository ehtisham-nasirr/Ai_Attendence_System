import { useMemo, useState } from "react";

import type { SettingItem } from "@/api/generated/model";
import { toApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { SettingField } from "@/components/settings/SettingField";
import { Button } from "@/components/ui/button";
import { useUpdateSettings } from "@/hooks/useSettings";
import { lowersStrictness, settingKind, settingLabel } from "@/lib/settingsMeta";
import { toast } from "sonner";

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Edits one group of settings (FR-38). Only changed keys are sent; the API validates each key.
 * Changes that make recognition less strict need an explicit confirmation.
 */
export function SettingsGroupForm({ items, title }: { items: SettingItem[]; title?: string }) {
  const update = useUpdateSettings();
  const saved = useMemo(() => Object.fromEntries(items.map((item) => [item.key, item.value])), [items]);
  const [draft, setDraft] = useState<Record<string, unknown>>(saved);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmLowering, setConfirmLowering] = useState<string[] | null>(null);

  const changed = items
    .filter((item) => settingKind(item.key, item.default, item.secret) !== "hidden")
    .filter((item) => {
      const value = draft[item.key];
      if (item.secret) return typeof value === "string" && value !== "" && value !== "********";
      return !same(value, saved[item.key]);
    })
    .map((item) => item.key);

  const save = async () => {
    setErrors({});
    try {
      await update.mutateAsync(Object.fromEntries(changed.map((key) => [key, draft[key]])));
      setConfirmLowering(null);
    } catch (error) {
      const apiError = toApiError(error);
      setErrors(Object.fromEntries(Object.entries(apiError.fieldErrors).map(([key, messages]) => [key, messages.join(" ")])));
      setConfirmLowering(null);
      if (Object.keys(apiError.fieldErrors).length === 0) toast.error(apiError.message);
    }
  };

  const onSave = () => {
    const lowering = changed.filter((key) => lowersStrictness(key, saved[key], draft[key]));
    if (lowering.length > 0) setConfirmLowering(lowering);
    else void save();
  };

  return (
    <div className="space-y-2">
      {title && <h3 className="font-medium">{title}</h3>}
      <div className="divide-y">
        {items.map((item) => (
          <SettingField
            key={item.key}
            item={item}
            value={draft[item.key]}
            error={errors[item.key]}
            onChange={(value) => setDraft((current) => ({ ...current, [item.key]: value }))}
          />
        ))}
      </div>
      <div className="flex items-center gap-2 pt-2">
        <Button onClick={onSave} disabled={changed.length === 0 || update.isPending}>
          {update.isPending ? "Saving…" : changed.length ? `Save ${changed.length} change${changed.length === 1 ? "" : "s"}` : "No changes"}
        </Button>
        {changed.length > 0 && (
          <Button
            variant="ghost"
            onClick={() => {
              setDraft(saved);
              setErrors({});
            }}
          >
            Discard
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={confirmLowering !== null}
        onOpenChange={(open) => !open && setConfirmLowering(null)}
        title="Make recognition less strict?"
        description={
          <>
            <p>You are lowering: {confirmLowering?.map(settingLabel).join(", ")}.</p>
            <p>
              Lower thresholds accept weaker matches and increase false recognitions. Only continue if the change was
              evaluated on test data and approved.
            </p>
          </>
        }
        confirmLabel="Lower and save"
        pending={update.isPending}
        onConfirm={save}
      />
    </div>
  );
}
