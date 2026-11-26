import React, { useEffect, useState } from 'react';
import { Download, SlidersHorizontal, X } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { inputCls, btn, Alert } from './ui';

/**
 * Task list filters (spec §6.1-2): service, task type, FY, person + role, due date range.
 * Every value lives in the URL, so a filtered list can be bookmarked and shared (a simple "saved view").
 */
export const TaskFilters: React.FC<{ params: URLSearchParams; isAdmin: boolean; onChange: (c: Record<string, string | null>) => void }> =
  ({ params, isAdmin, onChange }) => {
  const [open, setOpen] = useState(() => ['service', 'task_type', 'fy', 'user_id', 'due_from', 'due_to'].some(k => params.get(k)));
  const [types, setTypes] = useState<any[]>([]);
  const [fys, setFys] = useState<any[]>([]);
  const [staff, setStaff] = useState<any[]>([]);
  useEffect(() => {
    if (!open) return;
    api.get('/api/v1/services/task-types/flat_list/').then(setTypes).catch(err => console.error('[filters] types', err));
    api.get('/api/v1/periods/financial-years/?page_size=100').then((r: any) => setFys(r.results || [])).catch(() => undefined);
    if (isAdmin) api.get('/api/v1/accounts/users/mentionable/').then(setStaff).catch(() => undefined);
  }, [open]);
  const services = Array.from(new Map(types.map(t => [t.full_name.split(' → ').slice(0, 2).join(' → '), t])).keys());
  const active = ['service', 'task_type', 'fy', 'user_id', 'due_from', 'due_to', 'client'].filter(k => params.get(k));
  const set = (k: string, v: string) => onChange({ [k]: v || null, page: null });

  return (
    <div className="bg-white border border-slate-200 rounded-xl">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-slate-700">
        <span className="flex items-center gap-1.5"><SlidersHorizontal className="w-3.5 h-3.5" /> More filters{active.length ? ` (${active.length} on)` : ''}</span>
        {active.length > 0 && <span role="button" tabIndex={0} onClick={e => { e.stopPropagation(); onChange(Object.fromEntries(active.map(k => [k, null]))); }}
          className="text-slate-500 hover:text-rose-700 flex items-center gap-1"><X className="w-3 h-3" /> Clear</span>}
      </button>
      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 p-3 border-t border-slate-100">
          <select aria-label="Task type" value={params.get('task_type') || ''} onChange={e => set('task_type', e.target.value)} className={inputCls}>
            <option value="">All task types</option>
            {services.map(svc => (
              <optgroup key={svc} label={svc}>
                {types.filter(t => t.full_name.startsWith(svc + ' → ')).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </optgroup>
            ))}
          </select>
          <select aria-label="Financial year" value={params.get('fy') || ''} onChange={e => set('fy', e.target.value)} className={inputCls}>
            <option value="">All financial years</option>{fys.map(f => <option key={f.id} value={f.id}>FY {f.label}</option>)}
          </select>
          {isAdmin && (
            <div className="flex gap-1">
              <select aria-label="Person" value={params.get('user_id') || ''} onChange={e => set('user_id', e.target.value)} className={inputCls}>
                <option value="">Everyone</option>{staff.map(s => <option key={s.id} value={s.id}>{s.full_name}</option>)}
              </select>
              <select aria-label="As role" value={params.get('role') || ''} onChange={e => set('role', e.target.value)} className={inputCls + ' w-32'}>
                <option value="">any role</option><option value="assigned">assigned</option><option value="leader">leader</option><option value="manager">manager</option><option value="member">member</option>
              </select>
            </div>
          )}
          <div className="flex gap-1 items-center">
            <input aria-label="Due from" type="date" value={params.get('due_from') || ''} onChange={e => set('due_from', e.target.value)} className={inputCls} />
            <span className="text-xs text-slate-400">to</span>
            <input aria-label="Due to" type="date" value={params.get('due_to') || ''} onChange={e => set('due_to', e.target.value)} className={inputCls} />
          </div>
          {params.get('client') && <p className="text-xs text-slate-600 sm:col-span-2">Showing one client only. <button type="button" className="underline" onClick={() => set('client', '')}>Show all clients</button></p>}
        </div>
      )}
    </div>
  );
};

/** CSV / Excel export of exactly what the list shows (all pages, max 10 000 rows). */
export const ExportButtons: React.FC<{ query: string }> = ({ query }) => {
  const q = new URLSearchParams(query);
  q.delete('page'); q.delete('page_size');
  const href = (fmt: string) => `/api/v1/tasks/export/?${q.toString()}&format_type=${fmt}`;
  return (
    <span className="flex gap-1">
      <a href={href('csv')} className={btn.small}><Download className="w-3 h-3" /> CSV</a>
      <a href={href('xlsx')} className={btn.small}><Download className="w-3 h-3" /> Excel</a>
    </span>
  );
};

/** Bulk actions bar for selected tasks (Admin+). Every task goes through the normal server rules. */
export const BulkBar: React.FC<{ ids: string[]; onDone: (msg: string) => void; onClear: () => void }> = ({ ids, onDone, onClear }) => {
  const [action, setAction] = useState('');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [staff, setStaff] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.get('/api/v1/accounts/users/mentionable/').then(setStaff).catch(() => undefined); }, []);
  const needsReason = ['assign', 'due_date', 'delete'].includes(action);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    if (action === 'delete' && !window.confirm(`Delete ${ids.length} task(s)? This cannot be undone.`)) return;
    setBusy(true); setError(''); setResult(null);
    try {
      const res = await api.post('/api/v1/tasks/bulk_action/', { ids, action, value: value || null, reason });
      console.info('[tasks] bulk', action, res);
      if (res.errors?.length) setResult(res);
      onDone(`${res.done} task(s) updated${res.errors?.length ? `, ${res.errors.length} failed` : ''}.`);
      if (!res.errors?.length) { setAction(''); setValue(''); setReason(''); }
    } catch (err) { setError(errorMessage(err, 'Bulk action failed.')); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={run} className="sticky bottom-3 z-20 bg-slate-900 text-white rounded-xl shadow-xl p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <strong>{ids.length} selected</strong>
        <select aria-label="Bulk action" value={action} onChange={e => { setAction(e.target.value); setValue(''); }} className="text-slate-900 rounded-md px-2 py-1.5 text-sm">
          <option value="">Choose an action…</option><option value="assign">Assign to…</option><option value="priority">Set priority</option>
          <option value="due_date">Change due date</option><option value="delete">Delete</option>
        </select>
        {action === 'assign' && <select aria-label="Assign to" value={value} onChange={e => setValue(e.target.value)} className="text-slate-900 rounded-md px-2 py-1.5 text-sm">
          <option value="">Unassigned pool</option>{staff.map(s => <option key={s.id} value={s.id}>{s.full_name}</option>)}</select>}
        {action === 'priority' && <select aria-label="Priority" required value={value} onChange={e => setValue(e.target.value)} className="text-slate-900 rounded-md px-2 py-1.5 text-sm">
          <option value="">Choose…</option><option value="normal">Normal</option><option value="high">High</option></select>}
        {action === 'due_date' && <input aria-label="New due date" type="date" required value={value} onChange={e => setValue(e.target.value)} className="text-slate-900 rounded-md px-2 py-1 text-sm" />}
        {needsReason && <input aria-label="Reason" required minLength={3} value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason" className="text-slate-900 rounded-md px-2 py-1.5 text-sm flex-1 min-w-[140px]" />}
        {action && <button type="submit" disabled={busy} className={action === 'delete' ? btn.danger : btn.primary}>Apply</button>}
        <button type="button" onClick={onClear} className="ml-auto text-xs underline text-slate-300">Clear selection</button>
      </div>
      {error && <Alert>{error}</Alert>}
      {result?.errors?.length > 0 && <Alert kind="warn">Not changed: {result.errors.slice(0, 5).map((e: any) => `${e.task_number} (${e.error})`).join('; ')}</Alert>}
    </form>
  );
};
