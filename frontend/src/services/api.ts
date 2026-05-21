// File: frontend/src/services/api.ts

import axios from 'axios';

// Base URL for your Django backend
const DEFAULT_API_BASE_URL = import.meta.env.PROD
  ? 'https://bazaraf-production.up.railway.app/api'
  : 'http://localhost:8000/api';
const API_BASE_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');

// Create axios instance
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests if available
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Refresh token on 401 error
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        const response = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
          refresh: refreshToken,
        });

        const { access } = response.data;
        localStorage.setItem('access_token', access);

        originalRequest.headers.Authorization = `Bearer ${access}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Authentication API calls
export const authAPI = {
  login: async (identifier: string, password: string) => {
    const response = await api.post('/auth/login/', { identifier, password });
    return response.data;
  },

  verifyTwoFactor: async (challengeToken: string, code: string) => {
    const response = await api.post('/auth/2fa/verify/', {
      challenge_token: challengeToken,
      code,
    });
    return response.data;
  },

  register: async (userData: {
    full_name: string;
    phone: string;
    email: string;
    password: string;
    password_confirm: string;
    role: string;
    frontend_url?: string;
  }) => {
    const response = await api.post('/auth/register/', userData);
    return response.data;
  },

  logout: async (refreshToken: string) => {
    const response = await api.post('/auth/logout/', { refresh: refreshToken });
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/user/');
    return response.data;
  },
  
  googleAuth: async (credential: string) => {
    const response = await api.post('/auth/google/', { credential });
    return response.data;
  },

  resendVerificationEmail: async (email: string) => {
    const response = await api.post('/auth/resend-verification/', { email });
    return response.data;
  },
};
// frontend/src/services/api.ts
export const createOrder = async (orderData: any) => {
  const response = await api.post('/orders/checkout/', orderData); // ✅ Correct URL
  return response.data;
};


// Product API calls
export const getProducts = async (params?: { page?: number; page_size?: number; category?: string }) => {
  const response = await api.get('/products/', { params });
  return response.data;
};

export const getCategories = async () => {
  const response = await api.get('/products/', { params: { page_size: 1000 } });
  const products = response.data.results;

  const categoryCount: Record<string, number> = {};
  products.forEach((product: any) => {
    categoryCount[product.category] = (categoryCount[product.category] || 0) + 1;
  });

  return Object.entries(categoryCount).map(([name, count]) => ({
    name,
    productCount: count,
  }));
};

// Notification API calls
export const notificationAPI = {
  // Get all notifications
  getNotifications: async () => {
    const response = await api.get('/notifications/');
    const payload = response.data;
    return Array.isArray(payload)
      ? payload
      : payload.results ?? payload;
  },

  // Get unread count
  getUnreadCount: async () => {
    const response = await api.get('/notifications/unread_count/');
    return response.data.count;
  },

  // Mark as read
  markAsRead: async (notificationId: string) => {
    const response = await api.post(`/notifications/${notificationId}/mark_as_read/`);
    return response.data;
  },

  // Mark all as read
  markAllAsRead: async () => {
    const response = await api.post('/notifications/mark_all_read/');
    return response.data;
  },
};

export default api;