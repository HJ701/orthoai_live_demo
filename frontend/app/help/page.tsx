'use client'

import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Button,
} from '@mui/material'
import { ExpandMore, Email } from '@mui/icons-material'
import { Stethoscope } from 'lucide-react'
import { motion } from 'framer-motion'

const WORKFLOW_STEPS = [
  {
    title: 'Capture & upload the case',
    body: 'The dentist uploads the patient’s clinical images — intra-oral photos, OPG/panoramic, or cephalometric — under an anonymized Patient ID. No names or faces (PHI) are entered; consent is confirmed at upload.',
  },
  {
    title: 'AI analysis',
    body: 'OrthoAI runs its multimodal model and returns a malocclusion classification (e.g. Class I / II / III) with a confidence score and per-image evidence, typically in well under a minute.',
  },
  {
    title: 'Review the AI findings',
    body: 'On the Results page the dentist reviews the predicted class, confidence, and structured output, and can export a signed PDF or JSON for the patient record — always as decision support, never a standalone diagnosis.',
  },
  {
    title: 'Clinical validation',
    body: 'From the same case the dentist opens Clinical Validation and records their own assessment — manual class, DHC/IOTN, AC, and time taken — side by side with the AI output, then logs whether they agree or override, and how useful the AI was.',
  },
  {
    title: 'Governance & insight',
    body: 'Every action (upload, inference, validation) is written to the clinician’s audit log for traceability, while validation stats (class-agreement %, DHC delta, override rate) measure how the model performs in real clinics.',
  },
]

const FAQ_ITEMS = [
  {
    question: 'How do I upload images?',
    answer:
      'Navigate to the Upload page, fill in the patient case information, and either drag-and-drop images or click "Select Files" to browse. Supported formats include PNG, JPG, and DICOM files up to 10MB each.',
  },
  {
    question: 'What patient information should I include?',
    answer:
      'Use only Patient ID/code - never include patient names, faces, or other Protected Health Information (PHI). Ensure all images are properly anonymized before upload.',
  },
  {
    question: 'How long does analysis take?',
    answer:
      'Analysis typically takes 30-60 seconds depending on the number and size of images. You can monitor progress on the Inference page and navigate away safely - the process continues in the background.',
  },
  {
    question: 'Can I cancel an analysis?',
    answer:
      'Yes, you can cancel an analysis in progress using the "Cancel Analysis" button on the Inference page. Note that progress will be lost if cancelled.',
  },
  {
    question: 'How do I download results?',
    answer:
      'On the Results page, you can download a PDF summary, JSON file, or copy the results for your EMR system using the download options at the bottom of the page.',
  },
  {
    question: 'What does the confidence score mean?',
    answer:
      'Confidence scores indicate the AI model\'s certainty in its findings. Higher scores (80%+) indicate higher confidence, but all results should be reviewed by qualified clinicians.',
  },
  {
    question: 'Is this tool HIPAA/GDPR compliant?',
    answer:
      'Yes, the application complies with HIPAA and GDPR requirements. All data is encrypted at rest and in transit, and stored within the UAE/GCC region as per data residency requirements.',
  },
  {
    question: 'Can I share results with colleagues?',
    answer:
      'Yes, you can generate a secure, time-limited share link (expires in 7 days) using the "Share Secure Link" button on the Results page. Only share with authorized personnel.',
  },
]

export default function HelpPage() {
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
            className="font-bold text-gray-900 mb-2"
            sx={{ fontSize: { xs: '1.75rem', md: '2rem' } }}
          >
            Help & Support
          </Typography>
          <Typography variant="body1" className="text-gray-600 mb-6">
            Find answers to common questions and learn how to use the OrthoAI Diagnostic Assistant
          </Typography>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.08 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Box display="flex" alignItems="center" gap={1.5} mb={1}>
                <Box sx={{ color: '#6366f1', display: 'flex' }}>
                  <Stethoscope size={22} />
                </Box>
                <Typography variant="h5" className="font-semibold text-gray-800">
                  How OrthoAI fits your clinical workflow
                </Typography>
              </Box>
              <Typography variant="body2" className="text-gray-600" sx={{ mb: 3 }}>
                A dentist diagnoses a case end to end, with Clinical Validation woven in so
                the clinician’s judgement and the AI sit side by side on the same case.
              </Typography>
              <Box display="flex" flexDirection="column" gap={2}>
                {WORKFLOW_STEPS.map((step, i) => (
                  <Box key={step.title} display="flex" gap={2} alignItems="flex-start">
                    <Box
                      sx={{
                        flexShrink: 0,
                        width: 32,
                        height: 32,
                        borderRadius: '50%',
                        bgcolor: 'rgba(99,102,241,0.1)',
                        color: '#6366f1',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 700,
                        fontSize: '0.9rem',
                      }}
                    >
                      {i + 1}
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" className="font-semibold text-gray-800">
                        {step.title}
                      </Typography>
                      <Typography variant="body2" className="text-gray-600">
                        {step.body}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Card className="glass-effect" sx={{ mb: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-4">
                Frequently Asked Questions
              </Typography>
              {FAQ_ITEMS.map((item, index) => (
                <Accordion key={index} sx={{ mb: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="body1" className="font-medium text-gray-800">
                      {item.question}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" className="text-gray-600">
                      {item.answer}
                    </Typography>
                  </AccordionDetails>
                </Accordion>
              ))}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Card className="glass-effect">
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Typography variant="h5" className="font-semibold text-gray-800 mb-4">
                Privacy & Security
              </Typography>
              <Box display="flex" flexDirection="column" gap={2}>
                <Box>
                  <Typography variant="subtitle2" className="font-semibold text-gray-800 mb-1">
                    Data Residency
                  </Typography>
                  <Typography variant="body2" className="text-gray-600">
                    All data is processed and stored within the UAE/GCC region in compliance with
                    local data residency requirements.
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" className="font-semibold text-gray-800 mb-1">
                    Encryption
                  </Typography>
                  <Typography variant="body2" className="text-gray-600">
                    All data is encrypted at rest and in transit using industry-standard encryption
                    protocols.
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" className="font-semibold text-gray-800 mb-1">
                    Access Control
                  </Typography>
                  <Typography variant="body2" className="text-gray-600">
                    Access is restricted to authorized clinicians only. All actions are logged in
                    the audit trail.
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Box textAlign="center" mt={4}>
            <Typography variant="body2" className="text-gray-500 mb-2">
              Need additional support? Reach the OrthoAI team for demo access, workflow
              questions, or technical assistance.
            </Typography>
            <Button
              component="a"
              href="mailto:info@orthoai.co?subject=OrthoAI%20Demo%20Support"
              variant="contained"
              className="gradient-purple"
              startIcon={<Email />}
              sx={{
                color: 'white',
                textTransform: 'none',
                borderRadius: 2,
                px: 4,
                py: 1.25,
                mt: 1,
              }}
            >
              Contact Support
            </Button>
          </Box>
        </motion.div>
      </Container>
    </Box>
  )
}

