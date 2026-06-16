'use client'

import { Box, Button, Alert } from '@mui/material'

interface SubmitButtonProps {
  submitting: boolean
  disabled?: boolean
  onSubmit: () => void
  error?: string
  submitLabel?: string
  submittingLabel?: string
}

export default function SubmitButton({
  submitting,
  disabled = false,
  onSubmit,
  error,
  submitLabel = 'Run Analysis',
  submittingLabel = 'Creating Case...',
}: SubmitButtonProps) {
  return (
    <>
      <Box display="flex" justifyContent="flex-end">
        <Button
          variant="contained"
          className="gradient-purple"
          onClick={onSubmit}
          disabled={submitting || disabled}
          sx={{
            color: 'white',
            px: 6,
            py: 1.5,
            borderRadius: 2,
            fontSize: '1rem',
            textTransform: 'none',
          }}
        >
          {submitting ? submittingLabel : submitLabel}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </>
  )
}

