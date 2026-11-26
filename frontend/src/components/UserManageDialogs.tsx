import React, { useEffect, useState } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';
import { api, errorMessage } from '../api/client';

const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none';
const ROLE_NAMES: Record<string, string> = { assigned: 'Assigned to', leader: 'Leader', manager: 'Manager', member: 'Member' };

const Shell: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({ title, onClose, children }) => (
  <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
    <div className="bg-white w-full sm:max-w-lg max-h-[94vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl">
      <div className="flex items-center justify-between border-b px-5 py-3.5">
        <h3 className="font-bold text-slate-900">{title}</h3>
        <button type="button" onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
      </div>
      <div className="p-5 text-sm">{children}</div>
    </div>
  </div>
);

/** Edit a team member (Admin+; only a Superadmin may edit or create a Superadmin). */
export const EditUserDialog: React.FC<{ user: any; actorIsSuperadmin: boolean; onClose: () => void; onSaved: () => void }> =
  ({ user, actorIsSuperadmin, onClose, onSaved }) => {
  const [form, setForm] = useState({
    full_name: user.full_name || '', email: user.email || '', phone: user.phone || '',
    designation: user.designation || '', system_role: user.system_role,
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const changes: any = {};
    for (const [k, v] of Object.entries(form)) if ((user as any)[k] !== v) changes[k] = v;
    if (!Object.keys(changes).length) { onClose(); return; }
    setSaving(true);
    setError('');
    console.info('[team] edit user', user.email, Object.keys(changes));
    try {
      await api.patch(`/api/v1/accounts/users/${user.id}/`, changes);
      onSaved();
    } catch (err) {
      setError(errorMessage(err, 'Could not save.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell title={`Edit ${user.full_name}`} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        {error && <div role="alert" className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{error}</div>}
        <div>
          <label htmlFor="eu-name" className="block font-medium text-slate-700 mb-1">Full name *</label>
          <input id="eu-name" required value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} className={inputCls} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="eu-email" className="block font-medium text-slate-700 mb-1">Email (login) *</label>
            <input id="eu-email" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label htmlFor="eu-phone" className="block font-medium text-slate-700 mb-1">Phone</label>
            <input id="eu-phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label htmlFor="eu-des" className="block font-medium text-slate-700 mb-1">Designation</label>
            <input id="eu-des" value={form.designation} onChange={e => setForm({ ...form, designation: e.target.value })} className={inputCls} placeholder="e.g. Article Trainee" />
          </div>
          <div>
            <label htmlFor="eu-role" className="block font-medium text-slate-700 mb-1">System role</label>
            <select id="eu-role" value={form.system_role} onChange={e => setForm({ ...form, system_role: e.target.value })} className={inputCls}
              disabled={user.system_role === 'superadmin' && !actorIsSuperadmin}>
              <option value="staff">Staff</option>
              <option value="admin">Admin / Partner</option>
              {(actorIsSuperadmin || user.system_role === 'superadmin') && <option value="superadmin">Superadmin</option>}
            </select>
          </div>
        </div>
        {form.email !== user.email && <p className="text-xs text-amber-700">The person must log in with the new email next time.</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700">Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold inline-flex items-center gap-2">
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save
          </button>
        </div>
      </form>
    </Shell>
  );
};

/**
 * Move a user's open tasks to someone else (spec §5.4 A5), and optionally deactivate (spec U5:
 * deactivation forces a re-assign). Step 1 = preview (nothing changes), step 2 = move (+ deactivate).
 */
export const MoveTasksDialog: React.FC<{ user: any; staff: any[]; deactivate: boolean; onClose: () => void; onDone: (msg: string) => void }> =
  ({ user, staff, deactivate, onClose, onDone }) => {
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState<string[]>(['assigned', 'leader', 'manager', 'member']);
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState(deactivate ? 'Leaving the firm' : '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    api.post(`/api/v1/accounts/users/${user.id}/move_tasks/`, { preview: true })
      .then(res => setPreview(res))
      .catch(err => setError(errorMessage(err, 'Could not count the open tasks.')))
      .finally(() => setLoading(false));
  }, [user.id]);

  const total = preview ? Object.values(preview.counts as Record<string, number>).reduce((a, b) => a + b, 0) : 0;
  const selectedTotal = preview ? roles.reduce((a, r) => a + (preview.counts[r] || 0), 0) : 0;
  const candidates = staff.filter(s => s.id !== user.id && s.is_active !== false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      let moved: any = null;
      if (selectedTotal > 0) {
        moved = await api.post(`/api/v1/accounts/users/${user.id}/move_tasks/`, { to_user_id: target, roles, reason });
        console.info('[team] moved tasks', user.email, moved);
        if (moved.errors?.length) {
          setResult(moved);
          setSaving(false);
          return;          // show per-task errors; do not deactivate
        }
      }
      if (deactivate) {
        await api.patch(`/api/v1/accounts/users/${user.id}/`, { is_active: false });
        console.info('[team] deactivated', user.email);
      }
      const n = moved ? Object.values(moved.moved as Record<string, number>).reduce((a, b) => a + b, 0) : 0;
      onDone(deactivate ? `${user.full_name} deactivated${n ? `; ${n} task role(s) moved` : ''}.` : `${n} task role(s) moved.`);
    } catch (err) {
      setError(errorMessage(err, 'The change was not saved.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell title={deactivate ? `Deactivate ${user.full_name}` : `Move open tasks of ${user.full_name}`} onClose={onClose}>
      {loading ? <p className="text-slate-500 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Counting open tasks…</p> : (
        <form onSubmit={submit} className="space-y-3">
          {error && <div role="alert" className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{error}</div>}
          {result?.errors?.length > 0 && (
            <div role="alert" className="p-2.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-xs space-y-1">
              <p className="font-semibold">Some tasks were not moved. Fix them and try again:</p>
              <ul className="list-disc pl-4">{result.errors.slice(0, 10).map((e: any, i: number) => <li key={i}>{e.task_number} ({e.role}): {e.error}</li>)}</ul>
            </div>
          )}
          {preview && total === 0 ? (
            <p className="text-slate-700">{user.full_name} has no open tasks.{deactivate && ' The account can be deactivated now. History is kept.'}</p>
          ) : preview && (
            <>
              <p className="text-slate-700">{user.full_name} has open tasks. Choose who gets them.{deactivate && ' The account is deactivated after the move. History is kept.'}</p>
              <fieldset className="grid grid-cols-2 gap-1.5">
                <legend className="sr-only">Roles to move</legend>
                {Object.keys(ROLE_NAMES).map(r => (
                  <label key={r} className="flex items-center gap-2 p-2 rounded-lg border border-slate-200">
                    <input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={roles.includes(r)}
                      disabled={deactivate && r === 'assigned'}
                      onChange={e => setRoles(e.target.checked ? [...roles, r] : roles.filter(x => x !== r))} />
                    <span>{ROLE_NAMES[r]} <strong>({preview.counts[r] || 0})</strong></span>
                  </label>
                ))}
              </fieldset>
              {deactivate && <p className="text-xs text-slate-500">"Assigned to" tasks must move before deactivation.</p>}
              <div>
                <label htmlFor="mt-target" className="block font-medium text-slate-700 mb-1">Give the tasks to *</label>
                <select id="mt-target" required={selectedTotal > 0} value={target} onChange={e => setTarget(e.target.value)} className={inputCls}>
                  <option value="">Choose a person…</option>
                  {candidates.map(s => <option key={s.id} value={s.id}>{s.full_name}{s.designation ? ` · ${s.designation}` : ''}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="mt-reason" className="block font-medium text-slate-700 mb-1">Reason *</label>
                <input id="mt-reason" required={selectedTotal > 0} minLength={3} value={reason} onChange={e => setReason(e.target.value)} className={inputCls} />
              </div>
              {preview.tasks?.length > 0 && (
                <details className="text-xs text-slate-600">
                  <summary className="cursor-pointer font-semibold">Show tasks ({Math.min(preview.tasks.length, 50)}{total > 50 ? '+' : ''})</summary>
                  <ul className="mt-1 max-h-40 overflow-y-auto space-y-0.5">{preview.tasks.map((t: any) => <li key={t.id}><span className="font-mono">{t.task_number}</span> · {t.title}</li>)}</ul>
                </details>
              )}
              <p className="text-xs text-slate-500 flex gap-1.5"><AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-600" />Each person gets a notification. Every change is in the task history.</p>
            </>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700">Cancel</button>
            <button type="submit" disabled={saving || (!deactivate && selectedTotal === 0)}
              className={`px-4 py-2 rounded-lg font-semibold text-white inline-flex items-center gap-2 disabled:opacity-60 ${deactivate ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'}`}>
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {deactivate ? (selectedTotal > 0 ? 'Move tasks and deactivate' : 'Deactivate') : 'Move tasks'}
            </button>
          </div>
        </form>
      )}
    </Shell>
  );
};


/** Admin: give a user a new temporary password (shown one time). The user must change it at the next sign-in. */
export const TemporaryPasswordDialog: React.FC<{ user: any; onClose: () => void }> = ({ user, onClose }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ temporary_password: string; message: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const create = async () => {
    setBusy(true); setError('');
    try {
      const res = await api.post(`/api/v1/accounts/users/${user.id}/set_temporary_password/`);
      console.info('[team] temporary password set', { user: user.id });
      setResult(res);
    } catch (err: any) {
      setError(errorMessage(err, 'Could not set a temporary password.'));
    } finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(result!.temporary_password); setCopied(true); }
    catch (e) { console.warn('[team] clipboard not available', e); }
  };

  return (
    <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Reset password">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-6 space-y-4 text-sm">
        <div className="flex items-start justify-between">
          <h3 className="font-semibold text-slate-900">Reset password: {user.full_name}</h3>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-slate-100"><X className="w-4 h-4" /></button>
        </div>
        {error && <div role="alert" className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{error}</div>}
        {result ? (
          <>
            <p className="text-slate-700">{result.message}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-base font-mono tracking-wide bg-slate-100 border border-slate-200 rounded-lg px-3 py-2 select-all">{result.temporary_password}</code>
              <button type="button" onClick={copy} className="text-xs px-3 py-2 rounded-lg border font-semibold border-slate-300 hover:bg-slate-50">{copied ? 'Copied' : 'Copy'}</button>
            </div>
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2.5">This password shows only now. Give it to the person in a private way (not in a group chat).</p>
            <div className="flex justify-end"><button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold">Done</button></div>
          </>
        ) : (
          <>
            <ul className="list-disc pl-5 text-slate-600 space-y-1">
              <li>A new random password is made for {user.email}.</li>
              <li>The old password stops working. The person is signed out on all devices.</li>
              <li>At the next sign-in, the person must choose a new password.</li>
            </ul>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border border-slate-300 font-semibold text-slate-700 hover:bg-slate-50">Cancel</button>
              <button type="button" onClick={create} disabled={busy} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold disabled:opacity-60">
                {busy && <Loader2 className="w-4 h-4 animate-spin" />} Make temporary password
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
