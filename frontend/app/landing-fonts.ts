/**
 * Static export helper.
 *
 * We intentionally avoid `next/font/google` so that:
 * - air-gapped / restricted networks can still build/export
 * - the workbench can be exported to a single offline HTML file
 *
 * The landing page only consumes `.variable` to bind CSS variables.
 */

export const landingPlex = {
  className: "",
  style: undefined as undefined,
  variable: "--font-landing-plex",
};

export const landingNoto = {
  className: "",
  style: undefined as undefined,
  variable: "--font-landing-noto",
};

