/**
 * Utility functions for handling image URLs across the application
 */

/**
 * Get the API base URL dynamically
 */
const getApiBaseUrl = (): string => {
  // Try to get from environment variable first
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) {
    return envUrl.replace('/api', ''); // Remove /api suffix to get base URL
  }
  
  // If running in development with Vite, use localhost
  if (typeof window !== 'undefined') {
    const isDevelopment = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isDevelopment) {
      return 'http://localhost:8000';
    }
    // In production, use the current protocol and host
    return window.location.origin.replace(/:\d+$/, ':8000');
  }
  return 'http://localhost:8000';
};

/**
 * Convert relative image URLs to absolute URLs
 * Handles both relative paths (/media/...) and already absolute URLs
 * @param url - Image URL (relative or absolute)
 * @returns Absolute URL or fallback image path
 */
export function getAbsoluteImageUrl(url: string | null | undefined): string {
  if (!url) {
    return '/placeholder.jpg';
  }

  // Already an absolute URL
  if (url.startsWith('http')) {
    return url;
  }

  // Relative URL - prepend API base URL
  const baseUrl = getApiBaseUrl();
  return `${baseUrl}${url}`;
}

/**
 * Extract and normalize image URLs from a product image object
 * @param img - Product image object with image and image_url properties
 * @returns Absolute image URL
 */
export function getProductImageUrl(img: any): string {
  if (!img) {
    console.warn('⚠️ Image object is null/undefined');
    return '/placeholder.jpg';
  }
  
  // Try image_url first (should be absolute from backend)
  // Fall back to image field if image_url is not available
  const url = img.image_url || img.image;
  
  if (!url) {
    console.warn('⚠️ Image URL not found in object:', img);
    return '/placeholder.jpg';
  }

  const result = getAbsoluteImageUrl(url);
  console.log('✅ Image URL processed:', { input: url, output: result });
  return result;
}

/**
 * Get multiple product images as absolute URLs
 * @param images - Array of product image objects
 * @returns Array of absolute image URLs
 */
export function getProductImageUrls(images: any[]): string[] {
  if (!Array.isArray(images) || images.length === 0) {
    return ['/placeholder.jpg'];
  }

  return images.map(getProductImageUrl);
}
