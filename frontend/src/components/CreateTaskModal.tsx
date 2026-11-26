import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X, Search, Loader2 } from 'lucide-react';
import { api, errorMessage } from '../api/client';

interface Props {
  onClose: () => void;
  onCreated: (task: any) => void;
}

interface Option { id: string; label: string }

/**
 * Create task form (spec §6.1 item 4).
 * - Client: type-ahead search on the server (name / GSTIN / exact PAN), so firms
 *   with thousands of clients work (the old dropdown only had the first 25).
 * - Period: filtered by the task type's period kind and the chosen FY.
 *   Default = previous period (e.g. GSTR-3B for last month), like recurring batches.
 * - Due date: blank = calculated on the server from the task type rule.
 */
export const CreateTaskModal: React.FC<Props> = ({ onClose, onCreated }) => {
  const [taskTypes, setTaskTypes] = useState<any[]>([]);
  const [fys, setFys] = useState<any[]>([]);
  const [staff, setStaff] = useState<any[]>([]);
  const [periods, setPeriods] = useState<any[]>([]);

  const [clientQuery, setClientQuery] = useState('');
  const [clientResults, setClientResults] = useState<any[]>([]);
  const [clientSearching, setClientSearching] = useState(false);
  const [client, setClient] = useState<Option | null>(null);

  const [taskType, setTaskType] = useState('');
  const [fy, setFy] = useState('');
  const [period, setPeriod] = useState('');
  const [assignee, setAssignee] = useState('');
  const [leader, setLeader] = useState('');
  const [manager, setManager] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [priority, setPriority] = useState('normal');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  // Not fatal: the form still works, but a list could not load
  const [warn, setWarn] = useState('');
  const [saving, setSaving] = useState(false);
  const searchTimer = useRef<number | undefined>(undefined);

  const selectedType = useMemo(() => taskTypes.find(t => String(t.id) === taskType), [taskTypes, taskType]);
  const periodKind: string = selectedType?.period_kind || 'none';

  // Static lists
  useEffect(() => {
    Promise.allSettled([
      api.get('/api/v1/services/task-types/flat_list/'),
      api.get('/api/v1/periods/financial-years/?page_size=100'),
      api.get('/api/v1/accounts/users/mentionable/'),
    ]).then(([tt, fyRes, users]) => {
      if (tt.status === 'fulfilled') setTaskTypes(tt.value || []);
      else setError(errorMessage(tt.reason, 'Could not load task types.'));
      if (fyRes.status === 'fulfilled') setFys((fyRes.value as any).results || fyRes.value || []);
      if (users.status === 'fulfilled') setStaff(Array.isArray(users.value) ? users.value : []);
      else { console.error('[create-task] staff list failed', users.reason); setWarn('Could not load the staff list. You can create the task now and assign it later.'); }
    });
  }, []);

  // Client type-ahead (debounced 300 ms)
  useEffect(() => {
    window.clearTimeout(searchTimer.current);
    if (client && clientQuery === client.label) return;
    searchTimer.current = window.setTimeout(() => {
      setClientSearching(true);
      const q = encodeURIComponent(clientQuery.trim());
      api.get(`/api/v1/clients/?picker=true&is_active=true&page_size=20${q ? `&search=${q}` : ''}`)
        .then((res: any) => setClientResults(res.results || []))
        .catch(err => { console.error('[create-task] client search failed', err); setWarn(errorMessage(err, 'Client search failed.')); })
        .finally(() => setClientSearching(false));
    }, 300);
    return () => window.clearTimeout(searchTimer.current);
  }, [clientQuery]);

  // When the task type changes: ask the server for the suggested FY + period (previous period)
  useEffect(() => {
    setPeriod('');
    setPeriods([]);
    if (!taskType) return;
    api.get(`/api/v1/periods/periods/suggest/?task_type=${taskType}&offset=-1`)
      .then((res: any) => {
        console.debug('[create-task] suggestion', res);
        if (res.fy?.id) setFy(String(res.fy.id));
        if (res.period?.id) setPeriod(String(res.period.id));
      })
      .catch(err => { console.error('[create-task] suggest failed', err); setWarn('Could not suggest the period. Choose it yourself.'); });
  }, [taskType]);

  // Periods for the chosen FY and kind
  useEffect(() => {
    if (!fy || periodKind === 'none') {
      setPeriods([]);
      return;
    }
    api.get(`/api/v1/periods/periods/?fy_id=${fy}&kind=${periodKind}&order=asc&page_size=50`)
      .then((res: any) => setPeriods(res.results || []))
      .catch(err => { console.error('[create-task] periods failed', err); setWarn(errorMessage(err, 'Could not load the periods.')); });
  }, [fy, periodKind]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!client) {
      setError('Select a client from the search results.');
      return;
    }
    if (periodKind !== 'none' && selectedType && !period) {
      setError(`Select the ${periodKind} for this task.`);
      return;
    }
    setSaving(true);
    try {
      const task = await api.post('/api/v1/tasks/', {
        client: client.id,
        task_type: taskType,
        fy: fy || null,
        period: periodKind !== 'none' ? period || null : null,
        assigned_user: assignee || null,
        leader_user: leader || null,
        manager_user: manager || null,
        due_date: dueDate || null,
        priority,
        description,
      });
      console.info('[create-task] created', task?.task_number);
      onCreated(task);
    } catch (err: any) {
      setError(errorMessage(err, 'Could not create the task.'));
    } finally {
      setSaving(false);
    }
  };

  const staffOptions = (
    <>
      {staff.map(u => (
        <option key={u.id} value={u.id}>{u.full_name}{u.designation ? ` · ${u.designation}` : ''}</option>
      ))}
    </>
  );
  const inputCls = 'w-full border border-slate-300 rounded-lg px-2.5 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none';

  return (
    <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="create-task-title">
      <div className="bg-white w-full sm:max-w-2xl max-h-[95vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl">
        <div className="sticky top-0 bg-white flex items-center justify-between border-b px-5 py-4">
          <h3 id="create-task-title" className="text-lg font-bold text-slate-900">Create task</h3>
          <button onClick={onClose} aria-label="Close" className="p-1 text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
        </div>

        <form onSubmit={submit} className="p-5 space-y-4 text-sm">
          {error && <div role="alert" className="p-3 bg-rose-50 text-rose-800 rounded-lg border border-rose-200 text-sm">{error}</div>}
          {warn && <div role="status" className="p-2.5 bg-amber-50 text-amber-900 rounded-lg border border-amber-200 text-xs flex justify-between gap-2"><span>{warn}</span><button type="button" onClick={() => setWarn('')} aria-label="Dismiss">×</button></div>}

          <div className="relative">
            <label htmlFor="ct-client" className="block font-semibold text-slate-700 mb-1">Client *</label>
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                id="ct-client"
                value={clientQuery}
                autoComplete="off"
                onChange={e => { setClientQuery(e.target.value); setClient(null); }}
                placeholder="Type client name, GSTIN or full PAN"
                className={inputCls + ' pl-8'}
              />
              {clientSearching && <Loader2 className="w-4 h-4 animate-spin text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2" />}
            </div>
            {!client && clientResults.length > 0 && (
              <ul className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg">
                {clientResults.map(c => (
                  <li key={c.id}>
                    <button type="button"
                      onClick={() => { const label = c.name; setClient({ id: c.id, label }); setClientQuery(label); setClientResults([]); }}
                      className="w-full text-left px-3 py-2 hover:bg-emerald-50 flex justify-between gap-2">
                      <span className="font-medium text-slate-800">{c.name}</span>
                      <span className="text-xs text-slate-500 font-mono">{c.pan_masked || c.client_type}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!client && !clientSearching && clientQuery.trim() && clientResults.length === 0 && (
              <p className="text-xs text-slate-500 mt-1">No active client matches. Check the spelling, or ask an admin to add the client.</p>
            )}
          </div>

          <div>
            <label htmlFor="ct-type" className="block font-semibold text-slate-700 mb-1">Task type *</label>
            <select id="ct-type" value={taskType} onChange={e => setTaskType(e.target.value)} required className={inputCls}>
              <option value="">Select service / task type…</option>
              {taskTypes.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="ct-fy" className="block font-semibold text-slate-700 mb-1">Financial year</label>
              <select id="ct-fy" value={fy} onChange={e => { setFy(e.target.value); setPeriod(''); }} className={inputCls}>
                <option value="">Current FY</option>
                {fys.map(f => (
                  <option key={f.id} value={f.id}>
                    FY {f.label}{selectedType?.uses_assessment_year ? ` (AY ${f.assessment_year_label})` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="ct-period" className="block font-semibold text-slate-700 mb-1">
                Period {periodKind !== 'none' && selectedType ? '*' : ''}
              </label>
              <select id="ct-period" value={period} onChange={e => setPeriod(e.target.value)}
                disabled={periodKind === 'none' || !fy} className={inputCls + ' disabled:bg-slate-100 disabled:text-slate-400'}>
                <option value="">{periodKind === 'none' ? 'Not needed for this type' : 'Select period…'}</option>
                {periods.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="ct-due" className="block font-semibold text-slate-700 mb-1">Due date</label>
              <input id="ct-due" type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className={inputCls} />
              <p className="text-xs text-slate-500 mt-1">Leave blank to use the task type rule.</p>
            </div>
            <div>
              <label htmlFor="ct-priority" className="block font-semibold text-slate-700 mb-1">Priority</label>
              <select id="ct-priority" value={priority} onChange={e => setPriority(e.target.value)} className={inputCls}>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label htmlFor="ct-assignee" className="block font-semibold text-slate-700 mb-1">Assigned to</label>
              <select id="ct-assignee" value={assignee} onChange={e => setAssignee(e.target.value)} className={inputCls}>
                <option value="">Unassigned pool</option>
                {staffOptions}
              </select>
            </div>
            <div>
              <label htmlFor="ct-leader" className="block font-semibold text-slate-700 mb-1">Leader</label>
              <select id="ct-leader" value={leader} onChange={e => setLeader(e.target.value)} className={inputCls}>
                <option value="">None</option>
                {staffOptions}
              </select>
            </div>
            <div>
              <label htmlFor="ct-manager" className="block font-semibold text-slate-700 mb-1">Manager</label>
              <select id="ct-manager" value={manager} onChange={e => setManager(e.target.value)} className={inputCls}>
                <option value="">None</option>
                {staffOptions}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="ct-desc" className="block font-semibold text-slate-700 mb-1">Notes</label>
            <textarea id="ct-desc" rows={2} value={description} onChange={e => setDescription(e.target.value)} className={inputCls} />
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t">
            <button type="button" onClick={onClose} className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 font-semibold">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold inline-flex items-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Create task
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
