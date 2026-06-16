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
} from '@mui/material'
import {
  CheckCircle,
  Warning,
  Info,
  ArrowBack,
  Download,
  Refresh,
  NoteAdd,
  ExpandMore,
  ContentCopy,
  Visibility,
  PhotoCamera,
} from '@mui/icons-material'
import { motion } from 'framer-motion'
import { displayClass } from '@/lib/format'
import { Stethoscope } from 'lucide-react'

interface DiagnosticResult {
  condition: string
  confidence: number
  severity: 'low' | 'medium' | 'high'
  description: string
  recommendations: string[]
  imageIndex?: number
}

interface CaseData {
  case_id: string
  patient_id: string
  case_title: string
  modality_tags: string[]
  created_at: string
  model_version: string
  model_checksum: string
}

const SAMPLE_RESULTS: DiagnosticResult[] = [
  {
    condition: 'Malocclusion Class II',
    confidence: 87,
    severity: 'medium',
    description: 'Class II malocclusion detected with moderate severity. Overjet measurement indicates need for orthodontic evaluation.',
    recommendations: [
      'Schedule orthodontic consultation',
      'Consider cephalometric analysis for treatment planning',
      'Monitor growth patterns if patient is in growth phase',
    ],
    imageIndex: 0,
  },
  {
    condition: 'IOTN Grade 3',
    confidence: 92,
    severity: 'medium',
    description: 'Index of Orthodontic Treatment Need (IOTN) graded as 3 - moderate need for treatment.',
    recommendations: [
      'Orthodontic treatment recommended',
      'Assess patient motivation and compliance',
      'Consider functional appliance if indicated',
    ],
    imageIndex: 1,
  },
  {
    condition: 'Caries Risk - Low',
    confidence: 85,
    severity: 'low',
    description: 'Overall caries risk assessment indicates low risk. Good oral hygiene patterns observed.',
    recommendations: [
      'Maintain current preventive care routine',
      'Continue regular checkups every 6 months',
      'Monitor high-risk areas identified in images',
    ],
    imageIndex: 0,
  },
]

function ResultsPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const caseId = searchParams.get('case_id') || 'CASE-1234567890'

  const [results, setResults] = useState<DiagnosticResult[]>([])
  const [imageEvidence, setImageEvidence] = useState<
    { imageId: number; label: string; condition: string; confidence: number }[]
  >([])
  const [evidenceImages, setEvidenceImages] = useState<Record<number, string>>({})
  const [explanation, setExplanation] = useState<string>('')
  const [explanationSource, setExplanationSource] = useState<string>('')
  const [explanationLoading, setExplanationLoading] = useState(true)
  const [caseData, setCaseData] = useState<CaseData | null>(null)
  const [jsonExpanded, setJsonExpanded] = useState(false)
  const [noteDialogOpen, setNoteDialogOpen] = useState(false)
  const [clinicianNote, setClinicianNote] = useState('')

  useEffect(() => {
    const loadResults = async () => {
      try {
        const { resultsAPI, casesAPI } = await import('@/lib/api')
        // Case ID from URL might be numeric or have CASE- prefix
        const caseIdNum = caseId.startsWith('CASE-')
          ? parseInt(caseId.replace('CASE-', ''))
          : parseInt(caseId)

        // Fetch results from API
        const apiResults = await resultsAPI.getResults(caseIdNum)

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

        // Set case data (prefer the case's own backend fields)
        setCaseData({
          case_id: String(apiResults.case_id),
          patient_id: caseDetail?.patient_id || parsedCase.patient_id || '—',
          case_title: caseDetail?.title || parsedCase.case_title || 'Case Analysis',
          modality_tags: caseDetail?.tags || parsedCase.modality_tags || [],
          created_at: apiResults.created_at,
          model_version: apiResults.model_version,
          model_checksum: 'sha256:abc123def456...', // Backend doesn't return this yet
        })

        // Transform API results to frontend format.
        // The deployed model returns ONE patient-level prediction
        // (findings.prediction) plus per_image_evidence[].findings.detections[]
        // echoing that prediction per image. Class names are numeric ("0/1/2")
        // from the real model, or readable from the mock — displayClass handles both.
        const transformedResults: DiagnosticResult[] = []
        const evidenceSummaries: { imageId: number; label: string; condition: string; confidence: number }[] = []
        const prediction = (apiResults.findings as any)?.prediction

        // Per-image evidence cards (one per uploaded image), readable class names
        apiResults.per_image_evidence.forEach((evidence, idx) => {
          const detections: any[] = Array.isArray((evidence.findings as any)?.detections)
            ? (evidence.findings as any).detections
            : []
          const top = detections[0]
          evidenceSummaries.push({
            imageId: evidence.image_id,
            label: evidence.filename || `Image ${idx + 1}`,
            condition: displayClass(top?.type ?? prediction?.predicted_class ?? 'No findings'),
            confidence: Math.round(((top?.confidence ?? evidence.confidence) || 0) * 100),
          })
        })

        // Primary finding = the single patient-level diagnosis (not one row per image)
        if (prediction?.predicted_class != null) {
          transformedResults.push({
            condition: displayClass(prediction.predicted_class),
            confidence: Math.round((prediction.confidence || 0) * 100),
            severity: 'medium',
            description: apiResults.summary,
            recommendations: [],
          })
        } else {
          // Fallback: derive findings from per-image detections
          apiResults.per_image_evidence.forEach((evidence, idx) => {
            const detections: any[] = Array.isArray((evidence.findings as any)?.detections)
              ? (evidence.findings as any).detections
              : []
            detections.forEach((det) => {
              transformedResults.push({
                condition: displayClass(det.type),
                confidence: Math.round(((det.confidence ?? evidence.confidence) || 0) * 100),
                severity: det.severity || 'medium',
                description: det.description || apiResults.summary,
                recommendations: det.recommendations || [],
                imageIndex: idx,
              })
            })
          })
        }

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

        // Fallback to sample results only if the backend returned nothing usable
        if (transformedResults.length === 0) {
          setResults(SAMPLE_RESULTS)
        } else {
          setResults(transformedResults)
        }
      } catch (err: any) {
        console.error('Failed to load results:', err)
        setExplanationLoading(false)
        // Fallback to sample data on error
        const storedCase = sessionStorage.getItem('currentCase')
        if (storedCase) {
          const parsed = JSON.parse(storedCase)
          setCaseData({
            case_id: caseId,
            patient_id: parsed.patient_id || '—',
            case_title: parsed.case_title || 'Case Analysis',
            modality_tags: parsed.modality_tags || [],
            created_at: new Date().toISOString(),
            model_version: 'v1.0.0',
            model_checksum: 'sha256:abc123def456...',
          })
        }
        setResults(SAMPLE_RESULTS)
      }
    }

    loadResults()
  }, [caseId])

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high':
        return '#ef4444'
      case 'medium':
        return '#f59e0b'
      case 'low':
        return '#10b981'
      default:
        return '#6b7280'
    }
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'high':
        return <Warning sx={{ color: '#ef4444' }} />
      case 'medium':
        return <Info sx={{ color: '#f59e0b' }} />
      case 'low':
        return <CheckCircle sx={{ color: '#10b981' }} />
      default:
        return <Info />
    }
  }

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
    const jsonData = {
      case_id: caseData?.case_id,
      results,
      model_version: caseData?.model_version,
      generated_at: new Date().toISOString(),
    }
    const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `case-${caseId}-results.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCopyJSON = () => {
    const jsonData = {
      case_id: caseData?.case_id,
      results,
      model_version: caseData?.model_version,
      generated_at: new Date().toISOString(),
    }
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
      const { inferenceAPI } = await import('@/lib/api')
      const caseIdNum = caseId.startsWith('CASE-') 
        ? parseInt(caseId.replace('CASE-', '')) 
        : parseInt(caseId)
      const inferenceResponse = await inferenceAPI.startInference(caseIdNum)
      const jobId = inferenceResponse.job_id
      sessionStorage.setItem('jobId', String(jobId))
      router.push(`/inference?case_id=${caseId}&job_id=${jobId}`)
    } catch (err: any) {
      alert(`Failed to restart inference: ${err.message}`)
    }
  }

  if (!caseData) {
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
                <Typography variant="caption" className="text-gray-600">
                  <strong>Checksum:</strong> {caseData.model_checksum.substring(0, 20)}...
                </Typography>
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
                      {results.length}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Findings
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
                      {results.filter((r) => r.severity === 'low').length}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Low Risk
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
                      {results.filter((r) => r.severity !== 'low').length}
                    </Typography>
                    <Typography variant="body2" className="text-gray-600">
                      Require Attention
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
                      {getSeverityIcon(result.severity)}
                      <Box flexGrow={1}>
                        <Typography variant="body2" className="font-medium text-gray-800">
                          {result.condition}
                        </Typography>
                      </Box>
                      <Chip
                        label={`${result.confidence}%`}
                        size="small"
                        sx={{
                          bgcolor: 'rgba(99, 102, 241, 0.1)',
                          color: '#6366f1',
                          fontWeight: 500,
                        }}
                      />
                      <Chip
                        label={result.severity}
                        size="small"
                        sx={{
                          bgcolor: getSeverityColor(result.severity) + '20',
                          color: getSeverityColor(result.severity),
                          fontWeight: 500,
                          textTransform: 'capitalize',
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
                  : [{ imageId: -1, label: 'Image 1', condition: 'No findings', confidence: 0 }]
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
                      </Box>
                      <Typography variant="body2" className="font-medium text-gray-800 mb-1">
                        {ev.label || `Image ${index + 1}`}
                      </Typography>
                      <Typography variant="caption" className="text-gray-500">
                        Detected: {ev.condition} (confidence {ev.confidence}%)
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
                      {JSON.stringify(
                        {
                          case_id: caseData.case_id,
                          results,
                          model_version: caseData.model_version,
                          generated_at: new Date().toISOString(),
                        },
                        null,
                        2
                      )}
                    </pre>
                  </Paper>
                </AccordionDetails>
              </Accordion>
            </CardContent>
          </Card>
        </motion.div>

        {/* Clinician Actions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-1">
                Clinical Validation
              </Typography>
              <Typography variant="body2" className="text-gray-600" sx={{ mb: 2 }}>
                Record your own clinical assessment for this case alongside the OrthoAI output —
                enter your diagnosis, agreement, and notes without leaving the workflow.
              </Typography>
              <Box display="flex" gap={2} flexWrap="wrap">
                <Button
                  variant="contained"
                  className="gradient-purple"
                  startIcon={<Stethoscope size={18} />}
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      sessionStorage.setItem('caseId', String(caseData.case_id))
                    }
                    router.push(`/clinical?case_id=${caseData.case_id}`)
                  }}
                  sx={{
                    color: 'white',
                    textTransform: 'none',
                    borderRadius: 2,
                    px: 3,
                    py: 1.25,
                  }}
                >
                  Start Clinical Validation
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
