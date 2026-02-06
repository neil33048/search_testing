/**
 * API Service
 * 
 * Axios instance configured for Meridian Commerce API.
 * Handles authentication, error handling, and request/response interceptors.
 */

import axios, { AxiosError, AxiosResponse } from 'axios';

// API base URL from environment
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

/**
 * Create axios instance with default config
 */
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor - add auth token
 */
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('api_token');
    
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Add request ID for tracing
    config.headers['X-Request-ID'] = generateRequestId();
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor - handle errors
 */
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    // Handle specific error codes
    if (error.response) {
      const { status, data } = error.response;
      
      switch (status) {
        case 401:
          // Unauthorized - redirect to login
          localStorage.removeItem('api_token');
          window.location.href = '/login';
          break;
          
        case 403:
          // Forbidden - show permission error
          console.error('Permission denied:', data);
          break;
          
        case 429:
          // Rate limited - show warning
          console.warn('Rate limit exceeded. Retry after:', 
            error.response.headers['retry-after']);
          break;
          
        case 500:
          // Server error - log and show generic message
          console.error('Server error:', data);
          break;
      }
    }
    
    return Promise.reject(error);
  }
);

/**
 * Generate unique request ID
 */
function generateRequestId(): string {
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * API endpoints grouped by resource
 */
export const endpoints = {
  // Analytics (Pulse)
  analytics: {
    dashboard: (params?: { window?: string }) => 
      api.get('/analytics/dashboard', { params }),
    gmv: (params?: { window?: string }) => 
      api.get('/analytics/gmv', { params }),
    funnel: (params?: { window?: string }) => 
      api.get('/analytics/funnel', { params }),
    realtime: () => 
      api.get('/analytics/realtime'),
  },
  
  // Recommendations (Catalyst)
  recommendations: {
    get: (data: {
      placement: string;
      user_id?: string;
      source_product_id?: string;
      limit?: number;
    }) => api.post('/recommendations', data),
    
    similar: (productId: string, limit?: number) => 
      api.get(`/recommendations/similar/${productId}`, { 
        params: { limit } 
      }),
    
    popular: (categoryId?: string) => 
      api.get('/recommendations/popular', { 
        params: { category_id: categoryId } 
      }),
  },
  
  // Events (Beacon)
  events: {
    track: (event: {
      event_type: string;
      properties?: Record<string, any>;
      context?: Record<string, any>;
    }) => api.post('/events/track', event),
    
    trackBatch: (events: any[]) => 
      api.post('/events/batch', { events }),
  },
  
  // Merchant
  merchant: {
    me: () => api.get('/merchants/me'),
    settings: () => api.get('/merchants/me/settings'),
    updateSettings: (settings: any) => 
      api.patch('/merchants/me/settings', settings),
    tier: () => api.get('/merchants/me/tier'),
  },
};

export default api;
