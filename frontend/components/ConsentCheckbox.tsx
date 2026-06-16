'use client'

import {
  Card,
  CardContent,
  FormControlLabel,
  Checkbox,
  Typography,
  Box,
  Alert,
} from '@mui/material'

interface ConsentCheckboxProps {
  checked: boolean
  error?: string
  onChange: (checked: boolean) => void
}

export default function ConsentCheckbox({
  checked,
  error,
  onChange,
}: ConsentCheckboxProps) {
  return (
    <Card className="glass-effect" sx={{ mb: 3 }}>
      <CardContent sx={{ p: 3 }}>
        <FormControlLabel
          control={
            <Checkbox
              checked={checked}
              onChange={(e) => onChange(e.target.checked)}
              sx={{ color: '#6366f1' }}
            />
          }
          label={
            <Box>
              <Typography variant="body2" className="font-medium text-gray-800">
                I confirm I have consent and authority to upload these clinical images.
              </Typography>
              <Typography variant="caption" className="text-gray-500">
                No names/faces; anonymize overlays if needed. PHI reminder: Ensure all
                patient identifiers are removed.
              </Typography>
            </Box>
          }
        />
        {error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

