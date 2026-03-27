'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useToast } from '@/lib/toast';
import StatCard from '@/components/ui/StatCard';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import EmptyState from '@/components/ui/EmptyState';
import RankBadge from '@/components/ui/RankBadge';
import {
  TrendingUp, TrendingDown, Wallet, BarChart2, Activity,
  Trophy, X, AlertTriangle, Wifi, WifiOff,
} from 'lucide-react';

// ── Close position modal ─────────────────────────────────────────────────────
function CloseModal({ position, livePrice, onConfirm, onCancel, loading }) {
  if (!position) return null;
  const price  = livePrice ?? position.current_price;
  const pnl    = (price - position.average_price) * position.quantity;
  const isPos  = pnl >= 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div
        className="relative z-10 w-full max-w-sm mx-4 rounded-xl p-6 shadow-2xl"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)' }}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary)', fontFamily: 'Space Grotesk' }}>
            Close Position
          </h3>
          <button onClick={onCancel} style={{ color: 'var(--text-muted)' }} className="hover:opacity-70">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 mb-6">
          <div className="flex justify-between text-sm">
            <span style={{ color: 'var(--text-muted)' }}>Symbol</span>
            <span className="font-medium mono" style={{ color: 'var(--text-primary)' }}>{position.symbol}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span style={{ color: 'var(--text-muted)' }}>Quantity</span>
            <span className="mono" style={{ color: 'var(--text-secondary)' }}>{position.quantity}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span style={{ color: 'var(--text-muted)' }}>Close price</span>
            <span className="mono" style={{ color: 'var(--text-primary)' }}>
              ${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div className="flex justify-between text-sm pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <span style={{ color: 'var(--text-muted)' }}>Realized P&L</span>
            <span className="mono font-semibold" style={{ color: isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              {isPos ? '+' : ''}${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-opacity hover:opacity-80"
            style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-50"
            style={{ background: 'var(--accent-red)', color: '#fff' }}
          >
            {loading ? 'Closing…' : 'Close Position'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main dashboard ───────────────────────────────────────────────────────────
export default function Dashboard() {
  const router             = useRouter();
  const { user }           = useAuth();
  const { prices, isConnected } = usePriceStream();
  const { addToast }       = useToast();

  const [portfolio,    setPortfolio]    = useState(null);
  const [trades,       setTrades]       = useState([]);
  const [myRank,       setMyRank]       = useState(null);
  const [myContests,   setMyContests]   = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [closeTarget,  setCloseTarget]  = useState(null);
  const [closeLoading, setCloseLoading] = useState(false);

  // ── Fetch all data ────────────────────────────────────────────────────────
  useEffect(() => {
    async function fetchAll() {
      setLoading(true);
      const [portRes, tradesRes, rankRes, contestRes] = await Promise.allSettled([
        api.get('/trading/portfolio'),
        api.get('/trading/trades/history?limit=10'),
        api.get('/leaderboard/my-rank'),
        api.get('/contests/my'),
      ]);

      if (portRes.status === 'fulfilled')    setPortfolio(portRes.value.data);
      if (tradesRes.status === 'fulfilled')  setTrades(tradesRes.value.data?.trades ?? tradesRes.value.data ?? []);
      if (rankRes.status === 'fulfilled')    setMyRank(rankRes.value.data?.rank ?? null);
      if (contestRes.status === 'fulfilled') setMyContests(contestRes.value.data?.contests ?? contestRes.value.data ?? []);

      setLoading(false);
    }
    fetchAll();
  }, []);

  // ── Live portfolio value ──────────────────────────────────────────────────
  const liveValue = useMemo(() => {
    if (!portfolio) return null;
    const holdingsVal = (portfolio.holdings ?? []).reduce((acc, h) => {
      const lp = prices[h.symbol] ?? h.current_price;
      return acc + lp * h.quantity;
    }, 0);
    return portfolio.cash_balance + holdingsVal;
  }, [portfolio, prices]);

  const livePnl = liveValue !== null && portfolio
    ? liveValue - portfolio.starting_balance
    : null;
  const livePnlPct = livePnl !== null && portfolio?.starting_balance
    ? (livePnl / portfolio.starting_balance) * 100
    : null;

  // ── Win rate from trades ──────────────────────────────────────────────────
  const winRate = useMemo(() => {
    const closed = trades.filter(t => t.side === 'sell' && t.realized_pnl !== undefined);
    if (!closed.length) return null;
    const wins = closed.filter(t => t.realized_pnl > 0).length;
    return (wins / closed.length) * 100;
  }, [trades]);

  // ── Close position handler ────────────────────────────────────────────────
  async function handleClose() {
    if (!closeTarget) return;
    setCloseLoading(true);
    try {
      await api.post('/trading/sell', {
        symbol: closeTarget.symbol,
        quantity: closeTarget.quantity,
        order_type: 'market',
      });
      addToast(`${closeTarget.symbol} position closed`, 'success');
      setCloseTarget(null);
      // Refresh portfolio
      const res = await api.get('/trading/portfolio');
      setPortfolio(res.data);
    } catch (err) {
      addToast(err?.response?.data?.detail ?? 'Failed to close position', 'error');
    } finally {
      setCloseLoading(false);
    }
  }

  const displayName = user?.email?.split('@')[0] ?? 'Trader';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="skeleton h-8 w-64" />
        <LoadingSkeleton variant="stat" rows={4} />
        <LoadingSkeleton variant="table" rows={5} />
      </div>
    );
  }

  return (
    <>
      <CloseModal
        position={closeTarget}
        livePrice={closeTarget ? (prices[closeTarget.symbol] ?? null) : null}
        onConfirm={handleClose}
        onCancel={() => setCloseTarget(null)}
        loading={closeLoading}
      />

      <div className="p-6 space-y-6 max-w-7xl mx-auto">

        {/* ── Header ───────────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
              {greeting}, {displayName}
            </h1>
            {liveValue !== null && (
              <p className="text-3xl font-bold mono mt-1" style={{ color: 'var(--text-primary)' }}>
                ${liveValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                {livePnlPct !== null && (
                  <span
                    className="ml-3 text-base font-medium"
                    style={{ color: livePnlPct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
                  >
                    {livePnlPct >= 0 ? '▲' : '▼'} {Math.abs(livePnlPct).toFixed(2)}%
                  </span>
                )}
              </p>
            )}
          </div>
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium"
            style={{
              background: isConnected ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
              color: isConnected ? 'var(--accent-green)' : 'var(--accent-red)',
              border: `1px solid ${isConnected ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
            }}
          >
            {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
            {isConnected ? 'Live' : 'Offline'}
          </div>
        </div>

        {/* ── Stat cards ───────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={<Wallet size={18} />}
            label="Portfolio Value"
            value={liveValue !== null
              ? `$${liveValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '—'}
          />
          <StatCard
            icon={livePnl !== null && livePnl >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
            label="Total P&L"
            value={livePnl !== null
              ? `${livePnl >= 0 ? '+' : ''}$${Math.abs(livePnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '—'}
            trend={livePnlPct}
          />
          <StatCard
            icon={<BarChart2 size={18} />}
            label="Win Rate"
            value={winRate !== null ? `${winRate.toFixed(1)}%` : '—'}
          />
          <StatCard
            icon={<Activity size={18} />}
            label="Total Trades"
            value={trades.length > 0 ? trades.length.toString() : portfolio?.total_trades?.toString() ?? '0'}
            sub={myRank != null ? `Rank #${myRank}` : undefined}
          />
        </div>

        {/* ── Open positions ───────────────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
            Open Positions
          </h2>
          <div className="tf-card overflow-hidden">
            {(!portfolio?.holdings || portfolio.holdings.length === 0) ? (
              <EmptyState
                icon={<TrendingUp />}
                title="No open positions"
                description="Head to the trade page to open your first position."
                action={{ label: 'Trade Now', onClick: () => router.push('/trade') }}
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      {['Symbol', 'Entry', 'Current', 'Qty', 'P&L', 'Alloc', ''].map(h => (
                        <th
                          key={h}
                          className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.holdings.map(h => {
                      const lp   = prices[h.symbol] ?? h.current_price;
                      const pnl  = (lp - h.average_price) * h.quantity;
                      const pct  = ((lp - h.average_price) / h.average_price) * 100;
                      const isPos = pnl >= 0;
                      return (
                        <tr
                          key={h.symbol}
                          style={{ borderBottom: '1px solid var(--border-subtle)' }}
                          className="hover:bg-white/[0.02] transition-colors"
                        >
                          <td className="px-4 py-3">
                            <span className="font-semibold mono" style={{ color: 'var(--text-primary)' }}>{h.symbol}</span>
                          </td>
                          <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>
                            ${h.average_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-4 py-3 mono" style={{ color: 'var(--text-primary)' }}>
                            ${lp.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>
                            {h.quantity}
                          </td>
                          <td className="px-4 py-3">
                            <span className="mono font-medium" style={{ color: isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                              {isPos ? '+' : ''}${Math.abs(pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                            <span className="block text-xs mono" style={{ color: isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                              {isPos ? '+' : ''}{pct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="px-4 py-3 mono text-xs" style={{ color: 'var(--text-muted)' }}>
                            {h.allocation_percent != null ? `${h.allocation_percent.toFixed(1)}%` : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => setCloseTarget(h)}
                              className="px-3 py-1 rounded-md text-xs font-medium transition-colors hover:opacity-80"
                              style={{ background: 'rgba(239,68,68,0.12)', color: 'var(--accent-red)', border: '1px solid rgba(239,68,68,0.25)' }}
                            >
                              Close
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* ── Bottom row: contests + recent trades ─────────────────────── */}
        <div className="grid lg:grid-cols-3 gap-6">

          {/* Active contests */}
          <section className="lg:col-span-1">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
                Active Contests
              </h2>
              <button
                onClick={() => router.push('/contests')}
                className="text-xs transition-opacity hover:opacity-70"
                style={{ color: 'var(--accent-blue)' }}
              >
                View all →
              </button>
            </div>
            <div className="tf-card">
              {myContests.length === 0 ? (
                <EmptyState
                  icon={<Trophy />}
                  title="No active contests"
                  description="Join a contest to compete with other traders."
                  action={{ label: 'Browse Contests', onClick: () => router.push('/contests') }}
                />
              ) : (
                <div className="divide-y" style={{ '--tw-divide-opacity': 1 }}>
                  {myContests.slice(0, 4).map(c => (
                    <div key={c.id} className="px-4 py-3 flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{c.name}</p>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          {c.ends_at ? `Ends ${new Date(c.ends_at).toLocaleDateString()}` : 'Ongoing'}
                        </p>
                      </div>
                      <div className="flex-shrink-0 ml-3">
                        <RankBadge rank={c.rank} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Recent trades */}
          <section className="lg:col-span-2">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'Space Grotesk' }}>
                Recent Trades
              </h2>
            </div>
            <div className="tf-card overflow-hidden">
              {trades.length === 0 ? (
                <EmptyState icon={<Activity />} title="No trades yet" description="Your trade history will appear here." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        {['Date', 'Symbol', 'Side', 'Qty', 'Price', 'P&L'].map(h => (
                          <th
                            key={h}
                            className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {trades.slice(0, 8).map((t, idx) => {
                        const pnl   = t.realized_pnl ?? null;
                        const isPos = pnl !== null && pnl >= 0;
                        return (
                          <tr
                            key={t.id ?? idx}
                            style={{ borderBottom: '1px solid var(--border-subtle)' }}
                            className="hover:bg-white/[0.02] transition-colors"
                          >
                            <td className="px-4 py-3 text-xs mono" style={{ color: 'var(--text-muted)' }}>
                              {t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}
                            </td>
                            <td className="px-4 py-3 font-medium mono" style={{ color: 'var(--text-primary)' }}>{t.symbol}</td>
                            <td className="px-4 py-3">
                              <span
                                className="px-2 py-0.5 rounded text-xs font-medium uppercase"
                                style={{
                                  background: t.side === 'buy' ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                                  color: t.side === 'buy' ? 'var(--accent-green)' : 'var(--accent-red)',
                                }}
                              >
                                {t.side}
                              </span>
                            </td>
                            <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>{t.quantity}</td>
                            <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>
                              ${(t.price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                            <td className="px-4 py-3 mono font-medium" style={{ color: pnl === null ? 'var(--text-muted)' : isPos ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                              {pnl === null ? '—' : `${isPos ? '+' : ''}$${Math.abs(pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
