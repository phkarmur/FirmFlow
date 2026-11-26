import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Search, LogOut, Shield, Menu } from 'lucide-react';
import { NotificationPopover } from '../NotificationPopover';

export const Navbar: React.FC<{ onSearch?: (q: string) => void; onSelectTask?: (taskId: string) => void; onMenu?: () => void }> = ({ onSearch, onSelectTask, onMenu }) => {
  const { user, firm, logout } = useAuth();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchVal, setSearchVal] = useState('');

  const navigate = useNavigate();

  // Keyboard shortcut: '/' focuses search (spec §6.3) - but NOT while the user is typing
  // in another field (dates like 31/07 and "GSTR-1/3B" must still be typeable).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = document.activeElement as HTMLElement | null;
      const typing = !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);
      if (typing) return;
      e.preventDefault();
      searchInputRef.current?.focus();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchVal(e.target.value);
    onSearch?.(e.target.value);
  };

  // Enter = open the task list filtered by the text (task number, title, client, GSTIN, full PAN)
  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchVal.trim();
    console.debug('[search] global search', q);
    navigate(q ? `/tasks?search=${encodeURIComponent(q)}` : '/tasks');
    searchInputRef.current?.blur();
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-3 sm:px-6 flex items-center justify-between sticky top-0 z-30 shadow-sm">
      {/* Brand & Firm Name */}
      <div className="flex items-center space-x-2 sm:space-x-3 shrink-0">
        {onMenu && (
          <button type="button" onClick={onMenu} className="lg:hidden p-2 -ml-1 rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Open menu">
            <Menu className="w-5 h-5" />
          </button>
        )}
        {firm?.logo_url ? (
          <img src={firm.logo_url} alt={`${firm.name} logo`} className="h-9 w-auto max-w-[120px] object-contain"
            onError={() => console.warn('[navbar] logo failed to load', firm.logo_url)} />
        ) : (
          <div className="w-9 h-9 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold tracking-tight text-lg shadow-sm">
            FF
          </div>
        )}
        <div className="hidden sm:block">
          <h1 className="font-semibold text-slate-900 leading-tight flex items-center gap-2">
            FirmFlow
            <span className="text-xs bg-emerald-50 text-emerald-700 font-medium px-2 py-0.5 rounded-full border border-emerald-200">
              CA Practice
            </span>
          </h1>
          <p className="text-xs text-slate-500 font-medium truncate max-w-xs">
            {firm?.name || 'Practice Management'}
          </p>
        </div>
      </div>

      {/* Global Search with '/' Shortcut */}
      <form onSubmit={submitSearch} role="search" className="flex-1 min-w-0 max-w-md lg:max-w-xl mx-2 sm:mx-4 lg:mx-8">
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchVal}
            onChange={handleSearchChange}
            placeholder="Search tasks, clients, GSTIN or full PAN — press Enter"
            aria-label="Search tasks"
            className="w-full pl-9 pr-10 py-1.5 bg-slate-100 hover:bg-slate-50 focus:bg-white text-sm rounded-lg border border-slate-200 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition"
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-slate-400 bg-white px-1.5 py-0.5 rounded border border-slate-200 shadow-sm">
            /
          </kbd>
        </div>
      </form>

      {/* User Actions */}
      <div className="flex items-center space-x-4">
        {/* Interactive Notifications Popover */}
        <NotificationPopover onSelectTask={onSelectTask} />

        {/* User Profile */}
        <div className="flex items-center space-x-3 pl-3 border-l border-slate-200">
          <button type="button" onClick={() => navigate('/profile')} title="My profile" className="hidden md:block text-right hover:opacity-80">
            <p className="text-sm font-semibold text-slate-800 leading-none">{user?.full_name}</p>
            <p className="text-xs text-slate-500 capitalize mt-1 flex items-center justify-end gap-1">
              {user?.system_role === 'superadmin' && <Shield className="w-3 h-3 text-emerald-600" />}
              {user?.system_role}
            </p>
          </button>
          <button
            onClick={() => logout()}
            title="Log Out"
            className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
