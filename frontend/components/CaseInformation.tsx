'use client'

import {
  Card,
  CardContent,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Typography,
  Box,
} from '@mui/material'

const MODALITY_OPTIONS = [
  'RGB Intra-oral',
  'OPG (Panoramic)',
  'Cephalometric',
  'CBCT',
  'Other',
]

interface CaseInformationProps {
  patientId: string
  caseTitle: string
  modalityTags: string[]
  clinicLocation: string
  notes: string
  onPatientIdChange: (value: string) => void
  onCaseTitleChange: (value: string) => void
  onModalityTagsChange: (value: string[]) => void
  onClinicLocationChange: (value: string) => void
  onNotesChange: (value: string) => void
}

export default function CaseInformation({
  patientId,
  caseTitle,
  modalityTags,
  clinicLocation,
  notes,
  onPatientIdChange,
  onCaseTitleChange,
  onModalityTagsChange,
  onClinicLocationChange,
  onNotesChange,
}: CaseInformationProps) {
  return (
    <Card className="glass-effect" sx={{ mb: 3 }}>
      <CardContent sx={{ p: 3 }}>
        <Typography mb={1} variant="h6" className="font-semibold text-gray-800 mb-3">
          Case Information
        </Typography>

        <TextField
          fullWidth
          label="Patient ID/Code (Optional)"
          value={patientId}
          onChange={(e) => onPatientIdChange(e.target.value)}
          placeholder="PT-2024-001"
          helperText="No PHI names - use ID/code only"
          sx={{ mb: 3 }}
        />

        <TextField
          fullWidth
          label="Case Title (Optional)"
          value={caseTitle}
          onChange={(e) => onCaseTitleChange(e.target.value)}
          placeholder="e.g., Routine Checkup"
          sx={{ mb: 3 }}
        />

        <FormControl fullWidth sx={{ mb: 3 }}>
          <InputLabel>Modality Tags (Optional)</InputLabel>
          <Select
            multiple
            value={modalityTags}
            onChange={(e) => onModalityTagsChange(e.target.value as string[])}
            renderValue={(selected) => (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {(selected as string[]).map((value) => (
                  <Chip key={value} label={value} size="small" />
                ))}
              </Box>
            )}
          >
            {MODALITY_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {option}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <TextField
          fullWidth
          label="Clinic Location (Optional)"
          value={clinicLocation}
          onChange={(e) => onClinicLocationChange(e.target.value)}
          placeholder="e.g., Dubai Clinic"
          sx={{ mb: 3 }}
        />

        <TextField
          fullWidth
          multiline
          rows={4}
          label="Notes (Optional)"
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Additional clinical notes..."
          sx={{ mb: 3 }}
        />
      </CardContent>
    </Card>
  )
}

