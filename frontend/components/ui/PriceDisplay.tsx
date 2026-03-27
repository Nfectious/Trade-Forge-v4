'use client';

interface PriceDisplayProps {
  price: number;
  decimals?: number;
  size?: 'sm' | 'md' | 'lg';
  change?: number;   // if provided, colors green/red/neutral
}

const SIZE_CLASSES = { sm: 'text-sm', md: 'text-xl', lg: 'text-3xl' };

export default function PriceDisplay({ price, decimals = 2, size = 'md', change }: PriceDisplayProps) {
  const sizeClass = SIZE_CLASSES[size];
  const color =
    change === undefined ? 'var(--text-primary)'
    : change > 0  ? 'var(--accent-green)'
    : change < 0  ? 'var(--accent-red)'
    : 'var(--text-primary)';

  const formatted = price.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return (
    <span
      className={`mono font-medium ${sizeClass}`}
      style={{ color }}
    >
      ${formatted}
    </span>
  );
}
