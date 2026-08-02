'use client'

import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import Divider from '@mui/material/Divider'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormLabel from '@mui/material/FormLabel'
import Grid from '@mui/material/Grid'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Slider from '@mui/material/Slider'
import Step from '@mui/material/Step'
import StepLabel from '@mui/material/StepLabel'
import Stepper from '@mui/material/Stepper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import CheckCircle from '@mui/icons-material/CheckCircle'
import Download from '@mui/icons-material/Download'
import Lock from '@mui/icons-material/Lock'
import PersonAdd from '@mui/icons-material/PersonAdd'
import PlayArrow from '@mui/icons-material/PlayArrow'
import Science from '@mui/icons-material/Science'
import Timer from '@mui/icons-material/Timer'
import Visibility from '@mui/icons-material/Visibility'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  CaseResponse,
  ReferenceAssessment,
  ReferenceCase,
  ReferenceQueueItem,
  ResearchContext,
  ResearchEpisode,
  ResearchEventSubmission,
  ResearchEligibleUser,
  ResearchParticipant,
  ResearchRole,
  StudyInstrument,
  casesAPI,
  researchAPI,
} from '@/lib/api'
import ClinicianStudyWorkspace from '@/components/research/ClinicianStudyWorkspace'
import { displayClass } from '@/lib/format'

const STUDY_CODE = 'ORTHOAI-HCI-V3'
const TASK_SCHEMA_VERSION = 'orthoai.malocclusion-decision/1.0.0'
const EVENT_SCHEMA_VERSION = 'research-event/1.0.0'
const IDLE_AFTER_MS = 30_000

const classOptions = [
  'Class I',
  'Class II div 1',
  'Class II div 2',
  'Class III',
  'Unclassifiable',
]

function makeUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isoNow(): string {
  return new Date().toISOString()
}

function stateStep(episode: ResearchEpisode | null): number {
  if (!episode) return 0
  if (episode.state === 'pre_ai') return 0
  if (episode.state === 'pre_ai_locked') return 1
  if (episode.state === 'ai_revealed') return 2
  return 3
}

function DynamicSurvey({
  instrument,
  episode,
  onSaved,
}: {
  instrument: StudyInstrument
  episode: ResearchEpisode
  onSaved: (message: string) => void
}) {
  const [values, setValues] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const startedAt = useRef(isoNow())
  const questions = instrument.definition.questions || []

  async function submit() {
    const missing = questions.filter(
      (question) =>
        question.required &&
        (values[question.id] === undefined || values[question.id] === ''),
    )
    if (missing.length) {
      setError(`Complete: ${missing.map((item) => item.label).join(', ')}`)
      return
    }
    setSaving(true)
    setError('')
    try {
      await researchAPI.submitSurvey({
        study_code: episode.study_code,
        instrument_code: instrument.code,
        instrument_version: instrument.version,
        episode_id: episode.id,
        period_code: `episode-${episode.id}-post`,
        responses: values,
        completion_status: 'completed',
        client_started_at: startedAt.current,
        client_submitted_at: isoNow(),
      })
      onSaved(`${instrument.name} saved as an immutable study response.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Survey could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card variant="outlined" sx={{ borderRadius: 3 }}>
      <CardContent sx={{ p: 3 }}>
        <Typography variant="h6" fontWeight={700}>
          {instrument.name}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {instrument.construct} · version {instrument.version}
        </Typography>
        {instrument.definition.instructions && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            {instrument.definition.instructions}
          </Typography>
        )}
        <Box display="flex" flexDirection="column" gap={2.5} mt={2.5}>
          {questions.map((question) => {
            if (question.type === 'likert' || question.type === 'number') {
              const min = question.min ?? 1
              const max = question.max ?? 5
              return (
                <Box key={question.id}>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    {question.label}
                    {question.required ? ' *' : ''}
                  </Typography>
                  <Slider
                    value={values[question.id] ?? min}
                    min={min}
                    max={max}
                    step={1}
                    marks
                    valueLabelDisplay="on"
                    onChange={(_, value) =>
                      setValues((current) => ({
                        ...current,
                        [question.id]: value,
                      }))
                    }
                  />
                </Box>
              )
            }
            if (question.type === 'select') {
              return (
                <TextField
                  key={question.id}
                  select
                  fullWidth
                  label={question.label}
                  required={question.required}
                  value={values[question.id] ?? ''}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [question.id]: event.target.value,
                    }))
                  }
                >
                  {(question.options || []).map((option) => (
                    <MenuItem key={option} value={option}>
                      {option}
                    </MenuItem>
                  ))}
                </TextField>
              )
            }
            return (
              <TextField
                key={question.id}
                fullWidth
                multiline
                minRows={2}
                label={question.label}
                required={question.required}
                value={values[question.id] ?? ''}
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    [question.id]: event.target.value,
                  }))
                }
              />
            )
          })}
        </Box>
        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
        <Box display="flex" justifyContent="flex-end" mt={2.5}>
          <Button variant="contained" onClick={submit} disabled={saving}>
            {saving ? 'Saving…' : 'Submit instrument'}
          </Button>
        </Box>
      </CardContent>
    </Card>
  )
}

function ResearchAdminWorkspace({ context }: { context: ResearchContext }) {
  const [participants, setParticipants] = useState<ResearchParticipant[]>([])
  const [users, setUsers] = useState<ResearchEligibleUser[]>([])
  const [userId, setUserId] = useState('')
  const [participantCode, setParticipantCode] = useState('')
  const [role, setRole] = useState<ResearchRole>('clinician')
  const [siteCode, setSiteCode] = useState('DEMO')
  const [specialty, setSpecialty] = useState('')
  const [experienceBand, setExperienceBand] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const reload = useCallback(async () => {
    const [participantRows, userRows] = await Promise.all([
      researchAPI.participants(STUDY_CODE),
      researchAPI.eligibleUsers(STUDY_CODE),
    ])
    setParticipants(participantRows)
    setUsers(userRows)
  }, [])

  useEffect(() => {
    void reload().catch((err) =>
      setError(
        err instanceof Error ? err.message : 'Study governance data could not load.',
      ),
    )
  }, [reload])

  async function assignParticipant() {
    if (!userId || !participantCode.trim()) {
      setError('Select a user and provide a participant code.')
      return
    }
    if (!context.consent_version) {
      setError('The study has no active consent version.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await researchAPI.createParticipant({
        study_code: STUDY_CODE,
        site_code: siteCode,
        user_id: Number(userId),
        participant_code: participantCode.trim(),
        role,
        specialty: specialty.trim() || null,
        experience_band: experienceBand.trim() || null,
        consent_version: context.consent_version,
        consented_at: isoNow(),
      })
      await reload()
      setUserId('')
      setParticipantCode('')
      setSpecialty('')
      setExperienceBand('')
      setNotice('Governed participant identity and study role assigned.')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Participant could not be assigned.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function downloadExport() {
    setBusy(true)
    setError('')
    try {
      const payload = await researchAPI.exportStudy(STUDY_CODE)
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 2)], {
          type: 'application/json',
        }),
      )
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${STUDY_CODE}-research-export.json`
      anchor.click()
      URL.revokeObjectURL(url)
      setNotice('De-identified linked research export generated.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export could not be generated.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box minHeight="100vh" sx={{ bgcolor: '#f4f7fb', py: { xs: 3, md: 5 } }}>
      <Container maxWidth="lg">
        <Box
          display="flex"
          justifyContent="space-between"
          gap={2}
          alignItems="flex-start"
          flexWrap="wrap"
          mb={3}
        >
          <Box>
            <Box display="flex" alignItems="center" gap={1.5}>
              <Science sx={{ color: '#0f766e', fontSize: 34 }} />
              <Typography variant="h4" fontWeight={800} color="#17324d">
                Research governance
              </Typography>
            </Box>
            <Typography color="text.secondary" mt={0.75}>
              Manage protocol-bound identities, roles, epochs, and research export.
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={downloadExport}
            disabled={busy}
          >
            Export linked dataset
          </Button>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}

        <Grid container spacing={2.5} mb={3}>
          {[
            ['Study status', context.study_status || 'not configured'],
            ['Protocol', context.protocol_version || '—'],
            ['Consent', context.consent_version || '—'],
            ['Active epoch', context.active_epoch_code || '—'],
          ].map(([label, value]) => (
            <Grid item xs={6} md={3} key={label}>
              <Card sx={{ borderRadius: 3, height: '100%' }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography fontWeight={700}>{value}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Alert severity="warning" sx={{ mb: 3 }}>
          Role separation is enforced: administrators cannot submit clinician,
          reviewer, or adjudicator decisions. Assign those responsibilities to
          separate authenticated users only after documented consent.
        </Alert>

        <Grid container spacing={3}>
          <Grid item xs={12} md={5}>
            <Card sx={{ borderRadius: 4 }}>
              <CardContent sx={{ p: 3 }}>
                <Box display="flex" alignItems="center" gap={1} mb={2.5}>
                  <PersonAdd color="primary" />
                  <Typography variant="h6" fontWeight={700}>
                    Assign study participant
                  </Typography>
                </Box>
                <Box display="flex" flexDirection="column" gap={2}>
                  <TextField
                    select
                    required
                    label="Authenticated user"
                    value={userId}
                    onChange={(event) => setUserId(event.target.value)}
                  >
                    {users
                      .filter((user) => !user.is_enrolled)
                      .map((user) => (
                        <MenuItem key={user.id} value={user.id}>
                          {user.full_name || user.email} · user {user.id}
                        </MenuItem>
                      ))}
                  </TextField>
                  <TextField
                    required
                    label="De-identified participant code"
                    value={participantCode}
                    onChange={(event) => setParticipantCode(event.target.value)}
                  />
                  <TextField
                    select
                    required
                    label="Study role"
                    value={role}
                    onChange={(event) =>
                      setRole(event.target.value as ResearchRole)
                    }
                  >
                    <MenuItem value="clinician">Clinician</MenuItem>
                    <MenuItem value="reviewer">Independent reviewer</MenuItem>
                    <MenuItem value="adjudicator">Adjudicator</MenuItem>
                    <MenuItem value="research_admin">Research administrator</MenuItem>
                  </TextField>
                  <TextField
                    label="Site code"
                    value={siteCode}
                    onChange={(event) => setSiteCode(event.target.value)}
                  />
                  <TextField
                    label="Specialty"
                    value={specialty}
                    onChange={(event) => setSpecialty(event.target.value)}
                  />
                  <TextField
                    label="Experience band"
                    value={experienceBand}
                    onChange={(event) => setExperienceBand(event.target.value)}
                  />
                  <Button
                    variant="contained"
                    startIcon={<PersonAdd />}
                    onClick={assignParticipant}
                    disabled={busy || !userId || !participantCode.trim()}
                  >
                    Confirm consent and assign
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={7}>
            <Card sx={{ borderRadius: 4 }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" fontWeight={700}>
                  Governed participant registry
                </Typography>
                <Box display="flex" flexDirection="column" gap={1.5} mt={2.5}>
                  {participants.map((participant) => (
                    <Paper
                      key={participant.id}
                      variant="outlined"
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: 2,
                        alignItems: 'center',
                      }}
                    >
                      <Box>
                        <Typography fontWeight={700}>
                          {participant.participant_code}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {participant.site_code} · consent{' '}
                          {participant.consent_version}
                        </Typography>
                      </Box>
                      <Chip
                        label={participant.role.replaceAll('_', ' ')}
                        color={participant.is_active ? 'primary' : 'default'}
                        variant="outlined"
                      />
                    </Paper>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Container>
    </Box>
  )
}

function ReferenceWorkspace({ context }: { context: ResearchContext }) {
  const role = context.participant?.role
  const isAdjudicator = role === 'adjudicator'
  const [queue, setQueue] = useState<ReferenceQueueItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [referenceCase, setReferenceCase] = useState<ReferenceCase | null>(null)
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({})
  const [assessments, setAssessments] = useState<ReferenceAssessment[]>([])
  const [diagnosisClass, setDiagnosisClass] = useState('')
  const [dhc, setDhc] = useState('')
  const [ac, setAc] = useState('')
  const [confidence, setConfidence] = useState(50)
  const [uncertainty, setUncertainty] = useState('')
  const [rationale, setRationale] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const selectedQueueItem = queue.find(
    (item) => item.episode_id === Number(selectedId),
  )

  const loadQueue = useCallback(async () => {
    const rows = await researchAPI.referenceQueue(STUDY_CODE)
    setQueue(rows)
    return rows
  }, [])

  useEffect(() => {
    void loadQueue().catch((err) =>
      setError(
        err instanceof Error ? err.message : 'Reference queue could not load.',
      ),
    )
  }, [loadQueue])

  useEffect(
    () => () => {
      Object.values(imageUrls).forEach((url) => URL.revokeObjectURL(url))
    },
    [imageUrls],
  )

  async function openCase() {
    if (!selectedId) return
    setBusy(true)
    setError('')
    setNotice('')
    Object.values(imageUrls).forEach((url) => URL.revokeObjectURL(url))
    setImageUrls({})
    setAssessments([])
    try {
      const loadedCase = await researchAPI.referenceCase(Number(selectedId))
      setReferenceCase(loadedCase)
      const entries = await Promise.all(
        loadedCase.images.map(async (image) => {
          const blob = await researchAPI.referenceImage(
            loadedCase.episode_id,
            image.id,
          )
          return [image.id, URL.createObjectURL(blob)] as const
        }),
      )
      setImageUrls(Object.fromEntries(entries))
      if (isAdjudicator) {
        setAssessments(
          await researchAPI.referenceAssessments(loadedCase.episode_id),
        )
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Reference case could not load.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function submitReference() {
    if (!referenceCase || !diagnosisClass || !dhc) {
      setError('Malocclusion class and DHC are required.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await researchAPI.submitReferenceAssessment(referenceCase.episode_id, {
        task_schema_version: TASK_SCHEMA_VERSION,
        decision: {
          malocclusion_class: diagnosisClass,
          dhc: Number(dhc),
          ac: ac ? Number(ac) : null,
        },
        confidence,
        review_round: 1,
        blinded_to_clinician: true,
      })
      await loadQueue()
      setReferenceCase(null)
      setSelectedId('')
      setNotice(
        'Independent reference assessment locked. No clinician or AI answer was exposed.',
      )
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Reference assessment could not be saved.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function submitAdjudication() {
    if (!referenceCase || !diagnosisClass || !dhc) {
      setError('Consensus malocclusion class and DHC are required.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await researchAPI.submitAdjudication(referenceCase.episode_id, {
        reference_standard_version: 'orthoai-reference-standard/1.0.0',
        task_schema_version: TASK_SCHEMA_VERSION,
        consensus_decision: {
          malocclusion_class: diagnosisClass,
          dhc: Number(dhc),
          ac: ac ? Number(ac) : null,
        },
        uncertainty: uncertainty || null,
        rationale: rationale || null,
      })
      await loadQueue()
      setReferenceCase(null)
      setSelectedId('')
      setNotice('Adjudicated reference standard locked for this episode.')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Adjudication could not be saved.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box minHeight="100vh" sx={{ bgcolor: '#f4f7fb', py: { xs: 3, md: 5 } }}>
      <Container maxWidth="lg">
        <Box display="flex" justifyContent="space-between" gap={2} mb={3}>
          <Box>
            <Box display="flex" alignItems="center" gap={1.5}>
              <Science sx={{ color: '#0f766e', fontSize: 34 }} />
              <Typography variant="h4" fontWeight={800} color="#17324d">
                {isAdjudicator ? 'Adjudication workspace' : 'Blinded reference review'}
              </Typography>
            </Box>
            <Typography color="text.secondary" mt={0.75}>
              {isAdjudicator
                ? 'Resolve independent reviews into a reference standard.'
                : 'Assess source images without clinician decisions or AI output.'}
            </Typography>
          </Box>
          <Chip
            label={context.participant?.participant_code}
            color="primary"
          />
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
        <Alert severity="info" sx={{ mb: 3 }}>
          The reviewer interface never receives the treating clinician’s pre-AI or
          final answer and never receives the AI snapshot. Cases use research codes
          rather than patient identifiers.
        </Alert>

        <Card sx={{ borderRadius: 4, mb: 3 }}>
          <CardContent sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight={700} gutterBottom>
              Eligible reference cases
            </Typography>
            <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
              <TextField
                select
                label="Research case"
                value={selectedId}
                onChange={(event) => setSelectedId(event.target.value)}
                sx={{ minWidth: 320, flex: 1 }}
              >
                {queue.map((item) => (
                  <MenuItem
                    key={item.episode_id}
                    value={item.episode_id}
                    disabled={
                      (!isAdjudicator &&
                        (item.submitted_review_rounds.includes(1) ||
                          item.state === 'adjudicated')) ||
                      (isAdjudicator && !item.adjudication_ready)
                    }
                  >
                    {item.case_code} · {item.site_code} · {item.image_count} image
                    {item.image_count === 1 ? '' : 's'} ·{' '}
                    {item.total_reference_reviews}/{item.required_reference_reviews}{' '}
                    reviews
                  </MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                onClick={openCase}
                disabled={!selectedId || busy}
              >
                Open blinded case
              </Button>
            </Box>
            {selectedQueueItem && isAdjudicator && (
              <Typography variant="caption" color="text.secondary">
                Adjudication readiness:{' '}
                {selectedQueueItem.adjudication_ready ? 'ready' : 'not ready'}
              </Typography>
            )}
          </CardContent>
        </Card>

        {busy && !referenceCase && (
          <Box display="flex" justifyContent="center" py={5}>
            <CircularProgress />
          </Box>
        )}

        {referenceCase && (
          <Grid container spacing={3}>
            <Grid item xs={12} md={7}>
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" fontWeight={700}>
                    {referenceCase.case_code} source images
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {referenceCase.site_code} · {referenceCase.epoch_code}
                  </Typography>
                  <Grid container spacing={2} mt={0.5}>
                    {referenceCase.images.map((image) => (
                      <Grid item xs={12} sm={6} key={image.id}>
                        <Paper
                          variant="outlined"
                          sx={{ p: 1.25, borderRadius: 2, overflow: 'hidden' }}
                        >
                          {imageUrls[image.id] ? (
                            <Box
                              component="img"
                              src={imageUrls[image.id]}
                              alt={`Source image ${image.id}`}
                              sx={{
                                width: '100%',
                                height: 260,
                                objectFit: 'contain',
                                bgcolor: '#0f172a',
                                borderRadius: 1,
                              }}
                            />
                          ) : (
                            <Box
                              height={260}
                              display="flex"
                              alignItems="center"
                              justifyContent="center"
                            >
                              <CircularProgress size={28} />
                            </Box>
                          )}
                          <Typography variant="caption">{image.filename}</Typography>
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={5}>
              {isAdjudicator && (
                <Card variant="outlined" sx={{ borderRadius: 3, mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6" fontWeight={700}>
                      Independent assessments
                    </Typography>
                    {assessments.map((assessment) => (
                      <Paper
                        key={assessment.id}
                        variant="outlined"
                        sx={{ p: 1.5, mt: 1.5, borderRadius: 2 }}
                      >
                        <Typography variant="body2" fontWeight={700}>
                          {assessment.reviewer_participant_code}
                        </Typography>
                        <Typography variant="body2">
                          {String(assessment.decision?.malocclusion_class || '—')} ·
                          DHC {String(assessment.decision?.dhc || '—')} · confidence{' '}
                          {assessment.confidence ?? '—'}%
                        </Typography>
                      </Paper>
                    ))}
                  </CardContent>
                </Card>
              )}
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" fontWeight={700}>
                    {isAdjudicator
                      ? 'Consensus reference decision'
                      : 'Independent reference decision'}
                  </Typography>
                  <Box display="flex" flexDirection="column" gap={2.25} mt={2.5}>
                    <TextField
                      select
                      required
                      label="Malocclusion class"
                      value={diagnosisClass}
                      onChange={(event) => setDiagnosisClass(event.target.value)}
                    >
                      {classOptions.map((option) => (
                        <MenuItem key={option} value={option}>{option}</MenuItem>
                      ))}
                    </TextField>
                    <Box display="flex" gap={2}>
                      <TextField
                        required
                        type="number"
                        label="IOTN DHC"
                        inputProps={{ min: 1, max: 5 }}
                        value={dhc}
                        onChange={(event) => setDhc(event.target.value)}
                        sx={{ flex: 1 }}
                      />
                      <TextField
                        type="number"
                        label="IOTN AC"
                        inputProps={{ min: 1, max: 10 }}
                        value={ac}
                        onChange={(event) => setAc(event.target.value)}
                        sx={{ flex: 1 }}
                      />
                    </Box>
                    {!isAdjudicator && (
                      <Box>
                        <Typography variant="body2" fontWeight={600}>
                          Confidence: {confidence}%
                        </Typography>
                        <Slider
                          value={confidence}
                          min={0}
                          max={100}
                          onChange={(_, value) => setConfidence(value as number)}
                        />
                      </Box>
                    )}
                    {isAdjudicator && (
                      <>
                        <TextField
                          select
                          label="Residual uncertainty"
                          value={uncertainty}
                          onChange={(event) => setUncertainty(event.target.value)}
                        >
                          <MenuItem value="">Not recorded</MenuItem>
                          <MenuItem value="low">Low</MenuItem>
                          <MenuItem value="moderate">Moderate</MenuItem>
                          <MenuItem value="high">High</MenuItem>
                        </TextField>
                        <TextField
                          multiline
                          minRows={3}
                          label="Consensus rationale"
                          value={rationale}
                          onChange={(event) => setRationale(event.target.value)}
                        />
                      </>
                    )}
                    <Button
                      variant="contained"
                      startIcon={<Lock />}
                      disabled={busy || !diagnosisClass || !dhc}
                      onClick={
                        isAdjudicator ? submitAdjudication : submitReference
                      }
                    >
                      {isAdjudicator
                        ? 'Lock adjudicated standard'
                        : 'Lock independent review'}
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
      </Container>
    </Box>
  )
}

function LegacyResearchModePage() {
  const router = useRouter()
  const [context, setContext] = useState<ResearchContext | null>(null)
  const [cases, setCases] = useState<CaseResponse[]>([])
  const [episode, setEpisode] = useState<ResearchEpisode | null>(null)
  const [sourceCase, setSourceCase] = useState<ReferenceCase | null>(null)
  const [sourceImageUrls, setSourceImageUrls] = useState<Record<number, string>>(
    {},
  )
  const [instruments, setInstruments] = useState<StudyInstrument[]>([])
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [preClass, setPreClass] = useState('')
  const [preDhc, setPreDhc] = useState('')
  const [preAc, setPreAc] = useState('')
  const [preAction, setPreAction] = useState('')
  const [preNotes, setPreNotes] = useState('')
  const [preConfidence, setPreConfidence] = useState<number>(50)

  const [finalClass, setFinalClass] = useState('')
  const [finalDhc, setFinalDhc] = useState('')
  const [finalAc, setFinalAc] = useState('')
  const [finalAction, setFinalAction] = useState('')
  const [finalNotes, setFinalNotes] = useState('')
  const [finalConfidence, setFinalConfidence] = useState<number>(50)
  const [agreement, setAgreement] = useState<'agree' | 'partial' | 'disagree'>(
    'agree',
  )
  const [overrideValue, setOverrideValue] = useState<'yes' | 'no'>('no')
  const [overrideReason, setOverrideReason] = useState('')
  const [usefulness, setUsefulness] = useState<number>(3)

  const [activeSeconds, setActiveSeconds] = useState(0)
  const activeSecondsRef = useRef(0)
  const phaseStartedAt = useRef(isoNow())
  const lastActivityAt = useRef(Date.now())
  const idleRef = useRef(false)
  const eventSequence = useRef(0)
  const eventQueue = useRef<Promise<void>>(Promise.resolve())
  const revealedViewEpisode = useRef<number | null>(null)

  const collectingTime =
    episode?.state === 'pre_ai' || episode?.state === 'ai_revealed'
  const participantRole = context?.participant?.role
  const activeEpisodeId = episode?.id

  const updateEpisode = useCallback((next: ResearchEpisode) => {
    eventSequence.current = next.last_event_sequence
    setEpisode(next)
  }, [])

  const emitEvent = useCallback(
    (
      eventType: string,
      payload: Record<string, any> | null = null,
    ): Promise<void> => {
      if (!episode) return Promise.resolve()
      eventQueue.current = eventQueue.current
        .catch(() => undefined)
        .then(async () => {
          const sequence = eventSequence.current + 1
          const eventUuid = makeUuid()
          const body: ResearchEventSubmission = {
            event_uuid: eventUuid,
            idempotency_key: `${eventType}:${eventUuid}`,
            sequence_no: sequence,
            event_type: eventType,
            schema_version: EVENT_SCHEMA_VERSION,
            client_timestamp: isoNow(),
            client_timezone_offset_minutes: new Date().getTimezoneOffset(),
            payload,
          }
          const saved = await researchAPI.appendEvent(episode.id, body)
          eventSequence.current = saved.sequence_no
        })
      return eventQueue.current
    },
    [episode],
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (typeof window !== 'undefined' && !sessionStorage.getItem('authToken')) {
        router.replace('/signin')
        return
      }
      try {
        const loadedContext = await researchAPI.context(STUDY_CODE)
        if (cancelled) return
        setContext(loadedContext)
        if (loadedContext.participant?.role === 'clinician') {
          const [loadedCases, episodeList, loadedInstruments] = await Promise.all([
            casesAPI.listCases(),
            researchAPI.listEpisodes(STUDY_CODE),
            researchAPI.instruments(STUDY_CODE),
          ])
          if (cancelled) return
          setCases(loadedCases.filter((item) => item.status === 'done'))
          setInstruments(loadedInstruments)
          if (episodeList.items[0]) updateEpisode(episodeList.items[0])
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : 'Research Mode could not load.',
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [router, updateEpisode])

  useEffect(() => {
    if (!episode) return
    eventSequence.current = episode.last_event_sequence
  }, [episode])

  useEffect(() => {
    if (!activeEpisodeId || participantRole !== 'clinician') {
      setSourceCase(null)
      setSourceImageUrls({})
      return
    }
    let disposed = false
    let createdUrls: string[] = []
    setSourceCase(null)
    setSourceImageUrls({})
    async function loadSourceImages() {
      try {
        const loadedCase = await researchAPI.sourceCase(activeEpisodeId!)
        const entries = await Promise.all(
          loadedCase.images.map(async (image) => {
            const blob = await researchAPI.sourceImage(loadedCase.episode_id, image.id)
            const url = URL.createObjectURL(blob)
            createdUrls.push(url)
            return [image.id, url] as const
          }),
        )
        if (disposed) {
          createdUrls.forEach((url) => URL.revokeObjectURL(url))
          createdUrls = []
          return
        }
        setSourceCase(loadedCase)
        setSourceImageUrls(Object.fromEntries(entries))
      } catch (err) {
        if (!disposed) {
          setError(
            err instanceof Error
              ? err.message
              : 'Source images could not be loaded.',
          )
        }
      }
    }
    void loadSourceImages()
    return () => {
      disposed = true
      createdUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [activeEpisodeId, participantRole])

  useEffect(() => {
    activeSecondsRef.current = 0
    setActiveSeconds(0)
    phaseStartedAt.current = isoNow()
    lastActivityAt.current = Date.now()
    idleRef.current = false
  }, [episode?.id, episode?.state])

  useEffect(() => {
    if (!collectingTime) return
    const tick = window.setInterval(() => {
      const active =
        !idleRef.current &&
        document.visibilityState === 'visible' &&
        document.hasFocus()
      if (active) {
        activeSecondsRef.current += 1
        setActiveSeconds(activeSecondsRef.current)
      }
      if (!idleRef.current && Date.now() - lastActivityAt.current >= IDLE_AFTER_MS) {
        idleRef.current = true
        void emitEvent('idle_started', {
          phase: episode?.state,
          idle_after_seconds: IDLE_AFTER_MS / 1000,
        })
      }
    }, 1000)

    const activity = () => {
      lastActivityAt.current = Date.now()
      if (idleRef.current) {
        idleRef.current = false
        void emitEvent('idle_ended', { phase: episode?.state })
      }
    }
    const visibility = () =>
      void emitEvent(
        document.visibilityState === 'visible'
          ? 'page_visible'
          : 'page_hidden',
        { phase: episode?.state },
      )
    const focus = () => void emitEvent('window_focused', { phase: episode?.state })
    const blur = () => void emitEvent('window_blurred', { phase: episode?.state })

    window.addEventListener('mousemove', activity, { passive: true })
    window.addEventListener('keydown', activity)
    window.addEventListener('touchstart', activity, { passive: true })
    window.addEventListener('focus', focus)
    window.addEventListener('blur', blur)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.clearInterval(tick)
      window.removeEventListener('mousemove', activity)
      window.removeEventListener('keydown', activity)
      window.removeEventListener('touchstart', activity)
      window.removeEventListener('focus', focus)
      window.removeEventListener('blur', blur)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [collectingTime, emitEvent, episode?.state])

  useEffect(() => {
    if (episode?.state !== 'pre_ai') return
    const timeout = window.setTimeout(() => {
      void emitEvent('decision_fields_edited', {
        phase: 'pre_ai',
        completed_fields: {
          malocclusion_class: Boolean(preClass),
          dhc: Boolean(preDhc),
          ac: Boolean(preAc),
          clinical_action: Boolean(preAction),
          notes: Boolean(preNotes),
        },
        confidence: preConfidence,
      })
    }, 750)
    return () => window.clearTimeout(timeout)
  }, [
    emitEvent,
    episode?.state,
    preAc,
    preAction,
    preClass,
    preConfidence,
    preDhc,
    preNotes,
  ])

  useEffect(() => {
    if (episode?.state !== 'ai_revealed') return
    const timeout = window.setTimeout(() => {
      void emitEvent('decision_fields_edited', {
        phase: 'post_ai',
        completed_fields: {
          malocclusion_class: Boolean(finalClass),
          dhc: Boolean(finalDhc),
          ac: Boolean(finalAc),
          clinical_action: Boolean(finalAction),
          notes: Boolean(finalNotes),
          override_reason: Boolean(overrideReason),
        },
        confidence: finalConfidence,
        agreement,
        override: overrideValue === 'yes',
        usefulness,
      })
    }, 750)
    return () => window.clearTimeout(timeout)
  }, [
    agreement,
    emitEvent,
    episode?.state,
    finalAc,
    finalAction,
    finalClass,
    finalConfidence,
    finalDhc,
    finalNotes,
    overrideReason,
    overrideValue,
    usefulness,
  ])

  useEffect(() => {
    if (
      episode?.state !== 'ai_revealed' ||
      !episode.ai_reveal ||
      revealedViewEpisode.current === episode.id
    ) {
      return
    }
    revealedViewEpisode.current = episode.id
    void emitEvent('ai_snapshot_rendered', {
      payload_sha256: episode.ai_reveal.payload_sha256,
      model_version: episode.ai_reveal.model_version,
      exposure_index: episode.exposure_index,
    })
  }, [emitEvent, episode])

  useEffect(() => {
    if (episode?.state !== 'ai_revealed' || !episode.pre_ai_decision) return
    const decision = episode.pre_ai_decision.decision
    setFinalClass(String(decision.malocclusion_class || ''))
    setFinalDhc(decision.dhc == null ? '' : String(decision.dhc))
    setFinalAc(decision.ac == null ? '' : String(decision.ac))
    setFinalAction(String(decision.clinical_action || ''))
    setFinalNotes(String(decision.notes || ''))
    setFinalConfidence(episode.pre_ai_decision.confidence)
  }, [episode?.state, episode?.pre_ai_decision])

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === Number(selectedCaseId)),
    [cases, selectedCaseId],
  )

  async function initializeDevelopmentStudy() {
    setBusy(true)
    setError('')
    try {
      const next = await researchAPI.bootstrap()
      setContext(next)
      setNotice('Development research workspace initialized.')
      const loadedInstruments = await researchAPI.instruments(STUDY_CODE)
      setInstruments(loadedInstruments)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Development bootstrap could not be completed.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function startEpisode() {
    if (!selectedCaseId) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const sessionId = makeUuid()
      const next = await researchAPI.createEpisode(
        STUDY_CODE,
        Number(selectedCaseId),
        sessionId,
      )
      updateEpisode(next)
      setNotice(
        'Research episode started. No AI output has been returned to this page.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Episode could not be started.')
    } finally {
      setBusy(false)
    }
  }

  async function lockPreAI() {
    if (!episode) return
    if (!preClass || !preDhc) {
      setError('Malocclusion class and DHC are required before locking.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await emitEvent('pre_ai_submit_requested', {
        active_seconds: activeSecondsRef.current,
      })
      const next = await researchAPI.lockPreAI(episode.id, {
        task_schema_version: TASK_SCHEMA_VERSION,
        decision: {
          malocclusion_class: preClass,
          dhc: Number(preDhc),
          ac: preAc ? Number(preAc) : null,
          clinical_action: preAction || null,
          notes: preNotes || null,
        },
        confidence: preConfidence,
        client_active_seconds: activeSecondsRef.current,
        client_started_at: phaseStartedAt.current,
        client_submitted_at: isoNow(),
      })
      updateEpisode(next)
      setNotice(
        'Unaided assessment locked on the server. It can no longer be edited.',
      )
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Pre-AI decision could not be locked.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function revealAI() {
    if (!episode) return
    setBusy(true)
    setError('')
    try {
      const next = await researchAPI.revealAI(episode.id)
      updateEpisode(next)
      setNotice('AI output revealed and preserved as an immutable snapshot.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI output could not be revealed.')
    } finally {
      setBusy(false)
    }
  }

  async function lockFinal() {
    if (!episode) return
    if (!finalClass || !finalDhc) {
      setError('Final malocclusion class and DHC are required.')
      return
    }
    if (overrideValue === 'yes' && !overrideReason.trim()) {
      setError('Record a reason for the clinical override.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await emitEvent('final_submit_requested', {
        active_seconds: activeSecondsRef.current,
      })
      const next = await researchAPI.lockFinal(episode.id, {
        task_schema_version: TASK_SCHEMA_VERSION,
        decision: {
          malocclusion_class: finalClass,
          dhc: Number(finalDhc),
          ac: finalAc ? Number(finalAc) : null,
          clinical_action: finalAction || null,
          notes: finalNotes || null,
        },
        confidence: finalConfidence,
        agreement,
        override: overrideValue === 'yes',
        override_reason: overrideValue === 'yes' ? overrideReason : null,
        usefulness,
        client_active_seconds: activeSecondsRef.current,
        client_started_at: phaseStartedAt.current,
        client_submitted_at: isoNow(),
      })
      updateEpisode(next)
      setNotice('Final decision locked. The episode is ready for reference review.')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Final decision could not be locked.',
      )
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    )
  }

  if (
    context?.participant?.role === 'reviewer' ||
    context?.participant?.role === 'adjudicator'
  ) {
    return <ReferenceWorkspace context={context} />
  }

  if (context?.participant?.role === 'research_admin') {
    return <ResearchAdminWorkspace context={context} />
  }

  const prediction = episode?.ai_reveal?.payload?.findings?.prediction || {}
  const quantitative =
    episode?.ai_reveal?.payload?.findings?.quantitative_summary || {}
  const predictedClass = displayClass(prediction.predicted_class)
  const modelConfidence =
    typeof prediction.confidence === 'number'
      ? `${Math.round(prediction.confidence * 1000) / 10}%`
      : 'Not available'

  return (
    <Box
      minHeight="100vh"
      sx={{ bgcolor: '#f4f7fb', py: { xs: 3, md: 5 } }}
    >
      <Container maxWidth="lg">
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="flex-start"
          gap={2}
          flexWrap="wrap"
          mb={3}
        >
          <Box>
            <Box display="flex" alignItems="center" gap={1.5}>
              <Science sx={{ color: '#0f766e', fontSize: 34 }} />
              <Typography variant="h4" fontWeight={800} color="#17324d">
                Research Mode v3
              </Typography>
            </Box>
            <Typography color="text.secondary" mt={0.75}>
              Controlled pre-AI, reveal, and final-decision workflow for the HCI pilot.
            </Typography>
          </Box>
          {context?.participant && (
            <Box display="flex" gap={1} flexWrap="wrap">
              <Chip label={context.participant.participant_code} />
              <Chip label={context.participant.site_code} color="primary" />
              <Chip label={context.active_epoch_code || 'No epoch'} variant="outlined" />
            </Box>
          )}
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {notice && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {notice}
          </Alert>
        )}

        {!context?.participant ? (
          <Card sx={{ borderRadius: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 5 } }}>
              <Typography variant="h5" fontWeight={700}>
                No governed study enrollment
              </Typography>
              <Typography color="text.secondary" mt={1} maxWidth={720}>
                Research Mode does not accept free-text clinician or site identities.
                An authorized study participant record is required before a decision
                episode can begin.
              </Typography>
              <Alert severity="warning" sx={{ mt: 3 }}>
                The initialization action below works only when the backend explicitly
                enables development bootstrap. It is disabled in production.
              </Alert>
              <Button
                variant="contained"
                startIcon={<Science />}
                onClick={initializeDevelopmentStudy}
                disabled={busy}
                sx={{ mt: 3 }}
              >
                Initialize development research workspace
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card sx={{ borderRadius: 4, mb: 3 }}>
              <CardContent sx={{ p: { xs: 2.5, md: 3.5 } }}>
                <Stepper activeStep={stateStep(episode)} alternativeLabel>
                  {[
                    'Independent assessment',
                    'Server lock',
                    'AI-assisted decision',
                    'Final record',
                  ].map((label) => (
                    <Step key={label}>
                      <StepLabel>{label}</StepLabel>
                    </Step>
                  ))}
                </Stepper>
              </CardContent>
            </Card>

            {episode && (
              <Card sx={{ borderRadius: 4, mb: 3 }}>
                <CardContent sx={{ p: { xs: 2.5, md: 3.5 } }}>
                  <Box
                    display="flex"
                    justifyContent="space-between"
                    alignItems="center"
                    gap={2}
                    mb={2}
                  >
                    <Box>
                      <Typography variant="h6" fontWeight={700}>
                        Clinical source images
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {sourceCase?.case_code || `Episode ${episode.id}`} · the same
                        evidence remains available throughout this episode
                      </Typography>
                    </Box>
                    <Chip
                      label={
                        episode.state === 'pre_ai'
                          ? 'AI hidden'
                          : episode.state === 'pre_ai_locked'
                            ? 'Decision locked'
                            : 'AI phase'
                      }
                      color={episode.state === 'pre_ai' ? 'success' : 'default'}
                      variant="outlined"
                    />
                  </Box>
                  {!sourceCase ? (
                    <Box
                      minHeight={180}
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                    >
                      <CircularProgress size={30} />
                    </Box>
                  ) : (
                    <Grid container spacing={2}>
                      {sourceCase.images.map((image, index) => (
                        <Grid item xs={12} sm={6} key={image.id}>
                          <Paper
                            variant="outlined"
                            sx={{ p: 1.25, borderRadius: 2, overflow: 'hidden' }}
                          >
                            {sourceImageUrls[image.id] ? (
                              <Box
                                component="img"
                                src={sourceImageUrls[image.id]}
                                alt={`Clinical source image ${index + 1}`}
                                sx={{
                                  width: '100%',
                                  height: { xs: 260, md: 380 },
                                  objectFit: 'contain',
                                  bgcolor: '#0f172a',
                                  borderRadius: 1,
                                }}
                              />
                            ) : (
                              <Box
                                height={{ xs: 260, md: 380 }}
                                display="flex"
                                alignItems="center"
                                justifyContent="center"
                              >
                                <CircularProgress size={28} />
                              </Box>
                            )}
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              display="block"
                              mt={0.75}
                            >
                              Source image {index + 1}
                            </Typography>
                          </Paper>
                        </Grid>
                      ))}
                    </Grid>
                  )}
                </CardContent>
              </Card>
            )}

            {!episode && (
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                  <Typography variant="h5" fontWeight={700}>
                    Start a controlled decision episode
                  </Typography>
                  <Typography color="text.secondary" mt={1} mb={3}>
                    Only completed cases are eligible. Selecting a case confirms that
                    inference exists but does not return any AI result.
                  </Typography>
                  <TextField
                    select
                    fullWidth
                    label="Completed case"
                    value={selectedCaseId}
                    onChange={(event) => setSelectedCaseId(event.target.value)}
                  >
                    {cases.map((item) => (
                      <MenuItem key={item.id} value={item.id}>
                        {item.title || `Case #${item.id}`} · {item.patient_id || '—'}
                      </MenuItem>
                    ))}
                  </TextField>
                  {selectedCase && (
                    <Alert severity="info" sx={{ mt: 2 }}>
                      Case #{selectedCase.id} will be linked to participant{' '}
                      {context.participant.participant_code}.
                    </Alert>
                  )}
                  <Box display="flex" justifyContent="flex-end" mt={3}>
                    <Button
                      variant="contained"
                      startIcon={<PlayArrow />}
                      onClick={startEpisode}
                      disabled={!selectedCaseId || busy}
                    >
                      Start episode
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            )}

            {episode?.state === 'pre_ai' && (
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                  <Box display="flex" justifyContent="space-between" gap={2}>
                    <Box>
                      <Typography variant="overline" color="#0f766e" fontWeight={700}>
                        Step 1 · unaided assessment
                      </Typography>
                      <Typography variant="h5" fontWeight={700}>
                        Record your independent clinical decision
                      </Typography>
                    </Box>
                    <Chip
                      icon={<Timer />}
                      label={`${activeSeconds}s active`}
                      variant="outlined"
                    />
                  </Box>
                  <Alert severity="info" sx={{ my: 3 }}>
                    AI output has not been returned to this page. All fields are blank
                    by design. Locking is permanent; later corrections are appended
                    rather than overwriting this record.
                  </Alert>
                  <Grid container spacing={2.5}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        required
                        label="Malocclusion class"
                        value={preClass}
                        onChange={(event) => setPreClass(event.target.value)}
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
                        required
                        type="number"
                        label="IOTN DHC"
                        inputProps={{ min: 1, max: 5 }}
                        value={preDhc}
                        onChange={(event) => setPreDhc(event.target.value)}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <TextField
                        fullWidth
                        type="number"
                        label="IOTN AC"
                        inputProps={{ min: 1, max: 10 }}
                        value={preAc}
                        onChange={(event) => setPreAc(event.target.value)}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Clinical action / recommendation"
                        value={preAction}
                        onChange={(event) => setPreAction(event.target.value)}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" fontWeight={600} gutterBottom>
                        Diagnostic confidence: {preConfidence}%
                      </Typography>
                      <Slider
                        value={preConfidence}
                        min={0}
                        max={100}
                        valueLabelDisplay="auto"
                        onChange={(_, value) => setPreConfidence(value as number)}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        multiline
                        minRows={3}
                        label="Independent clinical notes"
                        value={preNotes}
                        onChange={(event) => setPreNotes(event.target.value)}
                      />
                    </Grid>
                  </Grid>
                  <Box display="flex" justifyContent="flex-end" mt={3}>
                    <Button
                      variant="contained"
                      startIcon={<Lock />}
                      onClick={lockPreAI}
                      disabled={busy || !preClass || !preDhc}
                    >
                      Lock independent assessment
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            )}

            {episode?.state === 'pre_ai_locked' && (
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                  <Box display="flex" alignItems="center" gap={2}>
                    <CheckCircle color="success" sx={{ fontSize: 38 }} />
                    <Box>
                      <Typography variant="h5" fontWeight={700}>
                        Independent assessment is locked
                      </Typography>
                      <Typography color="text.secondary">
                        Hash: {episode.pre_ai_decision?.content_sha256.slice(0, 16)}…
                      </Typography>
                    </Box>
                  </Box>
                  <Alert severity="success" sx={{ mt: 3 }}>
                    The server persisted the unaided decision before enabling AI
                    reveal. The reveal action will snapshot the frozen inference
                    result and its provenance.
                  </Alert>
                  <Box display="flex" justifyContent="flex-end" mt={3}>
                    <Button
                      variant="contained"
                      color="secondary"
                      startIcon={<Visibility />}
                      onClick={revealAI}
                      disabled={busy}
                    >
                      Reveal AI output
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            )}

            {episode?.state === 'ai_revealed' && episode.ai_reveal && (
              <Grid container spacing={3}>
                <Grid item xs={12} md={5}>
                  <Card sx={{ borderRadius: 4, height: '100%' }}>
                    <CardContent sx={{ p: 3.5 }}>
                      <Typography variant="overline" color="#7c3aed" fontWeight={700}>
                        Immutable AI snapshot
                      </Typography>
                      <Typography variant="h5" fontWeight={700}>
                        OrthoAI output
                      </Typography>
                      <Divider sx={{ my: 2.5 }} />
                      <Box display="grid" gridTemplateColumns="1fr auto" gap={1.5}>
                        <Typography color="text.secondary">Predicted class</Typography>
                        <Typography fontWeight={700}>
                          {predictedClass || 'Unclassifiable'}
                        </Typography>
                        <Typography color="text.secondary">Model score</Typography>
                        <Typography fontWeight={700}>{modelConfidence}</Typography>
                        <Typography color="text.secondary">Model version</Typography>
                        <Typography fontWeight={700}>
                          {episode.ai_reveal.model_version}
                        </Typography>
                        <Typography color="text.secondary">Dental instances</Typography>
                        <Typography fontWeight={700}>
                          {quantitative.total_instances ?? '—'}
                        </Typography>
                        <Typography color="text.secondary">Classes present</Typography>
                        <Typography fontWeight={700}>
                          {quantitative.classes_present ?? '—'}
                        </Typography>
                      </Box>
                      <Alert severity="warning" sx={{ mt: 2.5 }}>
                        Model scores are uncalibrated and are not probabilities of
                        disease. Verify every AI finding clinically.
                      </Alert>
                      <Paper variant="outlined" sx={{ p: 2, mt: 2.5, borderRadius: 2 }}>
                        <Typography variant="body2">
                          {episode.ai_reveal.payload.summary}
                        </Typography>
                      </Paper>
                      <Typography variant="caption" color="text.secondary" display="block" mt={2}>
                        Snapshot {episode.ai_reveal.payload_sha256.slice(0, 16)}… ·
                        exposure {episode.exposure_index}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} md={7}>
                  <Card sx={{ borderRadius: 4 }}>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Box display="flex" justifyContent="space-between" gap={2}>
                        <Box>
                          <Typography variant="overline" color="#0f766e" fontWeight={700}>
                            Step 3 · final decision
                          </Typography>
                          <Typography variant="h5" fontWeight={700}>
                            Record the post-AI clinical decision
                          </Typography>
                        </Box>
                        <Chip
                          icon={<Timer />}
                          label={`${activeSeconds}s active`}
                          variant="outlined"
                        />
                      </Box>
                      <Typography variant="body2" color="text.secondary" mt={1}>
                        The fields begin from your locked pre-AI assessment, not from
                        the AI output. Edit any item that changed.
                      </Typography>
                      <Grid container spacing={2.5} mt={0.5}>
                        <Grid item xs={12} sm={6}>
                          <TextField
                            select
                            fullWidth
                            required
                            label="Final malocclusion class"
                            value={finalClass}
                            onChange={(event) => setFinalClass(event.target.value)}
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
                            required
                            type="number"
                            label="Final DHC"
                            inputProps={{ min: 1, max: 5 }}
                            value={finalDhc}
                            onChange={(event) => setFinalDhc(event.target.value)}
                          />
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <TextField
                            fullWidth
                            type="number"
                            label="Final AC"
                            inputProps={{ min: 1, max: 10 }}
                            value={finalAc}
                            onChange={(event) => setFinalAc(event.target.value)}
                          />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField
                            fullWidth
                            label="Final clinical action / recommendation"
                            value={finalAction}
                            onChange={(event) => setFinalAction(event.target.value)}
                          />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                          <TextField
                            select
                            fullWidth
                            label="Agreement with AI"
                            value={agreement}
                            onChange={(event) =>
                              setAgreement(
                                event.target.value as
                                  | 'agree'
                                  | 'partial'
                                  | 'disagree',
                              )
                            }
                          >
                            <MenuItem value="agree">Agree</MenuItem>
                            <MenuItem value="partial">Partially agree</MenuItem>
                            <MenuItem value="disagree">Disagree</MenuItem>
                          </TextField>
                        </Grid>
                        <Grid item xs={12} sm={6}>
                          <FormControl>
                            <FormLabel>Clinical override</FormLabel>
                            <RadioGroup
                              row
                              value={overrideValue}
                              onChange={(event) =>
                                setOverrideValue(event.target.value as 'yes' | 'no')
                              }
                            >
                              <FormControlLabel
                                value="no"
                                control={<Radio />}
                                label="No"
                              />
                              <FormControlLabel
                                value="yes"
                                control={<Radio />}
                                label="Yes"
                              />
                            </RadioGroup>
                          </FormControl>
                        </Grid>
                        {overrideValue === 'yes' && (
                          <Grid item xs={12}>
                            <TextField
                              fullWidth
                              required
                              label="Override rationale"
                              value={overrideReason}
                              onChange={(event) =>
                                setOverrideReason(event.target.value)
                              }
                            />
                          </Grid>
                        )}
                        <Grid item xs={12} sm={6}>
                          <Typography variant="body2" fontWeight={600}>
                            Final confidence: {finalConfidence}%
                          </Typography>
                          <Slider
                            value={finalConfidence}
                            min={0}
                            max={100}
                            valueLabelDisplay="auto"
                            onChange={(_, value) =>
                              setFinalConfidence(value as number)
                            }
                          />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                          <Typography variant="body2" fontWeight={600}>
                            AI usefulness: {usefulness}/5
                          </Typography>
                          <Slider
                            value={usefulness}
                            min={1}
                            max={5}
                            step={1}
                            marks
                            valueLabelDisplay="auto"
                            onChange={(_, value) => setUsefulness(value as number)}
                          />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField
                            fullWidth
                            multiline
                            minRows={3}
                            label="Final clinical notes"
                            value={finalNotes}
                            onChange={(event) => setFinalNotes(event.target.value)}
                          />
                        </Grid>
                      </Grid>
                      <Box display="flex" justifyContent="flex-end" mt={3}>
                        <Button
                          variant="contained"
                          startIcon={<Lock />}
                          onClick={lockFinal}
                          disabled={busy || !finalClass || !finalDhc}
                        >
                          Lock final decision
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            )}

            {episode &&
              ['final_locked', 'adjudicated'].includes(episode.state) && (
                <Box display="flex" flexDirection="column" gap={3}>
                  <Card sx={{ borderRadius: 4 }}>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Box display="flex" alignItems="center" gap={2}>
                        <CheckCircle color="success" sx={{ fontSize: 42 }} />
                        <Box>
                          <Typography variant="h5" fontWeight={700}>
                            Decision episode complete
                          </Typography>
                          <Typography color="text.secondary">
                            State: {episode.state.replaceAll('_', ' ')} · exposure{' '}
                            {episode.exposure_index}
                          </Typography>
                        </Box>
                      </Box>
                      <Alert severity="success" sx={{ mt: 3 }}>
                        Pre-AI decision, AI snapshot, final decision, and ordered event
                        chronology are preserved. Reference review remains separate.
                      </Alert>
                    </CardContent>
                  </Card>
                  {instruments.length ? (
                    instruments.map((instrument) => (
                      <DynamicSurvey
                        key={`${instrument.code}:${instrument.version}`}
                        instrument={instrument}
                        episode={episode}
                        onSaved={setNotice}
                      />
                    ))
                  ) : (
                    <Alert severity="info">
                      No approved study instrument is configured. Survey wording and
                      cadence must be supplied by the principal investigator before
                      launch.
                    </Alert>
                  )}
                </Box>
              )}
          </>
        )}
      </Container>
    </Box>
  )
}

export default function ResearchModePage() {
  const router = useRouter()
  const [context, setContext] = useState<ResearchContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadContext = useCallback(async () => {
    if (typeof window !== 'undefined' && !sessionStorage.getItem('authToken')) {
      router.replace('/signin')
      return
    }
    try {
      setError('')
      setContext(await researchAPI.context(STUDY_CODE))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Research Mode could not load.')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    void loadContext()
  }, [loadContext])

  async function initializeDevelopmentStudy() {
    setBusy(true)
    setError('')
    try {
      setContext(await researchAPI.bootstrap())
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'The development study could not be initialized.',
      )
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    )
  }

  if (
    context?.participant?.role === 'reviewer' ||
    context?.participant?.role === 'adjudicator'
  ) {
    return <ReferenceWorkspace context={context} />
  }

  if (context?.participant?.role === 'research_admin') {
    return <ResearchAdminWorkspace context={context} />
  }

  if (context?.participant?.role === 'clinician') {
    return <ClinicianStudyWorkspace context={context} />
  }

  return (
    <Box minHeight="100vh" sx={{ bgcolor: '#f5f7fb', py: { xs: 4, md: 8 } }}>
      <Container maxWidth="sm">
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Card sx={{ borderRadius: 4 }}>
          <CardContent sx={{ p: { xs: 3.5, md: 5 } }}>
            <Typography variant="h4" fontWeight={850} color="#17324d">
              Study access required
            </Typography>
            <Typography color="text.secondary" mt={1}>
              Your study coordinator must assign your role before you can begin.
            </Typography>
            <Alert severity="info" sx={{ mt: 3 }}>
              For local development only, an authorized account can initialize the
              study workspace below.
            </Alert>
            <Button
              variant="contained"
              onClick={() => void initializeDevelopmentStudy()}
              disabled={busy}
              sx={{ mt: 3, minHeight: 48, textTransform: 'none', borderRadius: 2.5 }}
            >
              {busy ? 'Initializing…' : 'Initialize local study'}
            </Button>
          </CardContent>
        </Card>
      </Container>
    </Box>
  )
}
