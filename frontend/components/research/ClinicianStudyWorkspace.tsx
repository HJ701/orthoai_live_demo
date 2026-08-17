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
import Grid from '@mui/material/Grid'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Slider from '@mui/material/Slider'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import ArrowForward from '@mui/icons-material/ArrowForward'
import CheckCircle from '@mui/icons-material/CheckCircle'
import Science from '@mui/icons-material/Science'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  ReferenceCase,
  ResearchContext,
  ResearchEpisode,
  ResearchEventSubmission,
  StudyInstrument,
  researchAPI,
} from '@/lib/api'
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

const actionOptions = [
  'No immediate action',
  'Monitor / review',
  'Request further records',
  'Orthodontic referral',
  'Proceed to treatment planning',
]

function iotnInputError(
  rawValue: string,
  label: string,
  minimum: number,
  maximum: number,
): string {
  const value = rawValue.trim()
  if (!value) return ''
  if (value.length > 64) return `${label} must be 64 characters or fewer.`
  if (/^\d+$/.test(value)) {
    const numericValue = Number(value)
    if (numericValue < minimum || numericValue > maximum) {
      return `${label} must be between ${minimum} and ${maximum}.`
    }
  }
  return ''
}

function iotnPayloadValue(rawValue: string): number | string | null {
  const value = rawValue.trim()
  if (!value) return null
  return /^\d+$/.test(value) ? Number(value) : value
}

const influenceOptions = [
  ['no_influence', 'No influence'],
  ['confirmed_assessment', 'Confirmed my assessment'],
  ['changed_part', 'Changed part of my assessment'],
  ['changed_final', 'Changed my final decision'],
  ['rejected_ai', 'I rejected the AI suggestion'],
  ['prefer_not_to_say', 'Prefer not to say'],
] as const

const reasonOptions = [
  ['clinical_evidence_differed', 'Clinical evidence differed'],
  ['ai_appeared_incorrect', 'AI appeared incorrect'],
  ['image_quality', 'Image quality'],
  ['patient_or_context', 'Patient or clinical context'],
  ['uncertain', 'I was uncertain'],
  ['other', 'Other'],
] as const

function makeUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isoNow(): string {
  return new Date().toISOString()
}

function MicroFollowUp({
  episode,
  busy,
  setBusy,
  onAdvance,
  onError,
}: {
  episode: ResearchEpisode
  busy: boolean
  setBusy: (value: boolean) => void
  onAdvance: () => Promise<void>
  onError: (message: string) => void
}) {
  const [influence, setInfluence] = useState('')
  const [reason, setReason] = useState('')
  const [otherReason, setOtherReason] = useState('')
  const [usefulness, setUsefulness] = useState<number | null>(null)
  const startedAt = useRef(isoNow())
  const plan = episode.follow_up
  const asksReason = plan.kind === 'reason' || plan.kind === 'reason_and_pulse'
  const asksPulse = plan.kind === 'pulse' || plan.kind === 'reason_and_pulse'

  async function submit(completion: 'completed' | 'declined') {
    if (completion === 'completed' && !influence) {
      onError('Choose the option that best describes the AI influence.')
      return
    }
    if (completion === 'completed' && asksReason && !reason) {
      onError('Choose the main reason before continuing.')
      return
    }
    if (completion === 'completed' && reason === 'other' && !otherReason.trim()) {
      onError('Briefly record the other reason.')
      return
    }
    if (completion === 'completed' && asksPulse && usefulness === null) {
      onError('Choose a usefulness rating before continuing.')
      return
    }

    setBusy(true)
    onError('')
    try {
      await researchAPI.submitSurvey({
        study_code: episode.study_code,
        instrument_code: plan.instrument_code,
        instrument_version: plan.instrument_version,
        episode_id: episode.id,
        period_code: plan.period_code || `episode-${episode.id}-post`,
        responses:
          completion === 'completed'
            ? {
                influence,
                primary_reason: asksReason ? reason : null,
                other_reason:
                  asksReason && reason === 'other' ? otherReason.trim() : null,
                usefulness: asksPulse ? usefulness : null,
                trigger_codes: plan.triggers,
              }
            : null,
        completion_status: completion,
        missing_reason: completion === 'declined' ? 'participant_declined' : null,
        client_started_at: startedAt.current,
        client_submitted_at: isoNow(),
      })
      await onAdvance()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'The follow-up could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      sx={{
        borderRadius: 4,
        border: '1px solid #c7d2fe',
        boxShadow: '0 18px 45px rgba(49, 46, 129, 0.10)',
      }}
    >
      <CardContent sx={{ p: { xs: 3, md: 4 } }}>
        <Typography variant="overline" color="#4f46e5" fontWeight={800}>
          One final check
        </Typography>
        <Typography variant="h5" fontWeight={800} color="#17324d">
          How did the AI affect this decision?
        </Typography>
        <Typography color="text.secondary" mt={0.75}>
          One brief check helps us distinguish useful support from inappropriate
          influence.
        </Typography>

        <Grid container spacing={1.25} mt={1.5}>
          {influenceOptions.map(([value, label]) => (
            <Grid item xs={12} sm={6} key={value}>
              <Button
                fullWidth
                variant={influence === value ? 'contained' : 'outlined'}
                onClick={() => setInfluence(value)}
                sx={{
                  minHeight: 48,
                  justifyContent: 'flex-start',
                  textTransform: 'none',
                  borderRadius: 2.5,
                }}
              >
                {label}
              </Button>
            </Grid>
          ))}
        </Grid>

        {asksReason && (
          <Box mt={3}>
            <Typography fontWeight={700} mb={1.25}>
              Main reason
            </Typography>
            <Grid container spacing={1.25}>
              {reasonOptions.map(([value, label]) => (
                <Grid item xs={12} sm={6} key={value}>
                  <Button
                    fullWidth
                    variant={reason === value ? 'contained' : 'outlined'}
                    color="secondary"
                    onClick={() => setReason(value)}
                    sx={{
                      minHeight: 44,
                      justifyContent: 'flex-start',
                      textTransform: 'none',
                      borderRadius: 2.5,
                    }}
                  >
                    {label}
                  </Button>
                </Grid>
              ))}
            </Grid>
            {reason === 'other' && (
              <TextField
                fullWidth
                size="small"
                label="Brief reason"
                value={otherReason}
                onChange={(event) => setOtherReason(event.target.value)}
                inputProps={{ maxLength: 240 }}
                sx={{ mt: 1.5 }}
              />
            )}
          </Box>
        )}

        {asksPulse && (
          <Box mt={3}>
            <Typography fontWeight={700}>How useful was the AI?</Typography>
            <Box display="flex" gap={1} mt={1.25} flexWrap="wrap">
              {[1, 2, 3, 4, 5].map((value) => (
                <Button
                  key={value}
                  variant={usefulness === value ? 'contained' : 'outlined'}
                  onClick={() => setUsefulness(value)}
                  aria-label={`Usefulness ${value} out of 5`}
                  sx={{ minWidth: 52, minHeight: 46, borderRadius: 2.5 }}
                >
                  {value}
                </Button>
              ))}
            </Box>
            <Box display="flex" justifyContent="space-between" maxWidth={292} mt={0.5}>
              <Typography variant="caption" color="text.secondary">
                Not useful
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Very useful
              </Typography>
            </Box>
          </Box>
        )}

        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          gap={2}
          mt={3.5}
          flexWrap="wrap"
        >
          <Button
            color="inherit"
            onClick={() => void submit('declined')}
            disabled={busy}
            sx={{ textTransform: 'none' }}
          >
            Prefer not to answer
          </Button>
          <Button
            variant="contained"
            endIcon={<ArrowForward />}
            onClick={() => void submit('completed')}
            disabled={busy}
            sx={{ minHeight: 48, px: 3, textTransform: 'none', borderRadius: 2.5 }}
          >
            {busy ? 'Saving…' : 'Save and continue'}
          </Button>
        </Box>
      </CardContent>
    </Card>
  )
}

function SessionInstrument({
  instrument,
  completedCount,
}: {
  instrument: StudyInstrument
  completedCount: number
}) {
  const [values, setValues] = useState<Record<string, any>>({})
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
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
      setError('Please complete the required items.')
      return
    }
    setStatus('saving')
    setError('')
    try {
      await researchAPI.submitSurvey({
        study_code: STUDY_CODE,
        instrument_code: instrument.code,
        instrument_version: instrument.version,
        period_code: `session-after-${completedCount}`,
        responses: values,
        completion_status: 'completed',
        client_started_at: startedAt.current,
        client_submitted_at: isoNow(),
      })
      setStatus('saved')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The check-in could not be saved.')
      setStatus('idle')
    }
  }

  if (status === 'saved') {
    return <Alert severity="success">{instrument.name} saved.</Alert>
  }

  return (
    <Card variant="outlined" sx={{ borderRadius: 3 }}>
      <CardContent sx={{ p: 3 }}>
        <Typography variant="h6" fontWeight={800}>
          {instrument.name}
        </Typography>
        {instrument.definition.instructions && (
          <Typography color="text.secondary" mt={0.5}>
            {instrument.definition.instructions}
          </Typography>
        )}
        <Box display="flex" flexDirection="column" gap={2.25} mt={2.5}>
          {questions.map((question) =>
            question.type === 'likert' || question.type === 'number' ? (
              <Box key={question.id}>
                <Typography fontWeight={600} mb={0.75}>
                  {question.label}
                </Typography>
                <Slider
                  value={values[question.id] ?? question.min ?? 1}
                  min={question.min ?? 1}
                  max={question.max ?? 5}
                  step={1}
                  marks
                  valueLabelDisplay="auto"
                  onChange={(_, value) =>
                    setValues((current) => ({ ...current, [question.id]: value }))
                  }
                />
              </Box>
            ) : (
              <TextField
                key={question.id}
                select={question.type === 'select'}
                fullWidth
                label={question.label}
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
            ),
          )}
        </Box>
        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
        <Box display="flex" justifyContent="flex-end" mt={2.5}>
          <Button
            variant="contained"
            onClick={() => void submit()}
            disabled={status === 'saving'}
            sx={{ textTransform: 'none' }}
          >
            {status === 'saving' ? 'Saving…' : 'Submit check-in'}
          </Button>
        </Box>
      </CardContent>
    </Card>
  )
}

export default function ClinicianStudyWorkspace({
  context,
}: {
  context: ResearchContext
}) {
  const router = useRouter()
  const [episode, setEpisode] = useState<ResearchEpisode | null>(null)
  const [sourceCase, setSourceCase] = useState<ReferenceCase | null>(null)
  const [sourceImageUrls, setSourceImageUrls] = useState<Record<number, string>>({})
  const [sessionInstruments, setSessionInstruments] = useState<StudyInstrument[]>([])
  const [completedCount, setCompletedCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [preClass, setPreClass] = useState('')
  const [preDhc, setPreDhc] = useState('')
  const [preAc, setPreAc] = useState('')
  const [preAction, setPreAction] = useState('')
  const [preConfidence, setPreConfidence] = useState(50)

  const [finalClass, setFinalClass] = useState('')
  const [finalDhc, setFinalDhc] = useState('')
  const [finalAc, setFinalAc] = useState('')
  const [finalAction, setFinalAction] = useState('')
  const [finalConfidence, setFinalConfidence] = useState(50)

  const activeSecondsRef = useRef(0)
  const phaseStartedAt = useRef(isoNow())
  const lastActivityAt = useRef(Date.now())
  const idleRef = useRef(false)
  const eventSequence = useRef(0)
  const eventQueue = useRef<Promise<void>>(Promise.resolve())
  const revealedViewEpisode = useRef<number | null>(null)
  const activeEpisodeId = episode?.id
  const activeEpisodeState = episode?.state

  const updateEpisode = useCallback((next: ResearchEpisode) => {
    eventSequence.current = next.last_event_sequence
    setEpisode(next)
  }, [])

  const emitEvent = useCallback(
    (eventType: string, payload: Record<string, any> | null = null) => {
      if (!episode) return Promise.resolve()
      eventQueue.current = eventQueue.current
        .catch(() => undefined)
        .then(async () => {
          const eventUuid = makeUuid()
          const body: ResearchEventSubmission = {
            event_uuid: eventUuid,
            idempotency_key: `${eventType}:${eventUuid}`,
            sequence_no: eventSequence.current + 1,
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

  const openCases = useCallback(async () => {
    const completedCaseId = episode?.case_id
    setNotice('Saved. Opening your Cases page…')
    sessionStorage.removeItem('researchStartCaseId')
    router.replace(
      completedCaseId
        ? `/cases?completed_case_id=${completedCaseId}`
        : '/cases',
    )
  }, [episode?.case_id, router])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const fetchBundle = () =>
          Promise.all([
            researchAPI.listEpisodes(STUDY_CODE),
            researchAPI.instruments(STUDY_CODE),
          ])
        let bundle: Awaited<ReturnType<typeof fetchBundle>>
        try {
          bundle = await fetchBundle()
        } catch {
          // A route transition can briefly abort a development GET; retry once.
          bundle = await fetchBundle()
        }
        const [episodes, instruments] = bundle
        if (cancelled) return
        const completed = episodes.items.filter((item) =>
          ['final_locked', 'adjudicated'].includes(item.state),
        )
        const resumable = episodes.items.find((item) =>
          ['pre_ai', 'pre_ai_locked', 'ai_revealed'].includes(item.state),
        )
        const pendingFollowUp = episodes.items.find(
          (item) =>
            ['final_locked', 'adjudicated'].includes(item.state) &&
            item.follow_up.required &&
            !item.follow_up.completed,
        )
        setCompletedCount(completed.length)
        setSessionInstruments(
          instruments.filter(
            (item) =>
              item.code !== 'ai-influence-micro' &&
              item.schedule?.level === 'session',
          ),
        )

        const params = new URLSearchParams(window.location.search)
        const requestedEpisodeId = Number(params.get('episode_id') || 0)
        const requestedCaseId = Number(
          params.get('case_id') ||
            sessionStorage.getItem('researchStartCaseId') ||
            0,
        )
        const requestedEpisode = requestedEpisodeId
          ? episodes.items.find((item) => item.id === requestedEpisodeId)
          : undefined
        const requestedCaseEpisode = requestedCaseId
          ? episodes.items.find((item) => item.case_id === requestedCaseId)
          : undefined

        if (requestedEpisode) {
          updateEpisode(requestedEpisode)
        } else if (requestedCaseEpisode) {
          const reviewFinished =
            ['final_locked', 'adjudicated'].includes(requestedCaseEpisode.state) &&
            (!requestedCaseEpisode.follow_up.required ||
              requestedCaseEpisode.follow_up.completed)
          if (reviewFinished) {
            router.replace(`/cases?completed_case_id=${requestedCaseId}`)
          } else {
            updateEpisode(requestedCaseEpisode)
          }
        } else if (requestedCaseId) {
          const created = await researchAPI.createEpisode(
            STUDY_CODE,
            requestedCaseId,
            makeUuid(),
          )
          if (!cancelled) updateEpisode(created)
        } else if (resumable || pendingFollowUp) {
          updateEpisode((resumable || pendingFollowUp)!)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'The study could not load.')
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
    if (!activeEpisodeId) {
      setSourceCase(null)
      setSourceImageUrls({})
      return
    }
    const episodeId = activeEpisodeId
    let disposed = false
    let createdUrls: string[] = []
    setSourceCase(null)
    setSourceImageUrls({})

    async function loadImages() {
      try {
        const loaded = await researchAPI.sourceCase(episodeId)
        if (!disposed) setSourceCase(loaded)
        const entries: Array<readonly [number, string]> = []
        for (const image of loaded.images) {
          if (disposed) break
          try {
            const blob = await researchAPI.sourceImage(loaded.episode_id, image.id)
            const url = URL.createObjectURL(blob)
            createdUrls.push(url)
            entries.push([image.id, url] as const)
          } catch {
            // Keep the assessment usable if one source image cannot be retrieved.
          }
        }
        if (!disposed) {
          setSourceImageUrls(Object.fromEntries(entries))
          if (loaded.images.length > 0 && entries.length === 0) {
            setError('The case images could not be loaded. Please retry this case.')
          }
        }
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : 'The case images could not load.')
        }
      }
    }
    void loadImages()
    return () => {
      disposed = true
      createdUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [activeEpisodeId])

  useEffect(() => {
    activeSecondsRef.current = 0
    phaseStartedAt.current = isoNow()
    lastActivityAt.current = Date.now()
    idleRef.current = false
  }, [episode?.id, episode?.state])

  useEffect(() => {
    const collecting =
      episode?.state === 'pre_ai' || episode?.state === 'ai_revealed'
    if (!collecting) return

    const tick = window.setInterval(() => {
      if (
        !idleRef.current &&
        document.visibilityState === 'visible' &&
        document.hasFocus()
      ) {
        activeSecondsRef.current += 1
      }
      if (!idleRef.current && Date.now() - lastActivityAt.current >= IDLE_AFTER_MS) {
        idleRef.current = true
        void emitEvent('idle_started', { phase: episode.state })
      }
    }, 1000)
    const activity = () => {
      lastActivityAt.current = Date.now()
      if (idleRef.current) {
        idleRef.current = false
        void emitEvent('idle_ended', { phase: episode.state })
      }
    }
    window.addEventListener('mousemove', activity, { passive: true })
    window.addEventListener('keydown', activity)
    window.addEventListener('touchstart', activity, { passive: true })
    return () => {
      window.clearInterval(tick)
      window.removeEventListener('mousemove', activity)
      window.removeEventListener('keydown', activity)
      window.removeEventListener('touchstart', activity)
    }
  }, [emitEvent, episode])

  useEffect(() => {
    if (activeEpisodeState !== 'pre_ai_locked' || !activeEpisodeId) return
    const episodeId = activeEpisodeId
    let cancelled = false
    async function recoverReveal() {
      setBusy(true)
      setError('')
      try {
        const revealed = await researchAPI.revealAI(episodeId)
        if (!cancelled) updateEpisode(revealed)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'The AI result could not load.')
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    void recoverReveal()
    return () => {
      cancelled = true
    }
  }, [activeEpisodeId, activeEpisodeState, updateEpisode])

  useEffect(() => {
    if (episode?.state !== 'ai_revealed' || !episode.pre_ai_decision) return
    const decision = episode.pre_ai_decision.decision
    setFinalClass(String(decision.malocclusion_class || ''))
    setFinalDhc(decision.dhc == null ? '' : String(decision.dhc))
    setFinalAc(decision.ac == null ? '' : String(decision.ac))
    setFinalAction(String(decision.clinical_action || ''))
    setFinalConfidence(episode.pre_ai_decision.confidence)
  }, [episode?.state, episode?.pre_ai_decision])

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

  async function submitInitialAssessment() {
    const dhcError = iotnInputError(preDhc, 'IOTN DHC', 1, 5)
    const acError = iotnInputError(preAc, 'IOTN AC', 1, 10)
    if (!episode || !preClass || !preDhc.trim()) {
      setError('Choose a malocclusion class and DHC grade.')
      return
    }
    if (dhcError || acError) {
      setError(dhcError || acError)
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await emitEvent('pre_ai_submit_requested', {
        active_seconds: activeSecondsRef.current,
      })
      const locked = await researchAPI.lockPreAI(episode.id, {
        task_schema_version: TASK_SCHEMA_VERSION,
        decision: {
          malocclusion_class: preClass,
          dhc: iotnPayloadValue(preDhc),
          ac: iotnPayloadValue(preAc),
          clinical_action: preAction || null,
        },
        confidence: preConfidence,
        client_active_seconds: activeSecondsRef.current,
        client_started_at: phaseStartedAt.current,
        client_submitted_at: isoNow(),
      })
      updateEpisode(locked)
      setNotice('Initial assessment saved. Preparing the AI comparison…')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The initial assessment could not be saved.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function submitFinalDecision() {
    const dhcError = iotnInputError(finalDhc, 'IOTN DHC', 1, 5)
    const acError = iotnInputError(finalAc, 'IOTN AC', 1, 10)
    if (!episode || !finalClass || !finalDhc.trim()) {
      setError('Choose a final malocclusion class and DHC grade.')
      return
    }
    if (dhcError || acError) {
      setError(dhcError || acError)
      return
    }
    setBusy(true)
    setError('')
    try {
      await emitEvent('final_submit_requested', {
        active_seconds: activeSecondsRef.current,
      })
      const completed = await researchAPI.lockFinal(episode.id, {
        task_schema_version: TASK_SCHEMA_VERSION,
        decision: {
          malocclusion_class: finalClass,
          dhc: iotnPayloadValue(finalDhc),
          ac: iotnPayloadValue(finalAc),
          clinical_action: finalAction || null,
        },
        confidence: finalConfidence,
        client_active_seconds: activeSecondsRef.current,
        client_started_at: phaseStartedAt.current,
        client_submitted_at: isoNow(),
      })
      setCompletedCount((count) => count + 1)
      updateEpisode(completed)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The final decision could not be saved.',
      )
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (
      !episode ||
      !['final_locked', 'adjudicated'].includes(episode.state) ||
      (episode.follow_up.required && !episode.follow_up.completed)
    ) {
      return
    }
    setNotice('Research review complete. Opening your Cases page…')
    const redirect = window.setTimeout(() => {
      void openCases()
    }, 1200)
    return () => window.clearTimeout(redirect)
  }, [episode, openCases])

  if (loading) {
    return (
      <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
        <CircularProgress />
      </Box>
    )
  }

  const prediction = episode?.ai_reveal?.payload?.findings?.prediction || {}
  const quantitative =
    episode?.ai_reveal?.payload?.findings?.quantitative_summary || {}
  const predictedClass = displayClass(prediction.predicted_class)
  const modelConfidence =
    typeof prediction.confidence === 'number'
      ? `${Math.round(prediction.confidence * 1000) / 10}%`
      : 'Not available'
  const followUpPending =
    episode &&
    ['final_locked', 'adjudicated'].includes(episode.state) &&
    episode.follow_up.required &&
    !episode.follow_up.completed

  return (
    <Box minHeight="100vh" sx={{ bgcolor: '#f5f7fb', py: { xs: 3, md: 5 } }}>
      <Container maxWidth="lg">
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          gap={2}
          mb={3}
        >
          <Box>
            <Box display="flex" alignItems="center" gap={1.25}>
              <Science sx={{ color: '#4f46e5', fontSize: 30 }} />
              <Typography variant="h4" fontWeight={850} color="#17324d">
                Research Mode
              </Typography>
            </Box>
            <Typography color="text.secondary" mt={0.5}>
              Record your assessment, compare with OrthoAI, then finish.
            </Typography>
          </Box>
          <Chip
            label="Step 2 of 3 · Expert review"
            sx={{ bgcolor: '#eef2ff', color: '#3730a3', fontWeight: 700 }}
          />
        </Box>

        {error && (
          <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {notice && (
          <Alert severity="success" onClose={() => setNotice('')} sx={{ mb: 2 }}>
            {notice}
          </Alert>
        )}

        {!episode && (
          <Card
            sx={{
              borderRadius: 4,
              maxWidth: 720,
              mx: 'auto',
              mt: { xs: 3, md: 8 },
              boxShadow: '0 18px 50px rgba(15, 23, 42, 0.08)',
            }}
          >
            <CardContent sx={{ p: { xs: 3.5, md: 6 }, textAlign: 'center' }}>
              <Box
                width={64}
                height={64}
                borderRadius="50%"
                bgcolor="#eef2ff"
                color="#4f46e5"
                display="flex"
                alignItems="center"
                justifyContent="center"
                mx="auto"
              >
                <Science sx={{ fontSize: 32 }} />
              </Box>
              <Typography variant="h4" fontWeight={850} color="#17324d" mt={2.5}>
                Diagnose a case first
              </Typography>
              <Typography color="text.secondary" mt={1} mb={3.5}>
                Research Mode always follows a completed OrthoAI diagnosis, so
                every response stays linked to the correct case.
              </Typography>
              <Button
                variant="contained"
                size="large"
                endIcon={<ArrowForward />}
                onClick={() => router.push('/upload')}
                sx={{
                  minHeight: 52,
                  px: 4,
                  borderRadius: 2.5,
                  textTransform: 'none',
                  fontWeight: 750,
                }}
              >
                Diagnose a Case
              </Button>
            </CardContent>
          </Card>
        )}

        {episode && (
          <Box display="flex" flexDirection="column" gap={3}>
            <Card sx={{ borderRadius: 4 }}>
              <CardContent sx={{ p: { xs: 2.5, md: 3.5 } }}>
                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                  mb={2}
                >
                  <Box>
                    <Typography variant="h6" fontWeight={800} color="#17324d">
                      Case images
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {sourceCase?.case_code || 'Loading assigned case…'}
                    </Typography>
                  </Box>
                  {episode.state === 'pre_ai' && (
                    <Chip label="AI hidden" color="success" variant="outlined" />
                  )}
                </Box>
                {!sourceCase ? (
                  <Box minHeight={220} display="flex" justifyContent="center" alignItems="center">
                    <CircularProgress size={30} />
                  </Box>
                ) : (
                  <Grid container spacing={2}>
                    {sourceCase.images.map((image, index) => (
                      <Grid item xs={12} sm={6} key={image.id}>
                        <Paper
                          variant="outlined"
                          sx={{ p: 1, borderRadius: 2.5, overflow: 'hidden' }}
                        >
                          {sourceImageUrls[image.id] ? (
                            <Box
                              component="img"
                              src={sourceImageUrls[image.id]}
                              alt={`Clinical source image ${index + 1}`}
                              sx={{
                                display: 'block',
                                width: '100%',
                                height: { xs: 260, md: 390 },
                                objectFit: 'contain',
                                bgcolor: '#0f172a',
                                borderRadius: 1.5,
                              }}
                            />
                          ) : (
                            <Box
                              height={{ xs: 260, md: 390 }}
                              display="flex"
                              alignItems="center"
                              justifyContent="center"
                            >
                              <CircularProgress size={26} />
                            </Box>
                          )}
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                )}
              </CardContent>
            </Card>

            {episode.state === 'pre_ai' && (
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                  <Typography variant="overline" color="#0f766e" fontWeight={800}>
                    Your assessment
                  </Typography>
                  <Typography variant="h5" fontWeight={850} color="#17324d">
                    What is your independent decision?
                  </Typography>
                  <Typography color="text.secondary" mt={0.75} mb={3}>
                    Complete the core fields. The AI will appear after you submit.
                  </Typography>
                  <Grid container spacing={2.25}>
                    <Grid item xs={12} md={6}>
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
                    <Grid item xs={6} md={3}>
                      <TextField
                        fullWidth
                        required
                        label="IOTN DHC"
                        placeholder="e.g. 4 or 4h"
                        inputProps={{ maxLength: 64, inputMode: 'text' }}
                        value={preDhc}
                        onChange={(event) => setPreDhc(event.target.value)}
                        error={Boolean(iotnInputError(preDhc, 'IOTN DHC', 1, 5))}
                        helperText={
                          iotnInputError(preDhc, 'IOTN DHC', 1, 5) ||
                          'Enter a numeric grade or an IOTN code.'
                        }
                      />
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <TextField
                        fullWidth
                        label="IOTN AC (optional)"
                        placeholder="e.g. 6 or not assessable"
                        inputProps={{ maxLength: 64, inputMode: 'text' }}
                        value={preAc}
                        onChange={(event) => setPreAc(event.target.value)}
                        error={Boolean(iotnInputError(preAc, 'IOTN AC', 1, 10))}
                        helperText={
                          iotnInputError(preAc, 'IOTN AC', 1, 10) ||
                          'Enter a numeric grade or short text.'
                        }
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        select
                        fullWidth
                        label="Clinical action (optional)"
                        value={preAction}
                        onChange={(event) => setPreAction(event.target.value)}
                      >
                        {actionOptions.map((option) => (
                          <MenuItem key={option} value={option}>
                            {option}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Typography fontWeight={700}>
                        Confidence: {preConfidence}%
                      </Typography>
                      <Slider
                        value={preConfidence}
                        min={0}
                        max={100}
                        step={5}
                        valueLabelDisplay="auto"
                        onChange={(_, value) => setPreConfidence(value as number)}
                      />
                    </Grid>
                  </Grid>
                  <Box display="flex" justifyContent="flex-end" mt={3}>
                    <Button
                      variant="contained"
                      size="large"
                      endIcon={busy ? undefined : <ArrowForward />}
                      onClick={() => void submitInitialAssessment()}
                      disabled={busy || !preClass || !preDhc.trim()}
                      aria-busy={busy}
                      sx={{
                        minHeight: 50,
                        px: 3,
                        borderRadius: 2.5,
                        textTransform: 'none',
                        fontWeight: 750,
                      }}
                    >
                      {busy
                        ? 'Saving assessment and preparing AI…'
                        : 'Submit initial assessment'}
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            )}

            {episode.state === 'pre_ai_locked' && (
              <Card sx={{ borderRadius: 4 }}>
                <CardContent sx={{ p: 5, textAlign: 'center' }}>
                  <CircularProgress size={34} />
                  <Typography variant="h6" fontWeight={800} mt={2}>
                    Preparing the AI comparison…
                  </Typography>
                </CardContent>
              </Card>
            )}

            {episode.state === 'ai_revealed' && episode.ai_reveal && (
              <Grid container spacing={3}>
                <Grid item xs={12} md={5}>
                  <Card
                    sx={{
                      borderRadius: 4,
                      height: '100%',
                      border: '1px solid #ddd6fe',
                    }}
                  >
                    <CardContent sx={{ p: { xs: 3, md: 3.5 } }}>
                      <Typography variant="overline" color="#6d28d9" fontWeight={800}>
                        AI comparison
                      </Typography>
                      <Typography variant="h5" fontWeight={850} color="#17324d">
                        OrthoAI result
                      </Typography>
                      <Divider sx={{ my: 2.5 }} />
                      <Box display="grid" gridTemplateColumns="1fr auto" gap={1.5}>
                        <Typography color="text.secondary">Predicted class</Typography>
                        <Typography fontWeight={800}>
                          {predictedClass || 'Unclassifiable'}
                        </Typography>
                        <Typography color="text.secondary">Model score</Typography>
                        <Typography fontWeight={800}>{modelConfidence}</Typography>
                        <Typography color="text.secondary">Detected findings</Typography>
                        <Typography fontWeight={800}>
                          {quantitative.total_instances ?? '—'}
                        </Typography>
                        <Typography color="text.secondary">Finding types</Typography>
                        <Typography fontWeight={800}>
                          {quantitative.classes_present ?? '—'}
                        </Typography>
                      </Box>
                      {episode.ai_reveal.payload.summary && (
                        <Paper variant="outlined" sx={{ p: 2, mt: 2.5, borderRadius: 2.5 }}>
                          <Typography variant="body2">
                            {episode.ai_reveal.payload.summary}
                          </Typography>
                        </Paper>
                      )}
                      <Alert severity="warning" sx={{ mt: 2.5 }}>
                        Treat the score as model output, not a calibrated probability.
                      </Alert>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} md={7}>
                  <Card sx={{ borderRadius: 4 }}>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Typography variant="overline" color="#0f766e" fontWeight={800}>
                        Your final decision
                      </Typography>
                      <Typography variant="h5" fontWeight={850} color="#17324d">
                        Confirm or update your assessment
                      </Typography>
                      <Typography color="text.secondary" mt={0.75} mb={3}>
                        Your original answers are pre-filled. Change only what the
                        evidence supports.
                      </Typography>
                      <Grid container spacing={2.25}>
                        <Grid item xs={12} md={6}>
                          <TextField
                            select
                            fullWidth
                            required
                            label="Malocclusion class"
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
                        <Grid item xs={6} md={3}>
                          <TextField
                            fullWidth
                            required
                            label="IOTN DHC"
                            placeholder="e.g. 4 or 4h"
                            inputProps={{ maxLength: 64, inputMode: 'text' }}
                            value={finalDhc}
                            onChange={(event) => setFinalDhc(event.target.value)}
                            error={Boolean(
                              iotnInputError(finalDhc, 'IOTN DHC', 1, 5)
                            )}
                            helperText={
                              iotnInputError(finalDhc, 'IOTN DHC', 1, 5) ||
                              'Enter a numeric grade or an IOTN code.'
                            }
                          />
                        </Grid>
                        <Grid item xs={6} md={3}>
                          <TextField
                            fullWidth
                            label="IOTN AC"
                            placeholder="e.g. 6 or not assessable"
                            inputProps={{ maxLength: 64, inputMode: 'text' }}
                            value={finalAc}
                            onChange={(event) => setFinalAc(event.target.value)}
                            error={Boolean(
                              iotnInputError(finalAc, 'IOTN AC', 1, 10)
                            )}
                            helperText={
                              iotnInputError(finalAc, 'IOTN AC', 1, 10) ||
                              'Enter a numeric grade or short text.'
                            }
                          />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField
                            select
                            fullWidth
                            label="Clinical action (optional)"
                            value={finalAction}
                            onChange={(event) => setFinalAction(event.target.value)}
                          >
                            {actionOptions.map((option) => (
                              <MenuItem key={option} value={option}>
                                {option}
                              </MenuItem>
                            ))}
                          </TextField>
                        </Grid>
                        <Grid item xs={12}>
                          <Typography fontWeight={700}>
                            Confidence: {finalConfidence}%
                          </Typography>
                          <Slider
                            value={finalConfidence}
                            min={0}
                            max={100}
                            step={5}
                            valueLabelDisplay="auto"
                            onChange={(_, value) =>
                              setFinalConfidence(value as number)
                            }
                          />
                        </Grid>
                      </Grid>
                      <Box display="flex" justifyContent="flex-end" mt={3}>
                        <Button
                          variant="contained"
                          size="large"
                          endIcon={busy ? undefined : <ArrowForward />}
                          onClick={() => void submitFinalDecision()}
                          disabled={busy || !finalClass || !finalDhc.trim()}
                          aria-busy={busy}
                          sx={{
                            minHeight: 50,
                            px: 3,
                            borderRadius: 2.5,
                            textTransform: 'none',
                            fontWeight: 750,
                          }}
                        >
                          {busy ? 'Saving final decision…' : 'Submit final decision'}
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            )}

            {followUpPending && (
              <MicroFollowUp
                episode={episode}
                busy={busy}
                setBusy={setBusy}
                onError={setError}
                onAdvance={openCases}
              />
            )}

            {['final_locked', 'adjudicated'].includes(episode.state) &&
              !followUpPending && (
                <Card sx={{ borderRadius: 4 }}>
                  <CardContent sx={{ p: { xs: 3.5, md: 4.5 } }}>
                    <Box
                      display="flex"
                      alignItems="center"
                      justifyContent="space-between"
                      gap={3}
                      flexWrap="wrap"
                    >
                      <Box display="flex" alignItems="center" gap={2}>
                        <CheckCircle color="success" sx={{ fontSize: 42 }} />
                        <Box>
                          <Typography variant="h5" fontWeight={850} color="#17324d">
                            Research review complete
                          </Typography>
                          <Typography color="text.secondary">
                            Your responses are saved. Opening Cases…
                          </Typography>
                        </Box>
                      </Box>
                      <CircularProgress size={26} />
                    </Box>
                  </CardContent>
                </Card>
              )}
          </Box>
        )}
      </Container>
    </Box>
  )
}
