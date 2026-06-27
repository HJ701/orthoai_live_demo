import type { Metadata } from 'next'

export const platformMetadata: Metadata = {
  icons: {
    icon: [
      { url: '/platform-favicon.ico' },
      { url: '/platform-favicon.svg', type: 'image/svg+xml' },
      { url: '/platform-favicon-16x16.png', sizes: '16x16', type: 'image/png' },
      { url: '/platform-favicon-32x32.png', sizes: '32x32', type: 'image/png' },
      { url: '/platform-favicon-48x48.png', sizes: '48x48', type: 'image/png' },
    ],
    apple: [
      { url: '/platform-apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  },
}
