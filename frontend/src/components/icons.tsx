import type { ReactNode, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Base({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

export function VaultIcon(props: IconProps) {
  return (
    <Base {...props}>
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" />
      <circle cx="12" cy="12" r="2.8" />
      <path d="M12 9.2V7.5M12 16.5v-1.7M9.2 12H7.5m9 0h-1.7" />
    </Base>
  )
}

export function HomeIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m3.5 10 8.5-6.5 8.5 6.5" />
      <path d="M5.5 9.4V19a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V9.4" />
      <path d="M9.5 20.5v-6h5v6" />
    </Base>
  )
}

export function LibraryIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M5 4.5h11a1.5 1.5 0 0 1 1.5 1.5v13A1.5 1.5 0 0 1 16 20.5H5A1.5 1.5 0 0 1 3.5 19V6A1.5 1.5 0 0 1 5 4.5Z" />
      <path d="M7.5 8.5h7M7.5 12h7M7.5 15.5h4.5" />
      <path d="M19 7.5h1a1 1 0 0 1 1 1v10a2 2 0 0 1-2 2" />
    </Base>
  )
}

export function NoteIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M6 3.5h8.5L19 8v12a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 20V5a1.5 1.5 0 0 1 1-1.5Z" />
      <path d="M14 3.5V8h5" />
      <path d="M8.5 12h7M8.5 15.5h7M8.5 19h4" />
    </Base>
  )
}

export function GlobeIcon(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.6 12h16.8M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5Z" />
    </Base>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="10.8" cy="10.8" r="6.3" />
      <path d="m15.5 15.5 4.5 4.5" />
    </Base>
  )
}

export function SettingsIcon(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="2.8" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a1.9 1.9 0 1 1-2.69 2.69l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.56V21a1.9 1.9 0 1 1-3.8 0v-.09A1.7 1.7 0 0 0 9.1 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06a1.9 1.9 0 1 1-2.69-2.69l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3a1.9 1.9 0 1 1 0-3.8h.09A1.7 1.7 0 0 0 4.7 9.1a1.7 1.7 0 0 0-.34-1.87l-.06-.06a1.9 1.9 0 1 1 2.69-2.69l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3a1.9 1.9 0 1 1 3.8 0v.09a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a1.9 1.9 0 1 1 2.69 2.69l-.06.06A1.7 1.7 0 0 0 19.4 9c.13.6.69 1 1.3 1H21a1.9 1.9 0 1 1 0 3.8h-.09a1.7 1.7 0 0 0-1.51 1.2Z" />
    </Base>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M12 5v14M5 12h14" />
    </Base>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Base>
  )
}

export function MenuIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Base>
  )
}

export function SparkleIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M12 3.5 13.7 9l5.5 1.7-5.5 1.7L12 18l-1.7-5.6L4.8 10.7 10.3 9 12 3.5Z" />
      <path d="m18.8 16.3.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2Z" />
    </Base>
  )
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4.5 12h14M13 6.5l5.5 5.5-5.5 5.5" />
    </Base>
  )
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M13.5 5.5H19v5.5M19 5.5l-8.5 8.5" />
      <path d="M18 14.5v3.2a1.8 1.8 0 0 1-1.8 1.8H6.3a1.8 1.8 0 0 1-1.8-1.8V7.8a1.8 1.8 0 0 1 1.8-1.8h3.2" />
    </Base>
  )
}

export function RefreshIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M20 11.5a8 8 0 1 0-2.3 6.1" />
      <path d="M20 5v6.5h-6.5" />
    </Base>
  )
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m14.5 5-7 7 7 7" />
    </Base>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m9.5 5 7 7-7 7" />
    </Base>
  )
}

export function ClockIcon(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 1.8" />
    </Base>
  )
}

export function DatabaseIcon(props: IconProps) {
  return (
    <Base {...props}>
      <ellipse cx="12" cy="6" rx="7.5" ry="2.8" />
      <path d="M4.5 6v12c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8V6" />
      <path d="M4.5 12c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8" />
    </Base>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </Base>
  )
}

export function AlertIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M10.3 4.3 2.9 17.2A1.9 1.9 0 0 0 4.6 20h14.8a1.9 1.9 0 0 0 1.7-2.8L13.7 4.3a1.9 1.9 0 0 0-3.4 0Z" />
      <path d="M12 9v4.2M12 16.7h.01" />
    </Base>
  )
}

export function SendIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m20.5 3.5-8.8 17-2.4-7.3-7.3-2.4 18.5-7.3Z" />
      <path d="m9.3 13.2 4.2-4.2" />
    </Base>
  )
}

export function PanelRightIcon(props: IconProps) {
  return (
    <Base {...props}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M14.5 4.5v15" />
      <path d="m17.5 9-2 3 2 3" />
    </Base>
  )
}

export function QuoteIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M9.5 6.5H6A2.5 2.5 0 0 0 3.5 9v2.5A2.5 2.5 0 0 0 6 14h2v-.5c0 2.2-1 3.6-2.8 4.5" />
      <path d="M19.5 6.5H16a2.5 2.5 0 0 0-2.5 2.5v2.5A2.5 2.5 0 0 0 16 14h2v-.5c0 2.2-1 3.6-2.8 4.5" />
    </Base>
  )
}

export function LayersIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="m12 3.5 8.5 4.5L12 12.5 3.5 8 12 3.5Z" />
      <path d="m3.5 12 8.5 4.5L20.5 12" />
      <path d="m3.5 16 8.5 4.5L20.5 16" />
    </Base>
  )
}

export function InboxIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4 5.5h16l1.5 10v3a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5v-3L4 5.5Z" />
      <path d="M2.8 15.5h4.4l1.2 2h7.2l1.2-2h4.4" />
    </Base>
  )
}

export function FilterIcon(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4 6h16M7 12h10M10 18h4" />
    </Base>
  )
}
