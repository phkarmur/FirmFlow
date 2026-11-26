import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Pencil, Play, CheckCircle2, Repeat } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { fmtDate } from '../utils/format';
import { Modal, Field, Alert, Spinner, PageHeader, inputCls, btn } from '../components/ui';

/**
 * Bulk / recurring task creation (spec §5.5, §6.1 items 5 and 6).
 * 1. A batch = task type + which clients + default people + optional schedule.
 * 2. Run = choose a period -> PREVIEW (nothing is created) -> COMMIT.
 * Running again for the same period only creates tasks for clients that do not have one yet
 * (spec B4 "run for missing clients").
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const OUTCOME: Record<string, string> = {
  created: 'bg-emerald-100 text-emerald-800', skipped_duplicate: 'bg-slate-100 text-slate-700',
  skipped_inactive: 'bg-amber-100 text-amber-800', skipped_blocked: 'bg-amber-100 text-amber-800', error: 'bg-rose-100 text-rose-800',
};
const EMPTY = { name: '', task_type: '', client_selection: 'all', default_assigned_user: '', default_leader_user: '', default_manager_user: '',
  schedule: { day_of_month: '', months: [] as number[], period_offset: -1 }, is_active: true };

export const BatchesPage: React.FC = () => {
  const [batches, setBatches] = useState<any[]>([]);
  const [types, setTypes] = useState<any[]>([]);
  const [staff, setStaff] = useState<any[]>([]);
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState<any>(null);
  const [runFor, setRunFor] = useState<any>(null);        // batch being run
  const [periods, setPeriods] = useState<any[]>([]);
  const [periodId, setPeriodId] = useState('');
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<any>(null);

  const load = () => {
    Promise.allSettled([
      api.get('/api/v1/bulk/batches/?page_size=200'),
      api.get('/api/v1/services/task-types/flat_list/'),
      api.get('/api/v1/accounts/users/mentionable/'),
      api.get('/api/v1/clients/groups/?page_size=200'),
    ]).then(([b, t, s, g]) => {
      if (b.status === 'fulfilled') setBatches((b.value as any).results || []);
      else setError(errorMessage(b.reason, 'Could not load batches.'));
      if (t.status === 'fulfilled') setTypes(t.value as any[]);
      if (s.status === 'fulfilled') setStaff(s.value as any[]);
      if (g.status === 'fulfilled') setGroups((g.value as any).results || []);
    }).finally(() => setLoading(false));
  };
  useEffect(load, []);
  const typeById = useMemo(() => Object.fromEntries(types.map(t => [String(t.id), t])), [types]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    const payload = { ...form, default_assigned_user: form.default_assigned_user || null, default_leader_user: form.default_leader_user || null,
      default_manager_user: form.default_manager_user || null,
      schedule: { ...form.schedule, day_of_month: form.schedule.day_of_month === '' ? null : Number(form.schedule.day_of_month) } };
    console.info('[batches] save', payload);
    try {
      if (form.id) await api.patch(`/api/v1/bulk/batches/${form.id}/`, payload);
      else await api.post('/api/v1/bulk/batches/', payload);
      setForm(null); setNotice('Batch saved.'); load();
    } catch (err) { setError(errorMessage(err, 'Could not save the batch.')); } finally { setBusy(false); }
  };

  const openRun = (b: any) => {
    setRunFor(b); setPreview(null); setPeriodId(''); setError('');
    const kind = b.period_kind === 'none' ? 'year' : b.period_kind;
    Promise.all([api.get(`/api/v1/periods/periods/?kind=${kind}&page_size=40`),
      api.get(`/api/v1/periods/periods/suggest/?task_type=${b.task_type}&offset=${b.schedule?.period_offset ?? -1}`)])
      .then(([p, s]: any) => { setPeriods(p.results || []); if (s.period?.id) setPeriodId(String(s.period.id)); })
      .catch(err => setError(errorMessage(err)));
  };
  const doPreview = async () => {
    setBusy(true); setError('');
    try {
      const res = await api.post(`/api/v1/bulk/batches/${runFor.id}/preview/`, { period_id: periodId });
      console.info('[batches] preview', res.created_count, res.skipped_count);
      setPreview(res);
    } catch (err) { setError(errorMessage(err, 'Preview failed.')); } finally { setBusy(false); }
  };
  const doCommit = async () => {
    setBusy(true); setError('');
    try {
      const res = await api.post(`/api/v1/bulk/batches/${runFor.id}/commit/`, { run_id: preview.id });
      setNotice(`${res.created_count} task(s) created, ${res.skipped_count} skipped, ${res.error_count} error(s) for ${res.period_label}.`);
      setRunFor(null); setPreview(null); load();
    } catch (err) { setError(errorMessage(err, 'Commit failed.')); } finally { setBusy(false); }
  };
  const openHistory = (b: any, run: any) =>
    api.get(`/api/v1/bulk/batches/${b.id}/run_detail/?run_id=${run.id}`).then(setHistory).catch(err => setError(errorMessage(err)));

  const scheduleText = (b: any) => {
    const s = b.schedule || {};
    if (!s.day_of_month) return 'Manual only';
    const months = (s.months || []).length ? s.months.map((m: number) => MONTHS[m - 1]).join(', ') : 'every month';
    return `Day ${s.day_of_month}, ${months} · ${Number(s.period_offset ?? -1) === -1 ? 'previous' : 'current'} period`;
  };
  const selKind = form?.client_selection === 'all' ? 'all' : form?.client_selection?.startsWith('group:') ? 'group' : 'list';

  if (loading) return <Spinner text="Loading batches…" />;
  return (
    <div className="space-y-5">
      <PageHeader title="Bulk & recurring tasks" subtitle="Create the same task for many clients at once, by hand or on a schedule. Always preview before tasks are created."
        actions={<button type="button" className={btn.primary} onClick={() => setForm({ ...EMPTY })}><Plus className="w-4 h-4" /> New batch</button>} />
      {error && !form && !runFor && <Alert onClose={() => setError('')}>{error}</Alert>}
      {notice && <Alert kind="ok" onClose={() => setNotice('')}>{notice}</Alert>}

      <div className="grid gap-3">
        {batches.length === 0 && <p className="text-sm text-slate-500 bg-white border rounded-xl p-6 text-center">No batches yet. Example: "GSTR-3B for all GST clients, day 1 of every month, previous month".</p>}
        {batches.map(b => (
          <div key={b.id} className={`bg-white border border-slate-200 rounded-xl p-4 ${b.is_active ? '' : 'opacity-60'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-900 flex items-center gap-2"><Repeat className="w-4 h-4 text-slate-400" />{b.name}</p>
                <p className="text-xs text-slate-500 mt-0.5">{b.task_type_name} · clients: {b.client_selection === 'all' ? 'all active' : b.client_selection.startsWith('group:') ? `group ${groups.find(g => `group:${g.id}` === b.client_selection)?.name || ''}` : 'selected list'}</p>
                <p className="text-xs text-slate-500">Schedule: {scheduleText(b)}{b.next_run_date ? ` · next run ${fmtDate(b.next_run_date)}` : ''}</p>
              </div>
              <div className="flex gap-2">
                <button type="button" className={btn.secondary} onClick={() => setForm({ ...EMPTY, ...b, schedule: { ...EMPTY.schedule, ...(b.schedule || {}), day_of_month: b.schedule?.day_of_month ?? '' } })}><Pencil className="w-4 h-4" /> Edit</button>
                <button type="button" className={btn.primary} disabled={!b.is_active} onClick={() => openRun(b)}><Play className="w-4 h-4" /> Run</button>
              </div>
            </div>
            {b.last_runs?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {b.last_runs.map((r: any) => (
                  <button type="button" key={r.id} onClick={() => openHistory(b, r)} className="text-[11px] px-2 py-1 rounded-md border border-slate-200 hover:bg-slate-50">
                    {r.period_label}: <strong>{r.created_count}</strong> created, {r.skipped_count} skipped{r.error_count ? `, ${r.error_count} errors` : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {form && (
        <Modal title={form.id ? 'Edit batch' : 'New batch'} onClose={() => setForm(null)} wide>
          <form onSubmit={save} className="space-y-3">
            {error && <Alert>{error}</Alert>}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Name *" htmlFor="b-name"><input id="b-name" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="GSTR-3B monthly – all GST clients" /></Field>
              <Field label="Task type *" htmlFor="b-tt">
                <select id="b-tt" required value={form.task_type} onChange={e => setForm({ ...form, task_type: e.target.value })} className={inputCls}>
                  <option value="">Select…</option>{types.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Clients" htmlFor="b-sel">
              <div className="flex flex-col sm:flex-row gap-2">
                <select id="b-sel" value={selKind} className={inputCls + ' sm:w-48'}
                  onChange={e => setForm({ ...form, client_selection: e.target.value === 'all' ? 'all' : e.target.value === 'group' ? `group:${groups[0]?.id || ''}` : 'list:[]' })}>
                  <option value="all">All active clients</option><option value="group">A client group</option><option value="list">Chosen clients</option>
                </select>
                {selKind === 'group' && (
                  <select aria-label="Client group" value={form.client_selection.slice(6)} onChange={e => setForm({ ...form, client_selection: `group:${e.target.value}` })} className={inputCls}>
                    {groups.length === 0 && <option value="">No groups yet (create on the Clients page)</option>}
                    {groups.map(g => <option key={g.id} value={g.id}>{g.name} ({g.client_count})</option>)}
                  </select>
                )}
              </div>
              {selKind === 'list' && <ClientListPicker value={form.client_selection} onChange={v => setForm({ ...form, client_selection: v })} />}
            </Field>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[['default_assigned_user', 'Assign to'], ['default_leader_user', 'Leader'], ['default_manager_user', 'Manager']].map(([k, label]) => (
                <Field key={k} label={label} htmlFor={`b-${k}`}>
                  <select id={`b-${k}`} value={form[k] || ''} onChange={e => setForm({ ...form, [k]: e.target.value })} className={inputCls}>
                    <option value="">{k === 'default_assigned_user' ? 'Unassigned pool' : 'None'}</option>
                    {staff.map(s => <option key={s.id} value={s.id}>{s.full_name}</option>)}
                  </select>
                </Field>
              ))}
            </div>
            <fieldset className="border border-slate-200 rounded-lg p-3 space-y-2">
              <legend className="px-1 font-medium text-slate-700">Schedule (optional)</legend>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Run on day of month" htmlFor="b-dom" hint="1–28. Empty = run by hand only.">
                  <input id="b-dom" type="number" min={1} max={28} value={form.schedule.day_of_month} onChange={e => setForm({ ...form, schedule: { ...form.schedule, day_of_month: e.target.value } })} className={inputCls} />
                </Field>
                <Field label="Create tasks for" htmlFor="b-off">
                  <select id="b-off" value={form.schedule.period_offset} onChange={e => setForm({ ...form, schedule: { ...form.schedule, period_offset: Number(e.target.value) } })} className={inputCls}>
                    <option value={-1}>Previous period (e.g. October, on 1 November)</option><option value={0}>Current period</option>
                  </select>
                </Field>
              </div>
              <div className="grid grid-cols-6 sm:grid-cols-12 gap-1">
                {MONTHS.map((m, i) => {
                  const on = form.schedule.months.includes(i + 1);
                  return <button type="button" key={m} aria-pressed={on} onClick={() => setForm({ ...form, schedule: { ...form.schedule, months: on ? form.schedule.months.filter((x: number) => x !== i + 1) : [...form.schedule.months, i + 1].sort((a: number, b: number) => a - b) } })}
                    className={`py-1 rounded border text-xs font-semibold ${on ? 'bg-emerald-600 text-white border-emerald-600' : 'border-slate-300 text-slate-600'}`}>{m}</button>;
                })}
              </div>
              <p className="text-xs text-slate-500">No month selected = every month. The scheduler runs at 01:00 and never creates the same task twice.</p>
            </fieldset>
            {form.id && <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} />Active</label>}
            <div className="flex justify-end gap-2"><button type="button" className={btn.secondary} onClick={() => setForm(null)}>Cancel</button><button type="submit" disabled={busy} className={btn.primary}>Save</button></div>
          </form>
        </Modal>
      )}

      {runFor && (
        <Modal title={`Run: ${runFor.name}`} onClose={() => setRunFor(null)} wide>
          <div className="space-y-3">
            {error && <Alert>{error}</Alert>}
            <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
              <Field label="Period" htmlFor="r-period">
                <select id="r-period" value={periodId} onChange={e => { setPeriodId(e.target.value); setPreview(null); }} className={inputCls}>
                  <option value="">Select…</option>{periods.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </Field>
              <button type="button" className={btn.secondary} disabled={!periodId || busy} onClick={doPreview}>Preview</button>
            </div>
            {preview && (
              <>
                <Alert kind="warn">Nothing is created yet. <strong>{preview.created_count}</strong> task(s) will be created, {preview.skipped_count} skipped. Check the list, then confirm.</Alert>
                <div className="max-h-72 overflow-y-auto border border-slate-200 rounded-lg">
                  <table className="w-full text-xs"><tbody className="divide-y divide-slate-100">
                    {preview.items.map((i: any) => (
                      <tr key={i.id}><td className="px-3 py-1.5">{i.client_name}</td>
                        <td className="px-3 py-1.5"><span className={`px-1.5 py-0.5 rounded ${OUTCOME[i.outcome] || ''}`}>{i.outcome.replace('_', ' ')}</span></td>
                        <td className="px-3 py-1.5 text-slate-500">{i.message}</td></tr>
                    ))}
                  </tbody></table>
                </div>
                <div className="flex justify-end gap-2">
                  <button type="button" className={btn.secondary} onClick={() => setRunFor(null)}>Cancel</button>
                  <button type="button" className={btn.primary} disabled={busy || preview.created_count === 0} onClick={doCommit}><CheckCircle2 className="w-4 h-4" /> Create {preview.created_count} task(s)</button>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}

      {history && (
        <Modal title={`${history.batch_name} · ${history.period_label}`} onClose={() => setHistory(null)} wide>
          <p className="text-xs text-slate-500 mb-2">{history.created_count} created · {history.skipped_count} skipped · {history.error_count} errors</p>
          <div className="max-h-96 overflow-y-auto border border-slate-200 rounded-lg">
            <table className="w-full text-xs"><tbody className="divide-y divide-slate-100">
              {history.items.map((i: any) => (
                <tr key={i.id}><td className="px-3 py-1.5">{i.client_name}</td><td className="px-3 py-1.5 font-mono">{i.task_number}</td>
                  <td className="px-3 py-1.5"><span className={`px-1.5 py-0.5 rounded ${OUTCOME[i.outcome] || ''}`}>{i.outcome.replace('_', ' ')}</span></td>
                  <td className="px-3 py-1.5 text-slate-500">{i.message}</td></tr>
              ))}
            </tbody></table>
          </div>
        </Modal>
      )}
    </div>
  );
};

/** Pick clients for "list:[id,id]" selection. */
const ClientListPicker: React.FC<{ value: string; onChange: (v: string) => void }> = ({ value, onChange }) => {
  const ids: string[] = (value.slice(5).replace(/[[\]\s]/g, '') || '').split(',').filter(Boolean);
  const [q, setQ] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [searchError, setSearchError] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearchError('');
      api.get(`/api/v1/clients/?is_active=true&page_size=20${q ? `&search=${encodeURIComponent(q)}` : ''}`)
        .then((r: any) => { setResults(r.results || []); setNames(n => ({ ...n, ...Object.fromEntries((r.results || []).map((c: any) => [c.id, c.name])) })); })
        .catch(err => { console.error('[batches] client search failed', err); setSearchError(errorMessage(err, 'Client search failed.')); });
    }, 300);
    return () => window.clearTimeout(t);
  }, [q]);
  const toggle = (id: string) => onChange(`list:[${(ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]).join(',')}]`);
  return (
    <div className="mt-2 border border-slate-200 rounded-lg p-2 space-y-2">
      <div className="flex flex-wrap gap-1">{ids.map(id => <span key={id} className="text-xs bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">{names[id] || id.slice(0, 8)} <button type="button" aria-label="Remove" onClick={() => toggle(id)}>×</button></span>)}
        {ids.length === 0 && <span className="text-xs text-slate-500">No clients chosen.</span>}</div>
      <input aria-label="Search clients" value={q} onChange={e => setQ(e.target.value)} placeholder="Search clients…" className={inputCls} />
      {searchError && <p role="alert" className="text-xs text-rose-700">{searchError}</p>}
      <div className="max-h-40 overflow-y-auto">
        {results.map(c => <label key={c.id} className="flex items-center gap-2 px-1 py-1 text-sm"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={ids.includes(c.id)} onChange={() => toggle(c.id)} />{c.name}</label>)}
      </div>
    </div>
  );
};
