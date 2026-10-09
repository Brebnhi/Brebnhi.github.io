# Tjanser – Aalborg Volley

Laver automatisk tjans-kalendere til Holdsport ud fra tjanselisten og de
officielle kampprogrammer fra `resultater.volleyball.dk`. Kampprogrammerne og
holdkoderne finder robotten selv hver nat — se *Kampprogrammer og holdkoder*.

En kamp og dens tjans hænger sammen på **kampnummeret**. Flytter turnerings-
systemet en kamp, flytter tjansen med — først her (ved robottens næste kørsel), og i
Holdsport næste gang den henter kalenderne (én gang i døgnet). Hjemme- og udehold tages
også fra kampprogrammet, så titlen passer, selv om tjanselisten har dem omvendt.

Tjansen beholder sit kalender-id (UID), og dens versionsnummer (SEQUENCE) stiger, hver gang
den ændres, så Holdsport opdaterer den i stedet for at smide flytningen væk som gammel.
Robotten husker versionsnummeret i `docs/tjans_holdsport.json` på siden.

## Robotten retter selv i Holdsport

Ved hver kørsel (tre gange i døgnet, og når noget uploades) sammenholder robotten
tjanselisten og kampprogrammet med Holdsport og **retter selv** det, der står forkert:

- **En tjans på et forkert tidspunkt flyttes** til mødetiden — også når Volleyball Danmark
  har flyttet kampen, så der ikke skal ventes på Holdsports kalenderhentning.
- **En tjans, der mangler, oprettes** — også en ny i tjanselisten og en, der er slettet i
  Holdsport. Den får aktivitetstypen *Tjans* (findes den på holdet), antal pladser efter
  tjanselisten, holdets tilmeldingstype og påmindelser, og kommentaren slutter med
  *Oprettet af tjans-robotten*. Skal en tjans ikke være, så fjern den fra tjanselisten.
- **Robotten sletter aldrig noget.** En ekstra kopi meldes, og du sletter den.

Holdsports officielle API kan kun læse, så robotten skriver gennem det API, Holdsports egen
app bruger, med samme login (`HOLDSPORT_USER` og `HOLDSPORT_PASSWORD`). Det login kræver dit
**Holdsport-brugernavn** — siger robotten, at login blev afvist, så ret hemmeligheden
`HOLDSPORT_USER` til brugernavnet (det virker også til tjekket). Når robotten skriver, skifter
den dit *aktuelle hold* i Holdsport, så appen kan åbne på et andet hold end sidst.

Sikkerhed: robotten skriver først, når Holdsport har bekræftet holdskiftet; den læser en
aktivitet, før den ændrer den, og sender alle dens indstillinger med tilbage; gentagne
aktiviteter og betalingsaktiviteter røres ikke; højst 12 flytninger og 8 nye pr. kørsel; en
tjans, den har oprettet, og som bliver slettet, oprettes ikke igen før efter en uge (du får
besked); og en aktivitet, der bliver flyttet tilbage igen og igen, giver den op på efter 3
gange på 3 døgn og slår alarm. Bagefter læser den Holdsport igen og viser resultatet.
Slå det fra med `HOLDSPORT_RETTER = False` i `scripts/indstillinger.py` — så læser robotten
kun og slår alarm.

## Sådan bruger Holdsport kalenderne

Holdsport henter kalenderne én gang i døgnet og retter aktiviteterne efter dem. Det har vi
set (okt. 2026):

- **Hver aktivitet, Holdsport har lavet fra en kalender, hører til en tjans** (kalender-id).
  Når tjansens versionsnummer stiger, skriver Holdsport tjansens tidspunkt, navn og kommentar
  ind i aktiviteten — også oven i det, du selv har rettet.
- **Ændringer med et lavere versionsnummer springer Holdsport over.** Indtil 7/10 2026 kunne
  nummeret falde, når en kamp blev flyttet, og så blev tjansen stående (fx D1 – DHV Odense på
  17/10 og H3's pokaltjans på 1/11). Nu stiger det altid.
- **To tjanser på samme tidspunkt i et holds kalender bliver til én aktivitet**, og Holdsport
  kobler begge tjansers kalender-id til den. Bagefter skriver Holdsport begge tjanser ind i
  den samme aktivitet ved hver hentning, så den hopper frem og tilbage mellem dem. Sådan
  forsvandt H3's pokaltjans 11/10 2026 igen og igen. Robotten melder det, hvis et hold får to
  tjanser på samme tid.
- **Holdsport opretter ikke selv tjanser, der kom til efter importen** — det gør robotten nu.
  En aktivitet, du selv har oprettet, rører Holdsport aldrig.

**Når Holdsport har koblet to tjanser til én aktivitet**, ser robotten det selv: aktiviteten
står præcis på den anden tjans' tidspunkt, eller den var én tjans ved sidste kørsel og er en
anden nu. Aktiviteten (og dens tilmeldinger) bliver hos den tjans, den var — robotten flytter
den tilbage og giver den anden tjans sin egen aktivitet. Den anden tjans' kalender-id viser
derefter den første tjans i kalenderen, så Holdsport skriver det samme ind i aktiviteten fra
begge id'er, og den bliver, hvor den skal være. Har du selv givet tjansen en anden aktivitet
med `Kampnr. <nummer>` i kommentaren, respekterer robotten det. Tjansesiden viser koblingerne
under *Kontrol mod Holdsport*.

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
3. **Holdsport-login.** Settings → Secrets and variables → Actions → *New repository
   secret*: `HOLDSPORT_USER` (dit Holdsport-brugernavn) og `HOLDSPORT_PASSWORD`.
4. **Kør robotten første gang.** Actions → *Opdater tjans-kalendere* → Run workflow.
   Robotten opretter selv tjanserne i Holdsport (op til 8 pr. kørsel, de første først).

Robotten kører derefter tre gange i døgnet af sig selv. (Indtil oktober 2026 kom tjanserne
i Holdsport via kalender-import — *Importer kampprogram fra et WebCal feed* med adresserne i
tabellen "Feeds til Holdsport". De importer kører stadig, men nye skal ikke laves: så kan
der komme dobbelte tjanser.)

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

Derefter er arket facit: ret i det, så er tjansesiden og kalenderne opdateret ca. et
kvarter efter, og Holdsport har ændringen, næste gang den henter kalenderne (én gang i
døgnet). Det er workflowet *Tjek tjanselisten* (`.github/workflows/tjek-arket.yml`), der
kigger efter ændringer i arket hvert 10. minut fra morgen til midnat og så starter robotten.

Til en ny sæson laver du listen i det samme ark (gem evt. en kopi af den gamle først), så
linket ikke skifter. Udgivelsen viser kun den valgte fane, og listen er alligevel offentlig på
tjansesiden.

Uden linket bruger robotten `data/tjanser.csv` i repoet.

## Overvågning

Efter hver kørsel sammenholdes kampprogrammet med tjanselisten. Er der en kommende
hjemmekamp uden hold på tjans — eller en kommende tjans hvis kamp er forsvundet —
oprettes ét GitHub-issue med listen, og GitHub sender en mail. Issuet lukker
sig selv, når hullet er lukket. Er alt dækket, sker der ingenting.

Er `HOLDSPORT_USER` og `HOLDSPORT_PASSWORD` sat som hemmeligheder, tjekker robotten også, at
tjanserne ligger i Holdsport på **samme tidspunkt** som i kalenderen, og retter selv det, der
står forkert (se *Robotten retter selv i Holdsport*). Det, den ikke kan rette, kommer med i
issuet med det samme — og på telefonen. Robotten husker det hele i
`docs/tjans_holdsport.json` på siden.

Er rettelserne slået fra (`HOLDSPORT_RETTER = False`), venter robotten på Holdsports
kalenderhentning: en ny tjans står som *venter* i halvandet døgn, og en flyttet kamp får
halvandet døgn til at komme med, før den meldes — bortset fra tjanser inden for 3 døgn.

## Alarm på telefonen

Robotten sender en besked til appen **ntfy** (gratis, ingen konto), når noget nyt kræver
handling, når den selv har rettet noget i Holdsport, når alt er i orden igen — og ved hver
kørsel, så længe en tjans inden for 3 døgn står forkert eller mangler. Sådan (én gang):

1. Installér **ntfy** fra App Store eller Google Play.
2. Tryk **+** og abonnér på emnet `aav-tjans-x7t6nj282s` (står som `ALARM_NTFY` i
   `scripts/indstillinger.py`).

Issuet på GitHub tildeles dig og nævner dig (@), så GitHub også sender en mail.

Den husker også, hvilken aktivitet i Holdsport hver tjans ligger i. Laver Holdsport en
eksisterende tjans om til en ny, når den henter kalenderen (det skete med H3 1/11 → 11/10 i
oktober 2026), følger tilmeldingerne med til den forkerte dag. Det står så øverst under
*Kontrol mod Holdsport* og i issuet: tjek, hvem der er tilmeldt. Advarslen forsvinder ved
næste kørsel, når begge tjanser ligger i Holdsport på det rigtige tidspunkt — og ellers
efter tre døgn.

Pokal-, slutspils- og kvalifikationskampe tæller med for tjanseholdene (D1–D3, H1–H3),
så en ny hjemmekamp i pokalen eller slutspillet dukker op, indtil den står i tjanselisten.
Spillede kampe tæller ikke med — dem er der ikke noget at gøre ved.

## Tjans og egen kamp samme dag

Reglen er mindst én kamp imellem holdets egen kamp og tjansen — eller omvendt. Robotten
tjekker hver nat alle kommende tjanser mod holdets egne kampe (hjemme og ude) med Volleyball
Danmarks tider, så tjekket følger med, når kampe flyttes. Tjansesiden viser dem under
*Tjans og egen kamp samme dag*:

- **✓** mindst én kamp imellem (i samme hal; hal 1 og 2 er samme sted)
- **⚠** ingen kamp imellem, eller holdet spiller ude samme dag — står kun på siden
- **⛔** tjansen ligger oven i holdets egen kamp (en kamp regnes til 2 timer, tjansen fra
  mødetid) — kommer også med i issuet, så du får en mail

Er en advarsel i orden, så tryk **Ignorér** — se *Ignorér-knappen* nedenfor.

Tjanselisten er kun startfordelingen: tider og flytninger kommer altid fra Volleyball
Danmark. Arket rettes kun, når en tjans skal flyttes til et andet hold.

## Ignorér-knappen

Ud for hver ⚠ og ⛔ på tjansesiden står **Ignorér**. Ét tryk, og rækken streges over —
robotten melder ikke den tjans igen, og den tæller ikke med i issuet. *Fortryd* står samme
sted. I issuet åbner *Ignorér* tjansesiden og trykker for dig.

Ignorér gælder tjansen, som den ligger nu: flytter Volleyball Danmark tjansens kamp eller
holdets egen kamp, vurderer robotten den igen.

Hvad der er ignoreret, husker **tjansernes mellemmand** — et lille Google Apps Script på
din Google-konto, som siden og robotten spørger. Der gemmes intet på GitHub, så et tryk
kræver ingen commit. Svarer mellemmanden ikke, bruger robotten listen fra sidste kørsel.

Opsætningen (én gang) og koden står i [`MELLEMMAND.md`](MELLEMMAND.md). Til sidst skrives
mellemmandens adresse i `scripts/indstillinger.py`. Står den tom, er der ingen knap.

## Kampprogrammer og holdkoder

`scripts/kampprogrammer.py` slår hver nat klubbens hold op på klubbens side hos Volleyball
Danmark (samme opslag som kørselsudligningen, `forening_id` i
`koerselsudligning/config.json`) og henter kalenderen for hver pulje i Volleyligaen,
1. og 2. division og pokalturneringen. Tjansesiden viser, hvad den fandt.

Holdkoderne gives efter samme regel som i kørselsudligningen: D1/H1 er holdet i den
bedste række, og i samme række holdet med lavest nummer. Kun hold, der hedder "Aalborg
Volleyball" med eller uden nummer, tæller — talentholdene ("Aalborg Volleyball.2 (T)" i
2. division · Talent) er ikke med i tjanserne og står nederst under kampprogrammerne. Passer det ikke, så skriv holdet
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
2. **Holdsport skal ikke røres.** Robotten opretter selv den nye sæsons tjanser i Holdsport
   (de første først, op til 8 pr. kørsel). Importér ikke kalenderne igen — så kan der komme
   dobbelte tjanser.

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
