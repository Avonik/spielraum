import type { Metadata } from "next";
import { cookies } from "next/headers";
import NerdsContent from "./nerds-content";

export async function generateMetadata(): Promise<Metadata> {
  const en = (await cookies()).get("spielraum-language")?.value === "en";
  return { title: "Statistical Deep Dive | Spielraum", description: en
    ? "The story behind Spielraum: team strengths, xG, Bayesian inference, season transitions and backtesting."
    : "Die Geschichte hinter Spielraum: Teamstärken, xG, bayesianische Inferenz, Saisonübergang und Backtest." };
}
export default function NerdsPage() { return <NerdsContent />; }
