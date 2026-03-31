/**
 * API Client Library
 * Operation Phoenix | Trading Forge
 * For Madison
 *
 * Centralized HTTP client with authentication, error handling, and retry logic.
 * Access tokens are stored in memory (NOT localStorage) to prevent XSS theft.
 * Refresh tokens live in httpOnly cookies managed by the server.
 */

import axios, { AxiosInstance, AxiosError, AxiosRequestConfig } from 'axios'

// API base URL — always from environment, never hardcoded
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── In-memory token storage (XSS-safe) ──────────────────────────────────────
// This is module-scoped; survives component re-renders but not page refreshes.
// On refresh the auth provider calls tryRefreshToken() to restore the token
// using the httpOnly refresh cookie.
let _accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  _accessToken = token
}

export function getStoredAccessToken(): string | null {
  return _accessToken
}

/**
 * Attempt a silent refresh using the httpOnly cookie.
 * Does NOT redirect on failure — callers decide what to do.
 */
export async function tryRefreshToken(): Promise<string | null> {
  try {
    const response = await axios.post(
      `${API_BASE_URL}/auth/refresh`,
      {},
      { withCredentials: true }
    )
    const token: string | undefined = response.data.access_token
    if (token) {
      _accessToken = token
      return token
    }
    return null
  } catch {
    return null
  }
}

// ─── Axios client ─────────────────────────────────────────────────────────────

class APIClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      withCredentials: true, // send httpOnly cookies on every request
      headers: { 'Content-Type': 'application/json' },
    })

    this.setupInterceptors()
  }

  private setupInterceptors(): void {
    // ── Request: attach bearer token from memory ──
    this.client.interceptors.request.use(
      (config) => {
        const token = _accessToken
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // ── Response: handle auth errors, rate limits, server errors ──
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
        const status = error.response?.status

        // 401 → try to refresh access token once
        if (status === 401 && !originalRequest._retry) {
          originalRequest._retry = true
          const newToken = await tryRefreshToken()
          if (newToken && originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            return this.client(originalRequest)
          }
          // Refresh failed — redirect to login
          this.handleAuthFailure()
          return Promise.reject(error)
        }

        // 429 → dispatch event for global toast handler
        if (status === 429) {
          const retryAfter = (error.response?.headers as Record<string, string>)?.['retry-after'] ?? ''
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('api:rate-limited', { detail: { retryAfter } })
            )
          }
        }

        // 500+ → dispatch event for global toast handler
        if (status && status >= 500) {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('api:server-error', { detail: { status } }))
          }
        }

        return Promise.reject(error)
      }
    )
  }

  private handleAuthFailure(): void {
    if (typeof window === 'undefined') return
    _accessToken = null
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }

  public isAuthenticated(): boolean {
    return _accessToken !== null
  }

  public logout(): void {
    _accessToken = null
    if (typeof window !== 'undefined') {
      window.location.href = '/login'
    }
  }

  public async get<T = any>(url: string, config?: AxiosRequestConfig) {
    return this.client.get<T>(url, config)
  }

  public async post<T = any>(url: string, data?: any, config?: AxiosRequestConfig) {
    return this.client.post<T>(url, data, config)
  }

  public async put<T = any>(url: string, data?: any, config?: AxiosRequestConfig) {
    return this.client.put<T>(url, data, config)
  }

  public async patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig) {
    return this.client.patch<T>(url, data, config)
  }

  public async delete<T = any>(url: string, config?: AxiosRequestConfig) {
    return this.client.delete<T>(url, config)
  }
}

export const apiClient = new APIClient()
export const api = apiClient
export default api

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegisterResponse {
  id: string
  email: string
  created_at: string
}

export interface PortfolioResponse {
  user_id: string
  total_value: number
  cash_balance: number
  holdings_value: number
  total_invested: number
  starting_balance: number
  total_pnl: number
  pnl_percent: number
  holdings_count: number
  holdings: Holding[]
  updated_at: string
}

export interface Holding {
  symbol: string
  quantity: number
  average_price: number
  current_price: number
  total_invested: number
  current_value: number
  unrealized_pnl: number
  pnl_percent: number
  allocation_percent?: number
}

export interface TradeRequest {
  symbol: string
  side: 'buy' | 'sell'
  quantity: number
  order_type: string
}

export interface TradeResponse {
  trade_id: string
  symbol: string
  side: string
  quantity: number
  price: number
  total_value: number
  new_balance: number
  executed_at: string
  status: string
}

export interface PriceUpdate {
  symbol: string
  price: number
  exchange: string
  timestamp: string
}

// ─── Utils ────────────────────────────────────────────────────────────────────

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: 'always',
  }).format(value / 100)
}

export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}
