'use client';

interface RankBadgeProps {
  rank: number | null | undefined;
}

export default function RankBadge({ rank }: RankBadgeProps) {
  if (rank === null || rank === undefined) {
    return <span className="text-slate-500 mono text-sm">—</span>;
  }

  if (rank === 1) {
    return (
      <span className="inline-flex items-center gap-1 mono font-bold text-sm" style={{ color: '#f59e0b' }}>
        👑 1
      </span>
    );
  }
  if (rank === 2) {
    return (
      <span className="inline-flex items-center gap-1 mono font-bold text-sm" style={{ color: '#94a3b8' }}>
        🥈 2
      </span>
    );
  }
  if (rank === 3) {
    return (
      <span className="inline-flex items-center gap-1 mono font-bold text-sm" style={{ color: '#cd7f32' }}>
        🥉 3
      </span>
    );
  }

  return (
    <span className="mono text-sm" style={{ color: 'var(--text-secondary)' }}>
      #{rank}
    </span>
  );
}
