'use client'

import { useEffect, useState } from 'react'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  Paper,
  Chip,
  Grid,
  Alert,
  CircularProgress,
} from '@mui/material'
import { Assignment, VerifiedUser } from '@mui/icons-material'
import { motion } from 'framer-motion'
import { usersAPI, Activity } from '@/lib/api'

// Matches the old frontend's formatDate — concise, readable timestamps.
function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function AccountPage() {
  const [activity, setActivity] = useState<Activity | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    usersAPI
      .activity()
      .then((loaded) => {
        if (mounted) setActivity(loaded)
      })
      .catch((err) => {
        if (mounted)
          setError(
            err instanceof Error ? err.message : 'Unable to load account activity.',
          )
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  if (loading) {
    return (
      <Box className="min-h-screen flex items-center justify-center">
        <CircularProgress />
      </Box>
    )
  }

  const user = activity?.user
  const role =
    user?.auth_provider === 'email' ? 'Clinician' : user?.auth_provider || '—'

  const infoCards = [
    { label: 'Email', value: user?.email || '—' },
    { label: 'Role', value: role },
    { label: 'Data Residency', value: 'UAE/GCC' },
    { label: 'Terms & Conditions', value: user?.terms_accepted ? 'Accepted' : 'Pending' },
  ]

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
      sx={{ py: { xs: 4, md: 6 }, px: { xs: 2, md: 0 } }}
    >
      <Container maxWidth="lg">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Typography
            variant="h4"
            className="font-bold text-gray-900 mb-4"
            sx={{ fontSize: { xs: '1.75rem', md: '2rem' } }}
          >
            Account
          </Typography>
        </motion.div>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {/* Account information */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h6" className="font-semibold text-gray-800 mb-3">
                Account Information
              </Typography>
              <Grid container spacing={2}>
                {infoCards.map((c) => (
                  <Grid item xs={12} sm={6} md={3} key={c.label}>
                    <Paper
                      elevation={0}
                      sx={{ p: 2, bgcolor: '#f9fafb', borderRadius: 2, height: '100%' }}
                    >
                      <Typography
                        variant="caption"
                        className="text-gray-500"
                        sx={{ textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 700 }}
                      >
                        {c.label}
                      </Typography>
                      <Typography
                        variant="body1"
                        className="font-semibold text-gray-800"
                        sx={{ mt: 1, wordBreak: 'break-all' }}
                      >
                        {c.value}
                      </Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </motion.div>

        {/* Cases + Clinical validations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
        >
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} md={6}>
              <Card className="glass-effect" sx={{ height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <Box display="flex" alignItems="center" gap={1.5} mb={2}>
                    <Assignment sx={{ color: '#6366f1' }} />
                    <Typography variant="h6" className="font-semibold text-gray-800">
                      Cases ({activity?.cases.length ?? 0})
                    </Typography>
                  </Box>
                  <Box display="flex" flexDirection="column" gap={1.5}>
                    {activity?.cases.length ? (
                      activity.cases.map((item) => (
                        <Paper
                          key={item.id}
                          elevation={0}
                          sx={{ p: 1.5, border: '1px solid #e5e7eb', borderRadius: 2 }}
                        >
                          <Box
                            display="flex"
                            justifyContent="space-between"
                            alignItems="center"
                            gap={1}
                          >
                            <Typography className="font-semibold text-gray-800">
                              {item.title || `Case #${item.id}`}
                            </Typography>
                            <Chip
                              label={item.status || 'unknown'}
                              size="small"
                              color={item.status === 'done' ? 'success' : 'default'}
                              sx={{ textTransform: 'capitalize' }}
                            />
                          </Box>
                          <Typography variant="caption" className="text-gray-500">
                            {item.patient_id || '—'} · {formatDate(item.created_at)}
                          </Typography>
                        </Paper>
                      ))
                    ) : (
                      <Typography variant="body2" className="text-gray-500">
                        No case activity recorded.
                      </Typography>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card className="glass-effect" sx={{ height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <Box display="flex" alignItems="center" gap={1.5} mb={2}>
                    <VerifiedUser sx={{ color: '#6366f1' }} />
                    <Typography variant="h6" className="font-semibold text-gray-800">
                      Clinical Validations ({activity?.clinical_validations.length ?? 0})
                    </Typography>
                  </Box>
                  <Box display="flex" flexDirection="column" gap={1.5}>
                    {activity?.clinical_validations.length ? (
                      activity.clinical_validations.map((item) => (
                        <Paper
                          key={item.id}
                          elevation={0}
                          sx={{ p: 1.5, border: '1px solid #e5e7eb', borderRadius: 2 }}
                        >
                          <Box
                            display="flex"
                            justifyContent="space-between"
                            alignItems="center"
                            gap={1}
                          >
                            <Typography className="font-semibold text-gray-800">
                              {item.case_id}
                            </Typography>
                            <Chip
                              label={item.class_match ? 'match' : 'review'}
                              size="small"
                              color={item.class_match ? 'success' : 'warning'}
                            />
                          </Box>
                          <Typography variant="caption" className="text-gray-500">
                            {item.site} · OrthoAI case #{item.orthoai_case_id} ·{' '}
                            {formatDate(item.created_at)}
                          </Typography>
                        </Paper>
                      ))
                    ) : (
                      <Typography variant="body2" className="text-gray-500">
                        No clinical validation activity recorded.
                      </Typography>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </motion.div>

        {/* Audit log */}
      </Container>
    </Box>
  )
}
