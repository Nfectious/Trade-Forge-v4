'use client';

import { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      {icon && (
        <div className="mb-4 text-4xl opacity-30">{icon}</div>
      )}
      <p className="text-base font-semibold mb-2" style={{ color: 'var(--text-secondary)', fontFamily: 'Space Grotesk, sans-serif' }}>
        {title}
      </p>
      {description && (
        <p className="text-sm max-w-xs" style={{ color: 'var(--text-muted)' }}>{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-6 px-5 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-80"
          style={{ background: 'var(--accent-blue)' }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
