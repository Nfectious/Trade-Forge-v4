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
function UsersTab()         { return <div id="tab-users"     className="p-6" />; }
function ContestsTab()      { return <div id="tab-contests"  className="p-6" />; }
function TradeMonitorTab()  { return <div id="tab-trades"    className="p-6" />; }
function SystemHealthTab()  { return <div id="tab-health"    className="p-6" />; }
function EmailLogsTab()     { return <div id="tab-logs"      className="p-6" />; }

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
