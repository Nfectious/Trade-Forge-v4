'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

const ICONS: Record<ToastType, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

const STYLES: Record<ToastType, { border: string; icon: string }> = {
  success: { border: 'border-l-[var(--accent-green)]', icon: 'text-green-400' },
  error:   { border: 'border-l-[var(--accent-red)]',   icon: 'text-red-400'   },
  warning: { border: 'border-l-[var(--accent-gold)]',  icon: 'text-amber-400' },
  info:    { border: 'border-l-[var(--accent-blue)]',  icon: 'text-blue-400'  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  const remove = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}

      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map(toast => {
          const s = STYLES[toast.type];
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg border border-l-4
                tf-card shadow-xl min-w-[280px] max-w-[360px] animate-slide-up ${s.border}`}
              style={{ background: 'var(--bg-card)', borderColor: 'var(--border-subtle)' }}
            >
              <span className={`text-lg leading-none mt-0.5 ${s.icon}`}>{ICONS[toast.type]}</span>
              <span className="text-sm leading-snug flex-1" style={{ color: 'var(--text-primary)' }}>
                {toast.message}
              </span>
              <button
                onClick={() => remove(toast.id)}
                className="text-slate-500 hover:text-slate-300 ml-1 leading-none text-base"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextType {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
