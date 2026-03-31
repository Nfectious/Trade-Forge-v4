'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth';
import { useToast } from '@/lib/toast';
import api from '@/lib/api';
import StatCard from '@/components/ui/StatCard';
import {
  ResponsiveContainer,
  LineChart, Line,
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import {
  LayoutDashboard,
  Users,
  Trophy,
  Activity,
  Server,
  Mail,
  RefreshCw,
  ShieldOff,
  Menu,
  X,
  TrendingUp,
  BarChart2,
  DollarSign,
  Zap,
  UserCheck,
  Clock,
  Search,
  Database,
  Wifi,
} from 'lucide-react';

// ─── Tab type ─────────────────────────────────────────────────────────────────

type AdminTab = 'overview' | 'users' | 'contests' | 'trades' | 'health' | 'logs';

interface NavItem {
  id: AdminTab;
  label: string;
  icon: React.ReactNode;
}

const NAV: NavItem[] = [
  { id: 'overview',  label: 'Dashboard Overview',  icon: <LayoutDashboard size={18} /> },
  { id: 'users',     label: 'User Management',      icon: <Users      size={18} /> },
  { id: 'contests',  label: 'Contest Management',   icon: <Trophy     size={18} /> },
  { id: 'trades',    label: 'Trade Monitor',        icon: <Activity   size={18} /> },
  { id: 'health',    label: 'System Health',        icon: <Server     size={18} /> },
  { id: 'logs',      label: 'Email Logs',           icon: <Mail       size={18} /> },
];

// ─── Inner sidebar ────────────────────────────────────────────────────────────

function AdminSidebar({
  active,
  setActive,
  collapsed,
  setCollapsed,
}: {
  active: AdminTab;
  setActive: (t: AdminTab) => void;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
}) {
  return (
    <aside
      className="flex flex-col flex-shrink-0 transition-all duration-200"
      style={{
        width: collapsed ? 56 : 220,
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-subtle)',
        minHeight: 0,
      }}
    >
      {/* Collapse toggle */}
      <div
        className="flex items-center justify-between px-3 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        {!collapsed && (
          <span
            className="text-xs font-semibold uppercase tracking-widest"
            style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}
          >
            Admin
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto p-1 rounded transition-colors hover:opacity-70"
          style={{ color: 'var(--text-muted)' }}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <Menu size={16} /> : <X size={16} />}
        </button>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col gap-0.5 p-2 flex-1 overflow-y-auto">
        {NAV.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActive(item.id)}
              title={collapsed ? item.label : undefined}
              className="flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-all text-left"
              style={{
                background: isActive ? 'rgba(59,130,246,0.12)' : 'transparent',
                color: isActive ? 'var(--accent-blue)' : 'var(--text-secondary)',
                border: isActive
                  ? '1px solid rgba(59,130,246,0.25)'
                  : '1px solid transparent',
                justifyContent: collapsed ? 'center' : 'flex-start',
              }}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Footer label */}
      {!collapsed && (
        <div
          className="px-3 py-3 text-xs flex-shrink-0"
          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
        >
          Trade Forge Admin
        </div>
      )}
    </aside>
  );
}

// ─── Loading / access-denied screens ─────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex items-center justify-center flex-1 min-h-0">
      <RefreshCw
        size={28}
        className="animate-spin"
        style={{ color: 'var(--accent-blue)' }}
      />
    </div>
  );
}

function AccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4">
      <ShieldOff size={48} style={{ color: 'var(--accent-red)' }} />
      <div className="text-center">
        <h2
          className="text-xl font-bold"
          style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}
        >
          Access Denied
        </h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Admin privileges required.
        </p>
      </div>
    </div>
  );
}

// ─── Shared confirm dialog ────────────────────────────────────────────────────

function ConfirmDialog({
  title, message, confirmLabel = 'Confirm', danger = false,
  onConfirm, onCancel, loading = false,
}: {
  title: string; message: string; confirmLabel?: string; danger?: boolean;
  onConfirm: () => void; onCancel: () => void; loading?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={!loading ? onCancel : undefined} />
      <div
        className="relative z-10 w-full max-w-sm mx-4 rounded-xl p-6 shadow-2xl"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)' }}
      >
        <h3 className="text-base font-semibold mb-2" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
          {title}
        </h3>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>{message}</p>
        <div className="flex gap-3">
          <button
            onClick={onCancel} disabled={loading}
            className="flex-1 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm} disabled={loading}
            className="flex-1 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-85 disabled:opacity-50 flex items-center justify-center gap-2"
            style={{ background: danger ? 'var(--accent-red)' : 'var(--accent-blue)', color: '#fff' }}
          >
            {loading && <RefreshCw size={13} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Shared skeleton row ──────────────────────────────────────────────────────

function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3">
          {Array.from({ length: cols }).map((_, j) => (
            <div key={j} className="skeleton h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

// ─── Recharts custom tooltip ──────────────────────────────────────────────────

function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-lg"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)' }}
    >
      <p className="mb-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
        </p>
      ))}
    </div>
  );
}

// ─── Overview tab ─────────────────────────────────────────────────────────────

interface OverviewStats {
  total_users: number;
  active_today: number;
  trades_today: number;
  revenue_month_dollars: number;
  contest_counts: Record<string, number>;
  total_volume_dollars: number;
}

interface GrowthPoint  { day: string;  registrations: number }
interface ActivityPoint { hour: string; trade_count: number; volume_dollars: number }
interface LogEntry { id: string; action: string; admin_email: string; target_email: string | null; created_at: string }

function OverviewTab() {
  const [stats,      setStats]      = useState<OverviewStats | null>(null);
  const [growth,     setGrowth]     = useState<GrowthPoint[]>([]);
  const [activity,   setActivity]   = useState<ActivityPoint[]>([]);
  const [logs,       setLogs]       = useState<LogEntry[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchAll = useCallback(async () => {
    const [statsRes, growthRes, activityRes, logsRes] = await Promise.allSettled([
      api.get('/admin/stats/overview'),
      api.get('/admin/stats/user-growth?days=30'),
      api.get('/admin/stats/trading-activity?days=7'),
      api.get('/admin/logs?page=1&limit=10'),
    ]);

    if (statsRes.status    === 'fulfilled') setStats(statsRes.value.data);
    if (growthRes.status   === 'fulfilled') {
      setGrowth((growthRes.value.data as GrowthPoint[]).map(r => ({
        ...r,
        day: new Date(r.day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      })));
    }
    if (activityRes.status === 'fulfilled') {
      setActivity((activityRes.value.data as ActivityPoint[]).map(r => ({
        ...r,
        hour: new Date(r.hour).toLocaleTimeString('en-US', { month: 'short', day: 'numeric', hour: '2-digit' }),
      })));
    }
    if (logsRes.status     === 'fulfilled') setLogs(logsRes.value.data?.logs ?? []);

    setLoading(false);
    setLastRefresh(new Date());
  }, []);

  // Initial load + 30-second poll
  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 30_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const activeContests = stats?.contest_counts?.active ?? 0;

  return (
    <div className="p-6 space-y-6 max-w-7xl">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
            Dashboard Overview
          </h1>
          {lastRefresh && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Last updated {lastRefresh.toLocaleTimeString()} · auto-refreshes every 30s
            </p>
          )}
        </div>
        <button
          onClick={fetchAll}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-70"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard loading={loading} icon={<Users size={16} />}     label="Total Users"        value={stats ? stats.total_users.toLocaleString()                                              : '—'} />
        <StatCard loading={loading} icon={<UserCheck size={16} />} label="Active Today"       value={stats ? stats.active_today.toLocaleString()                                             : '—'} />
        <StatCard loading={loading} icon={<Activity size={16} />}  label="Trades Today"       value={stats ? stats.trades_today.toLocaleString()                                             : '—'} />
        <StatCard loading={loading} icon={<DollarSign size={16}/>} label="Revenue This Month" value={stats ? `$${stats.revenue_month_dollars.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}` : '—'} />
        <StatCard loading={loading} icon={<Trophy size={16} />}    label="Active Contests"    value={loading ? '—' : activeContests.toString()} />
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-2 gap-6">

        {/* User growth */}
        <div className="tf-card p-5">
          <p className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
            User Growth — Last 30 Days
          </p>
          {loading ? (
            <div className="skeleton h-48" />
          ) : growth.length === 0 ? (
            <div className="h-48 flex items-center justify-center">
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No registration data yet</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <LineChart data={growth} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTip />} />
                <Line type="monotone" dataKey="registrations" name="Registrations" stroke="var(--accent-blue)" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: 'var(--accent-blue)' }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Trading volume */}
        <div className="tf-card p-5">
          <p className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
            Trade Volume — Last 7 Days (Hourly)
          </p>
          {loading ? (
            <div className="skeleton h-48" />
          ) : activity.length === 0 ? (
            <div className="h-48 flex items-center justify-center">
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No trading activity yet</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={activity} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTip />} />
                <Bar dataKey="trade_count" name="Trades" fill="var(--accent-violet)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Recent activity */}
      <div className="tf-card overflow-hidden">
        <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
            Recent Admin Activity
          </p>
        </div>
        {loading ? (
          <SkeletonRows rows={6} cols={4} />
        ) : logs.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No admin activity recorded yet</p>
          </div>
        ) : (
          <div className="divide-y" style={{ '--tw-divide-color': 'var(--border-subtle)' } as any}>
            {logs.map(log => (
              <div key={log.id} className="flex items-center gap-4 px-5 py-3 hover:bg-white/[0.02] transition-colors">
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(59,130,246,0.12)', color: 'var(--accent-blue)' }}
                >
                  <Zap size={13} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                    <span className="font-medium">{log.admin_email}</span>
                    {' '}
                    <span style={{ color: 'var(--text-secondary)' }}>performed</span>
                    {' '}
                    <span className="font-medium" style={{ color: 'var(--accent-blue)' }}>{log.action.replace(/_/g, ' ')}</span>
                    {log.target_email && (
                      <> <span style={{ color: 'var(--text-secondary)' }}>on</span>{' '}
                      <span className="font-medium">{log.target_email}</span></>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
                  <Clock size={12} />
                  <span className="text-xs">
                    {new Date(log.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
// ─── Users tab ───────────────────────────────────────────────────────────────

interface AdminUser {
  id: string; email: string; nickname: string | null;
  role: string; status: string; tier: string;
  created_at: string; last_login: string | null; total_trades: number;
}

const TIERS   = ['free', 'pro', 'elite', 'valkyrie'] as const;
const TIER_COLORS: Record<string, string> = {
  free: 'var(--text-muted)', pro: 'var(--accent-blue)',
  elite: 'var(--accent-violet)', valkyrie: 'var(--accent-gold)',
};
const STATUS_COLORS: Record<string, string> = {
  active: 'var(--accent-green)', banned: 'var(--accent-red)',
  suspended: 'var(--accent-gold)', pending_verification: 'var(--text-muted)',
};

function UsersTab() {
  const { addToast } = useToast();
  const [users,        setUsers]        = useState<AdminUser[]>([]);
  const [total,        setTotal]        = useState(0);
  const [page,         setPage]         = useState(1);
  const [search,       setSearch]       = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [tierFilter,   setTierFilter]   = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading,      setLoading]      = useState(true);
  const [selected,     setSelected]     = useState<Set<string>>(new Set());

  // Action state
  type ActionType = 'ban' | 'unban' | 'tier' | 'reset_pw' | 'email_blast';
  const [confirm, setConfirm] = useState<{ type: ActionType; user?: AdminUser } | null>(null);
  const [newTier,  setNewTier]  = useState('');
  const [actioning, setActioning] = useState(false);

  const PER_PAGE = 25;

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  // Reset page when filters change
  useEffect(() => { setPage(1); }, [tierFilter, statusFilter]);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(PER_PAGE) });
      if (debouncedSearch) params.set('search', debouncedSearch);
      if (tierFilter)      params.set('tier',   tierFilter);
      if (statusFilter)    params.set('status', statusFilter);
      const res = await api.get(`/admin/users?${params}`);
      setUsers(res.data.users ?? []);
      setTotal(res.data.total ?? 0);
    } catch {
      addToast('Failed to load users', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, tierFilter, statusFilter, addToast]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // ── actions ──
  async function executeAction() {
    if (!confirm) return;
    setActioning(true);
    try {
      const { type, user } = confirm;
      if (type === 'ban' && user) {
        await api.patch(`/admin/users/${user.id}/ban`);
        addToast(`${user.email} suspended`, 'success');
      } else if (type === 'unban' && user) {
        await api.patch(`/admin/users/${user.id}/unban`);
        addToast(`${user.email} reactivated`, 'success');
      } else if (type === 'tier' && user && newTier) {
        await api.put(`/admin/users/${user.id}/tier`, { tier: newTier });
        addToast(`${user.email} tier → ${newTier}`, 'success');
      } else if (type === 'reset_pw' && user) {
        await api.post('/auth/forgot-password', { email: user.email });
        addToast(`Password reset email sent to ${user.email}`, 'success');
      } else if (type === 'email_blast') {
        // POST to endpoint; gracefully handles if not yet implemented
        try {
          await api.post('/admin/email-blast', { user_ids: Array.from(selected) });
          addToast('Email blast queued', 'success');
        } catch (e: any) {
          if (e?.response?.status === 404) addToast('Email blast endpoint not configured', 'error');
          else throw e;
        }
      }
      setConfirm(null);
      await fetchUsers();
    } catch (e: any) {
      addToast(e?.response?.data?.detail ?? 'Action failed', 'error');
    } finally {
      setActioning(false);
    }
  }

  // ── CSV export ──
  function exportCSV() {
    const headers = ['Email', 'Nickname', 'Tier', 'Status', 'Role', 'Joined', 'Trades'];
    const rows = (selected.size ? users.filter(u => selected.has(u.id)) : users).map(u => [
      u.email, u.nickname ?? '', u.tier, u.status, u.role,
      new Date(u.created_at).toLocaleDateString(), u.total_trades,
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const url  = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a    = Object.assign(document.createElement('a'), { href: url, download: 'users.csv' });
    a.click(); URL.revokeObjectURL(url);
    addToast('CSV exported', 'success');
  }

  // ── select helpers ──
  function toggleSelect(id: string) {
    setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  }
  function toggleAll() {
    setSelected(prev => prev.size === users.length ? new Set() : new Set(users.map(u => u.id)));
  }

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="p-6 space-y-4 max-w-7xl">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
          User Management
          {total > 0 && <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-muted)' }}>({total.toLocaleString()} total)</span>}
        </h1>
        <div className="flex gap-2">
          <button
            onClick={exportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            <Activity size={13} /> Export CSV {selected.size > 0 && `(${selected.size})`}
          </button>
          <button
            onClick={() => { if (selected.size === 0) { addToast('Select users first', 'warning'); return; } setConfirm({ type: 'email_blast' }); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            <Mail size={13} /> Email Blast {selected.size > 0 && `(${selected.size})`}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input
            type="text" placeholder="Search by email or username…"
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 rounded-lg text-sm"
            style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
          />
        </div>
        <select
          value={tierFilter} onChange={e => setTierFilter(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <option value="">All Tiers</option>
          {TIERS.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
        </select>
        <select
          value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="banned">Banned</option>
          <option value="pending_verification">Pending</option>
        </select>
      </div>

      {/* Table */}
      <div className="tf-card overflow-hidden">
        {loading ? (
          <SkeletonRows rows={8} cols={7} />
        ) : users.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Users size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No users match the current filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <th className="px-3 py-3 text-left w-8">
                    <input
                      type="checkbox"
                      checked={selected.size === users.length && users.length > 0}
                      onChange={toggleAll}
                      className="rounded"
                      style={{ accentColor: 'var(--accent-blue)' }}
                    />
                  </th>
                  {['User', 'Tier', 'Status', 'Joined', 'Trades', 'Actions'].map(h => (
                    <th key={h} className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr
                    key={u.id}
                    className="hover:bg-white/[0.02] transition-colors"
                    style={{ borderBottom: '1px solid var(--border-subtle)', background: selected.has(u.id) ? 'rgba(59,130,246,0.04)' : undefined }}
                  >
                    <td className="px-3 py-3">
                      <input
                        type="checkbox" checked={selected.has(u.id)} onChange={() => toggleSelect(u.id)}
                        className="rounded" style={{ accentColor: 'var(--accent-blue)' }}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{u.nickname ?? '—'}</p>
                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{u.email}</p>
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs font-semibold uppercase" style={{ color: TIER_COLORS[u.tier] ?? 'var(--text-muted)' }}>
                        {u.tier}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{
                          background: `${STATUS_COLORS[u.status] ?? 'var(--text-muted)'}18`,
                          color: STATUS_COLORS[u.status] ?? 'var(--text-muted)',
                        }}
                      >
                        {u.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-xs mono" style={{ color: 'var(--text-secondary)' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-3 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {u.total_trades}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1">
                        {/* Change Tier */}
                        <button
                          onClick={() => { setNewTier(u.tier); setConfirm({ type: 'tier', user: u }); }}
                          className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                          style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--accent-blue)' }}
                        >
                          Tier
                        </button>
                        {/* Ban / Unban */}
                        {u.status === 'banned' || u.status === 'suspended' ? (
                          <button
                            onClick={() => setConfirm({ type: 'unban', user: u })}
                            className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                            style={{ background: 'rgba(34,197,94,0.1)', color: 'var(--accent-green)' }}
                          >
                            Restore
                          </button>
                        ) : (
                          <button
                            onClick={() => setConfirm({ type: 'ban', user: u })}
                            className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                            style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)' }}
                          >
                            Suspend
                          </button>
                        )}
                        {/* Reset PW */}
                        <button
                          onClick={() => setConfirm({ type: 'reset_pw', user: u })}
                          className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                          style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--accent-gold)' }}
                        >
                          Reset PW
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && total > PER_PAGE && (
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderTop: '1px solid var(--border-subtle)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Showing {((page - 1) * PER_PAGE) + 1}–{Math.min(page * PER_PAGE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 transition-opacity hover:opacity-70"
                style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
              >
                ← Prev
              </button>
              <span className="px-3 py-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 transition-opacity hover:opacity-70"
                style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Confirm dialogs ── */}
      {confirm?.type === 'ban' && confirm.user && (
        <ConfirmDialog
          danger title="Suspend Account"
          message={`Suspend ${confirm.user.email}? They will lose access immediately.`}
          confirmLabel="Suspend" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.type === 'unban' && confirm.user && (
        <ConfirmDialog
          title="Restore Account"
          message={`Restore access for ${confirm.user.email}?`}
          confirmLabel="Restore" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.type === 'reset_pw' && confirm.user && (
        <ConfirmDialog
          title="Reset Password"
          message={`Send a password reset email to ${confirm.user.email}?`}
          confirmLabel="Send Reset Email" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.type === 'email_blast' && (
        <ConfirmDialog
          title="Send Email Blast"
          message={`Send a bulk email to ${selected.size} selected user${selected.size !== 1 ? 's' : ''}?`}
          confirmLabel="Send" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.type === 'tier' && confirm.user && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setConfirm(null)} />
          <div
            className="relative z-10 w-full max-w-sm mx-4 rounded-xl p-6 shadow-2xl"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)' }}
          >
            <h3 className="text-base font-semibold mb-1" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
              Change Subscription Tier
            </h3>
            <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>{confirm.user.email}</p>
            <select
              value={newTier} onChange={e => setNewTier(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm mb-5"
              style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
            >
              {TIERS.map(t => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirm(null)}
                className="flex-1 py-2 rounded-lg text-sm font-medium"
                style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
              >
                Cancel
              </button>
              <button
                onClick={executeAction} disabled={actioning}
                className="flex-1 py-2 rounded-lg text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
                style={{ background: 'var(--accent-blue)', color: '#fff' }}
              >
                {actioning && <RefreshCw size={13} className="animate-spin" />}
                Update Tier
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
// ─── Contest Management tab ───────────────────────────────────────────────────

interface AdminContest {
  id: string; name: string; description: string | null;
  type: string; status: string; entry_fee: number;
  prize_pool_dollars: number; max_participants: number | null;
  current_participants: number; start_time: string; end_time: string;
  starting_balance: number; prize_distributed: boolean;
}

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
  upcoming:  { bg: 'rgba(59,130,246,0.12)',  color: 'var(--accent-blue)'   },
  active:    { bg: 'rgba(34,197,94,0.12)',   color: 'var(--accent-green)'  },
  completed: { bg: 'rgba(71,85,105,0.2)',    color: 'var(--text-muted)'    },
  cancelled: { bg: 'rgba(239,68,68,0.12)',   color: 'var(--accent-red)'    },
};

function Countdown({ end }: { end: string }) {
  const [label, setLabel] = useState('');
  useEffect(() => {
    function calc() {
      const diff = new Date(end).getTime() - Date.now();
      if (diff <= 0) { setLabel('Ended'); return; }
      const d = Math.floor(diff / 86_400_000);
      const h = Math.floor((diff % 86_400_000) / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      setLabel(d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`);
    }
    calc();
    const id = setInterval(calc, 60_000);
    return () => clearInterval(id);
  }, [end]);
  return <span>{label}</span>;
}

const EMPTY_CONTEST_FORM = {
  name: '', description: '', type: 'free', visibility: 'public',
  entry_fee: 0, prize_pool_dollars: 0, starting_balance_dollars: 100_000,
  max_participants: '', min_participants: 2,
  start_time: '', end_time: '', registration_deadline: '',
  allowed_assets: '', max_trades_per_day: '',
  platform_commission_percent: 10,
};

function ContestsTab() {
  const { addToast } = useToast();
  const [contests,   setContests]   = useState<AdminContest[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [confirm,    setConfirm]    = useState<{ type: 'cancel' | 'force_end'; contest: AdminContest } | null>(null);
  const [actioning,  setActioning]  = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [form,       setForm]       = useState({ ...EMPTY_CONTEST_FORM });
  const [creating,   setCreating]   = useState(false);

  const fetchContests = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const res = await api.get(`/admin/contests${params}`);
      setContests(res.data ?? []);
    } catch {
      addToast('Failed to load contests', 'error');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, addToast]);

  useEffect(() => { fetchContests(); }, [fetchContests]);

  async function executeAction() {
    if (!confirm) return;
    setActioning(true);
    try {
      const { type, contest } = confirm;
      if (type === 'cancel') {
        await api.post(`/admin/contests/${contest.id}/cancel`);
        addToast(`"${contest.name}" cancelled — refunds queued`, 'success');
      } else {
        await api.post(`/admin/contests/${contest.id}/force-end`);
        addToast(`"${contest.name}" force-closed and prizes distributed`, 'success');
      }
      setConfirm(null);
      await fetchContests();
    } catch (e: any) {
      addToast(e?.response?.data?.detail ?? 'Action failed', 'error');
    } finally {
      setActioning(false);
    }
  }

  async function createContest(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/admin/contests', {
        name:          form.name,
        description:   form.description || null,
        type:          form.type,
        visibility:    form.visibility,
        entry_fee:     Number(form.entry_fee),
        prize_pool:    Math.round(Number(form.prize_pool_dollars) * 100),
        starting_balance: Math.round(Number(form.starting_balance_dollars) * 100),
        max_participants:  form.max_participants ? Number(form.max_participants) : null,
        min_participants:  Number(form.min_participants),
        start_time:    form.start_time,
        end_time:      form.end_time,
        registration_deadline: form.registration_deadline || null,
        allowed_assets: form.allowed_assets || null,
        max_trades_per_day: form.max_trades_per_day ? Number(form.max_trades_per_day) : null,
        platform_commission_percent: Number(form.platform_commission_percent),
      });
      addToast(`Contest "${form.name}" created`, 'success');
      setShowCreate(false);
      setForm({ ...EMPTY_CONTEST_FORM });
      await fetchContests();
    } catch (e: any) {
      addToast(e?.response?.data?.detail ?? 'Failed to create contest', 'error');
    } finally {
      setCreating(false);
    }
  }

  function fld(k: keyof typeof form, v: string | number) {
    setForm(f => ({ ...f, [k]: v }));
  }

  return (
    <div className="p-6 space-y-4 max-w-7xl">

      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
          Contest Management
        </h1>
        <div className="flex gap-2 items-center">
          <select
            value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg text-sm"
            style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            <option value="">All Statuses</option>
            <option value="upcoming">Upcoming</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity hover:opacity-85"
            style={{ background: 'var(--accent-blue)', color: '#fff' }}
          >
            + New Contest
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="tf-card overflow-hidden">
        {loading ? (
          <SkeletonRows rows={6} cols={7} />
        ) : contests.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Trophy size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No contests match the current filter</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Contest', 'Entry Fee', 'Participants', 'Prize Pool', 'Time Left', 'Status', 'Actions'].map(h => (
                    <th key={h} className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contests.map(c => {
                  const badge = STATUS_BADGE[c.status] ?? STATUS_BADGE.completed;
                  const canAct = c.status === 'active' || c.status === 'upcoming';
                  return (
                    <tr key={c.id} className="hover:bg-white/[0.02] transition-colors" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td className="px-3 py-3">
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{c.name}</p>
                        <p className="text-xs capitalize" style={{ color: 'var(--text-muted)' }}>{c.type}</p>
                      </td>
                      <td className="px-3 py-3 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {c.entry_fee === 0 ? 'Free' : `$${c.entry_fee.toFixed(2)}`}
                      </td>
                      <td className="px-3 py-3 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {c.current_participants}{c.max_participants ? `/${c.max_participants}` : ''}
                      </td>
                      <td className="px-3 py-3 mono text-xs" style={{ color: c.prize_pool_dollars > 0 ? 'var(--accent-gold)' : 'var(--text-muted)' }}>
                        {c.prize_pool_dollars > 0 ? `$${c.prize_pool_dollars.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td className="px-3 py-3 text-xs mono" style={{ color: 'var(--text-secondary)' }}>
                        {c.status === 'active' ? <Countdown end={c.end_time} /> : c.status === 'upcoming' ? <Countdown end={c.start_time} /> : '—'}
                      </td>
                      <td className="px-3 py-3">
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium capitalize" style={{ background: badge.bg, color: badge.color }}>
                          {c.status}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-1">
                          <a
                            href={`/contests/${c.id}`} target="_blank" rel="noreferrer"
                            className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                            style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--accent-blue)' }}
                          >
                            Board
                          </a>
                          {canAct && (
                            <>
                              <button
                                onClick={() => setConfirm({ type: 'force_end', contest: c })}
                                className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                                style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--accent-gold)' }}
                              >
                                Force End
                              </button>
                              <button
                                onClick={() => setConfirm({ type: 'cancel', contest: c })}
                                className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                                style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)' }}
                              >
                                Cancel
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Action confirm dialogs ── */}
      {confirm?.type === 'cancel' && (
        <ConfirmDialog danger
          title="Cancel Contest + Refund"
          message={`Cancel "${confirm.contest.name}"? All ${confirm.contest.current_participants} participants will be refunded.`}
          confirmLabel="Cancel & Refund" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.type === 'force_end' && (
        <ConfirmDialog
          title="Force Close Contest"
          message={`Immediately finalize "${confirm.contest.name}" and distribute prizes to the current leader?`}
          confirmLabel="Force Close" loading={actioning}
          onConfirm={executeAction} onCancel={() => setConfirm(null)}
        />
      )}

      {/* ── Create contest modal ── */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => !creating && setShowCreate(false)} />
          <div
            className="relative z-10 w-full max-w-2xl mx-4 rounded-xl shadow-2xl overflow-y-auto"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)', maxHeight: '90vh' }}
          >
            <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <h3 className="text-base font-semibold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
                Create New Contest
              </h3>
              <button onClick={() => setShowCreate(false)} style={{ color: 'var(--text-muted)' }} className="hover:opacity-70">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={createContest} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                {/* Name */}
                <div className="col-span-2">
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Contest Name *</label>
                  <input required value={form.name} onChange={e => fld('name', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    placeholder="Weekly Champions"
                  />
                </div>
                {/* Description */}
                <div className="col-span-2">
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Description</label>
                  <textarea value={form.description} onChange={e => fld('description', e.target.value)} rows={2}
                    className="w-full px-3 py-2 rounded-lg text-sm resize-none"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Type */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Type *</label>
                  <select value={form.type} onChange={e => fld('type', e.target.value)} required
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  >
                    <option value="free">Free</option>
                    <option value="paid">Paid</option>
                    <option value="sponsored">Sponsored</option>
                  </select>
                </div>
                {/* Visibility */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Visibility</label>
                  <select value={form.visibility} onChange={e => fld('visibility', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  >
                    <option value="public">Public</option>
                    <option value="private">Private</option>
                  </select>
                </div>
                {/* Entry Fee */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Entry Fee ($)</label>
                  <input type="number" min="0" step="0.01" value={form.entry_fee} onChange={e => fld('entry_fee', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Prize Pool */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Prize Pool ($)</label>
                  <input type="number" min="0" step="0.01" value={form.prize_pool_dollars} onChange={e => fld('prize_pool_dollars', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Starting Balance */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Starting Balance ($)</label>
                  <input type="number" min="100" step="1000" value={form.starting_balance_dollars} onChange={e => fld('starting_balance_dollars', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Commission */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Platform Commission (%)</label>
                  <input type="number" min="0" max="100" step="0.5" value={form.platform_commission_percent} onChange={e => fld('platform_commission_percent', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Max / Min participants */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Max Participants (blank = unlimited)</label>
                  <input type="number" min="2" value={form.max_participants} onChange={e => fld('max_participants', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    placeholder="Unlimited"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Min Participants</label>
                  <input type="number" min="2" value={form.min_participants} onChange={e => fld('min_participants', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                {/* Dates */}
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Start Time *</label>
                  <input required type="datetime-local" value={form.start_time} onChange={e => fld('start_time', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', colorScheme: 'dark' }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>End Time *</label>
                  <input required type="datetime-local" value={form.end_time} onChange={e => fld('end_time', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', colorScheme: 'dark' }}
                  />
                </div>
                {/* Allowed assets */}
                <div className="col-span-2">
                  <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Allowed Assets (comma-separated, blank = all)</label>
                  <input value={form.allowed_assets} onChange={e => fld('allowed_assets', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    placeholder="BTCUSDT,ETHUSDT,SOLUSDT"
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                  style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
                >
                  Cancel
                </button>
                <button type="submit" disabled={creating}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
                  style={{ background: 'var(--accent-blue)', color: '#fff' }}
                >
                  {creating && <RefreshCw size={13} className="animate-spin" />}
                  Create Contest
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Trade Monitor tab ────────────────────────────────────────────────────────

interface PlatformTrade {
  id: string; user_email: string; symbol: string;
  side: string; quantity: number; price: number;
  total_value_dollars: number; pnl_dollars: number | null;
  executed_at: string;
}

function TradeMonitorTab() {
  const { addToast } = useToast();
  const [trades,      setTrades]      = useState<PlatformTrade[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [symbolFilter, setSymbolFilter] = useState('');
  const [sideFilter,  setSideFilter]  = useState('');
  const [userFilter,  setUserFilter]  = useState('');
  const [lastUpdate,  setLastUpdate]  = useState<Date | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (symbolFilter) params.set('symbol', symbolFilter);
      if (sideFilter)   params.set('side',   sideFilter);
      const res = await api.get(`/admin/trades/recent?${params}`);
      setTrades(res.data ?? []);
      setLastUpdate(new Date());
    } catch {
      addToast('Failed to fetch trades', 'error');
    } finally {
      setLoading(false);
    }
  }, [symbolFilter, sideFilter, addToast]);

  // Initial + 10s poll
  useEffect(() => {
    fetchTrades();
    const id = setInterval(fetchTrades, 10_000);
    return () => clearInterval(id);
  }, [fetchTrades]);

  // Client-side user filter (no roundtrip needed)
  const visible = userFilter.trim()
    ? trades.filter(t => t.user_email.toLowerCase().includes(userFilter.toLowerCase()))
    : trades;

  return (
    <div className="p-6 space-y-4 max-w-7xl">

      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
            Trade Monitor
          </h1>
          {lastUpdate && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Last updated {lastUpdate.toLocaleTimeString()} · auto-refreshes every 10s
            </p>
          )}
        </div>
        <button
          onClick={fetchTrades}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-70"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="text" placeholder="Filter by user email…"
          value={userFilter} onChange={e => setUserFilter(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm flex-1 min-w-[160px]"
          style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
        />
        <input
          type="text" placeholder="Symbol (e.g. BTCUSDT)…"
          value={symbolFilter}
          onChange={e => { setSymbolFilter(e.target.value.toUpperCase()); }}
          className="px-3 py-2 rounded-lg text-sm w-44 mono uppercase"
          style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
        />
        <select
          value={sideFilter} onChange={e => setSideFilter(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <option value="">All Sides</option>
          <option value="buy">Buy</option>
          <option value="sell">Sell</option>
        </select>
      </div>

      {/* Table */}
      <div className="tf-card overflow-hidden">
        {loading ? (
          <SkeletonRows rows={10} cols={7} />
        ) : visible.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Activity size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No trades match the current filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Time', 'User', 'Symbol', 'Side', 'Quantity', 'Price', 'Total', 'P&L'].map(h => (
                    <th key={h} className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map(t => {
                  const isBuy = t.side === 'buy';
                  const rowBg = isBuy ? 'rgba(34,197,94,0.03)' : 'rgba(239,68,68,0.03)';
                  return (
                    <tr
                      key={t.id}
                      className="hover:brightness-125 transition-all"
                      style={{ borderBottom: '1px solid var(--border-subtle)', background: rowBg }}
                    >
                      <td className="px-3 py-2.5 text-xs mono" style={{ color: 'var(--text-muted)' }}>
                        {new Date(t.executed_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </td>
                      <td className="px-3 py-2.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        <span className="truncate block max-w-[120px]">{t.user_email}</span>
                      </td>
                      <td className="px-3 py-2.5 font-semibold mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        {t.symbol}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className="px-2 py-0.5 rounded text-xs font-semibold uppercase"
                          style={{
                            background: isBuy ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                            color: isBuy ? 'var(--accent-green)' : 'var(--accent-red)',
                          }}
                        >
                          {t.side}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {t.quantity}
                      </td>
                      <td className="px-3 py-2.5 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        ${t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2.5 mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        ${t.total_value_dollars.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2.5 mono text-xs font-medium"
                        style={{ color: t.pnl_dollars == null ? 'var(--text-muted)' : t.pnl_dollars >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
                      >
                        {t.pnl_dollars == null ? '—' : `${t.pnl_dollars >= 0 ? '+' : ''}$${Math.abs(t.pnl_dollars).toFixed(2)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!loading && visible.length > 0 && (
          <div className="px-4 py-2.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Showing {visible.length} most recent trade{visible.length !== 1 ? 's' : ''} · updates every 10s
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
// ─── System Health tab ───────────────────────────────────────────────────────

type ServiceStatus = 'up' | 'down' | 'stale' | 'live' | 'running' | 'no_heartbeat' | 'unknown' | 'degraded';

interface HealthData {
  database:   { status: ServiceStatus; latency_ms?: number; error?: string };
  redis:      { status: ServiceStatus; latency_ms?: number; used_memory_mb?: number; peak_memory_mb?: number; error?: string };
  price_feed: { status: ServiceStatus; symbols_live?: number; last_update?: string; error?: string };
  scheduler:  { status: ServiceStatus; last_ran?: string; next_run?: string; age_seconds?: number; error?: string };
  server:     { pid?: number; uptime_seconds?: number };
}

function statusColor(s: ServiceStatus | undefined): string {
  if (!s) return 'var(--text-muted)';
  if (s === 'up' || s === 'live' || s === 'running') return 'var(--accent-green)';
  if (s === 'stale' || s === 'no_heartbeat' || s === 'degraded') return 'var(--accent-gold)';
  return 'var(--accent-red)';
}

function statusBg(s: ServiceStatus | undefined): string {
  if (!s) return 'rgba(71,85,105,0.15)';
  if (s === 'up' || s === 'live' || s === 'running') return 'rgba(34,197,94,0.08)';
  if (s === 'stale' || s === 'no_heartbeat' || s === 'degraded') return 'rgba(245,158,11,0.08)';
  return 'rgba(239,68,68,0.08)';
}

function uptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function HealthCard({
  title, status, icon, children,
}: {
  title: string; status: ServiceStatus | undefined; icon: React.ReactNode; children: React.ReactNode;
}) {
  const color = statusColor(status);
  const bg    = statusBg(status);
  return (
    <div
      className="rounded-xl p-5 space-y-3"
      style={{ background: 'var(--bg-card)', border: `1px solid ${color}33` }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span style={{ color }}>{icon}</span>
          <span className="text-sm font-semibold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>{title}</span>
        </div>
        <span
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold capitalize"
          style={{ background: bg, color }}
        >
          <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
          {status ?? 'unknown'}
        </span>
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function HealthRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="mono font-medium" style={{ color: 'var(--text-secondary)' }}>{value}</span>
    </div>
  );
}

function SystemHealthTab() {
  const { addToast }  = useToast();
  const [health, setHealth]       = useState<HealthData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await api.get('/admin/health');
      setHealth(res.data);
      setLastChecked(new Date());
    } catch {
      addToast('Failed to fetch health data', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, 15_000);
    return () => clearInterval(id);
  }, [fetchHealth]);

  const d  = health?.database;
  const r  = health?.redis;
  const pf = health?.price_feed;
  const sc = health?.scheduler;
  const sv = health?.server;

  return (
    <div className="p-6 space-y-5 max-w-4xl">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
            System Health
          </h1>
          {lastChecked && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Last checked {lastChecked.toLocaleTimeString()} · auto-refreshes every 15s
            </p>
          )}
        </div>
        <button
          onClick={fetchHealth}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-70"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">

          {/* Database */}
          <HealthCard title="Database" status={d?.status} icon={<Database size={16} />}>
            <HealthRow label="Response time" value={d?.latency_ms != null ? `${d.latency_ms} ms` : '—'} />
            <HealthRow label="Driver" value="asyncpg (PostgreSQL)" />
            {d?.error && <p className="text-xs" style={{ color: 'var(--accent-red)' }}>{d.error}</p>}
          </HealthCard>

          {/* Redis */}
          <HealthCard title="Redis" status={r?.status} icon={<Server size={16} />}>
            <HealthRow label="Latency" value={r?.latency_ms != null ? `${r.latency_ms} ms` : '—'} />
            <HealthRow label="Memory used" value={r?.used_memory_mb != null ? `${r.used_memory_mb} MB` : '—'} />
            <HealthRow label="Memory peak" value={r?.peak_memory_mb != null ? `${r.peak_memory_mb} MB` : '—'} />
            {r?.error && <p className="text-xs" style={{ color: 'var(--accent-red)' }}>{r.error}</p>}
          </HealthCard>

          {/* Price Feed */}
          <HealthCard title="Price Feed" status={pf?.status} icon={<Activity size={16} />}>
            <HealthRow label="Symbols tracked" value={pf?.symbols_live ?? '—'} />
            <HealthRow label="Last update" value={
              pf?.last_update
                ? new Date(pf.last_update).toLocaleTimeString()
                : '—'
            } />
            {pf?.error && <p className="text-xs" style={{ color: 'var(--accent-red)' }}>{pf.error}</p>}
          </HealthCard>

          {/* Scheduler */}
          <HealthCard title="Scheduler" status={sc?.status} icon={<Clock size={16} />}>
            <HealthRow label="Last ran" value={
              sc?.last_ran ? new Date(sc.last_ran).toLocaleTimeString() : '—'
            } />
            <HealthRow label="Next run" value={
              sc?.next_run ? new Date(sc.next_run).toLocaleTimeString() : '—'
            } />
            <HealthRow label="Heartbeat age" value={
              sc?.age_seconds != null ? `${sc.age_seconds}s ago` : '—'
            } />
            {sc?.error && <p className="text-xs" style={{ color: 'var(--accent-red)' }}>{sc.error}</p>}
          </HealthCard>

          {/* Server */}
          <HealthCard title="Server" status="up" icon={<Zap size={16} />}>
            <HealthRow label="Uptime" value={sv?.uptime_seconds != null ? uptime(sv.uptime_seconds) : '—'} />
            <HealthRow label="PID" value={sv?.pid ?? '—'} />
            <HealthRow label="Runtime" value="FastAPI / Uvicorn" />
          </HealthCard>

          {/* WebSocket */}
          <HealthCard title="WebSocket" status="up" icon={<Wifi size={16} />}>
            <HealthRow label="Price feed" value="ws://…/market/ws/prices" />
            <HealthRow label="Feed status" value={pf?.status === 'live' ? 'Streaming' : 'Stale'} />
            <HealthRow label="Symbols active" value={pf?.symbols_live ?? 0} />
          </HealthCard>

        </div>
      )}
    </div>
  );
}

// ─── Email / Audit Logs tab ───────────────────────────────────────────────────

interface AuditLog {
  id: string; action: string; admin_email: string;
  target_email: string | null; details: Record<string, any> | null;
  created_at: string;
}

const ACTION_COLORS: Record<string, { bg: string; color: string }> = {
  ban_user:        { bg: 'rgba(239,68,68,0.12)',   color: 'var(--accent-red)'    },
  suspend_user:    { bg: 'rgba(239,68,68,0.12)',   color: 'var(--accent-red)'    },
  unsuspend_user:  { bg: 'rgba(34,197,94,0.12)',   color: 'var(--accent-green)'  },
  change_tier:     { bg: 'rgba(59,130,246,0.12)',  color: 'var(--accent-blue)'   },
  grant_currency:  { bg: 'rgba(245,158,11,0.12)',  color: 'var(--accent-gold)'   },
  deduct_currency: { bg: 'rgba(239,68,68,0.12)',   color: 'var(--accent-red)'    },
  contest_adjustment: { bg: 'rgba(139,92,246,0.12)', color: 'var(--accent-violet)' },
  delete_user:     { bg: 'rgba(239,68,68,0.15)',   color: 'var(--accent-red)'    },
  feature_toggle:  { bg: 'rgba(71,85,105,0.2)',    color: 'var(--text-secondary)' },
  grant_achievement: { bg: 'rgba(245,158,11,0.12)', color: 'var(--accent-gold)'  },
};

const LOG_ACTIONS = [
  'ban_user', 'suspend_user', 'unsuspend_user', 'change_tier',
  'grant_currency', 'deduct_currency', 'contest_adjustment',
  'delete_user', 'feature_toggle', 'grant_achievement',
];

function EmailLogsTab() {
  const { addToast }    = useToast();
  const [logs,    setLogs]    = useState<AuditLog[]>([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(1);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState('');
  const [retryTarget,  setRetryTarget]  = useState<AuditLog | null>(null);
  const [retrying,     setRetrying]     = useState(false);

  const PER_PAGE = 25;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/logs?page=${page}&limit=${PER_PAGE}`);
      const all: AuditLog[] = res.data?.logs ?? [];
      const filtered = actionFilter ? all.filter(l => l.action === actionFilter) : all;
      setLogs(filtered);
      setTotal(res.data?.total ?? 0);
    } catch {
      addToast('Failed to load audit logs', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter, addToast]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { setPage(1); }, [actionFilter]);

  async function retryAction() {
    if (!retryTarget) return;
    setRetrying(true);
    try {
      // Re-apply the same action if it was a ban/tier change
      if (retryTarget.action === 'ban_user' && retryTarget.target_email) {
        const userRes = await api.get(`/admin/users?search=${encodeURIComponent(retryTarget.target_email)}&limit=1`);
        const uid = userRes.data?.users?.[0]?.id;
        if (uid) {
          await api.patch(`/admin/users/${uid}/ban`);
          addToast('Action re-applied successfully', 'success');
        } else {
          addToast('Target user not found', 'error');
        }
      } else {
        addToast('Retry not supported for this action type', 'warning');
      }
    } catch (e: any) {
      addToast(e?.response?.data?.detail ?? 'Retry failed', 'error');
    } finally {
      setRetrying(false);
      setRetryTarget(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="p-6 space-y-4 max-w-6xl">

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
            Audit Log
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            All admin actions performed on this platform
          </p>
        </div>
        <select
          value={actionFilter} onChange={e => setActionFilter(e.target.value)}
          className="px-3 py-1.5 rounded-lg text-sm"
          style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          <option value="">All Actions</option>
          {LOG_ACTIONS.map(a => (
            <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </div>

      <div className="tf-card overflow-hidden">
        {loading ? (
          <SkeletonRows rows={8} cols={5} />
        ) : logs.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Mail size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>No audit log entries yet</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              Admin actions will appear here as they are performed
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Time', 'Admin', 'Action', 'Target', 'Details', ''].map(h => (
                    <th key={h} className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map(log => {
                  const badge = ACTION_COLORS[log.action] ?? { bg: 'rgba(71,85,105,0.2)', color: 'var(--text-secondary)' };
                  return (
                    <tr
                      key={log.id}
                      className="hover:bg-white/[0.02] transition-colors"
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                    >
                      <td className="px-3 py-3 text-xs mono" style={{ color: 'var(--text-muted)' }}>
                        {new Date(log.created_at).toLocaleString(undefined, {
                          month: 'short', day: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                        })}
                      </td>
                      <td className="px-3 py-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {log.admin_email}
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className="px-2 py-0.5 rounded-full text-xs font-medium"
                          style={{ background: badge.bg, color: badge.color }}
                        >
                          {log.action.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {log.target_email ?? <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                      <td className="px-3 py-3 text-xs mono max-w-[200px] truncate" style={{ color: 'var(--text-muted)' }}>
                        {log.details ? JSON.stringify(log.details) : '—'}
                      </td>
                      <td className="px-3 py-3">
                        <button
                          onClick={() => setRetryTarget(log)}
                          className="px-2 py-1 rounded text-xs font-medium transition-opacity hover:opacity-80"
                          style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--accent-blue)' }}
                        >
                          Retry
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && total > PER_PAGE && (
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderTop: '1px solid var(--border-subtle)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Page {page} of {totalPages} · {total.toLocaleString()} entries
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 transition-opacity hover:opacity-70"
                style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
              >
                ← Prev
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 transition-opacity hover:opacity-70"
                style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Retry confirm */}
      {retryTarget && (
        <ConfirmDialog
          title="Retry Admin Action"
          message={`Re-apply "${retryTarget.action.replace(/_/g, ' ')}" on ${retryTarget.target_email ?? 'target'}?`}
          confirmLabel="Retry" loading={retrying}
          onConfirm={retryAction} onCancel={() => setRetryTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const [activeTab, setActiveTab]       = useState<AdminTab>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Collapse sidebar by default on narrow viewports
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    if (mq.matches) setSidebarCollapsed(true);
    const handler = (e: MediaQueryListEvent) => setSidebarCollapsed(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  if (authLoading) return <Spinner />;
  if (!user || user.role !== 'admin') return <AccessDenied />;

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      {/* Inner admin sidebar */}
      <AdminSidebar
        active={activeTab}
        setActive={setActiveTab}
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
      />

      {/* Tab content area */}
      <main className="flex-1 min-h-0 overflow-y-auto">
        {activeTab === 'overview'  && <OverviewTab />}
        {activeTab === 'users'     && <UsersTab />}
        {activeTab === 'contests'  && <ContestsTab />}
        {activeTab === 'trades'    && <TradeMonitorTab />}
        {activeTab === 'health'    && <SystemHealthTab />}
        {activeTab === 'logs'      && <EmailLogsTab />}
      </main>
    </div>
  );
}
