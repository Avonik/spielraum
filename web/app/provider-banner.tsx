"use client";

import { useLanguage } from "./language";

export function ProviderBanner({ status }: { status?: { available: boolean } | null }) {
  const { t } = useLanguage();
  return <div role="status" aria-live="polite" aria-atomic="true">
    {status?.available === false && <aside className="provider-banner">
      <span className="provider-banner__icon" aria-hidden="true">!</span>
      <p><strong>{t("Understat-API derzeit nicht verfügbar.")}</strong>{" "}
        {t("Neue xG-Daten fehlen vorübergehend. Wir zeigen weiterhin die zuletzt veröffentlichten Prognosen.")}</p>
    </aside>}
  </div>;
}
