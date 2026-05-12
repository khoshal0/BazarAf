// File: src/lib/api-client.ts

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

interface RequestOptions {
  method: string;
  headers: Record<string, string>;
  body?: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getAuthToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private async request<T>(
    endpoint: string,
    options: Partial<RequestOptions> = {}
  ): Promise<T> {
    const token = this.getAuthToken();
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...options,
      headers,
    };

    const url = `${this.baseUrl}${endpoint}`;
    
    console.log('🌐 API Request:', {
      method: options.method || 'GET',
      url,
      headers,
      body: options.body ? JSON.parse(options.body) : undefined
    });

    try {
      const response = await fetch(url, config);

      // Log response details
      console.log('📥 API Response:', {
        status: response.status,
        statusText: response.statusText,
        url: response.url
      });

      // Handle 204 No Content
      if (response.status === 204) {
        return {} as T;
      }

      // Handle non-JSON responses
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        console.log('📄 Non-JSON Response:', text);
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
        }
        
        return {} as T;
      }

      const data = await response.json();

      if (!response.ok) {
        console.error('❌ API Error Response:', data);
        throw new Error(
          data.detail || 
          data.message || 
          data.error ||
          `HTTP ${response.status}: ${response.statusText}`
        );
      }

      console.log('✅ API Success:', data);
      return data;
    } catch (error) {
      console.error('❌ API Request Failed:', error);
      throw error;
    }
  }

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    let url = endpoint;
    
    if (params && Object.keys(params).length > 0) {
      const queryString = new URLSearchParams(params).toString();
      url = `${endpoint}?${queryString}`;
    }

    return this.request<T>(url, {
      method: 'GET',
    });
  }

  async post<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async patch<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async put<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete<T = void>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'DELETE',
    });
  }

  // Special method for multipart/form-data (file uploads)
  async postFormData<T>(endpoint: string, formData: FormData): Promise<T> {
    const token = this.getAuthToken();
    
    const headers: Record<string, string> = {};
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Don't set Content-Type for FormData - browser will set it with boundary
    
    const config: RequestInit = {
      method: 'POST',
      headers,
      body: formData,
    };

    const url = `${this.baseUrl}${endpoint}`;
    
    console.log('🌐 FormData Request:', {
      method: 'POST',
      url,
      headers
    });

    try {
      const response = await fetch(url, config);

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
        }
        
        return {} as T;
      }

      const data = await response.json();

      if (!response.ok) {
        console.error('❌ API Error Response:', data);
        throw new Error(
          data.detail || 
          data.message || 
          data.error ||
          `HTTP ${response.status}: ${response.statusText}`
        );
      }

      console.log('✅ FormData Success:', data);
      return data;
    } catch (error) {
      console.error('❌ FormData Request Failed:', error);
      throw error;
    }
  }

  async patchFormData<T>(endpoint: string, formData: FormData): Promise<T> {
    const token = this.getAuthToken();
    
    const headers: Record<string, string> = {};
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = {
      method: 'PATCH',
      headers,
      body: formData,
    };

    const url = `${this.baseUrl}${endpoint}`;
    
    console.log('🌐 PATCH FormData Request:', {
      method: 'PATCH',
      url,
      headers
    });

    try {
      const response = await fetch(url, config);

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
        }
        
        return {} as T;
      }

      const data = await response.json();

      if (!response.ok) {
        console.error('❌ API Error Response:', data);
        throw new Error(
          data.detail || 
          data.message || 
          data.error ||
          `HTTP ${response.status}: ${response.statusText}`
        );
      }

      console.log('✅ PATCH FormData Success:', data);
      return data;
    } catch (error) {
      console.error('❌ PATCH FormData Request Failed:', error);
      throw error;
    }
  }
}

export const apiClient = new ApiClient(API_BASE_URL);