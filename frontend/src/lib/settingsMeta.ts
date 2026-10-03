/** How the Settings screen edits each key (types come from common/settings_keys.py). */

export type SettingKind =
  | "boolean"
  | "integer"
  | "number"
  | "text"
  | "time"
  | "timezone"
  | "url"
  | "secret"
  | "emails"
  | "roles"
  | "thresholds"
  | "windows"
  | "choice"
  | "hidden";

export const CHOICES: Record<string, { value: string; label: string }[]> = {
  "integration.payroll_mode": [
    { value: "pull", label: "Pull — payroll calls the FaceTrack API" },
    { value: "push", label: "Push — FaceTrack sends a signed webhook" },
  ],
};

/** Keys edited on another screen (scheduled reports are managed on Reports). */
const HIDDEN = new Set(["notifications.report_schedules"]);

/** Lowering these makes recognition less strict; it needs an explicit confirmation (CLAUDE.md guardrail). */
export const STRICTNESS_KEYS = new Set([
  "recognition.match_thresholds",
  "recognition.margin",
  "recognition.min_votes",
  "recognition.detector_min_score",
  "recognition.min_crop_quality",
  "recognition.min_blur_variance",
  "enrollment.min_quality",
  "enrollment.min_blur_variance",
  "enrollment.min_face_width_px",
]);

export function settingKind(key: string, value: unknown, secret: boolean): SettingKind {
  if (HIDDEN.has(key)) return "hidden";
  if (secret) return "secret";
  if (key in CHOICES) return "choice";
  if (key === "general.timezone") return "timezone";
  if (key.endsWith("_roles")) return "roles";
  if (key.endsWith("_emails")) return "emails";
  if (key === "recognition.match_thresholds") return "thresholds";
  if (key === "engine.peak_windows") return "windows";
  if (key.endsWith("_time")) return "time";
  if (key.endsWith("_url")) return "url";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return Number.isInteger(value) && !String(value).includes(".") ? "integer" : "number";
  return "text";
}

export function settingLabel(key: string): string {
  const name = key.split(".").slice(1).join(" ").replace(/_/g, " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** True when any number in `next` is below the corresponding saved number. */
export function lowersStrictness(key: string, saved: unknown, next: unknown): boolean {
  if (!STRICTNESS_KEYS.has(key)) return false;
  if (typeof saved === "number" && typeof next === "number") return next < saved;
  if (saved && next && typeof saved === "object" && typeof next === "object") {
    const before = saved as Record<string, unknown>;
    return Object.entries(next as Record<string, unknown>).some(
      ([model, value]) => typeof value === "number" && typeof before[model] === "number" && value < (before[model] as number),
    );
  }
  return false;
}
