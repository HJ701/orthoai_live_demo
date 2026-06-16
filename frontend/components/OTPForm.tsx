'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  Link,
} from '@mui/material'
import { Lock, Refresh } from '@mui/icons-material'
import { useLogin, useRequestOTP } from '@/lib/hooks/useAuthMutations'

interface OTPFormProps {
  email: string
  onBack: () => void
  // Dev-only OTP returned by the backend when no email is actually sent
  // (DEV_EXPOSE_OTP=true). Undefined in production.
  initialDevOtp?: string | null
}

const RESEND_COOLDOWN_SECONDS = 60

export default function OTPForm({ email, onBack, initialDevOtp }: OTPFormProps) {
  const router = useRouter()
  const [otp, setOtp] = useState(initialDevOtp ?? '')
  const [devOtp, setDevOtp] = useState<string | null | undefined>(initialDevOtp)
  const [error, setError] = useState('')
  const [resendCooldown, setResendCooldown] = useState(0)
  const [resendSuccess, setResendSuccess] = useState(false)
  const { login, isLoading, error: mutationError } = useLogin()
  const { requestOTP, isLoading: isResending } = useRequestOTP()
  const cooldownIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Update error state when mutation error changes
  useEffect(() => {
    if (mutationError) {
      setError(mutationError.message || 'Invalid OTP. Please try again.')
    }
  }, [mutationError])

  // Handle resend cooldown timer
  useEffect(() => {
    if (resendCooldown > 0) {
      cooldownIntervalRef.current = setInterval(() => {
        setResendCooldown((prev) => {
          if (prev <= 1) {
            if (cooldownIntervalRef.current) {
              clearInterval(cooldownIntervalRef.current)
              cooldownIntervalRef.current = null
            }
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }

    return () => {
      if (cooldownIntervalRef.current) {
        clearInterval(cooldownIntervalRef.current)
      }
    }
  }, [resendCooldown])

  const handleResendOTP = async () => {
    if (resendCooldown > 0) return

    setError('')
    setResendSuccess(false)

    try {
      const res = await requestOTP({ email })
      if (res?.dev_otp) {
        setDevOtp(res.dev_otp)
        setOtp(res.dev_otp)
      }
      setResendCooldown(RESEND_COOLDOWN_SECONDS)
      setResendSuccess(true)
      // Clear success message after 3 seconds
      setTimeout(() => {
        setResendSuccess(false)
      }, 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to resend OTP. Please try again.')
    }
  }

  const handleSignIn = async () => {
    if (!otp) {
      setError('Please enter the OTP code')
      return
    }

    setError('')

    try {
      const result = await login({ email, otp })
      
      // Check if login was successful (status 200)
      if (result) {
        // Store email for reference
        sessionStorage.setItem('userEmail', email)
        const hasAcceptedTerms = sessionStorage.getItem('termsAccepted')
        if (hasAcceptedTerms) {
          router.push('/upload')
        } else {
          router.push('/terms')
        }
      } else {
        setError('Login failed. Please try again.')
      }
    } catch (err: any) {
      // Handle error - show error message
      setError(err.message || 'Invalid OTP. Please try again.')
    }
  }

  return (
    <Box>
      <Alert severity="success" sx={{ mb: 3 }}>
        OTP code sent to {email}
      </Alert>

      {devOtp && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Dev mode: no email is sent locally. Your code is{' '}
          <strong>{devOtp}</strong> (pre-filled below).
        </Alert>
      )}

      {resendSuccess && (
        <Alert severity="success" sx={{ mb: 2 }}>
          OTP code has been resent to {email}
        </Alert>
      )}

      <TextField
        fullWidth
        label="Enter OTP Code"
        type="text"
        value={otp}
        onChange={(e) => setOtp(e.target.value)}
        placeholder="123456"
        sx={{ mb: 2 }}
        InputProps={{
          startAdornment: <Lock sx={{ mr: 1, color: '#9ca3af' }} />,
        }}
        error={!!error}
        helperText={error}
        inputProps={{
          maxLength: 6,
          pattern: '[0-9]*',
        }}
      />

      <Box display="flex" justifyContent="flex-end" mb={2}>
        <Button
          variant="text"
          size="small"
          startIcon={<Refresh />}
          onClick={handleResendOTP}
          disabled={resendCooldown > 0 || isResending}
          sx={{
            color: resendCooldown > 0 ? '#9ca3af' : '#6366f1',
            textTransform: 'none',
            minWidth: 'auto',
          }}
        >
          {isResending
            ? 'Sending...'
            : resendCooldown > 0
            ? `Resend OTP (${resendCooldown}s)`
            : 'Resend OTP'}
        </Button>
      </Box>

      <Button
        fullWidth
        variant="contained"
        className="gradient-purple"
        onClick={handleSignIn}
        disabled={isLoading || !otp}
        sx={{
          color: 'white',
          py: 1.5,
          mb: 2,
          borderRadius: 2,
          textTransform: 'none',
        }}
      >
        {isLoading ? 'Signing in...' : 'Sign In'}
      </Button>

      <Box textAlign="center">
        <Link
          component="button"
          variant="body2"
          onClick={onBack}
          sx={{ color: '#6366f1', cursor: 'pointer' }}
        >
          Use a different email
        </Link>
      </Box>
    </Box>
  )
}

