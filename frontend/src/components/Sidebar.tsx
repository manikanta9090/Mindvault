import type { ConnectionState, ViewId } from '../navigation'
import { NAV_ITEMS } from '../navigation'
import { ConnectionPill } from './ConnectionStatus'
import { CloseIcon, GlobeIcon, HomeIcon, LibraryIcon, NoteIcon, PlusIcon, SearchIcon, SettingsIcon, VaultIcon } from './icons'

interface SidebarProps {
  view: ViewId
  onViewChange: (view: ViewId) => void
  onAddKnowledge: () => void
  connection: ConnectionState
  itemCount: number | null
  onClose?: () => void
}

function NavGlyph({ id }: { id: ViewId }) {
  const className = 'h-[18px] w-[18px]'
  switch (id) {
    case 'home':
      return <HomeIcon className={className} />
    case 'all':
      return <LibraryIcon className={className} />
    case 'notes':
      return <NoteIcon className={className} />
    case 'urls':
      return <GlobeIcon className={className} />
    case 'search':
      return <SearchIcon className={className} />
    case 'settings':
      return <SettingsIcon className={className} />
  }
}

export function Sidebar({
  view,
  onViewChange,
  onAddKnowledge,
  connection,
  itemCount,
  onClose,
}: SidebarProps) {
  const workspaceItems = NAV_ITEMS.slice(0, 4)
  const toolItems = NAV_ITEMS.slice(4)

  function renderNavItem(item: (typeof NAV_ITEMS)[number]) {
    const active = view === item.id
    return (
      <li key={item.id}>
        <button
          type="button"
          onClick={() => onViewChange(item.id)}
          aria-current={active ? 'page' : undefined}
          title={item.hint}
          className={`relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
            active
              ? 'bg-accent-wash font-medium text-ink'
              : 'text-muted hover:bg-white/[0.04] hover:text-ink'
          }`}
        >
          {active && (
            <span
              className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-accent"
              aria-hidden="true"
            />
          )}
          <span className={active ? 'text-accent' : 'text-faint'}>
            <NavGlyph id={item.id} />
          </span>
          <span className="truncate">{item.label}</span>
        </button>
      </li>
    )
  }

  return (
    <div className="scroll-slim flex h-full flex-col overflow-y-auto px-3 py-5">
      <div className="flex items-center justify-between gap-2 px-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-accent/25 bg-accent-wash text-accent">
            <VaultIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-tight text-ink">MindVault</p>
            <p className="truncate text-[11px] text-faint">Your knowledge layer</p>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="btn btn-ghost h-8 w-8 shrink-0 p-0 xl:hidden"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onAddKnowledge}
        className="btn btn-primary mt-7 w-full justify-start px-3.5"
      >
        <PlusIcon className="h-4 w-4" />
        Add knowledge
      </button>

      <nav className="mt-7 flex-1" aria-label="Main navigation">
        <p className="eyebrow px-3">Workspace</p>
        <ul className="mt-3 space-y-1">{workspaceItems.map(renderNavItem)}</ul>

        <p className="eyebrow mt-7 px-3">Tools</p>
        <ul className="mt-3 space-y-1">{toolItems.map(renderNavItem)}</ul>
      </nav>

      <div className="mt-8 space-y-3 border-t border-line pt-4">
        <ConnectionPill connection={connection} compact />
        <p className="px-1 text-[11px] leading-5 text-faint">
          {itemCount === null
            ? 'Loading vault…'
            : itemCount === 0
              ? 'Your vault is empty'
              : `${itemCount} item${itemCount === 1 ? '' : 's'} in your vault`}
        </p>
      </div>
    </div>
  )
}
