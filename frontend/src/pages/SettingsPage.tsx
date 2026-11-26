import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Settings, Save, Loader2, Lock, Info, ImagePlus, Trash2 } from 'lucide-react';
import { ComplianceCalendarEditor } from '../components/ComplianceCalendarEditor';
import { api, errorMessage } from '../api/client';
import { sampleDate } from '../utils/format';
import { useAuth } from '../context/AuthContext';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const TIMEZONES = ['Asia/Kolkata', 'Asia/Kathmandu', 'Asia/Dubai', 'Asia/Singapore', 'Europe/London', 'America/New_York', 'UTC'];
const DATE_FORMATS = ['DD-MM-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD'];
const EDITABLE = ['name', 'legal_name', 'staff_can_create_task', 'staff_can_complete', 'allow_pickup',
  'long_due_days', 'max_upload_mb', 'timezone', 'date_format', 'fy_start_month'] as const;

/**
 * Firm settings (spec §6.1 item 16). Superadmin edits; Admin can only view.
 * The server enforces the same rules (PATCH /api/v1/accounts/firm/ is Superadmin only).
 */
export const SettingsPage: React.FC = () => {
  const { user, refresh } = useAuth();
  const canEdit = user?.system_role === 'superadmin';
  const isAdminPlus = user?.system_role === 'superadmin' || user?.system_role === 'admin';
  const [saved, setSaved] = useState<any>(null);
  const [form, setForm] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = () => {
    setLoading(true);
    api.get('/api/v1/accounts/firm/')
      .then(res => { setSaved(res); setForm(res); })
      .catch(err => setError(errorMessage(err, 'Could not load settings.')))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const changes = useMemo(() => {
    if (!form || !saved) return {};
    const out: Record<string, any> = {};
    for (const k of EDITABLE) if (form[k] !== saved[k]) out[k] = form[k];
    return out;
  }, [form, saved]);
  const dirty = Object.keys(changes).length > 0;

  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setNotice('');
    if (!dirty) return;
    setSaving(true);
    console.info('[settings] saving', changes);
    try {
      const res = await api.patch('/api/v1/accounts/firm/', changes);
      setSaved(res);
      setForm(res);
      setNotice(`Saved: ${Object.keys(changes).map(k => k.replace(/_/g, ' ')).join(', ')}.`);
      await refresh();   // header, buttons and permissions use the new values at once
    } catch (err: any) {
      setError(errorMessage(err, 'Could not save settings.'));
    } finally {
      setSaving(false);
    }
  };

  // Logo: separate upload call (multipart). Superadmin only; server checks the real image type.
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoError, setLogoError] = useState('');
  const uploadLogo = async (file: File | undefined) => {
    if (!file) return;
    setLogoError('');
    if (file.size > 1024 * 1024) {
      setLogoError('The logo must be 1 MB or smaller.');
      return;
    }
    setLogoBusy(true);
    const fd = new FormData();
    fd.append('logo', file);
    try {
      const res = await api.post('/api/v1/accounts/firm/logo/', fd);
      console.info('[settings] logo uploaded', res.logo_url);
      setSaved((s: any) => ({ ...s, logo_url: res.logo_url }));
      setForm((f: any) => ({ ...f, logo_url: res.logo_url }));
      await refresh();
    } catch (err) {
      setLogoError(errorMessage(err, 'Could not upload the logo.'));
    } finally {
      setLogoBusy(false);
    }
  };
  const removeLogo = async () => {
    setLogoBusy(true);
    setLogoError('');
    try {
      await api.delete('/api/v1/accounts/firm/logo/');
      console.info('[settings] logo removed');
      setSaved((s: any) => ({ ...s, logo_url: null }));
      setForm((f: any) => ({ ...f, logo_url: null }));
      await refresh();
    } catch (err) {
      setLogoError(errorMessage(err, 'Could not remove the logo.'));
    } finally {
      setLogoBusy(false);
    }
  };

  if (loading) return <div className="p-8 text-center text-slate-500">Loading settings…</div>;
  if (!form) return <div role="alert" className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-sm">{error || 'Settings not available.'}</div>;

  const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none disabled:bg-slate-100 disabled:text-slate-500';

  const Toggle: React.FC<{ id: string; label: string; help: string }> = ({ id, label, help }) => (
    <label htmlFor={id} className="flex items-start justify-between gap-4 py-3 cursor-pointer">
      <span>
        <span className="block font-medium text-slate-800">{label}</span>
        <span className="block text-xs text-slate-500 mt-0.5">{help}</span>
      </span>
      <input id={id} type="checkbox" role="switch" disabled={!canEdit}
        checked={!!form[id]} onChange={e => set(id, e.target.checked)}
        className="mt-1 h-5 w-9 shrink-0 cursor-pointer appearance-none rounded-full bg-slate-300 transition checked:bg-emerald-600 relative
          before:absolute before:top-0.5 before:left-0.5 before:h-4 before:w-4 before:rounded-full before:bg-white before:transition checked:before:translate-x-4
          disabled:cursor-not-allowed disabled:opacity-60" />
    </label>
  );

  return (
    <div className="max-w-3xl space-y-5">
    <form onSubmit={save} className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2"><Settings className="w-6 h-6 text-slate-500" /> Firm settings</h2>
          <p className="text-sm text-slate-500 mt-1">Rules for the whole firm. Only the Superadmin can change them. Every change is written to the audit log.</p>
        </div>
        {canEdit && (
          <button type="submit" disabled={!dirty || saving}
            className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-semibold">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save changes
          </button>
        )}
      </div>

      {!canEdit && (
        <div className="p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm flex gap-2">
          <Lock className="w-4 h-4 mt-0.5 shrink-0" /> You can view these settings. Only the Superadmin can change them.
        </div>
      )}
      {error && <div role="alert" className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-sm">{error}</div>}
      {notice && <div role="status" className="p-3 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm">{notice}</div>}

      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="font-semibold text-slate-900 mb-3">Firm</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <label htmlFor="name" className="block font-medium text-slate-700 mb-1">Display name *</label>
            <input id="name" required disabled={!canEdit} value={form.name || ''} onChange={e => set('name', e.target.value)} className={inputCls} />
          </div>
          <div>
            <label htmlFor="legal_name" className="block font-medium text-slate-700 mb-1">Legal name</label>
            <input id="legal_name" disabled={!canEdit} value={form.legal_name || ''} onChange={e => set('legal_name', e.target.value)} className={inputCls} />
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-slate-100">
          <span className="block font-medium text-slate-700 mb-2">Logo</span>
          <div className="flex items-center gap-4">
            <div className="w-20 h-20 rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden">
              {form.logo_url
                ? <img src={form.logo_url} alt="Firm logo" className="max-w-full max-h-full object-contain" />
                : <span className="text-xs text-slate-400">No logo</span>}
            </div>
            {canEdit ? (
              <div className="space-y-1.5">
                <div className="flex gap-2">
                  <label className={`inline-flex items-center gap-1.5 border border-slate-300 hover:bg-slate-50 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer ${logoBusy ? 'opacity-60 pointer-events-none' : ''}`}>
                    {logoBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ImagePlus className="w-3.5 h-3.5" />}
                    {form.logo_url ? 'Replace' : 'Upload'}
                    <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only"
                      onChange={e => { uploadLogo(e.target.files?.[0]); e.target.value = ''; }} />
                  </label>
                  {form.logo_url && (
                    <button type="button" onClick={removeLogo} disabled={logoBusy}
                      className="inline-flex items-center gap-1.5 border border-slate-300 hover:bg-rose-50 hover:text-rose-700 px-3 py-1.5 rounded-lg text-xs font-semibold">
                      <Trash2 className="w-3.5 h-3.5" /> Remove
                    </button>
                  )}
                </div>
                <p className="text-xs text-slate-500">PNG, JPEG or WEBP, up to 1 MB. Shown in the top bar.</p>
                {logoError && <p role="alert" className="text-xs text-rose-700">{logoError}</p>}
              </div>
            ) : <p className="text-xs text-slate-500">Only the Superadmin can change the logo.</p>}
          </div>
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-xl px-5 py-2 divide-y divide-slate-100 text-sm">
        <h3 className="font-semibold text-slate-900 py-3">Staff permissions</h3>
        <Toggle id="staff_can_create_task" label="Staff can create tasks"
          help="Default for all staff. You can allow or block single staff members on the Team page." />
        <Toggle id="staff_can_complete" label="Staff can mark tasks completed"
          help="When on, the assigned user or the task leader can complete a task. When off, only admins can." />
        <Toggle id="allow_pickup" label="Staff can pick up unassigned tasks"
          help="Staff see the unassigned pool and can assign a task to themselves." />
        <p className="py-3 text-xs text-slate-500 flex gap-1.5">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          Per-person exceptions for task creation: <Link to="/team" className="text-emerald-700 font-semibold hover:underline">Team page</Link>.
        </p>
      </section>

      <section className="bg-white border border-slate-200 rounded-xl p-5 text-sm">
        <h3 className="font-semibold text-slate-900 mb-3">Rules and region</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="long_due_days" className="block font-medium text-slate-700 mb-1">Long-due after (days)</label>
            <input id="long_due_days" type="number" min={1} max={365} disabled={!canEdit}
              value={form.long_due_days ?? ''} onChange={e => set('long_due_days', e.target.value === '' ? '' : Number(e.target.value))} className={inputCls} />
            <p className="text-xs text-slate-500 mt-1">An open task older than this shows in "Long due".</p>
          </div>
          <div>
            <label htmlFor="max_upload_mb" className="block font-medium text-slate-700 mb-1">Largest file upload (MB)</label>
            <input id="max_upload_mb" type="number" min={1} max={50} disabled={!canEdit}
              value={form.max_upload_mb ?? ''} onChange={e => set('max_upload_mb', e.target.value === '' ? '' : Number(e.target.value))} className={inputCls} />
            <p className="text-xs text-slate-500 mt-1">For task files. 1 to 50 MB.</p>
          </div>
          <div>
            <label htmlFor="timezone" className="block font-medium text-slate-700 mb-1">Timezone</label>
            <select id="timezone" disabled={!canEdit} value={form.timezone} onChange={e => set('timezone', e.target.value)} className={inputCls}>
              {(TIMEZONES.includes(form.timezone) ? TIMEZONES : [form.timezone, ...TIMEZONES]).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <p className="text-xs text-slate-500 mt-1">Decides "today" for due today, overdue and time logs.</p>
          </div>
          <div>
            <label htmlFor="fy_start_month" className="block font-medium text-slate-700 mb-1">Financial year starts in</label>
            <select id="fy_start_month" disabled={!canEdit || form.has_tasks} value={form.fy_start_month}
              onChange={e => set('fy_start_month', Number(e.target.value))} className={inputCls}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
            {form.has_tasks && <p className="text-xs text-slate-500 mt-1">Locked because tasks already exist.</p>}
          </div>
          <div>
            <label htmlFor="date_format" className="block font-medium text-slate-700 mb-1">Date format</label>
            <select id="date_format" disabled={!canEdit} value={form.date_format} onChange={e => set('date_format', e.target.value)} className={inputCls}>
              {DATE_FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
            <p className="text-xs text-slate-500 mt-1">Example: {sampleDate(form.date_format)}. All screens use this format after you save.</p>
          </div>
        </div>
      </section>
    </form>
    <ComplianceCalendarEditor canEdit={isAdminPlus} />
    </div>
  );
};
