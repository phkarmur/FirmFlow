import React, { useEffect, useMemo, useState } from 'react';
import { api, errorMessage as apiErrorMessage, localToday } from '../api/client';
import { fmtDate as fmtDateShared, fmtDateTime as fmtDateTimeShared } from '../utils/format';
import { MentionInput, FormattedCommentText } from '../components/MentionInput';
import {
  X, Check, AlertTriangle, AlertCircle, Copy, CheckCheck, Sparkles, Send, Pencil, UserCog,
  Trash2, RotateCcw, Printer, Paperclip, Download, Upload, Loader2, History, Plus, UserMinus,
} from 'lucide-react';

interface TaskDetailPageProps {
  taskId: string;
  onClose: () => void;
  onUpdated: () => void;
}

type Tab = 'milestones' | 'todos' | 'issues' | 'comments' | 'files' | 'timelogs' | 'history';

const ON_HOLD_PRESETS = [
  'Awaiting Client Bank Statement',
  'Awaiting OTP / DSC from Client',
  'Portal Downtime (ITD / GSTN / MCA)',
  'Awaiting Signed Balance Sheet / Audit Report',
  'Awaiting Tax Challan Payment Confirmation',
  'Under Partner / Peer Review',
];
const RESOLVE_PRESETS = [
  'Received required documents from client on email',
  'Reconciled and matched with portal records',
  'Challan payment verified on portal',
  'Client shared OTP / DSC token',
];
const STATUS_LABEL: Record<string, string> = {
  not_started: 'Not started', in_process: 'In process', on_hold: 'On hold', completed: 'Completed', deleted: 'Deleted',
};
const STATUS_STYLE: Record<string, string> = {
  not_started: 'bg-slate-100 text-slate-700 border-slate-200',
  in_process: 'bg-sky-100 text-sky-800 border-sky-200',
  on_hold: 'bg-amber-100 text-amber-800 border-amber-200',
  completed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  deleted: 'bg-rose-100 text-rose-800 border-rose-200',
};
// Same table as the server (TaskService.ALLOWED_TRANSITIONS). Reopen/delete have their own buttons.
const NEXT_STATUS: Record<string, string[]> = {
  not_started: ['in_process', 'on_hold', 'completed'],
  in_process: ['on_hold', 'completed'],
  on_hold: ['in_process'],
  completed: [],
  deleted: [],
};
const ROLE_LABEL: Record<string, string> = { assigned: 'Assigned to', leader: 'Leader', manager: 'Manager' };

// Firm date format + time zone (Settings): see utils/format.ts
const fmtDateTime = (iso?: string) => fmtDateTimeShared(iso);
const fmtDate = (iso?: string) => fmtDateShared(iso);
const fmtSize = (b: number) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`);
const fmtMinutes = (m: number) => `${Math.floor(m / 60)}h ${m % 60}m`;
const escapeHtml = (s: any) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));

export const TaskDetailPage: React.FC<TaskDetailPageProps> = ({ taskId, onClose, onUpdated }) => {
  const [task, setTask] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [activeTab, setActiveTab] = useState<Tab>('milestones');
  const [busy, setBusy] = useState(false);

  const [labels, setLabels] = useState<any[]>([]);
  const [staff, setStaff] = useState<any[]>([]);

  const [commentBody, setCommentBody] = useState('');
  const [commentMentions, setCommentMentions] = useState<string[]>([]);
  const [timeMinutes, setTimeMinutes] = useState('60');
  const [timeWorkDate, setTimeWorkDate] = useState(localToday());
  const [timeNote, setTimeNote] = useState('');
  const [selectedLabel, setSelectedLabel] = useState('');
  const [issueDetail, setIssueDetail] = useState('');
  const [issueDue, setIssueDue] = useState('');

  // Dialogs
  const [onHoldOpen, setOnHoldOpen] = useState(false);
  const [onHoldInput, setOnHoldInput] = useState('');
  const [resolvingIssueId, setResolvingIssueId] = useState<string | null>(null);
  const [resolveNote, setResolveNote] = useState('');
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState<any>({});
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reassignForm, setReassignForm] = useState({ field: 'assigned', user: '', reason: '' });
  const [reasonDialog, setReasonDialog] = useState<null | 'delete' | 'reopen'>(null);
  const [reasonInput, setReasonInput] = useState('');
  const [memberToAdd, setMemberToAdd] = useState('');
  const [dupFile, setDupFile] = useState<{ file: File; message: string } | null>(null);
  const [uploading, setUploading] = useState(false);

  const [errorMessage, setErrorMessage] = useState('');
  const [toast, setToast] = useState('');
  const [copied, setCopied] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(''), 3000);
  };

  const loadTask = () => {
    api.get(`/api/v1/tasks/${taskId}/`)
      .then(data => { setTask(data); setLoadError(''); })
      .catch(err => {
        console.error('[task-detail] load failed', err);
        setLoadError(err?.status === 404
          ? 'You cannot open this task. It was re-assigned to someone else, deleted, or you have no role on it.'
          : apiErrorMessage(err, 'Could not open this task.'));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    loadTask();
    api.get('/api/v1/services/issue-labels/?page_size=200')
      .then(res => setLabels(res.results || []))
      .catch(err => { console.error('[task-detail] labels failed', err); setErrorMessage('Could not load the issue labels. Raising an issue may not work until you reload the page.'); });
    api.get('/api/v1/accounts/users/mentionable/')
      .then(res => setStaff(Array.isArray(res) ? res : []))
      .catch(err => { console.error('[task-detail] staff failed', err); setErrorMessage('Could not load the staff list. Re-assign and member lists may be empty until you reload the page.'); });
  }, [taskId]);

  // Esc closes the top-most dialog, then the task
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (onHoldOpen || resolvingIssueId || editOpen || reassignOpen || reasonDialog || dupFile) {
        setOnHoldOpen(false); setResolvingIssueId(null); setEditOpen(false); setReassignOpen(false);
        setReasonDialog(null); setDupFile(null);
      } else {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onHoldOpen, resolvingIssueId, editOpen, reassignOpen, reasonDialog, dupFile, onClose]);

  /** Run one API action: shows errors, reloads the task and the list behind it. */
  const run = async (label: string, fn: () => Promise<any>, success?: string) => {
    setErrorMessage('');
    setBusy(true);
    console.debug('[task-detail] action', label);
    try {
      const res = await fn();
      if (res && res.id && res.task_number) setTask(res); else loadTask();
      onUpdated();
      if (success) showToast(success);
      return true;
    } catch (err: any) {
      console.error(`[task-detail] ${label} failed`, err);
      setErrorMessage(apiErrorMessage(err, 'The change was not saved.'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = (status: string) => {
    if (status === 'on_hold') {
      setOnHoldInput('');
      setOnHoldOpen(true);
      return;
    }
    run('status', () => api.post(`/api/v1/tasks/${taskId}/change_status/`, { status, version: task.version }),
      `Status: ${STATUS_LABEL[status]}`);
  };

  const submitOnHold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!onHoldInput.trim()) return;
    if (await run('on_hold', () => api.post(`/api/v1/tasks/${taskId}/change_status/`,
      { status: 'on_hold', on_hold_reason: onHoldInput.trim(), version: task.version }), 'Task put on hold')) {
      setOnHoldOpen(false);
    }
  };

  const submitReason = async (e: React.FormEvent) => {
    e.preventDefault();
    const reason = reasonInput.trim();
    if (reason.length < 3) return;
    if (reasonDialog === 'delete') {
      const ok = await run('delete', () => api.delete(`/api/v1/tasks/${taskId}/`, { reason, version: task.version }));
      if (ok) {
        setReasonDialog(null);
        onClose();
      }
    } else if (reasonDialog === 'reopen') {
      if (await run('reopen', () => api.post(`/api/v1/tasks/${taskId}/change_status/`,
        { status: 'in_process', reason, version: task.version }), 'Task reopened')) setReasonDialog(null);
    }
  };

  const openEdit = () => {
    setEditForm({
      title: task.title, description: task.description || '', priority: task.priority,
      due_date: task.due_date, start_date: task.start_date || '',
    });
    setEditOpen(true);
  };

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = { version: task.version };
    for (const k of ['title', 'description', 'priority', 'due_date', 'start_date']) {
      const v = editForm[k] === '' && k === 'start_date' ? null : editForm[k];
      if ((task[k] ?? '') !== (v ?? '')) payload[k] = v;
    }
    if (Object.keys(payload).length === 1) { setEditOpen(false); return; }
    if (await run('edit', () => api.patch(`/api/v1/tasks/${taskId}/`, payload), 'Task updated')) setEditOpen(false);
  };

  const submitReassign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (await run('reassign', () => api.post(`/api/v1/tasks/${taskId}/reassign/`, {
      field: reassignForm.field, new_user_id: reassignForm.user || null, reason: reassignForm.reason, version: task.version,
    }), 'Role changed')) setReassignOpen(false);
  };

  const addMember = () => {
    if (!memberToAdd) return;
    run('add_member', () => api.post(`/api/v1/tasks/${taskId}/add_member/`, { user_id: memberToAdd }), 'Member added')
      .then(ok => ok && setMemberToAdd(''));
  };
  const removeMember = (userId: string) =>
    run('remove_member', () => api.post(`/api/v1/tasks/${taskId}/remove_member/`, { user_id: userId }), 'Member removed');

  const tickMilestone = (milestoneId: string) =>
    run('milestone', () => api.post(`/api/v1/tasks/${taskId}/tick_milestone/`, { milestone_id: milestoneId, version: task.version }), 'Milestone done');
  const toggleTodo = (todoId: string) =>
    run('todo', () => api.post(`/api/v1/tasks/${taskId}/toggle_todo/`, { todo_id: todoId }));
  const pickup = () => run('pickup', () => api.post(`/api/v1/tasks/${taskId}/pickup/`), 'Task assigned to you');

  const postComment = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!commentBody.trim()) return;
    if (await run('comment', () => api.post(`/api/v1/tasks/${taskId}/add_comment/`,
      { body: commentBody, mentions: commentMentions }))) {
      setCommentBody('');
      setCommentMentions([]);
    }
  };

  const logTime = async (e: React.FormEvent) => {
    e.preventDefault();
    if (await run('time', () => api.post(`/api/v1/tasks/${taskId}/log_time/`,
      { work_date: timeWorkDate, minutes: Number(timeMinutes), note: timeNote }), 'Time logged')) setTimeNote('');
  };

  const raiseIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedLabel) return;
    if (await run('issue', () => api.post(`/api/v1/tasks/${taskId}/raise_issue/`,
      { label_id: selectedLabel, detail: issueDetail, due_date: issueDue || null }), 'Issue raised')) {
      setSelectedLabel(''); setIssueDetail(''); setIssueDue('');
    }
  };

  const submitResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (await run('resolve', () => api.post(`/api/v1/tasks/${taskId}/resolve_issue/`,
      { issue_id: resolvingIssueId, note: resolveNote }), 'Issue resolved')) {
      setResolvingIssueId(null); setResolveNote('');
    }
  };

  const uploadFile = async (file: File | undefined, confirmDuplicate = false) => {
    if (!file) return;
    setErrorMessage('');
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    if (confirmDuplicate) fd.append('confirm_duplicate', 'true');
    try {
      await api.post(`/api/v1/tasks/${taskId}/upload_attachment/`, fd);
      console.info('[task-detail] uploaded', file.name, file.size);
      setDupFile(null);
      loadTask();
      onUpdated();
      showToast(`Uploaded ${file.name}`);
    } catch (err: any) {
      if (err?.status === 409 && err?.duplicate) {
        setDupFile({ file, message: apiErrorMessage(err) });
      } else {
        setErrorMessage(apiErrorMessage(err, 'Upload failed.'));
      }
    } finally {
      setUploading(false);
    }
  };
  const deleteFile = (attId: string, name: string) => {
    if (!window.confirm(`Remove "${name}" from this task?`)) return;
    run('delete_attachment', () => api.post(`/api/v1/tasks/${taskId}/delete_attachment/`, { attachment_id: attId }), 'File removed');
  };

  const copyTaskNumber = () => {
    if (!task?.task_number) return;
    navigator.clipboard.writeText(task.task_number).catch(() => undefined);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  /** Print / save as PDF: opens a clean printable page in a new window (spec §6.1-3). */
  const printTask = () => {
    const t = task;
    const rows = (items: any[], cols: (i: any) => any[]) =>
      items.map(i => `<tr>${cols(i).map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('');
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(t.task_number)}</title>
      <style>body{font:12px system-ui,sans-serif;color:#111;margin:24px}h1{font-size:18px;margin:0 0 4px}
      h2{font-size:13px;margin:18px 0 6px;border-bottom:1px solid #ccc;padding-bottom:3px}
      table{width:100%;border-collapse:collapse}td,th{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
      .meta td{border:none;padding:2px 12px 2px 0}.muted{color:#666}</style></head><body>
      <h1>${escapeHtml(t.task_number)} · ${escapeHtml(t.title)}</h1>
      <div class="muted">${escapeHtml(t.client_name)} · ${escapeHtml(t.task_type_name)} · ${escapeHtml(t.period_label || t.fy_label)} ${escapeHtml(t.ay_label)}</div>
      <table class="meta" style="margin-top:8px"><tr><td>Status: <b>${escapeHtml(STATUS_LABEL[t.status])}</b></td><td>Due: <b>${escapeHtml(fmtDate(t.due_date))}</b></td>
      <td>Priority: ${escapeHtml(t.priority)}</td></tr><tr><td>Assigned: ${escapeHtml(t.assigned_user_name)}</td>
      <td>Leader: ${escapeHtml(t.leader_user_name || '—')}</td><td>Manager: ${escapeHtml(t.manager_user_name || '—')}</td></tr></table>
      ${t.description ? `<h2>Notes</h2><div>${escapeHtml(t.description)}</div>` : ''}
      <h2>Milestones</h2><table>${rows(t.milestones || [], m => [m.milestone_name, m.status, m.done_by_name || '', fmtDateTime(m.done_at)])}</table>
      <h2>Checklist</h2><table>${rows(t.todos || [], d => [d.is_done ? '✔' : '☐', d.text, d.is_mandatory ? 'Mandatory' : ''])}</table>
      <h2>Issues</h2><table>${rows(t.issues || [], i => [i.label_name, i.status, i.detail, i.resolution_note])}</table>
      <h2>Comments</h2><table>${rows(t.comments || [], c => [fmtDateTime(c.created_at), c.user_name, c.body])}</table>
      <h2>Time logs</h2><table>${rows(t.time_logs || [], l => [l.work_date, l.user_name, fmtMinutes(l.minutes), l.note])}</table>
      <p class="muted" style="margin-top:18px">Printed ${escapeHtml(new Date().toLocaleString('en-IN'))}</p>
      <script>window.onload=function(){window.print()}</script></body></html>`;
    const w = window.open('', '_blank');
    if (!w) { setErrorMessage('Allow pop-ups for this site to print.'); return; }
    w.document.open(); w.document.write(html); w.document.close();
    console.info('[task-detail] print opened');
  };

  const perms = task?.my_permissions || {};
  const openMandatoryTodos = useMemo(() => (task?.todos || []).filter((t: any) => t.is_mandatory && !t.is_done), [task]);
  const openBlockers = useMemo(() => (task?.issues || []).filter((i: any) => i.status === 'open' && i.blocks_completion), [task]);
  const pendingMilestones = useMemo(() => (task?.milestones || []).filter((m: any) => m.status === 'pending'), [task]);
  const history = useMemo(() => {
    if (!task) return [];
    const a = (task.assignment_logs || []).map((l: any) => ({
      at: l.changed_at, who: l.changed_by_name,
      text: l.field === 'member_added' ? `added member ${l.new_user_name}`
        : l.field === 'member_removed' ? `removed member ${l.old_user_name}`
        : `${ROLE_LABEL[l.field] || l.field}: ${l.old_user_name} → ${l.new_user_name}`,
      reason: l.reason, kind: l.trigger,
    }));
    const s = (task.status_logs || []).map((l: any) => ({
      at: l.changed_at, who: l.changed_by_name,
      text: `status: ${STATUS_LABEL[l.old_status] || l.old_status} → ${STATUS_LABEL[l.new_status] || l.new_status}`,
      reason: l.reason, kind: 'status',
    }));
    return [...a, ...s].sort((x, y) => (x.at < y.at ? 1 : -1));
  }, [task]);

  if (loading || (!task && !loadError)) {
    return (
      <div className="fixed inset-0 !mt-0 z-50 bg-black/40 flex items-center justify-center p-4">
        <div className="bg-white p-6 rounded-2xl shadow-xl flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-emerald-600" />
          <span className="text-sm font-medium text-slate-700">Loading task…</span>
        </div>
      </div>
    );
  }
  if (!task) {
    return (
      <div className="fixed inset-0 !mt-0 z-50 bg-black/40 flex items-center justify-center p-4" role="dialog" aria-modal="true">
        <div className="bg-white p-6 rounded-2xl shadow-xl max-w-sm space-y-3">
          <p className="text-sm text-slate-800">{loadError}</p>
          <button onClick={onClose} className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold">Close</button>
        </div>
      </div>
    );
  }

  const isOpen = ['not_started', 'in_process', 'on_hold'].includes(task.status);
  const today = localToday();
  const isOverdue = ['not_started', 'in_process'].includes(task.status) && task.due_date < today;
  const isDueToday = isOpen && task.due_date === today;
  const statusOptions = perms.can_change_status ? NEXT_STATUS[task.status] || [] : [];
  const memberIds = new Set((task.members || []).map((m: any) => m.user));
  const roleIds = new Set([task.assigned_user, task.leader_user, task.manager_user].filter(Boolean));
  const addableStaff = staff.filter(u => !memberIds.has(u.id) && !roleIds.has(u.id));
  const openIssues = (task.issues || []).filter((i: any) => i.status === 'open');
  const totalMinutes = (task.time_logs || []).reduce((s: number, l: any) => s + l.minutes, 0);

  const TABS: { id: Tab; label: string; count?: number; alert?: boolean }[] = [
    { id: 'milestones', label: 'Milestones', count: task.milestones?.length },
    { id: 'todos', label: 'Checklist', count: task.todos?.length },
    { id: 'issues', label: 'Issues', count: openIssues.length, alert: openIssues.length > 0 },
    { id: 'comments', label: 'Comments', count: task.comments?.length },
    { id: 'files', label: 'Files', count: task.attachments?.length },
    { id: 'timelogs', label: 'Time', count: task.time_logs?.length },
    { id: 'history', label: 'History', count: history.length },
  ];

  const btn = 'inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition disabled:opacity-50';
  const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 bg-white text-sm focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 outline-none';

  return (
    <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-stretch sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="task-title">
      <div className="bg-white sm:rounded-2xl shadow-2xl w-full max-w-5xl h-full sm:h-auto sm:max-h-[94vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-4 sm:px-6 py-4 border-b border-slate-200 bg-slate-50/70">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-mono font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded inline-flex items-center gap-1">
                  {task.task_number}
                  <button type="button" onClick={copyTaskNumber} aria-label="Copy task number" className="hover:text-emerald-950">
                    {copied ? <CheckCheck className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  </button>
                </span>
                <span className={`font-semibold px-2 py-0.5 rounded border ${STATUS_STYLE[task.status]}`}>{STATUS_LABEL[task.status]}</span>
                <span className="text-slate-600 bg-white border px-2 py-0.5 rounded">{task.task_type_name}</span>
                <span className="text-slate-500">{task.period_label || task.fy_label || 'No period'}{task.ay_label ? ` · ${task.ay_label}` : ''}</span>
                {task.priority === 'high' && <span className="font-bold uppercase text-[10px] px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">High priority</span>}
              </div>
              <h2 id="task-title" className="text-lg sm:text-xl font-bold text-slate-900 mt-1.5 leading-snug break-words">{task.title}</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {task.client_name} <span className="font-mono text-slate-400">{task.client_pan ? `· PAN ${task.client_pan}` : ''}{task.client_gstin ? ` · GSTIN ${task.client_gstin}` : ''}</span>
              </p>
            </div>
            <button onClick={onClose} aria-label="Close (Esc)" className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 shrink-0">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Actions: only what this user may do (server checks again) */}
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {statusOptions.includes('completed') && (
              <button type="button" disabled={busy} onClick={() => changeStatus('completed')}
                title={openMandatoryTodos.length || openBlockers.length || pendingMilestones.length ? 'Some items are still open (see the yellow bar).' : 'Everything is done.'}
                className={`${btn} bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700`}>
                <Check className="w-3.5 h-3.5" /> Mark completed
              </button>
            )}
            {statusOptions.filter(s => s !== 'completed').length > 0 && (
              <select aria-label="Change status" value="" disabled={busy} onChange={e => e.target.value && changeStatus(e.target.value)}
                className="text-xs font-semibold px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white">
                <option value="">Move to…</option>
                {statusOptions.filter(s => s !== 'completed').map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </select>
            )}
            {perms.can_pickup && <button type="button" disabled={busy} onClick={pickup} className={`${btn} bg-purple-600 border-purple-600 text-white hover:bg-purple-700`}><Sparkles className="w-3.5 h-3.5" /> Assign to me</button>}
            {perms.can_edit && task.status !== 'deleted' && <button type="button" onClick={openEdit} className={`${btn} border-slate-300 bg-white hover:bg-slate-50`}><Pencil className="w-3.5 h-3.5" /> Edit</button>}
            {perms.can_reassign && task.status !== 'deleted' && <button type="button" onClick={() => { setReassignForm({ field: 'assigned', user: '', reason: '' }); setReassignOpen(true); }} className={`${btn} border-slate-300 bg-white hover:bg-slate-50`}><UserCog className="w-3.5 h-3.5" /> Re-assign</button>}
            {perms.can_reopen && task.status === 'completed' && <button type="button" onClick={() => { setReasonInput(''); setReasonDialog('reopen'); }} className={`${btn} border-slate-300 bg-white hover:bg-slate-50`}><RotateCcw className="w-3.5 h-3.5" /> Reopen</button>}
            <button type="button" onClick={printTask} className={`${btn} border-slate-300 bg-white hover:bg-slate-50`}><Printer className="w-3.5 h-3.5" /> Print / PDF</button>
            {perms.can_delete && task.status !== 'deleted' && <button type="button" onClick={() => { setReasonInput(''); setReasonDialog('delete'); }} className={`${btn} border-rose-200 text-rose-700 bg-white hover:bg-rose-50 sm:ml-auto`}><Trash2 className="w-3.5 h-3.5" /> Delete</button>}
          </div>
        </div>

        {toast && <div role="status" className="px-6 py-2 bg-emerald-600 text-white text-xs font-semibold">✓ {toast}</div>}
        {errorMessage && (
          <div role="alert" className="px-6 py-2.5 bg-red-50 border-b border-red-200 text-red-800 text-xs flex items-start justify-between gap-3">
            <span className="flex gap-2"><AlertCircle className="w-4 h-4 shrink-0" />{errorMessage}</span>
            <button onClick={() => setErrorMessage('')} aria-label="Dismiss" className="font-bold">×</button>
          </div>
        )}
        {isOpen && (openMandatoryTodos.length > 0 || openBlockers.length > 0 || pendingMilestones.length > 0) && (
          <div className="px-6 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-900 flex gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
            <span><strong>Before completing:</strong>{' '}
              {[pendingMilestones.length && `${pendingMilestones.length} milestone(s)`,
                openMandatoryTodos.length && `${openMandatoryTodos.length} mandatory to-do(s)`,
                openBlockers.length && `${openBlockers.length} blocking issue(s)`].filter(Boolean).join(', ')} still open.</span>
          </div>
        )}
        {task.status === 'on_hold' && task.on_hold_reason && (
          <div className="px-6 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-900"><strong>On hold:</strong> {task.on_hold_reason}</div>
        )}

        <div className="flex-1 overflow-y-auto">
          {/* People and dates */}
          <div className="px-4 sm:px-6 py-3 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-xs border-b bg-white">
            <div><span className="block text-slate-400">Due date</span>
              <span className={`font-semibold ${isOverdue ? 'text-red-700' : isDueToday ? 'text-amber-700' : 'text-slate-800'}`}>
                {fmtDate(task.due_date)}{isOverdue ? ' · overdue' : isDueToday ? ' · today' : ''}
              </span>
              <span className="text-slate-400"> ({task.due_date_source === 'manual' ? 'set by hand' : 'rule'})</span></div>
            <div><span className="block text-slate-400">Assigned to</span><span className="font-semibold text-slate-800">{task.assigned_user_name || 'Unassigned pool'}</span></div>
            <div><span className="block text-slate-400">Leader</span><span className="font-semibold text-slate-800">{task.leader_user_name || '—'}</span></div>
            <div><span className="block text-slate-400">Manager</span><span className="font-semibold text-slate-800">{task.manager_user_name || '—'}</span></div>
            <div className="col-span-2 md:col-span-4">
              <span className="block text-slate-400 mb-1">Members</span>
              <div className="flex flex-wrap items-center gap-1.5">
                {(task.members || []).length === 0 && <span className="text-slate-500">None</span>}
                {(task.members || []).map((m: any) => (
                  <span key={m.user} className="inline-flex items-center gap-1 bg-slate-100 border border-slate-200 rounded-full pl-2.5 pr-1 py-0.5 font-medium text-slate-700">
                    {m.name}
                    {perms.can_reassign && (
                      <button type="button" onClick={() => removeMember(m.user)} aria-label={`Remove ${m.name}`} className="p-0.5 text-slate-400 hover:text-rose-700"><UserMinus className="w-3 h-3" /></button>
                    )}
                  </span>
                ))}
                {perms.can_reassign && task.status !== 'deleted' && (
                  <span className="inline-flex items-center gap-1">
                    <select aria-label="Add member" value={memberToAdd} onChange={e => setMemberToAdd(e.target.value)} className="text-xs border border-slate-300 rounded-md px-1.5 py-0.5 bg-white">
                      <option value="">Add member…</option>
                      {addableStaff.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                    {memberToAdd && <button type="button" onClick={addMember} disabled={busy} className="p-1 rounded bg-emerald-600 text-white" aria-label="Add"><Plus className="w-3 h-3" /></button>}
                  </span>
                )}
              </div>
            </div>
            {task.description && <div className="col-span-2 md:col-span-4"><span className="block text-slate-400">Notes</span><p className="text-slate-700 whitespace-pre-wrap">{task.description}</p></div>}
          </div>

          {/* Tabs */}
          <div role="tablist" className="px-4 sm:px-6 border-b flex gap-1 overflow-x-auto bg-white sticky top-0 z-10">
            {TABS.map(t => (
              <button key={t.id} role="tab" aria-selected={activeTab === t.id} onClick={() => setActiveTab(t.id)}
                className={`px-3 py-2.5 text-xs font-semibold whitespace-nowrap border-b-2 -mb-px transition ${
                  activeTab === t.id ? 'border-emerald-600 text-emerald-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                {t.label}{typeof t.count === 'number' && <span className={`ml-1.5 text-[10px] px-1.5 rounded-full ${t.alert ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}>{t.count}</span>}
              </button>
            ))}
          </div>

          <div className="p-4 sm:p-6 text-sm">
            {activeTab === 'milestones' && (
              <ol className="space-y-2">
                {(task.milestones || []).length === 0 && <p className="text-slate-500 text-xs">This task type has no milestones.</p>}
                {(task.milestones || []).map((m: any, idx: number) => {
                  const done = m.status === 'done';
                  return (
                    <li key={m.id} className={`p-3 rounded-xl border flex items-center justify-between gap-3 ${done ? 'bg-emerald-50/50 border-emerald-200' : 'bg-white border-slate-200'}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${done ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-700'}`}>
                          {done ? <Check className="w-4 h-4" /> : idx + 1}
                        </span>
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900 text-xs">{m.milestone_name}
                            {m.is_terminal && <span className="ml-2 text-[10px] bg-emerald-100 text-emerald-800 px-1.5 rounded font-bold">Completes the task</span>}</p>
                          <p className="text-[11px] text-slate-500">{done ? `${m.done_by_name} · ${fmtDateTime(m.done_at)}` : 'Pending'}</p>
                        </div>
                      </div>
                      {!done && perms.can_work && isOpen && (
                        <button type="button" disabled={busy} onClick={() => tickMilestone(m.milestone)} className={`${btn} bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700 shrink-0`}>
                          <Check className="w-3.5 h-3.5" /> Done
                        </button>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}

            {activeTab === 'todos' && (
              <ul className="space-y-1.5">
                {(task.todos || []).length === 0 && <p className="text-slate-500 text-xs">No checklist items.</p>}
                {(task.todos || []).map((t: any) => (
                  <li key={t.id}>
                    <label className={`flex items-start gap-3 p-2.5 rounded-lg border ${t.is_done ? 'bg-slate-50 border-slate-200' : 'bg-white border-slate-200'} ${perms.can_work && isOpen ? 'cursor-pointer hover:bg-slate-50' : ''}`}>
                      <input type="checkbox" checked={t.is_done} disabled={!perms.can_work || !isOpen || busy} onChange={() => toggleTodo(t.id)} className="mt-0.5 h-4 w-4 accent-emerald-600" />
                      <span className="flex-1">
                        <span className={`text-sm ${t.is_done ? 'line-through text-slate-400' : 'text-slate-800'}`}>{t.text}</span>
                        {t.is_mandatory && <span className="ml-2 text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-1.5 rounded">Mandatory</span>}
                        {t.is_done && t.done_by_name && <span className="block text-[11px] text-slate-400">{t.done_by_name} · {fmtDateTime(t.done_at)}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}

            {activeTab === 'issues' && (
              <div className="space-y-4">
                {perms.can_work && task.status !== 'deleted' && (
                  <form onSubmit={raiseIssue} className="grid grid-cols-1 sm:grid-cols-[1fr_2fr_auto_auto] gap-2 p-3 rounded-xl border border-slate-200 bg-slate-50">
                    <select aria-label="Issue label" required value={selectedLabel} onChange={e => setSelectedLabel(e.target.value)} className={inputCls}>
                      <option value="">Issue type…</option>
                      {labels.map(l => <option key={l.id} value={l.id}>{l.name}{l.is_client_side ? ' (client)' : ''}</option>)}
                    </select>
                    <input aria-label="Issue detail" value={issueDetail} onChange={e => setIssueDetail(e.target.value)} placeholder="Detail (optional)" className={inputCls} />
                    <input aria-label="Follow-up date" type="date" value={issueDue} onChange={e => setIssueDue(e.target.value)} className={inputCls} title="Follow-up date (optional)" />
                    <button type="submit" disabled={busy || !selectedLabel} className={`${btn} justify-center bg-rose-600 border-rose-600 text-white hover:bg-rose-700`}>Raise</button>
                  </form>
                )}
                {(task.issues || []).length === 0 && <p className="text-slate-500 text-xs">No issues.</p>}
                {(task.issues || []).map((i: any) => (
                  <div key={i.id} className={`p-3 rounded-xl border ${i.status === 'open' ? 'border-rose-200 bg-rose-50/40' : 'border-slate-200 bg-white'}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-slate-900">{i.label_name}
                          {i.is_client_side && <span className="ml-2 text-[10px] bg-amber-100 text-amber-800 px-1.5 rounded">Waiting on client</span>}
                          {i.blocks_completion && i.status === 'open' && <span className="ml-1 text-[10px] bg-rose-100 text-rose-800 px-1.5 rounded">Blocks completion</span>}</p>
                        {i.detail && <p className="text-xs text-slate-600 mt-0.5">{i.detail}</p>}
                        <p className="text-[11px] text-slate-400 mt-0.5">Raised by {i.raised_by_name} · {fmtDateTime(i.raised_at)}{i.due_date ? ` · follow up ${fmtDate(i.due_date)}` : ''}</p>
                        {i.status !== 'open' && <p className="text-[11px] text-emerald-700 mt-0.5">Resolved by {i.resolved_by_name} · {fmtDateTime(i.resolved_at)}{i.resolution_note ? ` — ${i.resolution_note}` : ''}</p>}
                      </div>
                      {i.status === 'open' && perms.can_work && (
                        <button type="button" onClick={() => { setResolveNote(''); setResolvingIssueId(i.id); }} className={`${btn} border-emerald-300 text-emerald-800 bg-white hover:bg-emerald-50 shrink-0`}>Resolve</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'comments' && (
              <div className="space-y-3">
                {(task.comments || []).length === 0 && <p className="text-slate-500 text-xs">No comments yet.</p>}
                {(task.comments || []).map((c: any) => (
                  <div key={c.id} className="p-3 rounded-xl border border-slate-200 bg-white">
                    <p className="text-[11px] text-slate-500 mb-1"><strong className="text-slate-800">{c.user_name}</strong> · {fmtDateTime(c.created_at)}</p>
                    <div className="text-sm text-slate-800 break-words"><FormattedCommentText text={c.body} /></div>
                  </div>
                ))}
                {perms.can_work && task.status !== 'deleted' && (
                  <form onSubmit={postComment} className="flex gap-2 items-center pt-2">
                    <div className="flex-1 relative">
                      <MentionInput value={commentBody} onChange={setCommentBody} onMentionsChange={setCommentMentions}
                        placeholder="Write a comment. Type @ to mention someone." onSubmit={() => postComment()} />
                    </div>
                    <button type="submit" disabled={busy || !commentBody.trim()} className={`${btn} bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700`}>
                      <Send className="w-3.5 h-3.5" /> Send
                    </button>
                  </form>
                )}
              </div>
            )}

            {activeTab === 'files' && (
              <div className="space-y-3">
                {perms.can_work && task.status !== 'deleted' && (
                  <label className={`flex flex-col items-center justify-center gap-1 border-2 border-dashed border-slate-300 rounded-xl p-5 text-center cursor-pointer hover:bg-slate-50 ${uploading ? 'opacity-60 pointer-events-none' : ''}`}
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => { e.preventDefault(); uploadFile(e.dataTransfer.files?.[0]); }}>
                    {uploading ? <Loader2 className="w-5 h-5 animate-spin text-slate-500" /> : <Upload className="w-5 h-5 text-slate-500" />}
                    <span className="text-sm font-semibold text-slate-700">{uploading ? 'Uploading…' : 'Drop a file here or click to choose'}</span>
                    <span className="text-xs text-slate-500">PDF, JPG, PNG, XLSX, XLS, CSV, DOCX, DOC, ZIP, JSON, TXT</span>
                    <input type="file" className="sr-only" accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls,.csv,.docx,.doc,.zip,.json,.txt"
                      onChange={e => { uploadFile(e.target.files?.[0]); e.target.value = ''; }} />
                  </label>
                )}
                {(task.attachments || []).length === 0 && <p className="text-slate-500 text-xs">No files.</p>}
                <ul className="divide-y divide-slate-100 border border-slate-200 rounded-xl bg-white">
                  {(task.attachments || []).map((a: any) => (
                    <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <Paperclip className="w-4 h-4 text-slate-400 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{a.file_name}</p>
                          <p className="text-[11px] text-slate-500">{fmtSize(a.size_bytes)} · {a.uploaded_by_name} · {fmtDateTime(a.created_at)}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {perms.can_work && (
                          <a href={a.download_url} className="p-1.5 text-slate-500 hover:text-emerald-700" aria-label={`Download ${a.file_name}`}><Download className="w-4 h-4" /></a>
                        )}
                        {(perms.is_admin || perms.can_work) && (
                          <button type="button" onClick={() => deleteFile(a.id, a.file_name)} className="p-1.5 text-slate-500 hover:text-rose-700" aria-label={`Remove ${a.file_name}`}><Trash2 className="w-4 h-4" /></button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {activeTab === 'timelogs' && (
              <div className="space-y-4">
                {perms.can_work && task.status !== 'deleted' && (
                  <form onSubmit={logTime} className="p-3 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                      {[15, 30, 45, 60, 120, 240].map(m => (
                        <button type="button" key={m} onClick={() => setTimeMinutes(String(m))}
                          className={`text-xs px-2.5 py-1 rounded-md border ${Number(timeMinutes) === m ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white border-slate-300 text-slate-700'}`}>
                          {m < 60 ? `${m}m` : `${m / 60}h`}
                        </button>
                      ))}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-[auto_auto_1fr_auto] gap-2">
                      <input aria-label="Work date" type="date" max={today} required value={timeWorkDate} onChange={e => setTimeWorkDate(e.target.value)} className={inputCls} />
                      <input aria-label="Minutes" type="number" min={1} max={1440} required value={timeMinutes} onChange={e => setTimeMinutes(e.target.value)} className={inputCls + ' sm:w-28'} />
                      <input aria-label="What did you do" value={timeNote} onChange={e => setTimeNote(e.target.value)} placeholder="What did you do?" className={inputCls} />
                      <button type="submit" disabled={busy} className={`${btn} justify-center bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700`}>Log time</button>
                    </div>
                  </form>
                )}
                <p className="text-xs text-slate-500">Total on this task: <strong className="text-slate-800">{fmtMinutes(totalMinutes)}</strong></p>
                <ul className="divide-y divide-slate-100 border border-slate-200 rounded-xl bg-white">
                  {(task.time_logs || []).length === 0 && <li className="px-3 py-2.5 text-xs text-slate-500">No time logged.</li>}
                  {(task.time_logs || []).map((l: any) => (
                    <li key={l.id} className="px-3 py-2 flex items-center justify-between gap-3 text-xs">
                      <span><strong className="text-slate-800">{l.user_name}</strong> · {fmtDate(l.work_date)}{l.note ? ` — ${l.note}` : ''}</span>
                      <span className="font-semibold text-slate-700 shrink-0">{fmtMinutes(l.minutes)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {activeTab === 'history' && (
              <ol className="relative border-l border-slate-200 ml-2 space-y-3">
                {history.length === 0 && <p className="text-slate-500 text-xs pl-4">No changes yet.</p>}
                {history.map((h: any, idx: number) => (
                  <li key={idx} className="relative pl-4">
                    <span className="absolute -left-[7px] top-1 w-3 h-3 rounded-full bg-slate-300 border-2 border-white" />
                    <p className="text-xs text-slate-800"><strong>{h.who}</strong> {h.text}
                      {h.kind && h.kind !== 'manual' && h.kind !== 'status' && <span className="ml-1.5 text-[10px] bg-slate-100 text-slate-600 px-1.5 rounded">{h.kind}</span>}</p>
                    {h.reason && <p className="text-[11px] text-slate-500">Reason: {h.reason}</p>}
                    <p className="text-[11px] text-slate-400 flex items-center gap-1"><History className="w-3 h-3" />{fmtDateTime(h.at)}</p>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </div>

      {/* ---------- Dialogs ---------- */}
      {onHoldOpen && (
        <Dialog title="Put on hold" onClose={() => setOnHoldOpen(false)}>
          <form onSubmit={submitOnHold} className="space-y-3">
            <p className="text-xs text-slate-500">The reason is saved in the task history. Tasks on hold do not count as overdue.</p>
            <div className="flex flex-wrap gap-1.5">
              {ON_HOLD_PRESETS.map(p => (
                <button type="button" key={p} onClick={() => setOnHoldInput(p)}
                  className={`text-[11px] px-2 py-1 rounded-md border ${onHoldInput === p ? 'bg-amber-100 border-amber-300 text-amber-900' : 'bg-white border-slate-300 text-slate-600'}`}>{p}</button>
              ))}
            </div>
            <textarea aria-label="On-hold reason" required rows={3} value={onHoldInput} onChange={e => setOnHoldInput(e.target.value)} className={inputCls} placeholder="Reason" />
            <DialogButtons busy={busy} onCancel={() => setOnHoldOpen(false)} label="Put on hold" />
          </form>
        </Dialog>
      )}

      {resolvingIssueId && (
        <Dialog title="Resolve issue" onClose={() => setResolvingIssueId(null)}>
          <form onSubmit={submitResolve} className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {RESOLVE_PRESETS.map(p => (
                <button type="button" key={p} onClick={() => setResolveNote(p)}
                  className={`text-[11px] px-2 py-1 rounded-md border ${resolveNote === p ? 'bg-emerald-100 border-emerald-300 text-emerald-900' : 'bg-white border-slate-300 text-slate-600'}`}>{p}</button>
              ))}
            </div>
            <textarea aria-label="Resolution note" rows={3} value={resolveNote} onChange={e => setResolveNote(e.target.value)} className={inputCls} placeholder="How was it resolved? (optional)" />
            <DialogButtons busy={busy} onCancel={() => setResolvingIssueId(null)} label="Resolve" />
          </form>
        </Dialog>
      )}

      {editOpen && (
        <Dialog title="Edit task" onClose={() => setEditOpen(false)}>
          <form onSubmit={submitEdit} className="space-y-3 text-sm">
            <div>
              <label htmlFor="ed-title" className="block font-medium text-slate-700 mb-1">Title</label>
              <input id="ed-title" required maxLength={255} value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })} className={inputCls} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label htmlFor="ed-due" className="block font-medium text-slate-700 mb-1">Due date</label>
                <input id="ed-due" type="date" required value={editForm.due_date} onChange={e => setEditForm({ ...editForm, due_date: e.target.value })} className={inputCls} />
              </div>
              <div>
                <label htmlFor="ed-start" className="block font-medium text-slate-700 mb-1">Start date</label>
                <input id="ed-start" type="date" value={editForm.start_date} onChange={e => setEditForm({ ...editForm, start_date: e.target.value })} className={inputCls} />
              </div>
              <div>
                <label htmlFor="ed-pri" className="block font-medium text-slate-700 mb-1">Priority</label>
                <select id="ed-pri" value={editForm.priority} onChange={e => setEditForm({ ...editForm, priority: e.target.value })} className={inputCls}>
                  <option value="normal">Normal</option><option value="high">High</option>
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="ed-desc" className="block font-medium text-slate-700 mb-1">Notes</label>
              <textarea id="ed-desc" rows={3} value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} className={inputCls} />
            </div>
            <p className="text-xs text-slate-500">Changing the due date marks it as "set by hand". Everyone sees the change in History.</p>
            <DialogButtons busy={busy} onCancel={() => setEditOpen(false)} label="Save" />
          </form>
        </Dialog>
      )}

      {reassignOpen && (
        <Dialog title="Re-assign" onClose={() => setReassignOpen(false)}>
          <form onSubmit={submitReassign} className="space-y-3 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="ra-field" className="block font-medium text-slate-700 mb-1">Role</label>
                <select id="ra-field" value={reassignForm.field} onChange={e => setReassignForm({ ...reassignForm, field: e.target.value })} className={inputCls}>
                  <option value="assigned">Assigned to (now: {task.assigned_user_name || 'pool'})</option>
                  <option value="leader">Leader (now: {task.leader_user_name || 'none'})</option>
                  <option value="manager">Manager (now: {task.manager_user_name || 'none'})</option>
                </select>
              </div>
              <div>
                <label htmlFor="ra-user" className="block font-medium text-slate-700 mb-1">New person</label>
                <select id="ra-user" value={reassignForm.user} onChange={e => setReassignForm({ ...reassignForm, user: e.target.value })} className={inputCls}>
                  <option value="">{reassignForm.field === 'assigned' ? 'Unassigned pool' : 'Nobody'}</option>
                  {staff.map(u => <option key={u.id} value={u.id}>{u.full_name}{u.designation ? ` · ${u.designation}` : ''}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="ra-reason" className="block font-medium text-slate-700 mb-1">Reason *</label>
              <input id="ra-reason" required minLength={3} value={reassignForm.reason} onChange={e => setReassignForm({ ...reassignForm, reason: e.target.value })} className={inputCls} placeholder="e.g. Priya on leave this week" />
            </div>
            <p className="text-xs text-slate-500">The old and the new person get a notification.</p>
            <DialogButtons busy={busy} onCancel={() => setReassignOpen(false)} label="Re-assign" />
          </form>
        </Dialog>
      )}

      {reasonDialog && (
        <Dialog title={reasonDialog === 'delete' ? `Delete ${task.task_number}?` : `Reopen ${task.task_number}?`} onClose={() => setReasonDialog(null)}>
          <form onSubmit={submitReason} className="space-y-3 text-sm">
            <p className="text-xs text-slate-500">
              {reasonDialog === 'delete'
                ? 'The task is hidden from all lists and cannot be restored. The task number is never used again. Everyone on the task is notified.'
                : 'The task goes back to "In process" and the completed date is cleared.'}
            </p>
            <input aria-label="Reason" required minLength={3} value={reasonInput} onChange={e => setReasonInput(e.target.value)} className={inputCls} placeholder="Reason (required)" autoFocus />
            <DialogButtons busy={busy} onCancel={() => setReasonDialog(null)} label={reasonDialog === 'delete' ? 'Delete task' : 'Reopen'} danger={reasonDialog === 'delete'} />
          </form>
        </Dialog>
      )}

      {dupFile && (
        <Dialog title="Same file already attached" onClose={() => setDupFile(null)}>
          <div className="space-y-3 text-sm">
            <p className="text-slate-700">{dupFile.message}</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setDupFile(null)} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700">Cancel</button>
              <button type="button" disabled={uploading} onClick={() => uploadFile(dupFile.file, true)} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold">Upload anyway</button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
};

const Dialog: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({ title, onClose, children }) => (
  <div className="fixed inset-0 !mt-0 z-[60] bg-black/50 flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
    <div className="bg-white w-full sm:max-w-lg max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl">
      <div className="flex items-center justify-between border-b px-5 py-3.5">
        <h3 className="font-bold text-slate-900">{title}</h3>
        <button type="button" onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
      </div>
      <div className="p-5">{children}</div>
    </div>
  </div>
);

const DialogButtons: React.FC<{ busy: boolean; onCancel: () => void; label: string; danger?: boolean }> = ({ busy, onCancel, label, danger }) => (
  <div className="flex justify-end gap-2 pt-1">
    <button type="button" onClick={onCancel} className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-700 hover:bg-slate-50 text-sm">Cancel</button>
    <button type="submit" disabled={busy} className={`px-4 py-2 rounded-lg font-semibold text-white text-sm inline-flex items-center gap-2 disabled:opacity-60 ${danger ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'}`}>
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}{label}
    </button>
  </div>
);
