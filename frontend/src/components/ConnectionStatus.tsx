import type { ConnectionState } from '../navigation'
import { RefreshIcon } from './icons'

export function StatusDot({ kind }: { kind: ConnectionState['kind'] }) {
  const color =
    kind === 'connected' ? 'bg-good' : kind === 'disconnected' ? 'bg-bad' : 'bg-warn'

  return (
    <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
      {kind === 'checking' && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warn opacity-60" />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  )
}

export function ConnectionPill({
  connection,
  compact = false,
}: {
  connection: ConnectionState
  compact?: boolean
}) {
  const label =
    connection.kind === 'checking'
      ? 'Checking'
      : connection.kind === 'connected'
        ? 'Connected'
        : 'Offline'

  const styles =
    connection.kind === 'connected'
      ? 'border-good/20 bg-good/[0.07] text-good'
      : connection.kind === 'disconnected'
        ? 'border-bad/20 bg-bad/[0.07] text-bad'
        : 'border-warn/20 bg-warn/[0.07] text-warn'

  return (
    <div
      role="status"
      aria-live="polite"
      title={
        connection.kind === 'disconnected' ? connection.message : 'MindVault API connection status'
      }
      className={`inline-flex items-center gap-2 rounded-full border font-medium ${styles} ${
        compact ? 'px-2.5 py-1.5 text-[11px]' : 'px-3.5 py-2 text-xs'
      }`}
    >
      <StatusDot kind={connection.kind} />
      {compact ? label : connection.kind === 'connected' ? 'Backend connected' : label}
    </div>
  )
}

export function ConnectionDetails({
  connection,
  onRetry,
}: {
  connection: ConnectionState
  onRetry: () => void
}) {
  return (
    <div className="surface-quiet p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="eyebrow">Connection status</p>
        <button
          type="button"
          onClick={onRetry}
          className="btn btn-ghost gap-1.5 px-2.5 py-1.5 text-xs"
        >
          <RefreshIcon className={`h-3.5 w-3.5 ${connection.kind === 'checking' ? 'animate-spin' : ''}`} />
          Retry
        </button>
      </div>

      <div className="mt-4 flex items-center gap-2 text-sm font-medium text-ink">
        <StatusDot kind={connection.kind} />
        {connection.kind === 'checking' && 'Contacting the API…'}
        {connection.kind === 'connected' && 'Connected to MindVault API'}
        {connection.kind === 'disconnected' && 'Unable to reach the MindVault API'}
      </div>

      {connection.kind === 'connected' ? (
        <dl className="mt-4 grid grid-cols-2 gap-2.5 text-sm">
          <div className="rounded-lg border border-line bg-panel/60 p-3">
            <dt className="text-[11px] text-faint">Application</dt>
            <dd className="mt-1 truncate font-medium text-ink">{connection.application}</dd>
          </div>
          <div className="rounded-lg border border-line bg-panel/60 p-3">
            <dt className="text-[11px] text-faint">Version</dt>
            <dd className="mt-1 truncate font-medium text-ink">{connection.version}</dd>
          </div>
          <div className="col-span-2 rounded-lg border border-line bg-panel/60 p-3">
            <dt className="text-[11px] text-faint">Health</dt>
            <dd className="mt-1 font-medium text-good">{connection.status}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-3 text-sm leading-6 text-muted">
          {connection.kind === 'checking'
            ? 'Waiting for GET /health to respond.'
            : `${connection.message} Start the backend and choose Retry.`}
        </p>
      )}
    </div>
  )
}
