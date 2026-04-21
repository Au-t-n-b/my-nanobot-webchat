/**
 * Single swap boundary when the platform publishes an official npm `@agent-bridge/sdk`.
 * Re-export SPI types from here in new code; prefer `import … from '../spi/sdk-compat.js'`.
 */
export type * from "./types.js";
export type { ProviderCommandErrorInit, ProviderCommandErrorCode } from "./errors.js";
export { ProviderCommandError, providerError } from "./errors.js";
export { isProviderCommandError } from "./guards.js";
