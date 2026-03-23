/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WATTFOREST_API_BASE_URL?: string;
  readonly VITE_WATTFOREST_API_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
