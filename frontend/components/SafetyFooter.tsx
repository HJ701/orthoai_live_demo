'use client'

import { Box, Typography, Link } from '@mui/material'

export default function SafetyFooter() {
  return (
    <Box
      component="footer"
      sx={{
        mt: 'auto',
        py: 3,
        px: 2,
        bgcolor: '#f9fafb',
        borderTop: '1px solid #e5e7eb',
      }}
    >
      <Box sx={{ maxWidth: '1200px', mx: 'auto' }}>
        <Typography
          variant="caption"
          sx={{
            display: 'block',
            color: '#6b7280',
            textAlign: 'center',
            mb: 1,
            fontWeight: 500,
          }}
        >
          ⚠️ For decision support only; not a standalone diagnostic tool.
        </Typography>
        <Typography
          variant="caption"
          sx={{
            display: 'block',
            color: '#9ca3af',
            textAlign: 'center',
            fontSize: '0.75rem',
          }}
        >
          Model version: v1.0.0 | Data residency: UAE/GCC |{' '}
          <Link href="/help" sx={{ color: '#6366f1', textDecoration: 'none' }}>
            Privacy Policy
          </Link>
        </Typography>
      </Box>
    </Box>
  )
}

