# Exogene PT-Verspätungen und Routing mit Echtzeitdaten

Stand: 2026-11-26. Status: laufende Entwurfsdiskussion.
Dieses Dokument wird während des Gesprächs fortgeschrieben.

## Ziel und Arbeitsweise

Exogene Störungen sollen die tatsächliche Ausführung von PT-Fahrten in Rust verändern.
Passagiere sollen verfügbare Informationen darüber für neue Routenentscheidungen nutzen
können. Der externe Java-Router soll dafür aktualisierbare, reproduzierbare
Informationsstände verwenden.

Wir unterscheiden ausdrücklich zwischen gemeinsam festgehaltenen Arbeitsrichtungen,
offenen Entscheidungen und Vorschlägen des Assistenten. Die unten vorgeschlagenen
Implementierungsschritte und Tests sind noch keine beschlossene Umsetzung.

Pro Gesprächsschritt klären wir möglichst eine zusammenhängende Entscheidung und halten
danach Ergebnis, Begründung, Konsequenzen und passende Tests fest.

Leitlinie des Nutzers (2026-11-19): Es soll möglichst wenige synchrone Punkte geben, an
denen die Simulation darauf warten muss, dass Reisezeiten und Prognosen aktualisiert werden.

## Bisheriger Gesprächsstand

| Punkt | Arbeitsstand | Noch zu klären |
| --- | --- | --- |
| 1. Eingabe und Verteilung | Das Driver-Beispiel in D01 verwendet eine Störungswahrscheinlichkeit je Linie, eine gleichverteilte Wahl des Ankunftshalts und eine exponentielle Zusatzfahrzeit. Bei einer beobachteten Schwelle je Linie wird die mittlere Zusatzfahrzeit für das Szenario vorgegeben und die Störungswahrscheinlichkeit daraus geschätzt. Seit 2026-11-26 (M1) gibt es feste Störungswerte je Departure als Attribute `delayStopIndex`, `arrivalDelayOffset` und `departureDelayOffset` (D01, „Umsetzung in M1“). | Konkrete Szenariowerte, Kalibrierung im Simulationslauf, Eingabeformat für gezogene Werte. |
| 2. Fahrzeugausführung | Variante A ist entschieden. Der Driver zieht Störungswerte vor Fahrtbeginn und schreibt die tatsächlichen Fahrzeugzeiten während der Fahrt fort. Unterschiedliche Driver-Typen können Störungsmodelle verschiedener Komplexität abbilden. Seit 2026-11-26 umgesetzt (M1): `StopDelayDriver` für feste Störungen an einem Halt; Aufholen nach den bestehenden Zeitregeln. | Weitere Driver-Typen für gezogene Werte. |
| 3. Information und Prognose | Kernentscheidung bestätigt: Für den ersten Stand werden Ankunfts-/Abfahrtsbeobachtungen übertragen; unbekannte zusätzliche Boardingdauer entfällt in der optimistischen Prognose. Bekannte Zeitgrenzen werden eingehalten. Arbeitsrichtung seit 2026-11-19: Rust berechnet die Prognose in einem nebenläufigen Snapshot-Thread, nur aus dem Event-Strom und mit denselben Zeitregeln wie die Ausführung (D03). | Fortschreibung bei ausgebliebenen Ereignissen; Zeitbedarf des Snapshot-Threads messen. |
| 4. Java-Router | Nichtüberholung innerhalb derselben TransitRoute ist vom Nutzer als Vertrag zugesichert und in matsim-rust umgesetzt (f638bd5f). Der Router darf diese Ordnung voraussetzen. Seit 2026-11-19 erhält er die prognostizierten Zeiten je Fahrt und Halt von Rust und routet auf der genannten Version. | Seit 2026-11-19 entschieden: Umbau von SwissRailRaptor in einem Branch von matsim-libs. Seit 2026-11-20 umgesetzt und committet (B1–B4): Zeit-Schnittstelle `RaptorTimetable`, Option `useTimetableUpdates`, versionierte Zeiten mit einer Zeile je Fahrt, Auswahl der Version je Anfrage über einen per Guice injizierten Provider; Protokoll im Branch `ph/timetable-updates` von matsim-schemas (A2); keine Departure in der Antwort; Snapshot 0 einmal beim Start, Freigabe alter Versionen durch Rust, asynchrones Warten mit Frist, Abbruch bei Vertragsverletzung (A1). |
| 5. Snapshots | Feste, konfigurierbare Intervalle in der Simulationszeit sind bestätigt. Alle Partitionen bestätigen Vollständigkeit. Die Anfragezeit bestimmt eine konkrete Snapshot-ID; eine Anfrage wartet bei Bedarf auf genau diesen Stand. Seit 2026-11-19 erzeugt Rust die Snapshots (Arbeitsrichtung); Versand je Intervall, Änderungen je Fahrt und die Grenzkonvention mit Grace Gap g als Szenarioparameter sind bestätigt (D03). | Werte für Δ und g und Anwendung von Antworten. Seit 2026-11-20 entschieden (A1 in D04): Initialisierung und Iterationswechsel, Fehler im Router, Freigabe alter Versionen. |
| 6. Passagierverhalten | Auf ausdrücklichen Nutzerwunsch vertagt; Vorschläge zu Auslösern, Fahrtbindung und Antwortübernahme sind nicht beschlossen. | Entscheidungspunkte, Boarding, Routenwechsel und laufende Anfragen (D05/D06). |
| Umsetzung und Tests | Inkrementelle Umsetzung und automatisierte Rust-Java-Tests in GitHub CI sind ausdrücklich Teil der Planung. | Reihenfolge, Java-Artefakt, Testprozess und verbindliche Prüfungen. |

## Vertagte fachliche Entscheidungen

Die Grundrichtung für Driver, Prognose, Snapshots und Nichtüberholung ist geklärt.
Am 2026-11-13 vertagt der Nutzer ausdrücklich die nachfolgend aufgeführten
verbleibenden fachlichen Fragen. Sie werden für eine spätere Fortsetzung
festgehalten. Die Vorschläge sind unentschieden und gelten nicht als vereinbarte
Standardwerte oder Verhaltensregeln.

| Vertagte Entscheidung | Offene Frage | Bisheriger, unbestätigter Diskussionsvorschlag |
| --- | --- | --- |
| Auslöser für Neurouting (D05) | Vor Reisebeginn, beim Umstieg, während des Wartens oder bereits im Fahrzeug? | Zunächst vor Reisebeginn und nach dem Aussteigen bei einem Umstieg; zusätzliche Auslöser später ergänzen. |
| Verbindlichkeit des Routerergebnisses (D05) | Muss genau die genannte Departure genommen werden, oder ist die nächste passende Fahrt derselben Route erlaubt? | Route und bediente Halte verbindlich berücksichtigen; unter dem Nichtüberholungsvertrag eine passende Alternative derselben Route prüfen, ohne versehentlich eine andere Route derselben Linie zu wählen. |
| Übernahme von Antworten und Fehlerverhalten (D06) | An welchem Simulationszeitpunkt wirkt eine Antwort? Was geschieht bei fehlender Antwort oder fehlender Verbindung? | Ergebnis an einem festgelegten Entscheidungspunkt übernehmen und erforderlichenfalls rechnerisch darauf warten; technische Laufzeit darf die fachliche Entscheidung nicht verschieben. Technische Fehler und die gültige Antwort „keine Verbindung“ getrennt behandeln. |
| Exogene Störungen (D01 und vertagter Punkt 1) | Welche Störungsmodelle, Eingaben, Verteilungen und Ziehungen je Iteration sollen verwendet werden? | D01 beschreibt eine einmalige Zusatzfahrzeit als Beispiel für einen Driver-Typ. Für den ersten Test einen festen Störungswert verwenden. |

Weitere technische Konkretisierungen können auf Grundlage der bestehenden Verträge
ausgearbeitet werden: die genaue Snapshot-Grenzkonvention, das Nachrichtenschema,
Versionskennungen, Datenlayout, Lebensdauer alter Snapshots und parametrierbare
Intervalllänge. Dabei müssen die vereinbarten fachlichen Regeln erhalten bleiben.
Für Transferoptimierungen zwischen verschiedenen Routen sind die Voraussetzungen
zu prüfen; der Nichtüberholungsvertrag innerhalb einer Route wird nicht ausgeweitet.

Für CI bleiben vor allem Umsetzungsaufgaben: den tatsächlichen Java-Service und
seinen Versionsstand identifizieren, einen selbststartenden kleinen Kopplungstest
bereitstellen und ihn auf Pull Requests ausführen. Der Vorschlag ist, dies als M0
vor dem größeren Router-Umbau aufzubauen. Rust-Komponententests und die Vorarbeiten
an Nichtüberholung können davon unabhängig erfolgen.

## Verifizierter Ausgangszustand (Analyse vom 2026-11-12)

- Der `PlannedDriver` bestimmt Ankunfts- und Abfahrtszeiten. Eine verspätete Abfahrt
  verschiebt die nächste Ankunft; kürzere Aufenthalte können Verspätung abbauen.
- Die `TransitEngine` führt diese Zeiten aus und emittiert Fahrzeug- und Fahrgast-Events.
  Die vorhandenen Ankunfts-/Abfahrts-Events haben ein `delay`-Feld, das die Engine bisher
  beim Erzeugen auf dem Standardwert belässt.
- Linie, Route, Routenhalt und Departure besitzen bereits Attribute.
- Der bestehende externe Routing-Service unterstützt `GetRoute` und `Shutdown`.
  Ein Update-/Snapshot-Vertrag gehört bisher nicht dazu.
- Die adaptive Passagierlogik delegiert Boarding derzeit an die Prüfung von Linie
  und verbleibenden Halten; die konkrete Departure ist kein Boarding-Kriterium.
- Jede Departure hat in der fahrplanbasierten Simulation ein eigenes Fahrzeug.
  Eine Verspätungsübertragung zwischen Fahrten desselben Umlaufs wird dadurch nicht modelliert.
- In `tests/simulation/pt.rs` sind `pt_adaptive_with_access_egress` und
  `pt_adaptive_with_dummy` mit `#[ignore]` deaktiviert. Sie erwarten einen separat
  gestarteten Routing-Service auf `http://localhost:50051` und starten ihn nicht selbst.
  Die gemeinsame Hilfsfunktion führt die Simulation aus, enthält aber keine ausdrückliche
  Prüfung einer erwarteten Route oder Ankunftszeit.
- Der aktuelle lokale CI-Workflow führt Rust-Tests aus und enthält keinen Schritt,
  der den Java-Router bereitstellt oder startet. Am Workflow bestehen bereits Änderungen
  des Nutzers; dieses Dokument verändert ihn nicht.
- Die zuvor betrachtete Java-Upstream-Implementierung verwirft vorbereitete Daten bei
  `TransitScheduleChangedEvent`. Sie verwendet gemeinsame Halte-Offsets, sortierte
  Abfahrten sowie Transferoptimierungen mit zeitlichen und Nichtüberholungsannahmen.
  Die tatsächlich einzusetzende Java-Version und der bisher verwendete Service müssen
  noch identifiziert werden.

## Gesprächsfolge für eine spätere Fortsetzung

1. Driver: Rahmenentscheidung getroffen (D01, Variante A); genaue Störungssemantik bleibt offen.
2. Prognose: Kernentscheidung getroffen (D02); seit 2026-11-19 in Rust, Zeitregeln aus dem Code abgeleitet. Ausgebliebene Ereignisse bleiben offen.
3. Snapshots: Kernvertrag bestätigt (D03); seit 2026-11-19 erzeugt Rust die Snapshots. Versand je Intervall, Änderungsformat und Grenzkonvention mit Grace Gap sind bestätigt; Werte für Δ und g, Fehlerbehandlung und Antwortübernahme bleiben offen.
4. Router: Nichtüberholung innerhalb einer Route ist zugesichert (D04); Datenmodell, Prognoseordnung und Transfers zwischen Routen weiter klären.
5. Passagiere: Auslöser und Verbindlichkeit der Route (D05), Antwortübernahme und Fehlerfälle (D06) sind auf Nutzerwunsch vertagt.
6. Eingabe/Verteilungen: D01 beschreibt die Ziehungen und die Kalibrierung aus dem
   Paper-Entwurf. Konkrete Szenariowerte und Eingabeformat bleiben offen.
7. Umsetzungsschritte und CI anhand dieser Entscheidungen abschließend ordnen.

Testfälle und umsetzbare Zwischenschritte werden bei jeder Entscheidung ergänzt.

## Entscheidungen und offene Fragen

### D01: Vorab gezogene Störungswerte mit laufender Zeitfortschreibung

Entschieden am 2026-11-13: Der Nutzer bestätigt ausdrücklich Variante A.

- Der Driver zieht seine exogenen Störungswerte vor Fahrtbeginn und hält sie für
  die Ausführung bereit. Während der Fahrt werden diese Werte nicht erneut gezogen.
- Die tatsächlichen Ankunfts- und Abfahrtszeiten berechnet er weiterhin während der
  Fahrt aus Fahrplan, vorbereiteten Störungswerten, tatsächlichem vorherigem Zustand
  und den jeweils geltenden zeitlichen Constraints.
- Es wird kein vor Fahrtbeginn endgültig festgelegter Ankunfts-/Abfahrtszeitplan gewählt.

Konsequenz: Die Zufallsziehungen sind von der anschließenden Zeitfortschreibung
getrennt. Ein Partitionswechsel muss die vorbereiteten Werte beziehungsweise den
für ihre weitere Anwendung nötigen Zustand erhalten. Die laufende Zeitfortschreibung
muss auch den in D04 zugesicherten Nichtüberholungsvertrag einhalten.

Die genaue Bedeutung der Störungswerte, die Aufholregel, die Eingabe und die
Verteilungen hängen vom jeweiligen Störungsmodell ab. Die Informationsregel für
vorab gezogene Werte steht in D02.

Vorgeschlagene Abnahmetests für diese Entscheidung:

- Mit einem kontrollierten Ziehungsmodell prüfen, dass alle vorgesehenen Ziehungen
  vor Fahrtbeginn stattfinden und während der Fahrt keine weiteren hinzukommen.
- Die Zeitfortschreibung zunächst mit festen Störungswerten prüfen; Nullstörung,
  tatsächliche vorherige Abfahrt und zeitliche Constraints gezielt abdecken.
- Bei einem Partitionswechsel vorbereitete Werte und ihren Anwendungszustand
  erhalten; kein erneutes Ziehen und keine doppelte Anwendung einer Störung.
- Bei Einführung der stochastischen Profile gleiche Ergebnisse für denselben Seed
  und fachlichen Kontext prüfen, unabhängig von der Reihenfolge anderer Fahrten.

#### Driver-Beispiel für die S-Bahn

Arbeitsrichtung vom 2026-11-25. Unterschiedliche Driver-Typen bilden unterschiedliche
Störungsmodelle und Komplexitätsstufen ab. Eine Fahrt wird von einer Instanz des gewählten
Typs ausgeführt. Für das folgende Beispiel bietet sich die Zeitfortschreibung des
`PlannedDriver` als Grundlage an. Die Auswahl des Typs je Fahrt und das Eingabeformat
sind offen.

**Ziehung vor Fahrtbeginn.** Für das Driver-Beispiel gelten die drei Ziehungen
aus dem Abschnitt «Delay Model» des Paper-Entwurfs.

1. Je Fahrt $T$ entscheidet der Bernoulli-Indikator $D_T$, ob eine Störung eintritt.
   Die Wahrscheinlichkeit $p_{L(T)}$ ist für alle Fahrten der Linie $L(T)$ gleich.
2. Bei $D_T=1$ zieht der Driver den ersten betroffenen Ankunftshalt $H_T$ gleichverteilt
   aus den Ankunftshalten der Route $R(T)$. $N_R$ zählt die Ankunftshalte nach dem
   Ursprung. Der Index $H_T=1$ bezeichnet die erste Ankunft nach der Startabfahrt.
   Die Störung wirkt auf die Fahrzeit des Abschnitts unmittelbar vor dem gezogenen Halt.
3. Der Driver zieht die Zusatzfahrzeit $X_T$ aus einer Exponentialverteilung mit
   Mittelwert $\mu$. Bei einer Störung gilt dieselbe Verteilung für jeden möglichen
   Wert von $H_T$.

Eine Gewichtung nach planmäßiger Fahrzeit ist eine alternative Wahl des Abschnitts.
Sie liefert bei gleich langen Abschnitten dieselbe Ziehung wie die Gleichverteilung.
Eine von der Gesamtdauer der Fahrt abhängige Störungswahrscheinlichkeit ist eine
weitere Variante. Eine exogene Startverspätung wäre ein eigener Störungsfall
an der ersten Abfahrt.

**In der Ausführung** verlängert die Instanz die Fahrt über den gewählten Abschnitt einmalig
um den gezogenen Wert. Ausgangspunkt ist die tatsächliche Abfahrt am vorherigen Halt.
An den folgenden Halten greifen die bestehenden Zeitregeln. Ein kürzerer Aufenthalt kann
Verspätung abbauen. Die Nichtüberholung innerhalb derselben `TransitRoute` kann Verspätung
auf Folgefahrten übertragen. Ein Partitionswechsel erhält den gezogenen Abschnitt, die
Zusatzzeit und den für die einmalige Anwendung nötigen Zustand. Für die Prognose zählen
die beobachteten Auswirkungen auf die Ankunfts- und Abfahrtszeiten (D02).

##### Analytische Kalibrierung

Für die analytische Rechnung wirkt $X_T$ in gleicher Höhe vom ersten betroffenen
Halt bis zum Fahrtende. Alle übrigen Ankünfte liegen im Plan. Das Aufholen am Halt
und die Übertragung auf Folgefahrten werden bei der Ausführung in Rust berücksichtigt.

Eine Fahrt $T$ hat $n_T=N_{R(T)}$ Ankünfte. Eine Störung vor Halt $H_T$ betrifft
$n_T-H_T+1$ Ankünfte. Bei gleichverteilter Wahl des Halts sind das im Mittel
$(n_T+1)/2$ Ankünfte. Der mittlere Anteil betroffener Ankünfte bei einer Störung
ist damit $c_T=(n_T+1)/(2n_T)$. Um daraus den erwarteten Anteil verspäteter
Ankünfte ab einer Schwelle $x>0$ zu berechnen, multiplizieren wir $c_T$ mit
der Wahrscheinlichkeit einer Störung und mit der Chance, dass deren Höhe
mindestens $x$ beträgt.

$$
r_{\ge x}^{T} = c_T\,p_{L(T)}\,e^{-x/\mu}.
$$

Für die Linienquote summieren wir die erwarteten Anzahlen verspäteter Ankünfte
über alle Fahrten der Linie und teilen durch die Gesamtzahl ihrer Ankünfte.
Dabei wird jede Fahrt mit ihrer Zahl an Ankünften gewichtet.

$$
r_{\ge x}^{L}=c_L\,p_L\,e^{-x/\mu},\qquad
c_L=\frac{\sum_{T:\,L(T)=L}n_T c_T}{\sum_{T:\,L(T)=L}n_T}.
$$

**Eine beobachtete Schwelle je Linie.** Wir geben $\mu$ für das Szenario vor
und teilen die beobachtete Verspätungsquote der Linie durch $c_L e^{-x/\mu}$,
um $p_L$ zu schätzen. Bei kleinerem $\mu$ braucht es häufiger Störungen, um
dieselbe Quote zu erreichen. Ergibt die Rechnung $p_L>1$, kann die Linie
den beobachteten Wert mit diesem $\mu$ im analytischen Modell nicht erreichen.

**Zwei netzweite Schwellen.** Bei gemeinsamem $\mu$ für alle ausgewerteten
Linien und identischer Beobachtungsbasis kürzt sich beim Verhältnis der Quoten
der mit den Ankunftszahlen gewichtete Faktor aus $c_L$ und $p_L$ heraus.
Aus dem Verhältnis lässt sich $\mu$ schätzen. Anschließend genügt wieder
eine beobachtete Quote je Linie zur Schätzung von $p_L$.

Für den Abgleich ist dieselbe Definition der Pünktlichkeit zu verwenden wie in
der jeweiligen Quelle. Die Formeln oben zählen alle Ankünfte der betrachteten
Fahrten. Für Berichte mit ausgewählten Messhalten werden sowohl die Quote als
auch der Anteil betroffener Ankünfte über diese Messhalte berechnet. Für die
BVG wird die Kennzahl über die gewerteten Abfahrten nachgebildet.
[BVG-Vertragsdefinition, S. 19](https://www.parlament-berlin.de/adosservice/19/Haupt/vorgang/h19-1891.C-v.pdf#page=19)

##### Rechenbeispiel mit den S-Bahn-Quoten

Für 2024 meldet die S-Bahn 93,76 % Pünktlichkeit an der Vier-Minuten-Schwelle
und 96,78 % an der Sechs-Minuten-Schwelle. Das entspricht 6,24 % der Ankünfte
mit mindestens vier und 3,22 % mit mindestens sechs Minuten Verspätung. Aus
dem Verhältnis der beiden Quoten ergibt sich unter der Annahme eines gemeinsamen
exponentiellen Modells der Mittelwert $\mu=2/\ln(6{,}24/3{,}22)\approx3{,}02$ Minuten.
[S-Bahn-Jahreswerte 2024](https://pardok.parlament-berlin.de/starweb/adis/citat/VT/19/SchrAnfr/S19-21315.pdf)

In einer Beispiellinie mit 1.000 Fahrten zu je 20 Ankünften gilt $c_T=c_L=0{,}525$.
Eine Störung auf dem Abschnitt vor der neunten Ankunft betrifft 12 der 20
Ankünfte. Über alle Abschnitte sind es im Mittel 10,5. Setzt man für diese
Beispiellinie die netzweite Vier-Minuten-Quote von 6,24 % ein, ergibt sich
eine Störungswahrscheinlichkeit von 44,6 %. Für eine konkrete Linie gehen
ihre eigene beobachtete Quote und ihr eigener Faktor $c_L$ ein.

Eine Vergleichsvariante zieht vier Minuten plus eine exponentielle Zusatzzeit
mit demselben Mittelwert. Damit erreichen alle betroffenen Ankünfte die
Vier-Minuten-Schwelle und eine Störungswahrscheinlichkeit von 11,9 % genügt.

| Gezogene Zusatzfahrzeit bei einer Störung | Fahrten mit Störung im Rechenbeispiel | Ankünfte ab 1 Minute Verspätung im Rechenbeispiel |
| --- | ---: | ---: |
| Exponentiell, Mittelwert rund 3,0 min | 44,6 % | 16,8 % |
| 4 min plus exponentiell, Mittelwert des Zusatzanteils rund 3,0 min | 11,9 % | 6,24 % |

Beide Varianten treffen im Rechenbeispiel dieselben Quoten bei vier und sechs Minuten. Die
deutlich verschiedenen Anteile ab einer Minute können sich auf knappe Umstiege auswirken.
Eine Ein-Minuten-Quote aus derselben Periode und mit gleicher Beobachtungsbasis könnte
die Varianten eingrenzen. [VBB S-Bahn-Pünktlichkeit](https://unternehmen.vbb.de/qualitaet-im-oepnv/qualitaet-berliner-s-bahn/)

**Erster Versuch in Rust.** M1 kann die Ausführung mit einer festen Zusatzfahrzeit von
beispielsweise fünf Minuten auf einem festgelegten Abschnitt prüfen. Abgedeckt werden
Weitergabe, möglicher Abbau am Halt, Wartezeit der Folgefahrt, Partitionswechsel und der
Fall ohne Störung. Für die stochastische Kalibrierung dienen die analytischen Werte als
Startpunkte. Bei vorgegebenem $\mu$ wird $p_L$ an der Quote der tatsächlich simulierten
Ereignisse eingestellt. Liegen zwei vergleichbare Schwellen vor, kann auch $\mu$ anhand
der simulierten Quoten angepasst werden. Ein- und Zwei-Minuten-Quoten und Taktlücken
zeigen, wie sich die Varianten darüber hinaus unterscheiden.

#### Umsetzung in M1 (2026-11-26)

Vom Nutzer am 2026-11-26 entschieden und in matsim-rust umgesetzt: PR
matsim-vsp/matsim-rust#362 (Branch `ph/exogenous-pt-delays`) auf dem Szenario-PR
matsim-vsp/matsim-rust#361, der am 2026-11-26 gemergt wurde.

- **Eingabe:** Eine Departure kann feste Störungen an einem Halt ihrer Route haben, als
  Attribute der Departure analog zu den Offsets der Route: `delayStopIndex` (Integer, Position
  des Halts in der Route ab 0), `arrivalDelayOffset` und `departureDelayOffset` (Strings
  `"HH:MM:SS"`, beide optional, Standard 0). `TransitSimSchedule::build` liest sie als
  `StopDelay` und bricht ab bei einem Offset ohne Index, einem Index außerhalb der Route
  oder einem anderen Format. Ein Index ohne Offsets ergibt keine Störung.
- **Bedeutung an Halt i**, jeweils gegenüber den Zeitregeln ohne Störung: Die Ankunft ist
  die Ankunft nach den Zeitregeln plus `arrivalDelayOffset`. Bei i ≥ 1 ist das der Abschnitt
  vor Halt i wie im S-Bahn-Beispiel, bei i = 0 eine Startverspätung. Die Abfahrt ist
  max(Plan-Abfahrt, Ankunft) plus `departureDelayOffset`: Der Aufenthalt wird um diesen
  Wert länger, auch nach einer verspäteten Ankunft. Die Verspätung, die das Fahrzeug
  weiterträgt, misst der Driver weiter gegen den unveränderten Fahrplan. So wirkt die
  Störung an den folgenden Halten nach, und ein kürzerer Aufenthalt baut sie ab.
- **Driver-Typ:** `StopDelayDriver` enthält einen `PlannedDriver` und delegiert an ihn. Er
  addiert die Störungen dort, wo die Zeitregel die Ankunft an Halt i bzw. die Abfahrt von
  dort ergibt. Weil die Halt-Position nur einmal i wird, wirkt jede Störung genau einmal.
  Der wartende Driver wählt ihn beim Start der Fahrt, wenn die Departure eine Störung hat;
  sonst bleibt es der `PlannedDriver`.
- **Events:** `VehicleArrivesAtFacility` und `VehicleDepartsAtFacility` tragen jetzt
  `delay` gegenüber dem Fahrplan wie in MATSim. In der Berlin-Referenz (0,1pct, bis 10:00)
  haben 1.041 von 975.600 Halte-Events eine Verspätung (775 × 1 s, 175 × 61 s, 91 × 121 s),
  sonst sind die Events unverändert.
- **Tests:** Unit-Tests für Ankunfts- und Abfahrtsstörung, Störung am ersten und am letzten
  Halt, beide am selben Halt, die Auswahl des Drivers und die Prüfungen der Attribute. Im
  Szenario `pt_delays` laufen die fünf Varianten des README und
  `local_0800_late_before_center` mit 1 und 2 Partitionen gegen Referenz-Events. In der
  letzten wird die Störung beim Abfahren in hub auf Partition 1 wirksam, nachdem der Driver
  von Partition 0 kam.

### D02: Ort und Bedeutung der Prognose

Ursprüngliche Nutzerpräferenz: Prognose im Router; Übertragung kompakter Beobachtungen.
Am 2026-11-19 geändert: Die Präferenz hatte keinen fachlichen Grund, sondern sollte einen
Engpass in der Simulation vermeiden. Arbeitsrichtung ist nun, dass Rust die Prognose in einem
nebenläufigen Snapshot-Thread berechnet und den Routern fertige Zeitstände schickt (D03).
Die folgenden Regeln zur Information und zur optimistischen Prognose gelten unverändert.

Kernentscheidung am 2026-11-13 bestätigt: Für den ersten Stand werden fachlich
Ankunfts- und Abfahrtsbeobachtungen übertragen. Die noch unbekannte zusätzliche
Boardingdauer wird in der Prognose weggelassen; bekannte Zeitgrenzen bleiben
verbindlich. Zusätzliche Meldungen zu Fahrgastzahlen, Warteschlangen oder laufendem
Boarding sind für diesen ersten Stand nicht vorgesehen. Kontrollnachrichten zur
Vollständigkeit von Snapshots sind davon unabhängig erforderlich (D03).

Vorgesehene Beobachtungsdaten: Fahrtidentität, Position des Halts in der Haltefolge,
Beobachtungszeit und tatsächliche Zeit beziehungsweise Verspätung. Seit 2026-11-19 gehen
diese Beobachtungen innerhalb des Rust-Prozesses an den Snapshot-Thread, der den
unveränderten Fahrplan kennt und daraus die Prognosen ableitet (D03).

Diskussion am 2026-11-13: Der Nutzer weist darauf hin, dass das Aufholen von
Verspätung von der Dauer des Fahrgastwechsels abhängt. Aktuell dauert Boarding 0 s;
bei beispielsweise 1 s je Fahrgast hängt die gesamte Dauer zusätzlich von der
Zahl und Ankunftsfolge der Fahrgäste ab. Eine solche Änderung darf nicht zu
unbemerkt unterschiedlichen Modellregeln in Rust und Java führen. Der Nutzer
schlägt deshalb eine möglichst optimistische Prognose vor.

#### Bestätigter Ansatz: optimistisch unter bekannten Bedingungen

Der Ansatz ist bestätigt; die folgende Formel und die konkreten Regeln sind noch
auszugestalten. Optimistisch bedeutet: bekannte Verspätung fortschreiben,
mögliche Erholung nach den geltenden Zeitregeln berücksichtigen
und keine zusätzliche Haltezeit für noch unbekannten zukünftigen Fahrgastwechsel
ansetzen. Noch unbeobachtete zukünftige Störungen werden nicht aus der Vorabziehung
des Drivers übernommen. Bereits bekannte Tatsachen oder zwingende Mindestzeiten
dürfen durch diese Annahme nicht unterschritten werden.

Konsistenz bedeutet hier die Einhaltung derselben bekannten Zeitregeln und desselben
Informationsstands. Sie bedeutet keine garantierte Gleichheit von Prognose und
späterem Fahrzeugverlauf bei unbekannter Nachfrage.

Vereinfachte Regel für einen noch nicht abgefahrenen Halt:

`d_prognose = max(d_plan, a_prognose + h_min, bekannte_frueheste_abfahrt)`

Dabei ist `h_min` eine im Ausführungsmodell tatsächlich garantierte Mindesthaltezeit,
gegebenenfalls 0 s. Eine Boardingdauer von 1 s je Fahrgast ist für sich genommen
keine feste Mindesthaltezeit von 1 s an jedem Halt. Die Zahl der Vorgänge und die
Bedienungsregel bestimmen die zusätzliche Dauer. Soweit solche Vorgänge dem
Prognosemodul bereits bekannt sind, müssen daraus folgende Zeitgrenzen berücksichtigt
werden. Verbindliche Zeiten für den Fahrgast der Routenanfrage, insbesondere eigenes
Ein-/Aussteigen und Umsteigen, müssen außerdem bei der Anschlussprüfung beachtet
werden; Optimismus ist keine Freigabe, diese auf 0 zu setzen.

#### Aus dem Code abgeleitete Zeitregeln (2026-11-19)

`PlannedDriver` und `TransitEngine` legen den deterministischen Teil der Ausführung
bereits fest (`apply_stop_time_constraints`, `PlannedDriver::notify_stop_departed`,
Abfahrt in der `TransitEngine`, Nichtüberholung aus f638bd5f). Mit Plan-Ankunft `s_a(i)`
und Plan-Abfahrt `s_d(i)` am Halt i und dem Vorgänger derselben Route gilt:

- `a(i+1) = max(s_a(i+1) + (d(i) - s_d(i)), d(i) + 1 s, a_vorgaenger(i+1))`
- `d(i) = max(s_d(i), a(i), d_vorgaenger(i))`

`d(i) + 1 s` ist die Ankunft frühestens im nächsten Zeitschritt. Am ersten Halt ist die
Ankunft der Plan-Ankunft oder der spätere Startzeitpunkt. Ein Fahrzeug kann im selben
Zeitschritt wie sein Vorgänger ankommen und abfahren, in der Reihenfolge der Events nach ihm
(beobachtet in der Variante `local_0800_late` von `pt_delays`, 2026-11-26).

Rechnet die Prognose in Rust, verwendet sie dieselben Funktionen wie die Ausführung.
Ohne Störungen und mit 0 s Boarding trifft sie die Ausführung dann genau. Snapshot 0 ist
deshalb der Fahrplan nach diesen Regeln, nicht der rohe Fahrplan. In Berlin v7.1 (1pct)
betrifft das nur 44 Halt-zu-Halt-Abschnitte mit 0 s Fahrzeit, über alle Departures
gezählt. Künftige Störungen und Fahrgastwechsel bleiben unbekannt und werden mit 0
angesetzt. Die vereinfachte Regel oben entspricht dem mit `h_min = 0`.

Beispiel: Planankunft 08:00, Planabfahrt 08:02, beobachtete Ankunft 08:01. Ohne
weitere bekannte Einschränkung und mit `h_min = 0` wird die Abfahrt um 08:02
prognostiziert. Verlängert der tatsächlich stattfindende Fahrgastwechsel den
Aufenthalt bis 08:02:10, darf die reale Abfahrt später liegen. Das ist eine
beabsichtigte Unsicherheit der Prognose, solange die bekannten Regeln eingehalten
wurden. Das Abfahrts-Event liefert anschließend die tatsächliche Abfahrt für
die Fortschreibung der folgenden Halte.

Wird auf einem späteren vollständigen Snapshot weiterhin beobachtet, dass das
Fahrzeug noch nicht abgefahren ist, darf seine prognostizierte Abfahrt nicht vor
der Zeitgrenze dieses Snapshots liegen. Die genaue Gleichzeitigkeit an der
Zeitgrenze wird in D03 festgelegt. Eine neue Beobachtung verändert die Prognose
in einem neuen Snapshot; veröffentlichte ältere Snapshots bleiben unverändert.

Diese Prognose ist eine optimistische Referenz unter festgelegten Annahmen, kein
Erwartungswert und keine Garantie für das Erreichen eines Anschlusses. Unbekannter
Fahrgastwechsel kann dazu führen, dass ein prognostizierter Anschluss tatsächlich
verpasst wird. Diese Abweichung soll später messbar sein.

Zusätzliche verbindliche Randbedingung gemäß D04: Die Prognosen erhalten die
zugesicherte Fahrtreihenfolge innerhalb einer Route. Eine bekannte Einschränkung
durch das vorausfahrende Fahrzeug wird auch bei optimistischer Behandlung
unbekannter Boardingdauer berücksichtigt.

#### Gemeinsame Regeln und überprüfbare Konfiguration

Nachtrag 2026-11-19: Erzeugt Rust die Prognose mit denselben Funktionen wie die Ausführung
(D03), ist ein sprachübergreifender Vertrag für die Prognoseregeln nicht mehr nötig. Der
folgende Vorschlag bleibt nur für Annahmen relevant, die der Java-Router selbst trifft, etwa
Umstiegs- und Einstiegszeiten des anfragenden Fahrgasts.

Vorschlag: Rust und Java verwenden eine gemeinsame, versionierte Beschreibung der
für die Prognose relevanten Zeitregeln und Parameter. Dazu gehören beispielsweise
Abfahrtsbindung an den Fahrplan, tatsächlich wirksame Mindesthaltezeiten und die
Zeitschritt-/Rundungsregeln. Änderungen an relevanten Boarding-/Alightingregeln
werden in diesem Modellvertrag sichtbar; die Behandlung unbekannter Nachfrage
bleibt eine explizite Annahme des Prognosemodells.

Beide Dienste bestätigen die verwendete Modell-/Konfigurationsversion; eine
inkompatible Kombination scheitert ausdrücklich. Gemeinsame kleine Testeingaben
mit erwarteten Ergebnissen prüfen die Regeln in beiden Sprachen. Gleiche
Konfigurationswerte allein beweisen noch keine gleiche Semantik.

Codeprüfung am 2026-11-13: `BOARDING_TIME` und `ALIGHTING_TIME` stehen in der
`TransitEngine` auf 0 s. Die Engine verschiebt eine fällige Abfahrt, solange
Fahrgastwechsel oder Türbelegung noch nicht abgeschlossen sind. Das Datenmodell
enthält `minimum_stop_duration`; im betrachteten Driver-/Engine-Ausführungspfad
wird dieses Feld derzeit nicht angewendet. Eine Prognose darf daraus nicht allein
eine zusätzliche zwingende Mindesthaltezeit ableiten. Eine spätere Einführung
muss Ausführung und Prognose gemeinsam berücksichtigen.

#### Vorgeschlagene Tests für die Prognose

- Ohne unbekannte Störung oder zusätzlichen Fahrgastwechsel stimmen Prognose und
  Ausführung bei identischen Eingangsdaten gemäß den festgelegten Zeitregeln überein.
- Tests mit 0 s und später 1 s Boardingzeit je Fahrgast sowie unterschiedlichen
  Fahrgastzahlen unterscheiden die gemeinsame Regel von der unbekannten Haltezeit.
  In gezielt konstruierten Fällen darf die optimistische Prognose vor der realen
  Abfahrt liegen; dieser Unterschied wird ausdrücklich erwartet und geprüft.
- Eine wirksame feste Mindesthaltezeit wird in beiden Modellen gleich berücksichtigt;
  eine Zeit je Fahrgast wird nicht fälschlich als feste Zeit je Halt interpretiert.
- Ein bereits bekannter frühester Abfahrtszeitpunkt und die Zeitgrenze eines
  vollständigen Snapshots werden nicht unterschritten.
- Nach einem Abfahrts-Event wird mit der beobachteten Abfahrt weitergerechnet;
  die Prognose auf dem alten Snapshot bleibt unverändert.
- Nicht kompatible Modell-/Konfigurationsversionen werden erkannt. Gemeinsame
  Testeingaben decken Abfahrt, Aufenthalt und Zeitrundung in Rust und Java ab.
- Prognoseabweichungen werden getrennt von Vertragsverletzungen erfasst; eine
  später beobachtete Abweichung darf den älteren Informationsstand nicht nachträglich ändern.
- Ergänzt am 2026-11-19 für die Prognose in Rust: Ohne Störungen und mit 0 s Boarding
  stimmt in jedem Snapshot jede Prognose eines künftigen Halteereignisses mit der Ausführung
  überein. Mit Störungen, die nur Zeit hinzufügen, liegt jede Prognose nicht nach der
  ausgeführten Zeit, weil alle Regeln nur aus `max` und `+` bestehen.
- Die Prognose ist eine Funktion des Event-Stroms: Dieselbe Event-Datei ergibt dieselben
  Snapshots, unabhängig von der Reihenfolge der Events innerhalb eines Intervalls.

Offen bleiben insbesondere:

- Genaue Ausgestaltung der bestätigten optimistischen Prognose und der Zeitfortschreibung.
- Gemeinsame Zeitregeln und Konfigurationsvertrag einschließlich späterer Änderungen.
- Wann gilt eine Störung als bekannt: bei Beobachtung am Halt, bei Störungsbeginn oder
  durch eine zusätzliche Informationsquelle?
- Was wird für Fahrzeuge angenommen, deren erwartete Ankunft bereits verstrichen ist?
- Wie werden neuere Beobachtungen und Iterationswechsel behandelt?

### D03: Vertrag für Snapshots

Kernvertrag am 2026-11-13 bestätigt: Feste, konfigurierbare Snapshot-Intervalle
in der Simulationszeit, Vollständigkeitsbestätigung aller Partitionen und eine
durch die Simulationszeit der Anfrage festgelegte Snapshot-ID. Ist der vorgesehene
Snapshot noch nicht verfügbar, wartet die Anfrage auf genau diesen Stand.

Der Vertrag betrifft den Router und die Event-Verarbeitung. Bei mehreren
Simulationspartitionen muss die Vollständigkeit der Datenlieferung koordiniert
werden. Seit 2026-11-19 übernimmt das ein Snapshot-Thread in Rust (siehe
„Arbeitsstand 2026-11-19“ unten).

Kernvertrag und noch zu konkretisierende Ausführungsdetails:

- Ein Snapshot hat eine eindeutige Identität einschließlich Lauf-/Iterationskontext
  und eine definierte Grenze in der Simulationszeit.
- Alle beteiligten Produzenten bestätigen, dass ihre Beobachtungen bis zu dieser
  Grenze vollständig geliefert sind. Der Eingang eines beliebigen letzten Events
  allein ist keine Vollständigkeitsgarantie.
- Der Router veröffentlicht einen unveränderlichen Informationsstand einschließlich
  der daraus abgeleiteten Prognosen.
- Eine Routenanfrage benennt genau diesen Stand; die Antwort bestätigt dessen Identität.
- Ein fehlender oder noch nicht verfügbarer Stand wird explizit behandelt.
  Ein stiller Wechsel auf den jeweils neuesten Stand wäre nicht deterministisch.
- Später eintreffende Updates verändern einen veröffentlichten Stand nicht rückwirkend.
- Ob Events genau auf einer Zeitgrenze dazugehören und in welcher Phase anschließend
  Routenanfragen gestellt werden, wird ausdrücklich festgelegt.
- Alte Snapshots können erst freigegeben werden, wenn keine Anfrage sie mehr benötigt.

Ein Snapshot allein garantiert noch keine deterministische Gesamtsimulation.
Auch der Zeitpunkt der Anwendung einer Antwort und die Behandlung gleichzeitig
stattfindender Fahrzeug-/Passagierereignisse müssen festgelegt werden (D06).

#### Bestätigter Ansatz: Zeitgrenzen und feste Anfragezuordnung

Snapshots werden an festen Grenzen in der Simulationszeit erzeugt.
Das Intervall ist konfigurierbar; ein konkreter Wert
wird später festgelegt. Alle Produzenten melden ihre Daten und den Abschluss bis
zur jeweiligen Grenze. Ein Snapshot wird erst nach vollständigem Eingang aller
Beiträge veröffentlicht, auch wenn ein Produzent keine fachlichen Ereignisse hatte.

Die zu verwendende Snapshot-ID wird aus der Simulationszeit der Anfrage bestimmt,
also aus dem Zeitpunkt der verfügbaren Information und nicht aus einem eventuell
späteren geplanten Reisebeginn. Sie hängt nicht davon ab, welcher Snapshot beim
Eingang der Anfrage gerade technisch verfügbar ist. Eine Anfrage für einen noch
nicht veröffentlichten, aber vorgesehenen Snapshot wartet auf genau diesen Stand;
Transport und Bearbeitung können weiterhin asynchron erfolgen. Details des
Wartens und der Antwortübernahme bleiben Teil des Gesamtvertrags.

Beispiel mit einem nur zur Illustration gewählten Intervall von 30 s: Eine Anfrage
um 08:00:45 verwendet den Snapshot mit Grenze 08:00:30. Sie verwendet diesen auch,
wenn eine neuere Version vor ihrer Bearbeitung veröffentlicht wird. Für Ereignisse
genau auf einer Grenze gibt es seit 2026-11-19 einen Vorschlag (siehe unten).

Die Vollständigkeit liefert auch Information ohne neues fachliches Ereignis:
Wurde eine Abfahrt um 08:02 prognostiziert, aber bis zur vollständigen Grenze
08:03 keine Abfahrt beobachtet, ist das Fahrzeug bis zu dieser Grenze noch nicht
abgefahren. Der Vorschlag ist, seine früheste prognostizierte Abfahrt auf diese
Grenze anzuheben und folgende Halte entsprechend fortzuschreiben. Diese Verwendung
ausgebliebener Ereignisse und ihre genaue Zeitsemantik sind noch zu bestätigen.
Aus einem älteren Snapshot lässt sich dagegen kein solcher Schluss für die Zeit
nach seiner Grenze ziehen.

#### Arbeitsstand 2026-11-19: Rust erzeugt die Snapshots

Arbeitsrichtung, vom Nutzer am 2026-11-19 bestätigt: Rust erzeugt die Snapshots
einschließlich der Prognose in einem nebenläufigen Thread. Die Java-Router erhalten
fertige Zeitstände und routen auf ihnen. Die frühere Präferenz „Prognose im Router“ sollte
nur einen Engpass in der Simulation vermeiden; ein nebenläufiger Thread vermeidet ihn
ebenfalls.

Gründe:

- Die Zeitregeln der Ausführung existieren bereits in Rust (D02, „Aus dem Code abgeleitete
  Zeitregeln“), ebenso die Reihenfolge der Fahrten einer Route (`DepartureSequenceInRoute`).
  Die Prognose verwendet dieselben Funktionen. Eine zweite Implementierung in Java und ein
  sprachübergreifender Modellvertrag entfallen.
- Rust verteilt Anfragen reihum auf mehrere Router (`RingIter`). Die Prognose wird einmal
  statt in jedem Router berechnet, und alle Router routen auf demselben Zeitstand.
- Der Router braucht keinen Zustand je Fahrt und kennt das Intervall nicht.

Der Snapshot-Thread sieht nur den Event-Strom, nie die vorab gezogenen Störungswerte des
Drivers (D01). Die Informationsregel aus D02 bleibt damit prüfbar, etwa indem man der
Prognose eine Event-Datei zuführt.

Die folgenden Einzelheiten hat der Assistent am 2026-11-19 vorgeschlagen. Der Nutzer hat
am selben Tag den Versand je Intervall (1.) und das Änderungsformat (3.) bestätigt und die
Grace Gap ergänzt (4.). Die Formel der Snapshot-ID, die Grenzkonvention und g als
Szenarioparameter hat der Nutzer ebenfalls am 2026-11-19 bestätigt. Offen bleiben die
Anhebung überfälliger Fahrten (2.) und die Werte für Δ und g.

1. Jede Partition sammelt die Ankunfts- und Abfahrts-Events ihrer PT-Fahrzeuge lokal. Nach
   Schritt kΔ − 1 schickt sie die Events des Intervalls zusammen mit der Meldung
   „vollständig bis kΔ“ als eine Nachricht über einen prozessinternen Kanal an den
   Snapshot-Thread. In Schritten ohne Grenze sendet sie nichts. Das hält die zusätzliche
   Arbeit im Mobsim-Schritt klein: P Nachrichten je Intervall statt je Zeitschritt.
2. Liegt diese Meldung von allen Partitionen vor, schließt der Thread Snapshot k. Er wendet
   die Beobachtungen in fester Sortierung an, hebt gegebenenfalls überfällige Fahrten auf die
   Grenze an (noch offen, siehe oben) und schreibt die Prognose fort.
3. Er schickt jedem Router über einen eigenen, geordneten Stream die Änderungen gegenüber
   Snapshot k − 1.
4. Eine Anfrage mit Simulationszeit `now` nennt die Snapshot-ID
   k = max(0, ⌊(now − g) / Δ⌋) einschließlich Iteration, mit der Grace Gap g (siehe unten).
   Rust berechnet sie; Δ und g stehen damit nur an einer Stelle. Ist Version k im Router
   noch nicht angewendet, wartet die Anfrage dort. Die Antwort bestätigt die verwendete
   Snapshot-ID.

Grenzkonvention: Snapshot k enthält alle Events mit Zeit < kΔ; Events genau zur Zeit kΔ
gehören zu Snapshot k + 1. Snapshot 0 enthält keine Events, also den Fahrplan nach den
Zeitregeln. Damit hängt ein Snapshot nie vom Schritt ab, in dem eine Anfrage gestellt wird.
Die Information einer Anfrage ist mindestens g und höchstens g + Δ alt. Ein Deadlock ist
ausgeschlossen: Eine Partition, die zur Zeit t ≥ kΔ in `blocking_recv` auf eine Antwort
wartet, hat ihre Nachrichten für alle Schritte bis t − 1 bereits gesendet. Jede andere
Partition kann daher Schritt kΔ − 1 abschließen, mit Nachbar-Synchronisation ebenso wie mit
globaler Synchronisation.

Grace Gap (vom Nutzer vorgeschlagen und am 2026-11-19 bestätigt): Snapshot k gilt erst ab kΔ + g. Anfragen
in [kΔ, kΔ + g) verwenden noch Snapshot k − 1. Simulation, Snapshot-Thread und Router haben so
g Zeitschritte, um Snapshot k zu schließen, zu verteilen und anzuwenden, bevor eine Anfrage
ihn braucht.

- Die Antwort muss erst zur Abfahrt vorliegen, also bei now + h mit dem Horizont h. Zwischen
  der Grenze kΔ und dem Zeitpunkt, zu dem die erste Antwort auf Snapshot k vorliegen muss,
  liegen damit mindestens g + h Zeitschritte. Ohne Grace Gap hängt dieser Puffer allein am
  Horizont. Bei h = 0, etwa bei einem späteren Neurouting beim Umstieg (D05), wäre jede
  Anfrage direkt nach einer Grenze synchron.
- Die Grace Gap fängt auch ab, dass Partitionen ohne globale Synchronisation einige
  Zeitschritte auseinanderliegen können, denn Snapshot k wartet auf die langsamste Partition.
- Die Zuordnung bleibt deterministisch, weil die Snapshot-ID nur von `now`, Δ und g abhängt.
  Ist Snapshot k zur Zeit kΔ + g noch nicht angewendet, wartet die Anfrage weiterhin. Das
  kostet dann Zeit, ändert aber kein Ergebnis.
- g ist zugleich ein Informationsverzug des Modells und verändert die Ergebnisse. g ist
  daher ein Szenarioparameter, kein Leistungsparameter, und darf nicht zur Laufzeit an
  gemessene Latenzen angepasst werden.
- Wahl von g: g / RTR Wandzeit sollte die Latenz von Snapshot-Thread, Netz und Anwenden im
  Router übersteigen. Geschätzte, nicht gemessene 1-2 ms ergeben bei RTR 50.000 etwa 50-100 s,
  bei RTR 10.000 etwa 10-20 s.
- Nicht abgedeckt ist die Routingzeit selbst. Eine Anfrage mit Abfahrt kurz nach `now` bleibt
  synchron, weil sie auf ihr eigenes Routing wartet. Das lässt sich nur über den Zeitpunkt
  der Anfrage lösen (D05).

Änderungsformat: je geänderter Fahrt Departure-ID, Index i des Halts in der Haltefolge und
die neuen Ankunfts- und Abfahrtszeiten ab Halt i bis zum Ende der Fahrt. Prognoseänderungen
wirken immer entlang der Fahrt nach vorn. Der Router hält seine Versionen per copy-on-write
je Route (D04). Den Halt identifiziert der Index, nicht die Facility-ID, weil eine Route
einen Halt mehrfach bedienen kann.

Warum Änderungen statt vollständiger Snapshots: Die Nachrichtengröße ist vor allem eine Frage
der Verarbeitung, weniger des Netzes. gRPC läuft auf dem Cluster über TCP auf InfiniBand
(IPoIB), nicht über RDMA. Die Latenz liegt damit voraussichtlich bei einigen zehn bis einigen
hundert Mikrosekunden je Nachricht, nicht bei den 1-2 µs von MPI; die Bandbreite bei mehreren
GB/s. Beides ist nicht gemessen. Der Berliner Fahrplan (1pct) hat 78.106 Departures auf
19.098 Routen mit 1,68 Mio. Halteereignissen; ein vollständiger Zeitstand umfasst etwa
13 MB. Bei RTR 50.000 und Δ = 60 s hat jeder Snapshot ein Budget von 1,2 ms Wandzeit. Ein
vollständiger Zeitstand wären dann etwa 11 GB/s je Router, und Serialisierung in Rust sowie
Einlesen und Aufbau der Version in Java würden geschätzt einige zehn Millisekunden kosten.
Änderungen umfassen höchstens einige hundert KB je Minute Simulationszeit, meist weniger,
weil eine Beobachtung, die die Prognose bestätigt, nichts ändert. Eine weitere Verkleinerung
(Integer-IDs, Kompression) ist nicht nötig.

Zu messen, da der Snapshot-Thread sonst zum Engpass wird:

- Rechenzeit je Snapshot gegenüber dem Budget Δ / RTR. Braucht der Thread im Mittel länger,
  warten die Anfragen, und die Simulation läuft im Takt des Threads.
- Wartezeit der Anfragen auf ihren Snapshot und Blockieren in `blocking_recv`. Der Puffer
  für den Snapshot ist mindestens (g + h) / RTR, für das Routing selbst h / RTR. Bei
  h = 600 s (`routing-example`) und RTR 50.000 sind das 12 ms ohne g. Der RTR von Läufen mit
  Router ist noch nicht gemessen.

Der Vorschlag setzt einen einzigen Simulationsprozess voraus, wie heute. Bei mehreren
Prozessen müsste ein Prozess den Snapshot-Thread übernehmen.

Vorgeschlagene Tests für diesen Vertrag:

- Dieselbe Simulationszeit führt bei unterschiedlichen Nachrichtenlaufzeiten und
  Bearbeitungsreihenfolgen zur gleichen vorgesehenen Snapshot-ID.
- Noch nicht verfügbare vorgesehene Snapshots werden abgewartet; später
  veröffentlichte Versionen ersetzen die angeforderte Version nicht.
- Ein Produzent ohne fachliche Ereignisse muss trotzdem Vollständigkeit melden;
  ein fehlender Abschluss verhindert die Veröffentlichung.
- Ein ausgebliebenes Abfahrtsereignis erhöht die Zeitgrenze der Prognose erst auf
  einem dafür vollständigen Snapshot. Ältere Snapshots bleiben unverändert.
- Ergänzt am 2026-11-19: Ein Event genau zur Zeit kΔ erscheint erst in Snapshot k + 1.
- Anfragen in [kΔ, kΔ + g) verwenden Snapshot k − 1, ab kΔ + g Snapshot k; Anfragen vor
  Δ + g verwenden Snapshot 0.
- Ein künstlich verzögerter Snapshot verlängert nur die Wartezeit, ändert aber keine Antwort.
- Eine Partition, die auf eine Antwort wartet, verhindert nicht den Abschluss des Snapshots,
  den diese Anfrage braucht; mit Nachbar- und mit globaler Synchronisation.
- Ein Router, der Änderungen für k erhält, bevor eine Anfrage für k − 1 bearbeitet ist,
  beantwortet diese weiterhin auf Version k − 1.

### D04: Router-Datenmodell mit zugesicherter Nichtüberholung

Am 2026-11-13 vom Nutzer festgelegt: Fahrzeuge innerhalb derselben TransitRoute
können einander nicht überholen. Claude implementiert diese Eigenschaft parallel.
Für diesen Entwurf wird sie als zugesicherter Vertrag vorausgesetzt. Sie wird
hier nicht erneut implementiert oder zur offenen Entscheidung gestellt.

Die bisher vorgeschlagene Unterstützung von Überholungen innerhalb einer Route
entfällt damit als Anforderung. Individuelle Verspätungen, Aufenthalte und Aufholen
bleiben relevant, solange die garantierte Reihenfolge erhalten bleibt.
Nichtüberholung bedeutet keine konstanten Abstände und keine parallelen
tatsächlichen Zeitprofile.

Die Prognose muss dieselbe Reihenfolge erhalten. Folgt B auf A und wird A am
nächsten Halt um 10:05 erwartet, darf eine unabhängige Ankunftsprognose für B um
10:04 nicht unverändert in den Snapshot eingehen. Bekannte Einschränkungen durch
das vorausfahrende Fahrzeug sind auch bei einer optimistischen Prognose verbindlich.

Noch zu konkretisieren sind der zwischen Rust und Java vereinbarte
Reihenfolgeschlüssel, die Behandlung gleichzeitiger Fahrten und gegebenenfalls
Mindestabstände. Die genaue Suche und die Zeit- und Kostenberechnung im
Java-Router müssen individuelle Zeitprofile unter dieser Ordnung berücksichtigen.

Der Vertrag wird nicht auf verschiedene Route-IDs mit gleicher Haltefolge
ausgedehnt. Entsprechende Transferoptimierungen bleiben gesondert zu prüfen.

Wir wollen Aktualisierungskosten messen, bevor eine aufwendige Optimierung festgelegt
wird. Eine Testreferenz muss individuelle Zeitprofile unter dem
Nichtüberholungsvertrag und mögliche Transfers zwischen verschiedenen Routen
korrekt abdecken. Ein bloßer Neuaufbau des bisherigen Routers mit weiterhin
gemeinsamen Halte-Offsets reicht dafür nicht automatisch aus.

#### Verifiziert: bisherige Nichtüberholungsannahme im Java-Router

Auf Nachfrage des Nutzers am 2026-11-13 erneut im öffentlichen Upstream-Stand
`main` geprüft. Der konkret eingesetzte Java-Service wurde weiterhin nicht auf
seinen Quellstand abgeglichen.

Alle Departures derselben MATSim-`TransitRoute` verwenden die gemeinsamen
Ankunfts- und Abfahrts-Offsets ihrer Routenhalte. Eine Departure bringt ihre
Startzeit ein. Im Router-Kern wird die Ankunft als Startzeit der gewählten
Departure plus Ankunfts-Offset des jeweiligen Halts berechnet. Deshalb ist
Nichtüberholung innerhalb dieser Route bereits eine Eigenschaft der dargestellten
Zeitprofile: Für jeden Halt gilt `Zeit(B, Halt) - Zeit(A, Halt) = Start(B) - Start(A)`.
Eine Linie kann mehrere unterschiedliche TransitRoutes enthalten; die Aussage
bezieht sich zunächst auf eine einzelne Route mit gemeinsamem Zeitprofil.

Die Suche nutzt dies: `findNextDepartureIndex` sucht im gewöhnlichen Fall ohne
Kapazitätsbeschränkung die nächste erreichbare Departure per binärer Suche in
den nach Startzeiten sortierten Abfahrten. `exploreRoute` verwendet anschließend
die gemeinsame Offset-Folge. Individuelle Zeitprofile je Departure und Halt
werden dabei bisher nicht dargestellt. Dies ist eine Annahme der Datenhaltung
und Suche, keine betriebliche Regel, mit der der Router Fahrzeuge zurückhält.

Eine zusätzliche Transferoptimierung ist weiter gefasst: `isUsefulTransfer`
verwirft mit `cannotReachAdditionalStops` unter anderem Umstiege auf eine andere
Route mit identischer weiterer Haltefolge. Der Kommentar nennt ausdrücklich die
Annahme, dass Fahrzeuge mit gleicher Haltefolge einander nicht überholen.
Diese Optimierung betrifft somit auch verschiedene Route-IDs.

Konsequenz für den Entwurf: Eine je Fahrt über alle Halte konstante Zeitverschiebung
erhält die parallelen Zeitprofile. Bei korrekt aktualisierter Abfahrtsreihenfolge
und zugehörigen Zuordnungen bleibt Nichtüberholung innerhalb eines solchen
Snapshot-Modells erhalten. Haltabhängige Verspätungen oder unterschiedlicher
Verspätungsabbau benötigen allgemein zusätzliche Ordnungsregeln. Die vom Nutzer
zugesicherte Nichtüberholung erhält diese Ordnung auch bei individuellen
Zeitprofilen. Daraus folgt weiterhin keine Garantie zwischen verschiedenen Routen.

Quellstellen des geprüften Stands:

- [Gemeinsame Halte-Offsets](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorData.java#L621-L647)
- [Zeitberechnung im Suchkern](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorCore.java#L716-L759)
- [Auswahl der nächsten Departure](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorCore.java#L883-L904)
- [Transferausschluss und Nichtüberholungsannahme](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorData.java#L434-L437)

Blob-SHAs zur Identifikation des gelesenen Inhalts: `SwissRailRaptorData.java`
`5629aba3c978cb66288e40c35dc78504dc6a4e04`; `SwissRailRaptorCore.java`
`d93795d31252a5b1b6b7434dd7d0f0f4892e7d37`. Dies sind Inhaltskennungen, keine
festgelegten Commit-Referenzen für die spätere Implementierung.

#### Arbeitsvorschlag: gemeinsame Grundstruktur und Zeiten je Fahrt und Halt

Der folgende Entwurf ist noch nicht entschieden:

- Halte, Haltefolgen, Fahrtzuordnung und grundsätzlich mögliche Fußverbindungen
  bilden eine gemeinsam genutzte Grundstruktur.
- Ein Snapshot erlaubt den Zugriff auf prognostizierte Ankunfts- und Abfahrtszeiten
  je konkreter Fahrt und Position in ihrer Haltefolge. Eine einzelne Verschiebung
  je Linie oder Route genügt nicht für unterschiedliche Verspätungsverläufe.
- Neue Snapshots erzeugen neue Zeitstände. Laufende Anfragen bleiben an ihrem
  jeweiligen unveränderlichen Zeitstand gebunden.
- Bereits vorbereitete Transferausschlüsse werden auf ihre Voraussetzungen geprüft.
  Ausschlüsse aufgrund planmäßiger Zeiten oder fehlender Überholungen sind nicht
  automatisch Teil einer dauerhaft gültigen Grundstruktur.
- Die Prognosen sind innerhalb der zugesicherten Fahrtreihenfolge monoton.
  Ankunft und Abfahrt dürfen die jeweilige Zeit des vorausfahrenden Fahrzeugs
  nicht unterschreiten; genaue Mindestabstände ergeben sich aus dem Modellvertrag.
- Die Abfahrtssuche verwendet die effektiven Zeiten am jeweiligen Einstiegshalt.
  Die Ordnung ermöglicht weiterhin eine Suche nach der nächsten erreichbaren
  Fahrt, aber die bisherige Berechnung über Startzeit plus gemeinsamen Halte-Offset
  muss für individuelle Zeitprofile angepasst werden.

Die konkrete Speicherform bleibt offen: vollständige Zeittabellen, gespeicherte
Abweichungen oder gemeinsam genutzte unveränderte Teile werden anhand von
Verständlichkeit, Messungen und den benötigten gleichzeitig verfügbaren Snapshots
bewertet. Es wird noch keine Kopie des gesamten Fahrplans je Snapshot festgelegt.

#### Stand 2026-11-19: Umbau von SwissRailRaptor in einem Branch von matsim-libs

Entschieden am 2026-11-19: Der Umbau entsteht in einem Branch von matsim-libs. Korrektur vom
2026-11-20: Ein PR-Release entsteht erst beim Merge (PR5260 war schon gemergt). Bis dahin wird
der Branch lokal installiert, siehe „Umsetzungsplan Router“. Hängt das Review, kann derselbe Diff als
Kopie der Klassen nach parallel-qsim-berlin wandern. Ein eigener RAPTOR scheidet aus, weil er
das Kostenmodell von MATSim und die Vergleichbarkeit mit DSim und QSim aufgäbe.

Verifiziert am 2026-11-19 in MATSim 2027.0-2026w45, der Version des Routers (identisch mit
matsim-libs dbee7ca8; bis `origin/main` bd2ff64c keine Änderung am Paket):

- Alle Zeiten entstehen als `departures[d]` plus `arrivalOffset` oder `departureOffset` des
  Routenhalts, an etwa 15 Stellen in `SwissRailRaptorCore` (Start der Suche, `exploreRoute`,
  Wechsel auf eine bessere Departure, `findNextDepartureIndex`, `RouteSegmentIterator`) und in
  `hasNoPossibleDeparture` in `SwissRailRaptorData`.
- Der Berliner Router (`integration/berlin/router-config.xml` in parallel-qsim-berlin) nutzt
  `transferCalculation=Initial`, keine Range Query, keine Kapazitäten und kein Intermodal; der
  Fahrplan hat keine verketteten Departures. Nur dieser Standardpfad muss Versionen
  unterstützen; die übrigen Pfade lehnen sie ausdrücklich ab.
- Zwei Transferfilter beruhen auf Zeitannahmen: `cannotReachAdditionalStops` setzt
  Nichtüberholung zwischen Routen mit gleicher weiterer Haltefolge voraus, was D04 ausschließt.
  `hasNoPossibleDeparture` vergleicht Fahrplanzeiten und verwirft Anschlüsse, die erst durch
  Verspätung erreichbar werden. Die übrigen Filter sind topologisch. Entschieden am
  2026-11-19: Für veränderliche Zeiten gilt `cannotReachAdditionalStops` dank des
  Nichtüberholungsvertrags weiter für Umstiege innerhalb derselben Route und entfällt nur
  zwischen verschiedenen Routen. `hasNoPossibleDeparture` entfällt ganz; das betrifft nur
  wenige Umstiege an den Rändern der Betriebszeiten, und mit `--pt-arrival-shift` stimmen
  die Fahrplanzeiten des Routers schon ohne Verspätung nicht.
- `SwissRailRaptorData.create` sortiert die Departures einer Route instabil nach Startzeit.
  Rust ordnet nach Startzeit und dann nach Departure-Index, und dieser folgt innerhalb einer
  Route der Dateireihenfolge (`TransitSchedule::new`; der Kommentar in `schedule.rs`, der Index
  folge den externen IDs, trifft nur auf Linien und Routen zu). In Berlin v7.1 (1pct) haben
  5 Departures in 4 Routen dieselbe Startzeit wie eine andere ihrer Route.
- Weder `RaptorRoute.RoutePart` noch `PtRouteDescription` (matsim-schemas) enthalten die
  Departure.
- Rust kann die Ankünfte verschieben (`--pt-arrival-shift`, in `routing-example` 30 s früher);
  der Router liest den unveränderten Fahrplan. Eigene Offsets des Routers weichen dann schon
  ohne Verspätung von der Ausführung ab.

Arbeitsvorschlag für den Branch, noch nicht entschieden:

1. Eine Schnittstelle für Zeiten je Departure und Routenhalt: Ankunft, Abfahrt und nächste
   Departure ab einer Zeit an einem Routenhalt. Die Standardimplementierung rechnet wie heute;
   alle Zeitzugriffe im Core gehen über sie.
2. Eine versionierte Implementierung: je Route ein Block mit den Zeiten aller Departures an
   jedem Halt, nach Halt geordnet, damit die Suche am Einstiegshalt binär bleibt. Eine Version
   ist ein Array von Verweisen auf diese Blöcke; eine neue Version kopiert nur die geänderten
   Blöcke. Änderungen werden über Departure-ID und Halt-Index angegeben, damit Aufrufer keine
   internen Indizes kennen.
3. Die Version wird je Anfrage gewählt, entschieden am 2026-11-20: über einen per Guice
   injizierten Provider, siehe B4.
4. Eine Option in `RaptorStaticConfig` für veränderliche Zeiten:
   `cannotReachAdditionalStops` nur noch innerhalb derselben Route, `hasNoPossibleDeparture`
   aus (entschieden, siehe oben); Standard wie heute.
5. Die Reihenfolge der Departures einer Route kommt von außen (Snapshot 0 von Rust);
   die versionierte Implementierung übernimmt sie.
6. Gestrichen am 2026-11-20 (siehe A1 im Umsetzungsplan): Die Antwort enthält keine
   Departure, `RoutePart` bleibt unverändert.

Snapshot 0, entschieden am 2026-11-20 (A1): Beim Start schickt Rust den Zeitstand einmal
vollständig, je Route die Departures in Rust-Reihenfolge mit allen Zeiten (etwa 13 MB an Zeiten;
als Nachrichten mit Zeiten in ns 30,2 MB, gemessen in B6). Er ist
in jeder Iteration gleich (Fahrplan, Ankunftsverschiebung und Prognoseregeln ohne
Beobachtungen; die vorab gezogenen Störungen sieht die Prognose nicht). Zu Beginn jeder
Iteration genügt eine kurze Startmeldung, mit der der Router auf diese Grundversion
zurückfällt; danach kommen nur Änderungen. Der Router prüft IDs und Haltefolgen gegen seinen
Fahrplan und bricht bei Abweichungen ab. Die Offsets des Fahrplans verwendet er dann nicht mehr.
Ändert sich der Fahrplan einmal zwischen Iterationen, braucht es einen neuen Snapshot 0.

Vorgeschlagene Abnahme:

- Die bestehenden Tests von SwissRailRaptor laufen unverändert mit der
  Standardimplementierung; ein Benchmark zeigt, dass sie nicht langsamer ist.
- Die versionierte Implementierung ohne Änderungen, aus dem Fahrplan initialisiert, liefert
  dieselben Routen wie die Standardimplementierung, auch auf `pt-tutorial-dummy` und einer
  Stichprobe aus Berlin.
- Die binäre Suche stimmt bei zufälligen, ordnungserhaltenden Verspätungen mit einer linearen
  Suche überein.
- Ein verspäteter letzter Bus ist mit der Option erreichbar, ohne sie nicht.
- Mit der Option bleibt ein Umstieg zwischen verschiedenen Routen mit gleicher weiterer
  Haltefolge erhalten, und ein überholendes Fahrzeug der zweiten Route wird gefunden. Ein
  Umstieg innerhalb derselben Route an demselben Halt wird weiter verworfen.
- `#transfers` aus dem Log von `SwissRailRaptorData` und die Routing-Zeit werden mit und ohne
  Option verglichen.
- Eine Anfrage auf einer alten Version behält ihr Ergebnis, nachdem eine neue entstanden ist.

#### Umsetzungsplan Router (Vorschlag vom 2026-11-20, noch nicht bestätigt)

Bauen vor dem Merge, verifiziert am 2026-11-20 in `.github/workflows` von matsim-libs:

- `verify-push.yaml` baut und testet jeden Push auf einen Branch außer `main`, mit allen
  Modulen. Bei PRs aus einem Fork läuft er auf dem `pull_request`. Ein Jar wird dabei nicht
  veröffentlicht.
- `deploy-on-pr-merge.yaml` veröffentlicht `2027.0-PR<nr>` auf repo.matsim.org, aber nur,
  wenn der PR gemergt wird. Vor dem Merge gibt es kein PR-Release.
- Vorschlag bis zum Merge: Den Branch lokal installieren, nur mit den Modulen, die der Router
  braucht (`mvn install -DskipTests --also-make --projects
  contribs/application,contribs/dvrp,contribs/vsp,contribs/locationchoice,contribs/accidents`).
  parallel-qsim-berlin baut in einem Maven-Profil dagegen, `main` bleibt auf dem Weekly
  Release. Das Router-Jar ist geshadet und enthält MATSim. Es wird für Lise lokal gebaut und
  auf den Cluster kopiert; das Kopieren braucht jedes Mal die Zustimmung des Nutzers.
  Nach dem Merge wechselt der Parent auf `2027.0-PR<nr>`.
- matsim-schemas, entschieden am 2026-11-20 (A2): Der Nutzer fragte, ob das Protokoll zum
  Entwickeln besser erst lokal in parallel-qsim-berlin liegt. Das geht nicht allein, weil
  matsim-rust die Anfrage und den Snapshot-Sender braucht und nicht von parallel-qsim-berlin
  abhängen kann; eine Kopie in beiden Repos liefe auseinander. Daher bleibt der lokale Checkout
  `~/git/matsim-schemas` die einzige Quelle, während der Entwicklung per Pfad eingebunden:
  Rust über `[patch."https://github.com/matsim-org/matsim-schemas"]` mit `path` (das `build.rs`
  von matsim-schemas merkt geänderte Protos), Java über
  `mvn -q -f ~/git/matsim-schemas/java install` als SNAPSHOT im Entwicklungsprofil. Commits nur
  auf einem Branch. Korrektur vom 2026-11-26: Ein Vorab-Tag wie `v0.4.0-alpha.1` geht nicht,
  weil `release.yml` zwar bei jedem Tag `v*` startet, aber nur `vX.Y.Z` veröffentlicht.
  Entschieden am 2026-11-26: matsim-schemas#5 bleibt WIP bis nach M2, danach Release `v0.4.0`.

Schritte. Jeder Schritt ist ein Commit mit grünen Tests. A und B sind unabhängig, weil B keine
Protobuf-Typen verwendet.

| Schritt | Inhalt | Abnahme |
| --- | --- | --- |
| A1: offene Punkte für den Router | E, entschieden am 2026-11-20: Die Antwort enthält keine Departure. Rust braucht sie für die Ausführung nicht, denn Passagiere steigen in jedes Fahrzeug der geplanten Linie, das ihren Ausstiegshalt noch anfährt (`agent_logic.rs:385`). Für Prüfungen bestimmen Linie, Route, Ein- und Ausstiegshalt, `boarding_time_ns` und die Snapshot-ID die geplante Fahrt; mehrdeutig sind nur Fahrten derselben Route mit gleichen Zeiten an diesem Halt. Bindet D05 Passagiere später an eine Fahrt, kommt ein optionales Feld dazu. Die `Response` erhält `snapshot_id` als Kontrolle, dass auf der angefragten Version geroutet wurde. F, entschieden am 2026-11-20, soweit sie den Router betrifft: (a) Snapshot 0 nur einmal beim Start, je Iteration eine Startmeldung (siehe „Snapshot 0“ oben). (b) Freigabe durch Rust statt eines festen Fensters: Anfragen verzögern sich in Wandzeit, die Versionen wechseln in Simulationszeit (bei RTR 50k und Δ = 60 s sind 10 ms Warteschlange etwa 8 Intervalle). Jedes Delta nennt die älteste noch benötigte Version, das Minimum aus der Version der ältesten offenen Anfrage (Zähler im Adapter-Thread) und k − ⌈g/Δ⌉ für den neuesten geschlossenen Snapshot k; jede neue Anfrage hat mindestens diese ID, weil k erst schließt, wenn alle Partitionen kΔ passiert haben. Ältere Versionen verwirft der Router; eine Anfrage auf eine verworfene Version ist ein Fehler. (c) Warten asynchron, ohne blockierten Thread. Kein stiller Rückfall auf eine ältere Version; ein Fehlerstatus, den Rust als fatal behandelt. Geändert am 2026-11-20 (C2): keine Frist im Router. Endet oder bricht der Strom, schlagen wartende Anfragen sofort fehl (C1); gegen einen offenen Strom ohne weitere Deltas setzt Rust je Anfrage eine gRPC-Deadline (M2). (d) Vertragsverletzungen (Lücke in k, falsche Iteration, unbekannter Departure-Index, Zeiten gegen die Fahrtreihenfolge, abweichende IDs oder Haltefolgen in Snapshot 0): Der Router schließt den Strom mit Fehler und loggt; der Snapshot-Thread in Rust gerät in Panic, der Lauf endet. (e) Rust schickt für jedes k ein Delta, auch ein leeres, sonst warten Anfragen auf k ewig. Der Router kennt Δ und g nicht, die ID k genügt. C betrifft nur Rust und kann warten. | Entscheidungen des Nutzers im Protokoll. |
| A2: Protokoll in matsim-schemas | Umgesetzt am 2026-11-20 im Branch `ph/timetable-updates` von `~/git/matsim-schemas` (von `origin/main` 9fe316d, Version 0.4.0 bzw. `0.4.0-SNAPSHOT`; Commit 11919e2, gepusht, seit 2026-11-23 PR matsim-org/matsim-schemas#5 (WIP), CI grün). Alles steht in `routing.proto` im Paket `matsim.services.routing.v1` und sind nur Ergänzungen; `population.proto` bleibt unverändert. `Request` und `Response` erhalten `TimetableVersion timetable_version` (`iteration`, `snapshot_id`); ohne sie routet der Router auf dem Fahrplan. Neuer Dienst `TimetableService` mit `rpc UpdateTimetable(stream TimetableUpdate) returns (google.protobuf.Empty)`, ein geordneter Strom je Router für den ganzen Lauf. `TimetableUpdate` ist eines von: `BaseRoute` (Snapshot 0, eine Nachricht je Route, damit jede weit unter der gRPC-Grenze von 4 MB bleibt; Linie, Route, Haltefolge als Facility-IDs, Departures in Rust-Reihenfolge mit ID und Zeiten je Halt), `IterationStart` (die erste beendet Snapshot 0) und `TimetableDelta` (`iteration`, `snapshot_id`, `oldest_needed_snapshot_id`, je geänderter Fahrt ein `TripUpdate` mit der Nummer der Departure in Snapshot 0, `from_stop` und den Zeiten ab dort). Zeiten als `uint64` in ns wie im übrigen Schema, vom Nutzer am 2026-11-20 gewählt; der Java-Router verlangt ganze Sekunden. Vertragsverletzungen beendet der Router mit einem Fehlerstatus. Wechselt matsim-rust auf das neue Schema, braucht das Struct-Literal `Request { .. }` in `external_services/routing/mod.rs` `timetable_version: None`. | `buf lint` und `buf breaking` gegen `origin/main` grün (die lokale `main` ist veraltet); Rust mit `--features routing` und Java gebaut, `0.4.0-SNAPSHOT` lokal installiert. Review durch den Nutzer steht aus. Entschieden am 2026-11-26: Der PR bleibt WIP bis nach M2, weil der Client in matsim-rust den Vertrag noch ändern kann; danach Release `v0.4.0`. |
| B1: Zeit-Schnittstelle | Eine Schnittstelle (Name offen) mit Ankunft und Abfahrt je globalem Departure- und Routenhalt-Index. Die Standardimplementierung rechnet `departures[d]` plus Offset wie heute. Die 20 Zeilen mit Zeitzugriffen in `SwissRailRaptorCore` gehen über sie, also Start der Suche, `exploreRoute`, `findNextDepartureIndex` und `RouteSegmentIterator`. Zwei Stellen bleiben beim Fahrplan: `calcTreesObservable` in `SwissRailRaptor` (Baumsuche, mit der Option abgelehnt) und `hasNoPossibleDeparture` in Data (mit der Option aus). Core hält die Tabelle als Feld, das je Anfrage gesetzt wird. Umgesetzt am 2026-11-20 im Branch `ph/raptor-timetable` von matsim-libs (von `origin/main` bd2ff64c, Commit b2c64193ec6, nicht gepusht). Die package-private Schnittstelle `RaptorTimetable` (seit B4 öffentlich und `sealed`) bietet `getArrivalTime`, `getDepartureTime` und `findNextDepartureIndex`. `RaptorScheduleTimetable` ist die Standardimplementierung mit dem unveränderten Code der binären Suche; sie liegt als `scheduleTimetable` in `SwissRailRaptorData`. Die öffentliche API ändert sich nicht. Die verketteten Departures nehmen die Startzeit der Route weiter aus `data.departures`. Neu ist `RaptorScheduleTimetableTest`: die Zeiten gleich Start plus Offset, die Suche gegen eine lineare Suche, auch bei gleichen Startzeiten. | Alle Tests in `ch.sbb.matsim.routing.pt.raptor` unverändert grün (2026-11-20: 105 Tests, davon 3 neue; das ganze Modul `matsim` mit `verify` ebenfalls grün, 2479 + 77 Tests, 6 übersprungen; Contribs erst in der CI nach einem Push); B6 zeigt keine Verlangsamung: auf Lise 4036 statt 4028 µs je Anfrage, Faktor 1,002 (95-%-Intervall 0,982–1,026), siehe B6. |
| B2: Option für veränderliche Zeiten | Umgesetzt am 2026-11-20 (Commit e8795ed0681): `useTimetableUpdates` in `SwissRailRaptorConfigGroup`, übertragen nach `RaptorStaticConfig`, Standard aus. Mit der Option entfällt `hasNoPossibleDeparture`, und `cannotReachAdditionalStops` gilt nur innerhalb derselben Route, bei `Initial` und `Adaptive`. Die Option sortiert nichts: Java ordnet die Departures einer Route nach ihrer ID (`TreeMap` in `TransitRouteImpl`, `Id.compareTo` vergleicht Strings), die Dateireihenfolge ist also verloren; die Reihenfolge kommt deshalb aus Snapshot 0 (B3). Abgelehnt werden Kapazitäten und verkettete Departures (in `SwissRailRaptorData.create`) und die Range Query (`checkConsistency` und `calcRoute`; seit B4 auch `calcRoutes` und `calcTreesObservable`). | `SwissRailRaptorTimetableUpdatesTest` mit den Filtertests aus „Vorgeschlagene Abnahme“ (7 Tests). `#transfers` und Berlin mit und ohne Option hat der Nutzer zurückgestellt; gemessen in B6: mit Option 25,3 Mio. statt 16,3 Mio. Transfers (+56 %) und 26 % mehr Routing-Zeit bei gleichen Routen. Von den 9,05 Mio. zusätzlichen Transfers würde `hasNoPossibleDeparture` 6,17 Mio. entfernen, `cannotReachAdditionalStops` zwischen verschiedenen Routen 4,01 Mio. (davon 2,61 Mio. innerhalb einer Linie), beide 1,13 Mio. Mit einem Sicherheitsabstand von 1 h bzw. 2 h entfernte `hasNoPossibleDeparture` noch 5,11 bzw. 4,36 Mio.; das setzte eine zugesicherte Höchstverspätung voraus und ist nicht geplant. |
| B3: versionierte Zeiten | Umgesetzt am 2026-11-20 (Commit fbfcdaeb0dc): `VersionedRaptorTimetable`, unveränderliche Versionen mit einer Zeile je Fahrt (Ankunft und Abfahrt je Halt). Entschieden nach der Messung am Berliner Fahrplan 1pct: Departures je Route im Median 1, p90 10, Max 332; eine geänderte Fahrt kopiert im Median 160 Byte statt 1,7 KB für einen Block je Route, und `exploreRoute` liest entlang einer Fahrt. `fromSchedule` übernimmt den Fahrplan; `builder` baut Snapshot 0 aus Routen und Departures in Rust-Reihenfolge und prüft IDs, Halte und Anzahl gegen die Daten; `apply(Collection<TripUpdate>)` kopiert nur das äußere Array und die geänderten Zeilen. Der externe Departure-Index ist die Position in Snapshot 0, und die Suche nach der nächsten Departure folgt dieser Reihenfolge. Jede Version prüft Ankunft ≤ Abfahrt, Ankunft am nächsten Halt ≥ Abfahrt und keine Überholung innerhalb der Route. Versionen lassen sich nur mit der Option erzeugen. Die Schnittstelle besteht nur aus Arrays und Zahlen, sodass matsim-libs nicht von matsim-schemas abhängt. | `VersionedRaptorTimetableTest` (7 Tests): gleiche Zeiten wie der Fahrplan, Reihenfolge aus Snapshot 0, binäre gegen lineare Suche bei zufälligen ordnungserhaltenden Verspätungen, die alte Version bleibt nach `apply` unverändert, Verletzungen werden abgelehnt. Dieselben Routen wie der Standard: `RaptorVariantsTest` in parallel-qsim-berlin (Anfragen zwischen allen Haltepaaren auf pt-tutorial-dummy und pt-delays, alle Varianten gleich) und in B6 alle 2000 Anfragen der Berliner Stichprobe in allen Varianten identisch. |
| B4: Auswahl je Anfrage | Umgesetzt am 2026-11-20 (Commit ee6bd3c66a0). Entschieden am 2026-11-20, auf die Frage des Nutzers nach Guice: ein injizierter Provider, nicht die Tabelle selbst: `RaptorTimetableProvider.getTimetable(SwissRailRaptorData data, double departureTime, Person person, Attributes routingAttributes)`, Standard `DefaultRaptorTimetableProvider`. Die Tabelle wird aus drei Gründen nicht selbst injiziert. Erstens wechselt sie je Anfrage, eine Bindung ist aber je Injector fest. Zweitens hängt sie an `SwissRailRaptorData`, das die Factory erst bei Bedarf erzeugt und bei `TransitScheduleChangedEvent` verwirft. Drittens lässt sie sich außerhalb des Pakets nicht sinnvoll implementieren (`RRoute` und die Felder von `RRouteStop` sind package-private). Vorbild ist `RaptorStopFinder`: Er bekommt dieselben Eingaben je Anfrage, ist in `SwissRailRaptorModule` gebunden und wird in die Factory injiziert. Der Standard gibt `data.scheduleTimetable` zurück. Die Factory reicht den Provider an `SwissRailRaptor` weiter; der `Builder` bekommt `with(...)` mit dem Standard als Vorgabe, daher bleiben seine 76 Verwendungen unverändert. `SwissRailRaptor` fragt den Provider je Anfrage und reicht die Tabelle an den Core weiter. `RaptorTimetable` wird öffentlich als `sealed interface`, mit `permits` für die Fahrplan- und die versionierte Implementierung: Andere Projekte können sie halten und weiterreichen, aber nicht implementieren. Jede Tabelle kennt ihre Daten (`belongsTo`), und der Core lehnt eine Tabelle zu anderen Daten ab. Der alte Konstruktor von `SwissRailRaptor` bleibt und nimmt den Standard. `calcRoute` und `calcTree` für einen Zeitpunkt fragen den Provider; mit der Option werden `calcTreesObservable` und die Range Query, auch über `calcRoutes`, abgelehnt. | Neue Tests in `SwissRailRaptorTimetableUpdatesTest`: Ein verspäteter letzter Bus ist nur auf der Version erreichbar, auch per `calcTree`; vier Threads routen abwechselnd auf zwei Versionen; eine Tabelle zu anderen Daten wird abgelehnt; Range Query und `calcTreesObservable` werden abgelehnt. 123 Raptor-Tests grün. Den Test der Guice-Bindung (Standard ohne Bindung, Override) hat der Nutzer entfernt; er folgt in C3. |
| B5: gestrichen | Am 2026-11-20 gestrichen, weil die Antwort keine Departure enthält (A1). | – |
| B6: Benchmark | In parallel-qsim-berlin (dort liegen die Berliner Eingaben): eine feste Stichprobe von pt-Anfragen aus den it0-Plänen, 1pct, gemessen vor B1, nach B1, mit Option und mit versionierten Zeiten. Dazu die Zeit von `apply` mit synthetischen Verspätungen aller laufenden Fahrten zur Spitzenstunde, gegen das Budget Δ/RTR (etwa 1,2 ms bei RTR 50k und Δ = 60 s). Umgesetzt am 2026-11-24 im Branch `ph/timetable-updates` von parallel-qsim-berlin (Commit 738fe6f, nicht gepusht). `RaptorBenchmark` routet 2000 pt-Wege (Seed 1) aus `output_trips` des kalibrierten 1pct-Laufs wie `RoutingService` (Facility aus Link und Koordinate, ohne Person), in einem Thread und je Variante in einer eigenen JVM: `base/schedule` (matsim bd2ff64ce56; das Modul ist gleich dem Release 2027.0-2026w45), `branch/schedule` (ee6bd3c66a0, Option aus), `branch/option` (Option an, Zeiten des Fahrplans) und `branch/versioned` (Snapshot 0 als `VersionedRaptorTimetable` über `TimetableVersions`). Fünf Forks in wechselnder Reihenfolge mit je 3 + 10 Runden. Die 8 Busrouten, die einen Halt vor der Abfahrt am vorigen erreichen (31 Fahrten, Datenfehler des Fahrplans), entfernt der Benchmark in allen Varianten. `TimetableUpdateBenchmark` misst Snapshot 0 und 60 Deltas um die Spitze (07:10, 3104 laufende Fahrten), in denen jede laufende Fahrt eine neue Verspätung von 0–180 s ab ihrem nächsten Halt bekommt, also den ungünstigsten Fall; dazu dieselben Deltas mit kürzeren Zahlen in den Zeitfeldern, nur geparst. Skripte in `scripts/raptor-benchmark/`, Zusammenfassung mit `src/main/python/scripts/raptor_benchmark.py`. Läufe auf je einem exklusiven Genoa-Knoten von Lise am 2026-11-24: b6-lise-1 (alle Varianten), b6-lise-2 (JFR-Profile, Kodierungen, Zählung der Transferfilter) und b6-lise-3 (Wiederholung mit einer Suche ab der Departure des Fahrplans, matsim-libs d10a5bfbec5). | Standard ohne messbare Verlangsamung; Kosten der versionierten Zeiten und von `apply` dokumentiert. Ergebnisse (µs je Anfrage, Median über die Forks; lokal in `output/benchmark/raptor/b6-lise-{1,2,3}/summary.md`, nicht versioniert): Standard 4028 (base) und 4036 (branch, Faktor 1,002, 95-%-Intervall 0,982–1,026); Option 5092 (1,264); versioniert 6387 (1,586, gegenüber der Option 1,25). b6-lise-3 auf einem anderen Knoten wiederholt diese Werte auf 1 % genau. Alle 2000 Routen in allen Varianten identisch. Im Profil liegt der Mehraufwand der Option in `handleTransfers` und `exploreRoutes` (mehr Transfers, siehe B2), der der versionierten Zeiten fast ganz in `findNextDepartureIndex`: teuer ist der erste Cache-Miss auf die Zeile einer Departure (die Zeilen aller Fahrten belegen etwa 14 MB, `data.departures` des Fahrplans 0,3 MB), nicht die Zahl der Suchschritte; die Suche ab der Departure des Fahrplans änderte nichts (6364 µs) und wurde am 2026-11-26 wieder entfernt. Helfen würde nur eine kleinere Arbeitsmenge, etwa Zeilen nur für Fahrten, die vom Fahrplan abweichen; wegen der Ankunftsverschiebung in Snapshot 0 eine Frage für M2. Snapshot 0: 19.090 Routen mit 78.075 Fahrten, 30,2 MB Nachrichten (größte 110 kB), aufgebaut in 0,12 s. Deltas an der Spitze: im Median 3073 Fahrten (47.780 Halte), 708 kB je Nachricht, 1,03 MB je Version. Router-Pfad (Parsen und `applyDelta`) im Median 1,8–1,9 ms (p95 2,0 ms) gegen das Budget von 1,2 ms, davon Parsen 0,76 ms und `apply` allein 0,47 ms. Mit einem Thread hält der Router im ungünstigsten Fall bis etwa RTR 33k mit. Zeiten in Sekunden oder als Verspätung kürzten die Nachricht auf 324 bzw. 161 kB, das Parsen aber nur um 9–15 %; die ns bleiben. Spielraum: Parsen und Anwenden überlappen (etwa 1,16 ms), Rust schickt nur geänderte Fahrten (M2), größeres Δ. Der Nutzer bewertet das Ergebnis am 2026-11-24 als halbwegs vertretbar. |
| B7: Draft-PR | Früh öffnen, damit `verify-push` mitläuft; zum Review nach B4. Seit 2026-11-23 offen als Draft matsim-org/matsim-libs#5306 (Branch `ph/raptor-timetable` gepusht, ee6bd3c66a0). | CI grün (2026-11-24: 52 Checks erfolgreich, 2 übersprungen). Seit 2026-11-26 „ready for review“ (B6 steht im PR-Text, der Hinweis auf WIP ist entfernt); die Reviewer fragt der Nutzer selbst an. |
| C1: Versionsspeicher | Der neue Dienst aus A2 baut je Strom nacheinander die Versionen und legt sie unter (Iteration, k) ab. Er verwirft Versionen, die älter sind als die im Delta genannte älteste benötigte, und beim Iterationswechsel alle bis auf die Grundversion. Verletzungen des Vertrags beenden den Strom mit Fehler. Umgesetzt am 2026-11-20 im Branch `ph/timetable-updates` von parallel-qsim-berlin (von `origin/main` 4b709bb, Commit df1e158, gepusht): `TimetableVersions` (Speicher, `get(iteration, snapshotId)` liefert je Aufruf ein eigenes `CompletableFuture`, sofort erfüllt, wartend oder sofort fehlgeschlagen) und `TimetableUpdateService` (ein Strom je Router, Verletzungen als `INVALID_ARGUMENT`). Statt eines Maven-Profils baut der Branch gegen die lokal installierten Snapshots (Parent `2027.0-SNAPSHOT` aus `ph/raptor-timetable`, matsim-schemas `0.4.0-SNAPSHOT`), weil der neue Code deren API braucht; zurück auf Releases nach PR-Release und Tag. | Komponententests ohne Netz, auch für jede Verletzung aus A1 (d): `TimetableUpdateServiceTest`, 21 Tests (davon 14 Verletzungen) grün; alle Tests von parallel-qsim-berlin grün. |
| C2: RoutingService | Umgesetzt am 2026-11-20 im Branch `ph/timetable-updates` von parallel-qsim-berlin (Commit 44713a7, nicht gepusht). Mit `swissRailRaptor.useTimetableUpdates` in der Router-Config erzeugt `RoutingServer.createServices` den Speicher aus C1 (Daten über `getUnderlyingData()` eines `SwissRailRaptor` aus demselben Injector; die Factory cacht sie, daher teilen sich alle Router dieselbe Instanz) und daneben `RoutingService` und `TimetableUpdateService`, die nur den Speicher teilen und einander nicht kennen (auf Wunsch des Nutzers am 2026-11-23; vorher erzeugte `RoutingService` den Strom-Service selbst). Der Server registriert beide. Der Injector entspricht `ControllerUtils.createAdhocInjector`, mit einem Override, das `RaptorTimetableProvider` an `RequestTimetableProvider` bindet. Eine Anfrage mit `timetable_version` holt das Future aus dem Speicher: Ist die Version da, routet sie sofort im gRPC-Thread, sonst nach dem Eintreffen im Pool der Router-Threads (`whenCompleteAsync`), ohne blockierten Thread und ohne Frist (A1 c). Abweichend vom ersten Entwurf legt der Service nicht die Snapshot-ID, sondern die abgewartete Version selbst in die Routing-Attribute; der Provider gibt sie nur zurück und kennt den Speicher nicht. Bricht der Client den Aufruf ab (etwa über seine Deadline), wird das Warten abgebrochen. Fehler: freigegebene Version, beendete Iteration, beendeter Strom oder Router ohne die Option als `FAILED_PRECONDITION`, ein Fehler beim Routen als `INTERNAL`. Die Antwort enthält `timetable_version`. | `TimetableRoutingTest` (6 Tests, pt-tutorial, ohne Netz): Injector routet auf der Version in den Attributen; Snapshot 0 ergibt dieselben Legs wie der Fahrplan; eine Anfrage wartet auf ihren Snapshot und steigt nach dem Delta 60 s später ein; Ende des Stroms, freigegebene Version und Router ohne Option ergeben `FAILED_PRECONDITION`. Die Szenarien folgen in C3. |
| C3: Dienst-Tests | Umgesetzt am 2026-11-23 im Branch `ph/timetable-updates` von parallel-qsim-berlin (Commit a99ae42 am 2026-11-24, nicht gepusht). Statt pt-tutorial-dummy (nur eine Linie, kein Umstieg) das Szenario `pt_delays` des Nutzers aus dem matsim-rust-Branch `ph/pt-delays-scenario`, nach Wunsch des Nutzers kopiert nach `integration/pt-delays/` (Eingaben unverändert, README angepasst, neue `router-config.xml` für SwissRailRaptor: keine zusätzliche Umsteigezeit, Warten und Fahren gleich teuer, Umstieg ohne Zusatzkosten); der Rust-Test und seine Dateien bleiben vorerst in matsim-rust. `PtDelaysServerTest` startet den Router mit `RoutingServer.start` und spricht über gRPC auf localhost (nicht in-process, das bräuchte einen zweiten Startweg). Die Anfragen sind die Wege der Personen. Abweichend vom ersten Entwurf: eine unbekannte Version endet mit der Deadline des Clients (`DEADLINE_EXCEEDED`), nicht mit einer Frist im Router (A1 c). | `PtDelaysServerTest` (13 Tests, fünfmal hintereinander grün): Basisfall gleich den handgeschriebenen Plänen; Varianten des README als Delta 1 (express +10 → local_0800; feeder_0800 +3 → local_0800 ab hub 08:10, eine Minute vor trunk_0815, entgegen der ersten Erwartung trunk_0815; trunk_0815 +2 neu erreichbar; trunk_0815 +5 noch da), dabei behält Snapshot 0 sein Ergebnis; local_0800 +5 allein bricht den Vertrag, mit local_0802 dahinter nicht; wartende Anfragen belegen keine Router-Threads; Client-Deadline; freigegebene Version; Iterationswechsel; Vertragsbruch beendet den Strom, Anfragen ohne Version routen weiter; Health. Noch nicht in der CI (nur lokal): Der Branch ist seit 2026-11-26 gepusht, aber ohne PR, weil die CI `2027.0-SNAPSHOT` und `matsim-schemas-java 0.4.0-SNAPSHOT` nicht auflösen kann. Den PR nach `main` gibt es erst nach dem PR-Release von #5306 und dem Release von matsim-schemas (vom Nutzer am 2026-11-26 so entschieden, statt die Snapshots in der CI zu bauen). |

Danach folgt M2 in Rust, mit dem Vertragstest Rust-Java aus M3 als Abschluss. B1 kann sofort
beginnen, weil er nichts Offenes berührt. A1 sollte vor A2 und C2 entschieden sein.

#### Abgrenzung: Alternativen zwischen verschiedenen Routen

Die zuvor vorgeschlagene Entscheidung über Überholungen innerhalb einer Route
ist durch den zugesicherten Nichtüberholungsvertrag ersetzt.

Zwischen verschiedenen Routen bleibt eine später abfahrende, früher ankommende
Alternative möglich. Beispiel: Fahrt A einer Route fährt um 08:00 ab und erreicht
einen gemeinsamen Zielhalt um 08:25; Fahrt B einer anderen Route fährt um 08:05
ab und erreicht ihn um 08:15. Für Routing nach frühester Ankunft muss B
berücksichtigt werden. Ein sinnvoller Umstieg zwischen verschiedenen Routen
mit gleicher weiterer Haltefolge wird durch den zugesicherten Vertrag allein
nicht ausgeschlossen.

Vorgeschlagene Tests:

- Unterschiedliche Verspätungen und Aufenthalte verändern die Abstände zwischen
  Fahrten, während die zugesicherte Reihenfolge innerhalb einer Route erhalten bleibt.
- Eine bekannte Verzögerung des vorausfahrenden Fahrzeugs begrenzt auch die
  Prognose des folgenden Fahrzeugs; es entsteht keine fiktive Überholung.
- Die Abfahrtssuche verwendet effektive Zeiten am Einstiegshalt und wird mit
  einer einfachen vollständigen Prüfung erreichbarer Fahrten verglichen.
- Zwischen verschiedenen Routen ermöglicht eine später abfahrende Fahrt die
  frühere Ankunft; der Routenvergleich berücksichtigt diese Alternative.
- Ein sinnvoller Umstieg zwischen verschiedenen Routen mit gleicher weiterer
  Haltefolge wird nicht allein durch eine unzulässig ausgeweitete
  Nichtüberholungsannahme ausgeschlossen.
- Auf einem kleinen Testnetz werden Ergebnisse mit explizit erwarteten Wegen
  beziehungsweise einer unabhängigen vollständigen Suche verglichen. Der bestehende
  Java-Router ist für neue, bisher nicht korrekt dargestellte Fälle keine automatisch
  gültige Referenz.
- Eine Anfrage auf einem alten Snapshot behält ihre Zeiten und ihr Ergebnis,
  während neuere Beobachtungen die Zeitabstände auf einem neuen Snapshot verändern.

### D05: Entscheidung und Ausführung beim Passagier

Auf ausdrücklichen Nutzerwunsch am 2026-11-13 vertagt. Die folgenden Fragen und
Empfehlungen bleiben als unbestätigte Gesprächsnotizen erhalten.

- Auslöser: vor Reisebeginn, nach dem Aussteigen beim Umstieg, während des Wartens
  und gegebenenfalls aus dem Fahrzeug heraus. Empfehlung für den Einstieg: die
  ersten beiden Punkte abdecken und weitere Auslöser später ergänzen.
- Fahrtbindung: eine konkrete Departure oder die nächste passende Fahrt derselben
  Route? Die zugesicherte Nichtüberholung erleichtert die Wahl innerhalb einer
  Route, legt diese Verhaltensregel aber noch nicht fest. Die Auswahl muss das
  Routerergebnis einschließlich Route und Haltefolge korrekt ausführen.
- Umfang eines Routenwechsels: Ersatz des verbleibenden Wegs zum bisherigen
  Reiseziel, gegebenenfalls mit geänderter Umstiegshaltestelle. Fußwege zu anderen
  Haltestellen und Aussteigen aus einem Fahrzeug müssen tatsächlich ausgeführt werden.
- Fehlende Verbindung: Ist Warten mit späterer neuer Anfrage vorgesehen oder endet
  der Versuch? Eine solche fachliche Antwort wird von technischen Fehlern getrennt.

Die deterministische Übernahme einer Antwort und der Umgang mit inzwischen
verändertem Agentenzustand werden in D06 festgelegt. Danach können Tests zu einem
konkreten Entscheidungspunkt und ausgeführten Reiseverlauf präzisiert werden.

### D06: Deterministische Antwortübernahme und Fehlerverhalten

Auf ausdrücklichen Nutzerwunsch am 2026-11-13 vertagt. Die folgenden Vorschläge
sind nicht beschlossen. Ein fester Snapshot allein bestimmt nicht, wann die
Antwort das Verhalten eines Passagiers ändert.

Arbeitsvorschlag: Eine Antwort wird an einem festgelegten Entscheidungspunkt
wirksam. Falls das erforderliche Ergebnis noch nicht berechnet oder übertragen
ist, wird rechnerisch darauf gewartet. Die technische Antwortlaufzeit erzeugt
keine zusätzliche simulierte Wartezeit. Das von dieser Entscheidung abhängige
Simulationsgeschehen darf nicht vor dem erforderlichen Ergebnis über den
Entscheidungspunkt hinaus fortgeschrieben werden. Frühe asynchrone Anfragen
können das tatsächliche Warten des Rechners reduzieren.

Antworten werden außerdem der Anfrage, dem Snapshot und dem zugehörigen
Entscheidungszustand des Passagiers zugeordnet. Eine überholte Antwort wird nicht
auf einen inzwischen unpassenden Zustand angewendet; die genaue Behandlung
solcher Fälle wird mit D05 vereinbart.

Technische Fehler wie ein unerreichbarer Service und eine gültige Antwort
„keine Verbindung“ sind unterschiedliche Fälle. Empfehlung für den ersten Stand:
technische Fehler explizit melden und den Lauf beenden; ein fachlicher Rückfall
auf alte Routen müsste als eigene Verhaltensregel entschieden werden. Das
Verhalten bei einer gültigen Antwort ohne Verbindung bleibt Teil von D05.

Vorgeschlagene Tests: Bei gleicher Anfrage und gleichem Snapshot ergeben sich
trotz künstlich verschiedener Antwortlaufzeiten derselbe Übernahmezeitpunkt und
Reiseverlauf. Unpassende oder doppelte Antworten werden erkannt. Technische
Fehler und gültige Antworten ohne Verbindung werden getrennt geprüft.

## Inkrementelle Umsetzung: vorläufiger Vorschlag

Die Reihenfolge und der Umfang werden mit dem Gespräch angepasst.
Insbesondere ist M0 ein früher Test der vorhandenen Kopplung, keine Voraussetzung
für die unabhängige Arbeit am Driver in M1.
Die Stufen bleiben Vorschläge; die vertagten fachlichen Regeln werden dabei
nicht als festgelegt behandelt.

| Schritt | Konkretes Ergebnis | Abnahme durch Tests |
| --- | --- | --- |
| M0: Rust-Java-Kopplung automatisieren | Bisherigen Java-Service und seine Version identifizieren; kleiner Test startet/beendet ihn selbst und fragt eine bekannte Route ab. | Echter Java-Prozess in einem eigenen CI-Job; bekannte Haltefolge/Ankunft; Bereitschaft, Fehler und Beendigung geprüft. |
| M1: Fahrzeugverspätung isoliert | Driver gemäß D01: vorbereitete Störungswerte und laufende Zeitfortschreibung auf Grundlage der separat von Claude umgesetzten Nichtüberholung; zunächst feste Testwerte, tatsächliche Zeiten und korrekte Delay-Events. Umgesetzt am 2026-11-26, siehe D01, „Umsetzung in M1“. | Kleines Netz ohne externen Router; keine Ziehungen während der Fahrt, verspätete Ankunft, Weitergabe, Aufholen gemäß noch festzulegender Regel, erhaltene Fahrtreihenfolge, Nullstörung und Zustandserhalt beim Partitionswechsel. |
| M2: Beobachtungen, Snapshots und Prognose in Rust | Seit 2026-11-19 umfasst M2 auch die Prognose. Partitionen senden ihre Events je Intervall mit Vollständigkeitsmeldung an den Snapshot-Thread. Er schließt Snapshots, schreibt die Prognose mit den Zeitregeln der Ausführung fort und erzeugt Änderungen je Fahrt. Die Anfrage trägt die Snapshot-ID. | Rust-Tests mit kontrolliertem Testdienst: feste Zuordnung trotz vertauschter Nachrichten und Laufzeiten, Grenzkonvention, fehlende Produzenten, alte/neue Versionen und Iterationswechsel. Prognose exakt ohne Störung, nicht später als die Ausführung mit Störung, unabhängig von der Event-Reihenfolge. Zeitbedarf je Snapshot gemessen. |
| M3: Dynamischer Java-Router | SwissRailRaptor mit versionierten Zeiten in einem Branch von matsim-libs (D04), bis zum Merge lokal installiert, danach über das PR-Release (Plan in D04, „Umsetzungsplan Router“). Java übernimmt die Änderungen als neue Version (copy-on-write je Route), lässt Anfragen auf die genannte Version warten und routet mit Zeiten je Fahrt und Halt unter der Fahrtreihenfolge aus D04. | Java-Tests plus echter Rust-Java-Vertragstest: ohne Änderungen dieselben Routen wie der heutige Router, individuelle Zeitprofile ohne Überholung innerhalb einer Route, Alternativen zwischen verschiedenen Routen, verpasster und neu erreichbarer Anschluss, unveränderter alter Snapshot. |
| M4: Passagier reagiert | Ein zunächst eng begrenzter Entscheidungspunkt wendet eine neue Route korrekt an. | Vollständiger kleiner Simulationslauf: Störung -> Beobachtung -> Snapshot -> Route -> tatsächlich ausgeführte Fahrt und Ankunft. |
| M5: Konfiguration und stochastische Profile | Nach der vertagten Diskussion: Attribute/Profile und reproduzierbare Ziehungen. | Seed-/Kontext-Reproduzierbarkeit, Einlesevalidierung, XML-/Protobuf-Gleichwertigkeit und Verhalten ohne Profil. |

## Teststrategie und GitHub CI: vorläufiger Vorschlag

Drei Ebenen ergänzen sich:

1. Rust- und Java-Komponententests prüfen jeweils ihre eigene Fachlogik.
2. Vertragstests prüfen die Kommunikation. Ein Rust-Testdienst macht Zeitabläufe
   und Fehler gezielt steuerbar; mindestens ein zusätzlicher Test verwendet den
   echten Java-Prozess und die tatsächliche Serialisierung.
3. Ein kleines Ende-zu-Ende-Szenario prüft die fachliche Wirkung auf ausgeführte
   Fahrten, Anschlüsse und Passagierankunft, nicht lediglich erfolgreiche RPCs.

Für den echten Java-Test soll der Testablauf selbst verantwortlich sein für:

- Einen festgelegten Java-Service-Quellstand beziehungsweise ein versioniertes Artefakt.
  Kein unversionierter Download des jeweils neuesten Routers.
- Eine kleine lokale Testeingabe ohne große Szenariodownloads.
- Einen konfigurierbaren freien Port; die konkrete Vergabe wird beim Teststarter geklärt.
- Ein Bereitschaftssignal oder eine begrenzte Bereitschaftsabfrage statt einer
  pauschalen Startwartezeit.
- Begrenzte Laufzeiten, verständliche Fehler und Aufräumen auch bei Testfehlern.
- Aufbewahrung von Java-/Rust-Logs und bei Bedarf Snapshot-/Anfragedaten bei Fehlern.
- Dieselbe fachliche Ausführung lokal und in GitHub CI.
- Explizites Scheitern im vorgesehenen Kopplungsjob, wenn Java oder das Artefakt fehlt.
  Der Job darf einen fehlenden Service nicht als erfolgreichen Skip behandeln.

Normale Rust-Tests können weiterhin ohne Java laufen. Der dedizierte Kopplungsjob soll
auf Pull Requests ausgeführt werden; ob er anschließend als verpflichtende
Zusammenführungsprüfung eingerichtet wird, ist noch offen. Ein bewusst separater
Testaufruf darf nicht dazu führen, dass die Kopplung nur noch manuell geprüft wird.

Wichtige fachliche Testfälle:

- Eine bereits planmäßig abgefahrene Fahrt ist durch Verspätung noch erreichbar.
- Ein vorher erreichbarer Anschluss wird verpasst.
- Eine Verspätung macht einen zuvor nicht möglichen Anschluss erreichbar.
- Innerhalb einer Route bleibt die zugesicherte Reihenfolge auch bei individuellen
  Verspätungen und in den Prognosen erhalten.
- Zwischen verschiedenen Routen wird eine später abfahrende, früher ankommende
  Alternative berücksichtigt.
- Dieselbe Anfrage auf demselben Snapshot bleibt trotz späterer Updates unverändert.
- Nicht beobachtete, vorab gezogene Störungen beeinflussen den Router nicht.
- Unterschiedliche Reihenfolge der Meldungen und unterschiedliche Antwortlaufzeiten
  verändern bei gleichem vereinbartem Informationsstand nicht das fachliche Ergebnis.
- Ein fehlender Abschluss einer Partition verhindert die Veröffentlichung eines
  unvollständigen Snapshots.
- Eine Antwort wird nicht auf einen inzwischen unpassenden Passagierzustand angewendet.
- Die Ergebnisprüfung berücksichtigt die festgelegte Semantik gleichzeitiger Events;
  reine Dateireihenfolge ist nicht automatisch die relevante Gleichheit.

## Entscheidungsprotokoll

| Datum | Eintrag | Status |
| --- | --- | --- |
| 2026-11-12 | Nutzer vertagt Eingabe/Verteilungen und die Detaildiskussion zum Passagierverhalten. | Gesprächsreihenfolge festgehalten |
| 2026-11-12 | Nutzer schlägt eigenen Driver mit Ziehungen vor Fahrtbeginn vor. | Arbeitsrichtung, D01 offen |
| 2026-11-12 | Aufgebaute Verspätung soll zunächst weiter prognostiziert werden; Nutzer bevorzugt Prognose im Router. | Fortschreibung als Arbeitsrichtung; D02 offen |
| 2026-11-12 | Nutzer bestätigt Snapshots für eine deterministische Zuordnung von Routenanfragen. | Grundsatz bestätigt; D03 offen |
| 2026-11-12 | Inkrementelle Umsetzung und automatisierte Java-Rust-Tests in GitHub CI werden Teil des Entwurfs. | Ziel bestätigt; Schritte vorgeschlagen |
| 2026-11-13 | Nutzer bestätigt Variante A: Störungswerte vor Fahrtbeginn ziehen, tatsächliche Zeiten während der Fahrt fortschreiben. | D01 entschieden; konkrete Störungs- und Aufholregeln bleiben offen |
| 2026-11-13 | Nutzer weist auf fahrgastabhängige Haltezeiten und künftig veränderbare Boardingdauer hin und schlägt eine möglichst optimistische Prognose vor. | In D02 als Entwurf ausgearbeitet; Abgrenzung von Prognosefehler und Regelverletzung sowie gemeinsame Modellregeln vorgeschlagen, noch nicht bestätigt |
| 2026-11-13 | Nutzer bestätigt für den ersten Stand die Übertragung von Ankunfts-/Abfahrtsbeobachtungen und das Weglassen unbekannter zusätzlicher Boardingdauer in der Prognose. | D02 im Kern entschieden; konkrete Regeln, Parameter und Snapshot-Vertrag bleiben auszugestalten |
| 2026-11-13 | Nutzer bestätigt feste, konfigurierbare Snapshot-Intervalle mit Vollständigkeitsbestätigung aller Partitionen und fester Anfragezuordnung anhand der Simulationszeit einschließlich Warten auf den vorgesehenen Stand. | D03 im Kern entschieden; konkrete Intervalllänge, Grenzkonvention und weitere Ausführungsdetails bleiben offen |
| 2026-11-13 | Nutzer erklärt Nichtüberholung innerhalb einer Route zum zugesicherten Vertrag; Claude implementiert diese Eigenschaft parallel. | D04: keine Überholungsunterstützung innerhalb einer Route erforderlich; Prognosen erhalten die Ordnung, verschiedene Routen bleiben gesondert zu betrachten |
| 2026-11-13 | Nutzer vertagt die verbleibenden Fragen zu Neurouting-Auslösern, Verbindlichkeit der Fahrt, Antwortübernahme und Fehlerverhalten sowie zum Störungsmodell. | Offen und ausdrücklich vertagt; bisherige Empfehlungen sind keine beschlossenen Standardwerte oder Verhaltensregeln |
| 2026-11-19 | Nutzer beginnt mit der Vorbereitung des Routers. Rust soll die Snapshots einschließlich Prognose in einem nebenläufigen Thread erzeugen; die frühere Präferenz „Prognose im Router“ hatte keinen fachlichen Grund, sondern sollte einen Engpass vermeiden. | Arbeitsrichtung für D02/D03; der sprachübergreifende Modellvertrag für die Prognose entfällt |
| 2026-11-19 | Assistent schlägt Grenzkonvention (Events < kΔ in Snapshot k, Snapshot-ID ⌊now / Δ⌋ in Rust berechnet), Versand je Intervall und Änderungen je Fahrt ab Halt i statt vollständiger Snapshots vor; Begründung über Verarbeitungszeit statt Netz. | Vorgeschlagen, noch nicht bestätigt |
| 2026-11-19 | Nutzer bestätigt den Versand je Intervall und Änderungen je Fahrt statt vollständiger Snapshots. Leitlinie: möglichst wenige synchrone Punkte, an denen die Simulation auf Reisezeiten und Prognosen wartet. | D03: Versand und Format bestätigt |
| 2026-11-19 | Nutzer schlägt eine Grace Gap g vor: Snapshot k gilt erst ab kΔ + g, davor wird noch k − 1 verwendet. | Vorschlag; Formel k = max(0, ⌊(now − g) / Δ⌋) und Folgen (Informationsverzug, Szenarioparameter) vom Assistenten ergänzt, noch zu bestätigen |
| 2026-11-19 | Nutzer bestätigt die Grenzkonvention (Events < kΔ in Snapshot k), die Snapshot-ID k = max(0, ⌊(now − g) / Δ⌋), berechnet in Rust, und g als Szenarioparameter, der nicht zur Laufzeit angepasst wird. | D03 im Ablauf entschieden; Werte für Δ und g sowie Anhebung überfälliger Fahrten offen |
| 2026-11-19 | Nutzer entscheidet, SwissRailRaptor in einem Branch von matsim-libs umzubauen (statt Kopie in parallel-qsim-berlin oder eigenem RAPTOR). | D04: Ort entschieden; Schnittstelle, Datenhaltung, Snapshot 0 und Antwortformat vorgeschlagen |
| 2026-11-19 | Nutzer bestätigt die Eingrenzung der Transferfilter: `cannotReachAdditionalStops` nur noch innerhalb derselben Route, `hasNoPossibleDeparture` entfällt. | D04: Transferfilter entschieden |
| 2026-11-20 | Nutzer möchte die Umsetzung erst planen. Der Assistent stellt fest, dass matsim-libs PRs testet, aber erst beim Merge als `2027.0-PR<nr>` veröffentlicht, und schlägt den Umsetzungsplan Router vor (A1–C3, lokale Installation bis zum Merge). | Plan vorgeschlagen, noch nicht bestätigt; Annahme „PR-Release vor dem Merge“ korrigiert |
| 2026-11-20 | Nutzer streicht die Departure aus der Antwort: Rust braucht sie nicht, Linie, Route, Halte, Boarding-Zeit und Snapshot-ID bestimmen die geplante Fahrt. | E teilweise entschieden; B5 entfällt; Snapshot-ID in der Antwort und F (Punkte 3–7) noch offen |
| 2026-11-20 | Nutzer übernimmt die Empfehlungen: `snapshot_id` in der Antwort; Snapshot 0 einmal beim Start und eine Startmeldung je Iteration; Freigabe alter Versionen über die von Rust gemeldete älteste benötigte Version; asynchrones Warten mit Frist und Fehler statt Rückfall; Abbruch bei Vertragsverletzung; ein Delta für jedes k. Das Protokoll bleibt in matsim-schemas, während der Entwicklung per Pfad aus dem lokalen Checkout eingebunden. | A1 und Ort von A2 entschieden; Inhalt von A2 als Nächstes |
| 2026-11-20 | B1 umgesetzt (Branch `ph/raptor-timetable` in matsim-libs, auf Wunsch des Nutzers nur im Index, nicht committet). Den Benchmark in parallel-qsim-berlin stellt der Nutzer zurück. | B1 umgesetzt; Prüfung „nicht langsamer“ offen |
| 2026-11-20 | Der Nutzer schlägt vor, die Tabelle über Guice in `SwissRailRaptorFactory` injizierbar zu machen. Der Assistent analysiert: Injiziert wird ein Provider, der je Anfrage die Tabelle liefert, nach dem Vorbild von `RaptorStopFinder`; `RaptorTimetable` wird ein öffentliches `sealed interface`. Der Nutzer bestätigt. | B4 entschieden (ersetzt das Objekt unter einem festen Attributschlüssel); C2 angepasst |
| 2026-11-20 | B1–B4 auf Wunsch des Nutzers committet in `ph/raptor-timetable` von matsim-libs (b2c64193ec6, e8795ed0681, fbfcdaeb0dc, ee6bd3c66a0), nicht gepusht. B3 hält eine Zeile je Fahrt statt eines Blocks je Route. A2 umgesetzt im Branch `ph/timetable-updates` von matsim-schemas; der Nutzer wählt `uint64` in ns für die Zeiten, wie im übrigen Schema. | B1–B4 umgesetzt; A2 zum Review |
| 2026-11-20 | Der Nutzer nimmt A2 an. C1 committet in `ph/timetable-updates` von parallel-qsim-berlin (df1e158); der Branch baut gegen die lokal installierten Snapshots statt in einem Maven-Profil. Für C2 fragt der Nutzer, ob die Frist im Router nötig ist; der Assistent schlägt vor, darauf zu verzichten, weil ein endender Strom wartende Anfragen schon fehlschlagen lässt und Rust selbst eine gRPC-Deadline setzen kann. Der Nutzer stimmt zu. | A1 (c) geändert; C1 umgesetzt, C2 umgesetzt (nur im Index) |
| 2026-11-24 | B6 auf Lise gemessen und in `ph/timetable-updates` von parallel-qsim-berlin committet (738fe6f). Der Standard ist nicht langsamer; die Option kostet 26 %, die versionierten Zeiten 59 % gegenüber dem Standard, bei gleichen Routen. Der Router-Pfad je Delta braucht im ungünstigsten Fall 1,8 ms gegen ein Budget von 1,2 ms. Der Nutzer findet das halbwegs vertretbar. Kürzere Zeitfelder sparen beim Parsen nur 9–15 %, die Zeiten bleiben in ns. | B1, B3 und B6 abgenommen; Spielraum beim Delta-Pfad für später |
| 2026-11-25 | Der Nutzer befürwortet unterschiedliche Driver-Typen für unterschiedliche Verspätungskonzepte und Komplexitätsstufen. D01 ergänzt als Beispiel eine vorab gezogene, einmalige Zusatzfahrzeit auf einem S-Bahn-Abschnitt. | Driver-Typen als Arbeitsrichtung. Ziehungsmodell und Zahlen als Diskussionsbeispiel. |
| 2026-11-26 | Das Driver-Beispiel in D01 übernimmt die Herleitung aus dem Paper-Entwurf. Die Störung wird je Fahrt mit einer Wahrscheinlichkeit je Linie ausgelöst, der Ankunftshalt gleichverteilt gezogen. Bei einer beobachteten Schwelle je Linie wird $\mu$ vorgegeben und $p_L$ geschätzt. | Kalibrierungsansatz für das Beispiel. Szenariowerte und Umsetzung offen. |
| 2026-11-26 | Die Suche nach der nächsten Departure ab der Departure des Fahrplans (matsim-libs d10a5bfbec5, b6-lise-3) bringt nichts, weil der erste Cache-Miss auf die Zeile einer Departure den Aufwand bestimmt. Der Nutzer lässt den Commit wieder aus `ph/raptor-timetable` entfernen. | Verworfen; kleinere Arbeitsmenge der Versionen als Möglichkeit für M2 |
| 2026-11-26 | Abschluss der Java-Seite. matsim-schemas#5 bleibt WIP bis nach M2; ein Vorab-Tag geht nicht, weil `release.yml` nur `vX.Y.Z` veröffentlicht. matsim-libs#5306 ist „ready for review“, die Reviewer fragt der Nutzer an. `ph/timetable-updates` von parallel-qsim-berlin wird nur gepusht; einen PR gibt es erst nach den Releases, ohne Bau der Snapshots in der CI. | A2 wartet auf M2; B7 im Review; C1–C3 bis zu den Releases nur lokal getestet |
| 2026-11-26 | M1 geplant und umgesetzt. Der Nutzer entscheidet: Störung als Zusatzzeit an einem Halt i ≥ 0 (i = 0 Startverspätung), als Attribute der Departure analog zu den Offsets (`delayStopIndex`, `arrivalDelayOffset`, `departureDelayOffset`, `"HH:MM:SS"`, Standard 0), `departureDelayOffset` verlängert den Aufenthalt, ein eigener Driver-Typ, der an den `PlannedDriver` delegiert. Das Szenario `pt_delays` und der Berlin-Test mit fahrplanbasiertem Transit kommen zuerst als eigener PR (matsim-vsp/matsim-rust#361, gemergt), M1 darauf als matsim-vsp/matsim-rust#362. | D01 und M1 umgesetzt; gezogene Werte (M5) offen |

## Quellen im Projekt und Referenzen

- [Driver und Zeitfortschreibung](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/simulation/pt/driver.rs)
- [Transit Engine](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/simulation/engines/transit_engine.rs)
- [Transit-Datenmodell](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/simulation/scenario/transit.rs)
- [Events](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/simulation/events/mod.rs)
- [Passagier- und adaptive Logik](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/simulation/agents/agent_logic.rs)
- [Ursprüngliches Routing-Protokoll](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/src/external_services/routing/routing.proto)
- [Bisherige PT-Integrationstests](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/matsim_rust/tests/simulation/pt.rs)
- [CI-Workflow im untersuchten Rust-Stand](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/.github/workflows/rust.yml)
- [Testregeln](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/docs/tests.md)
- [Architektur](https://github.com/matsim-vsp/matsim-rust/blob/99bdffe0b1799e71680d2e93bb2327d3412b8c09/docs/architecture.md)
- [Java-Upstream: Factory](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorFactory.java)
- [Java-Upstream: Datenhaltung](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorData.java)
- [Java-Upstream: Router-Kern](https://github.com/matsim-org/matsim-libs/blob/main/matsim/src/main/java/ch/sbb/matsim/routing/pt/raptor/SwissRailRaptorCore.java)

Die Java-Links beziehen sich auf den zuvor untersuchten Upstream-Stand und sind kein
festgelegter Versionsbezug für die spätere Implementierung.
