/**
 * Display formatting only (standards/07: the frontend never computes business results).
 * The API sends UTC ISO timestamps; they are shown in the configured timezone (setting general.timezone).
 */

export const DEFAULT_TIMEZONE = "Asia/Karachi";

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatTime(value: string | null | undefined, timeZone = DEFAULT_TIMEZONE): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone }).format(
    toDate(value),
  );
}

export function formatDateTime(value: string | null | undefined, timeZone = DEFAULT_TIMEZONE): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(toDate(value));
}

/** Formats a calendar date string (YYYY-MM-DD) without shifting it through a timezone. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, month - 1, day)),
  );
}

/** Minutes as returned by the API, shown as "8h 05m". */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes === 0) return "0m";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours > 0 ? `${hours}h ${String(rest).padStart(2, "0")}m` : `${rest}m`;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Today's calendar date (YYYY-MM-DD) in the given timezone. */
export function todayIn(timeZone = DEFAULT_TIMEZONE, now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone }).format(
    now,
  );
  return parts;
}

/** Converts a local wall-clock time on a date (in `timeZone`) to a UTC ISO string for the API. */
export function localToUtcIso(dateValue: string, timeValue: string, timeZone = DEFAULT_TIMEZONE): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  const [hour, minute] = timeValue.split(":").map(Number);
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  // Offset of the zone at that instant, found by formatting the guess back into the zone.
  const zoned = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(guess));
  const get = (type: string) => Number(zoned.find((p) => p.type === type)?.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
  return new Date(guess - (asUtc - guess)).toISOString();
}

/** Local wall-clock time (HH:mm) of a UTC timestamp in `timeZone`, for editing forms. */
export function utcToLocalTime(value: string | null | undefined, timeZone = DEFAULT_TIMEZONE): string {
  return value ? formatTime(value, timeZone) : "";
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
