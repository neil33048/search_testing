/**
 * useDashboard Hook
 * 
 * Fetches dashboard data from Pulse API.
 * Handles caching, loading states, and error handling.
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

interface DashboardWidget {
  summary?: {
    gmv: { value: number; change_percent: number; trend: 'up' | 'down' };
    orders: { value: number; change_percent: number; trend: 'up' | 'down' };
    conversion_rate: { value: number; change_percent: number; trend: 'up' | 'down' };
    aov: { value: number; change_percent: number; trend: 'up' | 'down' };
  };
  funnel?: {
    stages: Array<{ name: string; count: number; conversion_rate: number }>;
    overall_conversion: number;
  };
  revenueChart?: {
    data: Array<{ timestamp: string; value: number }>;
    granularity: string;
  };
  topProducts?: {
    products: Array<{
      product_id: string;
      name: string;
      revenue: number;
      orders: number;
    }>;
  };
  trafficSources?: {
    sources: Array<{
      value: string;
      revenue: number;
      percentage: number;
    }>;
  };
}

interface DashboardData {
  merchant_id: string;
  window: string;
  generated_at: string;
  widgets: DashboardWidget;
}

type TimeWindow = 'realtime' | 'hourly' | 'daily' | 'weekly' | 'monthly';

/**
 * Hook to fetch dashboard data from Pulse API
 * 
 * @param merchantId - The merchant ID
 * @param window - Time window for metrics
 * @returns Query result with dashboard data
 */
export function useDashboard(merchantId: string, window: TimeWindow = 'daily') {
  return useQuery<DashboardData, Error>({
    queryKey: ['dashboard', merchantId, window],
    queryFn: async () => {
      const response = await api.get('/analytics/dashboard', {
        params: { window },
      });
      return response.data;
    },
    // Stale time based on window
    staleTime: getStaleTime(window),
    // Refetch interval for realtime
    refetchInterval: window === 'realtime' ? 30000 : false,
  });
}

/**
 * Get appropriate stale time based on time window
 */
function getStaleTime(window: TimeWindow): number {
  switch (window) {
    case 'realtime':
      return 10 * 1000; // 10 seconds
    case 'hourly':
      return 60 * 1000; // 1 minute
    case 'daily':
      return 5 * 60 * 1000; // 5 minutes
    case 'weekly':
    case 'monthly':
      return 30 * 60 * 1000; // 30 minutes
    default:
      return 5 * 60 * 1000;
  }
}

/**
 * Hook to fetch single metric
 */
export function useMetric(
  merchantId: string, 
  metricName: string,
  window: TimeWindow = 'daily'
) {
  return useQuery({
    queryKey: ['metric', merchantId, metricName, window],
    queryFn: async () => {
      const response = await api.get(`/analytics/metrics/${metricName}`, {
        params: { window },
      });
      return response.data;
    },
    staleTime: getStaleTime(window),
  });
}

/**
 * Hook to fetch GMV time series
 */
export function useGMVTimeSeries(
  merchantId: string,
  window: TimeWindow = 'daily',
  granularity: string = 'hour'
) {
  return useQuery({
    queryKey: ['gmv-timeseries', merchantId, window, granularity],
    queryFn: async () => {
      const response = await api.get('/analytics/gmv', {
        params: { window },
      });
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch conversion funnel
 */
export function useConversionFunnel(merchantId: string, window: TimeWindow = 'daily') {
  return useQuery({
    queryKey: ['funnel', merchantId, window],
    queryFn: async () => {
      const response = await api.get('/analytics/funnel', {
        params: { window },
      });
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}
