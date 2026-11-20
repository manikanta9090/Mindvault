import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description: string
  action?: ReactNode
  compact?: boolean
}

export function EmptyState({ icon, title, description, action, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-2xl border border-dashed border-line-strong/70 bg-sunken/40 px-6 text-center ${
        compact ? 'py-10' : 'py-16'
      }`}
    >
      {icon && (
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-raised text-faint">
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
