import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { errorMessage } from '../api/client';
import { Lock, Mail, ArrowRight } from 'lucide-react';
import { api } from '../api/client';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  // 'login' = sign-in form, 'forgot' = ask for a reset link
  const [mode, setMode] = useState<'login' | 'forgot'>('login');
  const [notice, setNotice] = useState('');

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setNotice(''); setLoading(true);
    try {
      const res = await api.post('/api/v1/auth/password_reset/', { email });
      console.info('[auth] password reset link requested');
      setNotice(res.message);
    } catch (err: any) {
      setError(errorMessage(err, 'Could not send the reset link.'));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      if (err?.status === 429) console.warn('[auth] sign-in locked for a short time (too many failed attempts)');
      setError(errorMessage(err, 'Invalid email or password.'));
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = (userEmail: string, userPass: string) => {
    setEmail(userEmail);
    setPassword(userPass);
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8 space-y-6">
        <div className="text-center">
          <div className="w-12 h-12 bg-emerald-600 rounded-xl mx-auto flex items-center justify-center text-white font-black text-xl shadow-md">
            FF
          </div>
          <h2 className="text-2xl font-black text-slate-900 tracking-tight mt-4">
            FirmFlow
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Chartered Accountant & Tax Practice Management System
          </p>
        </div>

        {error && (
          <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg font-medium">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-lg font-medium">
            {notice}
          </div>
        )}

        {mode === 'forgot' ? (
          <form onSubmit={handleForgot} className="space-y-4">
            <p className="text-sm text-slate-600">Enter your e-mail address. We send a link to set a new password. If e-mail does not arrive, ask your firm admin for a temporary password.</p>
            <div>
              <label htmlFor="fp-email" className="block text-xs font-semibold text-slate-700 mb-1">Email Address</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input id="fp-email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-emerald-500 outline-none" />
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg text-sm transition shadow-sm">
              {loading ? 'Sending…' : 'Send reset link'}
            </button>
            <button type="button" onClick={() => { setMode('login'); setError(''); setNotice(''); }} className="w-full text-xs text-slate-600 hover:text-slate-900">
              Back to sign in
            </button>
          </form>
        ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Email Address</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="ca.partner@firm.com"
                className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-emerald-500 outline-none"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">Password</label>
              <button type="button" onClick={() => { setMode('forgot'); setError(''); setNotice(''); }} className="text-xs text-emerald-700 hover:underline">Forgot password?</button>
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••••"
                className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-emerald-500 outline-none"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg text-sm transition shadow-sm flex items-center justify-center gap-2"
          >
            <span>{loading ? 'Authenticating...' : 'Sign In to FirmFlow'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
        )}

        {/* Demo logins: development build only (npm run dev). Not shown in a production build. */}
        {import.meta.env.DEV && mode === 'login' && (
        <div className="pt-4 border-t border-slate-100">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider text-center mb-2">
            Demo accounts (development only)
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              type="button"
              onClick={() => handleQuickLogin('admin@shahca.com', 'Admin@123456')}
              className="p-2 border border-slate-200 hover:border-emerald-500 hover:bg-emerald-50 rounded-lg text-left transition"
            >
              <div className="font-semibold text-slate-800">CA Rajesh Shah</div>
              <div className="text-[10px] text-slate-500">Managing Partner</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('priya.verma@shahca.com', 'Staff@123456')}
              className="p-2 border border-slate-200 hover:border-emerald-500 hover:bg-emerald-50 rounded-lg text-left transition"
            >
              <div className="font-semibold text-slate-800">Priya Verma</div>
              <div className="text-[10px] text-slate-500">Article Trainee</div>
            </button>
          </div>
        </div>
        )}
      </div>
    </div>
  );
};
