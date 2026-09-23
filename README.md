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

Robotten i `.github/workflows/main.yml` kører hver nat kl. 04.20 (vintertid) / 05.20
(sommertid), ved hver ændring i repoet og når du trykker Run workflow under Actions.

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

GitHub slår natkørslen fra, når et offentligt repo har været uden ændringer i 60 dage.
Startsiden viser en advarsel, når status er mere end 30 timer gammel. Gå til **Actions →
Opdater tjans-kalendere** og tryk **Enable workflow** (og evt. **Run workflow**).

## Ny sæson

- **Tjanser:** se afsnittet om tjanselisten i `tjans/README.md`, og ret sæsonen i overskriften
  i `tjans/scripts/render.py`.
- **Kørselsudligning:** finder selv den nye sæson. Nye takster hver januar i
  `koerselsudligning/config.json`.
- **Kontingent:** ret konstanterne øverst i scriptet i `tjans/docs/kontingent/index.html`:
  `HOLD` (takst, antal, kompensation og budget pr. hold fra fanen *Kontingent status*),
  `BUDGET_IALT`, `UNGDOMSAARGANG` (én op hvert år), `ERMIX`/`MOENSTRE` og titlen.
