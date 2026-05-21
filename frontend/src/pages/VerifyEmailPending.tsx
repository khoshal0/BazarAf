import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Mail, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '../app/components/ui/button';
import { Card } from '../app/components/ui/card';
import { authAPI } from '../services/api';

export default function VerifyEmailPending() {
  const navigate = useNavigate();
  const location = useLocation();
  const email = (location.state as any)?.email || '';
  const emailSent = (location.state as any)?.emailSent ?? true;
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState('');
  const [resendStatus, setResendStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const handleResend = async () => {
    if (!email) return;
    setResending(true);
    setResendMessage('');
    try {
      const result = await authAPI.resendVerificationEmail(email);
      setResendStatus('success');
      setResendMessage(result.message || 'Verification email sent!');
    } catch (error: any) {
      setResendStatus('error');
      setResendMessage(error?.response?.data?.message || 'Failed to resend. Please try again.');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-teal-50 to-blue-50 px-4">
      <Card className="w-full max-w-md shadow-lg">
        <div className="p-8 text-center">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center">
              <Mail className="w-8 h-8 text-amber-600" />
            </div>
          </div>

          <h1 className="text-2xl font-bold mb-2">Verify Your Email</h1>
          <p className="text-gray-600 mb-6">
            {emailSent ? (
              <>
                We sent a verification link to{' '}
                <span className="font-semibold text-gray-900">{email || 'your email'}</span>.
                Please check your inbox and click the link to verify your account.
              </>
            ) : (
              <>
                We could not send a verification email to{' '}
                <span className="font-semibold text-gray-900">{email || 'your email'}</span>.
                Please use the resend button below.
              </>
            )}
          </p>

          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 text-sm text-amber-800">
            You must verify your email before you can log in.
          </div>

          {resendMessage && (
            <div className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
              resendStatus === 'success' 
                ? 'bg-green-50 text-green-700 border border-green-200' 
                : 'bg-red-50 text-red-700 border border-red-200'
            }`}>
              {resendStatus === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              {resendMessage}
            </div>
          )}

          <div className="space-y-3">
            <Button
              onClick={handleResend}
              disabled={resending || !email}
              variant="outline"
              className="w-full"
            >
              {resending ? 'Sending...' : 'Resend Verification Email'}
            </Button>

            <Button
              onClick={() => navigate('/login')}
              className="w-full bg-teal-600 hover:bg-teal-700"
            >
              Back to Login
            </Button>
          </div>

          <p className="mt-6 text-xs text-gray-500">
            Check your spam folder if you don't see the email.
          </p>
        </div>
      </Card>
    </div>
  );
}
