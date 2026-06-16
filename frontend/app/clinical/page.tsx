'use client'

import { useEffect, useMemo, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  MenuItem,
  Grid,
  Chip,
  Alert,
  Divider,
  Paper,
  CircularProgress,
} from '@mui/material'
import { Save, Assessment, Description } from '@mui/icons-material'
import { Stethoscope } from 'lucide-react'
import { motion } from 'framer-motion'
import {
  casesAPI,
  resultsAPI,
  clinicalAPI,
  CaseResponse,
  CaseResultsResponse,
  ClinicalList,
  ClinicalStats,
  ClinicalPayload,
} from '@/lib/api'
import { displayClass } from '@/lib/format'

const classOptions = [
  'Class I',
  'Class II div 1',
  'Class II div 2',
  'Class III',
  'Unclassifiable',
]

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function ClinicalPageContent() {
  const router = useRouter()
  const params = useSearchParams()
  const caseId = useMemo(() => {
    const raw =
      params.get('case_id') ||
      (typeof window !== 'undefined' ? sessionStorage.getItem('caseId') : null)
    const parsed = Number(raw)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
  }, [params])

  const [cases, setCases] = useState<CaseResponse[]>([])
  const [caseItem, setCaseItem] = useState<CaseResponse | null>(null)
  const [results, setResults] = useState<CaseResultsResponse | null>(null)
  const [clinicalList, setClinicalList] = useState<ClinicalList | null>(null)
  const [stats, setStats] = useState<ClinicalStats | null>(null)
  const [diagnosisComplete, setDiagnosisComplete] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  // Validation form fields
  const [site, setSite] = useState('DEMO')
  const [clinicalCaseId, setClinicalCaseId] = useState('')
  const [clinician, setClinician] = useState('Demo clinician')
  const [manualClass, setManualClass] = useState('Class I')
  const [dhc, setDhc] = useState('4')
  const [ac, setAc] = useState('6')
  const [manualTime, setManualTime] = useState('4')
  const [useful, setUseful] = useState('4')
  const [agree, setAgree] = useState<'Agree' | 'Partial' | 'Disagree'>('Agree')
  const [overrideValue, setOverrideValue] = useState<'No' | 'Yes'>('No')
  const [comment, setComment] = useState('')

  useEffect(() => {
    setClinicalCaseId(`VAL-${Date.now()}`)
  }, [])

  // Derived OrthoAI output
  const prediction: any = (results?.findings as any)?.prediction || {}
  const timings: any = (results?.findings as any)?.timings || {}
  // Map the model's raw class (numeric "0/1/2" from the real model, or readable
  // from the mock) to a readable malocclusion class before matching options.
  const aiClassRaw = displayClass(prediction.predicted_class)
  const aiClass = classOptions.includes(aiClassRaw) ? aiClassRaw : 'Unclassifiable'
  const aiConfidence: number | null =
    typeof prediction.confidence === 'number' ? prediction.confidence : null
  const aiSeconds: number | null =
    typeof timings.total_inference_seconds === 'number'
      ? timings.total_inference_seconds
      : null

  async function loadClinical(selectedCaseId: number) {
    const [loadedCase, loadedList, loadedStats] = await Promise.all([
      casesAPI.getCase(selectedCaseId),
      clinicalAPI.list(selectedCaseId),
      clinicalAPI.stats(selectedCaseId),
    ])
    setCaseItem(loadedCase)
    setClinicalList(loadedList)
    setStats(loadedStats)
    // Results may not exist if analysis is incomplete — tolerate failure.
    try {
      setResults(await resultsAPI.getResults(selectedCaseId))
    } catch {
      setResults(null)
    }
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (typeof window !== 'undefined' && !sessionStorage.getItem('authToken')) {
        router.replace('/signin')
        return
      }
      try {
        const loadedCases = await casesAPI.listCases()
        if (cancelled) return
        setCases(loadedCases)

        if (!caseId) return

        try {
          const health = await clinicalAPI.health(caseId)
          if (!cancelled) setDiagnosisComplete(health.diagnosis_complete)
        } catch {
          /* health is advisory; continue */
        }
        if (!cancelled) await loadClinical(caseId)
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : 'Unable to load clinical validation.',
          )
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [caseId, router])

  async function saveValidation() {
    if (!caseId) return
    setSaving(true)
    setError('')
    setSaved('')
    try {
      const payload: ClinicalPayload = {
        site: site.trim(),
        case_id: clinicalCaseId.trim(),
        assess_date: today(),
        clinician: clinician.trim() || null,
        rec_opg: true,
        rec_photo: true,
        rec_other: false,
        m_class: manualClass,
        dhc: Number(dhc),
        ac: ac ? Number(ac) : null,
        t_manual: manualTime ? Number(manualTime) : null,
        ai_class: aiClass,
        ai_dhc: null,
        ai_ac: null,
        ai_conf: aiConfidence == null ? null : Math.round(aiConfidence * 1000) / 10,
        t_ai: aiSeconds == null ? null : Math.round((aiSeconds / 60) * 100) / 100,
        calib: 'N/A',
        agree,
        override: overrideValue,
        override_reason:
          overrideValue === 'Yes'
            ? comment.trim() || 'Clinical override recorded.'
            : null,
        useful: useful ? Number(useful) : null,
        comment: comment.trim() || null,
      }
      await clinicalAPI.create(caseId, payload)
      setSaved('Clinical validation saved.')
      setClinicalCaseId(`VAL-${Date.now()}`)
      await loadClinical(caseId)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to save clinical validation.',
      )
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <Box className="min-h-screen flex items-center justify-center">
        <CircularProgress />
      </Box>
    )
  }

  // ---------- No case selected: show picker ----------
  if (!caseId) {
    return (
      <Box
        className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
        sx={{ py: { xs: 4, md: 6 }, px: { xs: 2, md: 0 } }}
      >
        <Container maxWidth="md">
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Box display="flex" alignItems="center" gap={2}>
                <Box
                  sx={{
                    bgcolor: 'rgba(99,102,241,0.1)',
                    color: '#6366f1',
                    p: 1.5,
                    borderRadius: 2,
                    display: 'flex',
                  }}
                >
                  <Stethoscope size={24} />
                </Box>
                <Box>
                  <Typography variant="h5" className="font-bold text-gray-900">
                    Clinical Validation
                  </Typography>
                  <Typography variant="body2" className="text-gray-600">
                    Select a completed case to record clinician validation.
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>

          <Box display="flex" flexDirection="column" gap={2}>
            {cases.length ? (
              cases.map((item) => (
                <Card
                  key={item.id}
                  className="glass-effect"
                  sx={{ cursor: 'pointer', '&:hover': { borderColor: '#6366f1' } }}
                  onClick={() => router.push(`/clinical?case_id=${item.id}`)}
                >
                  <CardContent
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 2,
                    }}
                  >
                    <Box>
                      <Typography className="font-bold text-gray-800">
                        {item.title || `Case #${item.id}`}
                      </Typography>
                      <Typography variant="body2" className="text-gray-500">
                        #{item.id} · {item.patient_id || '—'}
                      </Typography>
                    </Box>
                    <Chip
                      label={item.status || 'unknown'}
                      size="small"
                      color={item.status === 'done' ? 'success' : 'default'}
                      sx={{ textTransform: 'capitalize' }}
                    />
                  </CardContent>
                </Card>
              ))
            ) : (
              <Typography className="text-gray-500">No cases found.</Typography>
            )}
          </Box>
        </Container>
      </Box>
    )
  }

  // ---------- Case selected: validation workspace ----------
  const selectSx = { '& .MuiOutlinedInput-root': { borderRadius: 2 } }

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
      sx={{ py: { xs: 4, md: 6 }, px: { xs: 2, md: 0 } }}
    >
      <Container maxWidth="lg">
        <Grid container spacing={3}>
          {/* Left: validation form */}
          <Grid item xs={12} md={7}>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
            >
              <Card className="glass-effect">
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                  <Box
                    display="flex"
                    justifyContent="space-between"
                    alignItems="flex-start"
                    flexWrap="wrap"
                    gap={2}
                    mb={2}
                  >
                    <Box display="flex" alignItems="center" gap={2}>
                      <Box
                        sx={{
                          bgcolor: 'rgba(99,102,241,0.1)',
                          color: '#6366f1',
                          p: 1.5,
                          borderRadius: 2,
                          display: 'flex',
                        }}
                      >
                        <Stethoscope size={24} />
                      </Box>
                      <Box>
                        <Typography variant="h5" className="font-bold text-gray-900">
                          Clinical Validation
                        </Typography>
                        <Typography variant="body2" className="text-gray-600">
                          {caseItem
                            ? `${caseItem.title || `Case #${caseId}`} · ${caseItem.patient_id || '—'}`
                            : `Case #${caseId}`}
                        </Typography>
                      </Box>
                    </Box>
                    <Button
                      variant="outlined"
                      startIcon={<Description />}
                      onClick={() => router.push(`/results?case_id=${caseId}`)}
                      sx={{
                        borderColor: '#6366f1',
                        color: '#6366f1',
                        textTransform: 'none',
                        borderRadius: 2,
                      }}
                    >
                      Results
                    </Button>
                  </Box>

                  {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      {error}
                    </Alert>
                  )}
                  {saved && (
                    <Alert severity="success" sx={{ mb: 2 }}>
                      {saved}
                    </Alert>
                  )}
                  {!diagnosisComplete && (
                    <Alert severity="warning" sx={{ mb: 2 }}>
                      This case has no completed analysis yet. Run the analysis before
                      saving a validation.
                    </Alert>
                  )}

                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Site"
                        value={site}
                        onChange={(e) => setSite(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Validation case ID"
                        value={clinicalCaseId}
                        onChange={(e) => setClinicalCaseId(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Clinician"
                        value={clinician}
                        onChange={(e) => setClinician(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        label="Manual class"
                        value={manualClass}
                        onChange={(e) => setManualClass(e.target.value)}
                        sx={selectSx}
                      >
                        {classOptions.map((option) => (
                          <MenuItem key={option} value={option}>
                            {option}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <TextField
                        fullWidth
                        type="number"
                        label="DHC"
                        inputProps={{ min: 1, max: 5 }}
                        value={dhc}
                        onChange={(e) => setDhc(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <TextField
                        fullWidth
                        type="number"
                        label="AC"
                        inputProps={{ min: 1, max: 10 }}
                        value={ac}
                        onChange={(e) => setAc(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <TextField
                        fullWidth
                        type="number"
                        label="Manual time (min)"
                        inputProps={{ min: 0, step: 0.1 }}
                        value={manualTime}
                        onChange={(e) => setManualTime(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <TextField
                        fullWidth
                        type="number"
                        label="Useful (1-5)"
                        inputProps={{ min: 1, max: 5 }}
                        value={useful}
                        onChange={(e) => setUseful(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        label="Agreement"
                        value={agree}
                        onChange={(e) =>
                          setAgree(e.target.value as 'Agree' | 'Partial' | 'Disagree')
                        }
                        sx={selectSx}
                      >
                        {['Agree', 'Partial', 'Disagree'].map((o) => (
                          <MenuItem key={o} value={o}>
                            {o}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        label="Override"
                        value={overrideValue}
                        onChange={(e) =>
                          setOverrideValue(e.target.value as 'No' | 'Yes')
                        }
                        sx={selectSx}
                      >
                        {['No', 'Yes'].map((o) => (
                          <MenuItem key={o} value={o}>
                            {o}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        multiline
                        minRows={3}
                        label="Clinical comment"
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        sx={selectSx}
                      />
                    </Grid>
                  </Grid>

                  <Box display="flex" justifyContent="flex-end" mt={3}>
                    <Button
                      variant="contained"
                      className="gradient-purple"
                      startIcon={<Save />}
                      onClick={saveValidation}
                      disabled={saving || !site.trim() || !clinicalCaseId.trim()}
                      sx={{
                        color: 'white',
                        px: 4,
                        py: 1.5,
                        borderRadius: 2,
                        textTransform: 'none',
                      }}
                    >
                      {saving ? 'Saving...' : 'Save Validation'}
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </motion.div>
          </Grid>

          {/* Right: AI output + stats + recent */}
          <Grid item xs={12} md={5}>
            <Box display="flex" flexDirection="column" gap={3}>
              <Card className="glass-effect">
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" className="font-semibold text-gray-800 mb-2">
                    OrthoAI Output
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  {[
                    ['AI class', aiClass],
                    [
                      'Confidence',
                      aiConfidence == null
                        ? '—'
                        : `${Math.round(aiConfidence * 1000) / 10}%`,
                    ],
                    ['AI time', aiSeconds == null ? '—' : `${aiSeconds.toFixed(2)}s`],
                    ['Model', results?.model_version || '—'],
                  ].map(([k, v]) => (
                    <Box
                      key={k}
                      display="flex"
                      justifyContent="space-between"
                      alignItems="center"
                      py={0.75}
                    >
                      <Typography variant="body2" className="text-gray-500">
                        {k}
                      </Typography>
                      <Typography variant="body2" className="font-semibold text-gray-800">
                        {v}
                      </Typography>
                    </Box>
                  ))}
                </CardContent>
              </Card>

              <Card className="glass-effect">
                <CardContent sx={{ p: 3 }}>
                  <Box display="flex" alignItems="center" gap={1.5} mb={1.5}>
                    <Assessment sx={{ color: '#6366f1' }} />
                    <Typography variant="h6" className="font-semibold text-gray-800">
                      Validation Stats
                    </Typography>
                  </Box>
                  <Divider sx={{ mb: 2 }} />
                  {[
                    ['Records', stats?.n ?? 0],
                    ['High need', stats?.high_need ?? 0],
                    [
                      'Class agreement',
                      stats?.class_agreement_pct == null
                        ? '—'
                        : `${stats.class_agreement_pct}%`,
                    ],
                  ].map(([k, v]) => (
                    <Box
                      key={k}
                      display="flex"
                      justifyContent="space-between"
                      alignItems="center"
                      py={0.75}
                    >
                      <Typography variant="body2" className="text-gray-500">
                        {k}
                      </Typography>
                      <Typography variant="body2" className="font-semibold text-gray-800">
                        {v}
                      </Typography>
                    </Box>
                  ))}
                </CardContent>
              </Card>

              <Card className="glass-effect">
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" className="font-semibold text-gray-800 mb-2">
                    Recent Records
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <Box display="flex" flexDirection="column" gap={1.5}>
                    {clinicalList?.items.length ? (
                      clinicalList.items.map((item) => (
                        <Paper
                          key={item.id}
                          elevation={0}
                          sx={{ p: 1.5, bgcolor: '#f9fafb', borderRadius: 2 }}
                        >
                          <Box
                            display="flex"
                            justifyContent="space-between"
                            alignItems="center"
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
                            {item.site} · DHC {item.dhc} ·{' '}
                            {new Date(item.created_at).toLocaleDateString()}
                          </Typography>
                        </Paper>
                      ))
                    ) : (
                      <Typography variant="body2" className="text-gray-500">
                        No validation records for this case yet.
                      </Typography>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Box>
          </Grid>
        </Grid>
      </Container>
    </Box>
  )
}

export default function ClinicalPage() {
  return (
    <Suspense
      fallback={
        <Box className="min-h-screen flex items-center justify-center">
          <CircularProgress />
        </Box>
      }
    >
      <ClinicalPageContent />
    </Suspense>
  )
}
