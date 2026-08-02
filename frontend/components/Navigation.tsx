'use client'

import { useState } from 'react'
import type { ElementType } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Image from 'next/image'
import AppBar from '@mui/material/AppBar'
import Avatar from '@mui/material/Avatar'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Toolbar from '@mui/material/Toolbar'
import AccountCircle from '@mui/icons-material/AccountCircle'
import Folder from '@mui/icons-material/Folder'
import Logout from '@mui/icons-material/Logout'
import Science from '@mui/icons-material/Science'
import { Stethoscope } from 'lucide-react'
import HeaderLogo from './header.png'

// lucide Stethoscope sized to match the MUI nav icons (~20px) and inheriting
// the button's text color via currentColor.
const StethoscopeIcon = (props: { size?: number }) => (
  <Stethoscope size={props.size ?? 20} />
)

export default function Navigation() {
  const router = useRouter()
  const pathname = usePathname()
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  const handleAccountClick = () => {
    router.push('/account')
    handleMenuClose()
  }

  const handleLogout = () => {
    // Import and use clearAuthToken from API
    import('@/lib/api').then(({ clearAuthToken }) => {
      clearAuthToken()
      sessionStorage.clear()
      router.push('/signin')
      handleMenuClose()
    })
  }

  const navItems: Array<{ label: string; path: string; icon: ElementType }> = [
    { label: 'Diagnose a Case', path: '/upload', icon: StethoscopeIcon },
    { label: 'Research Mode', path: '/research', icon: Science },
    { label: 'Cases', path: '/cases', icon: Folder },
  ]

  const handleNavClick = (path: string) => {
    router.push(path)
  }

  // Don't show navigation on auth pages
  if (pathname?.startsWith('/signin') || pathname?.startsWith('/terms')) {
    return null
  }

  return (
    <AppBar
      position="static"
      elevation={0}
      sx={{
        bgcolor: 'white',
        borderBottom: '1px solid #e5e7eb',
        color: '#1f2937',
      }}
    >
      <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 4 } }}>
        <Box
          onClick={() => router.push('/upload')}
          sx={{
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            height: 40,
          }}
        >
          <Image
            src={HeaderLogo}
            alt="OrthoAI"
            width={120}
            height={40}
            style={{
              height: 'auto',
              width: 'auto',
              maxHeight: '40px',
            }}
            priority
          />
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive =
              item.path === '/upload'
                ? ['/upload', '/inference', '/results'].some((path) =>
                    pathname?.startsWith(path),
                  )
                : pathname?.startsWith(item.path)
            return (
              <Button
                key={item.path}
                startIcon={<Icon />}
                onClick={() => handleNavClick(item.path)}
                sx={{
                  color: isActive ? '#6366f1' : '#6b7280',
                  fontWeight: isActive ? 600 : 400,
                  textTransform: 'none',
                  '&:hover': {
                    bgcolor: 'rgba(99, 102, 241, 0.05)',
                  },
                }}
              >
                {item.label}
              </Button>
            )
          })}

          <IconButton onClick={handleMenuOpen} sx={{ ml: 1 }}>
            <Avatar sx={{ width: 32, height: 32, bgcolor: '#6366f1' }}>
              <AccountCircle />
            </Avatar>
          </IconButton>

          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
          >
            <MenuItem onClick={handleAccountClick}>
              <AccountCircle sx={{ mr: 2 }} />
              Account
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <Logout sx={{ mr: 2 }} />
              Sign Out
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  )
}
