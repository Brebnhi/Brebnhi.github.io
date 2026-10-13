# Aalborg Volley – klubbens værktøjer

Ét GitHub Pages-site med klubbens værktøjer. Startsiden viser nattens status og
fører videre til det enkelte projekt:

**https://brebnhi.github.io/**

| Side | Adresse | Hvad den gør | Hvor koden ligger |
|---|---|---|---|
| Startside | `/` | Vælg projekt; viser om tjanserne er dækket og den forventede kørselsudligning | `tjans/docs/index.html` (fast fil) |
| Tjanser | `/tjanser/` | Tjans-kalendere til Holdsport og overblik over huller | `tjans/` – se `tjans/README.md` |
| Kalender-feeds | `/feeds/*.ics` | Kalenderne til Holdsport | bygges af `tjans/scripts/build.py` |
| Kørselsudligning | `/koerselsudligning/` | Forventet rejseudligning fra Volleyball Danmark | `koerselsudligning/` – se README dér |
| Kontingent | `/kontingent/` | Forventet kontingent ud fra en Holdsport-eksport | `tjans/docs/kontingent/index.html` (fast fil) |
| Kontingentmodel | `/kontingentmodel/` | Hvad bruger hvert hold, og hvor kommer pengene fra – kontingentet, holdets egne indtægter og det, klubben lægger til? Siden åbner på et enkelt overblik over holdenes udgifter, indtægter og resultat – og den takst, hvor kontingentet alene dækker halleje, turnering og dommere; fanen Ret tal retter takster, fritagne, hvad kontingentet skal dække, tøj og aktivitetstilskud for alle hold. Hvert hold er et lille regnskab, og listen har en søjle pr. hold. Fanen Klubben viser, hvordan holdenes underskud dækkes, vejen fra budgettets resultat til sidens og klubbens egne poster; fanen Kørsel prøver kørepenge – også det, VD's kørselsudligning giver pr. km. Kræver kode | `tjans/docs/kontingentmodel/index.html` (fast fil) – se *Kontingentmodellen* nedenfor |
| Budget | `/budget/` | Budget mod realiseret direkte fra budgetarket – alle posteringer pr. budgetpost, hold og arrangement. Kræver kode | `tjans/docs/budget/index.html` (fast fil) og `adresse.txt` ved siden af – se *Budgetsiden* nedenfor |
| Turpris | `/turpris/` | Sæsonens udeture for alle hold – D1's ture til Sjælland i lejebiler (klubben betaler), alle andre i egne biler (spillerne betaler) – hvad en kørselsgodtgørelse ville koste klubben, og en regner til den enkelte tur | `tjans/docs/turpris/index.html` (fast fil; kampene hentes fra kørselsudligningen) |
| Gammel adresse | `/Tjanser-i-Holdsport/` | Holdsports importer peger herhen – se nedenfor | bygges af `tjans/scripts/build.py` |
| Påmindelser | `/paamindelser.json` | Det, der skal gøres til en ny sæson – vises øverst på startsiden | bygges af `tjans/scripts/vedligehold.py` |

Robotten i `.github/workflows/main.yml` kører hver nat kl. 04.20 (vintertid) / 05.20
(sommertid), ved hver ændring i repoet og når du trykker Run workflow under Actions.
Ændrer du tjanselisten i Google-arket, starter `.github/workflows/tjek-arket.yml` den
inden for ca. 10 minutter – den kigger efter ændringer i arket hvert 10. minut fra morgen
til midnat.

**Upload fra telefonen:** læg filerne løst i roden af repoet (Add file → Upload files).
Robotten kender hver fil på indholdet og lægger den på plads – også `build (1).py` og
lignende. En helt ny fil kan have en linje `sti: mappe/fil` øverst. Kun
filerne i `.github/workflows/` kan robotten ikke flytte – dem uploader eller retter du
direkte i den mappe på GitHub.

## Repoets navn og den gamle adresse

Repoet hed `Tjanser-i-Holdsport`, da det kun lavede tjans-kalendere. Nu hedder det
`Brebnhi.github.io`, fordi et repo med det navn bliver sitet på selve
https://brebnhi.github.io/ – uden repo-navn i adressen.

De 11 importer i Holdsport blev lavet med adresser som
`https://brebnhi.github.io/Tjanser-i-Holdsport/feeds/D1-4pers.ics`. Robotten lægger hver
nat en kopi af kalenderne på den sti, så importerne virker uændret. De gamle sider sender
videre til de nye.

- **Slet ikke** `Tjanser-i-Holdsport`-stien (koden `gammel_adresse` i `build.py`), så længe
  Holdsport henter derfra. Skal den væk, så importér først kalenderne igen med adresserne
  fra `/tjanser/`, fx ved et sæsonskifte.
- **Omdøb ikke repoet igen.** Et user site skal hedde `<brugernavn>.github.io`.
- **Lav aldrig et nyt repo, der hedder `Tjanser-i-Holdsport`.** Det ville skygge for den
  gamle sti og bryde kalenderne.

## Det må du ikke

- **Lægge medlemsdata i repoet.** Repoet og siden er offentlige. Kontingentsiden viser først
  tal, når du selv lægger en Holdsport-eksport ind, og eksporten og fritagelseslisten gemmes
  kun i din egen browser. Det samme gælder turprisens gemte ture.
- **Flytte `/feeds/` eller den gamle sti.** Holdsport henter derfra.
- **Bruge «Udgiv på nettet» på budgetarket** eller lægge links til det i repoet. Budgetsiden
  henter tallene gennem scriptet i arket, så arket kan forblive privat.

## Budgetsiden

`/budget/` indeholder ingen tal. Når siden åbnes, spørger den et lille Google-script, der ligger
i selve budgetarket (Udvidelser → Apps Script), og scriptet svarer kun, når koden er rigtig. Efter
10 forkerte forsøg holder det lukket i 15 minutter. Adresserne på scripterne står i
`tjans/docs/budget/adresse.txt` – én linje pr. sæson, nyeste nederst:

```
25/26 https://script.google.com/macros/s/…/exec
26/27 https://script.google.com/macros/s/…/exec
```

Sæsonen foran adressen kan udelades (siden læser den så i arket). Siden åbner den nyeste sæson,
og man kan skifte sæson i overskriften og sammenligne to sæsoner på fanen *Sammenlign*.

- **Nye posteringer** står på siden, så snart de er i arket – der er intet at uploade.
- **Navnet på en postering** er kolonnen *Reference* i Konto 1/Konto 2. Uden reference bruger
  siden bankens tekst uden numre og koder.
- **Siden regner som arket.** Hver gang den henter, regner den arkets egne tal efter (Overblik,
  Hold - status, Event og saldi) og siger til, hvis de ikke stemmer – fx hvis arkets opbygning
  er ændret.
- **Nyt ark (1. juni):** Åbn `/budget/#opsaetning` og følg de fire trin i det nye ark – brug samme
  kode som sidste sæson. Til sidst **tilføjer du en ny linje nederst** i `adresse.txt`; siden
  kopierer linjen for dig. **Lad de gamle linjer og det gamle ark blive**, så siden stadig kan
  vise de tidligere sæsoner og sammenligne med dem.
- **Skift kode:** Ret linjen `var KODE = "…"` øverst i scriptet, gem, og vælg Implementer →
  Administrer implementeringer → blyanten → Version: Ny version → Implementer.

## Kontingentmodellen

`/kontingentmodel/` indeholder heller ingen tal fra budgettet. Den henter fanerne *Budget* (budgetlinjer,
poster og KONTINGENTBUDGET), *Hold - status*, *Konto 1* og *Konto 2* gennem **samme script og samme kode
som budgetsiden** – adressen er den nederste linje i `tjans/docs/budget/adresse.txt`. Er budgettet låst
op med «Husk koden», åbner modellen også. Udeture, km og den forventede kørselsudligning kommer fra
kørselsudligningens `status.json`.

- **Overblik** (forsiden – siden åbner altid her): holdenes udgifter, indtægter og resultat i én enkel
  tabel, grupperet i divisionshold, øvrige hold og ungdom, med klubbens egne poster og i alt (= klubbens
  resultat). Ingen knapper eller skydere – klik på et hold for detaljerne. Kolonnen **Takst for faste** er
  den takst pr. rate, hvor kontingentet alene dækker holdets halleje, turnering og dommere (efter gebyret,
  med de fritagne – posterne ÷ (rater × 99 %), rundet op); den står med rødt, når den er højere end
  taksten nu. På mobilen står den under holdnavnet.
- **Ret tal** (fanen): alt, der rettes for alle hold på én gang – **takst og fritagne rater**, **hvad
  kontingentet skal dække**, **tøj** (antal sæt, hvor ofte holdet får nyt, og hvad det koster at lukke huller)
  og **aktivitetstilskuddets** medlemmer pr. aldersgruppe. Et rettet felt bliver blåt; tomt felt giver
  tallet fra budgettet igen.
- **Hvad skal kontingentet dække?** (kortet under Ret tal) bestemmer forsidens takst-kolonne: kryds flere
  af holdets poster af (udgifter lægges til, indtægter trækkes fra), læg klubbens poster ud på holdene –
  *alle hold pr. spiller*, *alle hold ligeligt* eller *ét hold* – og skriv **egne poster** (udgift eller
  indtægt, beløb pr. sæson og hvor de lægges ud). Kolonnen hedder så *Takst for valgte*. Det ændrer kun
  den takst – ikke holdenes regnskab eller klubbens resultat. Kommer et hold under nul, er taksten 0.
- **Hvert hold er et regnskab** (fanen Hold) i to kolonner: det, holdet **bruger**, og det, holdet **får ind** –
  kontingentet fra spillerne, de fritagnes kontingent (som klubben betaler) og holdets egne indtægter.
  Under dem står, hvad **klubben dækker**, og hvad der **mangler** – eller holdets **overskud til
  klubben**. **Listen** viser det samme som en søjle pr. hold: længden er det, holdet bruger, og
  farverne er, hvor pengene kommer fra. Holdets poster er dets egne poster i budgettet og dets del af
  poster, der hører til bestemte hold.
- **Holdets resultat** = kontingentet med holdets takst (2 rater × alle spillere, minus 1 % gebyr og
  afgang) − udgifterne + indtægterne. Taksten er den nuværende fra KONTINGENTBUDGET, men du kan
  skrive **et hårdt tal** i stedet under **Justér** (eller Ret tal) – det samme med antallet af
  **fritagne rater** (KONTINGENTBUDGET's trænerkomp. + bestyrelseskomp.). Dér kan rejser, trænere, andre udgifter,
  egenbetaling, tilskud, SIFA, bolde, klubaktiviteter og kørselsudligning også justeres for holdet
  alene – og du vælger, hvor ofte holdet får nyt tøj, og hvor mange sæt. **Halleje, turnerings- og dommergebyr er faste** – klubben kan ikke betale mindre.
- **Klik på en linje** i regnskabet for at se, hvad der ligger i den: budgettets poster og det, der er
  bogført i sæsonen (*Aktuel sæson* = Ja), delt op i udgifter og indtægter – delte poster med holdets
  andel. Kontingentet viser udregningen, og *Klubben dækker*, *Mangler* og *Overskud til klubben*
  forklarer klubbens del.
- **Halleje** er sæsonens bookinger i Fritidsportalen (uden Skipper Clement) – de erstatter budgettets
  halleje. Træningstiden deles efter holdenes **banetimer** i træningsplanen (baner × timer – hele
  hallen i to timer er 6 banetimer, så et hold med én af tre baner betaler en tredjedel). Kampe og
  stævner deles efter 9 hjemmekampe à 2 t for divisionsholdene og 2 hjemmedage à 9 t for DU15, DU17,
  HU15/17, H4, D4 og OB. **Opstilling og nedtagning** deles ligeligt på alle hold undtagen Dame 5 og
  Kids. Vægtløftningen går til H1 og D1, stævner og camp til Kids, Mix og ungdommen. Booket tid, som
  intet hold bruger, skolevolley, juleturnering, ekstra træning og klublokalet ligger på klubben. Uden
  bookinger for sæsonen deles budgettets halleje efter træningstimer pr. uge à 46 kr. (23 kr. pr.
  halve time).
- **Poster til bestemte hold:** kørselsudligningen til pokalen deles ligeligt på H1, H2, D1 og D2,
  Volley-TV og Datavolley er D1's (under *Andre udgifter*), og Hørby-campen hører til U15-holdene
  (DU 15 og HU15/17). **Ungdommens fælles poster** deles pr. spiller i ungdommen – rejserne ligeligt
  pr. hold. **Dame 5 og Kids** har ingen del i opstilling, rejser og SIFA, og Kids heller ikke i
  egenbetaling (`RAMME.undtag`).
- **Nyt tøj** er ikke med i beregningen, før du vælger, **hvor mange år der går, før hvert hold får
  nyt** – på fanen Ret tal (også for alle hold på én gang) eller under Justér på holdet. Holdet betaler så prisen delt med årene hver sæson, og kortet viser, hvad klubben skal lægge
  til side pr. sæson. Et sæt pr. spiller + 2 (HU 20 og DU 20: 14 sæt hver – deres tøj ligger på
  klubben); **antallet af sæt kan rettes for hvert hold** samme steder (tomt felt giver standarden). H1 og D1 får spillertøj, træningsdragt og opvarmningstrøjer (D1 også strømper), de andre
  spillertøj. Priserne pr. sæt er fra D1's faktura og kun det print, klubben ikke kan fakturere til
  sponsorerne: spillertøj 554 kr., opvarmningstrøje 178 kr., træningsdragt 618 kr. – strømper har ingen
  pris endnu. **At lukke huller** er et beløb pr. sæson for hvert hold – budgettets tøj til holdet (D1's
  3.000 kr.), til du retter det. «Alle hold på én gang» springer H5, D5 og Kids over (`RAMME.toej`).
- **Aktivitetstilskuddet** fra kommunen deles efter kommunens point: 7-17 år 10 point, 18-24 år 2 point og
  0-6 år 1 point pr. medlem (2025: 370, 74 og 37 kr.). Ungdomsholdenes spillere regnes som 7-17 år; de
  andre holds 18-24-årige skriver du under Ret tal. HU 20 og DU 20's andel bliver på klubben
  (`RAMME.aktivitet`).
- **SIFA:** TV-bingo/SIFA på klubben går 2/3 til D1 og 1/3 til H1, og SIFA's 6.000 kr. til ungdommens
  kørsel til Scandinavian Masters går til holdene med stævnet i budgettet. **Bolde:** D1 får 12 bolde
  à 700 kr. gennem ligaen – en indtægt for D1.
- **Faste udgifter:** under holdets regnskab står, om kontingentet dækker holdets faste udgifter –
  halleje, turnering og dommere.
- **Klubben** (fanen): **sponsorater** og **det, klubben tjener ved at stille frivillige hjælpere**
  (Frivilligarrangement – indtægt) har hver sin skyder. Det samme har **overskuddet pr. sæson**
  (10.000 kr. i rammen). Klubbens indtægter − klubbens egne udgifter + holdenes overskud −
  fritagelserne − overskuddet dækker holdenes underskud, **med samme procentdel til alle hold med
  underskud**. Det, der ikke er dækket, **mangler** og skal skaffes ad andre veje – eller lægges på
  holdets kontingent. Fanen viser også **vejen fra budgettets resultat til sidens** (fanen *Budget*:
  indtægter i alt − udgifter i alt; halleje, SIFA og bolde efter rammen – og nyt tøj og dine justeringer) og
  **klubbens egne poster**: alt, der ikke kan lægges præcist på et hold eller mellem bestemte hold – IT,
  abonnementer, trænertøj, kurser, porto, bestyrelse, gaver, bøder, festerne, Bambusa og holdene uden
  kontingent (DU 20, HU 20). Klik på en linje for posterne.
- **Kørsel** (fanen): kørepenge til spillere i egne biler med en skyder for satsen pr. km. Hvert hold
  betaler sine egne – km fra natkørslen for divisionsholdene og Danmarksserien (H4 og H5), biler fra
  turprisen (ellers natkørslens), og ekstra ture kan skrives ind – også for hold, der ikke er i VD's
  kampprogrammer (damerne i serierne, ungdom, Mix og Kids). D1's ture til Sjælland i lejebil står under rejseomkostninger. *Pr. rate* er, hvad
  kørepengene svarer til på holdets kontingent. **Grænsen** er, hvor langt væk kampen skal være (km
  én vej), før der er kørepenge – enten *kun km ud over grænsen* (de første km hver vej er spillerens
  egne) eller *hele turen, når kampen er længere væk*. Den gælder også ekstra ture. **VD giver** er
  det, VD's kørselsudligning til holdet (natkørslens forventning) minus holdets egne rejser rækker til
  pr. km, der giver kørepenge (km × biler) – højst statens laveste takst. Knappen *Det, VD giver pr.
  hold* giver hvert hold den sats; med en grænse bliver satsen højere, og når den rammer statens takst,
  bliver resten af udligningen i klubben.
- **Fritagne** (trænere og frivillige) tæller med som spillere, så deres gratis kontingent er en udgift
  for klubben – holdkammeraterne betaler ikke for dem.
- **Gebyr og afgang:** siden trækker kun den 1 %, der reelt går til gebyrer (`RAMME.gebyr`). Budgettet
  regner med 5 % – de 4 % ekstra er en buffer mod dem, der ikke betaler – så kontingentet her er større
  end budgettets, og forskellen står som en linje i broen.
- **Holdets egen takst** – den takst, der lige dækker holdets egne tal uden hjælp fra klubben –
  står ved kontingentet og under Justér, rundet til 50 kr.
- **Rammen** – bookingerne og træningsplanen (banetimer pr. hold), hjemmekampe og hjemmedage,
  vægtløftningen, tøjpriserne, SIFA, boldene, klubbens indtægter og overskud, poster til bestemte hold
  og undtagelserne – står i `RAMME` øverst i scriptet. Ret dér, når noget ændrer sig. Bookingerne
  gælder kun for den sæson, der står i `RAMME.hal.saeson`.
- **Dine justeringer** gemmes kun i din browser. *Del* kopierer et link med dem (#s=…) – modtageren
  skal også have koden.
- **Ny sæson:** Modellen tager det nyeste budgetark fra `adresse.txt` og holdene fra
  KONTINGENTBUDGET. Posterne findes ud fra budgetlinjernes navne. Se efter i `RAMME`, om timer,
  tøj, SIFA og overskuddet stadig passer.
- **Udregningen** står mellem `MODEL-START` og `MODEL-END` i filen og kan testes for sig uden browser.

## Når natkørslen står stille

GitHub slår natkørslen fra, når et offentligt repo har været uden aktivitet i 60 dage.
Robotten holder sig selv i live: den slår workflowet til hver nat (det nulstiller uret), og
har ingen committet i 50 dage, skriver den et livstegn i `tjans/data/puls.txt`.

Står den alligevel stille, viser startsiden en advarsel, når status er mere end 30 timer
gammel. Gå til **Actions → Opdater tjans-kalendere** og tryk **Enable workflow** (og evt.
**Run workflow**).

## Ny sæson

Det meste følger med af sig selv. Når der er noget, kun du kan gøre, opretter robotten et
GitHub-issue med labelen **ny sæson** og en tjekliste. GitHub sender en mail, og startsiden
viser det øverst under *Til den nye sæson*. De issues, robotten selv kan tjekke, lukker sig,
når det er gjort. Lukker du selv et issue, lader robotten det være.

| Projekt | Følger med af sig selv | Det gør du | Påmindelse |
|---|---|---|---|
| Tjanser | Sæsonen i overskriften, kampprogrammer og holdkoder, kalenderne, flyttede kampe | Ny tjanseliste i Google-arket – se *Tjanselisten* i `tjans/README.md` | Når VD har lagt den nye sæsons kampprogram ud. Lukker sig selv |
| Kørselsudligning | Sæson, hold, pokal og slutspil | Årets km-takst og bropris i `koerselsudligning/config.json` | 10. januar. Lukker sig selv |
| Kontingent | Overskrifter, U17-årgang og budgetboks | `BUDGET_SAESON`, `HOLD` og `BUDGET_IALT` øverst i scriptet i `tjans/docs/kontingent/index.html` (fra fanen *Kontingent status*), og `MOENSTRE`/`ERMIX` ved nye holdnavne | 1. august. Lukker sig selv |
| Kontingentmodel | Budgetlinjer, poster, posteringer, hold, satser og antal fra det nyeste budgetark; udeture og forventet kørselsudligning fra natkørslen | Læg den nye sæsons bookinger fra Fritidsportalen og træningsplanen (banetimer pr. hold) i `RAMME.hal` øverst i scriptet i `tjans/docs/kontingentmodel/index.html`, og se efter, om hjemmedagene, tøjpriserne, SIFA og målet for overskud stadig passer. Indtil da deles budgettets halleje efter træningstimer | – |
| Turpris | Sæson, grundspillets udekampe, km og dobbeltweekender (D1: lørdag + søndag på Sjælland). Pokal og slutspil tæller ikke med | `PRISER_SAESON` og priserne (`STANDARD`, `SAESON`) øverst i scriptet i `tjans/docs/turpris/index.html` – og `EKSTRA_UDEKAMPE`, hvis VD's program mangler en udekamp | Når kampprogrammet for den nye sæson er ude. Lukker sig selv |
| Try-out (Vercel) | – | Væk Supabase og følg [guiden](https://docs.google.com/document/d/19cpzGXU_s858MQe_A-r4YyGGtSu8ppPURRt6Rq8Q1bY/edit) | 1. juni. Luk den selv, når billederne er slettet |
| Budgetarket | Budgetsidens udregning (den læser arkets faner og formler) og de tidligere sæsoner | Nyt budget, nyt ark og primosaldi pr. 1. juni – og budgetsidens script i det nye ark plus en ny linje i `adresse.txt`, se *Budgetsiden* | 1. juni. Luk den selv |

Prøv påmindelserne uden at røre GitHub: `python tjans/scripts/vedligehold.py --test --nu 2027-08-15`.
