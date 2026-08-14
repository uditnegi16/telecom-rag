/// <reference types="vite/client" />

/**
 * Vite's client type declarations.
 *
 * Without this, `tsc -b` fails with:
 *   Property 'env' does not exist on type 'ImportMeta'
 *
 * `npm run dev` works regardless, because Vite injects the types at runtime -
 * so the error only appears in the PRODUCTION build (ERROR_LOG E-029).
 */

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
