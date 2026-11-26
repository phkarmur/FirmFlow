/**
 * One place for date and number display (Phase C).
 *
 * - Dates follow the firm setting Settings > Date format (DD-MM-YYYY, DD/MM/YYYY or YYYY-MM-DD).
 * - Date + time is shown in the firm time zone (Settings > Time zone), 12-hour clock (Indian usage).
 * - Numbers use Indian grouping: 12,34,567.
 *
 * AuthContext calls setFormatSettings() when the firm loads or changes.
 * Logs: "[format] ..." (debug) when the settings change or a value cannot be read.
 */
export type DateFormat = 'DD-MM-YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD';

let dateFormat: DateFormat = 'DD-MM-YYYY';
let timeZone: string | undefined = undefined;

export function setFormatSettings(fmt?: string | null, tz?: string | null) {
  const nextFmt = (['DD-MM-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD'] as const).includes(fmt as DateFormat) ? (fmt as DateFormat) : 'DD-MM-YYYY';
  let nextTz: string | undefined = undefined;
  if (tz) {
    try { new Intl.DateTimeFormat('en-IN', { timeZone: tz }); nextTz = tz; }
    catch { console.warn('[format] unknown time zone, using the browser time zone', tz); }
  }
  if (nextFmt !== dateFormat || nextTz !== timeZone) console.debug('[format] settings', { dateFormat: nextFmt, timeZone: nextTz || 'browser' });
  dateFormat = nextFmt;
  timeZone = nextTz;
}

const pad = (n: number) => String(n).padStart(2, '0');
const join = (y: string | number, m: string | number, d: string | number) =>
  dateFormat === 'YYYY-MM-DD' ? `${y}-${m}-${d}` : `${d}${dateFormat === 'DD/MM/YYYY' ? '/' : '-'}${m}${dateFormat === 'DD/MM/YYYY' ? '/' : '-'}${y}`;

/** Year, month, day of a timestamp in the firm time zone. */
function ymdInZone(date: Date): [string, string, string] {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const get = (t: string) => parts.find(p => p.type === t)?.value || '';
  return [get('year'), get('month'), get('day')];
}

/** "2026-11-20" or an ISO timestamp -> firm date format. Empty -> fallback. */
export function fmtDate(value?: string | null, fallback = '—'): string {
  if (!value) return fallback;
  const s = String(value);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return join(m[1], m[2], m[3]);          // plain date: no time zone shift
  const d = new Date(s);
  if (isNaN(d.getTime())) { console.debug('[format] not a date', s); return s; }
  const [y, mo, da] = ymdInZone(d);
  return join(y, mo, da);
}

/** ISO timestamp -> "20-11-2026, 3:45 pm" in the firm time zone. */
export function fmtDateTime(value?: string | null, fallback = ''): string {
  if (!value) return fallback;
  const d = new Date(String(value));
  if (isNaN(d.getTime())) { console.debug('[format] not a date-time', value); return String(value); }
  const time = new Intl.DateTimeFormat('en-IN', { timeZone, hour: 'numeric', minute: '2-digit', hour12: true }).format(d);
  return `${fmtDate(String(value))}, ${time}`;
}

const intFmt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const decFmt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

/** 1234567 -> "12,34,567"; 1234.5 -> "1,234.5". Non-numbers are returned as text. */
export function fmtNumber(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  return (Number.isInteger(n) ? intFmt : decFmt).format(n);
}

/** For the Settings preview */
export function sampleDate(fmt: string): string {
  const old = dateFormat;
  dateFormat = (fmt as DateFormat) || old;
  const out = fmtDate('2026-11-20');
  dateFormat = old;
  return out;
}
