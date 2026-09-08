import { english } from "./translations";

export type Language = "de" | "en";
export function translate(language: Language, text: string) {
  if (language === "de") return text;
  const key = text.trim();
  return english[key] === undefined ? text : text.replace(key, english[key]);
}

export function createFormatting(language: Language) {
  const locale = language === "de" ? "de-DE" : "en-GB";
  return {
    formatPercent: (value: number) => `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}${language === "de" ? " " : ""}%`,
    formatOdds: (value: number) => (1 / value).toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    formatIndex: (value: number | undefined) => value === undefined ? "-" : value.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    formatRank: (value: number) => language === "de" ? `${value}.` : String(value),
    formatRange: (from: number, to: number) => language === "de" ? `${from}. bis ${to}.` : `${from} to ${to}`,
    formatKickoff: (value: string) => new Intl.DateTimeFormat(locale, {
      weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
      timeZone: "Europe/Berlin",
    }).format(new Date(value)).replace(",", " ·"),
    formatTimestamp: (value: string) => new Intl.DateTimeFormat(locale, {
      day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
      timeZone: "Europe/Berlin",
    }).format(new Date(value)),
  };
}
