'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  InputAdornment,
  TextField,
  Typography,
} from '@mui/material'
import {
  Add,
  ArrowForward,
  CheckCircle,
  Refresh,
  Science,
  Search,
  Visibility,
} from '@mui/icons-material'
import { motion } from 'framer-motion'

import {
  CaseResponse,
  ResearchEpisode,
  casesAPI,
  inferenceAPI,
  researchAPI,
} from '@/lib/api'

const STUDY_CODE = 'ORTHOAI-HCI-V3'

type DiagnosisStatus = 'not_started' | 'completed' | 'processing' | 'failed'
type ResearchStatus = 'not_started' | 'in_progress' | 'completed'

interface CaseRow {
  case_id: string
  patient_id: string
  case_title: string
  created_at: string
  diagnosis_status: DiagnosisStatus
  latest_job_id?: number
  latest_job_error_message?: string
  research_status: ResearchStatus
  research_attempts: number
  latest_episode_id?: number
  latest_completed_episode_id?: number
}

function makeUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isReviewComplete(episode: ResearchEpisode): boolean {
  return (
    ['final_locked', 'adjudicated'].includes(episode.state) &&
    (!episode.follow_up.required || episode.follow_up.completed)
  )
}

function diagnosisStatus(value?: string): DiagnosisStatus {
  if (value === 'queued' || value === 'running') return 'processing'
  if (value === 'error') return 'failed'
  if (value === 'done') return 'completed'
  return 'not_started'
}

export default function CasesPage() {
  const router = useRouter()
  const [cases, setCases] = useState<CaseRow[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyCaseId, setBusyCaseId] = useState('')
  const [error, setError] = useState('')
  const [recentCaseId, setRecentCaseId] = useState('')

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams(window.location.search)
    setRecentCaseId(params.get('completed_case_id') || '')

    async function loadCases() {
      try {
        setError('')
        const fetchBundle = () =>
          Promise.all([
            casesAPI.listCases(),
            researchAPI
              .listEpisodes(STUDY_CODE)
              .catch(() => ({ total: 0, items: [] as ResearchEpisode[] })),
          ])
        let bundle: Awaited<ReturnType<typeof fetchBundle>>
        try {
          bundle = await fetchBundle()
        } catch {
          // Route transitions can briefly abort an in-flight GET in development.
          bundle = await fetchBundle()
        }
        if (cancelled) return
        const [apiCases, episodeList] = bundle

        const rows = apiCases.map((apiCase: CaseResponse): CaseRow => {
          let patientId = apiCase.patient_id
          let caseTitle = apiCase.title
          if (!patientId || !caseTitle) {
            const stored =
              sessionStorage.getItem(`case_${apiCase.id}`) ||
              sessionStorage.getItem('currentCase')
            if (stored) {
              try {
                const metadata = JSON.parse(stored)
                if (metadata.case_id === String(apiCase.id)) {
                  patientId = patientId || metadata.patient_id
                  caseTitle = caseTitle || metadata.case_title
                }
              } catch {
                // Legacy browser metadata is optional.
              }
            }
          }

          const attempts = episodeList.items
            .filter((episode) => episode.case_id === apiCase.id)
            .sort((a, b) => b.attempt_index - a.attempt_index || b.id - a.id)
          const latest = attempts[0]
          const latestCompleted = attempts.find(isReviewComplete)

          return {
            case_id: String(apiCase.id),
            patient_id: patientId || `PT-${apiCase.id}`,
            case_title: caseTitle || `Case ${apiCase.id}`,
            created_at: apiCase.created_at,
            diagnosis_status: diagnosisStatus(apiCase.status),
            latest_job_id: apiCase.latest_job_id || undefined,
            latest_job_error_message: apiCase.latest_job_error_message || undefined,
            research_status: !latest
              ? 'not_started'
              : isReviewComplete(latest)
                ? 'completed'
                : 'in_progress',
            research_attempts: attempts.length,
            latest_episode_id: latest?.id,
            latest_completed_episode_id: latestCompleted?.id,
          }
        })
        setCases(rows)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Cases could not be loaded.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadCases()
    return () => {
      cancelled = true
    }
  }, [])

  const filteredCases = cases.filter((item) => {
    const query = searchQuery.toLowerCase()
    return (
      item.case_id.toLowerCase().includes(query) ||
      item.patient_id.toLowerCase().includes(query) ||
      item.case_title.toLowerCase().includes(query)
    )
  })

  async function openResearch(item: CaseRow) {
    setBusyCaseId(item.case_id)
    setError('')
    try {
      if (item.research_status === 'in_progress' && item.latest_episode_id) {
        router.push(`/research?episode_id=${item.latest_episode_id}`)
        return
      }
      if (item.research_status === 'completed' && item.latest_completed_episode_id) {
        const repeated = await researchAPI.repeatEpisode(
          item.latest_completed_episode_id,
          makeUuid(),
          'participant_requested',
        )
        router.push(`/research?episode_id=${repeated.id}`)
        return
      }
      router.push(`/research?case_id=${item.case_id}`)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The research review could not start.',
      )
      setBusyCaseId('')
    }
  }

  async function repeatDiagnosis(item: CaseRow) {
    setBusyCaseId(item.case_id)
    setError('')
    try {
      const started = await inferenceAPI.startInference(Number(item.case_id), {
        forceRerun: item.diagnosis_status !== 'not_started',
      })
      sessionStorage.setItem('jobId', String(started.job_id))
      const repeatQuery = item.latest_completed_episode_id
        ? `&repeat_of_episode_id=${item.latest_completed_episode_id}`
        : ''
      router.push(
        `/inference?case_id=${item.case_id}&job_id=${started.job_id}${repeatQuery}`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diagnosis could not be restarted.')
      setBusyCaseId('')
    }
  }

  function continueDiagnosis(item: CaseRow) {
    if (!item.latest_job_id) {
      setError('The active analysis could not be reopened. Please refresh the Cases page.')
      return
    }
    sessionStorage.setItem('jobId', String(item.latest_job_id))
    router.push(`/inference?case_id=${item.case_id}&job_id=${item.latest_job_id}`)
  }

  return (
    <Box
      minHeight="100vh"
      sx={{
        bgcolor: '#f5f7fb',
        py: { xs: 3, md: 5 },
        px: { xs: 2, md: 0 },
      }}
    >
      <Container maxWidth="lg">
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'center' }}
          flexDirection={{ xs: 'column', md: 'row' }}
          gap={2}
          mb={3}
        >
          <Box>
            <Typography variant="h4" fontWeight={850} color="#17324d">
              Cases
            </Typography>
            <Typography color="text.secondary" mt={0.5}>
              Every diagnosis and expert review stays linked and traceable here.
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => router.push('/upload')}
            sx={{ minHeight: 48, borderRadius: 2.5, textTransform: 'none' }}
          >
            Diagnose a new case
          </Button>
        </Box>

        {recentCaseId && (
          <Alert severity="success" sx={{ mb: 2.5, borderRadius: 2.5 }}>
            Case {recentCaseId} is complete. The diagnosis and research response
            have both been saved.
          </Alert>
        )}
        {error && (
          <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2.5 }}>
            {error}
          </Alert>
        )}

        <TextField
          fullWidth
          size="small"
          placeholder="Search by case, patient, or title"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search />
              </InputAdornment>
            ),
          }}
          sx={{ maxWidth: 480, mb: 3, bgcolor: 'white' }}
        />

        {loading ? (
          <Box minHeight={260} display="flex" alignItems="center" justifyContent="center">
            <CircularProgress />
          </Box>
        ) : filteredCases.length === 0 ? (
          <Card sx={{ borderRadius: 4 }}>
            <CardContent sx={{ py: 7, textAlign: 'center' }}>
              <Typography variant="h6" fontWeight={750}>
                {searchQuery ? 'No matching cases' : 'No cases yet'}
              </Typography>
              {!searchQuery && (
                <Button
                  variant="contained"
                  onClick={() => router.push('/upload')}
                  sx={{ mt: 2, textTransform: 'none' }}
                >
                  Diagnose your first case
                </Button>
              )}
            </CardContent>
          </Card>
        ) : (
          <Box display="flex" flexDirection="column" gap={2}>
            {filteredCases.map((item, index) => {
              const isBusy = busyCaseId === item.case_id
              const reviewLabel =
                item.research_status === 'completed'
                  ? 'Research complete'
                  : item.research_status === 'in_progress'
                    ? 'Research in progress'
                    : 'Research not started'
              const reviewAction =
                item.research_status === 'completed'
                  ? 'Repeat research review'
                  : item.research_status === 'in_progress'
                    ? 'Continue research review'
                    : 'Start research review'
              const diagnosisAction =
                item.diagnosis_status === 'processing'
                  ? 'Continue analysis'
                  : item.diagnosis_status === 'failed'
                    ? 'Retry diagnosis'
                    : item.diagnosis_status === 'not_started'
                      ? 'Start diagnosis'
                      : reviewAction

              return (
                <motion.div
                  key={item.case_id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: index * 0.04 }}
                >
                  <Card
                    sx={{
                      borderRadius: 3.5,
                      border:
                        recentCaseId === item.case_id
                          ? '2px solid #22c55e'
                          : '1px solid #e2e8f0',
                      boxShadow: '0 12px 35px rgba(15, 23, 42, 0.06)',
                    }}
                  >
                    <CardContent sx={{ p: { xs: 2.5, md: 3.25 } }}>
                      <Box
                        display="flex"
                        justifyContent="space-between"
                        alignItems="flex-start"
                        gap={2}
                        flexWrap="wrap"
                      >
                        <Box>
                          <Typography variant="h6" fontWeight={800} color="#17324d">
                            {item.case_title}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" mt={0.35}>
                            Case {item.case_id} · {item.patient_id} ·{' '}
                            {new Date(item.created_at).toLocaleDateString()}
                          </Typography>
                        </Box>
                        <Box display="flex" gap={1} flexWrap="wrap">
                          <Chip
                            icon={
                              item.diagnosis_status === 'completed' ? (
                                <CheckCircle />
                              ) : undefined
                            }
                            label={
                              item.diagnosis_status === 'completed'
                                ? 'Diagnosis complete'
                                : item.diagnosis_status === 'processing'
                                  ? 'Diagnosis processing'
                                  : item.diagnosis_status === 'failed'
                                    ? 'Diagnosis failed'
                                    : 'Diagnosis not started'
                            }
                            color={
                              item.diagnosis_status === 'completed'
                                ? 'success'
                                : item.diagnosis_status === 'processing'
                                  ? 'warning'
                                  : item.diagnosis_status === 'failed'
                                    ? 'error'
                                    : 'default'
                            }
                            variant="outlined"
                            size="small"
                          />
                          <Chip
                            icon={<Science />}
                            label={reviewLabel}
                            color={
                              item.research_status === 'completed'
                                ? 'success'
                                : item.research_status === 'in_progress'
                                  ? 'warning'
                                  : 'default'
                            }
                            variant="outlined"
                            size="small"
                          />
                          {item.research_attempts > 1 && (
                            <Chip
                              label={`${item.research_attempts} preserved attempts`}
                              size="small"
                            />
                          )}
                        </Box>
                      </Box>

                      <Divider sx={{ my: 2.25 }} />

                      <Box display="flex" gap={1.25} flexWrap="wrap">
                        <Button
                          variant="contained"
                          endIcon={<ArrowForward />}
                          disabled={isBusy}
                          onClick={() => {
                            if (item.diagnosis_status === 'processing') {
                              continueDiagnosis(item)
                            } else if (
                              item.diagnosis_status === 'failed' ||
                              item.diagnosis_status === 'not_started'
                            ) {
                              void repeatDiagnosis(item)
                            } else {
                              void openResearch(item)
                            }
                          }}
                          sx={{ minHeight: 44, borderRadius: 2.25, textTransform: 'none' }}
                        >
                          {isBusy ? 'Opening…' : diagnosisAction}
                        </Button>
                        {item.research_status === 'completed' && (
                          <Button
                            variant="outlined"
                            startIcon={<Visibility />}
                            onClick={() =>
                              router.push(`/results?case_id=${item.case_id}`)
                            }
                            sx={{ minHeight: 44, borderRadius: 2.25, textTransform: 'none' }}
                          >
                            View diagnosis
                          </Button>
                        )}
                        {item.diagnosis_status === 'completed' && (
                          <Button
                            variant="text"
                            startIcon={<Refresh />}
                            disabled={isBusy || item.research_status === 'in_progress'}
                            onClick={() => void repeatDiagnosis(item)}
                            sx={{ minHeight: 44, textTransform: 'none' }}
                          >
                            Run diagnosis again
                          </Button>
                        )}
                      </Box>
                    </CardContent>
                  </Card>
                </motion.div>
              )
            })}
          </Box>
        )}
      </Container>
    </Box>
  )
}
