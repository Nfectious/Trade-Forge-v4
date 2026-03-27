'use client';

import { ReactNode } from 'react';

interface StatCardProps {
  icon?: ReactNode;
  label: string;
  value: string | number;
  trend?: number;      // positive = green arrow up, negative = red arrow down
  sub?: string;        // small subtitle below value
  loading?: boolean;
}

export default function StatCard({ icon, label, value, trend, sub, loading }: StatCardProps) {
  if (loading) {
    return (
      <div className="tf-card p-5 space-y-3">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-8 w-32" />
        <div className="skeleton h-3 w-20" />
      </div>
    );
  }

  const trendPositive = trend !== undefined && trend >= 0;
  const trendColor = trend === undefined ? '' : trendPositive ? 'val-pos' : 'val-neg';

  return (
    <div className="tf-card tf-card-hover p-5 transition-colors">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {label}
        </span>
        {icon && (
          <span className="text-slate-500">{icon}</span>
        )}
      </div>

      <div className="flex items-end gap-3">
        <span className="mono text-2xl font-medium" style={{ color: 'var(--text-primary)' }}>
          {value}
        </span>
        {trend !== undefined && (
          <span className={`flex items-center gap-0.5 text-sm font-medium mono mb-0.5 ${trendColor}`}>
            {trendPositive ? '▲' : '▼'}
            {Math.abs(trend).toFixed(2)}%
          </span>
        )}
      </div>

      {sub && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{sub}</p>
      )}
    </div>
  );
}
