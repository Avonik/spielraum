import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Statistical Deep Dive | Spielraum",
  description: "Generatives Modell, Priors, MCMC-Inferenz, Saisonübergang und Backtest des Spielraum Bundesliga-Modells.",
};

function Equation({ children, label }: { children: ReactNode; label: string }) {
  return <div className="equation" role="region" tabIndex={0} aria-label={label}>{children}</div>;
}

function DeepDive({ children, title }: { children: ReactNode; title: string }) {
  return <details className="deep-dive"><summary>{title}<span aria-hidden="true">＋</span></summary><div className="deep-dive__body">{children}</div></details>;
}

export default function NerdsPage() {
  return <main className="nerd-page nerd-story">
    <a className="skip-link" href="#state">Zur Modellgeschichte</a>
    <header className="nerd-topbar">
      <Link className="brand" href="/"><span className="brand-mark"><i /><i /><i /></span><span>SPIELRAUM<small>Forecast Lab</small></span></Link>
      <Link className="back-link" href="/">← Zur Prognose</Link>
    </header>

    <section className="nerd-hero">
      <div><div className="eyebrow">Für Nerds &amp; Neugierige · Statistical Deep Dive</div><h1>Was weiß ein Modell<br /><em>über Fußball?</em></h1><p>Ein 1:0 erzählt, wer gewonnen hat. Es erzählt noch nicht, wer besser war oder nächstes Wochenende gewinnt. Genau hier beginnt unsere Prognose.</p><div className="story-meta"><span>6 Kapitel · Modell V2.1</span><a href="#paper">Die wissenschaftliche Grundlage ↗</a></div></div>
      <aside className="story-route" aria-label="Der Weg zur Prognose">
        <span className="eyebrow">Vom Spiel zur Wahrscheinlichkeit</span>
        <ol><li><span>01</span><div><strong>Chancen beobachten</strong><p>Was hat ein Team herausgespielt?</p></div></li><li><span>02</span><div><strong>Stärke schätzen</strong><p>Was lernen wir daraus über seine Form?</p></div></li><li><span>03</span><div><strong>Ausgänge gewichten</strong><p>Wie wahrscheinlich sind 1, X und 2?</p></div></li></ol>
      </aside>
    </section>

    <nav className="nerd-index" aria-label="Kapitel">
      <a href="#state">01 · Stärke</a><a href="#likelihood">02 · Chancen</a><a href="#priors">03 · Vorwissen</a><a href="#transition">04 · Saison</a><a href="#inference">05 · Prognose</a><a href="#score">06 · Realität</a>
    </nav>

    <section className="paper-origin" id="paper" aria-labelledby="paper-title">
      <div><div className="eyebrow">Die Idee dahinter · 2000</div><h2 id="paper-title">Fußballstärke ist in Bewegung.</h2><p>Håvard Rue und Øyvind Salvesen beschreiben Teams über verborgene, zeitlich veränderliche Stärken und schätzen diese mit bayesianischen Methoden. Ihr Paper ist die Grundlage dieses Projekts.</p><p>Spielraum entwickelt den Ansatz weiter: mit kontinuierlichem xG als Beobachtung, Kaderwerten als Startinformation und einem Übergang zwischen Vorsaisonwissen und aktueller Saison.</p></div>
      <a className="paper-reference" href="https://doi.org/10.1111/1467-9884.00243" target="_blank" rel="noopener noreferrer"><span>Originalpaper <span aria-hidden="true">↗</span></span><cite>Prediction and Retrospective Analysis of Soccer Matches in a League</cite><span>Rue &amp; Salvesen · 2000</span><small>JRSS: Series D (The Statistician), 49(3), 399–418<br />DOI: 10.1111/1467-9884.00243 · Öffnet einen neuen Tab</small></a>
    </section>

    <section className="math-section" id="state">
      <div className="math-section__heading"><div><div className="eyebrow">01 · Hinter dem Ergebnis</div><h2>Form steht nicht in der Tabelle.</h2></div></div>
      <div className="chapter-lead"><p>Ein Team kann viel kreieren und trotzdem verlieren. Ein anderes gewinnt mit wenigen Chancen. Deshalb schätzen wir zwei getrennte Größen: die Fähigkeit, Chancen zu erzeugen, und die Fähigkeit, sie zu verhindern.</p><p>Diese Stärken sind nicht direkt sichtbar. Das Modell erschließt sie aus den Spielen und lässt sie über die Zeit wandern. Nach einer längeren Pause ist mehr Veränderung möglich als nach drei Tagen.</p></div>
      <div className="concept-pair"><div><span>Angriff</span><strong>Chancen schaffen.</strong><p>Wie viel Gefahr entsteht vor dem gegnerischen Tor?</p></div><div><span>Abwehr</span><strong>Chancen begrenzen.</strong><p>Wie wenig Gefahr lässt das Team gegen sich zu?</p></div></div>
      <DeepDive title="Die Mathematik: zwei Stärken als zeitlicher Prozess">
      <div className="math-layout"><div className="math-copy"><p>Für Team <i>i</i> existieren Angriff <code>a<sub>i,t</sub></code> und Abwehr <code>d<sub>i,t</sub></code> am Zeitpunkt seines <i>t</i>-ten Spiels. Zwischen zwei Spielen folgen beide einer Brownschen Bewegung. Je größer der zeitliche Abstand, desto größer die erlaubte Zustandsänderung.</p><Equation label="Angriffsstärke folgt einer Normalverteilung um die vorherige Stärke"><span>a<sub>i,t</sub> | a<sub>i,t−1</sub></span><b>∼</b><span>Normal(a<sub>i,t−1</sub>, Δt/τ · σ²)</span></Equation><Equation label="Abwehrstärke folgt einer Normalverteilung um die vorherige Stärke"><span>d<sub>i,t</sub> | d<sub>i,t−1</sub></span><b>∼</b><span>Normal(d<sub>i,t−1</sub>, Δt/τ · σ²)</span></Equation></div><aside className="parameter-card"><h3>Produktionswerte</h3><dl><div><dt>τ</dt><dd>100 Tage</dd></div><div><dt>σ²</dt><dd>1 / 37</dd></div><div><dt>Δt</dt><dd>Tage seit letztem Spiel</dd></div></dl><p>Der Prozess ist nicht an Spieltage, sondern an reale Zeitabstände gekoppelt.</p></aside></div>
      </DeepDive>
    </section>

    <section className="math-section math-section--dark" id="likelihood">
      <div className="math-section__heading"><div><div className="eyebrow">02 · Leistung und Zufall</div><h2>Das Ergebnis ist nur ein Teil der Geschichte.</h2></div></div>
      <div className="chapter-lead"><p>Expected Goals, kurz xG, fassen die Qualität der Torchancen zusammen. So bleibt sichtbar, ob ein Team regelmäßig gute Chancen erzeugt, auch wenn der Ball an diesem Tag nicht ins Tor geht.</p><p>Unser Modell verbindet den Angriff eines Teams mit der Abwehr des Gegners und dem Heim- beziehungsweise Auswärtsniveau. Daraus entsteht eine erwartete Intensität. Die tatsächlich beobachteten xG dürfen davon abweichen.</p></div>
      <aside className="story-takeaway"><span>Die entscheidende Trennung</span><p>Wir lernen aus kontinuierlichen Chancenwerten. Für die Prognose übersetzen wir die geschätzten Intensitäten später wieder in ganze Tore.</p></aside>
      <DeepDive title="Unter der Haube: Intensitäten, Gamma-Verteilung und Ausreißer">
      <div className="formula-stack">
        <Equation label="Relative Teamstärkendifferenz"><span>Δ = ½[(a<sub>h</sub> + d<sub>h</sub>) − (a<sub>a</sub> + d<sub>a</sub>)]</span></Equation>
        <Equation label="Logarithmische Heimtorintensität"><span>log λ<sub>h</sub> = c<sub>h</sub> + a<sub>h</sub> − d<sub>a</sub> − γΔ</span></Equation>
        <Equation label="Logarithmische Auswärtstorintensität"><span>log λ<sub>a</sub> = c<sub>a</sub> + a<sub>a</sub> − d<sub>h</sub> + γΔ</span></Equation>
      </div>
      <div className="technical-grid"><article><small>Beobachtung</small><h3>Gamma statt gerundetem xG</h3><Equation label="Gamma Beobachtungsmodell"><span>g | λ ∼ Gamma(shape = φ, rate = φ / λ)</span></Equation><p><code>E[g|λ] = λ</code> und <code>Var[g|λ] = λ²/φ</code>. Verwendet wird <code>φ = 5</code>. Das rohe xG bleibt kontinuierlich; es wird nicht auf Tore gerundet.</p></article><article><small>Robustheit</small><h3>Latente Mischkomponente</h3><Equation label="Bernoulli Mischindikator"><span>δ<sub>m</sub> ∼ Bernoulli(ε), &nbsp; ε = 0,2</span></Equation><p>Für <code>δ=0</code> gelten teamspezifische Intensitäten. Für <code>δ=1</code> verwendet das Spiel das globale Ligalevel. Der Indikator wird im MCMC mitgesampelt und dämpft Spiele, die schlecht zum Teamzustand passen.</p></article></div>
      </DeepDive>
    </section>

    <section className="math-section" id="priors">
      <div className="math-section__heading"><div><div className="eyebrow">03 · Der erste Spieltag</div><h2>Niemand startet bei null.</h2></div></div>
      <div className="chapter-lead"><p>Vor dem ersten Anpfiff gibt es noch keine Spiele der neuen Saison. Trotzdem wissen wir etwas: über die Vorsaison und über die Zusammensetzung der Kader. Dieses vorläufige Wissen heißt im bayesianischen Modell <em>Prior</em>.</p><p>Wir rechnen mit zwei parallelen Modellläufen. <strong>Carry</strong> nimmt geschätzte Stärken aus der Vorsaison mit, wird über die Sommerpause aber unsicherer. <strong>Fresh</strong> startet ohne diesen alten Teamzustand. Beide nutzen den Kaderwert als schwachen Anhaltspunkt.</p></div>
      <DeepDive title="Die Startwerte: Marktwertprior, Carry und das Niveau der Liga">
      <div className="prior-columns"><article><span>FRESH</span><h3>Nur aktuelle Saison</h3><p>Der Fresh-Stream startet ohne Posterior der Vorsaison. Sein Mittelwert kommt aus dem standardisierten logarithmischen Kaderwert.</p><Equation label="Marktwertprior"><span>μ<sub>MV,i</sub> = κ · z(log MV<sub>i</sub>), &nbsp; κ = 0,10</span></Equation></article><article><span>CARRY</span><h3>Posterior plus Sommerunsicherheit</h3><p>Der Carry-Stream propagiert Mittelwert und Varianz des letzten Vorsaison-Zustands über die reale Sommerpause.</p><Equation label="Carry Varianz"><span>v<sub>carry</sub> = v<sub>prev</sub> + Δt<sub>Sommer</sub>/τ · σ²</span></Equation><Equation label="Präzisionsgewichtete Varianz"><span>v* = (1/v<sub>carry</sub> + 1/v<sub>MV</sub>)<sup>−1</sup></span></Equation><Equation label="Präzisionsgewichteter Mittelwert"><span>μ* = v* · (μ<sub>prev</sub>/v<sub>carry</sub> + μ<sub>MV</sub>/v<sub>MV</sub>)</span></Equation></article></div>
      <div className="level-prior"><div><small>GLOBALER LEVEL-PRIOR</small><h3>144 historische Pseudospiele</h3></div><Equation label="Geschrumpftes globales Torniveau"><span>L = [144 · L<sub>hist</sub> + n · L<sub>aktuell</sub>] / (144 + n)</span></Equation><p>Heim- und Auswärtsniveau werden separat auf der natürlichen Skala gemischt und danach logarithmiert. So kann ein einzelnes Freitagsspiel nicht das gesamte erste Wochenende verschieben. Der 144er-Prior besitzt bewusst keinen zusätzlichen Fade-Hyperparameter.</p></div>
      </DeepDive>
    </section>

    <section className="math-section math-section--acid" id="transition">
      <div className="math-section__heading"><div><div className="eyebrow">04 · Lernen heißt auch loslassen</div><h2>Die neue Saison übernimmt.</h2></div></div>
      <div className="chapter-lead"><p>Vorsaisonwissen hilft am Anfang. Nach vielen neuen Spielen soll es die Prognose weniger prägen. Deshalb wechselt Spielraum schrittweise vom Carry- zum Fresh-Modell. Beide lernen dabei aus den Spielen der aktuellen Saison.</p></div>
      <ol className="season-steps"><li><span>Spieltag 1 bis 12</span><strong>Erfahrung nutzen</strong><p>100 % Carry. Das Wissen der Vorsaison gibt dem Start Halt.</p></li><li><span>Spieltag 13 bis 17</span><strong>Gewicht verlagern</strong><p>Carry nimmt sanft ab, Fresh gewinnt mit jedem Spieltag an Gewicht.</p></li><li><span>Ab Spieltag 18</span><strong>Gegenwart vertrauen</strong><p>100 % Fresh. Der übernommene Teamzustand spielt keine Rolle mehr.</p></li></ol>
      <DeepDive title="Die Gewichtung: ein weicher Übergang mit einer Kosinuskurve">
      <Equation label="Mischung der Carry und Fresh Prognose"><span>p<sub>t</sub> = w<sub>t</sub> · p<sub>carry,t</sub> + (1 − w<sub>t</sub>) · p<sub>fresh,t</sub></span></Equation>
      <div className="weight-function"><div><span>1</span><b>w<sub>t</sub> =</b><span>½[1 + cos(π(t−12)/6)]</span><span>0</span></div><div className="weight-timeline"><i /><i /><i /><b>ST 1-12</b><b>ST 13-17</b><b>ab ST 18</b></div></div>
      <p className="math-note">Das Gewicht ist bis einschließlich Spieltag 12 exakt eins und ab Spieltag 18 exakt null. Nur im Übergangsfenster werden die beiden vollständigen 1-X-2-Verteilungen gemischt.</p>
      </DeepDive>
    </section>

    <section className="math-section" id="inference">
      <div className="math-section__heading"><div><div className="eyebrow">05 · Viele plausible Fußballwelten</div><h2>Eine Prognose. Viele mögliche Ausgänge.</h2></div></div>
      <div className="chapter-lead"><p>Es gibt nicht nur einen Satz von Teamstärken, der zu den beobachteten Spielen passt. MCMC, eine Markov-Chain-Monte-Carlo-Methode, sammelt viele plausible Zustände. So fließt auch die Unsicherheit über die Stärke eines Teams in die Prognose ein.</p><p>Für diese Zustände berechnen wir mögliche Torergebnisse. Wir fassen Heimsiege, Remis und Auswärtssiege zusammen und mitteln ihre Wahrscheinlichkeiten. Am Ende steht eine Verteilung, die zusammen 100 % ergibt.</p></div>
      <div className="probability-example" aria-label="Illustratives Beispiel: 50 Prozent Heimsieg, 28 Prozent Remis und 22 Prozent Auswärtssieg"><div><span>Ein Beispiel · keine aktuelle Prognose</span><strong>Favorit sein heißt nicht sicher gewinnen.</strong></div><div className="example-bar" aria-hidden="true"><span>1 · 50 %</span><span>X · 28 %</span><span>2 · 22 %</span></div><p>Bei 50 % Heimsieg bleibt in der anderen Hälfte der Fälle ein Remis oder Auswärtssieg. Die faire Quote für den Heimsieg wäre 1 ÷ 0,50 = 2,00.</p></div>
      <DeepDive title="Das Rechenverfahren: Single-Site Metropolis-Hastings">
      <div className="inference-flow"><article><h3>Proposal</h3><code>θ′ = θ + Normal(0, 0,06²)</code><p>Angriff und Abwehr werden an jedem lokalen Teamzustand einzeln vorgeschlagen.</p></article><article><h3>Acceptance</h3><code>α = min(1, posterior′ / posterior)</code><p>Nur die betroffene lokale Likelihood und die angrenzenden Zeitpriors müssen neu berechnet werden.</p></article><article><h3>Mixture update</h3><code>δ′ = 1 − δ</code><p>Der Bernoulli-Indikator jedes Spiels wird als eigener diskreter Zustand aktualisiert.</p></article><article><h3>Identifikation</h3><code>Σa + Σd = 0</code><p>Nach jeder Iteration wird der globale Leveldrift entfernt. Warm Starts beschleunigen aufeinanderfolgende Stichtage.</p></article></div>
      </DeepDive>
    </section>

    <section className="math-section math-section--dark" id="score">
      <div className="math-section__heading"><div><div className="eyebrow">06 · Der Test an der Realität</div><h2>Wie gut ist das alles?</h2></div></div>
      <div className="chapter-lead"><p>Eine gute Geschichte macht noch keine gute Prognose. Im Backtest gehen wir die Saison chronologisch durch: Erst wird mit den bis dahin verfügbaren Spieldaten gerechnet, dann mit dem späteren Ergebnis verglichen.</p><p>Der <strong>Ranked Probability Score</strong> bewertet die gesamte 1-X-2-Verteilung. Kleinere Werte sind besser. In den hier gezeigten Auswertungen liegt unser Modell nahe am Markt, die Buchmacherquoten schneiden aber besser ab.</p></div>
      <div className="score-comparison" role="region" aria-label="Backtest-Ergebnisse" tabIndex={0}><table><caption>Modell und Markt im Vergleich · Ranked Probability Score ↓</caption><thead><tr><th scope="col">Auswertung</th><th scope="col">Spielraum V2</th><th scope="col">Markt</th><th scope="col">Abstand</th></tr></thead><tbody><tr><th scope="row">High Budget<small>2023/24 bis 2025/26</small></th><td>0,19797</td><td>0,19204</td><td>+3,1 %</td></tr><tr><th scope="row">Breite Bestätigung<small>11 Saisons</small></th><td>0,20559</td><td>0,19892</td><td>+3,35 %</td></tr></tbody></table></div>
      <DeepDive title="Die Berechnung: vom Torergebnisgitter zum RPS">
      <div className="technical-grid"><article><small>Forecast</small><h3>Diskretes Ergebnisgitter</h3><p>Für jedes Posterior-Sample wird ein Torergebnisgitter von 0 bis 5 aufgebaut; die letzte Zelle enthält den jeweiligen Poisson-Tail. Eine Dixon-Coles-Korrektur verändert die vier niedrigen Ergebnisse 0:0, 0:1, 1:0 und 1:1.</p><Equation label="Heimsiegwahrscheinlichkeit"><span>P(H) = Σ<sub>x&gt;y</sub> p(x,y), &nbsp; P(X) = Σ<sub>x=y</sub> p(x,y)</span></Equation><p>Die drei Wahrscheinlichkeiten werden über alle gespeicherten MCMC-Samples gemittelt. Faire Quote: <code>q = 1/p</code>.</p></article><article><small>Scoring Rule</small><h3>Ranked Probability Score</h3><Equation label="Ranked Probability Score"><span>RPS = ½[(p<sub>H</sub>−o<sub>H</sub>)² + (p<sub>H</sub>+p<sub>D</sub>−o<sub>H</sub>−o<sub>D</sub>)²]</span></Equation><p>Der RPS berücksichtigt die Ordnung Heim, Remis, Auswärts und bewertet die komplette Verteilung. Niedriger ist besser; eine bloße Trefferquote würde Konfidenz und Kalibrierung ignorieren.</p></article></div>
      </DeepDive>
    </section>

    <section className="story-ending"><div className="eyebrow">Mit diesem Blick zurück zum Spieltag</div><h2>Der Fußball bleibt offen.<br /><em>Die Einschätzung wird genauer.</em></h2><p>Verletzungen, Aufstellungen und Trainerentscheidungen sind keine eigenen Eingaben dieses Modells. Gerade am Saisonanfang wiegt das Vorwissen schwer. Die Prozentwerte sind deshalb eine begründete Einschätzung mit Unsicherheit.</p><p>Schau beim nächsten Spiel auf alle drei Ausgänge. Nicht nur darauf, wer die größte Zahl neben seinem Namen hat.</p><Link className="story-cta" href="/">Mit diesem Wissen zum Spieltag <span aria-hidden="true">↗</span></Link><a className="ending-paper" href="https://doi.org/10.1111/1467-9884.00243" target="_blank" rel="noopener noreferrer">Weiterlesen: Rue &amp; Salvesen (2000) ↗</a></section>
  </main>;
}
