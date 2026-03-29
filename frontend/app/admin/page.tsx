'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/auth';
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

// ─── Tab content placeholders (replaced in later sections) ───────────────────

function OverviewTab()      { return <div id="tab-overview"  className="p-6" />; }
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
