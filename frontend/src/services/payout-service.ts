// File: src/services/payout-service.ts
import { apiClient } from '../lib/api-client';
import { Payout, PaginatedResponse, PayoutSummary } from '../types/api';

export const payoutService = {
  // ==================== GET PAYOUTS ====================
  async getPayouts(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    vendor_id?: string;
  }): Promise<PaginatedResponse<Payout>> {
    const queryParams: Record<string, string> = {};
    
    if (params?.page) queryParams.page = params.page.toString();
    if (params?.page_size) queryParams.page_size = params.page_size.toString();
    if (params?.status) queryParams.status = params.status;
    if (params?.vendor_id) queryParams.vendor_id = params.vendor_id;
    
    try {
      const response = await apiClient.get<PaginatedResponse<Payout>>('/payouts/', queryParams);
      console.log('✅ Payouts loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load payouts:', error);
      throw error;
    }
  },

  // ==================== MARK PAYOUT AS PAID ====================
  async markPaid(payoutId: string): Promise<{ status: string; message: string }> {
    try {
      const response = await apiClient.post<{ status: string; message: string }>(
        `/payouts/${payoutId}/mark_paid/`, 
        {}
      );
      console.log('✅ Payout marked as paid:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to mark payout as paid:', error);
      throw error;
    }
  },

  // ==================== GET PAYOUT SUMMARY ====================
  async getSummary(): Promise<PayoutSummary> {
    try {
      const response = await apiClient.get<PayoutSummary>('/payouts/summary/');
      console.log('✅ Payout summary loaded:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to load payout summary:', error);
      throw error;
    }
  },

  // ==================== GET PENDING PAYOUTS ====================
  async getPendingPayouts(): Promise<Payout[]> {
    try {
      const response = await apiClient.get<PaginatedResponse<Payout>>('/payouts/', {
        status: 'pending',
        page_size: '100'
      });
      console.log('✅ Pending payouts loaded:', response);
      return response.results;
    } catch (error) {
      console.error('❌ Failed to load pending payouts:', error);
      throw error;
    }
  },

  // ==================== GET PAID PAYOUTS ====================
  async getPaidPayouts(): Promise<Payout[]> {
    try {
      const response = await apiClient.get<PaginatedResponse<Payout>>('/payouts/', {
        status: 'paid',
        page_size: '100'
      });
      console.log('✅ Paid payouts loaded:', response);
      return response.results;
    } catch (error) {
      console.error('❌ Failed to load paid payouts:', error);
      throw error;
    }
  },

  // ==================== GET VENDOR PAYOUTS ====================
  async getVendorPayouts(vendorId: string): Promise<Payout[]> {
    try {
      const response = await apiClient.get<PaginatedResponse<Payout>>('/payouts/', {
        vendor_id: vendorId,
        page_size: '100'
      });
      console.log(`✅ Vendor ${vendorId} payouts loaded:`, response);
      return response.results;
    } catch (error) {
      console.error(`❌ Failed to load vendor ${vendorId} payouts:`, error);
      throw error;
    }
  },

  // ==================== BULK MARK AS PAID ====================
  async bulkMarkPaid(payoutIds: string[]): Promise<{ success: boolean; updated: number }> {
    try {
      const response = await apiClient.post<{ success: boolean; updated: number }>(
        '/payouts/bulk-mark-paid/', 
        { payout_ids: payoutIds }
      );
      console.log('✅ Bulk mark paid completed:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to bulk mark paid:', error);
      throw error;
    }
  },

  // ==================== GENERATE PAYOUTS ====================
  async generatePayouts(): Promise<{ status: string; message: string; created: number }> {
    try {
      const response = await apiClient.post<{ status: string; message: string; created: number }>(
        '/payouts/generate/', 
        {}
      );
      console.log('✅ Payouts generated:', response);
      return response;
    } catch (error) {
      console.error('❌ Failed to generate payouts:', error);
      throw error;
    }
  },
};