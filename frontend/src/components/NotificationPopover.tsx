import React, { useEffect, useState, useRef } from 'react';
import { api, errorMessage } from '../api/client';
import { fmtDate } from '../utils/format';
import { Bell, CheckCheck, ExternalLink, MessageSquare, UserCheck, AlertTriangle, Layers, Clock } from 'lucide-react';

interface NotificationItem {
  id: string;
  kind: string;
  task: string | null;
  task_number: string;
  can_open?: boolean;
  link?: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
}

interface NotificationPopoverProps {
  onSelectTask?: (taskId: string) => void;
}

export const NotificationPopover: React.FC<NotificationPopoverProps> = ({ onSelectTask }) => {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = () => {
    api.get('/api/v1/notifications/unread_count/')
      .then(res => setUnreadCount(res.unread_count))
      .catch(() => {});
  };

  const [popError, setPopError] = useState('');
  const fetchNotifications = () => {
    setLoading(true);
    setPopError('');
    api.get('/api/v1/notifications/')
      .then(res => {
        const list = Array.isArray(res) ? res : res.results || [];
        setNotifications(list);
      })
      .catch(err => { console.error('[notifications] list failed', err); setPopError(errorMessage(err, 'Could not load notifications.')); })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchUnreadCount();
    // Poll every 45s for fresh notifications
    const interval = setInterval(fetchUnreadCount, 45000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (open) {
      fetchNotifications();
    }
  }, [open]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleMarkAllRead = async () => {
    try {
      await api.post('/api/v1/notifications/mark_all_read/');
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error('[notifications] mark all read failed', err);
      setPopError(errorMessage(err, 'Could not mark the notifications as read.'));
    }
  };

  const handleItemClick = async (notif: NotificationItem) => {
    if (!notif.is_read) {
      try {
        await api.post(`/api/v1/notifications/${notif.id}/mark_read/`);
        setNotifications(prev => prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n));
        setUnreadCount(c => Math.max(0, c - 1));
      } catch (err) {
        // Opening the item still works; only the read mark failed
        console.error('[notifications] mark read failed', err);
      }
    }
    if (!notif.task && (notif as any).link) {
      // Summary notifications (e.g. "3 tasks due today") open a filtered task list
      setOpen(false);
      console.debug('[notifications] open link', (notif as any).link);
      window.location.href = (notif as any).link;
      return;
    }
    if (notif.task && notif.can_open === false) {
      // e.g. "re-assigned away from you": the reader has no role on the task any more
      console.debug('[notifications] task not accessible any more', notif.task_number);
      return;
    }
    if (notif.task) {
      setOpen(false);
      if (onSelectTask) {
        onSelectTask(notif.task);
      } else {
        window.location.href = `/tasks?taskId=${notif.task}`;
      }
    }
  };

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays < 7) return `${diffDays}d ago`;
      return fmtDate(isoString);
    } catch {
      return '';
    }
  };

  const getKindIcon = (kind: string) => {
    switch (kind) {
      case 'mentioned':
        return <span className="p-1.5 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">@</span>;
      case 'task_assigned':
        return <UserCheck className="w-4 h-4 text-blue-600" />;
      case 'task_pickup':
        return <Layers className="w-4 h-4 text-purple-600" />;
      case 'blocked':
        return <AlertTriangle className="w-4 h-4 text-rose-600" />;
      default:
        return <MessageSquare className="w-4 h-4 text-slate-500" />;
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen(!open)}
        title="Notifications"
        className="relative p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition focus:outline-none focus:ring-2 focus:ring-emerald-500"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-4 h-4 px-1 bg-rose-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-pulse">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden text-left animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="p-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-sm text-slate-900">Notifications</h3>
              {unreadCount > 0 && (
                <span className="text-[11px] font-semibold bg-rose-100 text-rose-700 px-2 py-0.5 rounded-full">
                  {unreadCount} new
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs text-emerald-700 hover:text-emerald-800 font-semibold flex items-center gap-1 hover:underline"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>Mark all read</span>
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
            {popError && (
              <div role="alert" className="m-2 p-2 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{popError}</div>
            )}
            {loading ? (
              <div className="p-6 text-center text-xs text-slate-400">Loading notifications...</div>
            ) : notifications.length === 0 ? (
              <div className="p-8 text-center">
                <CheckCheck className="w-8 h-8 text-emerald-500 mx-auto mb-2 opacity-60" />
                <p className="text-sm font-semibold text-slate-700">All caught up!</p>
                <p className="text-xs text-slate-400 mt-0.5">No notifications right now.</p>
              </div>
            ) : (
              notifications.map(notif => (
                <div
                  key={notif.id}
                  onClick={() => handleItemClick(notif)}
                  className={`p-3.5 hover:bg-slate-50 transition ${notif.can_open === false ? 'cursor-default' : 'cursor-pointer'} flex gap-3 ${
                    !notif.is_read ? 'bg-emerald-50/40' : ''
                  }`}
                >
                  <div className="shrink-0 mt-0.5">
                    {getKindIcon(notif.kind)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className={`text-xs ${!notif.is_read ? 'font-bold text-slate-900' : 'font-medium text-slate-700'} truncate`}>
                        {notif.title}
                      </p>
                      <span className="text-[10px] text-slate-400 shrink-0">
                        {formatTime(notif.created_at)}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">
                      {notif.body}
                    </p>
                    {notif.task_number && notif.can_open === false && (
                      <p className="mt-1.5 text-[10px] text-slate-500">
                        <span className="font-mono font-bold">{notif.task_number}</span> · You no longer have access to this task.
                      </p>
                    )}
                    {notif.task_number && notif.can_open !== false && (
                      <div className="mt-1.5 flex items-center gap-1">
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-emerald-700 bg-emerald-100/70 px-1.5 py-0.5 rounded">
                          {notif.task_number}
                          <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                        </span>
                      </div>
                    )}
                  </div>
                  {!notif.is_read && (
                    <span className="w-2 h-2 rounded-full bg-emerald-600 shrink-0 self-center" />
                  )}
                </div>
              ))
            )}
          </div>

          <div className="p-2.5 bg-slate-50 border-t border-slate-200 text-center">
            <span className="text-[11px] text-slate-400">
              Mention notifications & task alerts update in real-time
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
