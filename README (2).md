# Kørselsudligning – Aalborg Volley

Regner hver nat ud, hvad klubben kan forvente at få (eller betale) i
rejseudligning fra Volleyball Danmark — for grundspillet i Liga, 1. og 2.
division, for hver runde i pokalturneringen og for slutspillet i Volleyligaen.

**Siden:** https://brebnhi.github.io/koerselsudligning/

## Sådan virker det

1. Finder klubbens hold på foreningssiden på resultater.volleyball.dk
   (`forening_id` i `config.json`). Det sker af sig selv hver sæson — også når
   en ny pokalrunde er trukket, eller slutspillet er lagt ud.
2. Henter alle puljer i de rækker, klubben spiller i, og puljernes kampprogram.
3. Slår spillestedernes adresser op i DAWA og vejafstande i OpenStreetMap (OSRM).
4. Regner de tre slags udligning (plus = kreditnota til klubben, minus = faktura):

   **Grundspil** (Økonomiske retningslinjer § 2) — som VD's eget regneark:
   - pr. udekamp: biler × (2 × km × statens laveste km-takst + broafgift, hvis
     turen krydser Storebælt). Liga og 1. division: 3 biler, 2. division: 2.
   - udligning = holdets samlede udgift − gennemsnittet for rækken og kønnet
     (Øst, Vest, Syd og Nord regnes sammen).

   **Pokal** (pokalreglementets § 20) — hver runde for sig:
   - kvinder og herrer hver for sig; Øst og Vest i samme runde regnes sammen.
   - kun udeholdet har udgift: 3 biler fra dets registrerede hjemmebane.
   - udligning = holdets udgift − rundens gennemsnit pr. hold. Hjemmeholdet
     betaler altså sin andel, udeholdet får sin tur dækket.
   - kampe uden dato (fx w.o.) er ikke i kalenderen og tæller ikke med. Spilles
     en kamp om, tæller kun den sidste. Final4 afregnes efter regning og er ikke med.

   **Slutspil i Volleyligaen** (§ 2, pkt. 4 — "øvrige kampe"):
   - alle slutspils- og placeringskampe for kønnet findes via ligaklubbernes
     foreningssider. Kvalifikation til/fra Ligaen er ikke med.
   - gennemsnitspris pr. kamp = alle udeholds udgifter / antal kampe.
   - udligning = holdets egne udeture − spillede kampe × halvdelen af
     gennemsnitsprisen. Afregnes efter sæsonen.
   - regnes, når klubben har hold i slutspillet (eller grundspillet er ved at
     være slut), så siden i efteråret kun viser grundspil og pokal.

5. Lægger resultatet på siden og holder ét GitHub-issue pr. sæson opdateret.
   GitHub sender en mail, når en ny sæson er regnet, og når beløbet flytter
   sig mere end 500 kr — fx når en pokalrunde er trukket, eller et hold
   trækker sig. Kommentaren siger, hvilken del der har flyttet sig.

Adresser, afstande og tidligere sæsoner gemmes i `cache/` mellem kørslerne,
så robotten kun spørger de eksterne tjenester, når noget er nyt.

## Én gang om året (januar)

Tilføj det nye års tal i `config.json` — rediger filen direkte på GitHub:

- `km_takst`: statens laveste km-takst (over 20.000 km). 2026: 2,28 kr.
- `bropris`: Storebælt pr. bil tur/retur med weekendrabat. 2026: 346 kr.

Glemmer du det, bruges sidste års tal, og siden viser en advarsel.

## Når opgørelsen fra VD kommer

- Skriv sæsonens samlede beløb (grundspil + pokal + slutspil) under `faktisk`.
- Gerne også pr. hold under `kalibrering`, så siden viser, hvor tæt modellen
  ramte:
  - grundspil: sæsonens række-id'er i `raekke_ids` og beløbene som
    `"Række|Hold": beløb`.
  - pokal: `"type": "pokal"`, rundernes pulje-id'er i `runder` (én liste pr.
    runde, fx `[[3961], [3960]]`) og beløbene som `"PuljeId|Hold": beløb`.
- Har VD brugt en anden afstand end OpenStreetMap på en bestemt tur, så skriv
  den under `km_rettelser` som `"fra-adresse > til-adresse": km` (gælder begge
  veje). Eksempel: VD regnede 200 km Aalborg–Årre i pokalen 25/26, hvor
  OpenStreetMap siger 241 km.

## Hvor præcist er det?

- Grundspil: kontrolleret mod VD's kreditnotaer — 1. division ramt inden for
  0,1–0,4 % i både 24/25 og 25/26. Volleyligaen Kvinder 25/26 er undtagelsen:
  VD gav ca. 2.850 kr mindre end modellen, uden at det har kunnet forklares ud
  fra kampprogrammet.
- Pokal: VD's fakturaer for 25/26 passer med metoden — klubbens beløb = egen
  kørsel − rundens gennemsnit pr. hold (fx 1.645,74 − 734,08 = 911,66 kr).
  Kontrollen på siden regner hele runderne igen og viser, om gennemsnittene
  også rammer.
- Slutspil: metoden følger reglementet; at det regnes pr. køn, passer med VD's
  faktura for herrernes slutspil i 2024. Der er ikke et helt slutspil at
  kontrollere mod endnu.
- Afvigelser skyldes typisk, at VD bruger Google Maps og modellen
  OpenStreetMap, eller at en kamp er flyttet til en anden hal. Om VD tæller
  hold fra en w.o.-kamp med i pokalrundens gennemsnit, vides ikke — modellen
  gør det ikke.

## Test

    python koerselsudligning/test/test_beregn.py

kører hele kæden uden netværk på rigtige puljer, adresser og afstande — plus
en pokalrunde (med omkamp), et slutspil og kampe med resultat i titlen.
