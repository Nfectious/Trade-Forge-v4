'use client';

interface LoadingSkeletonProps {
  rows?: number;
  variant?: 'card' | 'table' | 'stat';
}

function SkeletonStat() {
  return (
    <div className="tf-card p-5 space-y-3">
      <div className="skeleton h-3 w-20" />
      <div className="skeleton h-7 w-28" />
      <div className="skeleton h-3 w-16" />
    </div>
  );
}

function SkeletonTableRow() {
  return (
    <tr>
      {[40, 28, 28, 20, 24, 20].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className={`skeleton h-4 w-${w}`} style={{ width: `${w * 4}px` }} />
        </td>
      ))}
    </tr>
  );
}

function SkeletonCard() {
  return (
    <div className="tf-card p-5 space-y-4">
      <div className="skeleton h-5 w-48" />
      <div className="skeleton h-4 w-full" />
      <div className="skeleton h-4 w-3/4" />
      <div className="flex gap-3 mt-2">
        <div className="skeleton h-8 flex-1" />
        <div className="skeleton h-8 w-24" />
      </div>
    </div>
  );
}

export default function LoadingSkeleton({ rows = 4, variant = 'card' }: LoadingSkeletonProps) {
  if (variant === 'stat') {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: rows }).map((_, i) => <SkeletonStat key={i} />)}
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <table className="w-full">
        <tbody>
          {Array.from({ length: rows }).map((_, i) => <SkeletonTableRow key={i} />)}
        </tbody>
      </table>
    );
  }

  return (
    <div className="grid gap-4">
      {Array.from({ length: rows }).map((_, i) => <SkeletonCard key={i} />)}
    </div>
  );
}
