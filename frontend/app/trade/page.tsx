'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api } from '@/lib/api';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useToast } from '@/lib/toast';
import { usePortfolio } from '@/hooks/usePortfolio';
import {
  TrendingUp, TrendingDown, ChevronDown, ChevronUp,
  Wifi, WifiOff, RefreshCw,
} from 'lucide-react';

// ── Symbol list ────────────────────────────────────────────────────────────
const SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
  'ADAUSDT', 'AVAXUSDT', 'DOGEUSDT', 'MATICUSDT', 'LINKUSDT',
];

const ORDER_TYPES = ['market', 'limit', 'stop_limit'] as const;
type OrderType = typeof ORDER_TYPES[number];

// ── Lightweight chart loader ──────────────────────────────────────────────
function useChart(containerRef: React.RefObject<HTMLDivElement>, symbol: string) {
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);

  useEffect(() => {
    if (typeof window === 'undefined' || !containerRef.current) return;

    async function init() {
      // Load LWC from CDN if not already loaded
      if (!(window as any).LightweightCharts) {
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement('script');
          s.src = 'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js';
          s.onload = () => resolve();
          s.onerror = () => reject(new Error('Failed to load chart library'));
          document.head.appendChild(s);
        });
      }

      const LWC = (window as any).LightweightCharts;
      if (!LWC || !containerRef.current) return;

      // Destroy existing chart
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }

      const chart = LWC.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
        layout: {
          background: { color: 'transparent' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#1e2d45' },
          horzLines: { color: '#1e2d45' },
        },
        crosshair: { mode: 1 },
        rightPriceScale: {
          borderColor: '#1e2d45',
          textColor: '#94a3b8',
        },
        timeScale: {
          borderColor: '#1e2d45',
          textColor: '#94a3b8',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      chartRef.current = chart;

      const series = chart.addCandlestickSeries({
        upColor:         '#22c55e',
        downColor:       '#ef4444',
        borderUpColor:   '#22c55e',
        borderDownColor: '#ef4444',
        wickUpColor:     '#22c55e',
        wickDownColor:   '#ef4444',
      });
      seriesRef.current = series;

      // Resize observer
      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          });
        }
      });
      ro.observe(containerRef.current);

      return () => ro.disconnect();
    }

    init().catch(console.error);

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load candle data when symbol changes
  useEffect(() => {
    if (!seriesRef.current) return;

    api.get(`/market/history/${symbol}?interval=1h&limit=200`)
      .then(res => {
        const candles = (res.data?.candles ?? res.data ?? []).map((c: any) => ({
          time: Math.floor(new Date(c.time ?? c.timestamp ?? c.t).getTime() / 1000),
          open:  c.open  ?? c.o,
          high:  c.high  ?? c.h,
          low:   c.low   ?? c.l,
          close: c.close ?? c.c,
        }));
        if (candles.length && seriesRef.current) {
          seriesRef.current.setData(candles);
          chartRef.current?.timeScale().fitContent();
        }
      })
      .catch(() => {}); // chart still works without historical data
  }, [symbol]);

  return seriesRef;
}

// ── Main component ─────────────────────────────────────────────────────────
export default function TradePage() {
  const { prices, isConnected } = usePriceStream();
  const { portfolio, refetch }  = usePortfolio(false);
  const { addToast }            = useToast();

  const [symbol,      setSymbol]      = useState('BTCUSDT');
  const [side,        setSide]        = useState<'buy' | 'sell'>('buy');
  const [orderType,   setOrderType]   = useState<OrderType>('market');
  const [quantity,    setQuantity]    = useState('');
  const [usdMode,     setUsdMode]     = useState(false);   // input in USD vs units
  const [limitPrice,  setLimitPrice]  = useState('');
  const [stopPrice,   setStopPrice]   = useState('');
  const [stopLoss,    setStopLoss]    = useState('');
  const [takeProfit,  setTakeProfit]  = useState('');
  const [riskOpen,    setRiskOpen]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [confirm,     setConfirm]     = useState(false);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  useChart(chartContainerRef, symbol);

  const livePrice = prices[symbol] ?? 0;

  // ── Derived values ───────────────────────────────────────────────────────
  const unitQty = useMemo(() => {
    const raw = parseFloat(quantity);
    if (!raw || !livePrice) return 0;
    return usdMode ? raw / livePrice : raw;
  }, [quantity, usdMode, livePrice]);

  const usdTotal = useMemo(() => {
    const raw = parseFloat(quantity);
    if (!raw || !livePrice) return 0;
    return usdMode ? raw : raw * livePrice;
  }, [quantity, usdMode, livePrice]);

  const execPrice = orderType === 'market' ? livePrice : parseFloat(limitPrice) || livePrice;
  const cashBalance = portfolio?.cash_balance ?? 0;
  const holding = portfolio?.holdings?.find(h => h.symbol === symbol);

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!unitQty || unitQty <= 0) {
      addToast('Enter a valid quantity', 'error');
      return;
    }
    setLoading(true);
    try {
      const payload: Record<string, any> = {
        symbol,
        side,
        quantity: unitQty,
        order_type: orderType,
      };
      if (orderType !== 'market') payload.limit_price = parseFloat(limitPrice);
      if (orderType === 'stop_limit') payload.stop_price = parseFloat(stopPrice);
      if (stopLoss)    payload.stop_loss    = parseFloat(stopLoss);
      if (takeProfit)  payload.take_profit  = parseFloat(takeProfit);

      await api.post('/trading/order', payload);
      addToast(`${side.toUpperCase()} ${unitQty.toFixed(4)} ${symbol} placed`, 'success');
      setQuantity('');
      setLimitPrice('');
      setStopPrice('');
      setConfirm(false);
      refetch();
    } catch (err: any) {
      addToast(err?.response?.data?.detail ?? 'Order failed', 'error');
    } finally {
      setLoading(false);
    }
  }, [unitQty, symbol, side, orderType, limitPrice, stopPrice, stopLoss, takeProfit, addToast, refetch]);

  const isBuy = side === 'buy';

  return (
    <div className="flex flex-col lg:flex-row h-full" style={{ background: 'var(--bg-primary)' }}>

      {/* ── Chart panel ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0">

        {/* Symbol header */}
        <div
          className="flex items-center gap-4 px-5 py-3 flex-shrink-0"
          style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-subtle)' }}
        >
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="text-sm font-semibold mono rounded-lg px-3 py-1.5 transition-colors"
            style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
          >
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          {livePrice > 0 && (
            <span className="text-xl font-bold mono" style={{ color: 'var(--text-primary)' }}>
              ${livePrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          )}

          <div className="ml-auto flex items-center gap-2 text-xs px-2.5 py-1 rounded-full"
            style={{
              background: isConnected ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
              color: isConnected ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {isConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
            {isConnected ? 'Live' : 'Offline'}
          </div>
        </div>

        {/* Chart */}
        <div ref={chartContainerRef} className="flex-1 min-h-[300px]" />
      </div>

      {/* ── Order panel ──────────────────────────────────────────────────── */}
      <div
        className="w-full lg:w-[320px] flex-shrink-0 flex flex-col overflow-y-auto"
        style={{ background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border-subtle)' }}
      >
        {/* Buy / Sell tabs */}
        <div className="flex" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          {(['buy', 'sell'] as const).map(s => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className="flex-1 py-3.5 text-sm font-semibold uppercase tracking-wider transition-all"
              style={{
                background: side === s
                  ? s === 'buy' ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)'
                  : 'transparent',
                color: side === s
                  ? s === 'buy' ? 'var(--accent-green)' : 'var(--accent-red)'
                  : 'var(--text-muted)',
                borderBottom: side === s
                  ? `2px solid ${s === 'buy' ? 'var(--accent-green)' : 'var(--accent-red)'}`
                  : '2px solid transparent',
              }}
            >
              {s === 'buy' ? <TrendingUp size={14} className="inline mr-1.5" /> : <TrendingDown size={14} className="inline mr-1.5" />}
              {s}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-4">

          {/* Order type */}
          <div>
            <label className="block text-xs font-medium uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-muted)' }}>Order Type</label>
            <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
              {ORDER_TYPES.map(ot => (
                <button
                  key={ot}
                  onClick={() => setOrderType(ot)}
                  className="flex-1 py-1.5 text-xs font-medium capitalize transition-colors"
                  style={{
                    background: orderType === ot ? 'var(--accent-blue)' : 'transparent',
                    color: orderType === ot ? '#fff' : 'var(--text-muted)',
                  }}
                >
                  {ot.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Limit price (non-market) */}
          {orderType !== 'market' && (
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-muted)' }}>
                {orderType === 'stop_limit' ? 'Limit Price' : 'Limit Price'}
              </label>
              <input
                type="number"
                step="any"
                value={limitPrice}
                onChange={e => setLimitPrice(e.target.value)}
                placeholder={livePrice > 0 ? livePrice.toFixed(2) : '0.00'}
                className="w-full px-3 py-2 rounded-lg text-sm mono transition-colors"
                style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
              />
            </div>
          )}

          {/* Stop trigger price (stop_limit) */}
          {orderType === 'stop_limit' && (
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Stop Trigger
              </label>
              <input
                type="number"
                step="any"
                value={stopPrice}
                onChange={e => setStopPrice(e.target.value)}
                placeholder="0.00"
                className="w-full px-3 py-2 rounded-lg text-sm mono"
                style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
              />
            </div>
          )}

          {/* Quantity + USD toggle */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                Amount
              </label>
              <button
                onClick={() => { setUsdMode(m => !m); setQuantity(''); }}
                className="text-xs px-2 py-0.5 rounded transition-colors"
                style={{ color: 'var(--accent-blue)', background: 'rgba(59,130,246,0.08)' }}
              >
                {usdMode ? 'USD' : 'Units'} ↕
              </button>
            </div>
            <div className="relative">
              <input
                type="number"
                step="any"
                min="0"
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
                placeholder="0"
                className="w-full px-3 py-2 rounded-lg text-sm mono pr-14"
                style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
              />
              <span
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium"
                style={{ color: 'var(--text-muted)' }}
              >
                {usdMode ? 'USD' : symbol.replace('USDT', '')}
              </span>
            </div>
            {quantity && livePrice > 0 && (
              <p className="text-xs mt-1 mono" style={{ color: 'var(--text-muted)' }}>
                ≈ {usdMode
                  ? `${(parseFloat(quantity) / livePrice).toFixed(6)} ${symbol.replace('USDT', '')}`
                  : `$${(parseFloat(quantity) * livePrice).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                }
              </p>
            )}
          </div>

          {/* Available balance */}
          <div
            className="flex items-center justify-between text-xs px-3 py-2 rounded-lg"
            style={{ background: 'var(--bg-card)', color: 'var(--text-muted)' }}
          >
            <span>{isBuy ? 'Available' : 'Holdings'}</span>
            <span className="mono font-medium" style={{ color: 'var(--text-secondary)' }}>
              {isBuy
                ? `$${cashBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : holding ? `${holding.quantity} ${symbol.replace('USDT', '')}` : `0 ${symbol.replace('USDT', '')}`
              }
            </span>
          </div>

          {/* Risk management collapsible */}
          <div>
            <button
              onClick={() => setRiskOpen(o => !o)}
              className="w-full flex items-center justify-between text-xs font-medium uppercase tracking-wider py-1.5 transition-opacity hover:opacity-70"
              style={{ color: 'var(--text-muted)' }}
            >
              Risk Management
              {riskOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {riskOpen && (
              <div className="space-y-3 pt-2">
                <div>
                  <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Stop Loss</label>
                  <input
                    type="number"
                    step="any"
                    value={stopLoss}
                    onChange={e => setStopLoss(e.target.value)}
                    placeholder="0.00"
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
                <div>
                  <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Take Profit</label>
                  <input
                    type="number"
                    step="any"
                    value={takeProfit}
                    onChange={e => setTakeProfit(e.target.value)}
                    placeholder="0.00"
                    className="w-full px-3 py-2 rounded-lg text-sm mono"
                    style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Order summary */}
          {usdTotal > 0 && (
            <div
              className="rounded-lg px-3 py-3 space-y-1.5 text-xs"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}
            >
              <div className="flex justify-between">
                <span style={{ color: 'var(--text-muted)' }}>Units</span>
                <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                  {unitQty.toFixed(6)} {symbol.replace('USDT', '')}
                </span>
              </div>
              <div className="flex justify-between">
                <span style={{ color: 'var(--text-muted)' }}>Est. price</span>
                <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                  ${execPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex justify-between pt-1" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <span className="font-medium" style={{ color: 'var(--text-muted)' }}>Total</span>
                <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                  ${usdTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          )}

          {/* Submit */}
          {!confirm ? (
            <button
              onClick={() => { if (!unitQty) { addToast('Enter a valid quantity', 'error'); return; } setConfirm(true); }}
              className="w-full py-3 rounded-lg text-sm font-semibold uppercase tracking-wider transition-opacity hover:opacity-85 active:opacity-70"
              style={{
                background: isBuy ? 'var(--accent-green)' : 'var(--accent-red)',
                color: '#fff',
              }}
            >
              {isBuy ? 'Buy' : 'Sell'} {symbol.replace('USDT', '')}
            </button>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-center font-medium" style={{ color: 'var(--text-muted)' }}>
                Confirm {side.toUpperCase()} {unitQty.toFixed(6)} {symbol.replace('USDT', '')}
                {' '}@ ${execPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfirm(false)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium"
                  style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={loading}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-85 disabled:opacity-50"
                  style={{ background: isBuy ? 'var(--accent-green)' : 'var(--accent-red)', color: '#fff' }}
                >
                  {loading ? <RefreshCw size={14} className="inline animate-spin" /> : 'Confirm'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Holdings for this symbol */}
        {holding && (
          <div
            className="mt-auto mx-4 mb-4 rounded-lg p-3 space-y-1 text-xs"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}
          >
            <p className="font-semibold text-xs uppercase tracking-wider mb-2" style={{ color: 'var(--text-muted)' }}>
              Your {symbol.replace('USDT', '')} Position
            </p>
            <div className="flex justify-between">
              <span style={{ color: 'var(--text-muted)' }}>Qty</span>
              <span className="mono" style={{ color: 'var(--text-secondary)' }}>{holding.quantity}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--text-muted)' }}>Avg Entry</span>
              <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                ${holding.average_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="flex justify-between pt-1" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Unrealized P&L</span>
              <span
                className="mono font-medium"
                style={{ color: holding.unrealized_pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}
              >
                {holding.unrealized_pnl >= 0 ? '+' : ''}
                ${Math.abs(holding.unrealized_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
