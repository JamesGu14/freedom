import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "freedom:theme";

function getSystemTheme() {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolveTheme(theme) {
  if (theme === "system") return getSystemTheme();
  return theme;
}

function applyThemeClass(resolved) {
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

export function useTheme() {
  const [themePreference, setThemePreference] = useState("dark");
  const [resolvedTheme, setResolvedTheme] = useState("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const initialPreference = stored ?? "dark";
    const initialResolved = resolveTheme(initialPreference);

    setThemePreference(initialPreference);
    setResolvedTheme(initialResolved);
    applyThemeClass(initialResolved);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const resolved = resolveTheme(themePreference);
    setResolvedTheme(resolved);
    applyThemeClass(resolved);
  }, [themePreference, mounted]);

  useEffect(() => {
    if (!mounted) return;

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (event) => {
      if (themePreference === "system") {
        const resolved = event.matches ? "dark" : "light";
        setResolvedTheme(resolved);
        applyThemeClass(resolved);
      }
    };

    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [themePreference, mounted]);

  useEffect(() => {
    if (!mounted) return;

    const handler = (event) => {
      if (event.key === STORAGE_KEY) {
        const newPreference = event.newValue ?? "system";
        setThemePreference(newPreference);
      }
    };

    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [mounted]);

  const setTheme = useCallback((newTheme) => {
    setThemePreference(newTheme);
    window.localStorage.setItem(STORAGE_KEY, newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemePreference((prev) => {
      const resolved = resolveTheme(prev);
      const next = resolved === "light" ? "dark" : "light";
      window.localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return {
    theme: resolvedTheme,
    themePreference,
    setTheme,
    toggleTheme,
    mounted,
  };
}
