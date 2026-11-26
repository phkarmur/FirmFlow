import React, { useEffect, useState, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { api, errorMessage, localToday } from '../api/client';
import { fmtDate } from '../utils/format';
import {
  Clock, AlertTriangle, Calendar, CheckCircle2,
  AlertCircle, Layers, PlusCircle, ArrowUpRight,
  ShieldCheck, HelpCircle, Flame, ExternalLink, ArrowRight
} from 'lucide-react';
import { TaskDetailPage } from './TaskDetailPage';

/** Row from /api/v1/services/compliance-calendar/?active=true (managed on the Settings page). */
interface ComplianceEvent {
  id: string;
  code: string;
  title: string;
  scope: string;
  description: string;
  due_text: string;
  next_due_date: string | null;
  days_left: number | null;
  state: 'due_today' | 'due_soon' | 'normal';
}

// Red on the due day; orange during the warning days before it (default 2 days)
const EVENT_STYLE: Record<ComplianceEvent['state'], { card: string; chip: string; code: string }> = {
  due_today: { card: 'bg-red-50 border-red-300', chip: 'bg-red-600 text-white border-red-600', code: 'bg-red-100 text-red-800' },
  due_soon: { card: 'bg-orange-50 border-orange-300', chip: 'bg-orange-500 text-white border-orange-500', code: 'bg-orange-100 text-orange-800' },
  normal: { card: 'bg-slate-50/60 border-slate-100', chip: 'bg-white text-slate-600 border-slate-200', code: 'bg-emerald-100 text-emerald-800' },
};

export const DashboardPage: React.FC = () => {
  const { user, firm } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.system_role === 'superadmin' || user?.system_role === 'admin';
  // Same rule as the server: staff create tasks only when the firm setting allows it
  const canCreate = !!user?.effective_can_create_tasks;

  const [stats, setStats] = useState<any>(null);
  const [urgentTasks, setUrgentTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const [loadError, setLoadError] = useState('');
  const [calendarError, setCalendarError] = useState('');
  const [upcomingError, setUpcomingError] = useState('');
  const [events, setEvents] = useState<ComplianceEvent[]>([]);

  useEffect(() => {
    api.get('/api/v1/services/compliance-calendar/?active=true')
      .then((rows: any) => {
        const list: ComplianceEvent[] = Array.isArray(rows) ? rows : [];
        console.debug('[dashboard] compliance calendar', list.map(r => `${r.code}:${r.state}:${r.days_left}`).join(' '));
        setEvents(list);
      })
      .catch(err => { console.error('[dashboard] compliance calendar failed', err); setCalendarError(errorMessage(err, 'Could not load the compliance calendar.')); });
  }, []);

  const fetchDashboardData = () => {
    setLoading(true);
    setLoadError('');
    setUpcomingError('');
    const endpoint = isAdmin
      ? '/api/v1/reports/dashboard/office/'
      : '/api/v1/reports/dashboard/my/';
    // Upcoming list: open tasks by due date. For staff, only tasks assigned to them.
    const urgentQuery = `/api/v1/tasks/?tile=pending&ordering=due_date&page_size=5${isAdmin ? '' : '&role=assigned'}`;

    // allSettled: one failing request must not blank the whole dashboard
    Promise.allSettled([api.get(endpoint), api.get(urgentQuery)])
      .then(([statsRes, tasksRes]) => {
        if (statsRes.status === 'fulfilled') {
          setStats(statsRes.value);
        } else {
          console.error('[dashboard] stats request failed', statsRes.reason);
          setLoadError(errorMessage(statsRes.reason, 'Could not load dashboard counts.'));
        }
        if (tasksRes.status === 'fulfilled') {
          const v: any = tasksRes.value;
          setUrgentTasks((Array.isArray(v) ? v : v.results || []).slice(0, 5));
        } else {
          console.error('[dashboard] upcoming tasks request failed', tasksRes.reason);
          setUpcomingError(errorMessage(tasksRes.reason, 'Could not load the upcoming tasks.'));
        }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDashboardData();
  }, [isAdmin]);

  const tiles = isAdmin ? [
    {
      label: 'Pending Tasks',
      value: stats?.pending || 0,
      icon: Clock,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      filter: 'pending',
      tooltip: 'Tasks currently in Not Started, In Process, or On Hold state.'
    },
    {
      label: 'Overdue Tasks',
      value: stats?.overdue || 0,
      icon: AlertTriangle,
      color: 'text-rose-600',
      bg: 'bg-rose-50',
      border: 'border-rose-200',
      filter: 'overdue',
      tooltip: 'Statutory or agreed due date is strictly prior to today.'
    },
    {
      label: 'Due Today',
      value: stats?.due_today || 0,
      icon: Calendar,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      filter: 'due_today',
      tooltip: 'Statutory compliance deadline is scheduled for today.'
    },
    {
      label: 'Due in 7 Days',
      value: stats?.due_in_7_days || 0,
      icon: Calendar,
      color: 'text-indigo-600',
      bg: 'bg-indigo-50',
      border: 'border-indigo-200',
      filter: 'due_in_7_days',
      tooltip: 'Upcoming statutory deadlines due within next 7 days.'
    },
    {
      label: 'With Pending Issues',
      value: stats?.with_issues || 0,
      icon: AlertCircle,
      color: 'text-red-600',
      bg: 'bg-red-50',
      border: 'border-red-200',
      filter: 'with_issues',
      tooltip: 'Tasks flagged with active issues (e.g. client bank statements, OTP downtime).'
    },
    {
      label: 'Unassigned Pool',
      value: stats?.unassigned || 0,
      icon: Layers,
      color: 'text-purple-600',
      bg: 'bg-purple-50',
      border: 'border-purple-200',
      filter: 'unassigned',
      tooltip: 'Tasks awaiting staff member self-pickup or assignment.'
    },
    {
      label: 'Completed (FY)',
      value: stats?.completed_fy || 0,
      icon: CheckCircle2,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
      border: 'border-emerald-200',
      filter: 'completed_fy',
      tooltip: 'Tasks completed inside the current financial year.'
    },
    {
      label: 'Not Started',
      value: stats?.not_started || 0,
      icon: Clock,
      color: 'text-slate-600',
      bg: 'bg-slate-50',
      border: 'border-slate-200',
      filter: 'not_started',
      tooltip: 'Created but no work recorded yet.'
    },
    {
      label: 'In Process',
      value: stats?.in_process || 0,
      icon: Clock,
      color: 'text-sky-600',
      bg: 'bg-sky-50',
      border: 'border-sky-200',
      filter: 'in_process',
      tooltip: 'Work has started.'
    },
    {
      label: 'On Hold',
      value: stats?.on_hold || 0,
      icon: AlertCircle,
      color: 'text-orange-600',
      bg: 'bg-orange-50',
      border: 'border-orange-200',
      filter: 'on_hold',
      tooltip: 'Paused with a documented reason. Not counted as overdue.'
    },
    {
      label: 'High Priority',
      value: stats?.priority_high || 0,
      icon: Flame,
      color: 'text-red-600',
      bg: 'bg-red-50',
      border: 'border-red-200',
      filter: 'priority_high',
      tooltip: 'Open tasks marked high priority.'
    },
    {
      label: 'Long Due',
      value: stats?.long_due || 0,
      icon: AlertTriangle,
      color: 'text-fuchsia-600',
      bg: 'bg-fuchsia-50',
      border: 'border-fuchsia-200',
      filter: 'long_due',
      tooltip: 'Open tasks created more than the firm long-due limit (Settings) ago.'
    },
    {
      label: 'Unbilled Deliverables',
      value: stats?.unbilled || 0,
      icon: ArrowUpRight,
      color: 'text-cyan-600',
      bg: 'bg-cyan-50',
      border: 'border-cyan-200',
      filter: 'unbilled',
      tooltip: 'Completed compliance tasks awaiting invoice generation.'
    },
  ] : [
    {
      label: 'My Pending Tasks',
      value: stats?.my_pending || 0,
      icon: Clock,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      filter: 'pending', mine: true,
      tooltip: 'Your active compliance assignments.'
    },
    {
      label: 'My Overdue Tasks',
      value: stats?.my_overdue || 0,
      icon: AlertTriangle,
      color: 'text-rose-600',
      bg: 'bg-rose-50',
      border: 'border-rose-200',
      filter: 'overdue', mine: true,
      tooltip: 'Assigned tasks past deadline requiring immediate delivery.'
    },
    {
      label: 'My Due Today',
      value: stats?.my_due_today || 0,
      icon: Calendar,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      filter: 'due_today', mine: true,
      tooltip: 'Tasks scheduled for completion today.'
    },
    {
      label: 'Completed This Month',
      value: stats?.my_completed_this_month || 0,
      icon: CheckCircle2,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
      border: 'border-emerald-200',
      filter: 'completed_this_month', mine: true,
      tooltip: 'Tasks assigned to you and completed this month.'
    },
    {
      label: 'Unassigned (Can Pick Up)',
      value: stats?.unassigned_available_to_pickup || 0,
      icon: Layers,
      color: 'text-purple-600',
      bg: 'bg-purple-50',
      border: 'border-purple-200',
      filter: 'unassigned',
      tooltip: 'Unassigned tasks available for 1-click self pickup.'
    },
  ];

  // Each tile opens the task list with the SAME server rule that produced its count (spec §6.3)
  const handleTileClick = (filter: string, mine?: boolean) => {
    const params = new URLSearchParams({ tile: filter });
    if (mine) params.set('role', 'assigned');
    console.debug('[dashboard] tile click', filter, mine ? '(mine)' : '');
    navigate(`/tasks?${params.toString()}`);
  };

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
            {isAdmin ? 'Practice Command Center' : 'My Work Dashboard'}
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {isAdmin
              ? 'Real-time overview of compliance deadlines, workflow stages, and firm-wide task delivery.'
              : 'Your assigned statutory tasks, upcoming client due dates, and open checklist items.'}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {canCreate && <button
            onClick={() => navigate('/tasks?create=true')}
            className="flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition shadow-sm"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Create Task</span>
          </button>}
        </div>
      </div>

      {/* Statutory Compliance Radar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-800">
              Statutory Compliance Calendar & Due Date Horizon
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">Indian CA / CS Statutory Calendar</span>
        </div>

        {calendarError ? (
          <p role="alert" className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2">{calendarError}</p>
        ) : events.length === 0 ? (
          <p className="text-xs text-slate-500 py-2">
            No calendar items are enabled.{isAdmin && <> Add them in <button onClick={() => navigate('/settings')} className="text-emerald-700 font-semibold hover:underline">Settings</button>.</>}
          </p>
        ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {events.map((evt) => {
            const st = EVENT_STYLE[evt.state] || EVENT_STYLE.normal;
            const hint = evt.state === 'due_today' ? 'Due today' : evt.state === 'due_soon'
              ? `Due in ${evt.days_left} day${evt.days_left === 1 ? '' : 's'}` : '';
            return (
            <div
              key={evt.id}
              className={`p-2.5 rounded-lg border transition flex items-start justify-between ${st.card}`}
            >
              <div>
                <div className="flex items-center gap-1.5">
                  <span className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${st.code}`}>
                    {evt.code}
                  </span>
                  <span className="text-xs font-semibold text-slate-800">{evt.title}</span>
                </div>
                {evt.description && <p className="text-[11px] text-slate-500 mt-1 leading-tight">{evt.description}</p>}
              </div>
              <div className="text-right shrink-0 ml-2">
                <span title={evt.next_due_date ? `Next due: ${fmtDate(evt.next_due_date)}` : ''}
                  className={`inline-block text-[10px] font-semibold border px-1.5 py-0.5 rounded ${st.chip}`}>
                  {evt.due_text}
                </span>
                {hint && <p className={`text-[10px] font-bold mt-1 ${evt.state === 'due_today' ? 'text-red-700' : 'text-orange-700'}`}>{hint}</p>}
              </div>
            </div>
            );
          })}
        </div>
        )}
      </div>

      {/* Metric Tiles Grid */}
      {loadError && (
        <div role="alert" className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-sm flex items-center justify-between gap-3">
          <span>{loadError}</span>
          <button onClick={fetchDashboardData} className="text-xs font-semibold underline">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map(n => (
            <div key={n} className="h-28 bg-slate-100 animate-pulse rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-4 gap-4">
          {tiles.map((tile, i) => {
            const Icon = tile.icon;
            return (
              <div
                key={i}
                onClick={() => handleTileClick(tile.filter, (tile as any).mine)}
                className={`p-5 rounded-xl border bg-white ${tile.border} hover:shadow-md transition cursor-pointer flex flex-col justify-between group relative`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      {tile.label}
                    </span>
                    <span title={tile.tooltip} className="text-slate-400 hover:text-slate-600">
                      <HelpCircle className="w-3 h-3" />
                    </span>
                  </div>
                  <div className={`p-2 rounded-lg ${tile.bg} ${tile.color} group-hover:scale-110 transition shadow-sm`}>
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-4 flex items-baseline justify-between">
                  <span className="text-3xl font-extrabold text-slate-900 tracking-tight">
                    {tile.value}
                  </span>
                  <span className="text-xs text-slate-400 group-hover:text-emerald-600 transition flex items-center font-medium">
                    View list →
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Urgent Attention Watchlist */}
      {urgentTasks.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Flame className="w-4 h-4 text-rose-600" />
              <h3 className="font-bold text-sm text-slate-900">Urgent Priority & Upcoming Deadlines</h3>
            </div>
            <button
              onClick={() => navigate('/tasks')}
              className="text-xs text-emerald-700 font-semibold hover:underline flex items-center gap-1"
            >
              <span>View All Tasks</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {upcomingError && <p role="alert" className="m-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2">{upcomingError}</p>}
            {urgentTasks.map(t => {
              const isOverdue = !!t.is_overdue || (t.due_date && t.due_date < localToday());
              return (
                <div
                  key={t.id}
                  onClick={() => setSelectedTaskId(t.id)}
                  className="p-3.5 hover:bg-slate-50 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                >
                  <div className="flex items-center space-x-3">
                    <span className="font-mono text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                      {t.task_number}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{t.client_name}</p>
                      <p className="text-xs text-slate-500">{t.task_type_name}</p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-4 self-end sm:self-auto text-xs">
                    <span className="text-slate-500 font-medium">
                      Assignee: <strong className="text-slate-700">{t.assigned_user_name || 'Unassigned Pool'}</strong>
                    </span>
                    <span className={`px-2 py-0.5 rounded-full font-semibold ${
                      isOverdue
                        ? 'bg-rose-100 text-rose-800 border border-rose-200'
                        : 'bg-slate-100 text-slate-700'
                    }`}>
                      {t.due_date ? `Due ${fmtDate(t.due_date)}` : 'No due date'}
                    </span>
                    <button className="text-xs text-emerald-700 font-semibold hover:underline flex items-center gap-0.5">
                      Open <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Task Detail Modal */}
      {selectedTaskId && (
        <TaskDetailPage
          taskId={selectedTaskId}
          onClose={() => setSelectedTaskId(null)}
          onUpdated={() => {
            fetchDashboardData();
          }}
        />
      )}
    </div>
  );
};
