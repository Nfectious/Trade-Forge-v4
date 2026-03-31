'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

const withAuth = (Component) => {
  return function AuthenticatedComponent(props) {
    const router = useRouter();
    const { user, loading } = useAuth();

    useEffect(() => {
      if (!loading && !user) {
        router.push('/login');
      }
    }, [user, loading, router]);

    if (loading) {
      return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
    }

    return user ? <Component {...props} /> : null;
  };
};

export default withAuth;
