'use client';

import { useEffect, useState } from 'react';
import api from '@/lib/api';
import RankBadge from '@/components/ui/RankBadge';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import EmptyState from '@/components/ui/EmptyState';
import TierBadge from '@/components/ui/TierBadge';
import { useAuth } from '@/lib/auth';
import { Medal, Trophy, TrendingUp } from 'lucide-react';

type Tab = 'alltime' | 'weekly' | 'volume';

interface LeaderEntry {
  rank:       number;
  user_id:    string;
  username:   string;
  tier:       string;
  total_pnl:  number;
  pnl_pct:    number;
  win_rate:   number;
  total_trades: number;
  portfolio_value?: number;
}

interface MyRank {
  rank:            number | null;
  total_pnl:       number;
  pnl_pct:         number;
  win_rate:        number;
  total_trades:    number;
  portfolio_value: number;
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'alltime', label: 'All-Time P&L' },
  { id: 'weekly',  label: 'Weekly'        },
  { id: 'volume',  label: 'By Volume'     },
];

// Podium card for top 3
function PodiumCard({ entry, position }: { entry: LeaderEntry; position: 1 | 2 | 3 }) {
  const heights   = { 1: 'h-24', 2: 'h-16', 3: 'h-12' };
  const colors    = { 1: '#f59e0b', 2: '#94a3b8', 3: '#cd7f32' };
  const emojis    = { 1: '👑', 2: '🥈', 3: '🥉' };
  const order     = { 1: 'order-2', 2: 'order-1', 3: 'order-3' };

  return (
    <div className={`flex flex-col items-center ${order[position]}`}>
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center text-xl font-bold mb-2"
        style={{ background: `${colors[position]}22`, border: `2px solid ${colors[position]}`, color: colors[position] }}
      >
        {entry.username[0]?.toUpperCase() ?? '?'}
      </div>
      <p className="text-xs font-semibold text-center truncate max-w-[80px]" style={{ color: 'var(--text-primary)' }}>
        {entry.username}
      </p>
      <p className="text-xs font-bold mono" style={{ color: entry.total_pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
        {entry.total_pnl >= 0 ? '+' : ''}${Math.abs(entry.total_pnl).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
      </p>
      <TierBadge tier={entry.tier as any} />
      <div
        className={`w-16 ${heights[position]} mt-2 rounded-t-md flex items-end justify-center pb-1`}
        style={{ background: `${colors[position]}22`, border: `1px solid ${colors[position]}44` }}
      >
        <span className="text-base">{emojis[position]}</span>
      </div>
    </div>
  );
}

export default function LeaderboardPage() {
  const { user }  = useAuth();
  const [tab,     setTab]     = useState<Tab>('alltime');
  const [entries, setEntries] = useState<LeaderEntry[]>([]);
  const [myRank,  setMyRank]  = useState<MyRank | null>(null);
  const [loading, setLoading] = useState(true);
  const [page,    setPage]    = useState(1);
  const PER_PAGE = 25;

  useEffect(() => {
    setLoading(true);
    setPage(1);

    const endpoint =
      tab === 'alltime' ? '/leaderboard/global?period=alltime' :
      tab === 'weekly'  ? '/leaderboard/global?period=weekly' :
      '/leaderboard/global?sort=volume';

    Promise.allSettled([
      api.get(endpoint),
      api.get('/leaderboard/my-rank'),
    ]).then(([rankRes, myRes]) => {
      if (rankRes.status === 'fulfilled') {
        const data = rankRes.value.data;
        setEntries(data?.entries ?? data?.rankings ?? data ?? []);
      }
      if (myRes.status === 'fulfilled') {
        setMyRank(myRes.value.data);
      }
    }).finally(() => setLoading(false));
  }, [tab]);

  const top3    = entries.slice(0, 3);
  const rest    = entries.slice(3);
  const paged   = rest.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const totalPg = Math.ceil(rest.length / PER_PAGE);

  const isMe = (e: LeaderEntry) => e.user_id === (user as any)?.id;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
          <Trophy size={20} style={{ color: 'var(--accent-gold)' }} />
          Leaderboard
        </h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
          Top traders ranked by performance
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', width: 'fit-content' }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
            style={{
              background: tab === t.id ? 'var(--accent-blue)' : 'transparent',
              color: tab === t.id ? '#fff' : 'var(--text-muted)',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingSkeleton variant="table" rows={8} />
      ) : entries.length === 0 ? (
        <EmptyState icon={<Medal />} title="No rankings yet" description="Be the first to make a trade and claim the top spot." />
      ) : (
        <>
          {/* My rank widget */}
          {myRank && (
            <div
              className="rounded-xl px-5 py-4 flex flex-wrap gap-4 items-center"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border-bright)' }}
            >
              <div>
                <p className="text-xs uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>Your Rank</p>
                <RankBadge rank={myRank.rank} />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>P&L</p>
                <p className="text-sm mono font-semibold" style={{ color: myRank.total_pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  {myRank.total_pnl >= 0 ? '+' : ''}${Math.abs(myRank.total_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>Win Rate</p>
                <p className="text-sm mono" style={{ color: 'var(--text-secondary)' }}>{(myRank.win_rate ?? 0).toFixed(1)}%</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>Trades</p>
                <p className="text-sm mono" style={{ color: 'var(--text-secondary)' }}>{myRank.total_trades}</p>
              </div>
            </div>
          )}

          {/* Podium */}
          {top3.length >= 3 && (
            <div className="tf-card p-6">
              <div className="flex items-end justify-center gap-4">
                <PodiumCard entry={top3[1]} position={2} />
                <PodiumCard entry={top3[0]} position={1} />
                <PodiumCard entry={top3[2]} position={3} />
              </div>
            </div>
          )}

          {/* Rest of table */}
          {paged.length > 0 && (
            <div className="tf-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      {['Rank', 'Trader', 'P&L', 'Return', 'Win Rate', 'Trades'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paged.map(e => {
                      const me = isMe(e);
                      return (
                        <tr
                          key={e.user_id}
                          style={{
                            borderBottom: '1px solid var(--border-subtle)',
                            background: me ? 'rgba(59,130,246,0.06)' : 'transparent',
                          }}
                          className="hover:bg-white/[0.02] transition-colors"
                        >
                          <td className="px-4 py-3"><RankBadge rank={e.rank} /></td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div
                                className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                                style={{ background: 'var(--accent-blue)', color: '#fff' }}
                              >
                                {e.username[0]?.toUpperCase()}
                              </div>
                              <div>
                                <p className="font-medium" style={{ color: me ? 'var(--accent-blue)' : 'var(--text-primary)' }}>
                                  {e.username}{me && ' (you)'}
                                </p>
                                <TierBadge tier={e.tier as any} />
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 mono font-medium" style={{ color: e.total_pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {e.total_pnl >= 0 ? '+' : ''}${Math.abs(e.total_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-4 py-3 mono text-xs" style={{ color: e.pnl_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {e.pnl_pct >= 0 ? '+' : ''}{(e.pnl_pct ?? 0).toFixed(2)}%
                          </td>
                          <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>
                            {(e.win_rate ?? 0).toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 mono" style={{ color: 'var(--text-secondary)' }}>
                            {e.total_trades}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPg > 1 && (
                <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity disabled:opacity-40"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
                  >
                    ← Prev
                  </button>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Page {page} of {totalPg}
                  </span>
                  <button
                    onClick={() => setPage(p => Math.min(totalPg, p + 1))}
                    disabled={page === totalPg}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity disabled:opacity-40"
                    style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)' }}
                  >
                    Next →
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
