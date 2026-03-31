'use client';

import { useEffect } from 'react';
import { useToast } from '@/lib/toast';

export default function GlobalApiErrorListener() {
  const { addToast } = useToast();

  useEffect(() => {
    const onRateLimit = (e: Event) => {
      const detail = (e as CustomEvent<{ retryAfter?: string }>).detail ?? {};
      const msg = detail.retryAfter
        ? `Rate limit exceeded. Try again in ${detail.retryAfter}s.`
        : 'Rate limit exceeded. Please slow down.';
      addToast(msg, 'warning');
    };

    const onServerError = () => {
      addToast('Server error. Please try again shortly.', 'error');
    };

    window.addEventListener('api:rate-limited', onRateLimit);
    window.addEventListener('api:server-error', onServerError);
    return () => {
      window.removeEventListener('api:rate-limited', onRateLimit);
      window.removeEventListener('api:server-error', onServerError);
    };
  }, [addToast]);

  return null;
}
