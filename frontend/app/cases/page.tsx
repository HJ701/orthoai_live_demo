'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Container,
  Box,
  Typography,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  TextField,
  InputAdornment,
  CircularProgress,
} from '@mui/material'
import {
  Visibility,
  Search,
} from '@mui/icons-material'
import { motion } from 'framer-motion'
import { casesAPI, CaseResponse } from '@/lib/api'

interface Case {
  case_id: string
  patient_id: string
  case_title: string
  created_at: string
  status: 'completed' | 'processing' | 'failed'
  last_viewed: string
}

const SAMPLE_CASES: Case[] = [
  {
    case_id: 'CASE-1234567890',
    patient_id: 'PT-2024-001',
    case_title: 'Routine Checkup',
    created_at: '2024-01-15T10:30:00Z',
    status: 'completed',
    last_viewed: '2024-01-15T11:00:00Z',
  },
  {
    case_id: 'CASE-1234567891',
    patient_id: 'PT-2024-002',
    case_title: 'Orthodontic Evaluation',
    created_at: '2024-01-14T14:20:00Z',
    status: 'completed',
    last_viewed: '2024-01-14T15:00:00Z',
  },
  {
    case_id: 'CASE-1234567892',
    patient_id: 'PT-2024-003',
    case_title: 'Pre-treatment Assessment',
    created_at: '2024-01-13T09:15:00Z',
    status: 'processing',
    last_viewed: '2024-01-13T09:15:00Z',
  },
]

export default function CasesPage() {
  const router = useRouter()
  const [cases, setCases] = useState<Case[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadCases = async () => {
      try {
        const apiCases = await casesAPI.listCases()
        
        // Transform backend cases to frontend format
        const transformedCases: Case[] = apiCases.map((apiCase: CaseResponse) => {
          // Use backend fields directly, with sessionStorage as fallback for backward compatibility
          let patientId = apiCase.patient_id
          let caseTitle = apiCase.title
          
          // Fallback to sessionStorage if backend fields are missing (for old cases)
          if (!patientId || !caseTitle) {
            const storedCaseKey = `case_${apiCase.id}`
            const storedCase = sessionStorage.getItem(storedCaseKey) || sessionStorage.getItem('currentCase')
            if (storedCase) {
              try {
                const caseMetadata = JSON.parse(storedCase)
                if (caseMetadata.case_id === String(apiCase.id)) {
                  patientId = patientId || caseMetadata.patient_id || `PT-${apiCase.id}`
                  caseTitle = caseTitle || caseMetadata.case_title || `Case ${apiCase.id}`
                }
              } catch (e) {
                // Ignore parse errors
              }
            }
          }
          
          // Map backend status to frontend status format
          // Backend returns: 'queued' | 'running' | 'done' | 'error'
          // Frontend expects: 'completed' | 'processing' | 'failed'
          let status: 'completed' | 'processing' | 'failed' = 'completed'
          if (apiCase.status) {
            switch (apiCase.status) {
              case 'done':
                status = 'completed'
                break
              case 'queued':
              case 'running':
                status = 'processing'
                break
              case 'error':
                status = 'failed'
                break
              default:
                status = 'completed'
            }
          }
          
          return {
            case_id: String(apiCase.id),
            patient_id: patientId || `PT-${apiCase.id}`,
            case_title: caseTitle || `Case ${apiCase.id}`,
            created_at: apiCase.created_at,
            status,
            last_viewed: apiCase.created_at, // Use created_at as last_viewed for now
          }
        })
        
        setCases(transformedCases)
      } catch (err: any) {
        console.error('Failed to load cases:', err)
        // On error, show empty state
        setCases([])
      } finally {
        setLoading(false)
      }
    }

    loadCases()
  }, [])

  const filteredCases = cases.filter(
    (caseItem) =>
      caseItem.case_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      caseItem.patient_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      caseItem.case_title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'processing':
        return 'warning'
      case 'failed':
        return 'error'
      default:
        return 'default'
    }
  }

  const handleViewCase = (caseId: string) => {
    router.push(`/results?case_id=${caseId}`)
  }

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
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={4} flexWrap="wrap" gap={2}>
            <Typography
              variant="h4"
              className="font-bold text-gray-900"
              sx={{ fontSize: { xs: '1.75rem', md: '2rem' } }}
            >
              Cases
            </Typography>
            <TextField
              placeholder="Search cases..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              size="small"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: { xs: '100%', sm: 300 } }}
            />
          </Box>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Card className="glass-effect">
            <CardContent sx={{ p: 0 }}>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#f9fafb' }}>
                      <TableCell className="font-semibold">Case ID</TableCell>
                      <TableCell className="font-semibold">Patient ID</TableCell>
                      <TableCell className="font-semibold">Case Title</TableCell>
                      <TableCell className="font-semibold">Created</TableCell>
                      <TableCell className="font-semibold">Status</TableCell>
                      <TableCell className="font-semibold">Last Viewed</TableCell>
                      <TableCell className="font-semibold" align="right">
                        Actions
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                          <CircularProgress size={40} />
                        </TableCell>
                      </TableRow>
                    ) : filteredCases.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                          <Typography variant="body2" className="text-gray-500">
                            {searchQuery ? 'No cases match your search' : 'No cases found'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredCases.map((caseItem) => (
                        <TableRow
                          key={caseItem.case_id}
                          sx={{
                            '&:hover': {
                              bgcolor: 'rgba(99, 102, 241, 0.03)',
                              cursor: 'pointer',
                            },
                          }}
                        >
                          <TableCell>{caseItem.case_id}</TableCell>
                          <TableCell>{caseItem.patient_id}</TableCell>
                          <TableCell>{caseItem.case_title}</TableCell>
                          <TableCell>
                            {new Date(caseItem.created_at).toLocaleDateString()}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={caseItem.status}
                              color={getStatusColor(caseItem.status) as any}
                              size="small"
                              sx={{ textTransform: 'capitalize' }}
                            />
                          </TableCell>
                          <TableCell>
                            {new Date(caseItem.last_viewed).toLocaleDateString()}
                          </TableCell>
                          <TableCell align="right">
                            <IconButton
                              size="small"
                              onClick={() => handleViewCase(caseItem.case_id)}
                              sx={{ color: '#6366f1' }}
                            >
                              <Visibility />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </motion.div>
      </Container>
    </Box>
  )
}

