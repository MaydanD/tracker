/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Tracker API. Empty by default: the dev server proxies /api. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
