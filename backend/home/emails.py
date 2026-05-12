# File: backend/home/emails.py

from django.core.mail import send_mail
from django.conf import settings
import logging
import os

logger = logging.getLogger(__name__)

def send_vendor_approval_email(vendor):
    """
    Send email notification when vendor is approved
    """
    subject = 'Congratulations! Your BazaarAF Seller Application is Approved ✅'
    
    message = f"""
Dear {vendor.user.full_name},

Congratulations! Your application to become a seller on BazaarAF has been approved! 🎉

Shop Details:
━━━━━━━━━━━━━━━━━━━━━━━━
Shop Name: {vendor.shop_name}
Location: {vendor.city}

You can now:
✓ Access your Vendor Dashboard
✓ Add and manage products
✓ Start receiving orders
✓ Track your earnings

Get Started:
1. Log in at: https://bazaaraf.com/login
2. Go to Vendor Dashboard
3. Start adding your products

Support:
━━━━━━━━━━━━━━━━━━━━━━━━
Email: seller-support@bazaaraf.com
Phone: +93 700 123 456
WhatsApp: +93 700 123 456

We're excited to have you on board!

Best regards,
The BazaarAF Team
    """
    
    try:
        # Check if email is configured
        if not settings.EMAIL_HOST_USER:
            logger.warning(f"Email not configured. Would send to: {vendor.user.email}")
            print(f"📧 EMAIL (not sent - no config): Approval email to {vendor.user.email}")
            return False
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[vendor.user.email],
            fail_silently=False,
        )
        logger.info(f"Approval email sent to {vendor.user.email}")
        print(f"✅ EMAIL SENT: Approval email to {vendor.user.email}")
        return True
    except Exception as e:
        logger.error(f"Error sending approval email: {e}")
        print(f"❌ EMAIL ERROR: {e}")
        return False


def send_vendor_rejection_email(vendor, reason=""):
    """
    Send email notification when vendor is rejected
    """
    subject = 'BazaarAF Seller Application - Additional Information Needed'
    
    message = f"""
Dear {vendor.user.full_name},

Thank you for applying to become a seller on BazaarAF.

We need some additional information before we can approve your application for "{vendor.shop_name}".

{f'Reason: {reason}' if reason else 'Please contact our support team for more details.'}

What to do next:
━━━━━━━━━━━━━━━━━━━━━━━━
Please reach out to our seller support team and we'll help you complete your application.

Support Contact:
━━━━━━━━━━━━━━━━━━━━━━━━
Email: seller-support@bazaaraf.com
Phone: +93 700 123 456
WhatsApp: +93 700 123 456

We're here to help you get started!

Best regards,
The BazaarAF Team
    """
    
    try:
        if not settings.EMAIL_HOST_USER:
            logger.warning(f"Email not configured. Would send to: {vendor.user.email}")
            print(f"📧 EMAIL (not sent - no config): Rejection email to {vendor.user.email}")
            return False
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[vendor.user.email],
            fail_silently=False,
        )
        logger.info(f"Rejection email sent to {vendor.user.email}")
        print(f"✅ EMAIL SENT: Rejection email to {vendor.user.email}")
        return True
    except Exception as e:
        logger.error(f"Error sending rejection email: {e}")
        print(f"❌ EMAIL ERROR: {e}")
        return False


def send_email_verification_email(user, verification_token, frontend_url=None):
    """
    Send email verification link to user after signup
    """
    if frontend_url is None:
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    
    subject = 'Verify your BazaarAF Email Address ✉️'
    verification_url = f"{frontend_url}/verify-email?token={verification_token}"
    
    message = f"""
Dear {user.full_name},

Thank you for signing up on BazaarAF! 🎉

To complete your registration, please verify your email address by clicking the link below:

Verification Link:
{verification_url}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Best regards,
The BazaarAF Team
    """
    
    try:
        if not settings.EMAIL_HOST_USER:
            logger.warning(f"✉️ DEVELOPMENT MODE: Email not configured. Verification link: {verification_url}")
            print(f"\n📧 VERIFICATION EMAIL (Development Mode - not sent):")
            print(f"   To: {user.email}")
            print(f"   Link: {verification_url}")
            print(f"   Expires: 24 hours\n")
            return True  # Return True to allow signup even in dev mode
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Verification email sent to {user.email}")
        print(f"✅ EMAIL SENT: Verification email to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Error sending verification email: {e}")
        print(f"❌ EMAIL ERROR: {e}")
        return True  # Don't block signup due to email errors


def send_password_reset_email(user, reset_token, frontend_url=None):
    """
    Send password reset link to user
    """
    if frontend_url is None:
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    
    subject = 'Reset Your BazaarAF Password 🔐'
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    
    message = f"""
Dear {user.full_name},

We received a request to reset your BazaarAF password.

To reset your password, please click the link below:

Reset Link:
{reset_url}

This link will expire in 1 hour.

If you didn't request a password reset, please ignore this email and your password will remain unchanged.

Best regards,
The BazaarAF Team
    """
    
    try:
        if not settings.EMAIL_HOST_USER:
            logger.warning(f"✉️ DEVELOPMENT MODE: Email not configured. Reset link: {reset_url}")
            print(f"\n📧 PASSWORD RESET EMAIL (Development Mode - not sent):")
            print(f"   To: {user.email}")
            print(f"   Link: {reset_url}")
            print(f"   Expires: 1 hour\n")
            return True  # Return True even in dev mode
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Password reset email sent to {user.email}")
        print(f"✅ EMAIL SENT: Password reset email to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")
        print(f"❌ EMAIL ERROR: {e}")
        return True  # Don't block password reset due to email errors
