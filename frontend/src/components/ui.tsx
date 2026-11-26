/** Small shared UI pieces so every screen looks and behaves the same. */
import React from 'react';
import { X, Loader2 } from 'lucide-react';

export const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none disabled:bg-slate-100 disabled:text-slate-500';
export const btn = {
  primary: 'inline-flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white px-3.5 py-2 rounded-lg text-sm font-semibold',
  secondary: 'inline-flex items-center justify-center gap-1.5 border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-50 text-slate-700 px-3.5 py-2 rounded-lg text-sm font-semibold',
  danger: 'inline-flex items-center justify-center gap-1.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white px-3.5 py-2 rounded-lg text-sm font-semibold',
  small: 'inline-flex items-center gap-1 border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-50 text-slate-700 px-2.5 py-1 rounded-md text-xs font-semibold',
};

export const Modal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }> = ({ title, onClose, children, wide }) => (
  <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}
    onKeyDown={e => e.key === 'Escape' && onClose()}>
    <div className={`bg-white w-full ${wide ? 'sm:max-w-3xl' : 'sm:max-w-lg'} max-h-[94vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl`}>
      <div className="sticky top-0 bg-white flex items-center justify-between border-b px-5 py-3.5 z-10">
        <h3 className="font-bold text-slate-900">{title}</h3>
        <button type="button" onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
      </div>
      <div className="p-5 text-sm">{children}</div>
    </div>
  </div>
);

export const Field: React.FC<{ label: string; htmlFor: string; hint?: string; children: React.ReactNode }> = ({ label, htmlFor, hint, children }) => (
  <div>
    <label htmlFor={htmlFor} className="block font-medium text-slate-700 mb-1 text-sm">{label}</label>
    {children}
    {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
  </div>
);

export const Alert: React.FC<{ kind?: 'error' | 'ok' | 'warn'; children: React.ReactNode; onClose?: () => void }> = ({ kind = 'error', children, onClose }) => {
  const cls = kind === 'ok' ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
    : kind === 'warn' ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-rose-50 border-rose-200 text-rose-800';
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`p-2.5 rounded-lg border text-xs flex items-start justify-between gap-3 ${cls}`}>
      <div>{children}</div>
      {onClose && <button type="button" onClick={onClose} aria-label="Dismiss" className="font-bold">×</button>}
    </div>
  );
};

export const Pager: React.FC<{ page: number; totalPages: number; count: number; onPage: (p: number) => void }> = ({ page, totalPages, count, onPage }) => (
  <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-slate-100 bg-slate-50/70 text-xs text-slate-500">
    <span>{count} row{count === 1 ? '' : 's'}</span>
    <span className="flex items-center gap-2">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className={btn.small}>Previous</button>
      <span>Page {page} of {totalPages}</span>
      <button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)} className={btn.small}>Next</button>
    </span>
  </div>
);

export const Spinner: React.FC<{ text?: string }> = ({ text = 'Loading…' }) => (
  <p className="p-6 text-center text-slate-500 text-sm flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />{text}</p>
);

export const PageHeader: React.FC<{ title: string; subtitle?: string; actions?: React.ReactNode }> = ({ title, subtitle, actions }) => (
  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
    <div>
      <h2 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h2>
      {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>
);
