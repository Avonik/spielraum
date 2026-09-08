"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { createFormatting, translate, type Language } from "./locale";

const LanguageContext = createContext<{ language: Language; setLanguage: (value: Language) => void }>({ language: "de", setLanguage: () => {} });

export function LanguageProvider({ initialLanguage, children }: { initialLanguage: Language; children: ReactNode }) {
  const [language, setLanguage] = useState(initialLanguage);
  useEffect(() => {
    document.documentElement.lang = language;
    const nerds = window.location.pathname.replace(/\/$/, "") === "/nerds";
    const description = nerds
      ? language === "de"
        ? "Die Geschichte hinter Spielraum: Teamstärken, xG, bayesianische Inferenz, Saisonübergang und Backtest."
        : "The story behind Spielraum: team strengths, xG, Bayesian inference, season transitions and backtesting."
      : language === "de"
        ? "Bayesianische Bundesliga-Prognosen, faire Quoten, Teamstärken und historische Forecasts."
        : "Bayesian Bundesliga predictions, fair odds, team strengths and historical forecasts.";
    document.querySelector('meta[name="description"]')?.setAttribute("content", description);
    document.querySelector('meta[property="og:locale"]')?.setAttribute("content", language === "de" ? "de_DE" : "en_GB");
  }, [language]);
  const changeLanguage = useCallback((value: Language) => {
    // The cookie also supplies the server-rendered language after navigation/reload.
    document.cookie = `spielraum-language=${value}; Path=/; Max-Age=31536000; SameSite=Lax`;
    setLanguage(value);
  }, []);
  return <LanguageContext.Provider value={{ language, setLanguage: changeLanguage }}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const { language, setLanguage } = useContext(LanguageContext);
  return useMemo(() => ({ language, setLanguage, t: (text: string) => translate(language, text), ...createFormatting(language) }), [language, setLanguage]);
}

export function LanguageSwitch() {
  const { language, setLanguage } = useLanguage();
  return <div className="language-switch" role="group" aria-label={language === "de" ? "Sprache wählen" : "Choose language"}>
    <button type="button" lang="de" aria-label="Deutsch" aria-pressed={language === "de"} onClick={() => setLanguage("de")}>DE</button>
    <button type="button" lang="en" aria-label="English" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
  </div>;
}
