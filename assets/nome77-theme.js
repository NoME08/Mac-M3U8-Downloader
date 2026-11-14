(() => {
  const root = document.documentElement;
  const storageKey = "nome77-theme";
  const controlSelector = "select[data-nome77-theme]";
  const modes = ["system", "dark", "light"];
  const systemTheme = window.matchMedia?.("(prefers-color-scheme: light)");

  function loadPreference() {
    try {
      const stored = window.localStorage.getItem(storageKey);
      return modes.includes(stored) ? stored : "system";
    } catch {
      return "system";
    }
  }

  let preference = loadPreference();

  function applyTheme() {
    const systemColor = systemTheme?.matches ? "light" : "dark";
    root.dataset.theme = preference === "system" ? systemColor : preference;
  }

  function syncControls() {
    document.querySelectorAll(controlSelector).forEach((control) => {
      control.value = preference;
    });
  }

  applyTheme();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncControls, { once: true });
  } else {
    syncControls();
  }

  systemTheme?.addEventListener?.("change", () => {
    if (preference === "system") applyTheme();
  });

  document.addEventListener("change", (event) => {
    const control = event.target;
    if (!control.matches?.(controlSelector) || !modes.includes(control.value)) return;

    preference = control.value;
    applyTheme();
    syncControls();
    try {
      window.localStorage.setItem(storageKey, preference);
    } catch {
      // Keep the preference active for the current page when storage is unavailable.
    }
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    preference = loadPreference();
    applyTheme();
    syncControls();
  });
})();
