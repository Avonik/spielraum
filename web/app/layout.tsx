import type { Metadata } from "next";
import "./fonts.css";
import "./globals.css";
import "./matchday.css";
import "./nerds/nerds.css";

export const metadata: Metadata = {
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

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="de"><head>
    <link rel="preload" href="/fonts/barlow-400.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
    <link rel="preload" href="/fonts/barlow-condensed-700.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
  </head><body>{children}</body></html>;
}
