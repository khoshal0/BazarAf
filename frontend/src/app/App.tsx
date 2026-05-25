// File: frontend/src/App.tsx

import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { CustomerHome } from '@/app/components/CustomerHome';
import { Checkout } from '@/app/components/Checkout';
import { OrderTracking } from '@/app/components/OrderTracking';
import { VendorDashboard } from '@/app/components/VendorDashboard';
import { AdminPanel } from '@/app/components/AdminPanel';
import { Toaster } from '@/app/components/ui/sonner';
import { toast } from 'sonner';
import { adminRoutes } from '@/routes/adminRoutes';

import AddProduct from '../pages/addProduct';
import ProductListing from '../pages/ProductListing';
import ProductDetail from '../pages/ProductDetail';
import CategoryManagement from '../pages/CategoryManagement';
import ProductApproval from '../pages/ProductApproval';
import StoreFront from '../pages/StoreFront';
import VendorProfilePage from '../app/pages/vendor/VendorProfilePage';
import VendorSettingsPage from '../app/pages/vendor/VendorSettingsPage';
import VendorReviewsPage from '../app/pages/vendor/VendorReviewsPage';

// Import Auth Pages
import ProtectedRoute from '../utils/ProtectedRoute';
import Login from '../pages/Login';
import SignUp from '../pages/SignUp';
import ForgotPassword from '../pages/ForgotPassword';
import VerifyEmail from '../pages/VerifyEmail';
import VerifyEmailPending from '../pages/VerifyEmailPending';
import ResetPassword from '../pages/ResetPassword';
import Landing from '../pages/Landing';
import BecomeSeller from '../pages/BecomeSeller';
import HelpSupport from '../pages/HelpSupport';
import MyProfile from '../pages/MyProfile';
import MyOrders from '../pages/MyOrders';
import Wishlist from '../pages/Wishlist';
import MyReviews from '../pages/MyReviews';
import Cart from './components/Cart';
import SellerRegistration from '../pages/SellerRegistration';
import Notifications from '../pages/Notifications';
import VendorOrderDetail from '../pages/VendorOrderDetail';
//import ProtectedRoute from './components/ProtectedRoute';

// Define CartItem interface
interface CartItem {
  id: string;
  name: string;
  price: number;
  image: string;
  quantity: number;
  slug?: string;
  seller: {
    name: string;
  };
}

// Wrapper component to handle product detail from location state
// In App.tsx, update ProductDetailWrapper:

// Note: ProductDetailWrapper removed - using new ProductDetail from pages instead

export default function App() {
  const [pageData, setPageData] = useState<any>(null);
  
  // Initialize RTL support based on current language
  useEffect(() => {
    const checkLanguageAndSetDirection = () => {
      const currentLng = localStorage.getItem('i18nextLng') || 'en';
      if (currentLng === 'fa' || currentLng === 'ps') {
        document.documentElement.dir = 'rtl';
        document.documentElement.lang = currentLng;
      } else {
        document.documentElement.dir = 'ltr';
        document.documentElement.lang = currentLng;
      }
    };

    // Set direction on mount
    checkLanguageAndSetDirection();

    // Listen for language changes
    const handleLanguageChange = () => {
      checkLanguageAndSetDirection();
    };

    window.addEventListener('languageChanged', handleLanguageChange);
    return () => window.removeEventListener('languageChanged', handleLanguageChange);
  }, []);

  const [cart, setCart] = useState<CartItem[]>(() => {
    // Initialize from localStorage on first load
    if (typeof window !== 'undefined') {
      try {
        const savedCart = localStorage.getItem('cart');
        if (savedCart) {
          const parsed = JSON.parse(savedCart);
          // console.log('📦 Initialized cart from localStorage:', parsed);
          return parsed;
        }
      } catch (error) {
        console.error('❌ Failed to parse saved cart:', error);
      }
    }
    return [];
  });

  // Sync cart to localStorage whenever it changes
  useEffect(() => {
    // console.log('💾 Saving cart to localStorage:', cart);
    localStorage.setItem('cart', JSON.stringify(cart));
  }, [cart]);

  // Listen for cart updates and sync state - simplified version
  useEffect(() => {
    // Handler for custom cartUpdated event from ProductDetail/ProductCard
    const handleCartUpdate = (e: any) => {
      // console.log('📡 Received cartUpdated event in App');
      if (e.detail && Array.isArray(e.detail)) {
        // console.log('📦 Setting cart from event:', e.detail);
        setCart(e.detail);
      }
    };

    // Add listener immediately
    window.addEventListener('cartUpdated', handleCartUpdate);
    // console.log('✅ Registered cartUpdated listener');

    // Also set up polling every 500ms - more aggressive
    const pollInterval = setInterval(() => {
      const currentCart = localStorage.getItem('cart');
      if (currentCart) {
        try {
          const parsed = JSON.parse(currentCart);
          setCart(prev => {
            const prevStr = JSON.stringify(prev);
            const newStr = JSON.stringify(parsed);
            if (prevStr !== newStr) {
              // console.log('🔄 Cart updated from localStorage polling');
              return parsed;
            }
            return prev;
          });
        } catch (error) {
          console.error('❌ Error in polling:', error);
        }
      }
    }, 500);

    return () => {
      window.removeEventListener('cartUpdated', handleCartUpdate);
      clearInterval(pollInterval);
    };
  }, []);

  const navigate = (_page: string, data?: any) => {
    setPageData(data);
    window.scrollTo(0, 0);
  };

  const updateQuantity = (productId: string, quantity: number) => {
    setCart(prevCart =>
      prevCart.map(item =>
        item.id === productId
          ? { ...item, quantity }
          : item
      )
    );
    toast.success('Cart updated');
  };

  const removeItem = (productId: string) => {
    setCart(prevCart => prevCart.filter(item => item.id !== productId));
    toast.success('Item removed from cart');
  };

  const clearCart = () => {
    setCart([]);
  };

  const UnauthorizedPage = () => (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-lg p-6 text-center">
        <h1 className="text-2xl font-bold text-gray-900">Unauthorized</h1>
        <p className="mt-2 text-gray-600">
          You do not have permission to access this page.
        </p>
      </div>
    </div>
  );

  const ExternalLandingRedirect = () => {
    useEffect(() => {
      window.location.href = 'https://bazar-af-seven.vercel.app/home';
    }, []);
    return null;
  };

  return (
    <Router>
      <div className="min-h-screen bg-background">
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<ExternalLandingRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<SignUp />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/verify-email-pending" element={<VerifyEmailPending />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/become-seller" element={<BecomeSeller />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/seller-registration" element={<SellerRegistration />} />

          <Route path="/help-support" element={<HelpSupport />} />

          {/* Main App Routes */}
          <Route
            path="/home"
            element={
              <CustomerHome
                onNavigate={navigate}
                cartCount={cart.reduce((sum, item) => sum + item.quantity, 0)}
              />
            }
          />

          {/* Cart Route */}
          <Route
            path="/cart"
            element={
              <Cart
                items={cart}
                onUpdateQuantity={updateQuantity}
                onRemoveItem={removeItem}
              />
            }
          />

          <Route
            path="/products"
            element={<ProductListing />}
          />

          <Route
            path="/product/:productSlug"
            element={<ProductDetail />}
          />

          <Route
            path="/checkout"
            element={
              <Checkout
                items={cart}
                onNavigate={navigate}
                onClearCart={clearCart}
              />
            }
          />

          <Route
            path="/order-tracking"
            element={
              <OrderTracking
                onNavigate={navigate}
                orderId={pageData?.orderId}
              />
            }
          />

          {/* Store Storefront - Public vendor store view */}
          <Route
            path="/store/:storeName"
            element={<StoreFront />}
          />

          <Route
            path="/vendor"
            element={
              <ProtectedRoute role="vendor">
                <VendorDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/vendor/add-product"
            element={
              <ProtectedRoute role="vendor">
                <AddProduct />
              </ProtectedRoute>
            }
          />
          <Route
            path="/vendor/orders/:orderId"
            element={
              <ProtectedRoute role="vendor">
                <VendorOrderDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/vendor/profile"
            element={
              <ProtectedRoute role="vendor">
                <VendorProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/vendor/settings"
            element={
              <ProtectedRoute role="vendor">
                <VendorSettingsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/vendor/reviews"
            element={
              <ProtectedRoute role="vendor">
                <VendorReviewsPage />
              </ProtectedRoute>
            }
          />

          {/* Admin Routes - New custom admin dashboard */}
          {adminRoutes}

          {/* Legacy admin routes - kept for backward compatibility */}
          <Route
            path="/admin-legacy"
            element={
              <ProtectedRoute role="admin">
                <AdminPanel onNavigate={navigate} />
              </ProtectedRoute>
            }
          />

          <Route path="/unauthorized" element={<UnauthorizedPage />} />

          <Route
            path="/admin/categories"
            element={
              <ProtectedRoute role="admin">
                <CategoryManagement />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin/products/approval"
            element={
              <ProtectedRoute role="admin">
                <ProductApproval />
              </ProtectedRoute>
            }
          />

          {/* Protected Routes */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <MyProfile />
              </ProtectedRoute>
            }
          />

          <Route
            path="/orders"
            element={
              <ProtectedRoute>
                <MyOrders />
              </ProtectedRoute>
            }
          />

          <Route
            path="/wishlist"
            element={
              <ProtectedRoute>
                <Wishlist />
              </ProtectedRoute>
            }
          />

          <Route
            path="/reviews"
            element={
              <ProtectedRoute>
                <MyReviews />
              </ProtectedRoute>
            }
          />
        </Routes>

        <Toaster />
      </div>
    </Router>
  );
}