/**
 * The app's MUI theme: light and dark palettes that follow `prefers-color-scheme`, plus the one
 * place status and node-kind colours are defined (used by cards, chips and the plan graph).
 * See documentation/design/core.md, Reporting: run view.
 */
import { createTheme, type Theme } from "@mui/material/styles";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useMemo } from "react";

/** Statuses of lens verdicts and plan nodes, all coloured from `theme.palette.status`. */
export type StatusName = "ok" | "abstained" | "failed" | "skipped" | "recovered" | "unknown";

declare module "@mui/material/styles" {
  interface Palette {
    /** Status -> colour for nodes, verdict chips and badges. */
    status: Record<StatusName, string>;
  }
  interface PaletteOptions {
    status?: Record<StatusName, string>;
  }
}

const STATUS_LIGHT: Record<StatusName, string> = {
  ok: "#2e7d32",
  abstained: "#757575",
  failed: "#c62828",
  skipped: "#9e9e9e",
  recovered: "#ed6c02",
  unknown: "#bdbdbd",
};
const STATUS_DARK: Record<StatusName, string> = {
  ok: "#66bb6a",
  abstained: "#9e9e9e",
  failed: "#ef5350",
  skipped: "#757575",
  recovered: "#ffa726",
  unknown: "#616161",
};

/** Build the theme for a colour mode. */
export function createAppTheme(mode: "light" | "dark"): Theme {
  return createTheme({
    palette: {
      mode,
      status: mode === "dark" ? STATUS_DARK : STATUS_LIGHT,
    },
    typography: { fontSize: 13 },
  });
}

/** The theme for the user's `prefers-color-scheme`; re-evaluates when it changes. */
export function useAppTheme(): Theme {
  const dark = useMediaQuery("(prefers-color-scheme: dark)");
  return useMemo(() => createAppTheme(dark ? "dark" : "light"), [dark]);
}

/** Status colour for any status string (unknown strings get the neutral colour). */
export function statusColor(theme: Theme, status: string): string {
  return theme.palette.status[status as StatusName] ?? theme.palette.status.unknown;
}
