import type { Metadata } from "next";
import { cookies } from "next/headers";
import { LanguageProvider } from "./language";
import "./fonts.css";
import "./globals.css";
import "./matchday.css";
import "./nerds/nerds.css";

const baseMetadata: Metadata = {
  title: "Spielraum | Bundesliga Forecast Lab",
  description: "Bayesianische Bundesliga-Prognosen, faire Quoten, Teamstärken und historische Forecasts.",
  openGraph: {
    title: "Spielraum | Bundesliga Forecast Lab",
    description: "Faire Quoten, dynamische Teamstärken und historische Prognosen.",
    type: "website",
    locale: "de_DE",
    images: [{ url: "/og.png", width: 1728, height: 909, alt: "Spielraum Bundesliga Forecast Lab" }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
};

export async function generateMetadata(): Promise<Metadata> {
  const language = (await cookies()).get("spielraum-language")?.value === "en" ? "en" : "de";
  if (language === "de") return baseMetadata;
  const description = "Bayesian Bundesliga predictions, fair odds, team strengths and historical forecasts.";
  return { ...baseMetadata, description, openGraph: { ...baseMetadata.openGraph, description, locale: "en_GB" } };
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const language = (await cookies()).get("spielraum-language")?.value === "en" ? "en" : "de";
  return <html lang={language}><head>
    <link rel="preload" href="/fonts/barlow-400.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
    <link rel="preload" href="/fonts/barlow-condensed-700.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
  </head><body><LanguageProvider initialLanguage={language}>{children}</LanguageProvider></body></html>;
}
