'use client';

import { useEffect, useState } from 'react';
import api from '@/lib/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import withAuth from '../../components/withAuth';
import LivePrice from '../../components/LivePrice';

const Dashboard = () => {
  const [user, setUser] = useState(null);
  const [portfolio, setPortfolio] = useState({ assets: [] });
  const [marketPrices, setMarketPrices] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const authMeResponse = await api.get('/auth/me');
        setUser(authMeResponse.data);

        // Correct endpoint: /trading/portfolio (not /portfolio)
        const portfolioResponse = await api.get('/trading/portfolio');
        setPortfolio(portfolioResponse.data);

        // Fetch prices for each symbol individually via the correct REST endpoint.
        // /market/prices/{symbol} returns {exchange: {price, volume, ...}, ...}
        // Normalise to a flat {SYMBOL: {price}} map for the chart.
        const [btcRes, ethRes, solRes] = await Promise.all([
          api.get('/market/prices/BTCUSDT'),
          api.get('/market/prices/ETHUSDT'),
          api.get('/market/prices/SOLUSDT'),
        ]);

        const extractPrice = (data) => {
          const entry = data.binance || data.bybit || data.kraken || {};
          return { price: entry.price || 0 };
        };

        setMarketPrices({
          BTCUSDT: extractPrice(btcRes.data),
          ETHUSDT: extractPrice(ethRes.data),
          SOLUSDT: extractPrice(solRes.data),
        });
      } catch (err) {
        setError(err.message);
      }
    };

    fetchData();
  }, []);

  if (error) return <div className="text-red-500">Error: {error}</div>;

  const chartData = portfolio.assets.map(asset => ({
    name: asset.symbol,
    price: marketPrices[asset.symbol]?.price || 0,
    change_24h: marketPrices[asset.symbol]?.change_24h || 0
  }));

  return (
    <div className="p-6 dark:bg-gray-900">
      <h1 className="text-3xl font-bold text-white mb-6">Dashboard</h1>
      <h2 className="text-xl font-semibold text-white">Live Prices</h2>
      <LivePrice symbol="BTCUSDT" />
      <LivePrice symbol="ETHUSDT" />
      <div className="mt-4">
        <LineChart width={730} height={250} data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="price" stroke="#8884d8" activeDot={{ r: 8 }} />
          <Line type="monotone" dataKey="change_24h" stroke="#82ca9d" />
        </LineChart>
      </div>
    </div>
  );
};

export default withAuth(Dashboard);
