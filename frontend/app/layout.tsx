import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth';
import { ToastProvider } from '@/lib/toast';
import Sidebar from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'Trading Forge — Professional Crypto Simulation',
  description: 'Paper trade crypto. Win contests. Upgrade to Pro.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <ToastProvider>
            <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
              <Sidebar />
              <main className="flex-1 overflow-y-auto">
                {children}
              </main>
            </div>
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
