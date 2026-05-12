// File: src/services/dashboard.ts
import { apiClient } from '../lib/api-client';
import { 
  DashboardResponse, 
  LogisticsStats, 
  OrderStatusCounts, 
  PayoutSummary,
  Order,
  PaginatedResponse 
} from '../types/api';

export const dashboardService = {
  // ==================== DASHBOARD STATS ====================
  async getStats(): Promise<DashboardResponse> {
    try {
      const response = await apiClient.get<DashboardResponse>('/dashboard/');
      console.log('✅ Dashboard stats loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load dashboard stats:', error);
      throw error;
    }
  },

  async getLogisticsStats(): Promise<LogisticsStats> {
    try {
      const response = await apiClient.get<LogisticsStats>('/logistics/stats/');
      console.log('✅ Logistics stats loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load logistics stats:', error);
      throw error;
    }
  },



  // ==================== ORDER STATUS COUNTS ====================
  async getOrderStatusCounts(): Promise<OrderStatusCounts> {
    try {
      const response = await apiClient.get<OrderStatusCounts>('/orders/status-counts/');
      console.log('✅ Order status counts loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load order status counts:', error);
      throw error;
    }
  },

  // ==================== PAYOUT SUMMARY ====================
  async getPayoutSummary(): Promise<PayoutSummary> {
    try {
      const response = await apiClient.get<PayoutSummary>('/payouts/summary/');
      console.log('✅ Payout summary loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load payout summary:', error);
      throw error;
    }
  },

  // ==================== RECENT ORDERS ====================
  async getRecentOrders(limit: number = 10): Promise<Order[]> {
    try {
      const response = await apiClient.get<PaginatedResponse<Order>>('/orders/', {
        page_size: limit.toString(),
        ordering: '-created_at'
      });
      console.log('✅ Recent orders loaded:', response);
      return response.results;
    } catch (error) {
      console.error('❌ Failed to load recent orders:', error);
      throw error;
    }
  },

  // ==================== UPDATE ORDER STATUS (ADMIN) ====================
  async updateOrderStatus(
  orderId: string,
  status: string
): Promise<{ success: boolean; status: string }> {
  try {
    const response = await apiClient.patch<{ success: boolean; status: string }>(
      `/orders/${orderId}/update_status/`,
      { status }
    );

    console.log('✅ Order status updated:', response.status);
    return response;
  } catch (error) {
    console.error('❌ Failed to update order status:', error);
    throw error;
  }
},





};