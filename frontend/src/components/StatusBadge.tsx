import type { ReactNode } from 'react'

type Tone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'slate'

const TONE_STYLES: Record<Tone, string> = {
  emerald: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
  rose: 'border-rose-400/25 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-300/25 bg-amber-300/10 text-amber-100',
  indigo: 'border-indigo-400/25 bg-indigo-400/10 text-indigo-200',
  slate: 'border-white/10 bg-white/5 text-slate-300',
}

interface StatusBadgeProps {
  children: ReactNode
  tone?: Tone
  title?: string
}

export function StatusBadge({ children, tone = 'slate', title }: StatusBadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${TONE_STYLES[tone]}`}
    >
      {children}
    </span>
  )
}
