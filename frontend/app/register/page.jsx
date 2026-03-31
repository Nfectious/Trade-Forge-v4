'use client';

import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';
import { z } from 'zod';

const registerSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  email: z.string().email('Invalid email'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number')
    .regex(/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/, 'Password must contain at least one special character'),
});

const Register = () => {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Redirect already-authenticated users
  useEffect(() => {
    if (!loading && user) {
      router.push('/dashboard');
    }
  }, [user, loading, router]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      registerSchema.parse({ username, email, password });
    } catch (err) {
      setError(err.errors?.[0]?.message ?? 'Invalid input');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/auth/register', { nickname: username, email, password });
      router.push('/login');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail ?? err?.message ?? 'Registration failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-800">
      <div className="max-w-md w-full mx-auto p-8 bg-white dark:bg-gray-900 rounded-lg shadow-md text-black dark:text-white">
        <h2 className="text-xl font-bold mb-4">Register</h2>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            required
            className="block w-full p-2 mt-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-600 dark:focus:border-blue-500 focus:ring-blue-500 dark:focus:ring-blue-700 focus:outline-none"
          />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            required
            className="block w-full p-2 mt-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-600 dark:focus:border-blue-500 focus:ring-blue-500 dark:focus:ring-blue-700 focus:outline-none"
          />
          <div className="relative mt-2">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              className="block w-full p-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-600 dark:focus:border-blue-500 focus:ring-blue-500 dark:focus:ring-blue-700 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400"
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Min 8 chars, 1 uppercase, 1 number, 1 special character
          </p>
          {error && <p className="text-red-500 mt-2 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="mt-4 w-full bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-md disabled:opacity-60"
          >
            {submitting ? 'Creating account…' : 'Register'}
          </button>
        </form>
        <p className="mt-4">
          Already have an account?{' '}
          <a href="/login" className="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300">
            Login
          </a>
        </p>
      </div>
    </div>
  );
};

export default Register;
