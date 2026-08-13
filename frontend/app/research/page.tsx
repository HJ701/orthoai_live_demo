'use client'

import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import Typography from '@mui/material/Typography'
import ArrowForward from '@mui/icons-material/ArrowForward'
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import ClinicianStudyWorkspace from '@/components/research/ClinicianStudyWorkspace'
import { ResearchContext, researchAPI } from '@/lib/api'

const STUDY_CODE = 'ORTHOAI-HCI-V3'

export default function ResearchModePage() {
  const router = useRouter()
  const [context, setContext] = useState<ResearchContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadClinicianWorkspace = useCallback(async () => {
    if (typeof window !== 'undefined' && !sessionStorage.getItem('authToken')) {
      router.replace('/signin')
      return
    }

    try {
      setError('')
      let next = await researchAPI.context(STUDY_CODE)
      if (next.participant?.role !== 'clinician') {
        next = await researchAPI.ensureClinicianAccess(STUDY_CODE)
      }
      if (next.participant?.role !== 'clinician') {
        throw new Error('The clinician research workspace could not be prepared.')
      }
      setContext(next)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Research Mode could not start.'
      if (/accept the terms/i.test(message)) {
        sessionStorage.setItem(
          'postTermsDestination',
          `${window.location.pathname}${window.location.search}`,
        )
        router.replace('/terms')
        return
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    void loadClinicianWorkspace()
  }, [loadClinicianWorkspace])

  if (loading) {
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    )
  }

  if (context?.participant?.role === 'clinician') {
    return <ClinicianStudyWorkspace context={context} />
  }

  return (
    <Box minHeight="100vh" sx={{ bgcolor: '#f5f7fb', py: { xs: 4, md: 8 } }}>
      <Container maxWidth="sm">
        <Card sx={{ borderRadius: 4 }}>
          <CardContent sx={{ p: { xs: 3.5, md: 5 } }}>
            <Typography variant="h4" fontWeight={850} color="#17324d">
              Research Mode could not start
            </Typography>
            <Alert severity="error" sx={{ mt: 2.5 }}>
              {error || 'The clinician workspace is temporarily unavailable.'}
            </Alert>
            <Typography color="text.secondary" mt={2}>
              Your diagnosis and uploaded images are still saved. Retry once, or
              return to Cases without repeating the upload.
            </Typography>
            <Box display="flex" gap={1.5} mt={3} flexWrap="wrap">
              <Button
                variant="contained"
                onClick={() => {
                  setLoading(true)
                  void loadClinicianWorkspace()
                }}
                sx={{ minHeight: 48, textTransform: 'none', borderRadius: 2.5 }}
              >
                Retry Research Mode
              </Button>
              <Button
                variant="outlined"
                endIcon={<ArrowForward />}
                onClick={() => router.push('/cases')}
                sx={{ minHeight: 48, textTransform: 'none', borderRadius: 2.5 }}
              >
                Open Cases
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Container>
    </Box>
  )
}
