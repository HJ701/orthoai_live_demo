'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  LinearProgress,
  CircularProgress,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Alert,
} from '@mui/material'
import { Cancel, CheckCircle } from '@mui/icons-material'
import { motion } from 'framer-motion'

type Status = 'queued' | 'processing' | 'generating' | 'completed' | 'failed'

interface StatusStep {
  status: Status
  label: string
  description: string
}

const STATUS_STEPS: StatusStep[] = [
  {
    status: 'queued',
    label: 'Queued',
    description: 'Your case has been queued for processing',
  },
  {
    status: 'processing',
    label: 'Processing',
    description: 'Checking image quality and extracting features',
  },
  {
    status: 'generating',
    label: 'Generating',
    description: 'Producing summary & findings',
  },
]

function InferencePageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const caseId = searchParams.get('case_id') || 'unknown'
  const jobIdParam = searchParams.get('job_id')

  const [currentStatus, setCurrentStatus] = useState<Status>('queued')
  const [progress, setProgress] = useState(0)
  const [estimatedTime, setEstimatedTime] = useState<number | null>(null)
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<number | null>(
    jobIdParam ? parseInt(jobIdParam) : null
  )

  useEffect(() => {
    // Get job ID from sessionStorage if not in URL
    if (!jobId) {
      const storedJobId = sessionStorage.getItem('jobId')
      if (storedJobId) {
        setJobId(parseInt(storedJobId))
      } else {
        setError('Job ID not found')
        return
      }
    }

    if (!jobId) return

    // Poll job status
    const pollInterval = setInterval(async () => {
      try {
        const { inferenceAPI } = await import('@/lib/api')
        const status = await inferenceAPI.getStatus(jobId)

        // Map backend states to frontend states
        const stateMap: Record<string, Status> = {
          queued: 'queued',
          running: 'processing',
          done: 'completed',
          error: 'failed',
        }
        setCurrentStatus(stateMap[status.state] || 'queued')

        // Update progress (convert from 0.0-1.0 to 0-100)
        setProgress(Math.round(status.progress * 100))

        // Handle errors
        if (status.error_message) {
          setError(status.error_message)
        }

        // If completed, navigate to results
        if (status.state === 'done') {
          clearInterval(pollInterval)
          setTimeout(() => {
            router.push(`/results?case_id=${caseId}`)
          }, 1000)
        }

        // If error, stop polling
        if (status.state === 'error') {
          clearInterval(pollInterval)
          setError(status.error_message || 'Inference failed')
        }

        // Calculate estimated time based on progress
        if (status.started_at && status.progress > 0) {
          const elapsed = Date.now() - new Date(status.started_at).getTime()
          const estimatedTotal = elapsed / status.progress
          const remaining = Math.max(0, estimatedTotal - elapsed)
          setEstimatedTime(Math.round(remaining / 1000))
        } else {
          setEstimatedTime(45) // Default estimate
        }
      } catch (err: any) {
        setError(err.message || 'Failed to fetch job status')
        clearInterval(pollInterval)
      }
    }, 2000) // Poll every 2 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [router, caseId, jobId])

  const handleCancel = () => {
    setCancelDialogOpen(true)
  }

  const confirmCancel = async () => {
    if (!jobId) {
      router.push('/upload')
      return
    }

    try {
      const { inferenceAPI } = await import('@/lib/api')
      await inferenceAPI.cancelJob(jobId)
      router.push('/upload')
    } catch (err: any) {
      setError(err.message || 'Failed to cancel job')
      setCancelDialogOpen(false)
    }
  }

  const currentStep = STATUS_STEPS.find((step) => step.status === currentStatus) || STATUS_STEPS[0]
  const currentStepIndex = STATUS_STEPS.findIndex((step) => step.status === currentStatus)

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50 flex items-center justify-center"
      sx={{ py: { xs: 4, md: 8 }, px: { xs: 2, md: 0 } }}
    >
      <Container maxWidth="md">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="glass-effect" sx={{ p: { xs: 3, md: 6 } }}>
            <CardContent>
              <Box display="flex" flexDirection="column" alignItems="center">
                {/* Case ID */}
                <Typography variant="caption" className="text-gray-500 mb-4">
                  Case ID: {caseId}
                </Typography>

                {/* Status Indicator */}
                <Box display="flex" gap={2} mb={4} sx={{ width: '100%', justifyContent: 'center' }}>
                  {STATUS_STEPS.map((step, index) => {
                    const isActive = index <= currentStepIndex
                    const isCurrent = step.status === currentStatus

                    return (
                      <motion.div
                        key={step.status}
                        initial={{ opacity: 0.3 }}
                        animate={{
                          opacity: isActive ? 1 : 0.3,
                          scale: isCurrent ? 1.1 : 1,
                        }}
                        transition={{ duration: 0.3 }}
                      >
                        <Box
                          sx={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            gap: 1,
                            minWidth: 100,
                          }}
                        >
                          <Box
                            sx={{
                              width: 48,
                              height: 48,
                              borderRadius: '50%',
                              bgcolor: isActive ? '#6366f1' : '#e5e7eb',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: 'white',
                              fontWeight: 600,
                              transition: 'all 0.3s ease',
                            }}
                          >
                            {isActive && index < currentStepIndex ? (
                              <CheckCircle />
                            ) : (
                              index + 1
                            )}
                          </Box>
                          <Typography
                            variant="caption"
                            sx={{
                              fontWeight: isCurrent ? 600 : 400,
                              color: isActive ? '#6366f1' : '#9ca3af',
                              textAlign: 'center',
                            }}
                          >
                            {step.label}
                          </Typography>
                        </Box>
                      </motion.div>
                    )
                  })}
                </Box>

                {/* Animated Progress Orb */}
                <motion.div
                  animate={{
                    scale: [1, 1.1, 1],
                    opacity: [0.8, 1, 0.8],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                  className="mb-6"
                >
                  <Box
                    sx={{
                      width: { xs: 120, md: 160 },
                      height: { xs: 120, md: 160 },
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: '0 20px 60px rgba(99, 102, 241, 0.4)',
                      position: 'relative',
                    }}
                  >
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{
                        duration: 3,
                        repeat: Infinity,
                        ease: 'linear',
                      }}
                    >
                      <CircularProgress
                        variant="determinate"
                        value={progress}
                        size={140}
                        thickness={2}
                        sx={{
                          color: 'white',
                          position: 'absolute',
                        }}
                      />
                    </motion.div>
                    <Typography
                      variant="h4"
                      className="font-bold text-white"
                      sx={{ fontSize: { xs: '2rem', md: '2.5rem' } }}
                    >
                      {progress}%
                    </Typography>
                  </Box>
                </motion.div>

                {/* Progress Bar */}
                <Box sx={{ width: '100%', mb: 4 }}>
                  <LinearProgress
                    variant="determinate"
                    value={progress}
                    sx={{
                      height: 8,
                      borderRadius: 4,
                      bgcolor: 'rgba(99, 102, 241, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        borderRadius: 4,
                        background: 'linear-gradient(90deg, #667eea 0%, #764ba2 100%)',
                      },
                    }}
                  />
                </Box>

                {/* Current Status Description */}
                <Typography
                  variant="h6"
                  className="font-semibold text-gray-800 mb-2"
                  sx={{ fontSize: { xs: '1.25rem', md: '1.5rem' }, textAlign: 'center' }}
                >
                  {currentStep.description}
                </Typography>

                {/* Estimated Time */}
                {estimatedTime !== null && estimatedTime > 0 && (
                  <Typography variant="body2" className="text-gray-500 mb-4">
                    Estimated time remaining: {Math.floor(estimatedTime / 60)}:
                    {String(estimatedTime % 60).padStart(2, '0')}
                  </Typography>
                )}

                {/* Error Message */}
                {error && (
                  <Alert severity="error" sx={{ mb: 4, width: '100%' }}>
                    {error}
                  </Alert>
                )}

                {/* Cancel Button */}
                <Button
                  variant="outlined"
                  startIcon={<Cancel />}
                  onClick={handleCancel}
                  sx={{
                    borderColor: '#ef4444',
                    color: '#ef4444',
                    mt: 2,
                    mb: 2,
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                    '&:hover': {
                      borderColor: '#dc2626',
                      bgcolor: 'rgba(239, 68, 68, 0.05)',
                    },
                  }}
                >
                  Cancel Analysis
                </Button>

                {/* Background Navigation Notice */}
                <Typography
                  variant="caption"
                  className="text-gray-400 mt-4 text-center"
                  sx={{ maxWidth: '400px' }}
                >
                  You can navigate away safely. Progress will continue in the background.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </motion.div>
      </Container>

      {/* Cancel Confirmation Dialog */}
      <Dialog
        open={cancelDialogOpen}
        onClose={() => setCancelDialogOpen(false)}
        aria-labelledby="cancel-dialog-title"
      >
        <DialogTitle id="cancel-dialog-title">Cancel Analysis?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to cancel this analysis? The current progress will be lost.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelDialogOpen(false)} sx={{ textTransform: 'none' }}>
            Continue Analysis
          </Button>
          <Button
            onClick={confirmCancel}
            color="error"
            variant="contained"
            sx={{ textTransform: 'none', mb: 2 }}
          >
            Cancel Analysis
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default function InferencePage() {
  return (
    <Suspense fallback={
      <Box className="min-h-screen flex items-center justify-center">
        <CircularProgress />
      </Box>
    }>
      <InferencePageContent />
    </Suspense>
  )
}
