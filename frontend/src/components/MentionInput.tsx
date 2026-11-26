import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { AtSign, Shield, Briefcase } from 'lucide-react';

export interface MentionableUser {
  id: string;
  full_name: string;
  email: string;
  designation?: string;
  system_role?: string;
}

interface MentionInputProps {
  value: string;
  onChange: (value: string) => void;
  onMentionsChange?: (mentionIds: string[]) => void;
  placeholder?: string;
  className?: string;
  onSubmit?: () => void;
}

export const MentionInput: React.FC<MentionInputProps> = ({
  value,
  onChange,
  onMentionsChange,
  placeholder = 'Write a comment or mention @team-member...',
  className = '',
  onSubmit,
}) => {
  const [users, setUsers] = useState<MentionableUser[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [filterQuery, setFilterQuery] = useState('');
  const [mentionStartIndex, setMentionStartIndex] = useState<number>(-1);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [trackedMentions, setTrackedMentions] = useState<Set<string>>(new Set());
  const [dropdownPlacement, setDropdownPlacement] = useState<'top' | 'bottom'>('top');

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isMounted = true;
    api.get('/api/v1/accounts/users/mentionable/')
      .then((res: any) => {
        if (isMounted && Array.isArray(res)) {
          setUsers(res);
        }
      })
      .catch((err) => {
        console.error('Failed to load mentionable users:', err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Click outside to dismiss suggestions
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    if (showSuggestions) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSuggestions]);

  // Dynamically calculate whether dropdown should open above or below
  useEffect(() => {
    if (showSuggestions && inputRef.current) {
      const rect = inputRef.current.getBoundingClientRect();
      // If distance from input top to viewport/container top is less than 240px, open downwards
      if (rect.top < 250) {
        setDropdownPlacement('bottom');
      } else {
        setDropdownPlacement('top');
      }
    }
  }, [showSuggestions, filterQuery]);

  const filteredUsers = users.filter((u) => {
    const q = filterQuery.toLowerCase();
    return (
      u.full_name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.designation && u.designation.toLowerCase().includes(q))
    );
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVal = e.target.value;
    onChange(newVal);

    const cursor = e.target.selectionStart || 0;
    const textBeforeCursor = newVal.slice(0, cursor);

    // Look for @ followed by characters up to the cursor
    const match = textBeforeCursor.match(/@([a-zA-Z0-9._-]*)$/);

    if (match) {
      setMentionStartIndex(match.index!);
      setFilterQuery(match[1]);
      setShowSuggestions(true);
      setSelectedIndex(0);
    } else {
      setShowSuggestions(false);
    }
  };

  const selectUser = (user: MentionableUser) => {
    if (!inputRef.current) return;

    const cursor = inputRef.current.selectionStart || value.length;
    const beforeMention = value.slice(0, mentionStartIndex);
    const afterCursor = value.slice(cursor);

    // Insert @FullName with trailing space
    const mentionText = `@${user.full_name} `;
    const nextValue = beforeMention + mentionText + afterCursor;

    onChange(nextValue);

    // Track user ID
    const updated = new Set(trackedMentions);
    updated.add(user.id);
    setTrackedMentions(updated);
    if (onMentionsChange) {
      onMentionsChange(Array.from(updated));
    }

    setShowSuggestions(false);

    // Reposition cursor after the mention
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        const nextPos = beforeMention.length + mentionText.length;
        inputRef.current.setSelectionRange(nextPos, nextPos);
      }
    }, 10);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showSuggestions && filteredUsers.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredUsers.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredUsers.length) % filteredUsers.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        selectUser(filteredUsers[selectedIndex]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSuggestions(false);
        return;
      }
    } else if (e.key === 'Enter' && !e.shiftKey) {
      if (onSubmit) {
        e.preventDefault();
        onSubmit();
      }
    }
  };

  const triggerMentionPrompt = () => {
    if (!inputRef.current) return;
    const cursor = inputRef.current.selectionStart || value.length;
    const newVal = value.slice(0, cursor) + '@' + value.slice(cursor);
    onChange(newVal);
    setMentionStartIndex(cursor);
    setFilterQuery('');
    setShowSuggestions(true);
    setSelectedIndex(0);

    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        inputRef.current.setSelectionRange(cursor + 1, cursor + 1);
      }
    }, 10);
  };

  return (
    <div className="relative w-full" ref={containerRef}>
      <div className="relative flex items-center">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={`w-full pr-9 pl-3 py-2 text-xs border rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white text-slate-800 ${className}`}
        />
        <button
          type="button"
          onClick={triggerMentionPrompt}
          title="Mention a staff member (@)"
          className="absolute right-2 text-slate-400 hover:text-emerald-600 transition p-1 rounded"
        >
          <AtSign className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Suggestion Popover Dropdown - Intelligently positions above or below */}
      {showSuggestions && (
        <div
          ref={dropdownRef}
          className={`absolute left-0 w-80 max-h-56 bg-white rounded-xl shadow-2xl border border-slate-200 overflow-y-auto z-50 divide-y divide-slate-100 animate-in fade-in zoom-in-95 duration-100 ${
            dropdownPlacement === 'top'
              ? 'bottom-full mb-1.5'
              : 'top-full mt-1.5'
          }`}
        >
          <div className="px-3 py-1.5 bg-slate-50 text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-between sticky top-0 z-10 border-b border-slate-100">
            <span>Mention staff member</span>
            <span className="text-slate-400 font-normal">↑↓ to navigate, Enter to select</span>
          </div>

          {filteredUsers.length === 0 ? (
            <div className="p-3 text-xs text-slate-400 text-center">
              No matching staff found for "{filterQuery}"
            </div>
          ) : (
            filteredUsers.map((u, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={u.id}
                  onClick={() => selectUser(u)}
                  className={`p-2.5 cursor-pointer flex items-center justify-between transition ${
                    isSelected ? 'bg-emerald-50/80 text-emerald-900' : 'hover:bg-slate-50 text-slate-800'
                  }`}
                >
                  <div className="flex items-center space-x-2.5">
                    <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center shrink-0">
                      {u.full_name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="text-xs font-semibold flex items-center gap-1.5">
                        {u.full_name}
                        {u.system_role === 'admin' || u.system_role === 'superadmin' ? (
                          <span className="text-[10px] px-1.5 py-0.2 rounded font-medium bg-amber-100 text-amber-800 flex items-center gap-0.5">
                            <Shield className="w-2.5 h-2.5" /> {u.system_role}
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[11px] text-slate-400">{u.email}</div>
                    </div>
                  </div>
                  {u.designation && (
                    <span className="text-[10px] text-slate-500 font-medium bg-slate-100 px-1.5 py-0.5 rounded shrink-0">
                      {u.designation}
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

export const FormattedCommentText: React.FC<{ text: string }> = ({ text }) => {
  if (!text) return null;

  // Regex to match @mentions: @word or @word word
  const parts = text.split(/(@[A-Za-z0-9._-]+(?:\s[A-Za-z0-9._-]+)?)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('@')) {
          return (
            <span
              key={i}
              className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs font-bold bg-emerald-100 text-emerald-800 rounded-md font-mono"
            >
              {part}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
};
