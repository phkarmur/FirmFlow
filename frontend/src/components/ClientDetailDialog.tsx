import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Pencil, Trash2, ExternalLink } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { Modal, Field, Alert, Spinner, inputCls, btn } from './ui';

const TYPES = [['individual', 'Individual'], ['huf', 'HUF'], ['partnership', 'Partnership firm'], ['llp', 'LLP'], ['company', 'Company'], ['trust', 'Trust'], ['aop', 'AOP / BOI'], ['other', 'Other']];
const CONTACT_ROLES = [['owner', 'Owner / Proprietor'], ['director', 'Director / Partner'], ['accountant', 'Accountant / Manager'], ['other', 'Other']];

/** Client detail + edit (spec §6.1 item 7): details, contacts, tasks by FY. Staff see it read-only. */
export const ClientDetailDialog: React.FC<{ clientId: string; canEdit: boolean; onClose: () => void; onChanged: () => void }> =
  ({ clientId, canEdit, onClose, onChanged }) => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'details' | 'contacts' | 'tasks'>('details');
  const [client, setClient] = useState<any>(null);
  const [form, setForm] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [summaryError, setSummaryError] = useState('');
  const [groups, setGroups] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState<any>(null);
  const [contact, setContact] = useState<any>(null);

  const load = () => {
    api.get(`/api/v1/clients/${clientId}/`).then(c => { setClient(c); setForm({ ...c, pan: '' }); })
      .catch(err => setError(errorMessage(err, 'Could not open the client.')));
    api.get(`/api/v1/clients/${clientId}/summary/`).then(setSummary).catch(err => { console.error('[client] summary failed', err); setSummaryError(errorMessage(err, 'Could not load the task summary.')); });
  };
  useEffect(() => {
    load();
    if (canEdit) api.get('/api/v1/clients/groups/?page_size=200').then((r: any) => setGroups(r.results || [])).catch(() => undefined);
  }, [clientId]);

  const save = async (e?: React.FormEvent, confirm = false) => {
    e?.preventDefault();
    setBusy(true); setError(''); setNotice('');
    const fields = ['name', 'client_type', 'gstin', 'tan', 'cin', 'email', 'phone', 'address', 'state_code', 'client_group', 'is_active', 'is_blocked_for_new_tasks', 'notes'];
    const payload: any = {};
    for (const k of fields) if ((form[k] ?? '') !== (client[k] ?? '')) payload[k] = form[k] === '' && k === 'client_group' ? null : form[k];
    if (form.pan) payload.pan = form.pan;
    if (confirm) payload.confirm_deactivate = true;
    if (!Object.keys(payload).length) { setBusy(false); setNotice('Nothing changed.'); return; }
    console.info('[client] save', Object.keys(payload));
    try {
      await api.patch(`/api/v1/clients/${clientId}/`, payload);
      setConfirmDeactivate(null); setNotice('Saved.'); load(); onChanged();
    } catch (err: any) {
      if (err?.status === 409 && err?.requires_confirmation) setConfirmDeactivate(err);
      else setError(errorMessage(err, 'Could not save.'));
    } finally { setBusy(false); }
  };

  const saveContact = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      if (contact.id) await api.patch(`/api/v1/clients/contacts/${contact.id}/`, contact);
      else await api.post('/api/v1/clients/contacts/', { ...contact, client: clientId });
      setContact(null); load();
    } catch (err) { setError(errorMessage(err, 'Could not save the contact.')); } finally { setBusy(false); }
  };
  const deleteContact = async (c: any) => {
    if (!window.confirm(`Delete contact ${c.name}?`)) return;
    try { await api.delete(`/api/v1/clients/contacts/${c.id}/`); load(); } catch (err) { setError(errorMessage(err)); }
  };

  if (!client || !form) return <Modal title="Client" onClose={onClose}>{error ? <Alert>{error}</Alert> : <Spinner />}</Modal>;
  const ro = !canEdit;
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });

  return (
    <Modal title={client.name} onClose={onClose} wide>
      <div className="space-y-4">
        <div role="tablist" className="flex gap-1 border-b">
          {[['details', 'Details'], ['contacts', `Contacts (${client.contacts?.length || 0})`], ['tasks', 'Tasks']].map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id as any)}
              className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === id ? 'border-emerald-600 text-emerald-800' : 'border-transparent text-slate-500'}`}>{label}</button>
          ))}
        </div>
        {error && <Alert onClose={() => setError('')}>{error}</Alert>}
        {notice && <Alert kind="ok" onClose={() => setNotice('')}>{notice}</Alert>}
        {client.pan_warning && <Alert kind="warn">{client.pan_warning}</Alert>}

        {tab === 'details' && (
          <form onSubmit={save} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Name *" htmlFor="c-name"><input id="c-name" required disabled={ro} value={form.name} onChange={e => set('name', e.target.value)} className={inputCls} /></Field>
              <Field label="Type" htmlFor="c-type"><select id="c-type" disabled={ro} value={form.client_type} onChange={e => set('client_type', e.target.value)} className={inputCls}>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
              <Field label="PAN" htmlFor="c-pan" hint={`Saved: ${client.pan_masked || 'none'}. Type a new PAN only to change it.`}>
                <input id="c-pan" disabled={ro} maxLength={10} value={form.pan} onChange={e => set('pan', e.target.value.toUpperCase())} placeholder="ABCDE1234F" className={inputCls + ' font-mono'} />
              </Field>
              <Field label="GSTIN" htmlFor="c-gstin"><input id="c-gstin" disabled={ro} maxLength={15} value={form.gstin || ''} onChange={e => set('gstin', e.target.value.toUpperCase())} className={inputCls + ' font-mono'} /></Field>
              <Field label="TAN" htmlFor="c-tan"><input id="c-tan" disabled={ro} maxLength={10} value={form.tan || ''} onChange={e => set('tan', e.target.value.toUpperCase())} className={inputCls + ' font-mono'} /></Field>
              <Field label="CIN / LLPIN" htmlFor="c-cin"><input id="c-cin" disabled={ro} maxLength={21} value={form.cin || ''} onChange={e => set('cin', e.target.value.toUpperCase())} className={inputCls + ' font-mono'} /></Field>
              <Field label="Email" htmlFor="c-email"><input id="c-email" type="email" disabled={ro} value={form.email || ''} onChange={e => set('email', e.target.value)} className={inputCls} /></Field>
              <Field label="Phone" htmlFor="c-phone"><input id="c-phone" disabled={ro} value={form.phone || ''} onChange={e => set('phone', e.target.value)} className={inputCls} /></Field>
              <Field label="Group" htmlFor="c-group">
                <select id="c-group" disabled={ro} value={form.client_group || ''} onChange={e => set('client_group', e.target.value)} className={inputCls}>
                  <option value="">No group</option>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                  {ro && client.group_name && <option value={client.client_group}>{client.group_name}</option>}
                </select>
              </Field>
              <Field label="State code" htmlFor="c-state" hint="Filled from the GSTIN when empty."><input id="c-state" disabled={ro} maxLength={2} value={form.state_code || ''} onChange={e => set('state_code', e.target.value)} className={inputCls} /></Field>
            </div>
            <Field label="Address" htmlFor="c-addr"><textarea id="c-addr" rows={2} disabled={ro} value={form.address || ''} onChange={e => set('address', e.target.value)} className={inputCls} /></Field>
            <Field label="Notes" htmlFor="c-notes"><textarea id="c-notes" rows={2} disabled={ro} value={form.notes || ''} onChange={e => set('notes', e.target.value)} className={inputCls} /></Field>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" disabled={ro} className="h-4 w-4 accent-emerald-600" checked={form.is_active} onChange={e => set('is_active', e.target.checked)} />Active</label>
              <label className="flex items-center gap-2"><input type="checkbox" disabled={ro} className="h-4 w-4 accent-emerald-600" checked={form.is_blocked_for_new_tasks} onChange={e => set('is_blocked_for_new_tasks', e.target.checked)} />Block new tasks (e.g. fees pending)</label>
            </div>
            {confirmDeactivate && (
              <Alert kind="warn">
                <p className="font-semibold">{confirmDeactivate.error}</p>
                <ul className="list-disc pl-4 mt-1">{confirmDeactivate.open_tasks?.slice(0, 10).map((t: any) => <li key={t.id}>{t.task_number} · {t.title}</li>)}</ul>
                <button type="button" className={`${btn.danger} mt-2`} disabled={busy} onClick={() => save(undefined, true)}>Deactivate anyway</button>
              </Alert>
            )}
            {canEdit && <div className="flex justify-end"><button type="submit" disabled={busy} className={btn.primary}>Save</button></div>}
          </form>
        )}

        {tab === 'contacts' && (
          <div className="space-y-2">
            {canEdit && <div className="flex justify-end"><button type="button" className={btn.small} onClick={() => setContact({ name: '', role: 'owner', email: '', phone: '', is_primary: !(client.contacts || []).length, receives_task_emails: true })}><Plus className="w-3 h-3" /> Contact</button></div>}
            {(client.contacts || []).length === 0 && <p className="text-xs text-slate-500">No contacts. E-mail to the client is not possible without one.</p>}
            {(client.contacts || []).map((c: any) => (
              <div key={c.id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-slate-200">
                <div className="text-sm"><strong>{c.name}</strong>{c.is_primary && <span className="ml-2 text-[10px] bg-emerald-100 text-emerald-800 px-1.5 rounded">Primary</span>}
                  <span className="block text-xs text-slate-500">{CONTACT_ROLES.find(r => r[0] === c.role)?.[1]} · {c.email || 'no email'} · {c.phone || 'no phone'}</span></div>
                {canEdit && <span className="flex gap-1 text-slate-500">
                  <button type="button" aria-label={`Edit ${c.name}`} onClick={() => setContact({ ...c })} className="p-1"><Pencil className="w-3.5 h-3.5" /></button>
                  <button type="button" aria-label={`Delete ${c.name}`} onClick={() => deleteContact(c)} className="p-1 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button></span>}
              </div>
            ))}
            {contact && (
              <form onSubmit={saveContact} className="p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Field label="Name *" htmlFor="ct-n"><input id="ct-n" required value={contact.name} onChange={e => setContact({ ...contact, name: e.target.value })} className={inputCls} /></Field>
                  <Field label="Role" htmlFor="ct-r"><select id="ct-r" value={contact.role} onChange={e => setContact({ ...contact, role: e.target.value })} className={inputCls}>{CONTACT_ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
                  <Field label="Email" htmlFor="ct-e"><input id="ct-e" type="email" value={contact.email} onChange={e => setContact({ ...contact, email: e.target.value })} className={inputCls} /></Field>
                  <Field label="Phone" htmlFor="ct-p"><input id="ct-p" value={contact.phone} onChange={e => setContact({ ...contact, phone: e.target.value })} className={inputCls} /></Field>
                </div>
                <div className="flex flex-wrap gap-4 text-sm">
                  <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={contact.is_primary} onChange={e => setContact({ ...contact, is_primary: e.target.checked })} />Primary</label>
                  <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-emerald-600" checked={contact.receives_task_emails} onChange={e => setContact({ ...contact, receives_task_emails: e.target.checked })} />Receives task e-mails (client portal, later)</label>
                </div>
                <div className="flex justify-end gap-2"><button type="button" className={btn.secondary} onClick={() => setContact(null)}>Cancel</button><button type="submit" disabled={busy} className={btn.primary}>Save contact</button></div>
              </form>
            )}
          </div>
        )}

        {tab === 'tasks' && (
          <div className="space-y-3">
            <p className="text-sm text-slate-700">{summary ? <>Open: <strong>{summary.open_tasks}</strong> · Overdue: <strong className="text-red-700">{summary.overdue}</strong></> : summaryError ? <span role="alert" className="text-rose-700">{summaryError}</span> : 'Loading…'}</p>
            <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase"><tr><th className="text-left px-3 py-2">FY</th><th className="px-3 py-2">Total</th><th className="px-3 py-2">Pending</th><th className="px-3 py-2">Completed</th><th className="px-3 py-2">Unbilled</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {(summary?.by_fy || []).map((r: any) => <tr key={r.fy__label || 'none'}><td className="px-3 py-1.5">{r.fy__label ? `FY ${r.fy__label}` : 'No FY'}</td><td className="text-center">{r.total}</td><td className="text-center">{r.pending}</td><td className="text-center">{r.completed}</td><td className="text-center">{r.unbilled}</td></tr>)}
                {summary && !summary.by_fy.length && <tr><td colSpan={5} className="px-3 py-2 text-xs text-slate-500">No tasks.</td></tr>}
              </tbody>
            </table>
            </div>
            <button type="button" className={btn.secondary} onClick={() => { onClose(); navigate(`/tasks?client=${clientId}`); }}><ExternalLink className="w-4 h-4" /> Open this client's tasks</button>
          </div>
        )}
      </div>
    </Modal>
  );
};

/** Client groups (spec C3): families / company groups; batches and reports can use a group. */
export const ClientGroupsDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [groups, setGroups] = useState<any[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const load = () => api.get('/api/v1/clients/groups/?page_size=200').then((r: any) => setGroups(r.results || [])).catch(err => setError(errorMessage(err)));
  useEffect(() => { load(); }, []);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api.post('/api/v1/clients/groups/', { name }); setName(''); load(); } catch (err) { setError(errorMessage(err, 'Could not add the group.')); }
  };
  const rename = async (g: any) => {
    const n = window.prompt('New name', g.name);
    if (!n || n === g.name) return;
    try { await api.patch(`/api/v1/clients/groups/${g.id}/`, { name: n }); load(); } catch (err) { setError(errorMessage(err)); }
  };
  const remove = async (g: any) => {
    if (!window.confirm(`Delete group "${g.name}"? Its ${g.client_count} client(s) stay, without a group.`)) return;
    try { await api.delete(`/api/v1/clients/groups/${g.id}/`); load(); } catch (err) { setError(errorMessage(err)); }
  };
  return (
    <Modal title="Client groups" onClose={onClose}>
      <div className="space-y-3">
        {error && <Alert onClose={() => setError('')}>{error}</Alert>}
        <form onSubmit={add} className="flex gap-2"><input aria-label="New group name" required value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Sharma family" className={inputCls} /><button type="submit" className={btn.primary}><Plus className="w-4 h-4" /> Add</button></form>
        <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg">
          {groups.length === 0 && <li className="px-3 py-2 text-xs text-slate-500">No groups yet. Put a client in a group from the client's Details tab.</li>}
          {groups.map(g => (
            <li key={g.id} className="flex items-center justify-between px-3 py-2 text-sm">
              <span>{g.name} <span className="text-xs text-slate-500">({g.client_count})</span></span>
              <span className="flex gap-1 text-slate-500">
                <button type="button" aria-label={`Rename ${g.name}`} onClick={() => rename(g)} className="p-1"><Pencil className="w-3.5 h-3.5" /></button>
                <button type="button" aria-label={`Delete ${g.name}`} onClick={() => remove(g)} className="p-1 hover:text-rose-700"><Trash2 className="w-3.5 h-3.5" /></button>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  );
};
