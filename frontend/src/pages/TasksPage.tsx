import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, errorMessage as apiErrorMessage } from '../api/client';
import { fmtDate } from '../utils/format';
import { CreateTaskModal } from '../components/CreateTaskModal';
import { TaskFilters, ExportButtons, BulkBar } from '../components/TaskListTools';
import { useAuth } from '../context/AuthContext';
import { TaskDetailPage } from './TaskDetailPage';
import {
  Search, Plus, Filter, Calendar, AlertCircle,
  Clock, CheckCircle, RefreshCw, X, Upload, Download,
  List, Kanban, AlertTriangle, ArrowRight, UserCheck, Check,
  Sparkles, CheckCheck
} from 'lucide-react';

const ON_HOLD_PRESETS = [
  'Awaiting Client Bank Statement',
  'Awaiting OTP / DSC from Client',
  'Portal Downtime (ITD / GSTN / MCA)',
  'Awaiting Signed Balance Sheet / Audit Report',
  'Awaiting Tax Challan Payment Confirmation',
  'Under Partner / Peer Review',
];

export const TasksPage: React.FC = () => {
  const { user, firm } = useAuth();
  const isAdmin = user?.system_role === 'superadmin' || user?.system_role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();

  const [viewMode, setViewMode] = useState<'list' | 'kanban'>(() => {
    return (localStorage.getItem('firmflow_task_view') as 'list' | 'kanban') || 'list';
  });

  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');

  // In-app On-Hold Modal
  const [pendingOnHoldTaskId, setPendingOnHoldTaskId] = useState<string | null>(null);
  const [onHoldInput, setOnHoldInput] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Drag and drop state for Kanban
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);

  // Server-side paging (spec §8: never load everything into the browser)
  const [count, setCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1);
  const PAGE_SIZE = 50;


  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(''), 3500);
  };

  const showError = (msg: string) => {
    setErrorMessage(msg);
    setTimeout(() => setErrorMessage(''), 6000);
  };

  const handleViewModeChange = (mode: 'list' | 'kanban') => {
    setViewMode(mode);
    localStorage.setItem('firmflow_task_view', mode);
  };

  // Build the list query from the URL so a dashboard tile, a tab, search and paging
  // all use the same server rule as the counts (spec §6.3).
  const buildQuery = () => {
    const q = new URLSearchParams();
    const tile = searchParams.get('tile')
      || (searchParams.get('unassigned') === 'true' ? 'unassigned' : '')
      || searchParams.get('date_filter') || '';
    if (tile) q.set('tile', tile);
    for (const key of ['role', 'status', 'search', 'priority', 'client', 'task_type', 'fy', 'period', 'billing_state', 'user_id', 'ordering']) {
      const v = searchParams.get(key);
      if (v) q.set(key, v);
    }
    if (!q.get('ordering')) q.set('ordering', 'due_date');
    q.set('page', String(page));
    q.set('page_size', String(PAGE_SIZE));
    return `/api/v1/tasks/?${q.toString()}`;
  };

  const fetchTasks = () => {
    setLoading(true);
    const query = buildQuery();
    console.debug('[tasks] fetch', query);
    api.get(query)
      .then(res => {
        setTasks(res.results || []);
        setCount(res.count || 0);
        setTotalPages(res.total_pages || 1);
      })
      .catch(err => {
        console.error('[tasks] list failed', err);
        setTasks([]);
        setCount(0);
        showError(apiErrorMessage(err, 'Could not load tasks.'));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchTasks();
  }, [searchParams]);

  useEffect(() => {
    if (searchParams.get('create') === 'true') {
      if (canCreate) {
        setShowCreateModal(true);
      } else {
        // Old link / bookmark: do not show a form that the server will refuse
        console.warn('[tasks] create=true ignored: effective_can_create_tasks is false for this user');
        showError('You are not allowed to create tasks. Ask an admin to allow it for you on the Team page.');
        updateParams({ create: null });
      }
    }
    const taskIdParam = searchParams.get('taskId');
    if (taskIdParam) {
      setSelectedTaskId(taskIdParam);
    }
  }, [searchParams]);

  // Keep the search box in sync with the URL, and push typing to the URL after 350 ms
  useEffect(() => {
    setSearchQuery(searchParams.get('search') || '');
  }, []);
  useEffect(() => {
    const current = searchParams.get('search') || '';
    if (searchQuery.trim() === current) return;
    const t = window.setTimeout(() => updateParams({ search: searchQuery.trim() || null, page: null }), 350);
    return () => window.clearTimeout(t);
  }, [searchQuery]);

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
    }
    setSearchParams(next);
  };

  // Server decides: admin, or per-user exception, or firm setting (see User.effective_can_create_tasks)
  const canCreate = !!user?.effective_can_create_tasks;
  // Bulk selection (admins only; spec §6.1-2)
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => setSelected([]), [searchParams]);
  const toggleSel = (id: string) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  const handleImportTasks = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFile) return;
    setImportLoading(true);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', importFile);
      const res = await api.post('/api/v1/tasks/import_spreadsheet/', formData);
      setImportResult(res);
      fetchTasks();
      showToast(`Spreadsheet imported! Processed rows.`);
    } catch (err: any) {
      showError(apiErrorMessage(err, 'Task import failed'));
    } finally {
      setImportLoading(false);
    }
  };

  const handlePickup = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.post(`/api/v1/tasks/${taskId}/pickup/`);
      fetchTasks();
      showToast('Task picked up and assigned to you!');
    } catch (err: any) {
      showError(apiErrorMessage(err, 'Failed to pick up task'));
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string) => {
    if (newStatus === 'on_hold') {
      setPendingOnHoldTaskId(taskId);
      setOnHoldInput('');
      return;
    }
    try {
      await api.post(`/api/v1/tasks/${taskId}/change_status/`, {
        status: newStatus,
        reason: '',
      });
      fetchTasks();
      showToast(`Task moved to ${newStatus.replace('_', ' ')}.`);
    } catch (err: any) {
      showError(apiErrorMessage(err, 'Could not change the status.'));
    }
  };

  const submitOnHold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingOnHoldTaskId || !onHoldInput.trim()) return;
    try {
      await api.post(`/api/v1/tasks/${pendingOnHoldTaskId}/change_status/`, {
        status: 'on_hold',
        on_hold_reason: onHoldInput.trim(),
      });
      setPendingOnHoldTaskId(null);
      fetchTasks();
      showToast('Task put on hold with documented reason.');
    } catch (err: any) {
      showError(apiErrorMessage(err, 'Failed to put task on hold'));
    }
  };

  const handleDragStart = (e: React.DragEvent, taskId: string) => {
    e.dataTransfer.setData('text/plain', taskId);
    setDraggedTaskId(taskId);
  };

  const handleDragOver = (e: React.DragEvent, colId: string) => {
    e.preventDefault();
    if (dragOverColumn !== colId) {
      setDragOverColumn(colId);
    }
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  const handleDrop = async (e: React.DragEvent, targetStatus: string) => {
    e.preventDefault();
    setDragOverColumn(null);
    const taskId = e.dataTransfer.getData('text/plain') || draggedTaskId;
    if (!taskId) return;
    setDraggedTaskId(null);

    const task = tasks.find(t => t.id === taskId);
    if (task && task.status !== targetStatus) {
      handleStatusChange(taskId, targetStatus);
    }
  };

  const TABS = [
    { id: '', label: 'All open & done' },
    { id: 'pending', label: 'Pending' },
    { id: 'unassigned', label: 'Unassigned pool', highlight: true },
    { id: 'due_today', label: 'Due today' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'with_issues', label: 'With issues' },
    { id: 'on_hold', label: 'On hold' },
    { id: 'completed', label: 'Completed' },
  ];
  const TILE_LABELS: Record<string, string> = {
    not_started: 'Not started', in_process: 'In process', priority_high: 'High priority', long_due: 'Long due',
    due_in_7_days: 'Due in 7 days', waiting_on_client: 'Waiting on client', completed_fy: 'Completed (this FY)',
    completed_this_month: 'Completed this month', unbilled: 'Unbilled',
  };
  const activeTile = searchParams.get('tile') || (searchParams.get('unassigned') === 'true' ? 'unassigned' : '') || searchParams.get('date_filter') || '';
  const roleParam = searchParams.get('role');

  const setFilterTab = (tab: string) => {
    const next = new URLSearchParams();
    if (tab) next.set('tile', tab);
    if (roleParam) next.set('role', roleParam);
    const sq = searchParams.get('search');
    if (sq) next.set('search', sq);
    setSearchParams(next);
  };

  // Filtering, search and paging happen on the server
  const filteredTasks = tasks;

  const KANBAN_COLUMNS = [
    {
      id: 'not_started',
      label: 'Not Started',
      badgeBg: 'bg-slate-100 text-slate-700',
      borderTop: 'border-t-slate-400',
    },
    {
      id: 'in_process',
      label: 'In Process',
      badgeBg: 'bg-blue-100 text-blue-800',
      borderTop: 'border-t-blue-500',
    },
    {
      id: 'on_hold',
      label: 'On Hold',
      badgeBg: 'bg-amber-100 text-amber-800',
      borderTop: 'border-t-amber-500',
    },
    {
      id: 'completed',
      label: 'Completed',
      badgeBg: 'bg-emerald-100 text-emerald-800',
      borderTop: 'border-t-emerald-600',
    },
  ];

  return (
    <div className="space-y-5">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Practice Tasks</h2>
          <p className="text-xs text-slate-500 mt-1">
            Track, assign, and advance tasks across all services and clients in List or Kanban view.
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          {/* View Mode Toggle */}
          <div className="bg-slate-100 p-1 rounded-xl flex items-center border border-slate-200">
            <button
              onClick={() => handleViewModeChange('list')}
              className={`flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                viewMode === 'list'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
              title="Table List View"
            >
              <List className="w-3.5 h-3.5" />
              <span>List</span>
            </button>
            <button
              onClick={() => handleViewModeChange('kanban')}
              className={`flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                viewMode === 'kanban'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
              title="Kanban Board View"
            >
              <Kanban className="w-3.5 h-3.5" />
              <span>Kanban</span>
            </button>
          </div>

          {/* Import Tasks Button */}
          {isAdmin && (
            <button
              onClick={() => setShowImportModal(true)}
              className="flex items-center space-x-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg text-xs font-semibold transition"
              title="Bulk import tasks from CSV/Excel"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Import</span>
            </button>
          )}

          {/* New Task Button */}
          {canCreate && <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white px-3.5 py-2 rounded-lg text-xs font-semibold transition shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>New Task</span>
          </button>}
        </div>
      </div>

      {/* Toast message */}
      {toastMessage && (
        <div className="p-2.5 bg-emerald-600 text-white rounded-xl text-xs font-semibold flex items-center justify-between shadow-sm animate-in fade-in">
          <span>✓ {toastMessage}</span>
          <button onClick={() => setToastMessage('')} className="text-white hover:text-emerald-100 font-bold">×</button>
        </div>
      )}

      {/* Error message */}
      {errorMessage && (
        <div className="p-3 bg-rose-600 text-white rounded-xl text-xs font-bold flex items-center justify-between shadow-md animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage('')} className="text-white hover:text-rose-100 font-bold ml-4">✕</button>
        </div>
      )}

      {/* Search Bar & Priority Filter */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <div className="relative flex-1 w-full max-w-xl">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search task number, title, client, GSTIN or full PAN"
            aria-label="Search tasks"
            className="w-full pl-9 pr-8 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-emerald-500 outline-none transition"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center space-x-3 self-end sm:self-auto w-full sm:w-auto justify-end">
          <div className="flex items-center space-x-1.5 text-xs text-slate-500">
            <Filter className="w-3.5 h-3.5" />
            <span>Priority:</span>
          </div>
          <select
            value={searchParams.get('priority') || 'all'}
            onChange={e => updateParams({ priority: e.target.value === 'all' ? null : e.target.value, page: null })}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-700 font-medium focus:ring-1 focus:ring-emerald-500"
          >
            <option value="all">All Priorities</option>
            <option value="high">High Priority</option>
            <option value="normal">Normal</option>
          </select>
          <span className="text-xs text-slate-400 font-medium shrink-0">
            {count} task{count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <TaskFilters params={searchParams} isAdmin={isAdmin} onChange={updateParams} />

      {/* Filter tabs (server rules, same as dashboard tiles) */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
        {roleParam && (
          <button onClick={() => updateParams({ role: null, page: null })}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200 whitespace-nowrap"
            title="Remove role filter">
            Role: {roleParam} <X className="w-3 h-3" />
          </button>
        )}
        {activeTile && !TABS.some(t => t.id === activeTile) && (
          <button onClick={() => setFilterTab('')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white whitespace-nowrap"
            title="Clear filter">
            {TILE_LABELS[activeTile] || activeTile} <X className="w-3 h-3" />
          </button>
        )}
        {TABS.map((tab) => {
          const isSelected = activeTile === tab.id;
          return (
            <button
              key={tab.id || 'all'}
              onClick={() => setFilterTab(tab.id)}
              aria-pressed={isSelected}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition whitespace-nowrap ${
                isSelected
                  ? 'bg-slate-900 text-white'
                  : tab.highlight
                  ? 'text-purple-700 bg-purple-50 hover:bg-purple-100'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {tab.label}{isSelected ? ` (${count})` : ''}
            </button>
          );
        })}
      </div>

      {/* Content Area: List View vs Kanban Board */}
      {loading ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-500">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
          <p className="text-xs font-semibold text-slate-700">Loading compliance tasks...</p>
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-500">
          <CheckCircle className="w-10 h-10 text-slate-300 mx-auto mb-2" />
          <p className="font-semibold text-slate-700 text-sm">No matching tasks found</p>
          <p className="text-xs text-slate-400 mt-0.5">Try clearing your search query or switching tabs.</p>
        </div>
      ) : viewMode === 'list' ? (
        /* TABLE LIST VIEW */
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 text-[11px] uppercase font-bold tracking-wider">
                <tr>
                  {isAdmin && <th className="pl-4 py-3.5 w-8"><input type="checkbox" aria-label="Select all on this page" className="h-4 w-4 accent-emerald-600"
                    checked={tasks.length > 0 && tasks.every(t => selected.includes(t.id))}
                    onChange={e => setSelected(e.target.checked ? tasks.map(t => t.id) : [])} /></th>}
                  <th className="px-5 py-3.5 w-36">Task Number</th>
                  <th className="px-5 py-3.5 min-w-[200px]">Client Legal Name</th>
                  <th className="px-5 py-3.5 min-w-[200px]">Service / Task Type</th>
                  <th className="px-5 py-3.5 w-32">Period</th>
                  <th className="px-5 py-3.5 w-32">Due Date</th>
                  <th className="px-5 py-3.5 min-w-[160px]">Assignee</th>
                  <th className="px-5 py-3.5 w-32">Status</th>
                  <th className="px-5 py-3.5 text-right w-28">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredTasks.map((task) => (
                  <tr
                    key={task.id}
                    onClick={() => setSelectedTaskId(task.id)}
                    className={`hover:bg-slate-50/80 cursor-pointer transition group ${selected.includes(task.id) ? 'bg-emerald-50/60' : ''}`}
                  >
                    {isAdmin && <td className="pl-4 py-3.5" onClick={e => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Select ${task.task_number}`} className="h-4 w-4 accent-emerald-600" checked={selected.includes(task.id)} onChange={() => toggleSel(task.id)} />
                    </td>}
                    <td className="px-5 py-3.5 font-bold text-emerald-800 font-mono whitespace-nowrap">
                      {task.priority === 'high' && (
                        <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1.5 align-middle" title="High Priority" />
                      )}
                      {task.task_number}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="font-semibold text-slate-900">{task.client_name}</div>
                      <div className="text-[11px] text-slate-400 font-mono">{task.client_pan || 'No PAN'}</div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-800 font-medium">
                      {task.task_type_name}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 text-[11px] whitespace-nowrap">
                      {task.period_label || task.fy_label || '-'}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap">
                      <span className={`font-semibold px-2 py-0.5 rounded text-[11px] ${
                        task.is_overdue
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : task.is_due_today
                          ? 'bg-amber-50 text-amber-800 border border-amber-200'
                          : 'text-slate-600'
                      }`}>
                        {fmtDate(task.due_date)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {task.assigned_user ? (
                        <span className="text-slate-800 font-semibold">{task.assigned_user_name}</span>
                      ) : (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                          Unassigned
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap">
                      <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full capitalize ${
                        task.status === 'completed'
                          ? 'bg-emerald-100 text-emerald-800'
                          : task.status === 'in_process'
                          ? 'bg-blue-100 text-blue-800'
                          : task.status === 'on_hold'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-700'
                      }`}>
                        {task.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {!task.assigned_user ? (
                        <button
                          type="button"
                          onClick={(e) => handlePickup(task.id, e)}
                          className="bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-semibold px-3 py-1 rounded-md transition shadow-sm"
                        >
                          Pick Up
                        </button>
                      ) : (
                        <span className="text-[11px] text-slate-400 group-hover:text-emerald-700 font-semibold transition">
                          View Details →
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Table Footer with Summary */}
          <div className="px-5 py-3 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>
              Showing {count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, count)} of {count}
            </span>
            <div className="flex items-center gap-2">
              <ExportButtons query={buildQuery().split('?')[1]} />
              <button disabled={page <= 1} onClick={() => updateParams({ page: String(page - 1) })}
                className="px-2.5 py-1 border border-slate-300 rounded-md bg-white disabled:opacity-40">Previous</button>
              <span>Page {page} of {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => updateParams({ page: String(page + 1) })}
                className="px-2.5 py-1 border border-slate-300 rounded-md bg-white disabled:opacity-40">Next</button>
            </div>
          </div>
        </div>
      ) : (
        /* KANBAN BOARD VIEW */
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
          {KANBAN_COLUMNS.map((column) => {
            const columnTasks = filteredTasks.filter(t => t.status === column.id);
            const isDropTarget = dragOverColumn === column.id;

            return (
              <div
                key={column.id}
                onDragOver={(e) => handleDragOver(e, column.id)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, column.id)}
                className={`bg-slate-50/80 rounded-2xl border ${
                  isDropTarget ? 'border-emerald-500 bg-emerald-50/30' : 'border-slate-200'
                } border-t-4 ${column.borderTop} flex flex-col min-h-[500px] transition`}
              >
                {/* Column Header */}
                <div className="p-3.5 flex items-center justify-between border-b border-slate-200/70">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-xs uppercase tracking-wider text-slate-700">
                      {column.label}
                    </span>
                    <span className={`text-xs font-bold px-2 py-0.2 rounded-full ${column.badgeBg}`}>
                      {columnTasks.length}
                    </span>
                  </div>
                </div>

                {/* Column Cards Container */}
                <div className="p-2.5 space-y-2.5 flex-1 overflow-y-auto max-h-[72vh]">
                  {columnTasks.length === 0 ? (
                    <div className="py-8 text-center text-[11px] text-slate-400 border-2 border-dashed border-slate-200 rounded-xl">
                      Drop tasks here
                    </div>
                  ) : (
                    columnTasks.map((task) => (
                      <div
                        key={task.id}
                        draggable
                        onDragStart={(e) => handleDragStart(e, task.id)}
                        onClick={() => setSelectedTaskId(task.id)}
                        className="bg-white rounded-xl p-3.5 shadow-sm border border-slate-200 hover:shadow-md hover:border-slate-300 transition cursor-grab active:cursor-grabbing group space-y-2"
                      >
                        {/* Top row: Priority & Task Number */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-emerald-800 font-mono">
                            {task.task_number}
                          </span>
                          <div className="flex items-center space-x-1">
                            {task.is_blocked && (
                              <span className="text-[10px] bg-red-100 text-red-800 font-bold px-1.5 py-0.2 rounded" title="Open blockers pending">
                                Blocked
                              </span>
                            )}
                            <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded uppercase ${
                              task.priority === 'high'
                                ? 'bg-red-50 text-red-700 border border-red-200'
                                : 'bg-slate-100 text-slate-600'
                            }`}>
                              {task.priority}
                            </span>
                          </div>
                        </div>

                        {/* Title & Service */}
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 line-clamp-2">
                            {task.title || task.task_type_name}
                          </h4>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            {task.client_name}
                            <span className="text-slate-400 text-[10px] ml-1 font-mono">({task.client_pan || 'No PAN'})</span>
                          </p>
                        </div>

                        {/* Period & Due Date */}
                        <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100">
                          <span className="text-slate-500 font-medium">
                            {task.period_label || task.fy_label || 'One-off'}
                          </span>
                          <span className={`font-semibold px-1.5 py-0.2 rounded ${
                            task.is_overdue
                              ? 'bg-red-50 text-red-700 border border-red-200'
                              : task.is_due_today
                              ? 'bg-amber-50 text-amber-800 border border-amber-200'
                              : 'text-slate-600'
                          }`}>
                            {fmtDate(task.due_date)}
                          </span>
                        </div>

                        {/* Footer: Assignee & Quick Status Dropdown */}
                        <div className="flex items-center justify-between pt-1 text-[11px]">
                          {task.assigned_user ? (
                            <div className="flex items-center space-x-1.5 text-slate-700 truncate max-w-[130px]">
                              <div className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 font-bold text-[10px] flex items-center justify-center shrink-0">
                                {task.assigned_user_name.charAt(0).toUpperCase()}
                              </div>
                              <span className="truncate font-semibold">{task.assigned_user_name}</span>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => handlePickup(task.id, e)}
                              className="bg-purple-600 hover:bg-purple-700 text-white text-[10px] font-bold px-2 py-0.5 rounded transition shadow-sm"
                            >
                              Pick Up
                            </button>
                          )}

                          {/* Quick Status Select */}
                          <select
                            value={task.status}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleStatusChange(task.id, e.target.value)}
                            className="text-[10px] font-semibold border border-slate-200 rounded px-1.5 py-0.5 bg-slate-50 hover:bg-white text-slate-700 capitalize focus:outline-none"
                          >
                            <option value="not_started">Not Started</option>
                            <option value="in_process">In Process</option>
                            <option value="on_hold">On Hold</option>
                            <option value="completed">Completed</option>
                          </select>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Task Detail Modal */}
      {selectedTaskId && (
        <TaskDetailPage
          taskId={selectedTaskId}
          onClose={() => {
            setSelectedTaskId(null);
            if (searchParams.get('taskId')) {
              const newParams = new URLSearchParams(searchParams);
              newParams.delete('taskId');
              setSearchParams(newParams, { replace: true });
            }
          }}
          onUpdated={fetchTasks}
        />
      )}

      {/* In-App On-Hold Reason Modal */}
      {pendingOnHoldTaskId && (
        <div className="fixed inset-0 !mt-0 z-[60] bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">Document On-Hold Reason</h3>
              </div>
              <button onClick={() => setPendingOnHoldTaskId(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Select a standard compliance reason or write your own note. This reason is recorded in the task history.
            </p>

            <div className="flex flex-wrap gap-1.5">
              {ON_HOLD_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setOnHoldInput(preset)}
                  className={`text-[11px] font-medium px-2.5 py-1 rounded-lg border text-left transition ${
                    onHoldInput === preset
                      ? 'bg-amber-100 text-amber-900 border-amber-300 font-semibold'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {preset}
                </button>
              ))}
            </div>

            <form onSubmit={submitOnHold} className="space-y-3">
              <textarea
                value={onHoldInput}
                onChange={e => setOnHoldInput(e.target.value)}
                placeholder="Specific details regarding the hold..."
                rows={2}
                required
                className="w-full border rounded-lg p-2.5 text-xs text-slate-800 focus:ring-1 focus:ring-amber-500"
              />
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setPendingOnHoldTaskId(null)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-600 border rounded-lg hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!onHoldInput.trim()}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40 rounded-lg shadow-sm"
                >
                  Confirm Hold
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Import Tasks Modal */}
      {showImportModal && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-base font-bold text-slate-900">Import Tasks via Spreadsheet</h3>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Upload a CSV or XLSX spreadsheet containing compliance tasks. The importer matches client PANs and service task types automatically.
            </p>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="font-semibold text-slate-700">Need a template?</div>
              <a
                href="/api/v1/tasks/download_template/"
                download
                className="text-emerald-700 hover:underline flex items-center gap-1 font-semibold"
              >
                <Download className="w-3.5 h-3.5" /> Download Sample CSV Template
              </a>
            </div>

            <form onSubmit={handleImportTasks} className="space-y-4">
              <div>
                <input
                  type="file"
                  accept=".csv, .xlsx, .xls"
                  onChange={e => setImportFile(e.target.files?.[0] || null)}
                  required
                  className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"
                />
              </div>

              {importResult && (
                <div className={`p-3 rounded-lg text-xs ${importResult.errors?.length > 0 ? 'bg-amber-50 text-amber-900 border border-amber-200' : 'bg-emerald-50 text-emerald-900 border border-emerald-200'}`}>
                  <p className="font-semibold">{importResult.message || `Processed ${importResult.imported_count || 0} tasks`}</p>
                  <p className="mt-0.5">Imported: {importResult.imported_count || 0} tasks | Errors: {importResult.errors?.length || 0}</p>
                  {importResult.errors?.length > 0 && (
                    <div className="mt-2 text-[11px] text-red-700 max-h-32 overflow-y-auto space-y-0.5">
                      {importResult.errors.map((err: any, idx: number) => (
                        <div key={idx}>Row {err.row}: {err.error}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-3.5 py-1.5 border rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={importLoading || !importFile}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {importLoading ? 'Importing...' : 'Upload & Import'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Task Modal */}
      {showCreateModal && (
        <CreateTaskModal
          onClose={() => {
            setShowCreateModal(false);
            if (searchParams.get('create')) updateParams({ create: null });
          }}
          onCreated={(task) => {
            setShowCreateModal(false);
            if (searchParams.get('create')) updateParams({ create: null });
            fetchTasks();
            showToast(`Task ${task?.task_number || ''} created.`);
          }}
        />
      )}
      {isAdmin && selected.length > 0 && (
        <BulkBar ids={selected} onClear={() => setSelected([])} onDone={(msg) => { showToast(msg); setSelected([]); fetchTasks(); }} />
      )}
    </div>
  );
};
