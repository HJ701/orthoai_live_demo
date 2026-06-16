# OrthoAI Frontend — Dental Diagnostic Assistant

A modern, AI-powered dental diagnostic tool built with Next.js, Material UI, and Tailwind CSS. Upload intra-oral photos or X-rays for AI-powered analysis and receive detailed diagnostic results.

This is the canonical frontend for the OrthoAI demo. It talks to the FastAPI backend in this same repository (the `app/` package) over `/api/v1/*`. It is a static export (`output: 'export'`) deployed to S3 + CloudFront by `.github/workflows/deploy-frontend.yml`.

## Features

- **Landing/Upload Page**: Drag-and-drop interface for uploading dental images
- **Inference & Progress Page**: Real-time progress tracking with animated feedback
- **Results Page**: Comprehensive diagnostic summary with recommendations

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **UI Library**: Material UI (MUI)
- **Styling**: Tailwind CSS
- **Animations**: Framer Motion
- **Language**: TypeScript

## Getting Started

### Prerequisites

- Node.js 18+
- npm
- The OrthoAI FastAPI backend running locally (from the repo root: `uvicorn app.main:app --reload --port 8000`)

### Installation

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
Copy `.env.example` to `.env.local` (already points at the local backend):
```bash
cp .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

### Backend Integration

This frontend is integrated with the OrthoAI FastAPI backend in this repository (the `app/` package, served on `http://127.0.0.1:8000` in local dev). The API client is located in `lib/api.ts` and handles:

- **Authentication**: OTP-based login (`/api/v1/auth/request-otp`, `/api/v1/auth/login`)
- **Cases**: Create cases and upload images (`/api/v1/cases`)
- **Inference**: Start inference jobs and poll status (`/api/v1/inference`)
- **Results**: Fetch results and download PDFs (`/api/v1/cases/{id}/results`)

All API calls include JWT authentication tokens stored in sessionStorage.

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout with theme provider
│   ├── page.tsx            # Home page (redirects)
│   ├── signin/             # OTP authentication
│   ├── terms/              # Terms acceptance
│   ├── upload/             # Case creation and image upload
│   ├── inference/          # Inference progress tracking
│   ├── results/            # Results display
│   ├── cases/              # Cases list
│   └── globals.css         # Global styles and Tailwind
├── components/
│   ├── ThemeProvider.tsx   # MUI theme configuration
│   ├── Navigation.tsx     # App navigation
│   └── SafetyFooter.tsx   # Safety disclaimer footer
├── lib/
│   └── api.ts             # API client with authentication
└── package.json
```

## Pages

### 1. Landing/Upload Page (`/`)
- Drag-and-drop file upload
- File selection with preview
- Support for multiple image files
- Clean, modern UI with gradient backgrounds

### 2. Inference & Progress Page (`/inference`)
- Animated progress indicator
- Step-by-step status updates
- Real-time progress feedback
- Smooth transitions to results

### 3. Results Page (`/results`)
- Diagnostic summary cards
- Condition details with confidence scores
- Severity indicators
- Recommendations for each condition
- Download report functionality

## Design Features

- **Modern UI**: Clean, minimalist design with soft gradients
- **Responsive**: Mobile-first design that works on all devices
- **Animations**: Smooth transitions and loading states
- **Glass Effects**: Frosted glass card effects for depth
- **Color Palette**: Purple, blue, and pink gradients inspired by modern design trends

## Customization

### Colors
Edit `tailwind.config.js` to customize the color palette:
```js
colors: {
  primary: {
    // Your custom colors
  }
}
```

### Theme
Modify `components/ThemeProvider.tsx` to adjust Material UI theme settings.

## Build for Production

```bash
npm run build
npm start
```

## License

MIT

