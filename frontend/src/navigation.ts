/** Frontend-local navigation and connection state shared across the workspace. */

export type ViewId = 'home' | 'all' | 'notes' | 'urls' | 'search' | 'settings'

export interface NavItem {
  id: ViewId
  label: string
  hint: string
}

export const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { id: 'home', label: 'Home', hint: 'Workspace overview' },
  { id: 'all', label: 'All Knowledge', hint: 'Everything you saved' },
  { id: 'notes', label: 'Notes', hint: 'Text notes only' },
  { id: 'urls', label: 'Web Pages', hint: 'Saved links only' },
  { id: 'search', label: 'Search', hint: 'Find something specific' },
  { id: 'settings', label: 'Settings', hint: 'Connection and configuration' },
]

export type ConnectionState =
  | { kind: 'checking' }
  | { kind: 'connected'; application: string; version: string; status: string }
  | { kind: 'disconnected'; message: string }
