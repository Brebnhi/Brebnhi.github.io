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
10 forkerte forsøg holder det lukket i 15 minutter. Adressen på scriptet står i
`tjans/docs/budget/adresse.txt`.

- **Nye posteringer** står på siden, så snart de er i arket – der er intet at uploade.
- **Navnet på en postering** er kolonnen *Reference* i Konto 1/Konto 2. Uden reference bruger
  siden bankens tekst uden numre og koder.
- **Siden regner som arket.** Hver gang den henter, regner den arkets egne tal efter (Overblik,
  Hold - status, Event og saldi) og siger til, hvis de ikke stemmer – fx hvis arkets opbygning
  er ændret.
- **Nyt ark (1. juni):** Åbn `/budget/#opsaetning` og følg de fire trin i det nye ark. Til sidst
  retter du `adresse.txt`; siden kopierer adressen for dig.
- **Skift kode:** Ret linjen `var KODE = "…"` øverst i scriptet, gem, og vælg Implementer →
  Administrer implementeringer → blyanten → Version: Ny version → Implementer.

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
| Turpris | Sæson, grundspillets udekampe, km og dobbeltweekender (D1: lørdag + søndag på Sjælland). Pokal og slutspil tæller ikke med | `PRISER_SAESON` og priserne (`STANDARD`, `SAESON`) øverst i scriptet i `tjans/docs/turpris/index.html` – og `EKSTRA_UDEKAMPE`, hvis VD's program mangler en udekamp | Når kampprogrammet for den nye sæson er ude. Lukker sig selv |
| Try-out (Vercel) | – | Væk Supabase og følg [guiden](https://docs.google.com/document/d/19cpzGXU_s858MQe_A-r4YyGGtSu8ppPURRt6Rq8Q1bY/edit) | 1. juni. Luk den selv, når billederne er slettet |
| Budgetarket | Budgetsidens udregning (den læser arkets faner og formler) | Nyt budget, nyt ark og primosaldi pr. 1. juni – og budgetsidens script i det nye ark, se *Budgetsiden* | 1. juni. Luk den selv |

Prøv påmindelserne uden at røre GitHub: `python tjans/scripts/vedligehold.py --test --nu 2027-08-15`.
