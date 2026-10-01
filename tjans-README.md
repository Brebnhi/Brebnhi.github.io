# Tjanser – Aalborg Volley

Laver automatisk tjans-kalendere til Holdsport ud fra tjanselisten og de
officielle kampprogrammer fra `resultater.volleyball.dk`. Kampprogrammerne og
holdkoderne finder robotten selv hver nat — se *Kampprogrammer og holdkoder*.

En kamp og dens tjans hænger sammen på **kampnummeret**. Flytter turnerings-
systemet en kamp, flytter tjansen med — først her, natten efter i Holdsport.

## Hvad der bliver bygget

| Fil | Indhold |
|---|---|
| `docs/feeds/<HOLD>-<ANTAL>pers.ics` | Ét kalender-feed pr. hold og deltagerantal |
| `docs/tjanser/index.html` | Live-overblik: dækning, huller, flyttede kampe, feed-adresser |
| `docs/status.json` | Rådata bag siden – også sæsonen, læst ud af tjanselisten |
| `docs/paamindelser.json` | Det, der skal gøres til en ny sæson (fra `scripts/vedligehold.py`) |

`docs/index.html` er klubbens startside og `docs/kontingent/` kontingentsiden. Begge er
faste filer, som robotten ikke bygger.

Ét feed pr. **hold og antal**, fordi Holdsport sætter maks. antal deltagere
én gang pr. import. Et hold med både liga- og divisionstjanser får derfor to feeds.

## Reglerne

- **Volleyligaen-hjemmekampe (D1):** 6 personer, mødetid 45 minutter før kampstart.
  Kommentar: 2 boldlangere, 2 sekretærer, 1 til entré, 1 til speaker.
- **Alle øvrige kampe:** 4 personer, mødetid 30 minutter før kampstart.
  Kommentar: 2 boldlangere og 2 sekretærer — ingen entré eller speaker.
- **Stævner** (U17, Kids/Teen, U15, NM i Mix) kommer ikke med, da de ikke findes
  i kampprogrammet. Sæt `INCLUDE_STAEVNER=1`, hvis de alligevel skal med.

## Opsætning (én gang)

1. **Opret repoet.** Nyt, *offentligt* repo på GitHub — Holdsport skal kunne
   hente feed'ene, og GitHub Pages er kun gratis på offentlige repos.
   Læg alle filer herfra ind (træk og slip virker fint i browseren).
2. **Slå Pages til.** Settings → Pages → Source: **GitHub Actions**.
3. **Kør robotten første gang.** Actions → *Opdater tjans-kalendere* → Run workflow.
4. **Hent adresserne.** Åbn https://brebnhi.github.io/tjanser/ — alle
   feed-adresser står i tabellen "Feeds til Holdsport".
5. **Importér i Holdsport,** ét feed ad gangen på det hold der har tjansen:
   Kalender → Mere → Importer kampprogram → *Importer kampprogram fra et WebCal feed*.
   Indsæt adressen, sæt **maks. antal deltagere** til tallet i tabellen, og slå
   **automatisk opdatering én gang i døgnet** til.

Robotten kører derefter hver nat af sig selv.

## Tjanselisten

Tjanselisten laves i Google Sheets, som den altid er blevet lavet: klubbens
kampprogram-eksport fra Volleyball Danmark med to ekstra kolonner, **Antal** og
**Tjans**. Robotten finder selv overskriftsrækken (Kampnr., Dato, Kl., Række … Antal,
Tjans) og springer linjerne over den og kolonnerne ved siden af (fx fordelingen af
fester) over. Rækker uden noget i Tjans tæller ikke, og rækker uden kampnummer er stævner.

**Så robotten læser arket direkte** (gøres én gang):

1. Arket skal være et Google-regneark. Er det et .xlsx i Drev: åbn det → **Filer → Gem
   som Google Sheets**, og brug den nye udgave fremover.
2. **Filer → Del → Udgiv på nettet** → vælg fanen med tjanselisten og
   **Kommaseparerede værdier (.csv)** → **Udgiv**. Kopiér linket.
3. På GitHub: **Settings → Secrets and variables → Actions → fanen Variables → New
   repository variable**. Navn `SHEET_CSV_URL`, værdi = linket.

Derefter er arket facit: ret i det, så har Holdsport ændringen næste morgen. Til en ny
sæson laver du listen i det samme ark (gem evt. en kopi af den gamle først), så linket
ikke skifter. Udgivelsen viser kun den valgte fane, og listen er alligevel offentlig på
tjansesiden.

Uden linket bruger robotten `data/tjanser.csv` i repoet.

## Overvågning

Efter hver kørsel sammenholdes kampprogrammet med tjanselisten. Er der en kommende
hjemmekamp uden hold på tjans — eller en kommende tjans hvis kamp er forsvundet —
oprettes ét GitHub-issue med listen, og GitHub sender en mail. Issuet lukker
sig selv, når hullet er lukket. Er alt dækket, sker der ingenting.

Pokal-, slutspils- og kvalifikationskampe tæller med for tjanseholdene (D1–D3, H1–H3),
så en ny hjemmekamp i pokalen eller slutspillet dukker op, indtil den står i tjanselisten.
Spillede kampe tæller ikke med — dem er der ikke noget at gøre ved.

## Kampprogrammer og holdkoder

`scripts/kampprogrammer.py` slår hver nat klubbens hold op på klubbens side hos Volleyball
Danmark (samme opslag som kørselsudligningen, `forening_id` i
`koerselsudligning/config.json`) og henter kalenderen for hver pulje i Volleyligaen,
1. og 2. division og pokalturneringen. Tjansesiden viser, hvad den fandt.

Holdkoderne gives efter samme regel som i kørselsudligningen: D1/H1 er holdet i den
bedste række, og i samme række holdet med lavest nummer. Passer det ikke, så skriv holdet
under `hold_koder` i `koerselsudligning/config.json`, fx
`"1. Division Kvinder|Aalborg Volleyball.2": "D2"` — det gælder så begge steder.

Kan Volleyball Danmark ikke nås, bruges adresserne i `data/feeds.json` og tabellen
`CLUB_TEAMS` i `scripts/build.py` som reserve. Ingen af dem skal rettes til en ny sæson.

## Ny sæson

Sæsonen står ikke i koden – `build.py` læser den ud af datoerne i tjanselisten, og
overskriften på tjansesiden følger med. Kampprogrammer og holdkoder finder robotten selv
(se ovenfor), og den ser kun på kampe fra tjanselistens sæson, så den nye sæsons
kampprogram forstyrrer ikke, før listen er lavet. Når Volleyball Danmark har lagt den nye
sæsons kampprogram ud, opretter robotten et issue med labelen **ny sæson**:

1. **Tjanselisten** for den nye sæson — se *Tjanselisten* ovenfor.
2. **Holdsport skal ikke røres.** Kalenderne hedder det samme hver sæson (`D1-4pers.ics`
   osv.), så importerne henter bare de nye tjanser. Står der et feed på tjansesiden, som
   ikke er importeret endnu – fx første gang et hold har 6-personers-tjanser – så importér det.

Issuet lukker sig selv, når tjanselisten er fra den nye sæson.

## Kolonner i tjanselisten

`Kampnr., Runde, Dag, Dato, Kl., Række, Pulje, Hjemmehold, Udehold, Spillested, Antal,
Tjans` — som i Volleyball Danmarks eksport. `data/tjanser.csv` bruger de samme kolonner
med robottens navne (`kampnr, runde, dag, dato, tid, raekke, pulje, hjemmehold, udehold,
spillested, antal, tjans`). Datoen må skrives 03-10-26, 03-10-2026 eller 3.10.2026, og
klokkeslættet 9:00 eller 9.00.

`tjans` er holdet der **har** tjansen. `antal` styrer både maks. deltagere og
mødetiden (6 → 45 min før, ellers 30 min før). Rækker uden `kampnr` regnes som
stævner.
