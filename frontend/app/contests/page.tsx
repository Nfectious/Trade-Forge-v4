'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { useToast } from '@/lib/toast';
import { useAuth } from '@/lib/auth';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import EmptyState from '@/components/ui/EmptyState';
import RankBadge from '@/components/ui/RankBadge';
import {
  Trophy, Clock, Users, DollarSign, Lock, CheckCircle, TrendingUp,
} from 'lucide-react';

type FilterTab = 'active' | 'upcoming' | 'my' | 'past';

interface Contest {
  id:           string;
  name:         string;
  description:  string;
  status:       'active' | 'upcoming' | 'completed' | 'cancelled';
  entry_fee_cents: number;
  prize_pool_cents: number;
  max_participants: number | null;
  participant_count: number;
  starts_at:    string;
  ends_at:      string;
  is_enrolled?: boolean;
  my_rank?:     number | null;
  my_pnl?:      number | null;
  tier_required?: string | null;
}

const TABS: { id: FilterTab; label: string }[] = [
  { id: 'active',   label: 'Active'    },
  { id: 'upcoming', label: 'Upcoming'  },
  { id: 'my',       label: 'My Contests' },
  { id: 'past',     label: 'Past'      },
];

// Countdown timer component
function Countdown({ target }: { target: string }) {
  const [remaining, setRemaining] = useState('');

  useEffect(() => {
    function calc() {
      const diff = new Date(target).getTime() - Date.now();
      if (diff <= 0) { setRemaining('Ended'); return; }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      if (d > 0) setRemaining(`${d}d ${h}h`);
      else if (h > 0) setRemaining(`${h}h ${m}m`);
      else setRemaining(`${m}m ${s}s`);
    }
    calc();
    const id = setInterval(calc, 1000);
    return () => clearInterval(id);
  }, [target]);

  return <span>{remaining}</span>;
}

function fmtCents(cents: number) {
  if (cents === 0) return 'Free';
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Join button with Stripe payment flow for paid contests
function JoinButton({ contest, onJoined }: { contest: Contest; onJoined: () => void }) {
  const { addToast } = useToast();
  const { user }     = useAuth();
  const [loading, setLoading] = useState(false);

  const handleJoin = useCallback(async () => {
    setLoading(true);
    try {
      if (contest.entry_fee_cents > 0) {
        // Paid contest: create payment intent, then redirect or handle
        const res = await api.post(`/payments/contest/${contest.id}/create-intent`);
        const { client_secret } = res.data;
        // For now, show client_secret info and confirm server-side
        // In production you'd use Stripe.js here
        await api.post(`/payments/contest/${contest.id}/confirm`, {
          payment_intent_id: client_secret.split('_secret_')[0],
        });
        addToast('Payment confirmed! You\'ve joined the contest.', 'success');
      } else {
        // Free contest
        await api.post(`/contests/${contest.id}/join`);
        addToast('You\'ve joined the contest!', 'success');
      }
      onJoined();
    } catch (err: any) {
      addToast(err?.response?.data?.detail ?? 'Failed to join contest', 'error');
    } finally {
      setLoading(false);
    }
  }, [contest, addToast, onJoined]);

  const tierRequired = contest.tier_required;
  const userTier = (user as any)?.tier ?? 'free';
  const tierOrder: Record<string, number> = { free: 0, pro: 1, elite: 2, valkyrie: 3 };
  const hasAccess = !tierRequired || (tierOrder[userTier] ?? 0) >= (tierOrder[tierRequired] ?? 0);

  if (!hasAccess) {
    return (
      <button
        disabled
        className="w-full py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2 opacity-60 cursor-not-allowed"
        style={{ background: 'var(--bg-card-hover)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
      >
        <Lock size={13} />
        Requires {tierRequired}
      </button>
    );
  }

  return (
    <button
      onClick={handleJoin}
      disabled={loading}
      className="w-full py-2.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-85 disabled:opacity-50 flex items-center justify-center gap-2"
      style={{ background: 'var(--accent-blue)', color: '#fff' }}
    >
      {loading ? (
        <span>Joining…</span>
      ) : (
        <>
          <Trophy size={14} />
          {contest.entry_fee_cents > 0 ? `Join · ${fmtCents(contest.entry_fee_cents)}` : 'Join Free'}
        </>
      )}
    </button>
  );
}

// Contest card
function ContestCard({ contest, onUpdate }: { contest: Contest; onUpdate: () => void }) {
  const router    = useRouter();
  const isActive  = contest.status === 'active';
  const isEnded   = contest.status === 'completed' || contest.status === 'cancelled';
  const enrolled  = contest.is_enrolled;

  const statusColor = {
    active:    'var(--accent-green)',
    upcoming:  'var(--accent-blue)',
    completed: 'var(--text-muted)',
    cancelled: 'var(--accent-red)',
  }[contest.status] ?? 'var(--text-muted)';

  return (
    <div
      className="tf-card p-5 flex flex-col gap-4 hover:border-opacity-100 transition-all"
      style={{ borderColor: enrolled ? 'var(--accent-blue)' : undefined }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="text-xs font-medium px-2 py-0.5 rounded-full"
              style={{
                background: `${statusColor}18`,
                color: statusColor,
                border: `1px solid ${statusColor}33`,
              }}
            >
              {contest.status}
            </span>
            {enrolled && (
              <span className="text-xs font-medium flex items-center gap-1" style={{ color: 'var(--accent-blue)' }}>
                <CheckCircle size={11} /> Enrolled
              </span>
            )}
          </div>
          <h3 className="font-semibold text-base" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
            {contest.name}
          </h3>
          {contest.description && (
            <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
              {contest.description}
            </p>
          )}
        </div>
        {contest.prize_pool_cents > 0 && (
          <div className="flex-shrink-0 text-right">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Prize Pool</p>
            <p className="text-lg font-bold mono" style={{ color: 'var(--accent-gold)' }}>
              {fmtCents(contest.prize_pool_cents)}
            </p>
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <p className="text-xs mb-0.5 flex items-center justify-center gap-1" style={{ color: 'var(--text-muted)' }}>
            <Users size={11} /> Players
          </p>
          <p className="text-sm font-medium mono" style={{ color: 'var(--text-secondary)' }}>
            {contest.participant_count}{contest.max_participants ? `/${contest.max_participants}` : ''}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs mb-0.5 flex items-center justify-center gap-1" style={{ color: 'var(--text-muted)' }}>
            <DollarSign size={11} /> Entry
          </p>
          <p className="text-sm font-medium mono" style={{ color: 'var(--text-secondary)' }}>
            {fmtCents(contest.entry_fee_cents)}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs mb-0.5 flex items-center justify-center gap-1" style={{ color: 'var(--text-muted)' }}>
            <Clock size={11} /> {isActive ? 'Ends' : isEnded ? 'Ended' : 'Starts'}
          </p>
          <p className="text-sm font-medium mono" style={{ color: 'var(--text-secondary)' }}>
            {isActive
              ? <Countdown target={contest.ends_at} />
              : !isEnded
              ? <Countdown target={contest.starts_at} />
              : new Date(contest.ends_at).toLocaleDateString()
            }
          </p>
        </div>
      </div>

      {/* My performance if enrolled */}
      {enrolled && contest.my_pnl !== null && contest.my_pnl !== undefined && (
        <div
          className="flex items-center justify-between px-3 py-2 rounded-lg text-xs"
          style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)' }}
        >
          <div className="flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
            <TrendingUp size={11} /> My P&L
          </div>
          <span className="mono font-semibold" style={{ color: (contest.my_pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            {(contest.my_pnl ?? 0) >= 0 ? '+' : ''}${Math.abs(contest.my_pnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          {contest.my_rank != null && (
            <RankBadge rank={contest.my_rank} />
          )}
        </div>
      )}

      {/* Action */}
      {isActive && !enrolled && <JoinButton contest={contest} onJoined={onUpdate} />}
      {isActive && enrolled && (
        <button
          onClick={() => router.push(`/contests/${contest.id}`)}
          className="w-full py-2.5 rounded-lg text-sm font-medium transition-opacity hover:opacity-80"
          style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          View Leaderboard
        </button>
      )}
      {!isActive && !isEnded && !enrolled && (
        <button
          disabled
          className="w-full py-2.5 rounded-lg text-sm font-medium opacity-50 cursor-not-allowed"
          style={{ background: 'var(--bg-card-hover)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
        >
          Starts {new Date(contest.starts_at).toLocaleDateString()}
        </button>
      )}
      {isEnded && (
        <button
          onClick={() => router.push(`/contests/${contest.id}`)}
          className="w-full py-2.5 rounded-lg text-sm font-medium transition-opacity hover:opacity-80"
          style={{ background: 'var(--bg-card-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          View Results
        </button>
      )}
    </div>
  );
}

export default function ContestsPage() {
  const [tab,      setTab]      = useState<FilterTab>('active');
  const [contests, setContests] = useState<Contest[]>([]);
  const [loading,  setLoading]  = useState(true);

  const fetchContests = useCallback(() => {
    setLoading(true);
    const endpoint =
      tab === 'my'      ? '/contests/my' :
      tab === 'past'    ? '/contests?status=completed' :
      tab === 'upcoming'? '/contests?status=upcoming' :
      '/contests?status=active';

    api.get(endpoint)
      .then(res => {
        const data = res.data;
        setContests(data?.contests ?? data ?? []);
      })
      .catch(() => setContests([]))
      .finally(() => setLoading(false));
  }, [tab]);

  useEffect(() => { fetchContests(); }, [fetchContests]);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2" style={{ fontFamily: 'Space Grotesk', color: 'var(--text-primary)' }}>
          <Trophy size={20} style={{ color: 'var(--accent-gold)' }} />
          Contests
        </h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
          Compete against other traders and win prizes
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

      {/* Content */}
      {loading ? (
        <LoadingSkeleton variant="card" rows={6} />
      ) : contests.length === 0 ? (
        <EmptyState
          icon={<Trophy />}
          title={tab === 'my' ? 'No contests joined' : 'No contests available'}
          description={
            tab === 'my'
              ? 'Join an active contest to see it here.'
              : 'Check back soon for new trading competitions.'
          }
          action={tab === 'my' ? { label: 'Browse Active', onClick: () => setTab('active') } : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {contests.map(c => (
            <ContestCard key={c.id} contest={c} onUpdate={fetchContests} />
          ))}
        </div>
      )}
    </div>
  );
}
