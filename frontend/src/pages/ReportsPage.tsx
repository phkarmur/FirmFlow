import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, ExternalLink } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { Alert, Pager, Spinner, PageHeader, inputCls, btn } from '../components/ui';
import { fmtDate, fmtDateTime, fmtNumber } from '../utils/format';

/**
 * Reports (spec §8) and audit log (spec §6.1-15). Every report: server query, paging where
 * the list can be long, CSV export of the same filters.
 */
type Col = { key: string; label: string; render?: (r: any) => React.ReactNode; num?: boolean };
type ReportDef = { id: string; label: string; url: string; paged?: boolean; dates?: boolean; csv?: boolean; cols?: Col[]; extra?: 'role' | 'metric' | 'grid' | 'issues' | 'audit' | 'activity' | 'search' };

// Firm date format + time zone (Settings), Indian number grouping: see utils/format.ts
const dt = (v: any) => fmtDateTime(v);
const d = (v: any) => fmtDate(v, '');

const REPORTS: ReportDef[] = [
  { id: 'employees', label: 'Staff workload', url: '/api/v1/reports/employees/', csv: true, extra: 'role', cols: [
    { key: 'name', label: 'Staff' }, { key: 'designation', label: 'Designation' }, { key: 'pending', label: 'Pending', num: true },
    { key: 'due_today', label: 'Due today', num: true }, { key: 'due_in_7_days', label: 'Due in 7 days', num: true },
    { key: 'overdue', label: 'Overdue', num: true }, { key: 'long_due', label: 'Long due', num: true },
    { key: 'with_issues', label: 'With issues', num: true }, { key: 'completed', label: 'Completed', num: true }] },
  { id: 'service-staff', label: 'Service × staff', url: '/api/v1/reports/service-staff/', csv: true, extra: 'grid' },
  { id: 'clients', label: 'Clients', url: '/api/v1/reports/clients/', paged: true, csv: true, extra: 'search', cols: [
    { key: 'client_name', label: 'Client' }, { key: 'pan_masked', label: 'PAN' }, { key: 'gstin', label: 'GSTIN' },
    { key: 'total_tasks', label: 'Tasks', num: true }, { key: 'pending', label: 'Pending', num: true },
    { key: 'completed', label: 'Completed', num: true }, { key: 'unbilled', label: 'Unbilled', num: true }] },
  { id: 'task-types', label: 'Task types', url: '/api/v1/reports/task-types/', cols: [
    { key: 'name', label: 'Task type' }, { key: 'service', label: 'Service' }, { key: 'total', label: 'Total', num: true },
    { key: 'not_started', label: 'Not started', num: true }, { key: 'in_process', label: 'In process', num: true },
    { key: 'on_hold', label: 'On hold', num: true }, { key: 'completed', label: 'Completed', num: true }] },
  { id: 'issues', label: 'Pending issues', url: '/api/v1/reports/issues/', paged: true, dates: true, csv: true, extra: 'issues', cols: [
    { key: 'task_number', label: 'Task' }, { key: 'client_name', label: 'Client' }, { key: 'label', label: 'Issue' },
    { key: 'detail', label: 'Detail' }, { key: 'raised_by', label: 'Raised by' }, { key: 'raised_at', label: 'Raised', render: r => dt(r.raised_at) },
    { key: 'due_date', label: 'Follow-up', render: r => <span className={r.is_overdue ? 'text-red-700 font-semibold' : ''}>{d(r.due_date)}</span> },
    { key: 'status', label: 'Status' }] },
  { id: 'performers', label: 'Staff activity', url: '/api/v1/reports/performers/', dates: true, csv: true, extra: 'metric', cols: [
    { key: 'name', label: 'Staff' }, { key: 'completed', label: 'Tasks completed', num: true }, { key: 'hours', label: 'Hours logged', num: true },
    { key: 'issues_resolved', label: 'Issues resolved', num: true }, { key: 'comments', label: 'Comments', num: true }] },
  { id: 'activity', label: 'Created / completed / deleted', url: '/api/v1/reports/activity/', dates: true, extra: 'activity' },
  { id: 'timelogs', label: 'Time logs', url: '/api/v1/reports/timelogs/', paged: true, dates: true, csv: true, cols: [
    { key: 'work_date', label: 'Date', render: r => d(r.work_date) }, { key: 'user_name', label: 'Staff' }, { key: 'task_number', label: 'Task' },
    { key: 'client_name', label: 'Client' }, { key: 'hours', label: 'Hours', num: true },
    { key: 'note', label: 'Note' }, { key: 'task_status', label: 'Task status', render: r => r.task_status === 'completed' ? <span className="text-amber-700">completed</span> : r.task_status }] },
  { id: 'assignment-changes', label: 'Assignment changes', url: '/api/v1/reports/assignment-changes/', paged: true, dates: true, cols: [
    { key: 'changed_at', label: 'When', render: r => dt(r.changed_at) }, { key: 'task_number', label: 'Task' }, { key: 'field', label: 'Role' },
    { key: 'old_user', label: 'From' }, { key: 'new_user', label: 'To' }, { key: 'changed_by', label: 'By' }, { key: 'trigger', label: 'How' }, { key: 'reason', label: 'Reason' }] },
  { id: 'deleted', label: 'Deleted tasks', url: '/api/v1/reports/deleted/', paged: true, cols: [
    { key: 'task_number', label: 'Task' }, { key: 'title', label: 'Title' }, { key: 'client_name', label: 'Client' },
    { key: 'deleted_by', label: 'Deleted by' }, { key: 'deleted_at', label: 'When', render: r => dt(r.deleted_at) }, { key: 'delete_reason', label: 'Reason' }] },
  { id: 'inactive-staff-tasks', label: 'Tasks of inactive staff', url: '/api/v1/reports/inactive-staff-tasks/', paged: true, cols: [
    { key: 'task_number', label: 'Task' }, { key: 'title', label: 'Title' }, { key: 'client_name', label: 'Client' },
    { key: 'inactive_staff_name', label: 'Inactive person' }, { key: 'due_date', label: 'Due', render: r => d(r.due_date) }, { key: 'status', label: 'Status' }] },
  { id: 'audit-log', label: 'Audit log', url: '/api/v1/reports/audit-log/', paged: true, dates: true, csv: true, extra: 'audit', cols: [
    { key: 'created_at', label: 'When', render: r => dt(r.created_at) }, { key: 'actor', label: 'Who' }, { key: 'action', label: 'Action' },
    { key: 'entity_type', label: 'What' }] },
];

const TASK_LISTS = [
  ['long_due', 'Long due'], ['unbilled', 'Unbilled completed'], ['completed_fy', 'Completed this FY'],
  ['waiting_on_client', 'Waiting on client'], ['overdue', 'Overdue'], ['due_in_7_days', 'Due in 7 days'],
];

export const ReportsPage: React.FC = () => {
  const navigate = useNavigate();
  const [active, setActive] = useState('employees');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const rep = REPORTS.find(r => r.id === active)!;

  const query = useMemo(() => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && q.set(k, v));
    if (rep.paged) { q.set('page', String(page)); q.set('page_size', '50'); }
    return q.toString();
  }, [filters, page, rep]);

  useEffect(() => {
    setLoading(true); setError('');
    const started = performance.now();
    api.get(`${rep.url}?${query}`)
      .then(res => { setData(res); console.debug('[reports]', rep.id, `${Math.round(performance.now() - started)} ms`); })
      .catch(err => { setData(null); setError(errorMessage(err, 'Could not run the report.')); })
      .finally(() => setLoading(false));
  }, [rep.url, query]);

  const choose = (id: string) => { setActive(id); setFilters({}); setPage(1); setData(null); };
  const setF = (k: string, v: string) => { setFilters(f => ({ ...f, [k]: v })); setPage(1); };
  const rows: any[] = Array.isArray(data) ? data : data?.results || data?.rows || [];
  const csvHref = () => { const q = new URLSearchParams(query); q.delete('page'); q.delete('page_size'); q.set('export', 'csv'); return `${rep.url}?${q}`; };

  return (
    <div className="space-y-5">
      <PageHeader title="Reports" subtitle="Every number comes from the same server rules as the dashboard. Use CSV to open a report in Excel." />
      <div className="flex flex-wrap gap-1.5">
        {TASK_LISTS.map(([tile, label]) => (
          <button key={tile} type="button" onClick={() => navigate(`/tasks?tile=${tile}`)} className={btn.small}>{label} <ExternalLink className="w-3 h-3" /></button>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4 items-start">
        <nav aria-label="Reports" className="bg-white border border-slate-200 rounded-xl p-1.5 flex lg:flex-col gap-1 overflow-x-auto">
          {REPORTS.map(r => (
            <button key={r.id} type="button" onClick={() => choose(r.id)} aria-current={active === r.id}
              className={`text-left px-3 py-2 rounded-lg text-sm whitespace-nowrap ${active === r.id ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'text-slate-600 hover:bg-slate-50'}`}>{r.label}</button>
          ))}
        </nav>
        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden min-w-0">
          <div className="flex flex-wrap items-end gap-2 p-3 border-b border-slate-100">
            {rep.dates && <>
              <label className="text-xs text-slate-500">From<input type="date" value={filters.start_date || ''} onChange={e => setF('start_date', e.target.value)} className={inputCls} /></label>
              <label className="text-xs text-slate-500">To<input type="date" value={filters.end_date || ''} onChange={e => setF('end_date', e.target.value)} className={inputCls} /></label>
            </>}
            {(rep.extra === 'role' || rep.extra === 'grid') && (
              <label className="text-xs text-slate-500">Task role<select value={filters.role || 'assigned'} onChange={e => setF('role', e.target.value)} className={inputCls}>
                <option value="assigned">Assigned</option><option value="leader">Leader</option><option value="manager">Manager</option>{rep.extra === 'role' && <option value="member">Member</option>}
              </select></label>
            )}
            {rep.extra === 'grid' && (
              <label className="text-xs text-slate-500">Count<select value={filters.tile || 'pending'} onChange={e => setF('tile', e.target.value)} className={inputCls}>
                <option value="pending">Pending</option><option value="overdue">Overdue</option><option value="due_in_7_days">Due in 7 days</option><option value="completed_fy">Completed this FY</option>
              </select></label>
            )}
            {rep.extra === 'metric' && (
              <label className="text-xs text-slate-500">Rank by<select value={filters.metric || 'completed'} onChange={e => setF('metric', e.target.value)} className={inputCls}>
                <option value="completed">Tasks completed</option><option value="hours">Hours logged</option><option value="issues_resolved">Issues resolved</option><option value="comments">Comments</option>
              </select></label>
            )}
            {rep.extra === 'issues' && (
              <label className="text-xs text-slate-500">Status<select value={filters.status || 'open'} onChange={e => setF('status', e.target.value)} className={inputCls}>
                <option value="open">Open</option><option value="resolved">Resolved</option><option value="all">All</option>
              </select></label>
            )}
            {rep.extra === 'search' && <label className="text-xs text-slate-500">Client<input value={filters.search || ''} onChange={e => setF('search', e.target.value)} placeholder="Name" className={inputCls} /></label>}
            {rep.extra === 'audit' && <>
              <label className="text-xs text-slate-500">Who<select value={filters.actor || ''} onChange={e => { console.debug('[reports] audit who filter', e.target.value || 'all'); setF('actor', e.target.value); }} className={inputCls}>
                <option value="">Everyone</option>{(data?.actors || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select></label>
              <label className="text-xs text-slate-500">Action<select value={filters.action || ''} onChange={e => setF('action', e.target.value)} className={inputCls}>
                <option value="">All</option>{(data?.actions || []).sort().map((a: string) => <option key={a} value={a}>{a}</option>)}
              </select></label>
              <label className="text-xs text-slate-500">Entity id<input value={filters.entity_id || ''} onChange={e => setF('entity_id', e.target.value.trim())} placeholder="Task / client id" className={inputCls} /></label>
            </>}
            {rep.csv && <a href={csvHref()} className={`${btn.small} ml-auto`}><Download className="w-3 h-3" /> CSV</a>}
          </div>
          {error && <div className="p-3"><Alert>{error}</Alert></div>}
          {loading && !data ? <Spinner /> : data && <ReportBody rep={rep} data={data} rows={rows} onLabel={(l: string) => setF('label', l)} />}
          {rep.paged && data?.total_pages && <Pager page={data.page || page} totalPages={data.total_pages} count={data.count} onPage={setPage} />}
        </section>
      </div>
    </div>
  );
};

const Table: React.FC<{ cols: Col[]; rows: any[] }> = ({ cols, rows }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead className="bg-slate-50 text-[11px] uppercase text-slate-500"><tr>{cols.map(c => <th key={c.key} className={`px-3 py-2 ${c.num ? 'text-right' : 'text-left'}`}>{c.label}</th>)}</tr></thead>
      <tbody className="divide-y divide-slate-100">
        {rows.length === 0 && <tr><td colSpan={cols.length} className="px-3 py-6 text-center text-slate-500 text-sm">No rows for these filters.</td></tr>}
        {rows.map((r, i) => <tr key={r.id || r.user_id || r.client_id || r.task_type_id || i} className="hover:bg-slate-50/60">
          {cols.map(c => <td key={c.key} className={`px-3 py-2 ${c.num ? 'text-right tabular-nums' : ''}`}>{c.render ? c.render(r) : c.num ? fmtNumber(r[c.key]) : String(r[c.key] ?? '')}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>
);

const ReportBody: React.FC<{ rep: ReportDef; data: any; rows: any[]; onLabel: (l: string) => void }> = ({ rep, data, rows, onLabel }) => {
  if (rep.extra === 'grid') {
    const users: any[] = data.users || [];
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[11px] uppercase text-slate-500"><tr><th className="px-3 py-2 text-left">Service</th>{users.map(u => <th key={u.id} className="px-3 py-2 text-right whitespace-nowrap">{u.name}</th>)}<th className="px-3 py-2 text-right">Total</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {(data.services || []).length === 0 && <tr><td className="px-3 py-6 text-center text-slate-500" colSpan={users.length + 2}>No tasks.</td></tr>}
            {(data.services || []).map((s: any) => {
              const row = data.grid[s.id] || {};
              const total = Object.values(row).reduce((a: number, b: any) => a + Number(b), 0);
              return <tr key={s.id}><td className="px-3 py-2">{s.name}</td>{users.map(u => <td key={u.id} className={`px-3 py-2 text-right tabular-nums ${row[u.id] ? 'font-semibold' : 'text-slate-300'}`}>{fmtNumber(row[u.id] || 0)}</td>)}<td className="px-3 py-2 text-right font-bold">{fmtNumber(total)}</td></tr>;
            })}
          </tbody>
        </table>
      </div>
    );
  }
  if (rep.extra === 'activity') {
    return (
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          {[['Created', data.created_count], ['Completed', data.completed_count], ['Deleted', data.deleted_count]].map(([l, v]) => (
            <div key={l as string} className="border border-slate-200 rounded-lg p-3"><p className="text-2xl font-bold text-slate-900">{fmtNumber(v)}</p><p className="text-xs text-slate-500">{l}</p></div>
          ))}
        </div>
        {[['recent_created', 'Latest created'], ['recent_completed', 'Latest completed'], ['recent_deleted', 'Latest deleted']].map(([k, l]) => (
          <div key={k}><h4 className="text-xs font-semibold text-slate-700 mb-1">{l}</h4>
            <ul className="text-xs text-slate-600 space-y-0.5">{(data[k] || []).map((t: any, i: number) => <li key={i}><span className="font-mono">{t.number}</span> · {t.title} · {dt(t.date)}{t.reason ? ` — ${t.reason}` : ''}</li>)}
              {!(data[k] || []).length && <li className="text-slate-400">None</li>}</ul></div>
        ))}
      </div>
    );
  }
  return (
    <>
      {rep.extra === 'metric' && (data.top?.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-3 p-3 border-b border-slate-100 text-xs">
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-2.5"><p className="font-semibold text-emerald-900 mb-1">Top</p>{data.top.map((r: any) => <p key={r.user_id}>{r.name}: <strong>{r[data.metric]}</strong></p>)}</div>
          {data.bottom?.length > 0 && <div className="rounded-lg bg-amber-50 border border-amber-200 p-2.5"><p className="font-semibold text-amber-900 mb-1">Needs attention</p>{data.bottom.map((r: any) => <p key={r.user_id}>{r.name}: <strong>{r[data.metric]}</strong></p>)}</div>}
        </div>
      )}
      {rep.extra === 'issues' && (
        <div className="p-3 border-b border-slate-100 space-y-2 text-xs">
          <p className="text-slate-600">In the dates: <strong>{data.raised_count}</strong> raised · <strong>{data.resolved_count}</strong> resolved · <strong className="text-red-700">{data.overdue_followups}</strong> open with an overdue follow-up date.</p>
          <div className="flex flex-wrap gap-1.5">{(data.by_label || []).map((l: any) => (
            <button type="button" key={l.label__name} onClick={() => onLabel(l.label__name)} className={btn.small}>{l.label__name}{l.label__is_client_side ? ' (client)' : ''}: <strong>{l.open}</strong></button>
          ))}</div>
        </div>
      )}
      {rep.id === 'timelogs' && data.total_hours !== undefined && <p className="px-3 pt-3 text-xs text-slate-600">Total for the filters: <strong>{fmtNumber(data.total_hours)} h</strong></p>}
      <Table cols={rep.cols || []} rows={rows} />
    </>
  );
};
