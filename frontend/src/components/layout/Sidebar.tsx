import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, CheckSquare, Users, FolderTree,
  BarChart3, UserCheck, Settings, Repeat, X
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const Sidebar: React.FC<{ open?: boolean; onClose?: () => void }> = ({ open = false, onClose }) => {
  const { user } = useAuth();
  const location = useLocation();
  // Close the phone drawer after navigation
  React.useEffect(() => { if (open) onClose?.(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);
  React.useEffect(() => {
    if (!open) return;
    console.info('[sidebar] mobile drawer opened');
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  const isAdmin = user?.system_role === 'superadmin' || user?.system_role === 'admin';

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/tasks', label: 'Tasks', icon: CheckSquare, end: false },
    { to: '/clients', label: 'Clients', icon: Users, end: false },
    { to: '/services', label: 'Service Catalog', icon: FolderTree, end: false },
    ...(isAdmin ? [{ to: '/batches', label: 'Bulk & Recurring', icon: Repeat, end: false }] : []),
    ...(isAdmin ? [{ to: '/reports', label: 'Reports & Analytics', icon: BarChart3, end: false }] : []),
    ...(isAdmin ? [{ to: '/team', label: 'Team Members', icon: UserCheck, end: false }] : []),
    ...(isAdmin ? [{ to: '/settings', label: 'Settings', icon: Settings, end: false }] : []),
  ];

  return (
    <>
    {/* Backdrop for the phone / tablet drawer */}
    {open && <div className="fixed inset-0 !mt-0 bg-slate-900/50 z-40 lg:hidden" onClick={onClose} aria-hidden="true" />}
    <aside className={`w-64 bg-slate-900 text-slate-300 flex flex-col shrink-0 border-r border-slate-800
      fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full'}
      lg:static lg:translate-x-0 lg:z-auto lg:min-h-[calc(100vh-4rem)]`} aria-label="Main navigation">
      <div className="p-3.5 space-y-1 overflow-y-auto">
        <div className="px-3 py-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase flex items-center justify-between">
          Practice Operations
          <button type="button" onClick={onClose} className="lg:hidden p-1 rounded hover:bg-slate-800 text-slate-300" aria-label="Close menu">
            <X className="w-4 h-4" />
          </button>
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                  isActive
                    ? 'bg-emerald-600 text-white shadow-sm font-semibold'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>

      <div className="mt-auto p-4 border-t border-slate-800 text-xs text-slate-400">
        <p className="font-semibold text-slate-300">Phase 1 Active</p>
        <p className="mt-0.5">FirmFlow v1.0 • Ready for CA/CS practice</p>
      </div>
    </aside>
    </>
  );
};
