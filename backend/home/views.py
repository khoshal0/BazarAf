"""
views.py - Professional E-commerce API Views
"""
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import Group
from django.contrib.auth import authenticate
from django.core import signing
from django.core.cache import cache
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
import logging
import os
import uuid
import secrets

from rest_framework import viewsets, status, permissions, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import (
    User, Vendor, Category, Product, ProductImage,
    Order, OrderItem, Delivery, Payout, SellerApplication,
    CategoryAttribute, ProductAttribute, AttributeValue
)
from .serializer import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    VendorSerializer, VendorCreateSerializer, VendorUpdateSerializer, CategorySerializer,
    ProductSerializer, ProductCreateSerializer, ProductUpdateSerializer,
    ProductImageSerializer, ProductListSerializer, ProductDetailSerializer,
    CategoryTreeSerializer, CategoryAttributeSerializer,
    OrderSerializer, OrderCreateSerializer, OrderUpdateSerializer,
    OrderItemSerializer,
    DeliverySerializer, DeliveryCreateSerializer, DeliveryUpdateSerializer,
    PayoutSerializer, PayoutCreateSerializer, PayoutUpdateSerializer,
    LoginSerializer, RegisterSerializer, CheckoutOrderSerializer, SellerApplicationSerializer, NotificationSerializer, ProductReviewSerializer
    
)
from .two_factor import consume_backup_code, verify_totp


TWO_FA_CHALLENGE_MAX_AGE_SECONDS = 5 * 60
TWO_FA_VERIFY_LIMIT_PER_WINDOW = 8
TWO_FA_VERIFY_WINDOW_SECONDS = 60
logger = logging.getLogger(__name__)


def _build_2fa_challenge_cache_key(user_id: str, nonce: str) -> str:
    return f"auth:2fa:challenge:{user_id}:{nonce}"


def _create_2fa_challenge_token(user: User) -> str:
    nonce = secrets.token_urlsafe(16)
    cache.set(
        _build_2fa_challenge_cache_key(str(user.id), nonce),
        True,
        TWO_FA_CHALLENGE_MAX_AGE_SECONDS,
    )
    return signing.dumps(
        {"uid": str(user.id), "nonce": nonce, "role": user.role},
        salt="auth-2fa-challenge",
    )


def _parse_2fa_challenge_token(challenge_token: str) -> tuple[User | None, str | None]:
    try:
        data = signing.loads(
            challenge_token,
            salt="auth-2fa-challenge",
            max_age=TWO_FA_CHALLENGE_MAX_AGE_SECONDS,
        )
    except Exception:
        return None, None

    uid = str(data.get("uid", ""))
    nonce = str(data.get("nonce", ""))
    if not uid or not nonce:
        return None, None

    if not cache.get(_build_2fa_challenge_cache_key(uid, nonce)):
        return None, None

    user = User.objects.filter(id=uid, is_active=True).first()
    if not user:
        return None, None
    return user, nonce


def _consume_2fa_challenge_token(user_id: str, nonce: str) -> None:
    cache.delete(_build_2fa_challenge_cache_key(str(user_id), nonce))


def _2fa_verify_rate_limited(request, challenge_token: str) -> bool:
    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = f"auth:2fa:verify:{ip}:{challenge_token[:16]}"
    count = int(cache.get(key, 0) or 0)
    if count >= TWO_FA_VERIFY_LIMIT_PER_WINDOW:
        return True
    cache.set(key, count + 1, TWO_FA_VERIFY_WINDOW_SECONDS)
    return False


# ====================
# CUSTOM PERMISSIONS
# ====================
class IsSuperAdmin(permissions.BasePermission):
    """Permission for super admin users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


class IsAdminUser(permissions.BasePermission):
    """Permission for admin role users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsVendorUser(permissions.BasePermission):
    """Permission for vendor role users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'vendor'


class IsAdminOrSuperAdmin(permissions.BasePermission):
    """Permission for admin-role or superadmin users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or request.user.role == 'admin'
        )


class IsAdminOrSuperAdminOrVendor(permissions.BasePermission):
    """Permission for admin-role, superadmin, or vendor users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in ['admin', 'vendor']
        )


class IsOwnerAdminOrSuperAdmin(permissions.BasePermission):
    """Permission for owners, admins, or superadmins on object actions"""

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.role == 'admin':
            return True
        return IsOwnerOrAdmin().has_object_permission(request, view, obj)


class IsRiderUser(permissions.BasePermission):
    """Permission for rider role users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'rider'


class IsCustomerUser(permissions.BasePermission):
    """Permission for customer role users"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'customer'


class IsOwnerOrAdmin(permissions.BasePermission):
    """Permission to allow owners or admins"""
    def has_object_permission(self, request, view, obj):
        # Check if user is admin
        if request.user.role == 'admin' or request.user.is_superuser:
            return True
        
        # Check ownership for different models
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'customer'):
            return obj.customer == request.user
        elif hasattr(obj, 'vendor'):
            return obj.vendor.user == request.user
        elif hasattr(obj, 'rider'):
            return obj.rider == request.user
        
        return False


# ====================
# CUSTOM PAGINATION
# ====================
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ====================
# AUTHENTICATION VIEWS
# ====================
# In views.py - Update LoginView
class LoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Get credentials - support both 'phone' and 'identifier' field names
        identifier = request.data.get('identifier', '').strip() or request.data.get('phone', '').strip()
        password = request.data.get('password', '')
        
        if not identifier or not password:
            return Response({
                'status': 'error',
                'message': 'Email/Phone and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
           
            
            # Determine if identifier is email or phone
            user = None
            is_email = False
            
            # Check if it's an email
            try:
                validate_email(identifier)
                is_email = True
                user = User.objects.filter(email__iexact=identifier).first()
            except DjangoValidationError:
                # It's a phone number - normalize before lookup
                phone = identifier.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                if not phone.startswith('+'):
                    if phone.startswith('0'):
                        phone = '+93' + phone[1:]
                    elif phone.isdigit():
                        phone = '+93' + phone
                user = User.objects.filter(phone=phone).first()
            
            # If user not found
            if not user:
                return Response({
                    'status': 'error',
                    'message': 'Invalid email/phone or password'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Check if password is correct
            if user.check_password(password):
                # Check if user is active
                if not user.is_active:
                    return Response({
                        'status': 'error',
                        'message': 'Account is inactive. Please contact support.'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Check if email verification is required
                if user.email and not user.email_verified:
                    return Response({
                        'status': 'error',
                        'message': 'Please verify your email before logging in. Check your inbox for the verification link.',
                        'requires_email_verification': True,
                        'email': user.email
                    }, status=status.HTTP_401_UNAUTHORIZED)

                vendor = Vendor.objects.filter(user=user).first()
                if vendor and vendor.two_factor_enabled and vendor.totp_secret:
                    challenge_token = _create_2fa_challenge_token(user)
                    return Response(
                        {
                            'status': '2fa_required',
                            'message': 'Two-factor verification required.',
                            'challenge_token': challenge_token,
                            'user': {
                                'id': str(user.id),
                                'full_name': user.full_name,
                                'role': user.role,
                            },
                        },
                        status=status.HTTP_200_OK,
                    )
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                # Get user data
                
                user_data = UserSerializer(user).data
                
                return Response({
                    'status': 'success',
                    'message': 'Login successful',
                    'user': user_data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                })
            else:
                return Response({
                    'status': 'error',
                    'message': 'Invalid email/phone or password'
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Login failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TwoFactorVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        challenge_token = str(request.data.get("challenge_token", "")).strip()
        code = str(request.data.get("code", "")).strip()
        if not challenge_token or not code:
            return Response(
                {"status": "error", "message": "challenge_token and code are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if _2fa_verify_rate_limited(request, challenge_token):
            return Response(
                {"status": "error", "message": "Too many attempts. Please try again shortly."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user, nonce = _parse_2fa_challenge_token(challenge_token)
        if not user or not nonce:
            return Response(
                {"status": "error", "message": "Invalid or expired 2FA challenge."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        vendor = Vendor.objects.filter(user=user).first()
        if not vendor or not vendor.two_factor_enabled or not vendor.totp_secret:
            _consume_2fa_challenge_token(str(user.id), nonce)
            return Response(
                {"status": "error", "message": "2FA is not enabled for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        totp_ok = verify_totp(vendor.totp_secret, code)

        backup_hashes = []
        try:
            import json

            backup_hashes = json.loads(vendor.backup_codes_hashed or "[]")
        except Exception:
            backup_hashes = []

        backup_ok, remaining_hashes = consume_backup_code(code, backup_hashes)
        if not (totp_ok or backup_ok):
            return Response(
                {"status": "error", "message": "Invalid authenticator or backup code."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if backup_ok:
            import json

            vendor.backup_codes_hashed = json.dumps(remaining_hashes)
            vendor.save(update_fields=["backup_codes_hashed", "updated_at"])

        _consume_2fa_challenge_token(str(user.id), nonce)

        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data
        return Response(
            {
                "status": "success",
                "message": "2FA verification successful.",
                "user": user_data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            }
        )








        
class RegisterView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            email_sent = None
            
            # Get user data
            user_data = UserSerializer(user).data
            
            # If user has email, they need to verify it
            if user.email and not user.email_verified:
                verification_token = user.generate_email_verification_token()
                verification_code = user.generate_email_verification_code()
                from .emails import send_email_verification_email
                frontend_url = request.data.get('frontend_url') or os.getenv('FRONTEND_URL', 'http://localhost:5173')
                email_sent = send_email_verification_email(user, verification_token, frontend_url, verification_code)
                return Response({
                    'status': 'success',
                    'message': (
                        'Registration successful! Please check your email to verify your account.'
                        if email_sent
                        else 'Registration successful, but we could not send the verification email. Please try resend.'
                    ),
                    'user': user_data,
                    'requires_email_verification': True,
                    'email': user.email,
                    'otp_required': True,
                    'email_sent': email_sent,
                }, status=status.HTTP_201_CREATED)
            
            # Generate tokens for user without email requirement
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'status': 'success',
                'message': 'User registered successfully',
                'user': user_data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class GoogleAuthView(APIView):
    """
    Handle Google OAuth sign-in. Accepts a Google ID token from the frontend,
    verifies it, and creates/logs in the user.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        token = request.data.get('credential')
        if not token:
            return Response({
                'status': 'error',
                'message': 'Google credential is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            google_client_id = os.getenv('GOOGLE_CLIENT_ID', '')
            if not google_client_id:
                return Response({
                    'status': 'error',
                    'message': 'Google authentication is not configured'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Verify the Google ID token
            idinfo = id_token.verify_oauth2_token(
                token, google_requests.Request(), google_client_id
            )
            
            email = idinfo.get('email')
            full_name = idinfo.get('name', '')
            
            if not email:
                return Response({
                    'status': 'error',
                    'message': 'Could not retrieve email from Google account'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if user exists
            user = User.objects.filter(email__iexact=email).first()
            
            if user:
                # Existing user - mark email as verified and log in
                if not user.email_verified:
                    user.email_verified = True
                    user.save(update_fields=['email_verified'])
            else:
                # New user - create account
                user = User(
                    email=email,
                    full_name=full_name,
                    phone=f"+93{uuid.uuid4().hex[:9]}",  # Temp phone, user can update later
                    email_verified=True,
                    role='customer',
                )
                user.set_unusable_password()
                user.save()
            
            if not user.is_active:
                return Response({
                    'status': 'error',
                    'message': 'Account is inactive. Please contact support.'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            user_data = UserSerializer(user).data
            
            return Response({
                'status': 'success',
                'message': 'Login successful',
                'user': user_data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            })
        except ValueError as e:
            return Response({
                'status': 'error',
                'message': 'Invalid Google token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Google auth error: {e}")
            return Response({
                'status': 'error',
                'message': 'Authentication failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response({
                'status': 'success',
                'message': 'Logged out successfully'
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    """
    Endpoint to verify email address with token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        code = str(request.data.get('code', '')).strip()
        email = str(request.data.get('email', '')).strip()

        if not token and not code:
            return Response({
                'status': 'error',
                'message': 'Token or code is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if code:
                if not email:
                    return Response({
                        'status': 'error',
                        'message': 'Email is required for code verification'
                    }, status=status.HTTP_400_BAD_REQUEST)

                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid email or code'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if user.verify_email_code(code):
                    return Response({
                        'status': 'success',
                        'message': 'Email verified successfully'
                    }, status=status.HTTP_200_OK)

                return Response({
                    'status': 'error',
                    'message': 'Code expired or invalid'
                }, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.get(email_verification_token=token)

            if user.verify_email_token(token):
                return Response({
                    'status': 'success',
                    'message': 'Email verified successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': 'error',
                    'message': 'Token expired or invalid'
                }, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmailView(APIView):
    """
    Resend email verification link
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({
                'status': 'error',
                'message': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email__iexact=email)
            if user.email_verified:
                return Response({
                    'status': 'success',
                    'message': 'Email is already verified'
                })
            
            verification_token = user.generate_email_verification_token()
            verification_code = user.generate_email_verification_code()
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
            from .emails import send_email_verification_email
            email_sent = send_email_verification_email(user, verification_token, frontend_url, verification_code)

            if not email_sent:
                return Response({
                    'status': 'error',
                    'message': 'Email service is not configured or failed to send. Please try again later.'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return Response({
                'status': 'success',
                'message': 'Verification email sent. Please check your inbox.',
                'otp_required': True,
                'email_sent': True,
            })
        except User.DoesNotExist:
            # Don't reveal if email exists
            return Response({
                'status': 'success',
                'message': 'If this email is registered, a verification link has been sent.'
            })


class RequestPasswordResetView(APIView):
    """
    Endpoint to request password reset email
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            return Response({
                'status': 'error',
                'message': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            
            # Generate reset token
            reset_token = user.generate_password_reset_token()
            
            # Send email with reset link
            from .emails import send_password_reset_email
            frontend_url = request.data.get('frontend_url', 'https://bazaaraf.com')
            send_password_reset_email(user, reset_token, frontend_url)
            
            return Response({
                'status': 'success',
                'message': 'Password reset email sent successfully'
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            # Don't reveal if email exists for security reasons
            return Response({
                'status': 'success',
                'message': 'If email exists, password reset link has been sent'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error sending email: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResetPasswordView(APIView):
    """
    Endpoint to reset password with token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('password')
        
        if not token or not new_password:
            return Response({
                'status': 'error',
                'message': 'Token and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(password_reset_token=token)
            
            if user.reset_password(token, new_password):
                return Response({
                    'status': 'success',
                    'message': 'Password reset successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': 'error',
                    'message': 'Token expired or invalid'
                }, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


# ====================
# USER VIEWSET
# ====================
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['phone', 'full_name', 'email']
    ordering_fields = ['created_at', 'full_name']
    
    def get_permissions(self):
        if self.action in ['create', 'list']:
            permission_classes = [IsAdminUser | IsSuperAdmin]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsOwnerOrAdmin | IsSuperAdmin]
        else:
            permission_classes = [IsAdminUser | IsSuperAdmin]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin' or user.is_superuser:
            return User.objects.all()
        
        # Non-admin users can only see their own profile
        return User.objects.filter(id=user.id)
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['put', 'patch'])
    def update_me(self, request):
        """Update current user profile"""
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ====================
# VENDOR VIEWSET
# ====================
from .emails import send_vendor_approval_email, send_vendor_rejection_email
from .models import Notification

class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.select_related('user').all().order_by('-created_at')
    serializer_class = VendorSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['shop_name', 'city', 'user__full_name', 'user__phone']
    ordering_fields = ['created_at', 'shop_name', 'status']
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [AllowAny]  # Anyone can apply to become a vendor
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsOwnerOrAdmin | IsSuperAdmin]
        else:
            permission_classes = [IsAdminUser | IsSuperAdmin]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return VendorCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return VendorUpdateSerializer
        return VendorSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin' or user.is_superuser:
            return Vendor.objects.all()
        elif user.role == 'vendor':
            # Vendor can only see their own vendor profile
            try:
                return Vendor.objects.filter(user=user)
            except Vendor.DoesNotExist:
                return Vendor.objects.none()
        
        # Customers can see approved vendors
        return Vendor.objects.filter(status='approved')
    
    def perform_create(self, serializer):
        # If user is authenticated, associate with their account
        if self.request.user.is_authenticated and self.request.user.role == 'customer':
            # Change user role to vendor
            self.request.user.role = 'vendor'
            self.request.user.save()
            serializer.save(user=self.request.user)
        else:
            # For new vendors (unauthenticated users during registration)
            serializer.save()
    
    # In VendorViewSet class, update the approve action:
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def approve(self, request, pk=None):
        """Approve a vendor application"""
        vendor = self.get_object()
        logger.info("admin_vendor_approve actor=%s vendor=%s", request.user.id, vendor.id)
    
        # Update vendor status
        vendor.status = 'approved'
        vendor.save()
    
        # Update user role if not already vendor
        if vendor.user.role != 'vendor':
            vendor.user.role = 'vendor'
            vendor.user.save()
    
        # Send email notification
        send_vendor_approval_email(vendor)
    
    # Create in-app notification
        Notification.objects.create(
            user=vendor.user,
            notification_type='vendor_approved',
            title='Seller Application Approved! 🎉',
            message=f'Congratulations! Your shop "{vendor.shop_name}" has been approved. You can now start adding products and receiving orders.',
            link='/vendor'
        )   
    
        return Response({
            'status': 'success',
            'message': 'Vendor approved successfully. Email notification sent.'
        })


    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def reject(self, request, pk=None):
        """Reject a vendor application"""
        vendor = self.get_object()
        reason = request.data.get('reason', '')

        logger.info("admin_vendor_reject actor=%s vendor=%s", request.user.id, vendor.id)

        vendor.status = 'suspended'
        vendor.save()
    
        # Send email notification
        send_vendor_rejection_email(vendor, reason)
    
    # Create in-app notification
        Notification.objects.create(
            user=vendor.user,
            notification_type='vendor_rejected',
            title='Seller Application - Additional Information Needed',
            message=f'We need some additional information for your shop "{vendor.shop_name}". Please contact support.',
            link='/help-support'
        )
    
        return Response({
            'status': 'success',
            'message': 'Vendor rejected. Email notification sent.'
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def suspend(self, request, pk=None):
        """Suspend an existing vendor account."""
        vendor = self.get_object()
        logger.info("admin_vendor_suspend actor=%s vendor=%s", request.user.id, vendor.id)

        vendor.status = 'suspended'
        vendor.save(update_fields=['status'])

        return Response({
            'status': 'success',
            'message': 'Vendor suspended successfully.'
        })
    
    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Get all products for a specific vendor"""
        vendor = self.get_object()
        products = Product.objects.filter(vendor=vendor, status='approved')
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[IsOwnerOrAdmin | IsSuperAdmin])
    def stats(self, request, pk=None):
        """Get vendor statistics"""
        vendor = self.get_object()
        
        # Calculate statistics
        total_products = Product.objects.filter(vendor=vendor).count()
        active_products = Product.objects.filter(vendor=vendor, status='approved').count()
        total_orders = OrderItem.objects.filter(vendor=vendor).count()
        total_sales = OrderItem.objects.filter(
            vendor=vendor,
            order__status='delivered'
        ).aggregate(total=Sum('price_at_order'))['total'] or 0
        
        return Response({
            'total_products': total_products,
            'active_products': active_products,
            'total_orders': total_orders,
            'total_sales': float(total_sales)
        })

# Add new NotificationViewSet
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'count': count})
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'success', 'message': 'Notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'success', 'message': 'All notifications marked as read'})
# backend/home/views.py - ADD THIS

class SellerApplicationViewSet(viewsets.ModelViewSet):
    queryset = SellerApplication.objects.all()
    serializer_class = SellerApplicationSerializer
    pagination_class = StandardResultsSetPagination
    
    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]  # Anyone can submit application
        elif self.action in ['list', 'retrieve']:
            return [IsAdminOrSuperAdminOrVendor()]  # Admins and vendors can view
        elif self.action in ['approve', 'reject']:
            return [IsAdminOrSuperAdmin()]  # Only admins can approve/reject
        else:
            return [IsAdminOrSuperAdmin()]
    
    def get_queryset(self):
        user = self.request.user
        
        if not user.is_authenticated:
            return SellerApplication.objects.none()
        
        if user.is_superuser or user.role == 'admin':
            # Admins see all applications
            return SellerApplication.objects.all().select_related('user', 'vendor')
        
        if user.role == 'vendor':
            # Vendors see only their own application
            try:
                vendor = Vendor.objects.get(user=user)
                return SellerApplication.objects.filter(vendor=vendor).select_related('user')
            except Vendor.DoesNotExist:
                return SellerApplication.objects.none()
        
        return SellerApplication.objects.none()
    
    def perform_create(self, serializer):
        """Link application to authenticated user if they exist"""
        # If user is authenticated, link the application
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            serializer.save()
    
    @action(detail=True, methods=['get'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def debug_status(self, request, pk=None):
        """Debug endpoint to check actual database state"""
        application = self.get_object()
        
        user_info = None
        vendor_info = None
        
        if application.user:
            user_info = {
                'id': str(application.user.id),
                'phone': application.user.phone,
                'full_name': application.user.full_name,
                'email': application.user.email,
                'role': application.user.role,
                'is_active': application.user.is_active,
            }
        
        if application.vendor:
            vendor_info = {
                'id': str(application.vendor.id),
                'shop_name': application.vendor.shop_name,
                'status': application.vendor.status,
                'city': application.vendor.city,
            }
        
        # Also check if vendor exists in DB for the phone
        vendor_by_phone = None
        if application.phone:
            try:
                user_by_phone = User.objects.get(phone=application.phone)
                vendor_by_phone = Vendor.objects.get(user=user_by_phone)
                vendor_by_phone = {
                    'id': str(vendor_by_phone.id),
                    'shop_name': vendor_by_phone.shop_name,
                    'status': vendor_by_phone.status,
                }
            except (User.DoesNotExist, Vendor.DoesNotExist):
                vendor_by_phone = 'NOT FOUND'
        
        return Response({
            'application': {
                'id': str(application.id),
                'application_id': application.application_id,
                'status': application.status,
                'phone': application.phone,
            },
            'linked_user': user_info,
            'linked_vendor': vendor_info,
            'user_and_vendor_by_phone': {
                'phone': application.phone,
                'vendor': vendor_by_phone
            }
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def approve(self, request, pk=None):
        """
        Approve a seller application.
        - If user exists: update their role to vendor and create vendor record
        - If user doesn't exist: create new user with vendor role, then create vendor record
        """
        import logging
        import secrets
        import string
        from django.db import transaction
        
        logger = logging.getLogger(__name__)
        
        application = self.get_object()
        
        if application.status != 'pending':
            return Response({'error': 'Application already processed'}, status=400)
        
        try:
            logger.info(f"🔄 Starting approval for application {application.application_id}")
            
            with transaction.atomic():
                # Step 1: Get or create user
                logger.info(f"📱 Looking for user with phone: {application.phone}")
                user = User.objects.filter(phone=application.phone).first()
                password = None
                user_created = False
                
                if not user:
                    logger.info(f"✨ Creating new user for {application.full_name}")
                    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                    
                    user = User.objects.create(
                        phone=application.phone,
                        full_name=application.full_name,
                        email=application.email,
                        role='vendor',  # Set role directly to vendor
                        is_active=True
                    )
                    user.set_password(password)
                    user.save(update_fields=['password'])
                    user_created = True
                    logger.info(f"✅ User created: {user.id} with role={user.role}")
                else:
                    logger.info(f"👤 Found existing user {user.id} with role={user.role}")
                    
                    # Update user to vendor role
                    if user.role != 'vendor':
                        logger.info(f"🔄 Changing user role from {user.role} to vendor")
                        user.role = 'vendor'
                        user.full_name = application.full_name
                        if application.email and not user.email:
                            user.email = application.email
                        user.save(update_fields=['role', 'full_name', 'email'])
                        logger.info(f"✅ User role updated to vendor")
                    else:
                        logger.info(f"ℹ️ User already has vendor role, just updating info")
                        user.full_name = application.full_name
                        if application.email and not user.email:
                            user.email = application.email
                        user.save(update_fields=['full_name', 'email'])
                
                # Verify user was saved with vendor role
                user.refresh_from_db()
                logger.info(f"✔️ Verified user role after save: {user.role}")
                
                # Step 2: Get or create vendor
                logger.info(f"🏪 Looking for vendor for user {user.id}")
                vendor = Vendor.objects.filter(user=user).first()
                
                if not vendor:
                    logger.info(f"✨ Creating new vendor for {application.shop_name}")
                    vendor = Vendor.objects.create(
                        user=user,
                        shop_name=application.shop_name,
                        address=application.address,
                        city=application.city,
                        identity_document=application.identity_document,
                        business_document=application.business_document,
                        status='approved'
                    )
                    logger.info(f"✅ Vendor created: {vendor.id}")
                else:
                    logger.info(f"🔄 Updating existing vendor {vendor.id}")
                    vendor.shop_name = application.shop_name
                    vendor.address = application.address
                    vendor.city = application.city
                    if application.identity_document:
                        vendor.identity_document = application.identity_document
                    if application.business_document:
                        vendor.business_document = application.business_document
                    vendor.status = 'approved'
                    vendor.save()
                    logger.info(f"✅ Vendor updated")
                
                # Step 3: Update application
                logger.info(f"📝 Updating application status")
                application.status = 'approved'
                application.user = user
                application.vendor = vendor
                application.reviewed_at = timezone.now()
                application.save()
                logger.info(f"✅ Application updated")
                
                # Step 4: Create notification
                logger.info(f"🔔 Creating notification")
                Notification.objects.create(
                    user=user,
                    notification_type='vendor_approved',
                    title='Seller Application Approved! 🎉',
                    message=f'Congratulations! Your shop "{application.shop_name}" has been approved. You can now start adding products and receiving orders.',
                    link='/vendor'
                )
                logger.info(f"✅ Notification created")
                
                logger.info(f"✨ ✨ APPLICATION APPROVAL COMPLETE ✨ ✨")
                
                response_data = {
                    'status': 'success',
                    'message': 'Application approved successfully',
                    'user_created': user_created,
                    'user_id': str(user.id),
                    'user_role': user.role,
                    'phone': application.phone,
                    'vendor_id': str(vendor.id),
                }
                
                if password:
                    response_data['credentials'] = {
                        'phone': application.phone,
                        'password': password
                    }
                
                return Response(response_data)
        
        except Exception as e:
            import traceback
            logger.error(f"❌ ERROR during approval: {str(e)}")
            logger.error(traceback.format_exc())
            return Response({
                'error': str(e),
                'detail': 'Failed to approve application. Please check server logs.'
            }, status=500)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def reject(self, request, pk=None):
        """Reject a seller application"""
        application = self.get_object()
        
        if application.status != 'pending':
            return Response({'error': 'Application already processed'}, status=400)
        
        reason = request.data.get('reason', '')
        application.status = 'rejected'
        application.rejection_reason = reason
        application.reviewed_at = timezone.now()
        application.save()
        
        # Create in-app notification if user is linked
        if application.user:
            Notification.objects.create(
                user=application.user,
                notification_type='vendor_rejected',
                title='Seller Application Update',
                message=f'Your seller application has been reviewed. Reason: {reason or "No details provided. Please contact support."}',
                link='/help-support'
            )
        
        return Response({'status': 'success', 'message': 'Application rejected'})
# ====================
# PRODUCT VIEWSET
# ====================
# File: backend/api/views.py
# UPDATE your ProductViewSet's get_queryset method

# ====================
# File: backend/home/views.py
# REPLACE the ProductViewSet's get_queryset method with this

class ProductViewSet(viewsets.ModelViewSet):
    """
    Comprehensive ProductViewSet with advanced filtering, search, and features
    """
    queryset = Product.objects.all()
    lookup_field = 'slug'
    lookup_value_regex = r'[\w-]+'
    pagination_class = StandardResultsSetPagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'category__name', 'vendor__shop_name']
    ordering_fields = ['created_at', 'price', 'name', 'sales_count', 'views_count', 'average_rating']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'search', 'featured', 'reviews']:
            return [permissions.AllowAny()]
        elif self.action == 'create':
            return [IsVendorUser()]
        elif self.action in ['update', 'partial_update', 'destroy', 'upload_images']:
            return [IsOwnerAdminOrSuperAdmin()]
        elif self.action == 'toggle_active':
            return [IsOwnerAdminOrSuperAdmin()]
        elif self.action in ['approve', 'reject']:
            return [IsAdminOrSuperAdmin()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action == 'create':
            return ProductCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ProductUpdateSerializer
        return ProductSerializer

    def get_queryset(self):
        user = self.request.user

        # Admins must always see the full product set, even if they also have vendor_profile.
        if user.is_authenticated and (user.role == 'admin' or user.is_superuser):
            return Product.objects.all()
        
        # Vendors see ALL their products
        if user.is_authenticated:
            try:
                vendor = user.vendor_profile
                return Product.objects.filter(vendor=vendor).order_by('-created_at')
            except (Vendor.DoesNotExist, AttributeError):
                pass
        
        # Customers and anonymous see only approved products
        queryset = Product.objects.filter(status='approved', is_active=True)
        
        # Advanced filtering
        queryset = self._apply_filters(queryset)
        return queryset

    def get_object(self):
        """Allow detail endpoints to resolve by either slug or UUID."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_field) or self.kwargs.get('pk')

        if lookup_value is None:
            return super().get_object()

        try:
            uuid.UUID(str(lookup_value))
            obj = get_object_or_404(queryset, id=lookup_value)
        except (ValueError, TypeError):
            obj = get_object_or_404(queryset, slug=lookup_value)

        self.check_object_permissions(self.request, obj)
        return obj
    
    def _apply_filters(self, queryset):
        """Apply complex filters to queryset"""
        category_slug = self.request.query_params.get('category_slug')
        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug)
                # Get category and all descendants
                category_ids = self._get_category_descendants(category)
                queryset = queryset.filter(category_id__in=category_ids)
            except Category.DoesNotExist:
                pass
        
        # Price range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        return queryset
    
    def _get_category_descendants(self, category):
        """Get category ID and all descendant category IDs"""
        ids = [category.id]
        for child in category.subcategories.all():
            ids.append(child.id)
            for grandchild in child.subcategories.all():
                ids.append(grandchild.id)
        return ids

    def create(self, request, *args, **kwargs):
        """Create a new product"""
        try:
            vendor = request.user.vendor_profile
        except (Vendor.DoesNotExist, AttributeError):
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(vendor=vendor)
        
        headers = self.get_success_headers(serializer.data)
        response_serializer = ProductDetailSerializer(
            serializer.instance,
            context={'request': request}
        )
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def retrieve(self, request, *args, **kwargs):
        """Return product detail with synchronized sold count for delivered orders."""
        product = self.get_object()
        sold_units = OrderItem.objects.filter(
            product=product,
            order__status='delivered'
        ).aggregate(total=Sum('quantity'))['total'] or 0

        if product.sales_count != sold_units:
            product.sales_count = sold_units
            product.save(update_fields=['sales_count'])

        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Advanced search for products and categories"""
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({'results': [], 'categories': []})
        
        # Search products
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query),
            is_active=True,
            status='approved'
        )[:20]
        
        # Search categories
        categories = Category.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query),
            is_active=True
        )[:10]
        
        return Response({
            'results': ProductListSerializer(products, many=True, context={'request': request}).data,
            'categories': CategoryTreeSerializer(categories, many=True).data,
        })
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured products for homepage"""
        limit = int(request.query_params.get('limit', 8))
        products = Product.objects.filter(
            is_featured=True,
            status='approved',
            is_active=True
        ).order_by('-created_at')[:limit]
        
        serializer = ProductListSerializer(
            products,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def increment_views(self, request, slug=None):
        """Increment product view count"""
        product = self.get_object()
        product.views_count += 1
        product.save(update_fields=['views_count'])
        return Response({'views_count': product.views_count})
    
    @action(detail=True, methods=['get'])
    def reviews(self, request, slug=None):
        """Get reviews for a product"""
        product = self.get_object()
        reviews = product.reviews.all()
        serializer = ProductReviewSerializer(
            reviews,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_images(self, request, slug=None):
        """Upload product images"""
        product = self.get_object()
        
        # Check permissions
        is_vendor_owner = (
            hasattr(request.user, 'vendor_profile') and
            product.vendor == request.user.vendor_profile
        )
        is_admin = request.user.role in ['admin'] or request.user.is_superuser
        
        if not (is_vendor_owner or is_admin):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        images = request.FILES.getlist('images')
        created_images = []
        
        for idx, image in enumerate(images):
            is_primary = idx == 0 and not product.images.exists()
            product_image = ProductImage.objects.create(
                product=product,
                image=image,
                is_primary=is_primary,
                display_order=product.images.count() + idx
            )
            created_images.append(
                {'id': str(product_image.id), 'url': product_image.image.url}
            )
        
        return Response({
            'status': 'success',
            'message': f'{len(created_images)} images uploaded',
            'images': created_images
        })

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, slug=None):
        """Toggle product status between approved and inactive."""
        product = self.get_object()

        current_status = (product.status or '').lower()
        if current_status == 'approved':
            product.status = 'inactive'
        elif current_status == 'inactive':
            product.status = 'approved'
        else:
            return Response(
                {
                    'error': 'Only approved or inactive products can be toggled.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        product.save(update_fields=['status'])
        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Admin: approve a pending product"""
        product = self.get_object()
        
        if product.status != 'pending':
            return Response(
                {'error': f'Only pending products can be approved (current: {product.status})'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        product.status = 'approved'
        product.save()
        
        return Response({
            'status': 'success',
            'message': f'Product "{product.name}" approved',
            'product': ProductDetailSerializer(product, context={'request': request}).data
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Admin: reject a pending product"""
        product = self.get_object()
        
        if product.status != 'pending':
            return Response(
                {'error': f'Only pending products can be rejected (current: {product.status})'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('reason', 'No reason provided')
        product.status = 'rejected'
        product.save()
        
        return Response({
            'status': 'success',
            'message': f'Product "{product.name}" rejected',
            'reason': reason
        })
    
    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle product featured status"""
        product = self.get_object()
        product.is_featured = not product.is_featured
        product.save()
        
        return Response({
            'is_featured': product.is_featured,
            'message': f'Product {"added to" if product.is_featured else "removed from"} featured'
        })

        if current_status not in ('approved', 'inactive'):
            return Response(
                {
                    'error': (
                        f"Product with status '{product.status}' cannot be toggled. "
                        "Only 'approved' or 'inactive' products are eligible."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if current_status == 'approved':
            product.status = 'inactive'
            message = 'Product deactivated successfully'
        else:
            product.status = 'approved'
            message = 'Product activated successfully'

        product.save()

        return Response({
            'status': 'success',
            'message': message,
            # ─── FIX 2: Return the full updated product so the frontend can
            #            sync its local state from the server's truth, not
            #            from an optimistic guess. ─────────────────────────
            'product': ProductSerializer(product, context={'request': request}).data,
        })



class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing categories with full hierarchy support
    """
    queryset = Category.objects.filter(is_active=True).order_by('order', 'name')
    serializer_class = CategorySerializer
    lookup_field = 'slug'
    pagination_class = StandardResultsSetPagination
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'tree', 'main_categories', 'attributes']:
            return [permissions.AllowAny()]
        return [IsAdminOrSuperAdmin()]

    def get_object(self):
        """Resolve categories by slug (default) and UUID for admin compatibility."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_field) or self.kwargs.get('pk')

        if lookup_value is None:
            return super().get_object()

        try:
            uuid.UUID(str(lookup_value))
            obj = get_object_or_404(queryset, id=lookup_value)
        except (ValueError, TypeError):
            obj = get_object_or_404(queryset, slug=lookup_value)

        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        category = serializer.save()
        logger.info("admin_category_create actor=%s category=%s", self.request.user.id, category.id)

    def perform_update(self, serializer):
        category = serializer.save()
        logger.info("admin_category_update actor=%s category=%s", self.request.user.id, category.id)

    def perform_destroy(self, instance):
        category_id = instance.id
        instance.delete()
        logger.info("admin_category_delete actor=%s category=%s", self.request.user.id, category_id)
    
    def get_serializer_class(self):
        if self.action == 'tree':
            return CategoryTreeSerializer
        return CategorySerializer
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Get complete category tree for navigation"""
        main_categories = Category.objects.filter(
            level='main', 
            is_active=True
        ).order_by('order', 'name')
        serializer = self.get_serializer(main_categories, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def main_categories(self, request):
        """Get only main categories for homepage"""
        categories = Category.objects.filter(
            level='main',
            is_active=True
        ).order_by('order', 'name')
        serializer = CategorySerializer(categories, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def attributes(self, request, slug=None):
        """Get attributes for a specific category"""
        category = self.get_object()
        attributes = CategoryAttribute.objects.filter(
            category=category
        ).order_by('display_order', 'name')
        serializer = CategoryAttributeSerializer(attributes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], pagination_class=StandardResultsSetPagination)
    def products(self, request, slug=None):
        """Get all products in a category with pagination"""
        category = self.get_object()
        
        # Get category and all its descendants
        category_ids = [category.id]
        for child in category.subcategories.all():
            category_ids.append(child.id)
            for grandchild in child.subcategories.all():
                category_ids.append(grandchild.id)
        
        products = Product.objects.filter(
            category_id__in=category_ids,
            status='approved',
            is_active=True
        ).order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)

# ====================
# ORDER VIEWSET
# ====================

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('customer').all().order_by('-created_at')
    serializer_class = OrderSerializer
    pagination_class = StandardResultsSetPagination
    parser_classes = [JSONParser]  # ✅ Added to accept JSON for status updates
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering_fields = ['created_at', 'total_amount']
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsCustomerUser]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [IsOwnerOrAdmin | IsSuperAdmin]
        elif self.action == 'destroy':
            permission_classes = [IsAdminUser | IsSuperAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return OrderUpdateSerializer
        return OrderSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        # Apply status filter if provided
        status_filter = self.request.query_params.get('status')
        queryset = Order.objects.all()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Role-based filtering
        if not user.is_authenticated:
            return queryset.none()
        
        # ✅ Admin sees ALL orders
        if user.role == 'admin' or user.is_superuser or user.is_staff:
            return queryset.select_related('customer').prefetch_related('items')
        
        elif user.role == 'customer':
            return queryset.filter(
                Q(customer=user) | Q(customer_phone=user.phone)
            )
        
        elif user.role == 'vendor':
            try:
                vendor = Vendor.objects.get(user=user)
                order_ids = OrderItem.objects.filter(vendor=vendor).values_list('order_id', flat=True).distinct()
                return queryset.filter(id__in=order_ids)
            except Vendor.DoesNotExist:
                return queryset.none()
        
        elif user.role == 'rider':
            return queryset.filter(delivery__rider=user)
        
        return queryset.none()
    
    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)
    
    # ==================== CUSTOM ACTIONS ====================
    
    @action(detail=True, methods=['post'], permission_classes=[IsCustomerUser])
    def cancel(self, request, pk=None):
        """Customer cancels their order"""
        order = self.get_object()
        
        if order.customer != request.user:
            return Response(
                {'error': 'You can only cancel your own orders'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if order.status not in ['pending', 'confirmed']:
            return Response({
                'error': f'Cannot cancel order with status: {order.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        order.status = 'cancelled'
        order.save()
        
        return Response({
            'status': 'success',
            'message': 'Order cancelled successfully'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsVendorUser | IsAdminUser | IsSuperAdmin])
    def confirm(self, request, pk=None):
        """Vendor/Admin confirms an order"""
        order = self.get_object()
        
        # Check if vendor has items in this order
        if request.user.role == 'vendor':
            vendor = Vendor.objects.get(user=request.user)
            if not OrderItem.objects.filter(order=order, vendor=vendor).exists():
                return Response(
                    {'error': 'You do not have items in this order'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        if order.status != 'pending':
            return Response({
                'error': f'Order is already {order.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        order.status = 'confirmed'
        order.save()
        
        return Response({
            'status': 'success',
            'message': 'Order confirmed successfully'
        })
    
    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get current user's orders"""
        user = request.user
        
        if user.role == 'customer':
            orders = Order.objects.filter(customer=user)
        elif user.role == 'vendor':
            vendor = Vendor.objects.get(user=user)
            order_ids = OrderItem.objects.filter(vendor=vendor).values_list('order_id', flat=True).distinct()
            orders = Order.objects.filter(id__in=order_ids)
        elif user.role == 'rider':
            orders = Order.objects.filter(delivery__rider=user)
        else:
            orders = Order.objects.none()
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)
    
    # ==================== NEW ACTIONS FOR ADMIN ====================
    
    @action(detail=False, methods=['get'], url_path='status-counts')
    def status_counts(self, request):
        """
        Get count of orders by status
        GET /api/orders/status-counts/
        """
        counts = {
            'pending': Order.objects.filter(status='pending').count(),
            'confirmed': Order.objects.filter(status='confirmed').count(),
            'picked': Order.objects.filter(status='picked').count(),
            'delivered': Order.objects.filter(status='delivered').count(),
        }
        
        print(f"✅ Order Status Counts: {counts}")
        return Response(counts)
    
    @action(detail=False, methods=['post'], url_path='bulk-update-status', 
            permission_classes=[IsAdminUser | IsSuperAdmin])
    def bulk_update_status(self, request):
        """
        Bulk update order status
        POST /api/orders/bulk-update-status/
        Body: {"order_ids": ["uuid1", "uuid2"], "status": "confirmed"}
        """
        order_ids = request.data.get('order_ids', [])
        new_status = request.data.get('status')
        
        if not order_ids or not new_status:
            return Response({
                'error': 'order_ids and status are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status
        valid_statuses = ['pending', 'confirmed', 'picked', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return Response({
                'error': f'Invalid status. Must be one of: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update orders
        updated = Order.objects.filter(id__in=order_ids).update(status=new_status)
        
        return Response({
            'success': True,
            'updated': updated,
            'message': f'Updated {updated} orders to {new_status}'
        })


# ==================== KEEP YOUR EXISTING VIEWS ====================

class CheckoutOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        customer_phone = request.data.get('customer_phone', '').strip()
        if customer_phone and customer_phone != request.user.phone:
            return Response({
                'status': 'error',
                'message': 'Customer phone must match your account phone number'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        request_data = dict(request.data) if hasattr(request.data, '__iter__') else request.data
        request_data['customer_phone'] = request.user.phone
        
        serializer = CheckoutOrderSerializer(data=request_data, context={'request': request})
        
        if serializer.is_valid():
            try:
                order = serializer.save()

                # Notify each vendor participating in this order.
                vendor_user_ids = (
                    OrderItem.objects.filter(order=order, vendor__user__isnull=False)
                    .values_list('vendor__user_id', flat=True)
                    .distinct()
                )
                for vendor_user_id in vendor_user_ids:
                    vendor_user = User.objects.filter(id=vendor_user_id).first()
                    if not vendor_user:
                        continue
                    Notification.objects.create(
                        user=vendor_user,
                        notification_type='order_placed',
                        title='New order received',
                        message=(
                            f"You received order {order.order_id}. "
                            f"Customer: {order.customer_name or order.customer_phone}."
                        ),
                        link=f'/vendor/orders/{order.id}',
                    )

                return Response({
                    'status': 'success',
                    'message': 'Order created successfully',
                    'order': {
                        'id': order.order_id,
                        'uuid': str(order.id),
                        'total': str(order.total_amount),
                        'status': order.status,
                        'customer_name': order.customer_name,
                        'customer_phone': order.customer_phone,
                        'created_at': order.created_at.isoformat(),
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': f'Failed to create order: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'status': 'error',
            'message': 'Invalid order data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class OrderDetailByIdView(APIView):
    """
    Get order details by order_id (for tracking)
    """
    permission_classes = [AllowAny]
    
    def get(self, request, order_id):
        try:
            order = Order.objects.get(order_id=order_id)
            serializer = OrderSerializer(order)
            
            return Response({
                'status': 'success',
                'order': serializer.data
            })
        except Order.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)














# ====================
# DELIVERY VIEWSET
# ====================
class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.select_related('order', 'rider').all().order_by('-id')
    serializer_class = DeliverySerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering_fields = ['id', 'delivered_at']
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsAdminUser | IsSuperAdmin]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser | IsSuperAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DeliveryCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return DeliveryUpdateSerializer
        return DeliverySerializer
    
    def get_queryset(self):
        user = self.request.user
        
        # Apply status filter if provided
        status_filter = self.request.query_params.get('status')
        queryset = Delivery.objects.all()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Role-based filtering
        if user.role == 'admin' or user.is_superuser:
            return queryset
        elif user.role == 'rider':
            return queryset.filter(rider=user)
        elif user.role == 'vendor':
            # Get deliveries for orders that have items from this vendor
            vendor = Vendor.objects.get(user=user)
            order_ids = OrderItem.objects.filter(vendor=vendor).values_list('order_id', flat=True).distinct()
            return queryset.filter(order_id__in=order_ids)
        elif user.role == 'customer':
            # Customers can see deliveries for their orders
            order_ids = Order.objects.filter(customer=user).values_list('id', flat=True)
            return queryset.filter(order_id__in=order_ids)
        
        return queryset.none()
    
    @action(detail=True, methods=['post'], permission_classes=[IsRiderUser])
    def pickup(self, request, pk=None):
        """Rider picks up the delivery"""
        delivery = self.get_object()
        
        # Check if rider is assigned to this delivery
        if delivery.rider != request.user:
            return Response(
                {'error': 'You are not assigned to this delivery'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if delivery.status != 'assigned':
            return Response({
                'error': f'Delivery is already {delivery.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        delivery.status = 'picked'
        delivery.save()
        
        # Update order status
        delivery.order.status = 'picked'
        delivery.order.save()
        
        return Response({
            'status': 'success',
            'message': 'Delivery picked successfully'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsRiderUser])
    def deliver(self, request, pk=None):
        """Rider delivers the order"""
        delivery = self.get_object()
        
        # Check if rider is assigned to this delivery
        if delivery.rider != request.user:
            return Response(
                {'error': 'You are not assigned to this delivery'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if delivery.status != 'picked':
            return Response({
                'error': 'You must pick up the delivery first'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        collected_amount = request.data.get('collected_amount', 0)
        
        delivery.status = 'delivered'
        delivery.collected_amount = collected_amount
        delivery.delivered_at = timezone.now()
        delivery.save()
        
        # Update order status
        delivery.order.status = 'delivered'
        delivery.order.save()

        # Increment sold units for each product in the delivered order
        for item in delivery.order.items.all():
            Product.objects.filter(id=item.product_id).update(
                sales_count=F('sales_count') + item.quantity
            )
        
        return Response({
            'status': 'success',
            'message': 'Delivery completed successfully'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsRiderUser])
    def fail(self, request, pk=None):
        """Mark delivery as failed"""
        delivery = self.get_object()
        
        # Check if rider is assigned to this delivery
        if delivery.rider != request.user:
            return Response(
                {'error': 'You are not assigned to this delivery'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reason = request.data.get('reason', '')
        
        delivery.status = 'failed'
        delivery.save()
        
        return Response({
            'status': 'success',
            'message': 'Delivery marked as failed',
            'reason': reason
        })


# ====================
# PAYOUT VIEWSET
# ====================
class PayoutViewSet(viewsets.ModelViewSet):
    queryset = Payout.objects.select_related('vendor').all().order_by('-period_end')
    serializer_class = PayoutSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering_fields = ['period_end', 'amount', 'paid_at']
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsAdminUser | IsSuperAdmin]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser | IsSuperAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PayoutCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PayoutUpdateSerializer
        return PayoutSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        # Apply filters
        status_filter = self.request.query_params.get('status')
        vendor_id = self.request.query_params.get('vendor_id')
        queryset = Payout.objects.all()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
        
        # Role-based filtering
        if user.role == 'admin' or user.is_superuser:
            return queryset
        elif user.role == 'vendor':
            vendor = Vendor.objects.get(user=user)
            return queryset.filter(vendor=vendor)
        
        return queryset.none()
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def mark_paid(self, request, pk=None):
        """Mark payout as paid"""
        payout = self.get_object()
        
        if payout.status == 'paid':
            return Response({
                'error': 'Payout is already marked as paid'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        payout.status = 'paid'
        payout.paid_at = timezone.now()
        payout.save()
        
        return Response({
            'status': 'success',
            'message': 'Payout marked as paid successfully'
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsVendorUser])
    def my_payouts(self, request):
        """Get current vendor's payouts"""
        vendor = Vendor.objects.get(user=request.user)
        payouts = Payout.objects.filter(vendor=vendor)
        
        # Calculate summary
        total_paid = payouts.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0
        total_pending = payouts.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
        
        page = self.paginate_queryset(payouts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                'summary': {
                    'total_paid': float(total_paid),
                    'total_pending': float(total_pending),
                    'total_payouts': payouts.count()
                },
                'results': serializer.data
            })
        
        serializer = self.get_serializer(payouts, many=True)
        return Response({
            'summary': {
                'total_paid': float(total_paid),
                'total_pending': float(total_pending),
                'total_payouts': payouts.count()
            },
            'payouts': serializer.data
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser | IsSuperAdmin])
    def summary(self, request):
        """Admin payout summary"""
        
        payouts = Payout.objects.all()
        
        paid_payouts = payouts.filter(status='paid')
        pending_payouts = payouts.filter(status='pending')
        
        total_paid = paid_payouts.aggregate(total=Sum('amount'))['total'] or 0
        total_pending = pending_payouts.aggregate(total=Sum('amount'))['total'] or 0
        
        return Response({
            'processed_amount': float(total_paid),
            'processed_count': paid_payouts.count(),
            'pending_amount': float(total_pending),
            'pending_count': pending_payouts.count(),
            'next_payout_date': None,  # Add logic if you track this
        })




# ====================
# DASHBOARD VIEWS
# ====================
class DashboardView(APIView):
    permission_classes = [IsAdminUser | IsSuperAdmin]
    
    def get(self, request):
        # Calculate dashboard statistics
        total_users = User.objects.count()
        total_vendors = Vendor.objects.count()
        total_products = Product.objects.count()
        total_orders = Order.objects.count()
        
        # Revenue calculations
        total_revenue = Order.objects.filter(status='delivered').aggregate(
            total=Sum('total_amount')
        )['total'] or 0
        
        # Active orders (not cancelled or delivered)
        active_orders = Order.objects.filter(
            status__in=['pending', 'confirmed', 'picked']
        ).count()
        
        pending_vendors = Vendor.objects.filter(status='pending').count()
        
        # In transit
        in_transit = Order.objects.filter(status='picked').count()
        
        # Recent orders
        recent_orders = Order.objects.select_related('customer').order_by('-created_at')[:10]
        recent_orders_serializer = OrderSerializer(recent_orders, many=True)
        
        return Response({
            'stats': {
                'total_users': total_users,
                'total_vendors': total_vendors,
                'total_products': total_products,
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'active_orders': active_orders,  # Changed from pending_orders
                'pending_vendors': pending_vendors,
                'in_transit': in_transit,  # Added
            },
            'recent_orders': recent_orders_serializer.data
        })


class OrderStatusCountsView(APIView):
    permission_classes = [IsAdminUser | IsSuperAdmin]
    
    def get(self, request):
        from django.db.models import Count
        
        status_counts = Order.objects.values('status').annotate(
            count=Count('id')
        )
        
        # Convert to dict for easier access
        counts = {item['status']: item['count'] for item in status_counts}
        
        return Response({
            'pending': counts.get('pending', 0),
            'processing': counts.get('confirmed', 0),  # Map 'confirmed' to 'processing'
            'shipped': counts.get('picked', 0),  # Map 'picked' to 'shipped'
            'delivered': counts.get('delivered', 0),
        })
    


 
# ====================
# PAYOUT SUMMARY (New endpoint)
# ====================
class PayoutSummaryView(APIView):
    permission_classes = [IsAdminUser | IsSuperAdmin]
    
    def get(self, request):
        from django.utils import timezone
        
        # Pending payouts
        pending_payouts = Payout.objects.filter(status='pending')
        pending_amount = pending_payouts.aggregate(total=Sum('amount'))['total'] or 0
        pending_count = pending_payouts.count()
        
        # Processed this month
        first_day_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0)
        processed_this_month = Payout.objects.filter(
            status='paid',
            paid_at__gte=first_day_of_month
        )
        processed_amount = processed_this_month.aggregate(total=Sum('amount'))['total'] or 0
        processed_count = processed_this_month.count()
        
        return Response({
            'pending_amount': float(pending_amount),
            'pending_count': pending_count,
            'processed_amount': float(processed_amount),
            'processed_count': processed_count,
            'next_payout_date': '2026-01-30'  # You can make this dynamic
        })   


# ====================
# LOGISTICS ENDPOINT (Missing in your backend)
# ====================
class LogisticsStatsView(APIView):
    permission_classes = [IsAdminUser | IsSuperAdmin]
    
    def get(self, request):
        # Packages in transit (orders that are picked but not delivered)
        in_transit = Order.objects.filter(status__in=['picked', 'confirmed']).count()
        
        # Delivered today
        from django.utils import timezone
        today = timezone.now().date()
        delivered_today = Order.objects.filter(
            status='delivered',
            updated_at__date=today
        ).count()
        
        # Active drivers
        active_drivers = User.objects.filter(role='rider', is_active=True).count()
        
        # Delivery by province
        from django.db.models import Q, Count
        provinces = Order.objects.values('city').annotate(
            active=Count('id', filter=Q(status__in=['picked', 'confirmed'])),
            completed=Count('id', filter=Q(status='delivered'))
        ).order_by('-active')
        
        delivery_by_province = [
            {
                'province': p['city'],
                'active': p['active'],
                'completed': p['completed']
            }
            for p in provinces
        ]
        
        return Response({
            'packages_in_transit': in_transit,
            'delivered_today': delivered_today,
            'active_drivers': active_drivers,
            'delivery_by_province': delivery_by_province
        })



class VendorDashboardView(APIView):
    permission_classes = [IsVendorUser]
    
    def get(self, request):
        # Get or create vendor (defensive check for orphaned vendor users)
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            # This shouldn't happen, but if it does, create a default vendor
            from django.db import transaction
            with transaction.atomic():
                # Get the most recent approved application if available
                app = SellerApplication.objects.filter(
                    phone=request.user.phone,
                    status='approved'
                ).order_by('-reviewed_at').first()
                
                if app:
                    vendor = Vendor.objects.create(
                        user=request.user,
                        shop_name=app.shop_name,
                        address=app.address,
                        city=app.city,
                        identity_document=app.identity_document,
                        business_document=app.business_document,
                        status='approved'
                    )
                    if app.vendor_id is None:
                        app.vendor = vendor
                        app.save()
                else:
                    # Create minimal vendor
                    vendor = Vendor.objects.create(
                        user=request.user,
                        shop_name=f"{request.user.full_name}'s Shop",
                        address='Business address not yet provided',
                        city='Location not provided',
                        status='pending'
                    )
        
        # Vendor statistics
        total_products = Product.objects.filter(vendor=vendor).count()
        active_products = Product.objects.filter(
            vendor=vendor,
            status='approved'
        ).count()
        
        # Order statistics
        vendor_orders = OrderItem.objects.filter(vendor=vendor)
        total_sales = vendor_orders.aggregate(total=Sum('price_at_order'))['total'] or 0
        
        # Group by status
        order_status = OrderItem.objects.filter(vendor=vendor).values(
            'order__status'
        ).annotate(count=Count('id')).order_by('order__status')
        
        # Recent orders
        recent_order_ids = vendor_orders.values_list('order_id', flat=True).distinct()[:10]
        recent_orders = Order.objects.filter(id__in=recent_order_ids).order_by('-created_at')
        recent_orders_serializer = OrderSerializer(recent_orders, many=True)
        
        # Payout summary
        payouts = Payout.objects.filter(vendor=vendor)
        total_paid = payouts.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0
        total_pending = payouts.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
        
        return Response({
            'vendor': VendorSerializer(vendor).data,
            'stats': {
                'total_products': total_products,
                'active_products': active_products,
                'total_sales': float(total_sales),
                'total_paid': float(total_paid),
                'total_pending': float(total_pending),
                'order_status': list(order_status)
            },
            'recent_orders': recent_orders_serializer.data
        })

# changes by Noman for user profile page only

# ====================
# USER PROFILE VIEWS (ADD THESE)
# ====================
from .serializer import (
    UserProfileSerializer, ChangePasswordSerializer,
    AddressSerializer,
    ReviewSerializer, ReviewCreateSerializer,
    CartSerializer, CartCreateSerializer
)
from .models import Address, Review, Cart

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get user profile"""
        serializer = UserProfileSerializer(request.user)
        return Response({
            'status': 'success',
            'user': serializer.data
        })

    def put(self, request):
        """Update user profile"""
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'message': 'Profile updated successfully',
                'user': serializer.data
            })
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save()
            return Response({
                'status': 'success',
                'message': 'Password changed successfully'
            })
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


# ====================
# ADDRESS VIEWS (ADD THESE)
# ====================
from rest_framework import generics

class AddressListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AddressSerializer

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({
            'status': 'success',
            'message': 'Address added successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AddressSerializer

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'status': 'success',
            'message': 'Address updated successfully',
            'data': serializer.data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({
            'status': 'success',
            'message': 'Address deleted successfully'
        }, status=status.HTTP_200_OK)


# ====================
# ORDER VIEWS FOR PROFILE (ADD THESE)
# ====================
class OrderListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = Order.objects.filter(customer=self.request.user)
        
        if not queryset.exists():
            queryset = Order.objects.filter(
                customer_phone=self.request.user.phone,
                customer__isnull=True
            )
        
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user)


# ====================
# WISHLIST VIEWS (ADD THESE)
# ====================
# class WishlistListView(generics.ListCreateAPIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def get_serializer_class(self):
#         if self.request.method == 'POST':
#             return WishlistCreateSerializer
#         return WishlistSerializer

#     def get_queryset(self):
#         return Wishlist.objects.filter(user=self.request.user)

#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         wishlist = serializer.save()
        
#         # Return full wishlist data
#         response_serializer = WishlistSerializer(wishlist, context={'request': request})
#         return Response({
#             'status': 'success',
#             'message': 'Added to wishlist',
#             'data': response_serializer.data
#         }, status=status.HTTP_201_CREATED)

#     def list(self, request, *args, **kwargs):
#         queryset = self.get_queryset()
#         serializer = WishlistSerializer(queryset, many=True, context={'request': request})
#         return Response(serializer.data)


# class WishlistDetailView(generics.DestroyAPIView):
#     permission_classes = [permissions.IsAuthenticated]
#     serializer_class = WishlistSerializer

#     def get_queryset(self):
#         return Wishlist.objects.filter(user=self.request.user)

#     def destroy(self, request, *args, **kwargs):
#         instance = self.get_object()
#         self.perform_destroy(instance)
#         return Response({
#             'status': 'success',
#             'message': 'Removed from wishlist'
#         }, status=status.HTTP_200_OK)


# ====================
# REVIEW VIEWS (ADD THESE)
# ====================
class ReviewListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()

        vendor_user = getattr(getattr(review.product, 'vendor', None), 'user', None)
        if vendor_user:
            Notification.objects.create(
                user=vendor_user,
                notification_type='new_review',
                title='New product review',
                message=(
                    f"{request.user.full_name} left a {review.rating}-star review on "
                    f"{review.product.name}."
                ),
                link='/vendor/reviews',
            )
        
        response_serializer = ReviewSerializer(review, context={'request': request})
        return Response({
            'status': 'success',
            'message': 'Review submitted successfully',
            'data': response_serializer.data
        }, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ReviewSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'status': 'success',
            'message': 'Review updated successfully',
            'data': serializer.data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({
            'status': 'success',
            'message': 'Review deleted successfully'
        }, status=status.HTTP_200_OK)

# ====================
# CART VIEWS (ADD THESE)
# ====================
class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get user cart"""
        cart_items = Cart.objects.filter(user=request.user)
        serializer = CartSerializer(cart_items, many=True, context={'request': request})
        
        total = sum(item.total_price for item in cart_items)
        
        return Response({
            'status': 'success',
            'items': serializer.data,
            'total': total,
            'count': cart_items.count()
        })

    def post(self, request):
        """Add item to cart"""
        serializer = CartCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            cart = serializer.save()
            response_serializer = CartSerializer(cart, context={'request': request})
            return Response({
                'status': 'success',
                'message': 'Added to cart',
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """Clear cart"""
        Cart.objects.filter(user=request.user).delete()
        return Response({
            'status': 'success',
            'message': 'Cart cleared'
        })


class CartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        """Update cart item quantity"""
        try:
            cart_item = Cart.objects.get(id=pk, user=request.user)
            quantity = request.data.get('quantity')
            
            if quantity and quantity > 0:
                cart_item.quantity = quantity
                cart_item.save()
                
                serializer = CartSerializer(cart_item, context={'request': request})
                return Response({
                    'status': 'success',
                    'message': 'Cart updated',
                    'data': serializer.data
                })
            else:
                return Response({
                    'status': 'error',
                    'message': 'Invalid quantity'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Cart.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        """Remove item from cart"""
        try:
            cart_item = Cart.objects.get(id=pk, user=request.user)
            cart_item.delete()
            return Response({
                'status': 'success',
                'message': 'Item removed from cart'
            })
        except Cart.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)