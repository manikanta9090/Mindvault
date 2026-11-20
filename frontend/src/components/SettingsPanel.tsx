import { API_BASE_URL } from '../services/api'
import type { ConnectionState } from '../navigation'
import { ConnectionDetails } from './ConnectionStatus'
import { ExternalLinkIcon, LayersIcon } from './icons'

interface SettingsPanelProps {
  connection: ConnectionState
  onRetryConnection: () => void
}

export function SettingsPanel({ connection, onRetryConnection }: SettingsPanelProps) {
  return (
    <section className="space-y-5">
      <div>
        <p className="eyebrow">Workspace</p>
        <h2 className="mt-1.5 text-lg font-semibold tracking-tight text-ink">Settings</h2>
        <p className="mt-1 text-sm leading-6 text-muted">
          Connection details and configuration for this MindVault workspace.
        </p>
      </div>

      <ConnectionDetails connection={connection} onRetry={onRetryConnection} />

      <div className="surface p-5 sm:p-6">
        <h3 className="text-sm font-semibold text-ink">API configuration</h3>
        <dl className="mt-4 divide-y divide-line text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 py-3">
            <dt className="text-muted">API base URL</dt>
            <dd className="font-mono text-xs text-ink">{API_BASE_URL}</dd>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 py-3">
            <dt className="text-muted">Frontend override</dt>
            <dd className="font-mono text-xs text-ink">VITE_API_BASE_URL</dd>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 py-3">
            <dt className="text-muted">AI provider key</dt>
            <dd className="font-mono text-xs text-ink">GROQ_API_KEY · backend only</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs leading-5 text-faint">
          The Groq key is read by the FastAPI backend from its environment. It is never sent to or
          stored in the browser.
        </p>
      </div>

      <div className="surface p-5 sm:p-6">
        <div className="flex items-center gap-2.5">
          <LayersIcon className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold text-ink">How knowledge becomes searchable</h3>
        </div>
        <ol className="mt-4 space-y-3 text-sm leading-6 text-muted">
          <li className="flex gap-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line bg-sunken text-[10px] font-semibold text-accent">
              1
            </span>
            Capture a note or URL. The item is stored immediately.
          </li>
          <li className="flex gap-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line bg-sunken text-[10px] font-semibold text-accent">
              2
            </span>
            Indexing extracts chunks and prepares them for retrieval. Status appears on each card
            after a fresh capture.
          </li>
          <li className="flex gap-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line bg-sunken text-[10px] font-semibold text-accent">
              3
            </span>
            Questions return an answer with citations and the snippets that grounded it.
          </li>
        </ol>
        <p className="mt-4 rounded-lg border border-line bg-sunken px-3 py-2.5 text-xs leading-5 text-faint">
          GET /items does not expose indexing status, and there is no retry endpoint. Re-submitting
          an item creates a new record.
        </p>
      </div>

      <div className="surface p-5 sm:p-6">
        <h3 className="text-sm font-semibold text-ink">Resources</h3>
        <div className="mt-3 flex flex-wrap gap-3">
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary gap-2 px-3 py-2 text-xs"
          >
            API documentation
            <ExternalLinkIcon className="h-3.5 w-3.5" />
          </a>
          <a
            href={`${API_BASE_URL}/openapi.json`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary gap-2 px-3 py-2 text-xs"
          >
            OpenAPI schema
            <ExternalLinkIcon className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </section>
  )
}
