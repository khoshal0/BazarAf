# File: backend/home/emails.py

from django.core.mail import send_mail
from django.conf import settings
import logging
import os
from email.utils import parseaddr

logger = logging.getLogger(__name__)


def _send_email(subject, message, from_email, recipient_list) -> bool:
    """Send email synchronously so failures can be reported to the caller."""
    if not settings.EMAIL_HOST_USER:
        logger.warning("Email not configured. Missing EMAIL_HOST_USER.")
        return False

    # Always use the authenticated SMTP user as sender to avoid rejection
    from_email = settings.EMAIL_HOST_USER or from_email or settings.DEFAULT_FROM_EMAIL

    # Ensure we pass a plain address to the SMTP server
    from_email = parseaddr(from_email)[1] or from_email

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info("Email sent to %s", recipient_list)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", recipient_list, exc)
        return False

def send_vendor_approval_email(vendor):
    """
    Send email notification when vendor is approved
    """
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
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
1. Log in at: {frontend_url}/login
2. Go to Vendor Dashboard
3. Start adding your products

We're excited to have you on board!

Best regards,
The BazaarAF Team
    """
    
    return _send_email(subject, message, settings.DEFAULT_FROM_EMAIL, [vendor.user.email])


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
    
    return _send_email(subject, message, settings.DEFAULT_FROM_EMAIL, [vendor.user.email])


def send_email_verification_email(user, verification_token, frontend_url=None, verification_code=None):
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

Verification Code:
{verification_code or 'Use the link above'}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Best regards,
The BazaarAF Team
    """
    
    return _send_email(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


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
    
    return _send_email(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
