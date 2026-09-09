/** Owns the path-only tab workspace; URL routing and page metadata stay elsewhere. */
import { useCallback, useEffect, useState } from "react";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "@/router/routeResolver";

export const TAB_WORKSPACE_STORAGE_KEY = "tab_workspace";
export const TAB_WORKSPACE_VERSION = 1;
export const MAX_OPEN_TABS = 12;

export interface TabWorkspaceStorage {
  version: number;
  openPaths: string[];
  activePath: string;
}

export type OpenTabResult = "opened" | "already-open" | "limit" | "invalid";

interface TabWorkspaceState extends TabWorkspaceStorage {
  observedPath: string;
  rejectedPath: string | null;
}

const defaultWorkspace = (): TabWorkspaceStorage => ({
  version: TAB_WORKSPACE_VERSION,
  openPaths: [DEFAULT_BUSINESS_PATH],
  activePath: DEFAULT_BUSINESS_PATH,
});

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const isAllowedPath = (path: string) => resolveRoute(path).kind === "allowed";

const syncActivePath = (
  workspace: TabWorkspaceStorage,
  requestedPath: string,
): TabWorkspaceState => {
  if (!isAllowedPath(requestedPath)) {
    return { ...workspace, observedPath: requestedPath, rejectedPath: null };
  }
  if (workspace.openPaths.includes(requestedPath)) {
    return {
      ...workspace,
      activePath: requestedPath,
      observedPath: requestedPath,
      rejectedPath: null,
    };
  }
  if (workspace.openPaths.length >= MAX_OPEN_TABS) {
    return {
      ...workspace,
      activePath: workspace.openPaths.includes(workspace.activePath)
        ? workspace.activePath
        : DEFAULT_BUSINESS_PATH,
      observedPath: requestedPath,
      rejectedPath: requestedPath,
    };
  }
  return {
    ...workspace,
    openPaths: [...workspace.openPaths, requestedPath],
    activePath: requestedPath,
    observedPath: requestedPath,
    rejectedPath: null,
  };
};

export function restoreTabWorkspace(rawValue: string | null): TabWorkspaceStorage {
  if (!rawValue) return defaultWorkspace();

  try {
    const value: unknown = JSON.parse(rawValue);
    if (
      !isRecord(value) ||
      value.version !== TAB_WORKSPACE_VERSION ||
      !Array.isArray(value.openPaths) ||
      typeof value.activePath !== "string"
    ) {
      return defaultWorkspace();
    }

    const openPaths = [DEFAULT_BUSINESS_PATH];
    for (const path of value.openPaths) {
      if (
        typeof path === "string" &&
        path !== DEFAULT_BUSINESS_PATH &&
        !openPaths.includes(path) &&
        isAllowedPath(path) &&
        openPaths.length < MAX_OPEN_TABS
      ) {
        openPaths.push(path);
      }
    }

    return {
      version: TAB_WORKSPACE_VERSION,
      openPaths,
      activePath: openPaths.includes(value.activePath)
        ? value.activePath
        : DEFAULT_BUSINESS_PATH,
    };
  } catch {
    return defaultWorkspace();
  }
}

export function readTabWorkspace(): TabWorkspaceStorage {
  if (typeof window === "undefined") return defaultWorkspace();

  try {
    return restoreTabWorkspace(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY));
  } catch {
    return defaultWorkspace();
  }
}

function writeTabWorkspace(openPaths: string[], activePath: string) {
  try {
    sessionStorage.setItem(
      TAB_WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        version: TAB_WORKSPACE_VERSION,
        openPaths,
        activePath,
      } satisfies TabWorkspaceStorage),
    );
  } catch {
    // The in-memory workspace remains usable when browser storage is unavailable.
  }
}

export function clearTabWorkspaceStorage() {
  try {
    sessionStorage.removeItem(TAB_WORKSPACE_STORAGE_KEY);
  } catch {
    // Logout still clears the mounted workspace when browser storage is unavailable.
  }
}

function useTabWorkspace(activePath: string) {
  const [workspace, setWorkspace] = useState(() =>
    syncActivePath(readTabWorkspace(), activePath),
  );

  if (workspace.observedPath !== activePath) {
    setWorkspace(syncActivePath(workspace, activePath));
  }

  const { openPaths } = workspace;

  useEffect(() => {
    writeTabWorkspace(openPaths, workspace.activePath);
  }, [openPaths, workspace.activePath]);

  const openPath = useCallback(
    (path: string): OpenTabResult => {
      if (!isAllowedPath(path)) return "invalid";
      if (openPaths.includes(path)) return "already-open";
      if (openPaths.length >= MAX_OPEN_TABS) return "limit";

      setWorkspace((value) => ({
        ...value,
        openPaths: [...value.openPaths, path],
      }));
      return "opened";
    },
    [openPaths],
  );

  const closePath = useCallback(
    (path: string) => {
      if (path === DEFAULT_BUSINESS_PATH || !openPaths.includes(path)) {
        return activePath;
      }

      const tabIndex = openPaths.indexOf(path);
      const remainingPaths = openPaths.filter((openPath) => openPath !== path);
      setWorkspace((value) => ({ ...value, openPaths: remainingPaths }));

      return path === activePath
        ? remainingPaths[Math.min(tabIndex, remainingPaths.length - 1)] ??
            DEFAULT_BUSINESS_PATH
        : activePath;
    },
    [activePath, openPaths],
  );

  return {
    openPaths,
    activePath: workspace.activePath,
    rejectedPath: workspace.rejectedPath,
    openPath,
    closePath,
    clearWorkspace: clearTabWorkspaceStorage,
  };
}

export default useTabWorkspace;
