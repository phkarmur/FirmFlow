import React, { useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { inputCls } from '../components/ui';

/** Shared new-password fields (Django rules: 10+ characters, not common, not only numbers). */
const NewPasswordFields: React.FC<{ value: { a: string; b: string }; onChange: (v: { a: string; b: string }) => void }> = ({ value, onChange }) => (
  <>
    <div>
      <label htmlFor="np-a" className="block text-xs font-semibold text-slate-700 mb-1">New password</label>
      <input id="np-a" type="password" autoComplete="new-password" required minLength={10} value={value.a}
        onChange={e => onChange({ ...value, a: e.target.value })} className={inputCls} />
    </div>
    <div>
      <label htmlFor="np-b" className="block text-xs font-semibold text-slate-700 mb-1">Repeat new password</label>
      <input id="np-b" type="password" autoComplete="new-password" required minLength={10} value={value.b}
        onChange={e => onChange({ ...value, b: e.target.value })} className={inputCls} />
    </div>
    <p className="text-xs text-slate-500">At least 10 characters. Not only numbers, and not a common password.</p>
  </>
);

const Shell: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
    <div className="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8 space-y-5">
      <div className="text-center">
        <div className="w-12 h-12 bg-emerald-600 rounded-xl mx-auto flex items-center justify-center text-white"><KeyRound className="w-6 h-6" /></div>
        <h2 className="text-xl font-bold text-slate-900 mt-3">{title}</h2>
      </div>
      {children}
    </div>
  </div>
);

/** /reset-password?uid=..&token=.. (link from the reset e-mail). Shown to signed-out users. */
export const ResetPasswordPage: React.FC = () => {
  const params = new URLSearchParams(window.location.search);
  const uid = params.get('uid') || '';
  const token = params.get('token') || '';
  const [pw, setPw] = useState({ a: '', b: '' });
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (pw.a !== pw.b) { setError('The new passwords do not match.'); return; }
    setSaving(true);
    try {
      const res = await api.post('/api/v1/auth/password_reset/confirm/', { uid, token, new_password: pw.a });
      console.info('[auth] password reset done');
      setDone(res.message);
    } catch (err: any) {
      setError(errorMessage(err, 'Could not set the password.'));
    } finally { setSaving(false); }
  };

  const toLogin = () => { window.location.href = '/'; };
  if (!uid || !token) {
    return <Shell title="Reset password"><p className="text-sm text-slate-600">This link is not complete. Open the link from the e-mail again, or ask for a new link on the sign-in page.</p>
      <button type="button" onClick={toLogin} className="w-full border border-slate-300 rounded-lg py-2 text-sm font-semibold">Go to sign in</button></Shell>;
  }
  return (
    <Shell title="Set a new password">
      {done ? (
        <>
          <div role="status" className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-lg">{done}</div>
          <button type="button" onClick={toLogin} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg py-2.5 text-sm font-semibold">Go to sign in</button>
        </>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          {error && <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg">{error}</div>}
          <NewPasswordFields value={pw} onChange={setPw} />
          <button type="submit" disabled={saving} className="w-full inline-flex justify-center items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold">
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} Set password
          </button>
          <button type="button" onClick={toLogin} className="w-full text-xs text-slate-600 hover:text-slate-900">Back to sign in</button>
        </form>
      )}
    </Shell>
  );
};

/** Shown after sign-in with a temporary password (User.must_change_password). Nothing else is open until done. */
export const ForcePasswordChange: React.FC = () => {
  const { user, refresh, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState({ a: '', b: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (pw.a !== pw.b) { setError('The new passwords do not match.'); return; }
    setSaving(true);
    try {
      await api.post('/api/v1/auth/change_password/', { current_password: current, new_password: pw.a });
      console.info('[auth] temporary password replaced');
      await refresh();
    } catch (err: any) {
      setError(errorMessage(err, 'Could not change the password.'));
    } finally { setSaving(false); }
  };

  return (
    <Shell title="Choose your own password">
      <p className="text-sm text-slate-600">Hello {user?.full_name}. You signed in with a temporary password from your admin. Set your own password to continue.</p>
      <form onSubmit={submit} className="space-y-3">
        {error && <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg">{error}</div>}
        <div>
          <label htmlFor="tp-cur" className="block text-xs font-semibold text-slate-700 mb-1">Temporary password</label>
          <input id="tp-cur" type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} className={inputCls} />
        </div>
        <NewPasswordFields value={pw} onChange={setPw} />
        <button type="submit" disabled={saving} className="w-full inline-flex justify-center items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold">
          {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save and continue
        </button>
        <button type="button" onClick={() => logout()} className="w-full text-xs text-slate-600 hover:text-slate-900">Sign out</button>
      </form>
    </Shell>
  );
};
