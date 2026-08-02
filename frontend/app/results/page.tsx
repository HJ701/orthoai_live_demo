'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Chip,
  Grid,
  Paper,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Tooltip,
  CircularProgress,
  Alert,
} from '@mui/material'
import {
  Info,
  ArrowBack,
  Download,
  Refresh,
  NoteAdd,
  ExpandMore,
  ContentCopy,
  PhotoCamera,
  Science,
} from '@mui/icons-material'
import { motion } from 'framer-motion'
import { displayClass } from '@/lib/format'

interface DiagnosticResult {
  condition: string
  confidence: number
  scope: 'Patient classification' | 'Image segmentation'
  description: string
  instanceCount?: number
  imageCount?: number
}

interface CaseData {
  case_id: string
  patient_id: string
  case_title: string
  modality_tags: string[]
  created_at: string
  model_version: string
  model_checksums: string[]
}

interface EvidenceSummary {
  imageId: number
  label: string
  condition: string
  confidence: number
  detectionCount: number
  width: number
  height: number
  detections: any[]
}

const detectionColor = (classId: number) => `hsl(${(classId * 47) % 360} 75% 48%)`

function ResultsPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const caseId = searchParams.get('case_id') || ''

  const [results, setResults] = useState<DiagnosticResult[]>([])
  const [imageEvidence, setImageEvidence] = useState<EvidenceSummary[]>([])
  const [evidenceImages, setEvidenceImages] = useState<Record<number, string>>({})
  const [rawResult, setRawResult] = useState<Record<string, any> | null>(null)
  const [loadError, setLoadError] = useState('')
  const [explanation, setExplanation] = useState<string>('')
  const [explanationSource, setExplanationSource] = useState<string>('')
  const [explanationLoading, setExplanationLoading] = useState(true)
  const [caseData, setCaseData] = useState<CaseData | null>(null)
  const [jsonExpanded, setJsonExpanded] = useState(false)
  const [noteDialogOpen, setNoteDialogOpen] = useState(false)
  const [clinicianNote, setClinicianNote] = useState('')
  const [researchAccessChecked, setResearchAccessChecked] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function protectPreAIAssessment() {
      try {
        if (!caseId) {
          setResearchAccessChecked(true)
          return
        }
        const { researchAPI } = await import('@/lib/api')
        const context = await researchAPI.context()
        if (context.participant?.role !== 'clinician') {
          if (!cancelled) setResearchAccessChecked(true)
          return
        }
        const episodes = await researchAPI.listEpisodes('ORTHOAI-HCI-V3')
        const numericCaseId = Number(caseId.replace('CASE-', ''))
        const latest = episodes.items.find((item) => item.case_id === numericCaseId)
        const finished =
          latest &&
          ['final_locked', 'adjudicated'].includes(latest.state) &&
          (!latest.follow_up.required || latest.follow_up.completed)
        if (!finished) {
          router.replace(
            latest
              ? `/research?episode_id=${latest.id}`
              : `/research?case_id=${numericCaseId}`,
          )
          return
        }
        if (!cancelled) setResearchAccessChecked(true)
      } catch {
        // Keep the diagnostic surface available outside an enrolled research study.
        if (!cancelled) setResearchAccessChecked(true)
      }
    }
    void protectPreAIAssessment()
    return () => {
      cancelled = true
    }
  }, [caseId, router])

  useEffect(() => {
    const loadResults = async () => {
      try {
        setLoadError('')
        if (!caseId) throw new Error('A case_id is required to load results.')
        const { resultsAPI, casesAPI } = await import('@/lib/api')
        // Case ID from URL might be numeric or have CASE- prefix
        const caseIdNum = caseId.startsWith('CASE-')
          ? parseInt(caseId.replace('CASE-', ''))
          : parseInt(caseId)

        // Fetch results from API
        const apiResults = await resultsAPI.getResults(caseIdNum)
        setRawResult(apiResults as unknown as Record<string, any>)

        // Fetch THIS case's own details so the header reflects the case being
        // viewed — not the last-uploaded case cached in sessionStorage (which
        // made different cases look identical).
        const caseDetail = await casesAPI.getCase(caseIdNum).catch(() => null)

        // sessionStorage only as a last-resort fallback for older cases
        const storedCase = sessionStorage.getItem('currentCase')
        let parsedCase: any = {}
        if (storedCase) {
          try {
            const sc = JSON.parse(storedCase)
            if (sc.case_id === String(caseIdNum)) parsedCase = sc
          } catch {
            /* ignore */
          }
        }

        const findings = (apiResults.findings as any) || {}
        const models = findings.models || {}
        const checksums = [
          models?.malocclusion?.provenance?.artifact_sha256,
          models?.dental_segmentation?.provenance?.artifact_sha256,
        ].filter((value): value is string => typeof value === 'string' && value.length > 0)

        // Set case data (prefer the case's own backend fields and real provenance)
        setCaseData({
          case_id: String(apiResults.case_id),
          patient_id: caseDetail?.patient_id || parsedCase.patient_id || '—',
          case_title: caseDetail?.title || parsedCase.case_title || 'Case Analysis',
          modality_tags: caseDetail?.tags || parsedCase.modality_tags || [],
          created_at: apiResults.created_at,
          model_version: apiResults.model_version,
          model_checksums: checksums,
        })

        // Preserve task boundaries: one patient-level malocclusion result and
        // per-class quantitative segmentation summaries. Scores are never fused.
        const transformedResults: DiagnosticResult[] = []
        const evidenceSummaries: EvidenceSummary[] = []
        const prediction = models?.malocclusion?.prediction || findings.prediction
        const quantitativeSummary =
          models?.dental_segmentation?.quantitative_summary || findings.quantitative_summary || {}

        // Per-image evidence cards (one per uploaded image), readable class names
        apiResults.per_image_evidence.forEach((evidence, idx) => {
          const detections: any[] = Array.isArray((evidence.findings as any)?.detections)
            ? (evidence.findings as any).detections
            : []
          const counts = new Map<string, number>()
          detections.forEach((detection) => {
            const label = String(detection.label || detection.type || 'Unclassified')
            counts.set(label, (counts.get(label) || 0) + 1)
          })
          const condition = counts.size
            ? Array.from(counts.entries()).map(([label, count]) => `${count} × ${label}`).join(', ')
            : (evidence.findings as any)?.status === 'skipped'
              ? 'Not run — outside validated modality scope'
              : 'No segmentation instances above threshold'
          evidenceSummaries.push({
            imageId: evidence.image_id,
            label: evidence.filename || `Image ${idx + 1}`,
            condition,
            confidence: Math.round((Math.max(0, ...detections.map((d) => Number(d.confidence) || 0))) * 100),
            detectionCount: detections.length,
            width: Number((evidence.findings as any)?.width_pixels) || 1,
            height: Number((evidence.findings as any)?.height_pixels) || 1,
            detections,
          })
        })

        // Primary finding = the single patient-level diagnosis (not one row per image)
        if (prediction?.predicted_class != null) {
          transformedResults.push({
            condition: displayClass(prediction.predicted_class),
            confidence: Math.round((prediction.confidence || 0) * 100),
            scope: 'Patient classification',
            description: apiResults.summary,
          })
        }

        const classSummaries: any[] = Array.isArray(quantitativeSummary.classes)
          ? quantitativeSummary.classes
          : []
        classSummaries.forEach((item) => {
          transformedResults.push({
            condition: String(item.label || 'Unclassified dental instance'),
            confidence: Math.round((Number(item.mean_confidence) || 0) * 100),
            scope: 'Image segmentation',
            instanceCount: Number(item.instance_count) || 0,
            imageCount: Number(item.image_count) || 0,
            description: `${Number(item.instance_count) || 0} segmented instance(s) across ${Number(item.image_count) || 0} image(s). Mean image-plane area per instance: ${Number(item.mean_instance_area_percent || 0).toFixed(2)}%.`,
          })
        })

        setImageEvidence(evidenceSummaries)

        // Fetch the actual uploaded images (first 3) for Evidence & Visuals
        evidenceSummaries.slice(0, 3).forEach(async (ev) => {
          try {
            const url = await casesAPI.getImageObjectUrl(caseIdNum, ev.imageId)
            setEvidenceImages((prev) => ({ ...prev, [ev.imageId]: url }))
          } catch {
            /* leave placeholder if an image fails to load */
          }
        })

        // Fetch the LLM "Structured Output" narrative explanation
        resultsAPI
          .getExplanation(caseIdNum)
          .then((e) => {
            setExplanation(e.explanation)
            setExplanationSource(e.source)
          })
          .catch(() => setExplanation(''))
          .finally(() => setExplanationLoading(false))

        setResults(transformedResults)
      } catch (err: any) {
        console.error('Failed to load results:', err)
        setExplanationLoading(false)
        setLoadError(err?.message || 'Results are unavailable.')
      }
    }

    loadResults()
  }, [caseId])

  const handleDownloadPDF = async () => {
    try {
      const { resultsAPI } = await import('@/lib/api')
      const caseIdNum = caseId.startsWith('CASE-') 
        ? parseInt(caseId.replace('CASE-', '')) 
        : parseInt(caseId)
      const blob = await resultsAPI.downloadPDF(caseIdNum)
      
      // Create download link
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `case_${caseId}_summary.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(`Failed to download PDF: ${err.message}`)
    }
  }

  const handleDownloadJSON = () => {
    if (!rawResult) return
    const jsonData = rawResult
    const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `case-${caseId}-results.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCopyJSON = () => {
    if (!rawResult) return
    const jsonData = rawResult
    navigator.clipboard.writeText(JSON.stringify(jsonData, null, 2))
    alert('JSON copied to clipboard')
  }

  const handleAddNote = async () => {
    try {
      const { casesAPI } = await import('@/lib/api')
      const caseIdNum = caseId.startsWith('CASE-') 
        ? parseInt(caseId.replace('CASE-', '')) 
        : parseInt(caseId)
      await casesAPI.addNote(caseIdNum, clinicianNote)
      setNoteDialogOpen(false)
      setClinicianNote('')
      alert('Note saved successfully')
    } catch (err: any) {
      alert(`Failed to save note: ${err.message}`)
    }
  }

  const handleRerun = async () => {
    try {
      const { inferenceAPI, researchAPI } = await import('@/lib/api')
      const caseIdNum = caseId.startsWith('CASE-') 
        ? parseInt(caseId.replace('CASE-', '')) 
        : parseInt(caseId)
      const inferenceResponse = await inferenceAPI.startInference(caseIdNum, {
        forceRerun: true,
      })
      const jobId = inferenceResponse.job_id
      sessionStorage.setItem('jobId', String(jobId))
      const episodes = await researchAPI
        .listEpisodes('ORTHOAI-HCI-V3')
        .catch(() => ({ total: 0, items: [] }))
      const repeatSource = episodes.items.find(
        (item) =>
          item.case_id === caseIdNum &&
          ['final_locked', 'adjudicated'].includes(item.state) &&
          (!item.follow_up.required || item.follow_up.completed),
      )
      const repeatQuery = repeatSource
        ? `&repeat_of_episode_id=${repeatSource.id}`
        : ''
      router.push(
        `/inference?case_id=${caseId}&job_id=${jobId}${repeatQuery}`,
      )
    } catch (err: any) {
      alert(`Failed to restart inference: ${err.message}`)
    }
  }

  if (loadError) {
    return (
      <Box className="min-h-screen flex items-center justify-center" sx={{ p: 3 }}>
        <Alert severity="error" sx={{ maxWidth: 720 }}>
          Results unavailable: {loadError} No placeholder or sample diagnosis has been substituted.
        </Alert>
      </Box>
    )
  }

  if (!researchAccessChecked || !caseData) {
    return (
      <Box className="min-h-screen flex items-center justify-center">
        <Typography>Loading...</Typography>
      </Box>
    )
  }

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
      sx={{ py: { xs: 4, md: 6 }, px: { xs: 2, md: 0 } }}
    >
      <Container maxWidth="lg">
        {/* Case Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Box display="flex" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={2}>
                <Box>
                  <Typography variant="h4" className="font-bold text-gray-900 mb-2">
                    {caseData.case_title}
                  </Typography>
                  <Box display="flex" gap={2} flexWrap="wrap" mb={2}>
                    <Chip label={`Case ID: ${caseData.case_id}`} size="small" />
                    <Chip label={`Patient ID: ${caseData.patient_id}`} size="small" />
                    <Chip
                      label={`Created: ${new Date(caseData.created_at).toLocaleString()}`}
                      size="small"
                    />
                  </Box>
                  <Box display="flex" gap={1} flexWrap="wrap">
                    {caseData.modality_tags.map((tag) => (
                      <Chip key={tag} label={tag} size="small" variant="outlined" />
                    ))}
                  </Box>
                </Box>
                <Button
                  variant="outlined"
                  startIcon={<ArrowBack />}
                  onClick={() => router.push('/upload')}
                  sx={{
                    borderRadius: 2,
                    textTransform: 'none',
                    borderColor: '#6366f1',
                    color: '#6366f1',
                  }}
                >
                  New Case
                </Button>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box display="flex" gap={1} flexWrap="wrap">
                <Typography variant="caption" className="text-gray-600">
                  <strong>Analyst:</strong> AI Model
                </Typography>
                <Typography variant="caption" className="text-gray-600">
                  <strong>Model Version:</strong> {caseData.model_version}
                </Typography>
                {caseData.model_checksums.length ? caseData.model_checksums.map((checksum, index) => (
                  <Typography key={checksum} variant="caption" className="text-gray-600">
                    <strong>{index === 0 ? 'Classifier' : 'Segmenter'} SHA-256:</strong>{' '}
                    {checksum.substring(0, 16)}…
                  </Typography>
                )) : (
                  <Typography variant="caption" className="text-gray-600">
                    <strong>Artifact provenance:</strong> unavailable for this legacy result
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </motion.div>

        {/* Diagnostic Summary */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-3" mb={2}>
                Diagnostic Summary
              </Typography>
              <Grid container spacing={3}>
                <Grid item xs={12} sm={4}>
                  <Paper
                    elevation={0}
                    sx={{
                      p: 2,
                      textAlign: 'center',
                      bgcolor: 'rgba(99, 102, 241, 0.05)',
                      borderRadius: 2,
                    }}
                  >
                    <Typography variant="h4" className="font-bold text-purple-600">
                      {results.filter((result) => result.scope === 'Patient classification').length}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Patient Classifications
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Paper
                    elevation={0}
                    sx={{
                      p: 2,
                      textAlign: 'center',
                      bgcolor: 'rgba(16, 185, 129, 0.05)',
                      borderRadius: 2,
                    }}
                  >
                    <Typography variant="h4" className="font-bold text-green-600">
                      {results.reduce((sum, result) => sum + (result.instanceCount || 0), 0)}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Segmented Instances
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Paper
                    elevation={0}
                    sx={{
                      p: 2,
                      textAlign: 'center',
                      bgcolor: 'rgba(245, 158, 11, 0.05)',
                      borderRadius: 2,
                    }}
                  >
                    <Typography variant="h4" className="font-bold text-amber-600">
                      {results.filter((result) => result.scope === 'Image segmentation').length}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Dental Classes Present
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>

              {/* Key Findings */}
              <Box mt={4}>
                <Typography variant="subtitle1" className="font-semibold text-gray-800 mb-2">
                  Key Findings:
                </Typography>
                <Box display="flex" flexDirection="column" gap={1}>
                  {results.length === 0 && (
                    <Alert severity="info">
                      The completed result contains no publishable model outputs. Review the raw provenance and rerun configuration.
                    </Alert>
                  )}
                  {results.map((result, index) => (
                    <Box
                      key={index}
                      display="flex"
                      alignItems="center"
                      gap={2}
                      sx={{
                        p: 1.5,
                        bgcolor: 'rgba(99, 102, 241, 0.03)',
                        borderRadius: 1,
                      }}
                    >
                      <Info sx={{ color: result.scope === 'Patient classification' ? '#6366f1' : '#0891b2' }} />
                      <Box flexGrow={1}>
                        <Typography variant="body2" className="font-medium text-gray-800">
                          {result.condition}
                        </Typography>
                        <Typography variant="caption" className="text-gray-500">
                          {result.description}
                        </Typography>
                      </Box>
                      <Chip
                        label={`Model score ${result.confidence}%`}
                        size="small"
                        sx={{
                          bgcolor: 'rgba(99, 102, 241, 0.1)',
                          color: '#6366f1',
                          fontWeight: 500,
                        }}
                      />
                      <Chip
                        label={result.scope}
                        size="small"
                        sx={{
                          bgcolor: result.scope === 'Patient classification' ? '#eef2ff' : '#ecfeff',
                          color: result.scope === 'Patient classification' ? '#4f46e5' : '#0e7490',
                          fontWeight: 500,
                        }}
                      />
                    </Box>
                  ))}
                </Box>
              </Box>
            </CardContent>
          </Card>
        </motion.div>

        {/* Evidence & Visuals */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-3" mb={2}>
                Evidence & Visuals
              </Typography>
              <Grid container spacing={2}>
                {(imageEvidence.length
                  ? imageEvidence.slice(0, 3)
                  : [{ imageId: -1, label: 'No image evidence', condition: 'Segmentation output unavailable', confidence: 0, detectionCount: 0, width: 1, height: 1, detections: [] }]
                ).map((ev, index) => (
                  <Grid item xs={12} sm={imageEvidence.length > 1 ? 6 : 12} key={index}>
                    <Paper
                      elevation={0}
                      sx={{
                        p: 2,
                        border: '1px solid #e5e7eb',
                        borderRadius: 2,
                      }}
                    >
                      <Box
                        sx={{
                          width: '100%',
                          height: 220,
                          bgcolor: '#0b0f19',
                          borderRadius: 1,
                          mb: 2,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          overflow: 'hidden',
                          position: 'relative',
                        }}
                      >
                        {evidenceImages[ev.imageId] ? (
                          <Box
                            component="img"
                            src={evidenceImages[ev.imageId]}
                            alt={ev.label}
                            sx={{ width: '100%', height: '100%', objectFit: 'contain' }}
                          />
                        ) : (
                          <PhotoCamera sx={{ fontSize: 48, color: '#6b7280' }} />
                        )}
                        {evidenceImages[ev.imageId] && ev.detections.some((detection) => Array.isArray(detection.polygon_normalized) && detection.polygon_normalized.length > 2) && (
                          <Box
                            component="svg"
                            viewBox={`0 0 ${ev.width} ${ev.height}`}
                            preserveAspectRatio="xMidYMid meet"
                            sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
                          >
                            {ev.detections.map((detection, detectionIndex) => {
                              const points = Array.isArray(detection.polygon_normalized)
                                ? detection.polygon_normalized
                                    .map((point: number[]) => `${point[0] * ev.width},${point[1] * ev.height}`)
                                    .join(' ')
                                : ''
                              if (!points) return null
                              const color = detectionColor(Number(detection.class_id) || 0)
                              return (
                                <polygon
                                  key={`${detection.class_id}-${detectionIndex}`}
                                  points={points}
                                  fill={color}
                                  fillOpacity="0.25"
                                  stroke={color}
                                  strokeWidth={Math.max(ev.width, ev.height) * 0.003}
                                >
                                  <title>{`${detection.label}: ${Math.round((Number(detection.confidence) || 0) * 100)}%`}</title>
                                </polygon>
                              )
                            })}
                          </Box>
                        )}
                      </Box>
                      <Typography variant="body2" className="font-medium text-gray-800 mb-1">
                        {ev.label || `Image ${index + 1}`}
                      </Typography>
                      <Typography variant="caption" className="text-gray-500">
                        {ev.condition}
                        {ev.detectionCount > 0 ? ` · highest model score ${ev.confidence}%` : ''}
                      </Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </motion.div>

        {/* Structured Output */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Box display="flex" alignItems="center" gap={1.5}>
                  <Typography variant="h5" className="font-semibold text-gray-800">
                    Structured Output
                  </Typography>
                  {!explanationLoading && explanation && (
                    <Chip
                      size="small"
                      label={explanationSource === 'openai' ? 'AI-generated' : 'Auto-generated'}
                      sx={{ bgcolor: 'rgba(99,102,241,0.1)', color: '#6366f1', fontWeight: 500 }}
                    />
                  )}
                </Box>
                <Tooltip title="Copy JSON">
                  <IconButton size="small" onClick={handleCopyJSON}>
                    <ContentCopy fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>

              {/* LLM narrative explanation of the findings */}
              {explanationLoading ? (
                <Box display="flex" alignItems="center" gap={1.5} sx={{ py: 2 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2" className="text-gray-500">
                    Generating clinical explanation…
                  </Typography>
                </Box>
              ) : explanation ? (
                <Paper elevation={0} sx={{ p: 3, bgcolor: '#f9fafb', borderRadius: 2, mb: 2 }}>
                  <Typography
                    variant="body1"
                    sx={{ color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}
                  >
                    {explanation}
                  </Typography>
                </Paper>
              ) : (
                <Typography variant="body2" className="text-gray-500" sx={{ mb: 2 }}>
                  Explanation unavailable for this case.
                </Typography>
              )}
              <Typography
                variant="caption"
                className="text-gray-400"
                sx={{ display: 'block', mb: 2 }}
              >
                AI-assisted decision support — review and validate before any clinical decision.
              </Typography>

              <Accordion expanded={jsonExpanded} onChange={() => setJsonExpanded(!jsonExpanded)}>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="body2" className="text-gray-600">
                    View raw JSON output
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Paper
                    elevation={0}
                    sx={{
                      p: 3,
                      bgcolor: '#1f2937',
                      borderRadius: 1,
                      overflow: 'auto',
                      maxHeight: 400,
                    }}
                  >
                    <pre style={{ color: '#f3f4f6', margin: 0, fontSize: '0.875rem' }}>
                      {JSON.stringify(rawResult, null, 2)}
                    </pre>
                  </Paper>
                </AccordionDetails>
              </Accordion>
            </CardContent>
          </Card>
        </motion.div>

        {/* Post-study actions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-1">
                Research review complete
              </Typography>
              <Typography variant="body2" className="text-gray-600" sx={{ mb: 2 }}>
                Your expert assessment and follow-up are saved. You can now use the
                diagnosis output or start a fresh analysis.
              </Typography>
              <Box display="flex" gap={2} flexWrap="wrap">
                <Button
                  variant="contained"
                  className="gradient-purple"
                  startIcon={<Science />}
                  onClick={() => router.push('/cases')}
                  sx={{
                    color: 'white',
                    textTransform: 'none',
                    borderRadius: 2,
                    px: 3,
                    py: 1.25,
                  }}
                >
                  Return to Cases
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Refresh />}
                  onClick={handleRerun}
                  sx={{
                    borderColor: '#6366f1',
                    color: '#6366f1',
                    textTransform: 'none',
                    borderRadius: 2,
                  }}
                >
                  Re-run Analysis
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<NoteAdd />}
                  onClick={() => setNoteDialogOpen(true)}
                  sx={{
                    borderColor: '#6366f1',
                    color: '#6366f1',
                    textTransform: 'none',
                    borderRadius: 2,
                  }}
                >
                  Add Note
                </Button>
              </Box>
            </CardContent>
          </Card>
        </motion.div>

        {/* Download Options */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <Card className="glass-effect">
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-3" mb={2}>
                Download Options
              </Typography>
              <Box display="flex" gap={2} flexWrap="wrap">
                <Button
                  variant="contained"
                  className="gradient-purple"
                  startIcon={<Download />}
                  onClick={handleDownloadPDF}
                  sx={{
                    color: 'white',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  Download PDF Summary
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Download />}
                  onClick={handleDownloadJSON}
                  sx={{
                    borderColor: '#6366f1',
                    color: '#6366f1',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  Download JSON
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<ContentCopy />}
                  onClick={handleCopyJSON}
                  sx={{
                    borderColor: '#6366f1',
                    color: '#6366f1',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  Copy for EMR
                </Button>
              </Box>
            </CardContent>
          </Card>
        </motion.div>
      </Container>

      {/* Add Note Dialog */}
      <Dialog open={noteDialogOpen} onClose={() => setNoteDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Clinical Note</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            multiline
            rows={6}
            value={clinicianNote}
            onChange={(e) => setClinicianNote(e.target.value)}
            placeholder="Enter your clinical notes or overrides..."
            sx={{ mt: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNoteDialogOpen(false)} sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button
            onClick={handleAddNote}
            variant="contained"
            className="gradient-purple"
            sx={{ textTransform: 'none', color: 'white' }}
          >
            Save Note
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default function ResultsPage() {
  return (
    <Suspense fallback={
      <Box className="min-h-screen flex items-center justify-center">
        <CircularProgress />
      </Box>
    }>
      <ResultsPageContent />
    </Suspense>
  )
}
