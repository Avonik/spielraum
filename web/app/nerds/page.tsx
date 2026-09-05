import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Statistical Deep Dive | Spielraum",
  description: "Generatives Modell, Priors, MCMC-Inferenz, Saisonübergang und Backtest des Spielraum Bundesliga-Modells.",
};

function Equation({ children, label }: { children: ReactNode; label: string }) {
  return <div className="equation" aria-label={label}>{children}</div>;
}

export default function NerdsPage() {
  return <main className="nerd-page">
    <header className="nerd-topbar">
      <Link className="brand" href="/"><span className="brand-mark"><i /><i /><i /></span><span>SPIELRAUM<small>Forecast Lab</small></span></Link>
      <Link className="back-link" href="/">← Zur Prognose</Link>
    </header>

    <section className="nerd-hero">
      <div><div className="eyebrow">Statistical Deep Dive · Modell V2.1</div><h1>Vom latenten Prozess zur<br /><em>1-X-2-Verteilung.</em></h1><p>Das hier ist keine vereinfachte „So funktioniert KI“-Erklärung. Es ist die mathematische Spezifikation des Modells, das den Backtest und später die veröffentlichten Prognosen erzeugt.</p></div>
      <aside className="model-facts">
        <span><small>Latenter Zustand</small><b>Angriff + Abwehr</b></span>
        <span><small>Beobachtung</small><b>kontinuierliches xG</b></span>
        <span><small>Inferenz</small><b>Metropolis-Hastings</b></span>
        <span><small>Forecast</small><b>Poisson + Mischung</b></span>
      </aside>
    </section>

    <nav className="nerd-index" aria-label="Kapitel">
      <a href="#state">Zustandsprozess</a><a href="#likelihood">Likelihood</a><a href="#priors">Priors</a><a href="#transition">Übergang</a><a href="#inference">Inferenz</a><a href="#score">Bewertung</a>
    </nav>

    <section className="math-section" id="state">
      <div className="math-section__heading"><div><div className="eyebrow">Latenter Zustandsraum</div><h2>Zwei zeitabhängige Stärken pro Team.</h2></div></div>
      <div className="math-layout"><div className="math-copy"><p>Für Team <i>i</i> existieren Angriff <code>a<sub>i,t</sub></code> und Abwehr <code>d<sub>i,t</sub></code> am Zeitpunkt seines <i>t</i>-ten Spiels. Zwischen zwei Spielen folgen beide einer Brownschen Bewegung. Je größer der zeitliche Abstand, desto größer die erlaubte Zustandsänderung.</p><Equation label="Angriffsstärke folgt einer Normalverteilung um die vorherige Stärke"><span>a<sub>i,t</sub> | a<sub>i,t−1</sub></span><b>∼</b><span>Normal(a<sub>i,t−1</sub>, Δt/τ · σ²)</span></Equation><Equation label="Abwehrstärke folgt einer Normalverteilung um die vorherige Stärke"><span>d<sub>i,t</sub> | d<sub>i,t−1</sub></span><b>∼</b><span>Normal(d<sub>i,t−1</sub>, Δt/τ · σ²)</span></Equation></div><aside className="parameter-card"><h3>Produktionswerte</h3><dl><div><dt>τ</dt><dd>100 Tage</dd></div><div><dt>σ²</dt><dd>1 / 37</dd></div><div><dt>Δt</dt><dd>Tage seit letztem Spiel</dd></div></dl><p>Der Prozess ist nicht an Spieltage, sondern an reale Zeitabstände gekoppelt.</p></aside></div>
    </section>

    <section className="math-section math-section--dark" id="likelihood">
      <div className="math-section__heading"><div><div className="eyebrow">Torintensität &amp; Beobachtungsmodell</div><h2>Stärken werden zu erwarteten Chancen.</h2></div></div>
      <div className="formula-stack">
        <Equation label="Relative Teamstärkendifferenz"><span>Δ = ½[(a<sub>h</sub> + d<sub>h</sub>) − (a<sub>a</sub> + d<sub>a</sub>)]</span></Equation>
        <Equation label="Logarithmische Heimtorintensität"><span>log λ<sub>h</sub> = c<sub>h</sub> + a<sub>h</sub> − d<sub>a</sub> − γΔ</span></Equation>
        <Equation label="Logarithmische Auswärtstorintensität"><span>log λ<sub>a</sub> = c<sub>a</sub> + a<sub>a</sub> − d<sub>h</sub> + γΔ</span></Equation>
      </div>
      <div className="technical-grid"><article><small>Beobachtung</small><h3>Gamma statt gerundetem xG</h3><Equation label="Gamma Beobachtungsmodell"><span>g | λ ∼ Gamma(shape = φ, rate = φ / λ)</span></Equation><p><code>E[g|λ] = λ</code> und <code>Var[g|λ] = λ²/φ</code>. Verwendet wird <code>φ = 5</code>. Das rohe xG bleibt kontinuierlich; es wird nicht auf Tore gerundet.</p></article><article><small>Robustheit</small><h3>Latente Mischkomponente</h3><Equation label="Bernoulli Mischindikator"><span>δ<sub>m</sub> ∼ Bernoulli(ε), &nbsp; ε = 0,2</span></Equation><p>Für <code>δ=0</code> gelten teamspezifische Intensitäten. Für <code>δ=1</code> verwendet das Spiel das globale Ligalevel. Der Indikator wird im MCMC mitgesampelt und dämpft Spiele, die schlecht zum Teamzustand passen.</p></article></div>
    </section>

    <section className="math-section" id="priors">
      <div className="math-section__heading"><div><div className="eyebrow">Saisonstart</div><h2>Zwei Priors, dieselbe Modellstruktur.</h2></div></div>
      <div className="prior-columns"><article><span>FRESH</span><h3>Nur aktuelle Saison</h3><p>Der Fresh-Stream startet ohne Posterior der Vorsaison. Sein Mittelwert kommt aus dem standardisierten logarithmischen Kaderwert.</p><Equation label="Marktwertprior"><span>μ<sub>MV,i</sub> = κ · z(log MV<sub>i</sub>), &nbsp; κ = 0,10</span></Equation></article><article><span>CARRY</span><h3>Posterior plus Sommerunsicherheit</h3><p>Der Carry-Stream propagiert Mittelwert und Varianz des letzten Vorsaison-Zustands über die reale Sommerpause.</p><Equation label="Carry Varianz"><span>v<sub>carry</sub> = v<sub>prev</sub> + Δt<sub>Sommer</sub>/τ · σ²</span></Equation><Equation label="Präzisionsgewichtete Varianz"><span>v* = (1/v<sub>carry</sub> + 1/v<sub>MV</sub>)<sup>−1</sup></span></Equation><Equation label="Präzisionsgewichteter Mittelwert"><span>μ* = v* · (μ<sub>prev</sub>/v<sub>carry</sub> + μ<sub>MV</sub>/v<sub>MV</sub>)</span></Equation></article></div>
      <div className="level-prior"><div><small>GLOBALER LEVEL-PRIOR</small><h3>144 historische Pseudospiele</h3></div><Equation label="Geschrumpftes globales Torniveau"><span>L = [144 · L<sub>hist</sub> + n · L<sub>aktuell</sub>] / (144 + n)</span></Equation><p>Heim- und Auswärtsniveau werden separat auf der natürlichen Skala gemischt und danach logarithmiert. So kann ein einzelnes Freitagsspiel nicht das gesamte erste Wochenende verschieben. Der 144er-Prior besitzt bewusst keinen zusätzlichen Fade-Hyperparameter.</p></div>
    </section>

    <section className="math-section math-section--acid" id="transition">
      <div className="math-section__heading"><div><div className="eyebrow">Produktions-Policy</div><h2>Carry wird nicht gewählt, sondern ausgeblendet.</h2></div></div>
      <Equation label="Mischung der Carry und Fresh Prognose"><span>p<sub>t</sub> = w<sub>t</sub> · p<sub>carry,t</sub> + (1 − w<sub>t</sub>) · p<sub>fresh,t</sub></span></Equation>
      <div className="weight-function"><div><span>1</span><b>w<sub>t</sub> =</b><span>½[1 + cos(π(t−12)/6)]</span><span>0</span></div><div className="weight-timeline"><i /><i /><i /><b>ST 1-12</b><b>ST 13-17</b><b>ab ST 18</b></div></div>
      <p className="math-note">Das Gewicht ist bis einschließlich Spieltag 12 exakt eins und ab Spieltag 18 exakt null. Nur im Übergangsfenster werden die beiden vollständigen 1-X-2-Verteilungen gemischt.</p>
    </section>

    <section className="math-section" id="inference">
      <div className="math-section__heading"><div><div className="eyebrow">Posterior-Inferenz</div><h2>Single-Site Metropolis-Hastings.</h2></div></div>
      <div className="inference-flow"><article><h3>Proposal</h3><code>θ′ = θ + Normal(0, 0,06²)</code><p>Angriff und Abwehr werden an jedem lokalen Teamzustand einzeln vorgeschlagen.</p></article><article><h3>Acceptance</h3><code>α = min(1, posterior′ / posterior)</code><p>Nur die betroffene lokale Likelihood und die angrenzenden Zeitpriors müssen neu berechnet werden.</p></article><article><h3>Mixture update</h3><code>δ′ = 1 − δ</code><p>Der Bernoulli-Indikator jedes Spiels wird als eigener diskreter Zustand aktualisiert.</p></article><article><h3>Identifikation</h3><code>Σa + Σd = 0</code><p>Nach jeder Iteration wird der globale Leveldrift entfernt. Warm Starts beschleunigen aufeinanderfolgende Stichtage.</p></article></div>
    </section>

    <section className="math-section math-section--dark" id="score">
      <div className="math-section__heading"><div><div className="eyebrow">Posterior Predictive &amp; Evaluation</div><h2>Von λ zu fairen Quoten.</h2></div></div>
      <div className="technical-grid"><article><small>Forecast</small><h3>Diskretes Ergebnisgitter</h3><p>Für jedes Posterior-Sample wird ein Torergebnisgitter von 0 bis 5 aufgebaut; die letzte Zelle enthält den jeweiligen Poisson-Tail. Eine Dixon-Coles-Korrektur verändert die vier niedrigen Ergebnisse 0:0, 0:1, 1:0 und 1:1.</p><Equation label="Heimsiegwahrscheinlichkeit"><span>P(H) = Σ<sub>x&gt;y</sub> p(x,y), &nbsp; P(X) = Σ<sub>x=y</sub> p(x,y)</span></Equation><p>Die drei Wahrscheinlichkeiten werden über alle gespeicherten MCMC-Samples gemittelt. Faire Quote: <code>q = 1/p</code>.</p></article><article><small>Scoring Rule</small><h3>Ranked Probability Score</h3><Equation label="Ranked Probability Score"><span>RPS = ½[(p<sub>H</sub>−o<sub>H</sub>)² + (p<sub>H</sub>+p<sub>D</sub>−o<sub>H</sub>−o<sub>D</sub>)²]</span></Equation><p>Der RPS berücksichtigt die Ordnung Heim, Remis, Auswärts und bewertet die komplette Verteilung. Niedriger ist besser; eine bloße Trefferquote würde Konfidenz und Kalibrierung ignorieren.</p></article></div>
      <div className="result-table"><div><span>Backtest</span><span>V2</span><span>Markt</span><span>Relativer Abstand</span></div><div><b>High Budget · 2023/24-2025/26</b><strong>0,19797</strong><strong>0,19204</strong><em>+3,1 %</em></div><div><b>Breite Bestätigung · 11 Saisons</b><strong>0,20559</strong><strong>0,19892</strong><em>+3,35 %</em></div></div>
    </section>

    <section className="limitations"><div className="eyebrow">Was das Modell nicht behauptet</div><h2>Unsicherheit bleibt Teil des Produkts.</h2><div><p>Das Modell ist prädiktiv, nicht kausal. Es erklärt keine Trainerentscheidungen, Verletzungen oder taktischen Mechanismen.</p><p>Marktwerte sind ein schwacher Preseason-Prior und kein beobachteter Leistungswert. Im Saisonverlauf werden sie von Spieldaten überschrieben.</p><p>Buchmacher-Schlussquoten aggregieren zusätzliche Informationen. Der aktuelle Backtest zeigt ausdrücklich, dass der Markt weiterhin besser ist.</p><p>Frühe Saisonprognosen sind stark priorgetrieben. Konfidenzintervalle und vollständige Verteilungen sind daher wichtiger als ein einzelner Tipp.</p></div><Link className="back-link" href="/">← Zurück zum Spieltag</Link></section>
  </main>;
}
