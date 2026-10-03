#!/usr/bin/env python3
"""
Bygger tjans-kalendere (.ics) til Holdsport ud fra tjanselisten og de officielle
kampprogram-feeds fra resultater.volleyball.dk.

Ét feed pr. (hold, antal personer), fordi Holdsport sætter maks. deltagere
én gang pr. import. Tjansen får stabilt UID pr. kampnummer, så en flyttet kamp
flytter tjansen i stedet for at oprette en ny.

Kilder:  tjanselisten (Google-arket i SHEET_CSV_URL, ellers data/tjanser.csv) og
         klubbens kampprogrammer, som scripts/kampprogrammer.py selv finder hos
         Volleyball Danmark hver nat (data/feeds.json er reserve)
Output:  docs/feeds/*.ics, docs/status.json, docs/tjanser/index.html
         (docs/index.html er klubbens startside og bygges ikke her)
"""

import csv, hashlib, json, os, re, shutil, sys, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK, UTC = ZoneInfo("Europe/Copenhagen"), timezone.utc

LEAD_MINUTES = {6: 45, 5: 30, 4: 30}
ROLES = {
    6: ("Der skal stilles 6 personer til rådighed: 2 boldlangere, 2 sekretærer, "
        "1 til entré og 1 til speaker."),
    5: "Der skal stilles 5 personer til rådighed.",
    4: ("Der skal stilles 4 personer til rådighed: 2 boldlangere og 2 sekretærer. "
        "Ingen entré eller speaker."),
}
DEFAULT_LEN = {6: timedelta(hours=3), 5: timedelta(hours=4), 4: timedelta(hours=2, minutes=30)}
INCLUDE_STAEVNER = os.environ.get("INCLUDE_STAEVNER", "0") == "1"

# Repoet hed "Tjanser-i-Holdsport", og Holdsport er sat op med kalenderadresser
# under det navn. Nu er repoet brebnhi.github.io (et user site), så den gamle sti
# ligger i vores eget site: kalenderne kopieres derhen hver nat, og de gamle sider
# sender videre. Slet ikke mappen, så længe Holdsport henter derfra.
GAMMEL = "Tjanser-i-Holdsport"
VIDERE = ("<!doctype html><html lang=\"da\"><head><meta charset=\"utf-8\">"
          "<meta name=\"robots\" content=\"noindex\">"
          "<meta http-equiv=\"refresh\" content=\"0; url={til}\">"
          "<title>Flyttet · Aalborg Volley</title>"
          "<script>location.replace(\"{til}\" + location.hash)</script></head>"
          "<body><p>Siden er flyttet. <a href=\"{til}\">Gå videre</a>.</p></body></html>")

# Holdkoderne (D1, H2 …) finder scripts/kampprogrammer.py selv hver sæson. Tabellen her
# er kun reserve, hvis Volleyball Danmark ikke kan nås — så gælder den som i 2026/27.
# (række i regnearket, holdnavn i turneringssystemet) -> klubbens interne holdnavn
CLUB_TEAMS = {
    ("Volleyligaen Kvinder", "Aalborg Volleyball"):   "D1",
    ("1. Division Kvinder",  "Aalborg Volleyball.2"): "D2",
    ("2. Division Kvinder",  "Aalborg Volleyball.3"): "D3",
    ("1. Division Herrer",   "Aalborg Volleyball"):   "H1",
    ("2. Division Herrer",   "Aalborg Volleyball.2"): "H2",
    ("2. Division Herrer",   "Aalborg Volleyball.3"): "H3",
}

KODER = {}       # (køn, holdnøgle) -> kode, fyldes af load_feeds() når opslaget lykkes


def holdnoegle(navn):
    """'Aalborg Volleyball.2' og 'Aalborg Volleyball 2' -> 'aalborgvolleyball2'."""
    return re.sub(r"[^0-9a-zæøå]", "", (navn or "").lower())


def koen(raekke):
    r = (raekke or "").lower()
    return "H" if "herre" in r else "D" if ("kvinde" in r or "dame" in r) else ""


def holdkode(raekke, holdnavn):
    """Klubbens kode for holdet (D1, H2 …) — tom, hvis det ikke er et af tjanseholdene."""
    if KODER:
        return KODER.get((koen(raekke), holdnoegle(holdnavn)), "")
    for (r, h), kode in CLUB_TEAMS.items():
        if (raekke or "").startswith(r) and holdnavn == h:
            return kode
    return ""


def saeson_for(dt):
    """Startåret for den sæson et tidspunkt hører til (sæsonen regnes fra 1. juli)."""
    d = dt.astimezone(DK)
    return d.year if d.month >= 7 else d.year - 1

# ------------------------------------------------------------------ hjælpere

def norm(s):
    s = (s or "").lower()
    for a, b in (("æ", "ae"), ("ø", "oe"), ("å", "aa")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", s)).strip()


def unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n")
             .replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\"))


def parse_dt(value, params):
    value = value.strip()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if "T" in value:
        naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        try:
            tz = ZoneInfo(params["TZID"]) if params.get("TZID") else DK
        except Exception:
            tz = DK
        return naive.replace(tzinfo=tz)
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=DK)


def parse_ics(text):
    """Returnerer VEVENT'er. VALARM-blokke springes over, så deres
    DESCRIPTION ('Reminder') ikke overskriver kampens egen."""
    events, cur, depth = [], None, 0
    for line in unfold(text):
        u = line.upper()
        if u.startswith("BEGIN:VEVENT"):
            cur, depth = {}, 0
            continue
        if u.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        if u.startswith("BEGIN:"):
            depth += 1
            continue
        if u.startswith("END:"):
            depth -= 1
            continue
        if depth > 0 or ":" not in line:
            continue
        head, _, value = line.partition(":")
        parts = head.split(";")
        name = parts[0].upper()
        params = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.upper()] = v.strip('"')
        if name in ("DTSTART", "DTEND"):
            try:
                cur[name] = parse_dt(value, params)
            except Exception:
                pass
        else:
            cur[name] = unescape(value)
    return events


def fetch(url):
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; aalborg-volley-tjans/1.0)",
        "Accept": "text/calendar,*/*"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", errors="replace")

# ------------------------------------------------------------------ feed-model

KAMPNR_RE = re.compile(r"Kampnr\.?\s*(\d{4,8})", re.I)
# Spillede kampe har resultatet sidst i titlen: "Ikast KFUM.2 - ASV Aarhus.2 3 - 1"
RESULTAT_RE = re.compile(r"\s+\d{1,2}\s*-\s*\d{1,2}(\s*\(.*\))?\s*$")


def describe(ev):
    """Trækker kampnr, række, hjemme- og udehold ud af en VEVENT."""
    desc = ev.get("DESCRIPTION", "") or ""
    summ = ev.get("SUMMARY", "") or ""
    m = KAMPNR_RE.search(desc) or KAMPNR_RE.search(summ)
    kampnr = m.group(1) if m else ""
    lines = [l.strip() for l in desc.split("\n") if l.strip()]
    raekke_linje = lines[0] if lines else ""
    hjemme, ude = "", ""
    summ = RESULTAT_RE.sub("", summ)
    if " - " in summ:
        hjemme, ude = [p.strip() for p in summ.split(" - ", 1)]
    return {"kampnr": kampnr, "raekke": raekke_linje, "hjemme": hjemme,
            "ude": ude, "klubhold": holdkode(raekke_linje, hjemme),
            "udekode": holdkode(raekke_linje, ude),
            "klubkamp": "aalborg volleyball" in norm(f"{hjemme} {ude}"),
            "hjemmekamp": "aalborg volleyball" in norm(hjemme),
            "start": ev.get("DTSTART"), "slut": ev.get("DTEND"),
            "sted": ev.get("LOCATION", "") or ""}


def load_feeds():
    """Klubbens kampe. Kampprogrammerne findes automatisk hos Volleyball Danmark
    (scripts/kampprogrammer.py); data/feeds.json læses med som reserve. Samme kamp kan
    stå i flere kalendere — kampnummeret holder dem fra hinanden."""
    global KODER
    kp = {"kilde": "data/feeds.json", "fejl": None, "hold": [], "puljer": []}
    feeds = {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kampprogrammer
        fundet = kampprogrammer.find()
        feeds.update(fundet["feeds"])
        KODER = fundet["koder"]
        kp.update(kilde="Volleyball Danmark", hold=fundet["hold"], puljer=fundet["puljer"])
    except Exception as exc:                       # noqa: BLE001 — så bruges reserven
        kp["fejl"] = str(exc)
        print(f"ADVARSEL: kampprogrammerne kunne ikke findes automatisk ({exc}) "
              "– bruger data/feeds.json og CLUB_TEAMS", file=sys.stderr)
    def noegle(url):                             # webcal:// og https:// er samme kalender
        m = re.search(r"key=([\w-]+)", url or "")
        return m.group(1) if m else url
    fundne = {noegle(u) for u in feeds.values()}
    reserve = json.load(open(os.path.join(ROOT, "data", "feeds.json"), encoding="utf-8"))
    reserve = {f"feeds.json: {n}": u for n, u in reserve.items()
               if not n.startswith("_") and noegle(u) not in fundne}

    kampe, fejl, raa = {}, {}, 0
    for navn, url in list(feeds.items()) + list(reserve.items()):
        try:
            evs = parse_ics(fetch(url))
        except Exception as exc:
            # En gammel adresse i feeds.json, der er holdt op med at virke, er ikke en
            # fejl, når robotten selv har fundet kampprogrammerne.
            if navn in feeds or not KODER:
                fejl[navn] = str(exc)
            continue
        raa += len(evs)
        for ev in evs:
            info = describe(ev)
            if not info["kampnr"] or not info["start"] or not info["klubkamp"]:
                continue
            kampe.setdefault(info["kampnr"], info)   # samme kamp kan stå i flere feeds

    # Sikkerhedsnet: genkendes ingen af klubbens hjemmekampe på holdkoderne, er holdnavnene
    # skrevet anderledes end ventet — så hellere den faste tabel end tomme koder.
    if KODER and kampe and not any(k["klubhold"] for k in kampe.values() if k["hjemmekamp"]):
        print("ADVARSEL: holdkoderne passede ikke på kampprogrammet – bruger CLUB_TEAMS",
              file=sys.stderr)
        kp["fejl"] = "holdkoderne passede ikke på kampprogrammet – bruger CLUB_TEAMS"
        KODER = {}
        for k in kampe.values():
            k["klubhold"] = holdkode(k["raekke"], k["hjemme"])
            k["udekode"] = holdkode(k["raekke"], k["ude"])
    return kampe, fejl, raa, kp

# ------------------------------------------------------------------ tjanseliste

def tjans_kilde():
    """Tjanselisten hentes fra Google Sheet hvis SHEET_CSV_URL er sat,
    ellers fra data/tjanser.csv i repoet."""
    url = os.environ.get("SHEET_CSV_URL", "").strip()
    if url:
        try:
            return fetch(url).lstrip("\ufeff").splitlines(), "Google Sheet"
        except Exception as exc:
            print(f"ADVARSEL: kunne ikke hente Google Sheet ({exc}) "
                  f"– bruger data/tjanser.csv", file=sys.stderr)
    path = os.path.join(ROOT, "data", "tjanser.csv")
    # utf-8-sig: en CSV gemt fra Excel starter med et BOM-tegn, som ellers ødelægger "kampnr"
    return open(path, encoding="utf-8-sig").read().splitlines(), "data/tjanser.csv"


# Overskrifterne i tjanselisten. Både robottens egne navne og dem fra Volleyball Danmarks
# kampprogram-eksport (Kampnr., Kl., Række …) virker, og linjer over overskriftsrækken
# ("Kampprogram", "Periode: …") og ekstra kolonner (fx fordelingen af fester) springes over.
KOLONNER = {"kampnr": "kampnr", "runde": "runde", "dag": "dag", "dato": "dato",
            "kl": "tid", "tid": "tid", "klokken": "tid", "raekke": "raekke", "pulje": "pulje",
            "hjemmehold": "hjemmehold", "udehold": "udehold", "spillested": "spillested",
            "antal": "antal", "tjans": "tjans"}
DATOFORMATER = ("%d-%m-%y", "%d-%m-%Y", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y",
                "%Y-%m-%d")


def laes_liste(linjer):
    raekker = list(csv.reader(linjer))
    for i, r in enumerate(raekker):
        navne = [norm(c).replace(".", "").strip() for c in r]
        if "kampnr" in navne and "tjans" in navne:
            break
    else:
        raise RuntimeError("tjanselisten har ingen overskriftsrække med Kampnr og Tjans")
    kol = {}
    for j, n in enumerate(navne):
        if n in KOLONNER and KOLONNER[n] not in kol:
            kol[KOLONNER[n]] = j
    for r in raekker[i + 1:]:
        yield {k: (r[j].strip() if j < len(r) else "") for k, j in kol.items()}


def tidspunkt(dato, tid):
    """'03-10-26' / '03-10-2026' / '3.10.2026' og '9:00' / '09.00' -> datetime i dansk tid."""
    d = (dato or "").strip().split(" ")[0]
    for f in DATOFORMATER:
        try:
            dag = datetime.strptime(d, f)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"datoen '{dato}' kan ikke læses")
    t = re.findall(r"\d+", tid or "") + ["0", "0"]
    return dag.replace(hour=int(t[0]), minute=int(t[1]), tzinfo=DK)


def load_tjanser():
    """Tjanselisten. Kan Google-arket ikke bruges (forkert fane udgivet, ingen
    overskriftsrække, ingen tjanser), bruges data/tjanser.csv — hellere sidste kendte
    liste end tomme kalendere i Holdsport."""
    linjer, kilde = tjans_kilde()
    try:
        rows = laes_tjanser(linjer)
        if not rows and kilde == "Google Sheet":
            raise RuntimeError("ingen rækker med noget i kolonnen Tjans")
    except RuntimeError as exc:
        if kilde != "Google Sheet":
            raise
        print(f"ADVARSEL: Google-arket kunne ikke bruges ({exc}) – bruger data/tjanser.csv",
              file=sys.stderr)
        linjer = open(os.path.join(ROOT, "data", "tjanser.csv"),
                      encoding="utf-8-sig").read().splitlines()
        kilde = f"data/tjanser.csv – Google-arket kunne ikke læses: {exc}"
        rows = laes_tjanser(linjer)
    load_tjanser.kilde = kilde
    return rows


def laes_tjanser(linjer):
    rows = []
    for r in laes_liste(linjer):
        for k in KOLONNER.values():
            r.setdefault(k, "")
        if not r.get("tjans"):
            continue
        try:
            r["ark_start"] = tidspunkt(r["dato"], r["tid"])
        except ValueError as exc:
            print(f"ADVARSEL: springer en række over i tjanselisten ({exc})", file=sys.stderr)
            continue
        # samme skrivemåde som altid, så sortering og kalender-id'er ikke flytter sig
        r["dato"] = r["ark_start"].strftime("%d-%m-%y")
        r["tid"] = f"{r['ark_start'].hour}:{r['ark_start'].minute:02d}"
        r["kampnr"] = re.sub(r"\.0$", "", r["kampnr"])
        r["antal"] = int(float(r["antal"])) if r["antal"] else 4
        r["klubhold"] = holdkode(r["raekke"], r["hjemmehold"])
        rows.append(r)
    return rows

def saeson_af(rows):
    """Sæsonen tjanselisten hører til: (2026, "2026/27"). En sæson regnes fra 1. juli,
    som i kørselsudligningen, og flertallet af datoerne afgør den, så en enkelt
    tastefejl ikke flytter sæsonen. Tom liste: (None, "")."""
    starter = Counter(r["ark_start"].year if r["ark_start"].month >= 7
                      else r["ark_start"].year - 1 for r in rows)
    if not starter:
        return None, ""
    start = starter.most_common(1)[0][0]
    return start, f"{start}/{str(start + 1)[2:]}"

# ------------------------------------------------------------------ ics-output

def esc(v):
    return (str(v).replace("\\", "\\\\").replace(";", "\;")
                  .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    raw, parts, limit = line.encode("utf-8"), [], 74
    while len(raw) > limit:
        cut = limit
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(raw[:cut].decode("utf-8"))
        raw, limit = raw[cut:], 73
    parts.append(raw.decode("utf-8"))
    return "\r\n ".join(parts)


def ics_dt(dt):
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(titel, entries, stamp):
    L = ["BEGIN:VCALENDAR", "VERSION:2.0",
         "PRODID:-//Aalborg Volley//Tjanser//DA", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", fold(f"X-WR-CALNAME:{titel}"),
         "X-WR-TIMEZONE:Europe/Copenhagen",
         "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for e in entries:
        L += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
              f"DTSTART:{ics_dt(e['start'])}", f"DTEND:{ics_dt(e['end'])}",
              fold(f"SUMMARY:{esc(e['summary'])}"),
              fold(f"DESCRIPTION:{esc(e['description'])}"),
              fold(f"LOCATION:{esc(e['location'])}"),
              "CATEGORIES:Tjans",
              f"SEQUENCE:{e['seq']}", "STATUS:CONFIRMED", "TRANSP:OPAQUE",
              "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"

# ------------------------------------------------------------------ hovedprogram

def main():
    kampe, feed_fejl, raa, kp = load_feeds()        # først: giver også holdkoderne
    rows = load_tjanser()
    saeson_start, saeson = saeson_af(rows)
    if saeson_start:
        # Kun kampe fra tjanselistens sæson: så forstyrrer den nye sæsons kampprogram
        # ikke, før tjanselisten er lavet — og en gammel feeds.json heller ikke bagefter.
        kampe = {nr: k for nr, k in kampe.items() if saeson_for(k["start"]) == saeson_start}
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    buckets, rapport, forventede = {}, [], []

    for row in rows:
        staevne = not row["kampnr"]
        kamp = kampe.get(row["kampnr"]) if row["kampnr"] else None

        if staevne and not INCLUDE_STAEVNER:
            rapport.append({**snapshot(row), "status": "stævne",
                            "kilde": "regneark", "start": None, "flyttet": False})
            continue

        if kamp:
            # Volleyball Danmark er facit – også for, hvem der er hjemme og ude. Det betyder
            # noget, når to af klubbens egne hold mødes (fx H2 mod H1 i pokalen), og
            # tjanselisten har dem omvendt.
            match_start, match_slut = kamp["start"], kamp["slut"]
            sted = kamp["sted"] or row["spillested"]
            hjemme = kamp["hjemme"] or row["hjemmehold"]
            ude = kamp["ude"] or row["udehold"]
            klub = kamp["klubhold"] or row["klubhold"] or row["raekke"]
            kilde = "feed"
        else:
            match_start, match_slut = row["ark_start"], None
            sted, hjemme, ude = row["spillested"], row["hjemmehold"], row["udehold"]
            klub = row["klubhold"] or row["raekke"]
            kilde = "mangler i feed" if row["kampnr"] else "regneark"

        antal = row["antal"]
        lead = LEAD_MINUTES.get(antal, 30)
        start = match_start - timedelta(minutes=lead)
        end = (match_slut if match_slut and match_slut > match_start
               else match_start + DEFAULT_LEN.get(antal, DEFAULT_LEN[4]))
        flyttet = bool(kamp) and match_start != row["ark_start"]

        # antallet står også i titlen, så det er synligt selv hvis en
        # kalender-import ikke tager kommentarfeltet med
        summary = (f"Tjans ({antal} pers.): {klub} mod {ude}" if ude
                   else f"Tjans ({antal} pers.): {row['raekke']}")
        desc = (f"{ROLES.get(antal, ROLES[4])}\n\n"
                f"Kampstart kl. {match_start.astimezone(DK).strftime('%H:%M')} "
                f"– mød {lead} minutter før.\n"
                f"{row['raekke']}: {hjemme or klub} - {ude}\n"
                f"Sted: {sted}")
        if row["kampnr"]:
            desc += f"\nKampnr. {row['kampnr']}"
        if flyttet:
            desc += (f"\n\nOBS: kampen er flyttet siden tjanselisten blev lavet "
                     f"(stod til {row['ark_start'].strftime('%d-%m-%Y %H:%M')}).")

        seed = row["kampnr"] or hashlib.md5(
            f"{row['dato']}{row['tid']}{row['raekke']}".encode()).hexdigest()[:8]
        buckets.setdefault((row["tjans"], antal), []).append({
            "uid": f"tjans-{seed}-{row['tjans']}@aalborgvolley.dk",
            "start": start, "end": end, "summary": summary,
            "description": desc, "location": sted,
            "seq": int(match_start.timestamp()) % 100000,
        })
        forventede.append({"tjans": row["tjans"], "kampnr": row["kampnr"],
                           "navn": summary, "start": start.astimezone(DK).isoformat(),
                           "antal": antal,
                           "kamp": f"{hjemme or klub} - {ude}"})
        rapport.append({**snapshot(row), "status": "ok", "kilde": kilde,
                        "start": start.astimezone(DK).isoformat(),
                        "kampstart": match_start.astimezone(DK).isoformat(),
                        "flyttet": flyttet, "sted": sted, "modstander": ude,
                        "hjemmehold": hjemme})

    feeds_dir = os.path.join(ROOT, "docs", "feeds")
    os.makedirs(feeds_dir, exist_ok=True)
    for f in os.listdir(feeds_dir):
        if f.endswith(".ics"):
            os.remove(os.path.join(feeds_dir, f))

    feeds = []
    for (hold, antal), entries in sorted(buckets.items()):
        entries.sort(key=lambda e: e["start"])
        fil = f"{hold}-{antal}pers.ics"
        titel = f"Tjanser {hold} ({antal} personer)"
        open(os.path.join(feeds_dir, fil), "w", encoding="utf-8").write(
            build_ics(titel, entries, stamp))
        feeds.append({"hold": hold, "antal": antal, "fil": fil, "titel": titel,
                      "kampe": len(entries),
                      "foerste": entries[0]["start"].astimezone(DK).strftime("%d-%m-%Y"),
                      "sidste": entries[-1]["start"].astimezone(DK).strftime("%d-%m-%Y")})

    gammel_adresse(feeds_dir)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import holdsport
    hs = holdsport_historik(holdsport.koer(forventede, ROOT), forventede)

    huller, forsvundne = find_huller(rows, kampe)
    mm = mellemmand()
    ignoreres, ign_fejl = ignorerede(mm)
    egne = egen_kamp(rows, kampe, ignoreres)
    if mm and (not ign_fejl or "sidste kørsel" in ign_fejl):   # reserve til næste kørsel
        json.dump({"ignoreret": sorted(ignoreres)},
                  open(os.path.join(ROOT, "docs", "ignoreret.json"), "w", encoding="utf-8"))
    elif ign_fejl:
        print(f"ADVARSEL: {ign_fejl}", file=sys.stderr)
    status = {
        "saeson": saeson,                  # fx "2026/27" – ud fra datoerne i tjanselisten
        "saeson_start": saeson_start,
        "holdsport": hs,
        "tjanskilde": getattr(load_tjanser, "kilde", "data/tjanser.csv"),
        "opdateret": datetime.now(UTC).astimezone(DK).strftime("%d-%m-%Y %H:%M"),
        "feed_fejl": feed_fejl,
        "kampprogrammer": kp,
        "feed_kampe": len(kampe),
        "feed_raa": raa,
        "feeds": feeds,
        "tjanser": rapport,
        "huller": huller,
        "forsvundne": forsvundne,
        "flyttede": [r for r in rapport if r.get("flyttet")],
        "egen_kamp": egne,                       # tjanser på dage hvor holdet selv spiller
        "mellemmand": mm,                        # Ignorér-knappen (tom = ingen knap)
        "ignoreret_fejl": ign_fejl,
        "konflikter": [e for e in egne if e["status"] == "konflikt" and not e["ignoreret"]],
    }
    json.dump(status, open(os.path.join(ROOT, "docs", "status.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)

    from render import render
    side_dir = os.path.join(ROOT, "docs", "tjanser")   # startsiden ligger i docs/index.html
    os.makedirs(side_dir, exist_ok=True)
    open(os.path.join(side_dir, "index.html"), "w", encoding="utf-8").write(
        render(status, os.environ.get("BASE_URL", "")))

    print(f"Tjanseliste for sæson {saeson or 'ukendt'} ({status['tjanskilde']})")
    print(f"{len(feeds)} feeds, {sum(f['kampe'] for f in feeds)} tjanser")
    print(f"{len(kampe)} kampe fra feeds ({raa} rå events)")
    print(f"huller: {len(huller)} | forsvundne: {len(forsvundne)} | flyttede: {len(status['flyttede'])}"
          f" | tjans oven i egen kamp: {len(status['konflikter'])}")
    if hs["aktiveret"]:
        if hs["fejl"]:
            print(f"Holdsport-tjek: {hs['fejl']}", file=sys.stderr)
        else:
            print(f"Holdsport-tjek: {hs['fundet']}/{hs['kontrolleret']} tjanser fundet"
                  f" | mangler: {len(hs['mangler'])}"
                  f" | nye, som Holdsport ikke har hentet endnu: {len(hs.get('venter') or [])}")
        print("Dine hold i Holdsport: " + ", ".join(
            f"{h['navn']} (id {h['id']})" for h in hs["alle_hold"]) or "ingen")
    else:
        print("Holdsport-tjek: slået fra (ingen HOLDSPORT_USER/HOLDSPORT_PASSWORD)")
    for n, e in feed_fejl.items():
        print(f"  FEED-FEJL {n}: {e}", file=sys.stderr)
    return status


def gammel_adresse(feeds_dir):
    """Kopierer kalenderne til docs/Tjanser-i-Holdsport/feeds/ og lægger
    videresendende sider på de gamle adresser. Se GAMMEL øverst."""
    rod = os.path.join(ROOT, "docs", GAMMEL)
    ud = os.path.join(rod, "feeds")
    os.makedirs(ud, exist_ok=True)
    for f in os.listdir(ud):
        if f.endswith(".ics"):
            os.remove(os.path.join(ud, f))
    for f in os.listdir(feeds_dir):
        if f.endswith(".ics"):
            shutil.copyfile(os.path.join(feeds_dir, f), os.path.join(ud, f))
    for sti, til in (("", "../"), ("tjanser", "../../tjanser/"),
                     ("koerselsudligning", "../../koerselsudligning/"),
                     ("kontingent", "../../kontingent/")):
        d = os.path.join(rod, sti)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(VIDERE.format(til=til))


KAMPTID = timedelta(hours=2)            # så længe regnes en kamp at vare

# Holdsport henter kalenderne én gang i døgnet, så en tjans, der lige er kommet i kalenderen,
# mangler i Holdsport et stykke tid uden at være slettet. Robotten husker derfor for hver
# tjans, hvornår den kom i kalenderen, hvornår den sidst blev fundet i Holdsport, og i hvilken
# Holdsport-aktivitet. Listen gemmes i docs/tjans_holdsport.json og hentes fra siden ved
# næste kørsel.
HISTORIK_FIL = "tjans_holdsport.json"
VENTETID = timedelta(hours=36)          # så længe får en ny tjans til at komme i Holdsport
GENBRUG_VISES = timedelta(days=3)       # så længe står en advarsel om genbrug på siden


def _alder(iso, nu):
    """Hvor længe siden et gemt tidspunkt er – uendeligt længe, hvis det ikke kan læses."""
    try:
        return nu - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return timedelta.max


def tjans_noegle(t):
    """'150792-H3' – eller dato-hold for stævner. Virker på forventede og manglende tjanser
    og på tjanserne i status.json."""
    return f"{t['kampnr'] or t['start'][:10]}-{t['tjans']}"


def _sidste_historik(base, gammel):
    """Listen fra sidste kørsel. Findes den ikke endnu, bygges den ud fra sidste kørsels
    status.json: tjanser, der stod dér, er ikke nye, og dem, Holdsport-tjekket fandt
    dengang, har været i Holdsport. None, hvis intet kan læses – så regnes alt for gammelt."""
    try:
        h = json.loads(fetch(base + HISTORIK_FIL))
        return h if isinstance(h, dict) else None
    except Exception as exc:                       # noqa: BLE001
        if getattr(exc, "code", None) != 404:
            return None
    try:
        st = json.loads(fetch(base + "status.json"))
    except Exception:                              # noqa: BLE001
        return None
    hs = st.get("holdsport") or {}
    tjekket = hs.get("aktiveret") and not hs.get("fejl")
    ikke_fundet = {tjans_noegle(m) for m in (hs.get("mangler") or []) + (hs.get("venter") or [])}
    h = {}
    for t in st.get("tjanser") or []:
        if t.get("status") != "ok" or not t.get("start"):
            continue
        n = tjans_noegle(t)
        h[n] = {"set": gammel, "fundet": gammel if tjekket and n not in ikke_fundet else None}
    return h


def holdsport_historik(hs, forventede, nu=None):
    """Sorterer de tjanser, Holdsport-tjekket ikke fandt:
      venter   – ny i kalenderen, Holdsport har ikke nået at hente den (under VENTETID)
      mangler  – har været i Holdsport og er væk nu, eller er ikke kommet inden for VENTETID
    og finder de aktiviteter, Holdsport har genbrugt til en anden tjans (hs["genbrugt"]) —
    så følger tilmeldingerne med til den forkerte tjans."""
    nu = nu or datetime.now(UTC)
    nu_iso, gammel = nu.isoformat(), (nu - VENTETID).isoformat()
    foer = _sidste_historik(os.environ.get("BASE_URL", ""), gammel)
    tjekket = hs.get("aktiveret") and not hs.get("fejl")
    fundne = {tjans_noegle(f): f for f in hs.get("fundne") or []} if tjekket else {}

    hist, foer_akt = {}, {}
    for n, p in (foer or {}).items():
        if isinstance(p, dict) and p.get("aktivitet") and not n.startswith("_"):
            foer_akt[p["aktivitet"]] = (n, p)
    for f in forventede:
        n = tjans_noegle(f)
        p = (foer or {}).get(n)
        if foer is None:                          # kunne ikke læse noget: regn den for gammel
            post = {"set": gammel}
        elif isinstance(p, dict):
            post = {k: p[k] for k in ("set", "fundet", "aktivitet") if p.get(k)}
            post.setdefault("set", nu_iso)
        else:
            post = {"set": nu_iso}
        post["start"], post["tjans"] = f["start"][:16].replace("T", " "), f["tjans"]
        if n in fundne:
            post["fundet"] = nu_iso
            post["aktivitet"] = fundne[n].get("aktivitet") or post.get("aktivitet")
        hist[n] = post

    # Holdsport har flyttet en aktivitet fra én tjans til en anden (tilmeldingerne følger med)
    genbrugt = [g for g in ((foer or {}).get("_genbrugt") or [])
                if isinstance(g, dict) and _alder(g.get("tid"), nu) < GENBRUG_VISES]
    for n, f in fundne.items():
        gl = foer_akt.get(f.get("aktivitet"))
        if gl and gl[0] != n and not any(g["aktivitet"] == f["aktivitet"] and g["nu"] == n
                                         for g in genbrugt):
            genbrugt.append({"aktivitet": f["aktivitet"], "tid": nu_iso,
                             "foer": gl[0], "foer_start": gl[1].get("start", ""),
                             "nu": n, "nu_start": hist[n]["start"], "tjans": hist[n]["tjans"]})
    hist["_genbrugt"] = genbrugt
    json.dump(hist, open(os.path.join(ROOT, "docs", HISTORIK_FIL), "w", encoding="utf-8"),
              indent=0, sort_keys=True, ensure_ascii=False)
    if not tjekket:
        return hs

    venter, mangler = [], []
    for m in hs.get("mangler") or []:
        post = hist.get(tjans_noegle(m), {})
        if post.get("fundet"):
            mangler.append({**m, "foer_fundet": True})      # var i Holdsport, nu væk
        elif _alder(post.get("set"), nu) < VENTETID:
            venter.append(m)
        else:
            mangler.append(m)
    hs["venter"], hs["mangler"], hs["genbrugt"] = venter, mangler, genbrugt
    for post in hs.get("hold") or []:
        v = sum(1 for m in venter if m["tjans"] == post.get("kode"))
        post["venter"] = v
        post["mangler"] = max(0, (post.get("mangler") or 0) - v)
    return hs


# Ignorér-knappen: tjansernes mellemmand (et Google Apps Script) husker, hvilke advarsler
# du har ignoreret. Adressen står i scripts/indstillinger.py.
def mellemmand():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import indstillinger
        url = (getattr(indstillinger, "MELLEMMAND", "") or "").strip()
    except ImportError:
        return ""
    return url if re.match(r"^https://script\.google\.com/macros/s/[\w-]+/exec$", url) else ""


def ignorerede(url):
    """(nøgler, fejl). Nøglerne på de tjans-advarsler, du har ignoreret, fx "148228-D1-3fa2"
    (kampnummer-hold-aftryk; stævner har datoen i stedet for kampnummer). Svarer
    mellemmanden ikke, bruges listen fra sidste kørsel, så advarslerne ikke dukker op igen."""
    if not url:
        return set(), None
    try:
        return set(json.loads(fetch(url)).get("ignoreret") or []), None
    except Exception as exc:                       # noqa: BLE001
        fejl = f"mellemmanden svarede ikke ({exc})"
        try:
            sidst = json.loads(fetch(os.environ.get("BASE_URL", "") + "ignoreret.json"))
            return set(sidst.get("ignoreret") or []), fejl + " – bruger listen fra sidste kørsel"
        except Exception:                          # noqa: BLE001
            return set(), fejl


def hal(sted):
    """'Aalborg Stadionhal 2' -> 'aalborg stadionhal' (hal 1 og 2 er samme sted)."""
    return re.sub(r"\s*\d+\s*$", "", norm(sted))


def ignorer_noegle(r, s_t, s_o):
    """Nøglen til Ignorér, fx "148228-D1-3fa2": kampnummer (stævner: datoen), hold og et
    aftryk af tjansens og holdets egen kamps tider. Flytter Volleyball Danmark en af
    kampene, får tjansen en ny nøgle — så vurderes den igen."""
    nr = re.sub(r"\D", "", r["kampnr"])[:8] or f"{s_t.astimezone(DK):%Y%m%d}"
    hold = re.sub(r"[^A-Za-z0-9]", "", r["tjans"])[:8] or "x"
    tider = f"{s_t.astimezone(UTC):%Y%m%d%H%M}|{s_o.astimezone(UTC):%Y%m%d%H%M}"
    return f"{nr}-{hold}-{hashlib.md5(tider.encode()).hexdigest()[:4]}"


def egen_kamp(rows, kampe, ignoreres=frozenset()):
    """Kommende tjanser på dage, hvor holdet selv spiller. Tiderne er Volleyball Danmarks,
    så tjekket følger med, når kampe flyttes. Reglen er mindst én kamp imellem holdets
    egen kamp og tjansen — eller omvendt. Status pr. tjans:
      ok        – mindst én kamp imellem
      taet      – ingen kamp imellem, eller holdet spiller ude samme dag
      konflikt  – tjansen ligger oven i holdets egen kamp, så de kan ikke nå begge dele"""
    i_dag = datetime.now(DK).replace(hour=0, minute=0, second=0, microsecond=0)
    hjemme = [k for k in kampe.values() if k["hjemmekamp"]]
    ud = []
    for r in rows:
        kamp = kampe.get(r["kampnr"]) if r["kampnr"] else None
        s_t = kamp["start"] if kamp else r["ark_start"]
        if s_t < i_dag or not r["tjans"]:
            continue
        if r["kampnr"]:                      # fra mødetid til kampen er slut
            fra = s_t - timedelta(minutes=LEAD_MINUTES.get(r["antal"], 30))
            til = s_t + KAMPTID
        else:                                # stævne: hele formiddagen/eftermiddagen
            fra, til = s_t, s_t + DEFAULT_LEN.get(r["antal"], DEFAULT_LEN[5])
        sted_t = hal(kamp["sted"] if kamp else r["spillested"])
        dag = s_t.astimezone(DK).date()
        for o in kampe.values():
            egen = (o["hjemmekamp"] and o["klubhold"] == r["tjans"]) or o["udekode"] == r["tjans"]
            if not egen or o["start"].astimezone(DK).date() != dag or o["kampnr"] == r["kampnr"]:
                continue
            s_o = o["start"]
            konflikt = fra < s_o + KAMPTID and s_o < til        # tiderne overlapper
            egen_kl = s_o.astimezone(DK).strftime("%H:%M")
            imellem = None
            if not o["hjemmekamp"]:
                status = "konflikt" if konflikt else "taet"
                tekst = (f"spiller ude kl. {egen_kl} i {o['sted'] or o['hjemme']}"
                         + (" – samtidig med tjansen" if konflikt else " samme dag – kan det nås?"))
            elif konflikt:
                status, tekst = "konflikt", f"tjansen ligger oven i egen kamp kl. {egen_kl}"
            elif not r["kampnr"]:
                status, tekst = "ok", f"spiller selv kl. {egen_kl} samme dag"
            else:
                lav, hoej = sorted((s_o, s_t))
                imellem = sum(1 for k in hjemme if lav < k["start"] < hoej
                              and hal(k["sted"]) == sted_t)
                if imellem == 0:
                    foer = "efter" if s_o < s_t else "før"
                    status, tekst = "taet", f"ingen kamp imellem – tjans lige {foer} egen kamp"
                else:
                    status = "ok"
                    tekst = f"{imellem} kamp{'e' if imellem > 1 else ''} imellem"
            e = {"dato": s_t.astimezone(DK).strftime("%d-%m-%Y"), "hold": r["tjans"],
                 "tjans_kl": s_t.astimezone(DK).strftime("%H:%M"),
                 "tjans_kamp": (f"{r['hjemmehold']} - {r['udehold']}" if r["kampnr"]
                                else f"{r['raekke']} (stævne)"),
                 "egen_kl": egen_kl, "egen_kamp": f"{o['hjemme']} - {o['ude']}",
                 "hjemme": o["hjemmekamp"], "imellem": imellem,
                 "status": status, "tekst": tekst, "_t": s_t}
            e["noegle"] = ignorer_noegle(r, s_t, s_o)
            e["ignoreret"] = e["noegle"] in ignoreres
            ud.append(e)
    ud.sort(key=lambda e: (e["_t"], e["hold"]))
    for e in ud:
        del e["_t"]
    return ud


def snapshot(row):
    return {k: row[k] for k in ("kampnr", "dato", "tid", "raekke", "hjemmehold",
                                "udehold", "spillested", "antal", "tjans", "klubhold")}


def find_huller(rows, kampe):
    """Kommende hjemmekampe uden hold på tjans, og kommende tjanser hvis kamp er væk.
    Det, der allerede er spillet, kræver ingen handling og tælles ikke med. Når
    holdkoderne er fundet automatisk, tæller kun tjanseholdenes hjemmekampe (ikke fx
    Danmarksserien-holdets pokalkampe)."""
    i_dag = datetime.now(DK).replace(hour=0, minute=0, second=0, microsecond=0)
    daekket = {r["kampnr"] for r in rows if r["kampnr"]}
    huller = []
    for nr, k in kampe.items():
        if (not k["hjemmekamp"] or nr in daekket or (KODER and not k["klubhold"])
                or k["start"] < i_dag):
            continue
        huller.append({"kampnr": nr, "raekke": k["raekke"], "klubhold": k["klubhold"],
                       "kamp": f"{k['hjemme']} - {k['ude']}", "sted": k["sted"],
                       "start": k["start"].astimezone(DK).strftime("%d-%m-%Y %H:%M")})
    huller.sort(key=lambda h: h["start"][6:10] + h["start"][3:5] + h["start"][:2] + h["start"][11:])
    forsvundne = [{"kampnr": r["kampnr"], "dato": r["dato"], "tjans": r["tjans"],
                   "kamp": f"{r['hjemmehold']} - {r['udehold']}"}
                  for r in rows if r["kampnr"] and r["kampnr"] not in kampe
                  and r["ark_start"] >= i_dag]
    return huller, forsvundne


if __name__ == "__main__":
    main()
