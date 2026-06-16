'use client'

import { useState } from 'react'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
} from '@mui/material'
import { motion } from 'framer-motion'
import LoginForm from '@/components/LoginForm'
import OTPForm from '@/components/OTPForm'

export default function SignInPage() {
  const [otpSent, setOtpSent] = useState(false)
  const [email, setEmail] = useState('')
  const [devOtp, setDevOtp] = useState<string | null | undefined>(undefined)

  const handleOTPSent = (userEmail: string, code?: string | null) => {
    setEmail(userEmail)
    setDevOtp(code)
    setOtpSent(true)
  }

  const handleBack = () => {
    setOtpSent(false)
    setEmail('')
    setDevOtp(undefined)
  }

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50 flex items-center justify-center"
      sx={{ py: 4, px: 2 }}
    >
      <Container maxWidth="sm">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="glass-effect" sx={{ p: 4 }}>
            <CardContent>
              <Box textAlign="center" mb={4}>
                <Typography
                  variant="h4"
                  className="font-bold text-gray-900 mb-2"
                >
                  Sign In
                </Typography>
                <Typography variant="body2" className="text-gray-600">
                  Access your clinical diagnostic assistant
                </Typography>
              </Box>

              {!otpSent ? (
                <LoginForm onOTPSent={handleOTPSent} />
              ) : (
                <OTPForm email={email} onBack={handleBack} initialDevOtp={devOtp} />
              )}
            </CardContent>
          </Card>
        </motion.div>
      </Container>
    </Box>
  )
}

