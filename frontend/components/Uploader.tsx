'use client'

import { useState } from 'react'
import {
  Card,
  CardContent,
  Typography,
  Button,
  Box,
  Paper,
  FormControl,
  Select,
  MenuItem,
  Alert,
} from '@mui/material'
import {
  CloudUpload,
  Delete,
  Add,
} from '@mui/icons-material'

export interface ImageFile {
  file: File
  modality: string
  preview: string
}

const MODALITY_OPTIONS = [
  'RGB Intra-oral',
  'OPG (Panoramic)',
  'Cephalometric',
  'CBCT',
  'Other',
]

interface UploaderProps {
  images: ImageFile[]
  errors: Record<string, string>
  submitting: boolean
  onImagesChange: (images: ImageFile[]) => void
  onModalityTagsChange: (tags: string[]) => void
}

export default function Uploader({
  images,
  errors,
  submitting,
  onImagesChange,
  onModalityTagsChange,
}: UploaderProps) {
  const [dragActive, setDragActive] = useState(false)

  const detectModality = (fileName: string): string => {
    const lower = fileName.toLowerCase()
    if (lower.includes('opg') || lower.includes('panoramic')) return 'OPG (Panoramic)'
    if (lower.includes('ceph') || lower.includes('cephalometric')) return 'Cephalometric'
    if (lower.includes('cbct')) return 'CBCT'
    return 'RGB Intra-oral'
  }

  const handleFiles = (files: File[]) => {
    const imageFiles = files.filter(
      (file) => file.type.startsWith('image/') || file.name.toLowerCase().endsWith('.dcm')
    )

    const newImages: ImageFile[] = imageFiles.map((file) => ({
      file,
      modality: detectModality(file.name),
      preview: URL.createObjectURL(file),
    }))

    const updatedImages = [...images, ...newImages]
    onImagesChange(updatedImages)
    
    // Auto-add detected modalities to tags
    const detectedModalities = new Set(newImages.map(img => img.modality))
    onModalityTagsChange(Array.from(detectedModalities))
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(Array.from(e.target.files))
    }
  }

  const removeImage = (index: number) => {
    const image = images[index]
    URL.revokeObjectURL(image.preview)
    const updatedImages = images.filter((_, i) => i !== index)
    onImagesChange(updatedImages)
  }

  const updateImageModality = (index: number, modality: string) => {
    const updatedImages = images.map((img, i) => (i === index ? { ...img, modality } : img))
    onImagesChange(updatedImages)
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(Array.from(e.dataTransfer.files))
    }
  }
  return (
    <>
      <Card
        className="glass-effect"
        sx={{
          mb: 3,
          border: dragActive ? '2px dashed #6366f1' : '2px dashed transparent',
          transition: 'all 0.3s ease',
        }}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <CardContent sx={{ p: 3 }}>
          <Typography variant="h6" className="font-semibold text-gray-800 mb-3">
            Add Images
          </Typography>

          {images.length === 0 ? (
            <Box
              display="flex"
              flexDirection="column"
              alignItems="center"
              justifyContent="center"
              sx={{ minHeight: '200px', py: 4 }}
            >
              <CloudUpload sx={{ fontSize: 64, color: '#6366f1', mb: 2 }} />
              <Typography variant="body1" className="text-gray-600 mb-2">
                Drop images here to begin
              </Typography>
              <Typography variant="body2" className="text-gray-500" mb={3}>
                or click to browse
              </Typography>
              <input
                accept="image/*,.dcm"
                style={{ display: 'none' }}
                id="file-upload"
                type="file"
                multiple
                onChange={handleFileInput}
              />
              <label htmlFor="file-upload">
                <Button
                  variant="contained"
                  component="span"
                  className="gradient-purple"
                  sx={{
                    color: 'white',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    textTransform: 'none',
                  }}
                >
                  Select Files
                </Button>
              </label>
              <Typography variant="caption" className="text-gray-500" mt={2}>
                Supported: PNG, JPG, DICOM | Max 10MB per file
              </Typography>
            </Box>
          ) : (
            <Box>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="body2" className="text-gray-600">
                  {images.length} file{images.length !== 1 ? 's' : ''} selected
                </Typography>
                <input
                  accept="image/*,.dcm"
                  style={{ display: 'none' }}
                  id="file-upload-add"
                  type="file"
                  multiple
                  onChange={handleFileInput}
                />
                <label htmlFor="file-upload-add">
                  <Button
                    size="small"
                    component="span"
                    startIcon={<Add />}
                    sx={{ textTransform: 'none' }}
                  >
                    Add More
                  </Button>
                </label>
              </Box>

              {errors.images && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {errors.images}
                </Alert>
              )}

              <Box display="flex" flexDirection="column" gap={2}>
                {images.map((image, index) => (
                  <Paper
                    key={index}
                    elevation={0}
                    sx={{
                      p: 2,
                      bgcolor: 'rgba(99, 102, 241, 0.05)',
                      borderRadius: 2,
                    }}
                  >
                    <Box display="flex" gap={2}>
                      <Box
                        component="img"
                        src={image.preview}
                        alt={image.file.name}
                        sx={{
                          width: 80,
                          height: 80,
                          objectFit: 'cover',
                          borderRadius: 1,
                        }}
                      />
                      <Box flexGrow={1}>
                        <Typography variant="body2" className="font-medium text-gray-800">
                          {image.file.name}
                        </Typography>
                        <Typography variant="caption" className="text-gray-500">
                          {(image.file.size / 1024 / 1024).toFixed(2)} MB
                        </Typography>
                        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
                          <Select
                            value={image.modality}
                            onChange={(e) => updateImageModality(index, e.target.value)}
                          >
                            {MODALITY_OPTIONS.map((option) => (
                              <MenuItem key={option} value={option}>
                                {option}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Box>
                      <Button
                        size="small"
                        onClick={() => removeImage(index)}
                        sx={{ color: '#ef4444', minWidth: 'auto' }}
                      >
                        <Delete />
                      </Button>
                    </Box>
                    {errors[`image_${index}`] && (
                      <Alert severity="error" sx={{ mt: 1 }}>
                        {errors[`image_${index}`]}
                      </Alert>
                    )}
                  </Paper>
                ))}
              </Box>
            </Box>
          )}
        </CardContent>
      </Card>
    </>
  )
}

