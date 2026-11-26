import React, { useEffect, useMemo, useState } from 'react';
import { FolderTree, Plus, Pencil, Trash2, ArrowUp, ArrowDown, Tag, Save } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Modal, Field, Alert, Spinner, PageHeader, inputCls, btn } from '../components/ui';

/**
 * Service catalogue editor (spec §6.1 items 8 and 9).
 * Category -> Service -> Task type. Each task type has a due-date rule, period kind,
 * milestones (ordered) and a checklist. Changes apply to NEW tasks only; existing tasks keep
 * the copy they got when they were created.
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const PERIOD_COUNT: Record<string, number> = { month: 12, quarter: 4, half: 2, year: 1, none: 0 };
const ROLES = ['assigned', 'leader', 'manager', 'member'];

export function describeRule(rule: any, kind: string): string {
  if (!rule || !rule.kind) return '15 days after the task is created (default)';
  switch (rule.kind) {
    case 'fixed_day_after_period_end':
      return `Day ${rule.day ?? 20} of the ${Number(rule.months_after ?? 1) === 1 ? 'month after' : `${rule.months_after ?? 1}th month after`} the ${kind === 'none' ? 'FY' : kind} ends`;
    case 'fixed_date':
      return `${rule.day} ${MONTHS[(rule.month || 1) - 1]} after the financial year ends`;
    case 'per_period_sequence':
      return 'By period: ' + Object.entries(rule.dates || {}).map(([k, v]) => `#${k} → ${v}`).join(', ');
    case 'days_after_creation':
      return `${rule.days ?? 15} days after the task is created`;
    default:
      return '15 days after the task is created (default)';
  }
}

const RuleEditor: React.FC<{ value: any; periodKind: string; onChange: (r: any) => void; disabled: boolean }> = ({ value, periodKind, onChange, disabled }) => {
  const rule = value || {};
  const kind = rule.kind || 'days_after_creation';
  const n = PERIOD_COUNT[periodKind] || 0;
  const set = (patch: any) => onChange({ ...rule, ...patch });
  return (
    <div className="space-y-2">
      <select aria-label="Due rule type" disabled={disabled} value={kind} className={inputCls}
        onChange={e => {
          const k = e.target.value;
          const defaults: any = {
            fixed_day_after_period_end: { kind: k, day: 20, months_after: 1 },
            fixed_date: { kind: k, month: 7, day: 31 },
            per_period_sequence: { kind: k, dates: Object.fromEntries(Array.from({ length: Math.max(n, 1) }, (_, i) => [String(i + 1), '01-31'])) },
            days_after_creation: { kind: k, days: 15 },
          };
          onChange(defaults[k]);
        }}>
        <option value="fixed_day_after_period_end">Day N of the month after the period ends (GST returns)</option>
        <option value="fixed_date">Fixed date after the financial year ends (ITR, audit)</option>
        <option value="per_period_sequence">Different date for each period (TDS, advance tax)</option>
        <option value="days_after_creation">N days after the task is created</option>
      </select>
      {kind === 'fixed_day_after_period_end' && (
        <div className="grid grid-cols-2 gap-2">
          <Field label="Day of month" htmlFor="r-day"><input id="r-day" type="number" min={1} max={31} disabled={disabled} value={rule.day ?? 20} onChange={e => set({ day: Number(e.target.value) })} className={inputCls} /></Field>
          <Field label="Months after period end" htmlFor="r-after"><input id="r-after" type="number" min={0} max={12} disabled={disabled} value={rule.months_after ?? 1} onChange={e => set({ months_after: Number(e.target.value) })} className={inputCls} /></Field>
        </div>
      )}
      {kind === 'fixed_date' && (
        <div className="grid grid-cols-2 gap-2">
          <Field label="Day" htmlFor="r-fd"><input id="r-fd" type="number" min={1} max={31} disabled={disabled} value={rule.day ?? 31} onChange={e => set({ day: Number(e.target.value) })} className={inputCls} /></Field>
          <Field label="Month" htmlFor="r-fm">
            <select id="r-fm" disabled={disabled} value={rule.month ?? 7} onChange={e => set({ month: Number(e.target.value) })} className={inputCls}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </Field>
        </div>
      )}
      {kind === 'per_period_sequence' && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {Array.from({ length: Math.max(n, 1) }, (_, i) => String(i + 1)).map(k => (
            <Field key={k} label={`${periodKind === 'quarter' ? 'Q' : '#'}${k} due (MM-DD)`} htmlFor={`r-p${k}`}>
              <input id={`r-p${k}`} disabled={disabled} pattern="\d{2}-\d{2}" placeholder="07-31" value={(rule.dates || {})[k] || ''}
                onChange={e => set({ dates: { ...(rule.dates || {}), [k]: e.target.value } })} className={inputCls} />
            </Field>
          ))}
          <p className="col-span-full text-xs text-slate-500">The date is the first such day on or after the period starts. Example TDS: Q1 07-31, Q2 10-31, Q3 01-31, Q4 05-31.</p>
        </div>
      )}
      {kind === 'days_after_creation' && (
        <Field label="Days" htmlFor="r-days"><input id="r-days" type="number" min={0} max={3650} disabled={disabled} value={rule.days ?? 15} onChange={e => set({ days: Number(e.target.value) })} className={inputCls} /></Field>
      )}
      <p className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-md px-2 py-1">{describeRule(rule, periodKind)}</p>
    </div>
  );
};

export const ServicesPage: React.FC = () => {
  const { user } = useAuth();
  const canEdit = user?.system_role === 'superadmin' || user?.system_role === 'admin';
  const [tab, setTab] = useState<'tree' | 'labels'>('tree');
  const [cats, setCats] = useState<any[]>([]);
  const [labels, setLabels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selectedTT, setSelectedTT] = useState<string | null>(null);
  const [dialog, setDialog] = useState<any>(null);   // {kind, mode, data}
  const [ttForm, setTtForm] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    Promise.allSettled([
      api.get('/api/v1/services/categories/?page_size=200'),
      api.get('/api/v1/services/issue-labels/?include_inactive=true&page_size=200'),
    ]).then(([c, l]) => {
      if (c.status === 'fulfilled') setCats((c.value as any).results || []);
      else setError(errorMessage(c.reason, 'Could not load the service catalogue.'));
      if (l.status === 'fulfilled') setLabels((l.value as any).results || []);
    }).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const allTT = useMemo(() => cats.flatMap(c => (c.services || []).flatMap((s: any) => (s.task_types || []).map((t: any) => ({ ...t, _svc: s, _cat: c })))), [cats]);
  const tt = allTT.find(t => t.id === selectedTT) || null;
  useEffect(() => {
    if (tt) setTtForm({ name: tt.name, code: tt.code, recurrence: tt.recurrence, period_kind: tt.period_kind, default_due_rule: tt.default_due_rule,
      default_priority: tt.default_priority, uses_assessment_year: tt.uses_assessment_year, allow_out_of_order_milestones: tt.allow_out_of_order_milestones,
      is_billable_default: tt.is_billable_default, is_active: tt.is_active });
  }, [selectedTT, cats]);

  const call = async (label: string, fn: () => Promise<any>, ok?: string) => {
    setError(''); setNotice(''); setSaving(true);
    console.debug('[services]', label);
    try {
      const res = await fn();
      if (ok) setNotice(ok);
      load();
      return res || true;
    } catch (err) {
      console.error('[services] failed', label, err);
      setError(errorMessage(err, 'The change was not saved.'));
      return false;
    } finally { setSaving(false); }
  };

  const saveTT = () => call('save task type', () => api.patch(`/api/v1/services/task-types/${tt.id}/`, ttForm), 'Task type saved. New tasks use the new rules.');
  const move = (list: any[], idx: number, dir: -1 | 1, endpoint: string) => {
    const ids = list.map(x => x.id);
    const j = idx + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    call('reorder', () => api.post(`/api/v1/services/task-types/${tt.id}/${endpoint}/`, { ids }));
  };
  const del = (url: string, what: string) => {
    if (!window.confirm(`Delete ${what}? If tasks already use it, it cannot be deleted — make it inactive instead.`)) return;
    call('delete', () => api.delete(url), `${what} deleted.`);
  };

  const submitDialog = async (e: React.FormEvent) => {
    e.preventDefault();
    const d = dialog;
    const map: Record<string, string> = { category: 'categories', service: 'services', tasktype: 'task-types', milestone: 'milestones', todo: 'todo-templates', label: 'issue-labels' };
    const base = `/api/v1/services/${map[d.kind]}/`;
    const res = await call(`${d.mode} ${d.kind}`, () => d.mode === 'add' ? api.post(base, d.data) : api.patch(`${base}${d.data.id}/`, d.data), 'Saved.');
    if (res) {
      setDialog(null);
      if (d.kind === 'tasktype' && d.mode === 'add' && res.id) setSelectedTT(res.id);
    }
  };
  const setD = (patch: any) => setDialog({ ...dialog, data: { ...dialog.data, ...patch } });

  if (loading) return <Spinner text="Loading service catalogue…" />;

  return (
    <div className="space-y-5">
      <PageHeader title="Service catalogue" subtitle="The kinds of work the firm does, with the rules each new task gets. Changes apply to new tasks only."
        actions={canEdit && tab === 'tree' && <button type="button" className={btn.primary} onClick={() => setDialog({ kind: 'category', mode: 'add', data: { name: '', sort_order: cats.length } })}><Plus className="w-4 h-4" /> Category</button>} />
      <div role="tablist" className="flex gap-1 border-b">
        {[['tree', 'Service tree', FolderTree], ['labels', 'Issue labels', Tag]].map(([id, label, Icon]: any) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px flex items-center gap-1.5 ${tab === id ? 'border-emerald-600 text-emerald-800' : 'border-transparent text-slate-500'}`}>
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>
      {error && <Alert onClose={() => setError('')}>{error}</Alert>}
      {notice && <Alert kind="ok" onClose={() => setNotice('')}>{notice}</Alert>}
      {!canEdit && <Alert kind="warn">You can view the catalogue. Only admins can change it.</Alert>}

      {tab === 'tree' && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(260px,340px)_1fr] gap-4 items-start">
          {/* Tree */}
          <nav aria-label="Service tree" className="bg-white border border-slate-200 rounded-xl p-2 space-y-2 max-h-[75vh] overflow-y-auto">
            {cats.length === 0 && <p className="p-3 text-xs text-slate-500">No categories yet.</p>}
            {cats.map(c => (
              <div key={c.id}>
                <div className="flex items-center justify-between px-2 py-1.5 rounded-md bg-slate-900 text-white">
                  <span className={`text-sm font-bold ${c.is_active ? '' : 'line-through opacity-60'}`}>{c.name}</span>
                  {canEdit && <span className="flex gap-0.5">
                    <button type="button" aria-label={`Add service to ${c.name}`} title="Add service" onClick={() => setDialog({ kind: 'service', mode: 'add', data: { category: c.id, name: '', sort_order: (c.services || []).length } })} className="p-1 hover:text-emerald-300"><Plus className="w-3.5 h-3.5" /></button>
                    <button type="button" aria-label={`Edit ${c.name}`} onClick={() => setDialog({ kind: 'category', mode: 'edit', data: { id: c.id, name: c.name, sort_order: c.sort_order, is_active: c.is_active } })} className="p-1 hover:text-emerald-300"><Pencil className="w-3.5 h-3.5" /></button>
                    <button type="button" aria-label={`Delete ${c.name}`} onClick={() => del(`/api/v1/services/categories/${c.id}/`, `category "${c.name}"`)} className="p-1 hover:text-rose-300"><Trash2 className="w-3.5 h-3.5" /></button>
                  </span>}
                </div>
                {(c.services || []).map((s: any) => (
                  <div key={s.id} className="ml-2 mt-1">
                    <div className="flex items-center justify-between px-2 py-1 text-xs font-semibold text-slate-700">
                      <span className={s.is_active ? '' : 'line-through opacity-60'}>{s.name}</span>
                      {canEdit && <span className="flex gap-0.5 text-slate-400">
                        <button type="button" aria-label={`Add task type to ${s.name}`} title="Add task type" onClick={() => setDialog({ kind: 'tasktype', mode: 'add', data: { service: s.id, name: '', code: '', recurrence: 'monthly', period_kind: 'month', default_due_rule: { kind: 'fixed_day_after_period_end', day: 20, months_after: 1 } } })} className="p-1 hover:text-emerald-700"><Plus className="w-3.5 h-3.5" /></button>
                        <button type="button" aria-label={`Edit ${s.name}`} onClick={() => setDialog({ kind: 'service', mode: 'edit', data: { id: s.id, name: s.name, sort_order: s.sort_order, is_active: s.is_active } })} className="p-1 hover:text-slate-800"><Pencil className="w-3.5 h-3.5" /></button>
                        <button type="button" aria-label={`Delete ${s.name}`} onClick={() => del(`/api/v1/services/services/${s.id}/`, `service "${s.name}"`)} className="p-1 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button>
                      </span>}
                    </div>
                    {(s.task_types || []).map((t: any) => (
                      <button key={t.id} type="button" onClick={() => setSelectedTT(t.id)} aria-current={selectedTT === t.id}
                        className={`w-full text-left ml-2 px-2 py-1.5 rounded-md text-xs flex justify-between gap-2 ${selectedTT === t.id ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'hover:bg-slate-50 text-slate-700'} ${t.is_active ? '' : 'opacity-50'}`}>
                        <span>{t.name}</span><span className="font-mono text-[10px] text-slate-400">{t.code}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </nav>

          {/* Task type editor */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-5 min-w-0">
            {!tt || !ttForm ? (
              <p className="text-sm text-slate-500">Select a task type on the left to see or change its rules.</p>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-xs text-slate-500">{tt._cat.name} → {tt._svc.name}</p>
                    <h3 className="text-lg font-bold text-slate-900">{tt.name}</h3>
                  </div>
                  {canEdit && <div className="flex gap-2">
                    <button type="button" disabled={saving} className={btn.primary} onClick={saveTT}><Save className="w-4 h-4" /> Save</button>
                    <button type="button" className={btn.secondary} onClick={() => del(`/api/v1/services/task-types/${tt.id}/`, `task type "${tt.name}"`)}><Trash2 className="w-4 h-4" /></button>
                  </div>}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Name" htmlFor="tt-name"><input id="tt-name" disabled={!canEdit} value={ttForm.name} onChange={e => setTtForm({ ...ttForm, name: e.target.value })} className={inputCls} /></Field>
                  <Field label="Code (for import)" htmlFor="tt-code"><input id="tt-code" disabled={!canEdit} value={ttForm.code} onChange={e => setTtForm({ ...ttForm, code: e.target.value })} className={inputCls} /></Field>
                  <Field label="Repeats" htmlFor="tt-rec">
                    <select id="tt-rec" disabled={!canEdit} value={ttForm.recurrence} onChange={e => setTtForm({ ...ttForm, recurrence: e.target.value })} className={inputCls}>
                      <option value="none">One-off</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option>
                      <option value="half_yearly">Half-yearly</option><option value="yearly">Yearly</option><option value="custom">Custom</option>
                    </select>
                  </Field>
                  <Field label="Period of each task" htmlFor="tt-pk" hint="What you pick when you create a task (Oct 2026, Q2, FY…).">
                    <select id="tt-pk" disabled={!canEdit} value={ttForm.period_kind} onChange={e => setTtForm({ ...ttForm, period_kind: e.target.value })} className={inputCls}>
                      <option value="month">Month</option><option value="quarter">Quarter</option><option value="half">Half year</option>
                      <option value="year">Financial year</option><option value="none">None (one-off)</option>
                    </select>
                  </Field>
                </div>
                <Field label="Due date rule" htmlFor="tt-rule">
                  <RuleEditor value={ttForm.default_due_rule} periodKind={ttForm.period_kind} disabled={!canEdit} onChange={r => setTtForm({ ...ttForm, default_due_rule: r })} />
                </Field>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  {[['uses_assessment_year', 'Show Assessment Year (AY = FY + 1), for income tax'],
                    ['allow_out_of_order_milestones', 'Milestones can be ticked in any order'],
                    ['is_billable_default', 'Billable by default'],
                    ['is_active', 'Active (can be used for new tasks)']].map(([k, label]) => (
                    <label key={k} className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" disabled={!canEdit}
                      checked={!!ttForm[k]} onChange={e => setTtForm({ ...ttForm, [k]: e.target.checked })} />{label}</label>
                  ))}
                  <label className="flex items-center gap-2">Default priority
                    <select aria-label="Default priority" disabled={!canEdit} value={ttForm.default_priority} onChange={e => setTtForm({ ...ttForm, default_priority: e.target.value })} className="border border-slate-300 rounded-md px-2 py-1 text-sm">
                      <option value="normal">Normal</option><option value="high">High</option>
                    </select></label>
                </div>

                {/* Milestones */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-slate-900">Milestones <span className="text-xs font-normal text-slate-500">— the stages, in order</span></h4>
                    {canEdit && <button type="button" className={btn.small} onClick={() => setDialog({ kind: 'milestone', mode: 'add', data: { task_type: tt.id, name: '', sort_order: (tt.milestones || []).length + 1, is_terminal: false, can_be_completed_by: [], auto_resolve_issue_labels: [] } })}><Plus className="w-3 h-3" /> Add</button>}
                  </div>
                  <ol className="space-y-1.5">
                    {(tt.milestones || []).length === 0 && <li className="text-xs text-slate-500">No milestones.</li>}
                    {(tt.milestones || []).map((m: any, i: number) => (
                      <li key={m.id} className="flex items-center justify-between gap-2 p-2 rounded-lg border border-slate-200 text-sm">
                        <span className="min-w-0"><span className="text-slate-400 mr-2">{i + 1}.</span>{m.name}
                          {m.is_terminal && <span className="ml-2 text-[10px] bg-emerald-100 text-emerald-800 px-1.5 rounded font-bold">Completes task</span>}
                          {(m.can_be_completed_by || []).length > 0 && <span className="ml-2 text-[10px] text-slate-500">by {m.can_be_completed_by.join(', ')}</span>}
                          {(m.auto_resolve_issue_labels || []).length > 0 && <span className="ml-2 text-[10px] text-slate-500">resolves: {m.auto_resolve_issue_labels.join(', ')}</span>}</span>
                        {canEdit && <span className="flex gap-0.5 shrink-0 text-slate-500">
                          <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(tt.milestones, i, -1, 'reorder_milestones')} className="p-1 disabled:opacity-30"><ArrowUp className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label="Move down" disabled={i === tt.milestones.length - 1} onClick={() => move(tt.milestones, i, 1, 'reorder_milestones')} className="p-1 disabled:opacity-30"><ArrowDown className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label={`Edit ${m.name}`} onClick={() => setDialog({ kind: 'milestone', mode: 'edit', data: { ...m } })} className="p-1"><Pencil className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label={`Delete ${m.name}`} onClick={() => del(`/api/v1/services/milestones/${m.id}/`, `milestone "${m.name}"`)} className="p-1 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button>
                        </span>}
                      </li>
                    ))}
                  </ol>
                </div>

                {/* Checklist */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-slate-900">Checklist <span className="text-xs font-normal text-slate-500">— copied into each new task</span></h4>
                    {canEdit && <button type="button" className={btn.small} onClick={() => setDialog({ kind: 'todo', mode: 'add', data: { task_type: tt.id, text: '', is_mandatory: false, sort_order: (tt.todo_templates || []).length + 1 } })}><Plus className="w-3 h-3" /> Add</button>}
                  </div>
                  <ul className="space-y-1.5">
                    {(tt.todo_templates || []).length === 0 && <li className="text-xs text-slate-500">No checklist items.</li>}
                    {(tt.todo_templates || []).map((t: any, i: number) => (
                      <li key={t.id} className="flex items-center justify-between gap-2 p-2 rounded-lg border border-slate-200 text-sm">
                        <span>{t.text}{t.is_mandatory && <span className="ml-2 text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-1.5 rounded">Mandatory</span>}</span>
                        {canEdit && <span className="flex gap-0.5 shrink-0 text-slate-500">
                          <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(tt.todo_templates, i, -1, 'reorder_todos')} className="p-1 disabled:opacity-30"><ArrowUp className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label="Move down" disabled={i === tt.todo_templates.length - 1} onClick={() => move(tt.todo_templates, i, 1, 'reorder_todos')} className="p-1 disabled:opacity-30"><ArrowDown className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label="Edit item" onClick={() => setDialog({ kind: 'todo', mode: 'edit', data: { ...t } })} className="p-1"><Pencil className="w-3.5 h-3.5" /></button>
                          <button type="button" aria-label="Delete item" onClick={() => del(`/api/v1/services/todo-templates/${t.id}/`, 'checklist item')} className="p-1 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button>
                        </span>}
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {tab === 'labels' && (
        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-4 border-b">
            <p className="text-sm text-slate-600">Reasons a task is stuck. "Waiting on client" labels feed the client-side counts.</p>
            {canEdit && <button type="button" className={btn.primary} onClick={() => setDialog({ kind: 'label', mode: 'add', data: { name: '', is_client_side: false, blocks_completion: true, is_active: true } })}><Plus className="w-4 h-4" /> Label</button>}
          </div>
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase"><tr>
              <th className="text-left px-4 py-2">Label</th><th className="text-left px-4 py-2">Waiting on client</th>
              <th className="text-left px-4 py-2">Blocks completion</th><th className="text-left px-4 py-2">Active</th>{canEdit && <th className="px-4 py-2" />}
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {labels.map(l => (
                <tr key={l.id} className={l.is_active ? '' : 'opacity-50'}>
                  <td className="px-4 py-2 font-medium">{l.name}</td>
                  <td className="px-4 py-2">{l.is_client_side ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-2">{l.blocks_completion ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-2">{l.is_active ? 'Yes' : 'No'}</td>
                  {canEdit && <td className="px-4 py-2 text-right whitespace-nowrap">
                    <button type="button" className={btn.small} onClick={() => setDialog({ kind: 'label', mode: 'edit', data: { ...l } })}><Pencil className="w-3 h-3" /> Edit</button>
                  </td>}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      {dialog && (
        <Modal title={`${dialog.mode === 'add' ? 'Add' : 'Edit'} ${({ category: 'category', service: 'service', tasktype: 'task type', milestone: 'milestone', todo: 'checklist item', label: 'issue label' } as any)[dialog.kind]}`} onClose={() => setDialog(null)}>
          <form onSubmit={submitDialog} className="space-y-3">
            {error && <Alert>{error}</Alert>}
            {dialog.kind === 'todo' ? (
              <>
                <Field label="Text" htmlFor="d-text"><input id="d-text" required maxLength={255} value={dialog.data.text} onChange={e => setD({ text: e.target.value })} className={inputCls} /></Field>
                <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={dialog.data.is_mandatory} onChange={e => setD({ is_mandatory: e.target.checked })} />Mandatory (must be ticked before the task can be completed)</label>
              </>
            ) : (
              <Field label="Name" htmlFor="d-name"><input id="d-name" required maxLength={150} value={dialog.data.name} onChange={e => setD({ name: e.target.value })} className={inputCls} autoFocus /></Field>
            )}
            {dialog.kind === 'tasktype' && dialog.mode === 'add' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Code" htmlFor="d-code"><input id="d-code" value={dialog.data.code} onChange={e => setD({ code: e.target.value })} className={inputCls} placeholder="e.g. GSTR3B" /></Field>
                <Field label="Period of each task" htmlFor="d-pk">
                  <select id="d-pk" value={dialog.data.period_kind} onChange={e => setD({ period_kind: e.target.value, recurrence: ({ month: 'monthly', quarter: 'quarterly', half: 'half_yearly', year: 'yearly', none: 'none' } as any)[e.target.value] })} className={inputCls}>
                    <option value="month">Month</option><option value="quarter">Quarter</option><option value="half">Half year</option><option value="year">Financial year</option><option value="none">None (one-off)</option>
                  </select>
                </Field>
                <p className="col-span-2 text-xs text-slate-500">Set the due rule, milestones and checklist after you save.</p>
              </div>
            )}
            {dialog.kind === 'milestone' && (
              <>
                <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={dialog.data.is_terminal} onChange={e => setD({ is_terminal: e.target.checked })} />Last step: ticking it completes the task (if nothing else is open)</label>
                <fieldset><legend className="font-medium text-slate-700 mb-1">Who can tick it <span className="font-normal text-slate-500">(none = assigned, leader, manager)</span></legend>
                  <div className="flex flex-wrap gap-3">{ROLES.map(r => (
                    <label key={r} className="flex items-center gap-1.5"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={(dialog.data.can_be_completed_by || []).includes(r)}
                      onChange={e => setD({ can_be_completed_by: e.target.checked ? [...(dialog.data.can_be_completed_by || []), r] : dialog.data.can_be_completed_by.filter((x: string) => x !== r) })} />{r}</label>
                  ))}</div>
                </fieldset>
                <fieldset><legend className="font-medium text-slate-700 mb-1">Resolve these open issues when ticked</legend>
                  <div className="flex flex-wrap gap-3">{labels.filter(l => l.is_active).map(l => (
                    <label key={l.id} className="flex items-center gap-1.5 text-xs"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={(dialog.data.auto_resolve_issue_labels || []).includes(l.name)}
                      onChange={e => setD({ auto_resolve_issue_labels: e.target.checked ? [...(dialog.data.auto_resolve_issue_labels || []), l.name] : dialog.data.auto_resolve_issue_labels.filter((x: string) => x !== l.name) })} />{l.name}</label>
                  ))}</div>
                </fieldset>
              </>
            )}
            {dialog.kind === 'label' && (
              <div className="space-y-2">
                <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={dialog.data.is_client_side} onChange={e => setD({ is_client_side: e.target.checked })} />Waiting on the client</label>
                <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={dialog.data.blocks_completion} onChange={e => setD({ blocks_completion: e.target.checked })} />Blocks completion while open</label>
              </div>
            )}
            {['category', 'service', 'label'].includes(dialog.kind) && dialog.mode === 'edit' && (
              <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={dialog.data.is_active} onChange={e => setD({ is_active: e.target.checked })} />Active</label>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className={btn.secondary} onClick={() => setDialog(null)}>Cancel</button>
              <button type="submit" disabled={saving} className={btn.primary}>Save</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
