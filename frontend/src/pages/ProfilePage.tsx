import React, { useEffect, useState } from 'react';
import { Loader2, Save, KeyRound, Bell, MonitorSmartphone } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { useAuth } from '../context/AuthContext';

/** My profile (spec §6.2 item 7): name, phone, password, notification preferences. */
export const ProfilePage: React.FC = () => {
  const { refresh } = useAuth();
  const [profile, setProfile] = useState<any>(null);
  const [form, setForm] = useState<any>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [othersMsg, setOthersMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [othersBusy, setOthersBusy] = useState(false);
  const logoutOthers = async () => {
    setOthersBusy(true); setOthersMsg(null);
    try {
      const res = await api.post('/api/v1/auth/logout_others/');
      console.info('[profile] signed out other devices', res.sessions_ended);
      setOthersMsg({ ok: true, text: res.message });
    } catch (err: any) {
      setOthersMsg({ ok: false, text: errorMessage(err, 'Could not sign out the other devices.') });
    } finally { setOthersBusy(false); }
  };
  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' });
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

  useEffect(() => {
    api.get('/api/v1/auth/profile/')
      .then(res => { setProfile(res); setForm(res); })
      .catch(err => setMsg({ ok: false, text: errorMessage(err, 'Could not load your profile.') }));
  }, []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.patch('/api/v1/auth/profile/', {
        full_name: form.full_name, phone: form.phone, notifications: form.notifications,
      });
      setProfile(res);
      setForm(res);
      setMsg({ ok: true, text: 'Saved.' });
      console.info('[profile] saved', res.notifications);
      refresh();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err, 'Could not save.') });
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMsg(null);
    if (pw.new_password !== pw.confirm) {
      setPwMsg({ ok: false, text: 'The new passwords do not match.' });
      return;
    }
    setPwSaving(true);
    try {
      await api.post('/api/v1/auth/change_password/', { current_password: pw.current_password, new_password: pw.new_password });
      setPw({ current_password: '', new_password: '', confirm: '' });
      setPwMsg({ ok: true, text: 'Password changed. You are signed out on your other devices.' });
    } catch (err) {
      setPwMsg({ ok: false, text: errorMessage(err, 'Could not change the password.') });
    } finally {
      setPwSaving(false);
    }
  };

  if (!form) return <div className="p-8 text-center text-slate-500">{msg?.text || 'Loading…'}</div>;
  const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none disabled:bg-slate-100';
  const Note = ({ m }: { m: { ok: boolean; text: string } | null }) => m && (
    <div role={m.ok ? 'status' : 'alert'} className={`p-2.5 rounded-lg text-xs border ${m.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-rose-50 border-rose-200 text-rose-800'}`}>{m.text}</div>
  );

  return (
    <div className="max-w-2xl space-y-5">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight">My profile</h2>
        <p className="text-sm text-slate-500 mt-1">{profile.email} · {profile.designation || profile.system_role}</p>
      </div>

      <form onSubmit={save} className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 text-sm">
        <Note m={msg} />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="pf-name" className="block font-medium text-slate-700 mb-1">Full name</label>
            <input id="pf-name" required value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label htmlFor="pf-phone" className="block font-medium text-slate-700 mb-1">Phone</label>
            <input id="pf-phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={inputCls} />
          </div>
        </div>
        <fieldset className="space-y-2">
          <legend className="font-semibold text-slate-900 flex items-center gap-2 mb-1"><Bell className="w-4 h-4 text-slate-500" /> Notifications</legend>
          <p className="text-xs text-slate-500">You always see notifications in the bell. These settings control e-mail only.</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={form.notifications.email_enabled}
              onChange={e => setForm({ ...form, notifications: { ...form.notifications, email_enabled: e.target.checked } })} />
            E-mail me about my tasks (assigned, comments, issues, due today…)
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={form.notifications.digest_enabled}
              onChange={e => setForm({ ...form, notifications: { ...form.notifications, digest_enabled: e.target.checked } })} />
            Daily digest e-mail at 07:00 (admins only)
          </label>
        </fieldset>
        <div className="flex justify-end">
          <button type="submit" disabled={saving} className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white px-4 py-2 rounded-lg font-semibold">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save
          </button>
        </div>
      </form>

      <form onSubmit={changePassword} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3 text-sm">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2"><KeyRound className="w-4 h-4 text-slate-500" /> Change password</h3>
        <Note m={pwMsg} />
        <div>
          <label htmlFor="pw-cur" className="block font-medium text-slate-700 mb-1">Current password</label>
          <input id="pw-cur" type="password" autoComplete="current-password" required value={pw.current_password} onChange={e => setPw({ ...pw, current_password: e.target.value })} className={inputCls} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="pw-new" className="block font-medium text-slate-700 mb-1">New password</label>
            <input id="pw-new" type="password" autoComplete="new-password" required minLength={10} value={pw.new_password} onChange={e => setPw({ ...pw, new_password: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label htmlFor="pw-conf" className="block font-medium text-slate-700 mb-1">Repeat new password</label>
            <input id="pw-conf" type="password" autoComplete="new-password" required minLength={10} value={pw.confirm} onChange={e => setPw({ ...pw, confirm: e.target.value })} className={inputCls} />
          </div>
        </div>
        <p className="text-xs text-slate-500">At least 10 characters. Not only numbers, and not a common password.</p>
        <div className="flex justify-end">
          <button type="submit" disabled={pwSaving} className="inline-flex items-center gap-2 border border-slate-300 hover:bg-slate-50 px-4 py-2 rounded-lg font-semibold text-slate-800">
            {pwSaving && <Loader2 className="w-4 h-4 animate-spin" />} Change password
          </button>
        </div>
      </form>

      <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-3 text-sm">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2"><MonitorSmartphone className="w-4 h-4 text-slate-500" /> Signed-in devices</h3>
        <Note m={othersMsg} />
        <p className="text-slate-600">Use this if you signed in on a shared or lost computer or phone. This device stays signed in.</p>
        <div className="flex justify-end">
          <button type="button" onClick={logoutOthers} disabled={othersBusy} className="inline-flex items-center gap-2 border border-slate-300 hover:bg-slate-50 px-4 py-2 rounded-lg font-semibold text-slate-800 disabled:opacity-60">
            {othersBusy && <Loader2 className="w-4 h-4 animate-spin" />} Sign out all other devices
          </button>
        </div>
      </section>
    </div>
  );
};
