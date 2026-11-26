import React, { useEffect, useState, useMemo } from 'react';
import { api, errorMessage } from '../api/client';
import { ClientDetailDialog, ClientGroupsDialog } from '../components/ClientDetailDialog';
import { useAuth } from '../context/AuthContext';
import {
  Plus, Search, Eye, Shield, Building2, User, Upload,
  Download, X, Copy, Check, AlertCircle, HelpCircle,
  FileSpreadsheet, Sparkles, Filter, Trash2
} from 'lucide-react';

const PAN_REVEAL_PRESETS = [
  'ITR E-Filing & Verification',
  'ROC / MCA Annual Compliance',
  'GST Notice / Scrutiny Response',
  'Form 15CA/CB Certification',
  'Bank Credit Facility / Loan Dossier',
  'Faceless Assessment Submission',
];

export const ClientsPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.system_role === 'superadmin' || user?.system_role === 'admin';

  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [entityFilter, setEntityFilter] = useState('all');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);

  // PAN Reveal Modal State
  const [revealClient, setRevealClient] = useState<any | null>(null);
  const [revealReason, setRevealReason] = useState('');
  const [revealedPan, setRevealedPan] = useState<string | null>(null);
  const [revealLoading, setRevealLoading] = useState(false);
  const [revealError, setRevealError] = useState('');
  const [copiedPan, setCopiedPan] = useState(false);

  // New Client inputs
  const [name, setName] = useState('');
  const [clientType, setClientType] = useState('company');
  const [pan, setPan] = useState('');
  const [gstin, setGstin] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [formError, setFormError] = useState('');

  // Delete Client State
  const [clientToDelete, setClientToDelete] = useState<any | null>(null);
  const [deleteError, setDeleteError] = useState('');

  // Server-side search and paging: works with thousands of clients (old code loaded only 25)
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const PAGE_SIZE = 50;

  const [openClientId, setOpenClientId] = useState<string | null>(null);
  const [showGroups, setShowGroups] = useState(false);

  const fetchClients = (targetPage = page) => {
    setLoading(true);
    setListError('');
    const q = new URLSearchParams({ page: String(targetPage), page_size: String(PAGE_SIZE) });
    if (searchQuery.trim()) q.set('search', searchQuery.trim());
    if (entityFilter !== 'all') q.set('client_type', entityFilter);
    api.get(`/api/v1/clients/?${q.toString()}`)
      .then(res => {
        setClients(res.results || []);
        setCount(res.count || 0);
        setTotalPages(res.total_pages || 1);
      })
      .catch(err => { console.error('[clients] list failed', err); setClients([]); setListError(errorMessage(err, 'Could not load clients.')); })
      .finally(() => setLoading(false));
  };

  // Re-query 350 ms after typing stops, or at once when the type filter changes
  useEffect(() => {
    const t = window.setTimeout(() => { setPage(1); fetchClients(1); }, 350);
    return () => window.clearTimeout(t);
  }, [searchQuery, entityFilter]);

  const goToPage = (p: number) => {
    setPage(p);
    fetchClients(p);
  };

  const filteredClients = clients;

  // Handle PAN input with 4th character auto-detection
  const handlePanChange = (val: string) => {
    const clean = val.toUpperCase().slice(0, 10);
    setPan(clean);
    if (clean.length >= 4) {
      const fourthChar = clean[3];
      if (fourthChar === 'P') setClientType('individual');
      else if (fourthChar === 'C') setClientType('company');
      else if (fourthChar === 'F') setClientType('partnership');
      else if (fourthChar === 'H') setClientType('huf');
      else if (fourthChar === 'T') setClientType('trust');
      else if (fourthChar === 'A' || fourthChar === 'B') setClientType('aop');
    }
  };

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    try {
      await api.post('/api/v1/clients/', {
        name,
        client_type: clientType,
        pan: pan || undefined,
        gstin: gstin || undefined,
        email,
        phone,
      });
      setShowCreateModal(false);
      setName('');
      setPan('');
      setGstin('');
      setEmail('');
      setPhone('');
      fetchClients();
    } catch (err: any) {
      setFormError(errorMessage(err, 'Something went wrong. Please try again.'));
    }
  };

  const handleImportSpreadsheet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFile) return;
    setImportLoading(true);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', importFile);
      const res = await api.post('/api/v1/clients/import_spreadsheet/', formData);
      setImportResult(res);
      fetchClients();
    } catch (err: any) {
      setImportResult({ errors: [{ row: 0, error: err.error || 'Import failed' }], imported_count: 0 });
    } finally {
      setImportLoading(false);
    }
  };

  const openRevealModal = (client: any) => {
    setRevealClient(client);
    setRevealReason('');
    setRevealedPan(null);
    setRevealError('');
    setCopiedPan(false);
  };

  const submitRevealPan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!revealReason.trim() || revealReason.trim().length < 3) {
      setRevealError('Please provide a specific audit reason (minimum 3 characters).');
      return;
    }
    setRevealLoading(true);
    setRevealError('');
    try {
      const res = await api.post(`/api/v1/clients/${revealClient.id}/reveal_pan/`, {
        reason: revealReason.trim(),
      });
      setRevealedPan(res.pan);
    } catch (err: any) {
      setRevealError(errorMessage(err, 'Failed to decrypt PAN'));
    } finally {
      setRevealLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedPan(true);
    setTimeout(() => setCopiedPan(false), 2500);
  };

  const handleDeleteClient = async () => {
    if (!clientToDelete) return;
    setDeleteError('');
    try {
      await api.delete(`/api/v1/clients/${clientToDelete.id}/`);
      setClientToDelete(null);
      fetchClients();
    } catch (err: any) {
      setDeleteError(errorMessage(err, 'Cannot delete client. Ensure no active tasks belong to this client.'));
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Clients Directory</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage practice clients, AES-256 masked PANs, GSTINs, and compliance contacts.
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {isAdmin && (
            <button onClick={() => setShowGroups(true)}
              className="flex items-center space-x-2 border border-slate-300 hover:bg-slate-100 text-slate-700 px-3.5 py-2 rounded-lg text-sm font-semibold">
              <span>Groups</span>
            </button>
          )}
          {isAdmin && (
            <button
              onClick={() => {
                setImportResult(null);
                setImportFile(null);
                setShowImportModal(true);
              }}
              className="flex items-center space-x-2 border border-slate-300 hover:bg-slate-100 text-slate-700 px-3.5 py-2 rounded-lg text-sm font-semibold transition shadow-sm"
            >
              <Upload className="w-4 h-4 text-slate-500" />
              <span>Import CSV</span>
            </button>
          )}
          {isAdmin && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>New Client</span>
          </button>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search client name, GSTIN, email, phone or full PAN"
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
            <span>Entity:</span>
          </div>
          <select
            value={entityFilter}
            onChange={e => setEntityFilter(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-emerald-500"
          >
            <option value="all">All Entity Types</option>
            <option value="company">Company</option>
            <option value="individual">Individual</option>
            <option value="partnership">Partnership Firm</option>
            <option value="llp">LLP</option>
            <option value="huf">HUF</option>
            <option value="trust">Trust / Society</option>
          </select>
          <span className="text-xs text-slate-400 font-medium shrink-0">
            {count} client{count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Clients Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading clients directory...</div>
        ) : listError ? (
          <div role="alert" className="m-4 p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-800 text-sm flex items-center justify-between gap-3">
            <span>{listError}</span>
            <button type="button" onClick={() => fetchClients()} className="text-xs px-2.5 py-1 rounded-lg border border-rose-300 font-semibold hover:bg-rose-100">Try again</button>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <h4 className="font-semibold text-slate-700">No matching clients found</h4>
            <p className="text-xs text-slate-400 mt-1">
              Try adjusting your search query or entity filter.
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 text-xs uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Client Legal Name</th>
                <th className="px-5 py-3">Entity Type</th>
                <th className="px-5 py-3">PAN (Masked)</th>
                <th className="px-5 py-3">GSTIN</th>
                <th className="px-5 py-3">Contact</th>
                <th className="px-5 py-3">State</th>
                {isAdmin && <th className="px-5 py-3 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredClients.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50/80 transition">
                  <td className="px-5 py-3.5 font-semibold text-slate-900">
                    <div className="flex items-center gap-2">
                      <button type="button" onClick={() => setOpenClientId(c.id)} className="text-left hover:text-emerald-700 hover:underline">{c.name}</button>
                      {!c.is_active && <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 rounded">Inactive</span>}
                      {c.is_blocked_for_new_tasks && <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 rounded">Blocked</span>}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 capitalize">
                      {c.client_type}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 font-mono text-xs font-semibold text-slate-700">
                    {c.pan_masked ? (
                      <span className="bg-slate-100 px-2 py-1 rounded text-slate-800 tracking-wider">
                        {c.pan_masked}
                      </span>
                    ) : (
                      <span className="text-slate-400 font-sans italic">Not provided</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-600">
                    {c.gstin ? (
                      <span className="bg-slate-100/70 px-1.5 py-0.5 rounded tracking-wide">
                        {c.gstin}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-600">
                    <div>{c.email || '-'}</div>
                    <div className="text-slate-400 font-mono">{c.phone || ''}</div>
                  </td>
                  <td className="px-5 py-3.5 text-xs font-semibold text-slate-500">
                    {c.state_code || '-'}
                  </td>
                  {isAdmin && (
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        {c.pan_masked && (
                          <button
                            onClick={() => openRevealModal(c)}
                            title="Reveal full PAN with audit logging (§2.4)"
                            className="text-xs text-slate-600 hover:text-emerald-700 border border-slate-200 hover:border-emerald-300 hover:bg-emerald-50 px-2.5 py-1 rounded-lg font-medium inline-flex items-center gap-1 transition"
                          >
                            <Eye className="w-3.5 h-3.5 text-emerald-600" />
                            <span>Reveal PAN</span>
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setClientToDelete(c);
                            setDeleteError('');
                          }}
                          title="Delete client"
                          className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
            </div>
            <div className="px-5 py-3 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Showing {count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, count)} of {count} clients</span>
              <span className="flex items-center gap-2">
                <button disabled={page <= 1} onClick={() => goToPage(page - 1)} className="px-2.5 py-1 border border-slate-300 rounded-md bg-white disabled:opacity-40">Previous</button>
                <span>Page {page} of {totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => goToPage(page + 1)} className="px-2.5 py-1 border border-slate-300 rounded-md bg-white disabled:opacity-40">Next</button>
              </span>
              <span className="text-[11px] text-slate-400">All PANs are AES-256 encrypted at rest (§2.4)</span>
            </div>
          </>
        )}
      </div>

      {/* Admin PAN Reveal Modal */}
      {revealClient && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/60 backdrop-blur-2xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start justify-between border-b pb-3">
              <div>
                <div className="flex items-center space-x-2">
                  <Shield className="w-5 h-5 text-emerald-600" />
                  <h3 className="text-lg font-bold text-slate-900">Admin PAN Decryption</h3>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Client: <strong className="text-slate-800">{revealClient.name}</strong> ({revealClient.pan_masked})
                </p>
              </div>
              <button
                onClick={() => setRevealClient(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Security Compliance (§2.4):</p>
                <p className="mt-0.5 text-amber-800">
                  Revealing the full plain PAN is logged permanently in the firm security audit log with your user identity and timestamp.
                </p>
              </div>
            </div>

            {!revealedPan ? (
              <form onSubmit={submitRevealPan} className="space-y-4">
                {revealError && (
                  <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs font-medium border border-red-200">
                    {revealError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Quick Audit Reason Presets (Click to apply):
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {PAN_REVEAL_PRESETS.map((p, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => setRevealReason(p)}
                        className={`text-[11px] px-2.5 py-1 rounded-full border transition ${
                          revealReason === p
                            ? 'bg-emerald-100 border-emerald-400 text-emerald-800 font-semibold'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>

                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Documented Reason for Decryption *
                  </label>
                  <textarea
                    rows={2}
                    required
                    value={revealReason}
                    onChange={e => setRevealReason(e.target.value)}
                    placeholder="Specify why the unmasked PAN is required for practice filing..."
                    className="w-full text-xs border rounded-lg p-2.5 bg-slate-50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>

                <div className="flex justify-end space-x-3 pt-3 border-t">
                  <button
                    type="button"
                    onClick={() => setRevealClient(null)}
                    className="px-4 py-2 border rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={revealLoading || revealReason.trim().length < 3}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition shadow-sm flex items-center gap-1.5"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>{revealLoading ? 'Decrypting...' : 'Reveal PAN & Log Audit'}</span>
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 pt-2">
                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-center space-y-2">
                  <p className="text-xs font-semibold text-emerald-800 uppercase tracking-wider">
                    Full Unmasked PAN
                  </p>
                  <div className="font-mono text-2xl font-extrabold text-emerald-950 tracking-widest selection:bg-emerald-200">
                    {revealedPan}
                  </div>
                  <div className="pt-2">
                    <button
                      onClick={() => copyToClipboard(revealedPan)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition shadow-sm ${
                        copiedPan
                          ? 'bg-emerald-700 text-white'
                          : 'bg-white border border-emerald-300 text-emerald-800 hover:bg-emerald-100'
                      }`}
                    >
                      {copiedPan ? (
                        <>
                          <Check className="w-3.5 h-3.5" />
                          <span>Copied to Clipboard!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy Full PAN</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <p className="text-[11px] text-slate-400 text-center">
                  Audit log record created with reason: "{revealReason}"
                </p>

                <div className="flex justify-end pt-3 border-t">
                  <button
                    onClick={() => setRevealClient(null)}
                    className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold shadow-sm"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Client Confirmation Modal */}
      {clientToDelete && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Delete Client</h3>
            <p className="text-xs text-slate-600">
              Are you sure you want to delete <strong className="text-slate-800">{clientToDelete.name}</strong>?
            </p>
            {deleteError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs border border-red-200">
                {deleteError}
              </div>
            )}
            <div className="flex justify-end space-x-3 pt-3 border-t">
              <button
                type="button"
                onClick={() => setClientToDelete(null)}
                className="px-4 py-2 border rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteClient}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-bold shadow-sm"
              >
                Delete Client
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Client Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
              <h3 className="text-lg font-bold text-slate-900">Add New Practice Client</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs border border-red-200 font-medium">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateClient} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Client Legal Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g. Reliance Industries Limited or Rahul Sharma"
                  className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-slate-700">PAN (AES-256 Encrypted at rest)</label>
                  {pan.length >= 4 && (
                    <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
                      4th Char '{pan[3]}' = {clientType.toUpperCase()}
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  maxLength={10}
                  value={pan}
                  onChange={e => handlePanChange(e.target.value)}
                  placeholder="e.g. ABCDE1234F"
                  className="w-full border rounded-lg p-2.5 font-mono uppercase bg-white tracking-widest focus:ring-1 focus:ring-emerald-500"
                />
                <p className="text-[10px] text-slate-400 mt-1">
                  Entity type is auto-detected from 4th character (P=Individual, C=Company, F=Firm, H=HUF, T=Trust).
                </p>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Entity Type *</label>
                <select
                  value={clientType}
                  onChange={e => setClientType(e.target.value)}
                  className="w-full border rounded-lg p-2.5 bg-white capitalize focus:ring-1 focus:ring-emerald-500"
                >
                  <option value="company">Company (Pvt Ltd / Public Ltd)</option>
                  <option value="llp">LLP (Limited Liability Partnership)</option>
                  <option value="partnership">Partnership Firm</option>
                  <option value="individual">Individual / Proprietorship</option>
                  <option value="huf">HUF (Hindu Undivided Family)</option>
                  <option value="trust">Trust / Society / AOP</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">GSTIN (15 Digits)</label>
                <input
                  type="text"
                  maxLength={15}
                  value={gstin}
                  onChange={e => setGstin(e.target.value.toUpperCase())}
                  placeholder="e.g. 27ABCDE1234F1Z5"
                  className="w-full border rounded-lg p-2.5 font-mono uppercase bg-white tracking-wider focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Primary Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="accounts@client.com"
                    className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Phone / Mobile</label>
                  <input
                    type="text"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="w-full border rounded-lg p-2.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border rounded-lg text-slate-600 hover:bg-slate-50 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold shadow-sm"
                >
                  Save Client
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Import Spreadsheet Modal */}
      {showImportModal && (
        <div className="fixed inset-0 !mt-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
              <h3 className="text-lg font-bold text-slate-900">Import Clients Spreadsheet</h3>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg text-xs text-slate-600 space-y-2 border">
              <p>Download our pre-formatted spreadsheet template with Indian PAN & GSTIN columns:</p>
              <a
                href="/api/v1/clients/download_template/"
                className="inline-flex items-center gap-1.5 text-emerald-700 font-semibold hover:underline"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download Sample CSV Template</span>
              </a>
            </div>

            {importResult && (
              <div className={`p-3 rounded-lg text-xs space-y-1 ${importResult.errors?.length > 0 ? 'bg-amber-50 text-amber-900 border border-amber-200' : 'bg-emerald-50 text-emerald-900 border border-emerald-200'}`}>
                <div className="font-bold">
                  Imported {importResult.imported_count} clients successfully!
                </div>
                {importResult.errors?.map((err: any, i: number) => (
                  <div key={i} className="text-red-600">Row {err.row}: {err.error}</div>
                ))}
              </div>
            )}

            <form onSubmit={handleImportSpreadsheet} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Select CSV or XLSX file</label>
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  required
                  onChange={e => setImportFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-3 border-t">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 border rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={importLoading || !importFile}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-sm"
                >
                  {importLoading ? 'Importing...' : 'Upload & Process'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {openClientId && (
        <ClientDetailDialog clientId={openClientId} canEdit={isAdmin} onClose={() => setOpenClientId(null)} onChanged={() => fetchClients()} />
      )}
      {showGroups && <ClientGroupsDialog onClose={() => setShowGroups(false)} />}
    </div>
  );
};
