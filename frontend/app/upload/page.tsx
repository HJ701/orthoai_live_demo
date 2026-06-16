'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Container,
  Box,
  Grid,
} from '@mui/material'
import PageHeader from '@/components/PageHeader'
import CaseInformation from '@/components/CaseInformation'
import Uploader, { ImageFile } from '@/components/Uploader'
import ConsentCheckbox from '@/components/ConsentCheckbox'
import SubmitButton from '@/components/SubmitButton'

export default function UploadPage() {
  const router = useRouter()
  const [images, setImages] = useState<ImageFile[]>([])
  const [patientId, setPatientId] = useState('')
  const [caseTitle, setCaseTitle] = useState('')
  const [modalityTags, setModalityTags] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const [clinicLocation, setClinicLocation] = useState('')
  const [consentChecked, setConsentChecked] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    // Check authentication
    const authToken = sessionStorage.getItem('authToken')
    const termsAccepted = sessionStorage.getItem('termsAccepted')
    if (!authToken || !termsAccepted) {
      router.push('/signin')
    }
  }, [router])

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (images.length === 0) {
      newErrors.images = 'At least one image is required'
    }

    if (!consentChecked) {
      newErrors.consent = 'You must confirm consent and authority to upload'
    }

    // Validate file sizes (max 10MB per file)
    images.forEach((img, index) => {
      if (img.file.size > 10 * 1024 * 1024) {
        newErrors[`image_${index}`] = 'File size exceeds 10MB limit'
      }
    })

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async () => {
    if (!validateForm()) {
      return
    }

    setSubmitting(true)

    try {
      // Import API functions
      const { casesAPI, inferenceAPI } = await import('@/lib/api')

      // Step 1: Create case with all information
      const caseData: {
        consent_checked: boolean
        patient_id?: string
        title?: string
        clinic_location?: string
        tags?: string[]
        note?: string
      } = {
        consent_checked: consentChecked,
      }
      
      if (patientId.trim()) {
        caseData.patient_id = patientId.trim()
      }
      if (caseTitle.trim()) {
        caseData.title = caseTitle.trim()
      }
      if (clinicLocation.trim()) {
        caseData.clinic_location = clinicLocation.trim()
      }
      if (modalityTags.length > 0) {
        caseData.tags = modalityTags
      }
      if (notes.trim()) {
        caseData.note = notes.trim()
      }
      const caseResponse = await casesAPI.createCase(caseData)
      const caseId = caseResponse.id

      // Step 2: Upload images
      const imageFiles = images.map(img => img.file)
      await casesAPI.uploadImages(caseId, imageFiles)

      // Step 3: Store case metadata in sessionStorage for reference (backward compatibility)
      const storedCaseData = {
        case_id: caseId,
        patient_id: patientId.trim() || undefined,
        case_title: caseTitle.trim() || undefined,
        modality_tags: modalityTags,
        notes: notes.trim() || undefined,
        clinic_location: clinicLocation.trim() || undefined,
      }
      sessionStorage.setItem('currentCase', JSON.stringify(storedCaseData))
      sessionStorage.setItem('caseId', String(caseId))
      // Also store with case ID as key for easy lookup in cases list
      sessionStorage.setItem(`case_${caseId}`, JSON.stringify(storedCaseData))

      // Step 4: Start inference
      const inferenceResponse = await inferenceAPI.startInference(caseId)
      const jobId = inferenceResponse.job_id
      sessionStorage.setItem('jobId', String(jobId))

      // Navigate to inference page
      router.push(`/inference?case_id=${caseId}&job_id=${jobId}`)
    } catch (error: any) {
      setErrors({ submit: error.message || 'Failed to create case. Please try again.' })
      setSubmitting(false)
    }
  }

  return (
    <Box
      className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-pink-50"
      sx={{ py: { xs: 4, md: 6 }, px: { xs: 2, md: 0 } }}
    >
      <Container maxWidth="lg">
        <PageHeader
          title="Create Patient Case"
          description="Create a new case and upload clinical images for AI analysis"
        />

        <Grid container spacing={3} mt={0}>
          {/* Left Column - Case Details */}
          <Grid item xs={12} md={5}>
            <CaseInformation
              patientId={patientId}
              caseTitle={caseTitle}
              modalityTags={modalityTags}
              clinicLocation={clinicLocation}
              notes={notes}
              onPatientIdChange={setPatientId}
              onCaseTitleChange={setCaseTitle}
              onModalityTagsChange={setModalityTags}
              onClinicLocationChange={setClinicLocation}
              onNotesChange={setNotes}
            />
          </Grid>

          {/* Right Column - Image Upload */}
          <Grid item xs={12} md={7}>
            <Uploader
              images={images}
              errors={errors}
              submitting={submitting}
              onImagesChange={setImages}
              onModalityTagsChange={(tags) => {
                setModalityTags((prev) => {
                  const combined = new Set([...prev, ...tags])
                  return Array.from(combined)
                })
              }}
            />

            <ConsentCheckbox
              checked={consentChecked}
              error={errors.consent}
              onChange={setConsentChecked}
            />

            <SubmitButton
              submitting={submitting}
              disabled={images.length === 0}
              onSubmit={handleSubmit}
              error={errors.submit}
            />
          </Grid>
        </Grid>
      </Container>
    </Box>
  )
}

