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
  return authAPI.login(arg.email, arg.otp)
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
