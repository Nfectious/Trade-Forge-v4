'use client';

import { usePriceStream } from '../hooks/usePriceStream';

// exchanges prop removed — usePriceStream stores prices[symbol] as a bare number
// keyed by symbol only (e.g. prices["BTCUSDT"] = 65000.0). There is no per-exchange
// breakdown available from the hook; the last received price is shown.
const LivePrice = ({ symbol = 'BTCUSDT' }) => {
  const { prices, isConnected } = usePriceStream();

  const formatPrice = (price) => {
    if (price == null || price === 0) return '---';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(price);
  };

  // prices[symbol] is the raw number pushed by usePriceStream
  const currentPrice = prices[symbol];

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      {/* Header with connection indicator */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">{symbol}</h3>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-xs text-gray-400">
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Price display */}
      <div className="text-2xl font-bold text-green-400">
        {formatPrice(currentPrice)}
      </div>

      {/* Last Update */}
      {currentPrice != null && (
        <div className="mt-3 pt-2 border-t border-gray-700 text-xs text-gray-500">
          Last update: {new Date().toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};

export default LivePrice;
