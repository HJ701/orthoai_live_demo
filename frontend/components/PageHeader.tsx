'use client'

import { Typography } from '@mui/material'
import { motion } from 'framer-motion'

interface PageHeaderProps {
  title: string
  description: string
}

export default function PageHeader({ title, description }: PageHeaderProps) {
  return (
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
        {title}
      </Typography>
      <Typography variant="body1" className="text-gray-600 mb-6">
        {description}
      </Typography>
    </motion.div>
  )
}

