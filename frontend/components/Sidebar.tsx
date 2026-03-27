'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useAuth } from '@/lib/auth';
import TierBadge from '@/components/ui/TierBadge';
import {
  LayoutDashboard,
  TrendingUp,
  Trophy,
  Medal,
  User,
  Shield,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard'   },
  { href: '/trade',       icon: TrendingUp,      label: 'Trade'        },
  { href: '/contests',    icon: Trophy,          label: 'Contests'     },
  { href: '/leaderboard', icon: Medal,           label: 'Leaderboard'  },
  { href: '/profile',     icon: User,            label: 'Profile'      },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const displayName = user?.email?.split('@')[0] ?? 'Trader';
  const isAdmin = user?.role === 'admin';

  const navItems = isAdmin
    ? [...NAV_ITEMS, { href: '/admin', icon: Shield, label: 'Admin' }]
    : NAV_ITEMS;

  function NavLink({ href, icon: Icon, label }: typeof NAV_ITEMS[0]) {
    const active = pathname === href || pathname.startsWith(href + '/');
    return (
      <Link
        href={href}
        onClick={() => setMobileOpen(false)}
        className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors relative group"
        style={{
          background: active ? 'rgba(59,130,246,0.12)' : 'transparent',
          color: active ? 'var(--accent-blue)' : 'var(--text-secondary)',
          borderLeft: active ? '2px solid var(--accent-blue)' : '2px solid transparent',
        }}
      >
        <Icon size={18} className="flex-shrink-0" />
        {!collapsed && (
          <span className="text-sm font-medium truncate">{label}</span>
        )}
        {collapsed && (
          <div className="absolute left-14 bg-gray-800 text-white text-xs px-2 py-1 rounded
                          opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50
                          transition-opacity border border-gray-700">
            {label}
          </div>
        )}
      </Link>
    );
  }

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo + collapse toggle */}
      <div className="flex items-center justify-between px-4 py-5 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        {!collapsed && (
          <span className="font-bold text-sm tracking-widest" style={{ fontFamily: 'Space Grotesk', color: 'var(--accent-blue)' }}>
            TRADING FORGE
          </span>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          className="hidden lg:flex items-center justify-center w-7 h-7 rounded-md transition-colors hover:bg-white/5"
          style={{ color: 'var(--text-muted)', marginLeft: collapsed ? 'auto' : undefined }}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <button className="lg:hidden" onClick={() => setMobileOpen(false)} style={{ color: 'var(--text-muted)' }}>
          <X size={18} />
        </button>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navItems.map(item => (
          <NavLink key={item.href} {...item} />
        ))}
      </nav>

      {/* User section */}
      {user && (
        <div className="border-t px-2 py-4 space-y-1" style={{ borderColor: 'var(--border-subtle)' }}>
          {!collapsed && (
            <div className="flex items-center gap-3 px-3 py-2 mb-2">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
                style={{ background: 'var(--accent-blue)', color: '#fff' }}
              >
                {displayName[0].toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                  {displayName}
                </p>
                <TierBadge tier={user.tier} />
              </div>
            </div>
          )}
          <Link href="/profile" className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors hover:bg-white/5"
            style={{ color: 'var(--text-muted)' }}>
            <Settings size={17} className="flex-shrink-0" />
            {!collapsed && <span className="text-sm">Settings</span>}
          </Link>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors hover:bg-red-500/10"
            style={{ color: 'var(--text-muted)' }}
          >
            <LogOut size={17} className="flex-shrink-0" />
            {!collapsed && <span className="text-sm">Log out</span>}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
        onClick={() => setMobileOpen(true)}
      >
        <Menu size={20} />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      <aside
        className="lg:hidden fixed left-0 top-0 h-full w-64 z-50 transition-transform"
        style={{
          background: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border-subtle)',
          transform: mobileOpen ? 'translateX(0)' : 'translateX(-100%)',
        }}
      >
        {sidebarContent}
      </aside>

      {/* Desktop sidebar */}
      <aside
        className="hidden lg:flex flex-col h-screen sticky top-0 flex-shrink-0 transition-all duration-300"
        style={{
          width: collapsed ? '64px' : '240px',
          background: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
