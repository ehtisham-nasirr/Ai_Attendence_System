import { Plus, Trash2 } from "lucide-react";

import type { SettingItem } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cameraRoleLabel } from "@/lib/labels";
import { CHOICES, settingKind, settingLabel } from "@/lib/settingsMeta";
import type { CameraRole } from "@/api/generated/model";

const TIMEZONES: string[] = (() => {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return ["Asia/Karachi", "UTC"];
  }
})();

function display(value: unknown): string {
  if (Array.isArray(value)) return value.length ? JSON.stringify(value) : "none";
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** One setting: label, description, default, the right input for its type, and its error. */
export function SettingField({
  item,
  value,
  error,
  onChange,
}: {
  item: SettingItem;
  value: unknown;
  error?: string;
  onChange: (value: unknown) => void;
}) {
  const kind = settingKind(item.key, item.default, item.secret);
  if (kind === "hidden") return null;
  const id = `setting-${item.key}`;
  const label = settingLabel(item.key);

  let input: React.ReactNode;
  switch (kind) {
    case "boolean":
      input = <Switch id={id} checked={Boolean(value)} onCheckedChange={onChange} />;
      break;
    case "integer":
    case "number":
      input = (
        <Input
          id={id}
          type="number"
          step={kind === "integer" ? 1 : "any"}
          className="w-40"
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        />
      );
      break;
    case "time":
      input = <Input id={id} type="time" className="w-36" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "timezone":
      input = (
        <Select value={String(value)} onValueChange={onChange}>
          <SelectTrigger id={id} className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            {TIMEZONES.map((zone) => (
              <SelectItem key={zone} value={zone}>
                {zone}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
      break;
    case "choice":
      input = (
        <Select value={String(value)} onValueChange={onChange}>
          <SelectTrigger id={id} className="w-full sm:w-96">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CHOICES[item.key].map((choice) => (
              <SelectItem key={choice.value} value={choice.value}>
                {choice.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
      break;
    case "secret":
      input = (
        <Input
          id={id}
          type="password"
          autoComplete="off"
          className="w-full sm:w-96"
          placeholder={item.is_set ? "Stored. Type a new value to replace it." : "Not set"}
          value={typeof value === "string" && value !== "********" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
      break;
    case "emails":
      input = (
        <Textarea
          id={id}
          rows={2}
          className="w-full sm:w-96"
          placeholder="one@example.com, two@example.com"
          value={Array.isArray(value) ? value.join(", ") : ""}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(/[,\n;]/)
                .map((part) => part.trim())
                .filter(Boolean),
            )
          }
        />
      );
      break;
    case "roles": {
      const selected = new Set(Array.isArray(value) ? (value as string[]) : []);
      input = (
        <div className="flex flex-wrap gap-3">
          {(Object.keys(cameraRoleLabel) as CameraRole[]).map((role) => (
            <label key={role} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selected.has(role)}
                onCheckedChange={(checked) => {
                  const next = new Set(selected);
                  if (checked === true) next.add(role);
                  else next.delete(role);
                  onChange([...next]);
                }}
              />
              {cameraRoleLabel[role]}
            </label>
          ))}
        </div>
      );
      break;
    }
    case "thresholds": {
      const map = (value ?? {}) as Record<string, number>;
      input = (
        <div className="flex flex-wrap gap-3">
          {Object.entries(map).map(([model, threshold]) => (
            <label key={model} className="flex items-center gap-2 text-sm">
              <span className="font-mono">{model}</span>
              <Input
                type="number"
                step="0.01"
                min={0}
                max={1}
                className="w-24"
                value={threshold}
                onChange={(e) => onChange({ ...map, [model]: Number(e.target.value) })}
              />
            </label>
          ))}
        </div>
      );
      break;
    }
    case "windows": {
      const windows = Array.isArray(value) ? (value as { start: string; end: string }[]) : [];
      input = (
        <div className="space-y-2">
          {windows.map((window, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                type="time"
                aria-label="From"
                className="w-32"
                value={window.start}
                onChange={(e) => onChange(windows.map((w, i) => (i === index ? { ...w, start: e.target.value } : w)))}
              />
              <span className="text-muted-foreground text-sm">to</span>
              <Input
                type="time"
                aria-label="To"
                className="w-32"
                value={window.end}
                onChange={(e) => onChange(windows.map((w, i) => (i === index ? { ...w, end: e.target.value } : w)))}
              />
              <Button type="button" variant="ghost" size="icon" aria-label="Remove window" onClick={() => onChange(windows.filter((_, i) => i !== index))}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => onChange([...windows, { start: "08:00", end: "10:00" }])}>
            <Plus aria-hidden /> Add window
          </Button>
        </div>
      );
      break;
    }
    default:
      input = (
        <Input
          id={id}
          type={kind === "url" ? "url" : "text"}
          className="w-full sm:w-96"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }

  return (
    <div className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:gap-6">
      <div>
        <Label htmlFor={id}>{label}</Label>
        <p className="text-muted-foreground mt-1 text-xs">{item.description}</p>
        {!item.secret && <p className="text-muted-foreground text-xs">Default: {display(item.default)}</p>}
      </div>
      <div className="space-y-1">
        {input}
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
