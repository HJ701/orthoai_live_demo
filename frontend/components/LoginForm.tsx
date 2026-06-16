'use client'

import { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  TextField,
  Button,
  Divider,
} from '@mui/material'
import { Email } from '@mui/icons-material'
import { useRequestOTP } from '@/lib/hooks/useAuthMutations'

interface LoginFormProps {
  onOTPSent: (email: string, devOtp?: string | null) => void
}

// Email validation regex pattern
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// Email validation function
function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email.trim())
}

export default function LoginForm({ onOTPSent }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [emailTouched, setEmailTouched] = useState(false)
  const { requestOTP, isLoading, error: mutationError } = useRequestOTP()

  // Update error state when mutation error changes
  useEffect(() => {
    if (mutationError) {
      setError(mutationError.message || 'Failed to send OTP. Please try again.')
    }
  }, [mutationError])

  // Validate email format
  const emailError = emailTouched && email && !isValidEmail(email)
    ? 'Please enter a valid email address'
    : ''

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    setEmailTouched(true)
    // Clear error when user starts typing
    if (error && mutationError) {
      setError('')
    }
  }

  const handleSendOTP = async () => {
    // Reset touched state to show validation errors
    setEmailTouched(true)

    if (!email) {
      setError('Please enter your email address')
      return
    }

    if (!isValidEmail(email)) {
      setError('Please enter a valid email address')
      return
    }

    setError('')
    
    try {
      const res = await requestOTP({ email: email.trim() })
      onOTPSent(email.trim(), res?.dev_otp)
    } catch (err: any) {
      console.error(err)
      setError(err.message || 'Failed to send OTP. Please try again.')
    }
  }

  return (
    <Box>
      <TextField
        fullWidth
        label="Email Address"
        type="email"
        value={email}
        onChange={handleEmailChange}
        onBlur={() => setEmailTouched(true)}
        placeholder="clinician@example.com"
        sx={{ mb: 3 }}
        InputProps={{
          startAdornment: <Email sx={{ mr: 1, color: '#9ca3af' }} />,
        }}
        error={!!error || !!emailError}
        helperText={error || emailError}
      />

      <Button
        fullWidth
        variant="contained"
        className="gradient-purple"
        onClick={handleSendOTP}
        disabled={isLoading || !email || !isValidEmail(email)}
        sx={{
          color: 'white',
          py: 1.5,
          mb: 2,
          borderRadius: 2,
          textTransform: 'none',
        }}
      >
        {isLoading ? 'Sending...' : 'Send OTP Code'}
      </Button>

      <Divider sx={{ my: 3 }}>
        <Typography variant="body2" className="text-gray-500">
          OR
        </Typography>
      </Divider>

      <Button
        fullWidth
        variant="outlined"
        sx={{
          borderColor: '#6366f1',
          color: '#6366f1',
          py: 1.5,
          borderRadius: 2,
          textTransform: 'none',
          '&:hover': {
            borderColor: '#4f46e5',
            bgcolor: 'rgba(99, 102, 241, 0.05)',
          },
        }}
      >
        Sign in with SSO
      </Button>
    </Box>
  )
}

