/**
 * RevenueChart Component
 * 
 * Time series chart for revenue/GMV visualization.
 * Uses Chart.js for rendering.
 */

import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { format, parseISO } from 'date-fns';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface DataPoint {
  timestamp: string;
  value: number;
}

interface RevenueChartProps {
  data?: DataPoint[];
  granularity?: 'hour' | 'day' | 'week';
  title?: string;
}

export const RevenueChart: React.FC<RevenueChartProps> = ({
  data = [],
  granularity = 'day',
  title = 'Revenue',
}) => {
  const chartData = useMemo(() => {
    const labels = data.map((point) => {
      const date = parseISO(point.timestamp);
      
      switch (granularity) {
        case 'hour':
          return format(date, 'HH:mm');
        case 'day':
          return format(date, 'MMM d');
        case 'week':
          return format(date, 'MMM d');
        default:
          return format(date, 'MMM d');
      }
    });

    const values = data.map((point) => point.value);

    return {
      labels,
      datasets: [
        {
          label: title,
          data: values,
          fill: true,
          borderColor: 'rgb(59, 130, 246)', // Blue
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.4,
          pointRadius: 2,
          pointHoverRadius: 6,
        },
      ],
    };
  }, [data, granularity, title]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: (context: any) => {
            const value = context.raw as number;
            return `$${value.toLocaleString()}`;
          },
        },
      },
    },
    scales: {
      x: {
        grid: {
          display: false,
        },
      },
      y: {
        beginAtZero: true,
        ticks: {
          callback: (value: number) => `$${(value / 1000).toFixed(0)}K`,
        },
      },
    },
    interaction: {
      intersect: false,
      mode: 'index' as const,
    },
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div className="h-64">
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
};

export default RevenueChart;
