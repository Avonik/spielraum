import type { Metadata } from "next";
import "./globals.css";
import "./matchday.css";

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
  return <html lang="de"><body>{children}</body></html>;
}
