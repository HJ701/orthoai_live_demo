import useSWRMutation from 'swr/mutation'
import { authAPI, Token, OTPResponse } from '@/lib/api'

// Fetcher function for OTP request
async function requestOTPFetcher(
  url: string,
  { arg }: { arg: { email: string } }
): Promise<OTPResponse> {
  return authAPI.requestOTP(arg.email)
}

// Fetcher function for login
async function loginFetcher(
  url: string,
  { arg }: { arg: { email: string; otp: string } }
): Promise<Token> {
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL
  
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email: arg.email, otp: arg.otp }),
  })

  // Explicitly check for status 200
  if (response.status !== 200) {
    const errorData = await response.json().catch(() => ({ 
      detail: `Login failed with status ${response.status}` 
    }))
    throw new Error(errorData.detail || `Login failed: ${response.statusText}`)
  }

  // Status is 200, proceed with login
  const token = await response.json()
  
  // Store token in sessionStorage
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('authToken', token.access_token)
  }
  
  return token
}

/**
 * Hook for requesting OTP
 */
export function useRequestOTP() {
  const { trigger, isMutating, error } = useSWRMutation(
    '/api/v1/auth/request-otp',
    requestOTPFetcher
  )

  return {
    requestOTP: trigger,
    isLoading: isMutating,
    error: error as Error | undefined,
  }
}

/**
 * Hook for login with OTP
 */
export function useLogin() {
  const { trigger, isMutating, error, data } = useSWRMutation(
    '/api/v1/auth/login',
    loginFetcher
  )

  return {
    login: trigger,
    isLoading: isMutating,
    error: error as Error | undefined,
    data,
  }
}

