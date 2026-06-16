'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Container,
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Checkbox,
  FormControlLabel,
  Alert,
  Paper,
} from '@mui/material'
import { motion } from 'framer-motion'

export default function TermsPage() {
  const router = useRouter()
  const [accepted, setAccepted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleAccept = () => {
    if (!accepted) return

    setLoading(true)
    sessionStorage.setItem('termsAccepted', 'true')
    
    setTimeout(() => {
      router.push('/upload')
      setLoading(false)
    }, 500)
  }

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
      sx={{ py: 6, px: 2 }}
    >
      <Container maxWidth="md">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="glass-effect">
            <CardContent sx={{ p: { xs: 3, md: 6 } }}>
              <Typography
                variant="h4"
                className="font-bold text-gray-900 mb-4"
                sx={{ fontSize: { xs: '1.75rem', md: '2rem' } }}
              >
                Terms & Data Use Agreement
              </Typography>

              <Alert severity="info" sx={{ mb: 4 }}>
                Please review and accept the following terms to continue.
              </Alert>

              <Paper
                elevation={0}
                sx={{
                  p: 3,
                  mb: 4,
                  bgcolor: '#f9fafb',
                  maxHeight: '400px',
                  overflow: 'auto',
                }}
              >
                <Typography variant="body2" className="text-gray-700" sx={{ mb: 2 }}>
                  <strong>1. HIPAA/GDPR Compliance</strong>
                </Typography>
                <Typography variant="body2" className="text-gray-600" sx={{ mb: 3 }}>
                  This application complies with HIPAA (Health Insurance Portability and Accountability Act) and GDPR (General Data Protection Regulation) requirements. All patient data is handled with strict confidentiality and security measures.
                </Typography>

                <Typography variant="body2" className="text-gray-700" sx={{ mb: 2 }}>
                  <strong>2. Data Residency & UAE Disclaimer</strong>
                </Typography>
                <Typography variant="body2" className="text-gray-600" sx={{ mb: 3 }}>
                  All data processed through this application is stored and processed within the UAE/GCC region. By using this service, you acknowledge that your data will remain within this geographic region in compliance with local data residency requirements.
                </Typography>

                <Typography variant="body2" className="text-gray-700" sx={{ mb: 2 }}>
                  <strong>3. Patient Data Protection</strong>
                </Typography>
                <Typography variant="body2" className="text-gray-600" sx={{ mb: 3 }}>
                  You are responsible for ensuring that all uploaded images are properly anonymized and do not contain Protected Health Information (PHI) such as patient names, faces, or other identifying information. The use of Patient ID/code is required instead of names.
                </Typography>

                <Typography variant="body2" className="text-gray-700" sx={{ mb: 2 }}>
                  <strong>4. AI Diagnostic Tool Disclaimer</strong>
                </Typography>
                <Typography variant="body2" className="text-gray-600" sx={{ mb: 3 }}>
                  This tool is for decision support only and is not a standalone diagnostic tool. All AI-generated findings must be reviewed and validated by qualified clinicians. The system provides assistance but does not replace professional clinical judgment.
                </Typography>

                <Typography variant="body2" className="text-gray-700" sx={{ mb: 2 }}>
                  <strong>5. Consent & Authority</strong>
                </Typography>
                <Typography variant="body2" className="text-gray-600">
                  By uploading clinical images, you confirm that you have obtained proper consent and have the authority to upload these images for analysis. You are responsible for maintaining appropriate documentation of patient consent.
                </Typography>
              </Paper>

              <FormControlLabel
                control={
                  <Checkbox
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                    sx={{ color: '#6366f1' }}
                  />
                }
                label={
                  <Typography variant="body2" className="text-gray-700">
                    I have read and agree to the Terms & Data Use Agreement, including HIPAA/GDPR compliance requirements and UAE data residency provisions.
                  </Typography>
                }
                sx={{ mb: 3 }}
              />

              <Box display="flex" gap={2} justifyContent="flex-end">
                <Button
                  variant="outlined"
                  onClick={() => router.push('/signin')}
                  sx={{
                    borderColor: '#6366f1',
                    color: '#6366f1',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="contained"
                  className="gradient-purple"
                  onClick={handleAccept}
                  disabled={!accepted || loading}
                  sx={{
                    color: 'white',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  {loading ? 'Processing...' : 'Accept & Continue'}
                </Button>
              </Box>
            </CardContent>
          </Card>
        </motion.div>
      </Container>
    </Box>
  )
}

