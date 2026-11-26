import React, { useEffect, useState } from 'react';
import { Plus, Pencil, Trash2, Loader2, X, CalendarClock } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { fmtDate } from '../utils/format';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const EMPTY = { code: '', title: '', scope: '', description: '', due_day: 7, due_months: [] as number[], warn_days: 2, is_active: true, sort_order: 0 };

/**
 * Settings: manage the dashboard "Statutory Compliance Calendar".
 * Admin+ can add / edit / remove / enable / disable. Others see it read-only.
 */
export const ComplianceCalendarEditor: React.FC<{ canEdit: boolean }> = ({ canEdit }) => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<any | null>(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<any | null>(null);

  const load = () => {
    setLoading(true);
    api.get('/api/v1/services/compliance-calendar/')
      .then((res: any) => setRows(Array.isArray(res) ? res : []))
      .catch(err => setError(errorMessage(err, 'Could not load the calendar.')))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const toggleActive = async (row: any) => {
    setBusyId(row.id);
    setError('');
    try {
      await api.patch(`/api/v1/services/compliance-calendar/${row.id}/`, { is_active: !row.is_active });
      console.info('[calendar] toggled', row.code, !row.is_active);
      load();
    } catch (err) {
      setError(errorMessage(err, 'Could not change the item.'));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async () => {
    if (!confirmDelete) return;
    setBusyId(confirmDelete.id);
    try {
      await api.delete(`/api/v1/services/compliance-calendar/${confirmDelete.id}/`);
      console.info('[calendar] deleted', confirmDelete.code);
      setConfirmDelete(null);
      load();
    } catch (err) {
      setError(errorMessage(err, 'Could not delete the item.'));
    } finally {
      setBusyId(null);
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    const payload = {
      code: editing.code, title: editing.title, scope: editing.scope, description: editing.description,
      due_day: Number(editing.due_day), due_months: editing.due_months, warn_days: Number(editing.warn_days),
      is_active: editing.is_active, sort_order: Number(editing.sort_order) || 0,
    };
    try {
      if (editing.id) await api.patch(`/api/v1/services/compliance-calendar/${editing.id}/`, payload);
      else await api.post('/api/v1/services/compliance-calendar/', payload);
      console.info('[calendar] saved', payload.code);
      setEditing(null);
      load();
    } catch (err) {
      setFormError(errorMessage(err, 'Could not save the item.'));
    } finally {
      setSaving(false);
    }
  };

  const toggleMonth = (m: number) => {
    const set = new Set<number>(editing.due_months);
    set.has(m) ? set.delete(m) : set.add(m);
    setEditing({ ...editing, due_months: Array.from(set).sort((a, b) => a - b) });
  };

  const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none';

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5 text-sm">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2"><CalendarClock className="w-4 h-4 text-slate-500" /> Dashboard compliance calendar</h3>
        {canEdit && (
          <button type="button" onClick={() => { setFormError(''); setEditing({ ...EMPTY, sort_order: rows.length }); }}
            className="inline-flex items-center gap-1.5 border border-slate-300 hover:bg-slate-50 px-3 py-1.5 rounded-lg text-xs font-semibold">
            <Plus className="w-3.5 h-3.5" /> Add item
          </button>
        )}
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Shown on everyone's dashboard. A card turns <span className="font-semibold text-orange-700">orange</span> in the warning days before the due day and <span className="font-semibold text-red-700">red</span> on the due day.
        {!canEdit && ' Only admins can change this list.'}
      </p>
      {error && <div role="alert" className="mb-3 p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{error}</div>}

      {loading ? <p className="text-slate-500 text-xs">Loading…</p> : rows.length === 0 ? (
        <p className="text-slate-500 text-xs">No items yet.</p>
      ) : (
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500 uppercase text-[10px] tracking-wider border-b border-slate-200">
              <tr>
                <th className="px-5 py-2">On</th>
                <th className="px-2 py-2">Code</th>
                <th className="px-2 py-2">Title</th>
                <th className="px-2 py-2">Due</th>
                <th className="px-2 py-2">Warn</th>
                <th className="px-2 py-2">Next due</th>
                {canEdit && <th className="px-5 py-2 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map(r => (
                <tr key={r.id} className={r.is_active ? '' : 'opacity-50'}>
                  <td className="px-5 py-2">
                    <input type="checkbox" role="switch" aria-label={`Show ${r.title} on dashboard`} checked={r.is_active}
                      disabled={!canEdit || busyId === r.id} onChange={() => toggleActive(r)} className="h-4 w-4 accent-emerald-600" />
                  </td>
                  <td className="px-2 py-2 font-mono font-semibold">{r.code}</td>
                  <td className="px-2 py-2 text-slate-800">{r.title}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{r.due_text}</td>
                  <td className="px-2 py-2">{r.warn_days}d</td>
                  <td className="px-2 py-2 whitespace-nowrap">{fmtDate(r.next_due_date)}</td>
                  {canEdit && (
                    <td className="px-5 py-2 text-right whitespace-nowrap">
                      <button type="button" aria-label={`Edit ${r.title}`} onClick={() => { setFormError(''); setEditing({ ...r }); }}
                        className="p-1.5 text-slate-500 hover:text-slate-900"><Pencil className="w-3.5 h-3.5" /></button>
                      <button type="button" aria-label={`Delete ${r.title}`} onClick={() => setConfirmDelete(r)}
                        className="p-1.5 text-slate-500 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true">
          <form onSubmit={save} className="bg-white w-full sm:max-w-lg max-h-[95vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <h4 className="font-bold text-slate-900">{editing.id ? 'Edit calendar item' : 'Add calendar item'}</h4>
              <button type="button" onClick={() => setEditing(null)} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-3 text-sm">
              {formError && <div role="alert" className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{formError}</div>}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label htmlFor="ce-code" className="block font-medium text-slate-700 mb-1">Code *</label>
                  <input id="ce-code" required maxLength={30} value={editing.code} onChange={e => setEditing({ ...editing, code: e.target.value })} className={inputCls} />
                </div>
                <div className="col-span-2">
                  <label htmlFor="ce-title" className="block font-medium text-slate-700 mb-1">Title *</label>
                  <input id="ce-title" required maxLength={150} value={editing.title} onChange={e => setEditing({ ...editing, title: e.target.value })} className={inputCls} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ce-day" className="block font-medium text-slate-700 mb-1">Due day of month *</label>
                  <input id="ce-day" type="number" min={1} max={31} required value={editing.due_day} onChange={e => setEditing({ ...editing, due_day: e.target.value })} className={inputCls} />
                </div>
                <div>
                  <label htmlFor="ce-warn" className="block font-medium text-slate-700 mb-1">Orange warning (days before)</label>
                  <input id="ce-warn" type="number" min={0} max={15} required value={editing.warn_days} onChange={e => setEditing({ ...editing, warn_days: e.target.value })} className={inputCls} />
                </div>
              </div>
              <fieldset>
                <legend className="block font-medium text-slate-700 mb-1">Months <span className="font-normal text-slate-500">(none selected = every month)</span></legend>
                <div className="grid grid-cols-6 gap-1.5">
                  {MONTHS.map((m, i) => {
                    const on = editing.due_months.includes(i + 1);
                    return (
                      <button type="button" key={m} aria-pressed={on} onClick={() => toggleMonth(i + 1)}
                        className={`py-1.5 rounded-md border text-xs font-semibold ${on ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'}`}>{m}</button>
                    );
                  })}
                </div>
              </fieldset>
              <div>
                <label htmlFor="ce-scope" className="block font-medium text-slate-700 mb-1">Applies to</label>
                <input id="ce-scope" maxLength={150} value={editing.scope} onChange={e => setEditing({ ...editing, scope: e.target.value })} className={inputCls} />
              </div>
              <div>
                <label htmlFor="ce-desc" className="block font-medium text-slate-700 mb-1">Description</label>
                <input id="ce-desc" maxLength={255} value={editing.description} onChange={e => setEditing({ ...editing, description: e.target.value })} className={inputCls} />
              </div>
              <div className="grid grid-cols-2 gap-3 items-end">
                <div>
                  <label htmlFor="ce-order" className="block font-medium text-slate-700 mb-1">Order</label>
                  <input id="ce-order" type="number" min={0} value={editing.sort_order} onChange={e => setEditing({ ...editing, sort_order: e.target.value })} className={inputCls} />
                </div>
                <label className="flex items-center gap-2 pb-2">
                  <input type="checkbox" checked={editing.is_active} onChange={e => setEditing({ ...editing, is_active: e.target.checked })} className="h-4 w-4 accent-emerald-600" />
                  Show on dashboard
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t px-5 py-3">
              <button type="button" onClick={() => setEditing(null)} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700 hover:bg-slate-50">Cancel</button>
              <button type="submit" disabled={saving} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold inline-flex items-center gap-2">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save
              </button>
            </div>
          </form>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-center justify-center p-4" role="alertdialog" aria-modal="true">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-3">
            <h4 className="font-bold text-slate-900">Delete "{confirmDelete.title}"?</h4>
            <p className="text-sm text-slate-600">It is removed from the dashboard for everyone. To hide it for a while, turn it off instead.</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmDelete(null)} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700">Cancel</button>
              <button type="button" onClick={remove} disabled={busyId === confirmDelete.id} className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-semibold">Delete</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
