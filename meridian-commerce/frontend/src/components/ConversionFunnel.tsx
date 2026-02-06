/**
 * ConversionFunnel Component
 * 
 * Visualizes the e-commerce conversion funnel with stages:
 * Page View -> Product View -> Add to Cart -> Checkout -> Order
 */

import React from 'react';

interface FunnelStage {
  name: string;
  count: number;
  conversion_rate: number;
}

interface ConversionFunnelProps {
  stages?: FunnelStage[];
  overallConversion?: number;
}

export const ConversionFunnel: React.FC<ConversionFunnelProps> = ({
  stages = [],
  overallConversion = 0,
}) => {
  // Get max count for scaling
  const maxCount = Math.max(...stages.map((s) => s.count), 1);

  // Stage display names - maps internal event names to user-friendly labels
  const stageLabels: Record<string, string> = {
    page_view: 'Page Views',
    product_view: 'Product Views',
    add_to_cart: 'Add to Cart',
    checkout_started: 'Checkout',
    order_completed: 'Orders',
  };

  const formatNumber = (num: number): string => {
    if (num >= 1000000) {
      return `${(num / 1000000).toFixed(1)}M`;
    }
    if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}K`;
    }
    return num.toString();
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Conversion Funnel</h3>
        <div className="text-sm text-gray-500">
          Overall: <span className="font-medium text-gray-900">{overallConversion.toFixed(2)}%</span>
        </div>
      </div>

      <div className="space-y-3">
        {stages.map((stage, index) => {
          const width = (stage.count / maxCount) * 100;
          const label = stageLabels[stage.name] || stage.name;
          const isLast = index === stages.length - 1;

          return (
            <div key={stage.name}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-600">{label}</span>
                <span className="text-sm font-medium">{formatNumber(stage.count)}</span>
              </div>
              
              <div className="relative h-8">
                <div 
                  className="h-full rounded transition-all duration-500"
                  style={{
                    width: `${width}%`,
                    background: `linear-gradient(90deg, 
                      hsl(${220 - index * 20}, 70%, 55%) 0%, 
                      hsl(${220 - index * 20}, 70%, 65%) 100%)`,
                  }}
                />
              </div>

              {/* Drop-off indicator between stages */}
              {!isLast && stages[index + 1] && (
                <div className="flex items-center mt-1 text-xs text-gray-400">
                  <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                      d="M19 9l-7 7-7-7" />
                  </svg>
                  <span>
                    {((1 - stages[index + 1].count / stage.count) * 100).toFixed(1)}% drop-off
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Stage-to-stage conversion rates */}
      <div className="mt-6 pt-4 border-t">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Stage Conversion Rates</h4>
        <div className="grid grid-cols-2 gap-2">
          {stages.slice(0, -1).map((stage, index) => {
            const nextStage = stages[index + 1];
            const label = stageLabels[stage.name] || stage.name;
            const nextLabel = stageLabels[nextStage.name] || nextStage.name;
            
            return (
              <div key={`${stage.name}-${nextStage.name}`} className="text-xs">
                <span className="text-gray-500">
                  {label} → {nextLabel}:
                </span>
                <span className="ml-1 font-medium">
                  {((nextStage.count / stage.count) * 100).toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ConversionFunnel;
