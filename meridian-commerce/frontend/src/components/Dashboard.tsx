/**
 * Dashboard Component
 * 
 * Main merchant dashboard showing key metrics and analytics.
 * Displays data from Pulse analytics engine.
 */

import React, { useEffect, useState } from 'react';
import { MetricCard } from './MetricCard';
import { ConversionFunnel } from './ConversionFunnel';
import { RevenueChart } from './RevenueChart';
import { useDashboard } from '../hooks/useDashboard';

interface DashboardProps {
  merchantId: string;
}

type TimeWindow = 'realtime' | 'hourly' | 'daily' | 'weekly' | 'monthly';

export const Dashboard: React.FC<DashboardProps> = ({ merchantId }) => {
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('daily');
  
  const { 
    data: dashboardData, 
    isLoading, 
    error,
    refetch 
  } = useDashboard(merchantId, timeWindow);

  // Auto-refresh for realtime view
  useEffect(() => {
    if (timeWindow === 'realtime') {
      const interval = setInterval(() => {
        refetch();
      }, 30000); // 30 seconds
      
      return () => clearInterval(interval);
    }
  }, [timeWindow, refetch]);

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="p-6 bg-red-50 rounded-lg">
        <h3 className="text-red-800 font-semibold">Error loading dashboard</h3>
        <p className="text-red-600">{error.message}</p>
        <button 
          onClick={() => refetch()}
          className="mt-4 px-4 py-2 bg-red-600 text-white rounded"
        >
          Retry
        </button>
      </div>
    );
  }

  const { summary, funnel, revenueChart, topProducts, trafficSources } = 
    dashboardData?.widgets || {};

  return (
    <div className="space-y-6">
      {/* Time Window Selector */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <TimeWindowSelector 
          value={timeWindow} 
          onChange={setTimeWindow} 
        />
      </div>

      {/* Summary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="GMV"
          value={formatCurrency(summary?.gmv?.value)}
          change={summary?.gmv?.change_percent}
          trend={summary?.gmv?.trend}
          tooltip="Gross Merchandise Value - total order subtotals"
        />
        <MetricCard
          title="Orders"
          value={formatNumber(summary?.orders?.value)}
          change={summary?.orders?.change_percent}
          trend={summary?.orders?.trend}
        />
        <MetricCard
          title="Conversion Rate"
          value={formatPercent(summary?.conversion_rate?.value)}
          change={summary?.conversion_rate?.change_percent}
          trend={summary?.conversion_rate?.trend}
        />
        <MetricCard
          title="Avg Order Value"
          value={formatCurrency(summary?.aov?.value)}
          change={summary?.aov?.change_percent}
          trend={summary?.aov?.trend}
          tooltip="AOV = GMV / Orders"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RevenueChart 
          data={revenueChart?.data}
          granularity={revenueChart?.granularity}
        />
        <ConversionFunnel 
          stages={funnel?.stages}
          overallConversion={funnel?.overall_conversion}
        />
      </div>

      {/* Tables Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TopProductsTable products={topProducts?.products} />
        <TrafficSourcesChart sources={trafficSources?.sources} />
      </div>
    </div>
  );
};

// Time window selector component
const TimeWindowSelector: React.FC<{
  value: TimeWindow;
  onChange: (value: TimeWindow) => void;
}> = ({ value, onChange }) => {
  const options: { value: TimeWindow; label: string }[] = [
    { value: 'realtime', label: 'Real-time' },
    { value: 'hourly', label: 'Hourly' },
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
  ];

  return (
    <div className="flex space-x-1 bg-gray-100 rounded-lg p-1">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            value === option.value
              ? 'bg-white text-gray-900 shadow'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};

// Loading skeleton
const DashboardSkeleton: React.FC = () => (
  <div className="space-y-6 animate-pulse">
    <div className="grid grid-cols-4 gap-6">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-32 bg-gray-200 rounded-lg" />
      ))}
    </div>
    <div className="grid grid-cols-2 gap-6">
      <div className="h-80 bg-gray-200 rounded-lg" />
      <div className="h-80 bg-gray-200 rounded-lg" />
    </div>
  </div>
);

// Top products table
const TopProductsTable: React.FC<{ products?: any[] }> = ({ products }) => (
  <div className="bg-white rounded-lg shadow p-6">
    <h3 className="text-lg font-semibold mb-4">Top Products</h3>
    <table className="w-full">
      <thead>
        <tr className="text-left text-gray-500 text-sm">
          <th className="pb-2">Product</th>
          <th className="pb-2 text-right">Revenue</th>
          <th className="pb-2 text-right">Orders</th>
        </tr>
      </thead>
      <tbody>
        {products?.map((product, i) => (
          <tr key={product.product_id} className="border-t">
            <td className="py-2">{product.name}</td>
            <td className="py-2 text-right">{formatCurrency(product.revenue)}</td>
            <td className="py-2 text-right">{product.orders}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// Traffic sources chart
const TrafficSourcesChart: React.FC<{ sources?: any[] }> = ({ sources }) => (
  <div className="bg-white rounded-lg shadow p-6">
    <h3 className="text-lg font-semibold mb-4">Traffic Sources</h3>
    <div className="space-y-3">
      {sources?.map((source) => (
        <div key={source.value} className="flex items-center">
          <div className="w-24 text-sm text-gray-600">{source.value}</div>
          <div className="flex-1 mx-4">
            <div className="h-4 bg-gray-100 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${source.percentage}%` }}
              />
            </div>
          </div>
          <div className="w-20 text-right text-sm">
            {formatCurrency(source.revenue)}
          </div>
        </div>
      ))}
    </div>
  </div>
);

// Formatting helpers
const formatCurrency = (value?: number): string => {
  if (value === undefined) return '--';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatNumber = (value?: number): string => {
  if (value === undefined) return '--';
  return new Intl.NumberFormat('en-US').format(value);
};

const formatPercent = (value?: number): string => {
  if (value === undefined) return '--';
  return `${value.toFixed(2)}%`;
};

export default Dashboard;
