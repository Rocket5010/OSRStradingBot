# 🚨 KRITISK REVISJON: OSRS INVESTER

**Revisor:** Senior Quant Developer (kynisk modus) + erfaren OSRS-mercher
**Dato:** 2026-06-21
**Mandat:** Uavhengig sikkerhets- og logikkrevisjon. Ingen tillit til forrige økts kode.
**Endringer i koden:** Ingen. Dette er kun en rapport.

---

## ⚠️ Forutsetning som endrer hele trusselbildet

Før panikken: **denne botten handler ikke selv.** README (`README.md:6-9`) er tydelig:
> «Bot = brain, you = hand. It never trades in-game.»

Botten *foreslår* kjøp og *anbefaler* salg — du klikker selv i GE. Det betyr at
overskriftens skrekkscenario — «botten tømmer banken min automatisk» — **ikke kan
skje bokstavelig**. Det finnes ingen kode som sender en handel til spillet.

Men ikke pust lettet ut. En rådgivningsbot som systematisk gir **feil råd** er
like farlig over tid — du er bare den lydige hånden som utfører tapet. Risikoene
under handler om hvordan botten kan *lure deg* til å brenne GP, ikke om at den
gjør det bak ryggen din. Det gjør dem mer lumske, ikke mindre.

---

## De 3 største økonomiske risikoene (nådeløst)

### 🥇 RISIKO 1 — Utdaterte/None-priser tas for ferske → råtne signaler og fantom-stop-loss

Dette er den verste, og den er stille.

`poller.py:11-20` skriver `low`/`high` fra `/latest` og setter `ts` til
**tidspunktet vi pollet**, ikke tidspunktet varen sist ble handlet. OSRS Wiki
sitt `/latest`-endepunkt gir `highTime`/`lowTime` per vare nettopp for å fortelle
deg hvor gammel prisen er — **botten kaster disse feltene rett i søpla.**

Konsekvens: en illikvid vare som sist ble handlet for 3 dager siden vises som
«fersk» med dagens tidsstempel. Alle strategier (`mean_reversion.py`,
`crash_recovery.py`, `margin_flip.py`) handler på den som om den er sann.

- **På kjøpssiden:** botten foreslår å kjøpe på en pris du aldri får, fordi det
  ikke finnes likviditet der.
- **På salgssiden (verre):** stop-loss leser en frossen `market.high`
  (`mean_reversion.py:49-51`, `crash_recovery.py:51-52`, `margin_flip.py:46-48`).
  Hvis prisen er fastlåst, fyrer stop-loss **aldri** — eller den ber deg dumpe på
  en kurs ingen kjøper. I et reelt krasj er «high» (instant-sell) det første som
  tørker ut. Stop-loss er teoretisk trygghet, ikke reell.

**Ingen None-vern.** API-et returnerer `null` for `low`/`high` på varer som
mangler en side. `poller.py:19` lagrer `None` rått. Det flyter videre til
`engine_live.py:73` → `ge_tax(m.high)` → `tax.py:11` → `floor(None * 0.02)` →
`TypeError`. Hele `evaluate`-passet kræsjer den tikken. `_loop`
(`scheduler.py:224-230`) fanger og lever videre, men neste tikk kræsjer på samme
vare — botten kan slutte å produsere signaler helt til kuratoren tilfeldigvis
luker bort varen.

**Ingen fornuftsgrenser / pump-and-dump-vern.** Det finnes ingen sjekk av typen
«prisen hoppet 10x siden forrige poll → ignorer». En enkelt fat-finger-handel
eller en bevisst manipulasjon (klassisk OSRS pump) tas som ekte data. Spør
revisjonsmandatet etter dette eksplisitt — svaret er nei, vernet finnes ikke.

> **Quant-dommen:** «Garbage in, gospel out.» Botten har null tillitsvurdering av
> egen datakilde. Det er den enkeltfeilen som forplanter seg til alt annet.

---

### 🥈 RISIKO 2 — Backtesten er systematisk for optimistisk, og auto-piloten setter ekte kapital på den

Auto-piloten (`scheduler.py:117-137`) rangerer alle strategier ukentlig og
allokerer auto-budsjettet ditt til «vinnerne». Problemet er hva den rangerer
**på.**

`backtest/engine.py`:
- Kjøper på candle-ens `avgLowPrice` (`engine.py:90-101`) og selger på
  `avgHighPrice` (`engine.py:83-84`) — **ofte i samme candle.** Det betyr at
  backtesten antar at du alltid treffer periodens bunn på kjøp og periodens topp
  på salg, og fanger hele spreaden hver eneste runde.
- **Null slippage. Ingen order-book-dybde.** README innrømmer det selv
  (`README.md:174-175`), men det blir likevel grunnlaget for kapitalallokering.
- Selv tvungen exit (`max_hold_steps`, `engine.py:80-85`) selger på gunstig
  `hi`.
- Volumtaket lar deg «kjøpe» opptil **100 %** av en candles omsatte volum
  (`engine.py:91`) — i praksis ville du flyttet prisen mot deg selv lenge før
  det.

Resultatet er at en strategi som ser ut som «+25k gp/dag, 85 % win, 3 % drawdown»
(eksempel rett fra `README.md:152-153`) i stor grad kan være en **artefakt av
fyll-antakelsen.** Live kjøper du høyere, selger du lavere, betaler reell skatt og
mister handler som backtesten antok at fylte. Den realiserte kanten kan være
negativ — og auto-piloten har nettopp pekt budsjettet ditt dit med selvtillit.

Diversifisering over topp-N (`scheduler.py:128-137`) demper variansen, men
beskytter deg ikke mot at **alle** N strategiene er rangert på samme
overoptimistiske målestokk. Du diversifiserer over flere varianter av samme
illusjon.

> **Quant-dommen:** En backtest som kjøper på low og selger på high i samme bar er
> ikke en backtest, det er en ønskeliste. At den driver live kapitalallokering er
> den dyreste designfeilen i prosjektet.

---

### 🥉 RISIKO 3 — Ingen reell GE-restriksjons- eller kapitalrotasjons-bokføring → kapital fryser fast

To hull som sammen gjør at GP-en din blir sittende død.

**A) 4-timers kjøpsgrense bokføres ikke kumulativt.** `sizing.py:13-14` kapper
*ett enkelt signal* til `buy_limit`. Men GEs grense er et **rullerende 4-timers
vindu over alle dine kjøp av varen** — botten sporer ingenting. Med diversifisert
auto-pilot kan to ulike runs sikte på samme vare (det finnes ingen sjekk på tvers
av runs i `engine_live.py:39-44`; `_has_open_position` er per `run_id`), og
sammen sprenge 4t-grensen. Resultat: aksepterte ordrer som aldri fylles.

**B) Null logikk for ordre-stagnasjon.** Dette er spørsmål 4 i mandatet, og
svaret er brutalt: det finnes **ingen** håndtering.
- En `accepted`-ordre som ikke fylles i spillet blir liggende **for alltid**.
  Det er ingen tidsbasert utløp, ingen «denne har stått i 3 dager».
- Det er **ingen** anbefaling om å underby/overby (undercut/overcut) for å få
  fyll. Botten beskjærer kun *proposed*-signaler som strategien ikke lenger vil
  ha (`engine_live.py:85-97`) — den rører aldri en akseptert ordre.
- README sier «Use Cancel for any order that doesn't fill» (`README.md:70`).
  Med andre ord: *du* er stagnasjonshåndteringen. Manuelt. Hver gang.

**Og her biter det:** `accept()` (`positions.py:60-66`) legger kostnaden til
`spent_gp`. `available()` (`runs.py:116-118`) er `budget_gp - spent_gp`. Kapital
frigjøres **kun** ved `mark_sold` eller `cancel` (`positions.py:84-105`). En død,
aldri-fylt ordre holder altså GP-en låst og sulter resten av budsjettet i det
stille — helt til du selv husker å kansellere. Botten vil aldri minne deg på det.

**Bonus-stillhet:** salgssignaler fyres **én gang** per posisjon
(`engine_live.py:113-117` sjekker `status='shown'`). Ignorerer du varselet,
blir du aldri purret på nytt — heller ikke om stop-loss-betingelsen forverres.

> **Quant-dommen:** Bot som åpner posisjoner uten å eie hele livssyklusen
> (inkludert «ordren min råtner») er en halv bot. Den halvdelen som mangler er
> den som beskytter kapitalen din.

---

## Svar på de fire mandatpunktene

### 1. API-feilhåndtering og data-stale

| Tilfelle | Håndtering | Dom |
|---|---|---|
| 502 / HTTP-feil | `api_client.py:38-39` → `ApiError`. `poll_once` fanger ikke; `scheduler._loop:228-229` fanger og fortsetter. Ingen kjøp den tikken. | OK på overlevelse — **men** `price_cache` beholder forrige polls priser, som blir eldre uten at noe markerer dem stale. |
| Tomt svar / manglende `data`-nøkkel | `["data"]` (`api_client.py:47-63`) gir `KeyError` → tikk avbrytes. | Akseptabelt fail-safe, men brutalt (ingen graceful degrade). |
| `null` low/high | Lagres rått (`poller.py:19`) → `TypeError` i `ge_tax` nedstrøms. | **Bug.** Se Risiko 1. |
| Utdaterte priser | `highTime`/`lowTime` ignoreres totalt. Ingen staleness-grense. | **Alvorlig hull.** Se Risiko 1. |
| Panikk-kjøp på falsk topp (pump) | Ingen avvik-/spike-deteksjon. | **Sårbart.** Men: mennesket klikker, så ikke automatisk katastrofe. |

### 2. GE-restriksjoner (skatt og kjøpsgrenser)

- **Skatt:** modellert i `tax.py` — **2 %** (`TAX_RATE = 0.02`), gulvet, kappet på
  5M per vare. Brukes konsekvent live (`engine_live.py:73`, `positions.py:88`) og
  i backtest (`engine.py:37`, `:84`).
  - ⚠️ **Mandatet sier 1 %.** Det stemmer ikke med koden, og det stemmer ikke
    nødvendigvis med dagens Jagex-regel heller. GE-skatten startet på 1 % (2021)
    og er senere endret. **Verifiser gjeldende sats og tak mot Jagex før du
    stoler på marginene** — er satsen feil, er *hver* margin- og P/L-beregning i
    botten feil. (Koden bruker 2 %; mandatets 1 % er trolig utdatert. Sjekk.)
  - Mindre hull: spesifikke skatte-unntatte varer modelleres ikke. <50 gp-varer
    blir riktig 0 via gulvet, så det er greit; den eksplisitte unntakslisten er
    ikke implementert (lav betydning).
- **Kjøpsgrenser:** `size_qty` (`sizing.py`) leser `buy_limit` fra mapping
  (`market.py:50`) og kapper ett signal. **Den rullerende 4t-grensen på tvers av
  fyll/posisjoner/runs spores ikke** (Risiko 3A). Backtesten modellerer en grov
  per-candle-grense (`engine.py:54-55`), men det finnes ingen ekvivalent live —
  så ja, kapital kan låses i ordrer som aldri fylles fordi grensen er brukt opp.

### 3. Risikostyring og porteføljebalanse

- **Stop-loss finnes** per strategi (`stop_loss_pct`, f.eks.
  `mean_reversion.py:49`, `crash_recovery.py:52`, `margin_flip.py:47`). Bra — men
  den er (a) kun et *varsel* du må handle på, (b) **engangs** (Risiko 3 bonus), og
  (c) avhengig av fersk `high` (Risiko 1). I et reelt krasj er alle tre mot deg.
- **Maks eksponering per vare:** ingen global grense. `_has_open_position`
  (`engine_live.py:39-44`) tillater kun én åpen posisjon per vare **per run** —
  men ett enkelt `find_buys` kan dimensjonere qty opp til **hele run-budsjettet**
  i én vare (sizing kappes av budsjett/volum, ikke av en per-vare-andel). Med N
  runs kan altså 1/N av auto-budsjettet havne i én oppdaterings-spekulasjon.
- **Scenarioet i mandatet (90 % i én raid-spekulasjon):** ikke mulig på auto-pilot
  *hvis* `auto_strategies` ≥ 2 (budsjettet splittes, `scheduler.py:134`). Men en
  **manuell** run har ingen slik beskyttelse — der kan du dytte hele run-budsjettet
  i én vare, og krasjer den, er stop-loss-varselet din eneste redning (se over).
- **Ingen porteføljenivå kill-switch / maks total drawdown.** Stopper ikke seg
  selv om alt blør samtidig.

### 4. Ordre-stagnasjon og likviditet

Dekket fullt i Risiko 3B. Kort: **ingen** auto-kanselering, **ingen**
undercut/overcut-anbefaling, **ingen** tidsutløp på aksepterte ordrer. Kapitalen
blir bare sittende, og `available()` regner den som brukt. Manuell `Cancel` er
hele løsningen. Likviditetsvern på kjøp finnes delvis (`vol_fraction` i
`sizing.py:15-16`), men gjelder kun ved *inngang* — ikke utgang, og ikke for
ordrer som allerede står fast.

---

## Hurtigtabell: hva som faktisk er bra (rettferdighetens skyld)

- ✅ Skatt modellert på riktig side (kun salg), med 5M-tak.
- ✅ Stop-loss eksisterer i alle posisjons-strategier.
- ✅ Rate-limiting med global lås på API-klienten (`api_client.py:29`).
- ✅ Scheduler-loopen overlever exceptions og dør ikke (`scheduler.py:228-229`).
- ✅ Backtest komponerer ikke (fast budsjett) — unngår eksponensielt tøv.
- ✅ Volum-/likviditetstak på *inngang* (`vol_fraction`).
- ✅ Botten handler aldri selv — det største sikkerhetsnettet av alle.

---

## Anbefalte tiltak (prioritert — ingen er utført)

1. **Bruk `highTime`/`lowTime`.** Marker priser eldre enn X som stale; ikke
   foreslå kjøp og ikke stol på stop-loss på stale data. (Adresserer Risiko 1.)
2. **None-vern.** Hopp over / vis tydelig varer med `null` low/high før de når
   `ge_tax`. (Risiko 1.)
3. **Spike-/avviksfilter.** Avvis priser som hopper urealistisk mot forrige poll.
   (Pump-and-dump-vern.)
4. **Realistisk backtest-fyll.** Kjøp ved high (eller midt-spread + slippage),
   ikke ved low; selg ved low/midt. Re-evaluer all rangering etterpå. (Risiko 2.)
5. **Kumulativ 4t-grense-sporing** på tvers av runs/posisjoner. (Risiko 3A.)
6. **Ordre-aldring:** flagg/auto-utløp aksepterte ordrer over N timer, foreslå
   undercut/overcut, og purr salgssignaler på nytt. (Risiko 3B.)
7. **Verifiser GE-skattesatsen** mot dagens Jagex-regel før du stoler på én eneste
   margin. (Mandatpunkt 2.)
8. **Per-vare eksponeringstak** og porteføljenivå drawdown-stopp. (Risiko 3 /
   mandatpunkt 3.)

---

*Slutt på rapport. Ingen kodeendringer gjort — som bestilt.*
