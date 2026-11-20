import type { ReactNode } from 'react'

type Tone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'slate'

const TONE_STYLES: Record<Tone, string> = {
  emerald: 'border-good/25 bg-good/10 text-good',
  rose: 'border-bad/25 bg-bad/10 text-bad',
  amber: 'border-warn/25 bg-warn/10 text-warn',
  indigo: 'border-accent/25 bg-accent-wash text-accent',
  slate: 'border-line bg-white/[0.03] text-muted',
}

interface StatusBadgeProps {
  children: ReactNode
  tone?: Tone
  title?: string
  dot?: boolean
}

export function StatusBadge({ children, tone = 'slate', title, dot = false }: StatusBadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium leading-none ${TONE_STYLES[tone]}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  )
}
