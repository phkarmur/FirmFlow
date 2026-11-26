import React, { useEffect, useState } from 'react';
import { api, errorMessage } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { EditUserDialog, MoveTasksDialog, TemporaryPasswordDialog } from '../components/UserManageDialogs';
import {
  UserCheck, Shield, Plus, Mail, Building,
  AlertCircle, Check, X, UserX, Briefcase, Filter, Search
} from 'lucide-react';

export const TeamPage: React.FC = () => {
  const { user: currentUser, firm, refresh } = useAuth();
  const isAdmin = currentUser?.system_role === 'superadmin' || currentUser?.system_role === 'admin';

  const [users, setUsers] = useState<any[]>([]);
  const [branches, setBranches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');

  // Add User Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [systemRole, setSystemRole] = useState<'admin' | 'staff'>('staff');
  const [designation, setDesignation] = useState('');
  const [selectedBranch, setSelectedBranch] = useState('');
  const [formError, setFormError] = useState('');
  const [formLoading, setFormLoading] = useState(false);

  // Status Action Modal State
  const [actionUser, setActionUser] = useState<any | null>(null);
  const [actionError, setActionError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const fetchUsers = () => {
    setLoading(true);
    setListError('');
    Promise.all([
      api.get('/api/v1/accounts/users/?page_size=500'),
      api.get('/api/v1/accounts/branches/'),
    ])
      .then(([usersRes, branchRes]) => {
        setUsers(Array.isArray(usersRes) ? usersRes : usersRes.results || []);
        setBranches(Array.isArray(branchRes) ? branchRes : branchRes.results || []);
      })
      .catch(err => { console.error('[team] list failed', err); setListError(errorMessage(err, 'Could not load team members.')); })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setFormLoading(true);
    try {
      await api.post('/api/v1/accounts/users/', {
        full_name: fullName,
        email: email.toLowerCase(),
        password,
        system_role: systemRole,
        designation: designation || undefined,
        branch_id: selectedBranch || undefined,
      });
      setShowAddModal(false);
      setFullName('');
      setEmail('');
      setPassword('');
      setDesignation('');
      setSelectedBranch('');
      fetchUsers();
    } catch (err: any) {
      setFormError(errorMessage(err, 'Something went wrong. Please try again.'));
    } finally {
      setFormLoading(false);
    }
  };

  const handleToggleActive = async (targetUser: any) => {
    setActionError('');
    setActionLoading(true);
    try {
      await api.patch(`/api/v1/accounts/users/${targetUser.id}/`, {
        is_active: !targetUser.is_active,
      });
      setActionUser(null);
      fetchUsers();
    } catch (err: any) {
      setActionError(errorMessage(err, 'Failed to update user status'));
    } finally {
      setActionLoading(false);
    }
  };

  // Edit / move tasks / deactivate dialogs
  const [editUser, setEditUser] = useState<any | null>(null);
  const [moveDialog, setMoveDialog] = useState<{ user: any; deactivate: boolean } | null>(null);
  const [tempPwUser, setTempPwUser] = useState<any>(null);
  const [pageNotice, setPageNotice] = useState('');
  const actorIsSuperadmin = currentUser?.system_role === 'superadmin';
  const canManage = (u: any) => actorIsSuperadmin || u.system_role !== 'superadmin';

  // Per-user "can create tasks" exception (null = follow firm setting)
  const [permSaving, setPermSaving] = useState<string | null>(null);
  const [permError, setPermError] = useState('');
  const handleCreatePermission = async (targetUser: any, value: string) => {
    const payload = value === 'default' ? null : value === 'allow';
    setPermError('');
    setPermSaving(targetUser.id);
    console.debug('[team] set can_create_tasks', targetUser.email, payload);
    try {
      await api.patch(`/api/v1/accounts/users/${targetUser.id}/`, { can_create_tasks: payload });
      fetchUsers();
      if (targetUser.id === currentUser?.id) refresh();
    } catch (err: any) {
      setPermError(errorMessage(err, 'Could not save the permission.'));
    } finally {
      setPermSaving(null);
    }
  };

  const filteredUsers = users.filter(u => {
    const q = searchQuery.toLowerCase().trim();
    const matchesSearch = !q ||
      u.full_name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.designation && u.designation.toLowerCase().includes(q));

    const matchesRole = roleFilter === 'all' || u.system_role === roleFilter;
    return matchesSearch && matchesRole;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Team & Staff Directory</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage practice partners, senior associates, article assistants, and branch assignments.
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>Add Team Member</span>
          </button>
        )}
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Staff</p>
          <p className="text-2xl font-extrabold text-slate-900 mt-1">{users.length}</p>
        </div>
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Members</p>
          <p className="text-2xl font-extrabold text-emerald-600 mt-1">
            {users.filter(u => u.is_active).length}
          </p>
        </div>
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Firm Admins</p>
          <p className="text-2xl font-extrabold text-blue-600 mt-1">
            {users.filter(u => u.system_role === 'admin' || u.system_role === 'superadmin').length}
          </p>
        </div>
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Staff / Articles</p>
          <p className="text-2xl font-extrabold text-indigo-600 mt-1">
            {users.filter(u => u.system_role === 'staff').length}
          </p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search team by name, email, designation..."
            className="w-full pl-9 pr-8 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          <div className="flex items-center space-x-1.5 text-xs text-slate-500 shrink-0">
            <Filter className="w-3.5 h-3.5" />
            <span>Role:</span>
          </div>
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-emerald-500"
          >
            <option value="all">All Roles</option>
            <option value="superadmin">Superadmin</option>
            <option value="admin">Admin / Partner</option>
            <option value="staff">Staff / Article</option>
          </select>
          <span className="text-xs text-slate-400 font-medium shrink-0">
            {filteredUsers.length} member{filteredUsers.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading team members...</div>
        ) : listError ? (
          <div role="alert" className="m-4 p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-sm flex items-center justify-between gap-3">
            <span>{listError}</span>
            <button type="button" onClick={fetchUsers} className="text-xs px-2.5 py-1 rounded-lg border border-rose-300 font-semibold hover:bg-rose-100">Try again</button>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="p-12 text-center">
            <UserCheck className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <h4 className="font-semibold text-slate-700">No team members match search</h4>
          </div>
        ) : (
          <>
            {pageNotice && (
              <div role="status" className="m-3 p-2.5 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs flex justify-between">
                <span>{pageNotice}</span><button onClick={() => setPageNotice('')} aria-label="Dismiss">×</button>
              </div>
            )}
            {permError && (
              <div role="alert" className="m-3 p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-xs">{permError}</div>
            )}
            <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 text-xs uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Member Name</th>
                <th className="px-5 py-3">System Role</th>
                <th className="px-5 py-3">Designation</th>
                <th className="px-5 py-3">Primary Branch</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3" title="Staff only. Admins can always create tasks.">Can create tasks</th>
                {isAdmin && <th className="px-5 py-3 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredUsers.map((u) => {
                const initials = u.full_name
                  ? u.full_name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
                  : 'U';
                return (
                  <tr key={u.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-full bg-emerald-600 text-white font-bold text-xs flex items-center justify-center shrink-0">
                          {initials}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-900 leading-tight">
                            {u.full_name}
                            {u.id === currentUser?.id && (
                              <span className="ml-2 text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-normal">
                                You
                              </span>
                            )}
                          </p>
                          <p className="text-xs text-slate-400 font-normal">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${
                        u.system_role === 'superadmin'
                          ? 'bg-purple-100 text-purple-800'
                          : u.system_role === 'admin'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-slate-100 text-slate-700'
                      }`}>
                        {u.system_role === 'superadmin' && <Shield className="w-3 h-3 text-purple-600" />}
                        {u.system_role === 'superadmin' ? 'Superadmin' : u.system_role === 'admin' ? 'Admin / Partner' : 'Staff'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-700 font-medium">
                      {u.designation || <span className="text-slate-400 italic">Not set</span>}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-600">
                      {u.user_branches?.[0]?.branch?.name || 'Head Office'}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full ${
                        u.is_active
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                        {u.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-xs">
                      {u.system_role !== 'staff' ? (
                        <span className="text-slate-500">Always (admin)</span>
                      ) : isAdmin ? (
                        <div className="flex flex-col gap-0.5">
                          <select
                            aria-label={`Can ${u.full_name} create tasks`}
                            value={u.can_create_tasks === null || u.can_create_tasks === undefined ? 'default' : u.can_create_tasks ? 'allow' : 'block'}
                            disabled={permSaving === u.id}
                            onChange={e => handleCreatePermission(u, e.target.value)}
                            className="border border-slate-300 rounded-md px-2 py-1 bg-white text-xs focus:ring-2 focus:ring-emerald-500/40"
                          >
                            <option value="default">Firm default ({firm?.staff_can_create_task ? 'allowed' : 'blocked'})</option>
                            <option value="allow">Allow</option>
                            <option value="block">Block</option>
                          </select>
                          <span className={u.effective_can_create_tasks ? 'text-emerald-700' : 'text-slate-500'}>
                            Now: {u.effective_can_create_tasks ? 'can create' : 'cannot create'}
                          </span>
                        </div>
                      ) : (
                        <span>{u.effective_can_create_tasks ? 'Yes' : 'No'}</span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-3.5 text-right whitespace-nowrap space-x-1.5">
                        {canManage(u) && (
                          <button onClick={() => setEditUser(u)}
                            className="text-xs px-2.5 py-1 rounded-lg border font-semibold text-slate-700 border-slate-300 hover:bg-slate-50">Edit</button>
                        )}
                        {canManage(u) && u.is_active && (
                          <button onClick={() => setMoveDialog({ user: u, deactivate: false })}
                            className="text-xs px-2.5 py-1 rounded-lg border font-semibold text-slate-700 border-slate-300 hover:bg-slate-50">Move tasks</button>
                        )}
                        {u.id !== currentUser?.id && canManage(u) && u.is_active && (
                          <button onClick={() => setTempPwUser(u)} title="Make a temporary password for this person"
                            className="text-xs px-2.5 py-1 rounded-lg border font-semibold text-slate-700 border-slate-300 hover:bg-slate-50">Reset password</button>
                        )}
                        {u.id !== currentUser?.id && canManage(u) && (
                          <button
                            onClick={() => {
                              if (u.is_active) {
                                setMoveDialog({ user: u, deactivate: true });   // spec U5: forced re-assign
                              } else {
                                setActionUser(u);
                                setActionError('');
                              }
                            }}
                            className={`text-xs px-2.5 py-1 rounded-lg border font-semibold transition ${
                              u.is_active
                                ? 'text-rose-700 border-rose-200 hover:bg-rose-50'
                                : 'text-emerald-700 border-emerald-200 hover:bg-emerald-50'
                            }`}
                          >
                            {u.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
            </div>
            <div className="px-5 py-3 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Showing {filteredUsers.length} of {users.length} team members</span>
              <span className="text-[11px] text-slate-400">Firm practice hierarchy (Superadmin, Admin, Staff)</span>
            </div>
          </>
        )}
      </div>

      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
              <h3 className="text-lg font-bold text-slate-900">Add Team Member</h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs font-medium border border-red-200">
                {formError}
              </div>
            )}

            <form onSubmit={handleAddUser} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Full Name *</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                  placeholder="e.g. Priya Sharma, CA"
                  className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Email Address *</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="priya@firm.com"
                  className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Initial Password *</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">System Role *</label>
                  <select
                    value={systemRole}
                    onChange={e => setSystemRole(e.target.value as any)}
                    className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="staff">Staff / Article Assistant</option>
                    <option value="admin">Admin / Partner</option>
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Designation</label>
                  <input
                    type="text"
                    value={designation}
                    onChange={e => setDesignation(e.target.value)}
                    placeholder="e.g. Article Assistant, Tax Mgr"
                    className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Branch</label>
                <select
                  value={selectedBranch}
                  onChange={e => setSelectedBranch(e.target.value)}
                  className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                >
                  <option value="">Head Office (Default)</option>
                  {branches.map(b => (
                    <option key={b.id} value={b.id}>{b.name} ({b.city || 'Office'})</option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border rounded-lg text-slate-600 hover:bg-slate-50 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formLoading}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold shadow-sm"
                >
                  {formLoading ? 'Creating Member...' : 'Create Member'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Deactivate / Reactivate User Modal */}
      {actionUser && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">
              {actionUser.is_active ? 'Deactivate Member' : 'Reactivate Member'}
            </h3>
            <p className="text-xs text-slate-600">
              Are you sure you want to {actionUser.is_active ? 'deactivate' : 'reactivate'} <strong className="text-slate-800">{actionUser.full_name}</strong> ({actionUser.email})?
            </p>

            {actionUser.is_active && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-1">
                <p className="font-semibold flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-700" />
                  <span>Statutory Reassignment Guard (Rule U5):</span>
                </p>
                <p className="text-amber-800">
                  Deactivation requires all open assigned tasks to be completed or re-assigned to another team member beforehand.
                </p>
              </div>
            )}

            {actionError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs font-medium border border-red-200">
                {actionError}
              </div>
            )}

            <div className="flex justify-end space-x-3 pt-3 border-t">
              <button
                type="button"
                onClick={() => setActionUser(null)}
                className="px-4 py-2 border rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleToggleActive(actionUser)}
                className={`px-4 py-2 rounded-lg text-xs font-bold shadow-sm text-white ${
                  actionUser.is_active
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {actionLoading ? 'Updating...' : actionUser.is_active ? 'Confirm Deactivation' : 'Confirm Reactivation'}
              </button>
            </div>
          </div>
        </div>
      )}
      {editUser && (
        <EditUserDialog user={editUser} actorIsSuperadmin={actorIsSuperadmin} onClose={() => setEditUser(null)}
          onSaved={() => { setEditUser(null); setPageNotice('Saved.'); fetchUsers(); if (editUser.id === currentUser?.id) refresh(); }} />
      )}
      {tempPwUser && <TemporaryPasswordDialog user={tempPwUser} onClose={() => setTempPwUser(null)} />}
      {moveDialog && (
        <MoveTasksDialog user={moveDialog.user} deactivate={moveDialog.deactivate} staff={users.filter(x => x.is_active)}
          onClose={() => setMoveDialog(null)}
          onDone={(msg) => { setMoveDialog(null); setPageNotice(msg); fetchUsers(); }} />
      )}
    </div>
  );
};
