'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function HomePage() {
  const router = useRouter()

  useEffect(() => {
    // Check if user is authenticated
    const authToken = sessionStorage.getItem('authToken')
    const termsAccepted = sessionStorage.getItem('termsAccepted')
    
    if (authToken && termsAccepted) {
      router.push('/upload')
    } else {
      router.push('/signin')
    }
  }, [router])

  return null
}
