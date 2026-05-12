import { apiClient } from '../lib/api-client';
import { Vendor, PaginatedResponse } from '../types/api';

export const vendorService = {
  async getVendors(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
  }): Promise<PaginatedResponse<Vendor>> {
    const queryParams: Record<string, string> = {};
    
    if (params?.page) queryParams.page = params.page.toString();
    if (params?.page_size) queryParams.page_size = params.page_size.toString();
    if (params?.status) queryParams.status = params.status;
    if (params?.search) queryParams.search = params.search;
    
    return apiClient.get('/vendors/', queryParams);
  },

  async getVendor(vendorId: string): Promise<Vendor> {
    return apiClient.get(`/vendors/${vendorId}/`);
  },

  async approveVendor(vendorId: string): Promise<{ status: string; message: string }> {
    return apiClient.post(`/vendors/${vendorId}/approve/`, {});
  },

  async rejectVendor(vendorId: string, reason: string = ''): Promise<{ status: string; message: string }> {
    return apiClient.post(`/vendors/${vendorId}/reject/`, { reason });
  },

  async suspendVendor(vendorId: string): Promise<{ status: string; message: string }> {
    return apiClient.post(`/vendors/${vendorId}/suspend/`, {});
  },

  async getVendorStats(vendorId: string): Promise<any> {
    return apiClient.get(`/vendors/${vendorId}/stats/`);
  },
};