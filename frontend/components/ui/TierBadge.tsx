'use client';

type Tier = 'free' | 'pro' | 'elite' | 'valkyrie';

interface TierBadgeProps {
  tier: Tier | string;
  size?: 'sm' | 'md';
}

const TIER_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  free:     { bg: 'rgba(71,85,105,0.3)',  text: '#94a3b8', label: 'FREE'     },
  pro:      { bg: 'rgba(59,130,246,0.2)', text: '#3b82f6', label: 'PRO'      },
  elite:    { bg: 'rgba(139,92,246,0.2)', text: '#a78bfa', label: 'ELITE'    },
  valkyrie: { bg: 'rgba(245,158,11,0.2)', text: '#f59e0b', label: 'VALKYRIE' },
};

export default function TierBadge({ tier, size = 'sm' }: TierBadgeProps) {
  const key = (tier || 'free').toLowerCase();
  const s = TIER_STYLES[key] ?? TIER_STYLES.free;
  const padding = size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center rounded-full font-bold tracking-wider mono border ${padding}`}
      style={{
        background: s.bg,
        color: s.text,
        borderColor: s.text + '44',
      }}
    >
      {s.label}
    </span>
  );
}
