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
  kun i din egen browser.
- **Flytte `/feeds/` eller den gamle sti.** Holdsport henter derfra.

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
| Try-out (Vercel) | – | Væk Supabase og følg [guiden](https://docs.google.com/document/d/19cpzGXU_s858MQe_A-r4YyGGtSu8ppPURRt6Rq8Q1bY/edit) | 1. juni. Luk den selv, når billederne er slettet |
| Budgetarket | – | Nyt budget, nyt ark og primosaldi pr. 1. juni | 1. juni. Luk den selv |

Prøv påmindelserne uden at røre GitHub: `python tjans/scripts/vedligehold.py --test --nu 2027-08-15`.
