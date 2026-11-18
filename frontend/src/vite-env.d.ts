/// <reference types="vite/client" />
interface ImportMetaEnv {
  /** Optional absolute URL of the API when frontend and backend are hosted separately. */
  readonly VITE_API_URL?: string;
}
