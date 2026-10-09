#!/usr/bin/env python3
# sti: tjans/scripts/build.py
"""
Bygger tjans-kalendere (.ics) til Holdsport ud fra tjanselisten og de officielle
kampprogram-feeds fra resultater.volleyball.dk.

Ét feed pr. (hold, antal personer), fordi Holdsport sætter maks. deltagere
én gang pr. import. Tjansen får stabilt UID pr. kampnummer, så en flyttet kamp
flytter tjansen i stedet for at oprette en ny — og et SEQUENCE, der altid stiger,
når tjansen ændres, så kalenderen ikke smider flytningen væk som "gammel".

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
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


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
        kp.update(kilde="Volleyball Danmark", hold=fundet["hold"], puljer=fundet["puljer"],
                  udeladt=fundet.get("udeladt") or [])
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
    return (str(v).replace("\\", "\\\\").replace(";", "\\;")
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


# SEQUENCE er tjansens versionsnummer. Det skal stige, hver gang tjansen ændres — en kalender,
# der følger standarden, smider ellers ændringen væk som "gammel", og så flytter tjansen ikke med
# kampen. Tallet er minutter siden 1/1 2026 på det tidspunkt, tjansen sidst blev ændret; en
# uændret tjans beholder sit tal. (Indtil okt. 2026 var det kampens tidspunkt modulo 100000, og det
# kunne falde, når en kamp blev flyttet: 149194 fra 17/10 til 3/12 gav 40200 → 26200.)
SEKVENS_EPOKE = datetime(2026, 1, 1, tzinfo=UTC)


def aftryk(e):
    """Fingeraftryk af det, kalenderen viser om tjansen. Ændres det, får tjansen nyt SEQUENCE."""
    tekst = "|".join([ics_dt(e["start"]), ics_dt(e["end"]), e["summary"],
                      e["description"], e["location"]])
    return hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:12]


def sekvens(foer_post, nyt_aftryk, nu):
    """SEQUENCE til en tjans ud fra sidste kørsels udgave (fra tjans_holdsport.json).
    Uændret: samme tal som sidst. Ændret, ny eller ukendt: minutter siden SEKVENS_EPOKE,
    som altid er større end alt, robotten har udgivet før."""
    nu_min = int((nu - SEKVENS_EPOKE).total_seconds() // 60)
    gl = foer_post.get("seq") if isinstance(foer_post, dict) else None
    if not isinstance(gl, int):
        return nu_min
    if foer_post.get("aftryk") == nyt_aftryk:
        return gl
    return max(nu_min, gl + 1)


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
    nu = datetime.now(UTC)
    stamp = nu.strftime("%Y%m%dT%H%M%SZ")
    # Sidste kørsels udgave af hver tjans: giver SEQUENCE, og hvornår tidspunktet blev udgivet
    foer = _sidste_historik(os.environ.get("BASE_URL", ""), (nu - VENTETID).isoformat())
    buckets, rapport, forventede, evs = {}, [], [], {}

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
        ev = {"uid": f"tjans-{seed}-{row['tjans']}@aalborgvolley.dk",
              "start": start, "end": end, "summary": summary,
              "description": desc, "location": sted}
        forv = {"tjans": row["tjans"], "kampnr": row["kampnr"],
                "navn": summary, "start": start.astimezone(DK).isoformat(),
                "antal": antal, "kamp": f"{hjemme or klub} - {ude}",
                "aftryk": aftryk(ev), "slut": end.astimezone(DK).isoformat(),
                # mødetiden efter tjanselisten – den, Holdsport fik, før kampen blev flyttet
                "ark": (row["ark_start"] - timedelta(minutes=lead)).astimezone(DK)
                       .strftime("%Y-%m-%d %H:%M")}
        ev["noegle"] = n = tjans_noegle(forv)
        evs[n] = ev
        buckets.setdefault((row["tjans"], antal), []).append(ev)
        forventede.append(forv)
        rapport.append({**snapshot(row), "status": "ok", "kilde": kilde,
                        "start": start.astimezone(DK).isoformat(),
                        "kampstart": match_start.astimezone(DK).isoformat(),
                        "flyttet": flyttet, "sted": sted, "modstander": ude,
                        "hjemmehold": hjemme})

    # Holdsport: læs, ret det, der står forkert, og læs igen. Det sker, før kalenderne skrives:
    # har Holdsport koblet en aktivitet til to tjanser, skal kalenderen vide det.
    hs, bundet, skrevet = holdsport_ret(forventede, evs, foer, nu)
    spejl = kalender_spejl(hs, forventede, bundet, foer)
    for f in forventede:
        n = tjans_noegle(f)
        if spejl.get(n) in evs:
            # Holdsport har koblet tjansens kalender-id til en aktivitet, som er en anden tjans'.
            # Kalenderen viser derfor den tjans her, så Holdsport ikke flytter aktiviteten væk fra
            # den – og robotten passer tjansens egen aktivitet i Holdsport.
            ev = evs[n] = {**evs[spejl[n]], "uid": evs[n]["uid"], "noegle": n, "spejl": spejl[n]}
            buckets[(f["tjans"], f["antal"])] = [ev if e["noegle"] == n else e
                                                  for e in buckets[(f["tjans"], f["antal"])]]
            f["spejl"] = spejl[n]
        f["aftryk"] = aftryk(evs[n])
        f["seq"] = evs[n]["seq"] = sekvens((foer or {}).get(n), f["aftryk"], nu)
    hs["spejl"], hs["bundet"] = spejl, bundet
    hs, hist = holdsport_historik(hs, forventede, foer, nu)
    hist["_bundet"], hist["_skrevet"] = bundet, skrevet

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
                      "kampe": len(entries), "spejl": sum(1 for e in entries if e.get("spejl")),
                      "foerste": entries[0]["start"].astimezone(DK).strftime("%d-%m-%Y"),
                      "sidste": entries[-1]["start"].astimezone(DK).strftime("%d-%m-%Y")})

    gammel_adresse(feeds_dir)

    huller, forsvundne = find_huller(rows, kampe)
    dobbelt = dobbelt_tjans(forventede)
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
        "dobbelt_tjans": dobbelt,                # samme hold, to tjanser på samme tid
        "flyttede": [r for r in rapport if r.get("flyttet")],
        "egen_kamp": egne,                       # tjanser på dage hvor holdet selv spiller
        "mellemmand": mm,                        # Ignorér-knappen (tom = ingen knap)
        "ignoreret_fejl": ign_fejl,
        "konflikter": [e for e in egne if e["status"] == "konflikt" and not e["ignoreret"]],
    }
    status["alarm"], hist["_alarm"] = alarm(status, foer, nu)
    json.dump(hist, open(os.path.join(ROOT, "docs", HISTORIK_FIL), "w", encoding="utf-8"),
              indent=0, sort_keys=True, ensure_ascii=False)
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
          f" | tjans oven i egen kamp: {len(status['konflikter'])}"
          f" | to tjanser på samme tid: {len(dobbelt)}")
    if hs["aktiveret"]:
        if hs["fejl"]:
            print(f"Holdsport-tjek: {hs['fejl']}", file=sys.stderr)
        else:
            print(f"Holdsport-tjek: {hs['fundet']}/{hs['kontrolleret']} tjanser fundet"
                  f" | mangler: {len(hs['mangler'])}"
                  f" | nye, som Holdsport ikke har hentet endnu: {len(hs.get('venter') or [])}"
                  f" | flyttet, venter på Holdsport: {len(hs.get('venter_tid') or [])}"
                  f" | forkert tidspunkt i Holdsport: {len(hs.get('forkert_tid') or [])}")
            for r in hs.get("forkert_tid") or []:
                print(f"  {r['tjans']} {r['kampnr']}: skal stå {r['start']}, står {r['hs_start']}"
                      f" i Holdsport{kopi_tekst(r, ' – ')}")
        r = hs.get("rettet") or {}
        if not r.get("slaaet_til"):
            print("Robotten retter ikke selv i Holdsport (HOLDSPORT_RETTER = False i indstillinger.py)")
        for x in r.get("flyttet") or []:
            print(f"  RETTET: {x['hvilken']} flyttet fra {x['fra']} til {x['til']}"
                  f" (aktivitet {x['aktivitet']})")
        for x in r.get("oprettet") or []:
            print(f"  OPRETTET: {x['hvilken']} (aktivitet {x['aktivitet']})")
        for x in r.get("fejl") or []:
            print(f"  KUNNE IKKE RETTE: {x.get('hvilken') or 'Holdsport'}: {x['fejl']}",
                  file=sys.stderr)
        for x in r.get("givet_op") or []:
            print(f"  GIVET OP: {x['hvilken']}", file=sys.stderr)
        for x in r.get("udskudt") or []:
            print(f"  UDSKUDT til næste kørsel: {x['hvad']} {x['hvilken']}")
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


AKUT = timedelta(hours=72)              # tjanser inden for så kort tid får ingen ventetid


def holdsport_historik(hs, forventede, foer, nu=None):
    """Sorterer de tjanser, der stadig mangler i Holdsport, efter robotten har rettet:
      venter   – ny i kalenderen, Holdsport har ikke nået at hente den (under VENTETID)
      mangler  – har været i Holdsport og er væk nu, eller er ikke kommet inden for VENTETID
    og dem, der ligger på et andet tidspunkt i Holdsport end i kalenderen:
      venter_tid  – Holdsport står på det gamle tidspunkt, og flytningen er under VENTETID
                    gammel, så Holdsport har ikke nået at hente den
      forkert_tid – Holdsport har ikke flyttet tjansen med kampen inden for VENTETID, står
                    på et tidspunkt, robotten aldrig har udgivet, har selv flyttet den, eller
                    har en ekstra kopi
    og finder de aktiviteter, Holdsport har genbrugt til en anden tjans (hs["genbrugt"]) —
    så følger tilmeldingerne med til den forkerte tjans.

    Retter robotten selv i Holdsport (hs["rettet"]["slaaet_til"]), venter den ikke på noget:
    det, der stadig står forkert, kunne robotten ikke rette, og det skal du vide med det samme.
    Heller ingen ventetid for tjanser inden for AKUT: så er der ikke tid til at vente.

    foer: listen fra sidste kørsel (_sidste_historik) – None, hvis den ikke kunne læses.
    Returnerer (hs, hist); hist gemmes af main() i docs/tjans_holdsport.json."""
    nu = nu or datetime.now(UTC)
    nu_iso, gammel = nu.isoformat(), (nu - VENTETID).isoformat()
    tjekket = hs.get("aktiveret") and not hs.get("fejl")
    fundne = {tjans_noegle(f): f for f in hs.get("fundne") or []} if tjekket else {}
    i_dag = nu.astimezone(DK).strftime("%Y-%m-%d %H:%M")
    # tjanser, der starter før "snart", får ingen ventetid – heller ingen, når robotten retter selv
    snart = ("9999" if (hs.get("rettet") or {}).get("slaaet_til")
             else (nu + AKUT).astimezone(DK).strftime("%Y-%m-%d %H:%M"))

    hist, foer_akt = {}, {}
    for n, p in (foer or {}).items():
        if isinstance(p, dict) and p.get("aktivitet") and not n.startswith("_"):
            foer_akt[p["aktivitet"]] = (n, p)
    for f in forventede:
        n = tjans_noegle(f)
        p = (foer or {}).get(n)
        start = f["start"][:16].replace("T", " ")
        if foer is None:                          # kunne ikke læse noget: regn den for gammel
            post = {"set": gammel}
        elif isinstance(p, dict):
            post = {k: p[k] for k in ("set", "fundet", "aktivitet", "flyttet", "forrige")
                    if p.get(k)}
            post.setdefault("set", nu_iso)
            if p.get("start") and p["start"] != start:
                # flyttet nu: husk hvornår og fra hvad – Holdsport skal nå at hente det
                post["flyttet"], post["forrige"] = nu_iso, p["start"]
        else:
            post = {"set": nu_iso}
        post["start"], post["tjans"] = start, f["tjans"]
        post["seq"], post["aftryk"] = f.get("seq"), f.get("aftryk")
        if f.get("spejl"):
            post["spejl"] = f["spejl"]       # kalenderen viser en anden tjans (kalender_spejl)
        if n in fundne:
            post["fundet"] = nu_iso
            post["aktivitet"] = fundne[n].get("aktivitet") or post.get("aktivitet")
            post["hs_start"] = fundne[n].get("hs_start") or ""   # så robotten ser, hvis Holdsport
        hist[n] = post                                           # selv flytter den næste gang

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
    # Advarslen er klaret, når både den gamle og den nye tjans ligger i Holdsport på det rigtige
    # tidspunkt — fx når du selv har rettet aktiviteten og oprettet den anden tjans igen.
    if tjekket:
        paa_plads = {n for n, f in fundne.items() if f.get("hs_start") == hist[n]["start"]}
        genbrugt = [g for g in genbrugt if not (g["foer"] in paa_plads and g["nu"] in paa_plads)]
    hist["_genbrugt"] = genbrugt

    # Står tjansen på et andet tidspunkt i Holdsport end i kalenderen? Står Holdsport på et
    # tidspunkt, robotten har udgivet før (før flytningen, eller tjanselistens oprindelige), har
    # Holdsport bare ikke hentet flytningen endnu: den får VENTETID, regnet fra flytningen (eller
    # fra første gang robotten ser den, hvis den ikke ved, hvornår kampen blev flyttet). Står
    # Holdsport på et tidspunkt, robotten aldrig har udgivet, er der noget galt med det samme.
    # Spillede kampe tæller ikke med.
    ark = {tjans_noegle(f): f.get("ark") for f in forventede}
    venter_tid, forkert_tid = [], []
    for n, f in fundne.items():
        post = hist.get(n) or {}
        hs_start = f.get("hs_start") or ""
        if not hs_start or hs_start == post.get("start") or post.get("start", "") < i_dag:
            continue
        r = {"tjans": f["tjans"], "kampnr": f["kampnr"], "holdsport": f.get("holdsport", ""),
             "navn": f.get("navn", ""), "kamp": f.get("kamp", ""), "start": post["start"],
             "hs_start": hs_start, "aktivitet": f.get("aktivitet")}
        gl = (foer or {}).get(n) or {}
        if gl.get("hs_start") and gl.get("hs_start") == gl.get("start") == post["start"]:
            # Rigtigt ved sidste kørsel, kalenderen er uændret – Holdsport har selv flyttet den
            r["selv_flyttet"] = True
            forkert_tid.append(r)
            continue
        gammelt = hs_start in (post.get("forrige"), ark.get(n))
        if gammelt and not post.get("flyttet"):
            post["flyttet"] = nu_iso                # første gang robotten ser det: uret starter
        if (gammelt and post["start"] > snart
                and _alder(post["flyttet"], nu) < VENTETID):
            venter_tid.append(r)
        else:
            forkert_tid.append(r)
    # En ekstra aktivitet med samme kampnummer — Holdsport har lavet en ny i stedet for at flytte
    # den gamle, eller der ligger en kopi. Den skal slettes, ellers tilmelder folk sig den.
    for d in hs.get("dubletter") or []:
        if d.get("start", "") >= i_dag:
            forkert_tid.append({**d, "dublet": True})
    forkert_tid.sort(key=lambda r: r["start"])
    venter_tid.sort(key=lambda r: r["start"])
    if not tjekket:
        return hs, hist

    venter, mangler = [], []
    for m in hs.get("mangler") or []:
        n = tjans_noegle(m)
        post = hist.get(n, {})
        if post.get("fundet"):
            mangler.append({**m, "foer_fundet": True})      # var i Holdsport, nu væk
        elif m["start"] > snart and _alder(post.get("set"), nu) < VENTETID:
            venter.append(m)
        else:
            mangler.append(m)
    hs["venter"], hs["mangler"], hs["genbrugt"] = venter, mangler, genbrugt
    hs["venter_tid"], hs["forkert_tid"] = venter_tid, forkert_tid

    for post in hs.get("hold") or []:
        v = sum(1 for m in venter if m["tjans"] == post.get("kode"))
        post["venter"] = v
        post["mangler"] = max(0, (post.get("mangler") or 0) - v)
        post["forkert_tid"] = sum(1 for r in forkert_tid if r["tjans"] == post.get("kode"))
    return hs, hist


def holdsport_ret(forventede, evs, foer, nu):
    """Læser Holdsport (holdsport.py), retter det, der står forkert (holdsport_skriv.py), og læser
    igen, så siden og alarmen viser, hvordan det står nu. Returnerer (hs, bundet, skrevet):
      hs      – holdsport.py's resultat efter rettelserne; hs["rettet"] er det, robotten gjorde
      bundet  – aktiviteter, Holdsport har koblet til flere tjanser (bindinger)
      skrevet – det, robotten har skrevet, så den ikke gentager sig selv (gemmes i historikken)"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import holdsport, holdsport_skriv
    # En aktivitet, Holdsport har koblet til flere tjanser, hører til den tjans, robotten har givet
    # den – også selv om Holdsport har skrevet en anden tjans ind i den i nat.
    faste = {a: p["ejer"] for a, p in bindinger({}, forventede, foer, nu).items() if p.get("ejer")}
    hs = holdsport.koer(forventede, ROOT, faste)
    bundet = bindinger(hs, forventede, foer, nu)
    nye_faste = {a: p["ejer"] for a, p in bundet.items() if p.get("ejer")}
    if nye_faste != faste:                    # robotten har lige opdaget en ny: læs igen med den
        igen = holdsport.koer(forventede, ROOT, nye_faste)
        if igen.get("aktiveret") and not igen.get("fejl"):
            hs = igen
    ejere(bundet, hs)
    tjanser = {}
    for f in forventede:
        ev = evs[tjans_noegle(f)]
        tjanser[tjans_noegle(f)] = {
            "tjans": f["tjans"], "kampnr": f["kampnr"], "kamp": f.get("kamp", ""),
            "start": f["start"][:16].replace("T", " "), "slut": f["slut"][:16].replace("T", " "),
            "navn": ev["summary"], "beskrivelse": ev["description"], "sted": ev["location"],
            "antal": f["antal"]}
    klient = holdsport_skriv.Klient(os.environ.get("HOLDSPORT_USER", "").strip(),
                                    os.environ.get("HOLDSPORT_PASSWORD", "").strip())
    rettet, skrevet = holdsport_skriv.ret(hs, tjanser, (foer or {}).get("_skrevet"), nu, klient,
                                          tilladt=bool(indstilling("HOLDSPORT_RETTER", True)))
    if rettet["flyttet"] or rettet["oprettet"]:
        faste = {a: p["ejer"] for a, p in bundet.items() if p.get("ejer")}
        igen = holdsport.koer(forventede, ROOT, faste)              # står det rigtigt nu?
        hs = igen if igen.get("aktiveret") and not igen.get("fejl") else _rettet_i(hs, rettet)
        ejere(bundet, hs)
    hs["rettet"] = rettet
    return hs, bundet, skrevet


def _rettet_i(hs, rettet):
    """Kunne Holdsport ikke læses igen efter rettelserne, bruges Holdsports svar på dem."""
    til = {str(r["aktivitet"]): r["til"] for r in rettet["flyttet"]}
    for f in hs.get("fundne") or []:
        if str(f.get("aktivitet")) in til:
            f["hs_start"] = til[str(f["aktivitet"])]
    ny = {(r["kampnr"], r["tjans"], r["start"]): r for r in rettet["oprettet"]}
    hold = {p.get("kode"): p for p in hs.get("hold") or []}
    rest = []
    for m in hs.get("mangler") or []:
        r = ny.get((m["kampnr"], m["tjans"], m["start"]))
        if not r:
            rest.append(m)
            continue
        hs["fundne"].append({**m, "aktivitet": r["aktivitet"], "hs_start": m["start"],
                             "kilde": "robot"})
        hs["fundet"] = hs.get("fundet", 0) + 1
        p = hold.get(m["tjans"]) or {}
        p["fundet"], p["mangler"] = p.get("fundet", 0) + 1, max(0, p.get("mangler", 0) - 1)
    hs["mangler"] = rest
    return hs


# Set 8/10 2026 (robottens advarsel om genbrug): Holdsport havde koblet aktivitet 56812950 – H3's
# pokaltjans 11/10 (kamp 150792) – til H3's tjans 1/11 (kamp 148646) også og flyttede den frem og
# tilbage mellem de to dage. Den slags finder robotten selv fremover (bindinger).
KENDT_BUNDET = {"56812950": {"tjanser": ["148646-H3", "150792-H3"], "ejer": "150792-H3",
                             "set": "2026-10-08T00:00:00+00:00"}}


def bindinger(hs, forventede, foer, nu):
    """Aktiviteter, Holdsport har koblet til mere end én tjans' kalender-id. Holdsport skriver så
    begge tjanser ind i den samme aktivitet, hver gang den henter kalenderen, og aktiviteten
    hopper frem og tilbage mellem dem – sådan forsvandt H3's pokaltjans 11/10 2026. Robotten ser
    det på to måder:
      - en aktivitet, Holdsport har lavet fra kalenderen, står præcis på tidspunktet for en anden
        af holdets tjanser
      - en aktivitet var én tjans ved sidste kørsel og er en anden nu (Holdsport har genbrugt den)
    Returnerer {aktivitet: {"tjanser": [nøgler], "ejer": nøgle, "set": tid}}.

    Ejeren beholder aktiviteten og dens tilmeldinger: den tjans, aktiviteten var, før Holdsport
    tog den – ellers den, der står i den nu. Robotten flytter den tilbage til ejeren, og de andre
    tjanser får hver deres egen aktivitet. Bindingerne huskes, til alle tjanserne er over en måned
    gamle. Uden Holdsport-data (hs = {}) gives bare det, robotten allerede ved."""
    nu_iso = nu.isoformat()
    noegler = {tjans_noegle(f) for f in forventede}
    bundet = {}
    for kilde in (KENDT_BUNDET, (foer or {}).get("_bundet") or {}):
        for a, p in kilde.items():
            if not isinstance(p, dict) or not p.get("tjanser"):
                continue
            gl = bundet.get(str(a)) or {}
            bundet[str(a)] = {"tjanser": sorted(set(gl.get("tjanser") or []) | set(p["tjanser"])),
                              "ejer": p.get("ejer") or gl.get("ejer"),
                              "set": gl.get("set") or p.get("set") or nu_iso}
    if hs.get("aktiveret") and not hs.get("fejl"):
        starter = {}
        for f in forventede:
            starter.setdefault((f["tjans"], f["start"][:16].replace("T", " ")), []).append(
                tjans_noegle(f))
        foer_akt = {str(p["aktivitet"]): n for n, p in (foer or {}).items()
                    if not n.startswith("_") and isinstance(p, dict) and p.get("aktivitet")}
        for f in hs.get("fundne") or []:
            n, a = tjans_noegle(f), str(f.get("aktivitet") or "")
            if not a:
                continue
            andre, gl = set(), foer_akt.get(a)
            if f.get("kilde") == "kalender" and f.get("hs_start") and f["hs_start"] != f["start"]:
                andre |= {m for m in starter.get((f["tjans"], f["hs_start"]), []) if m != n}
            if gl not in (None, n) and gl in noegler:
                andre.add(gl)                      # var en anden tjans ved sidste kørsel
            if andre or a in bundet:
                p = bundet.setdefault(a, {"tjanser": [], "set": nu_iso})
                p["tjanser"] = sorted(set(p["tjanser"]) | andre | {n})
                if p.get("ejer") not in noegler:
                    p["ejer"] = gl if gl in noegler else n
    # glem en binding, når alle dens tjanser er over en måned gamle eller væk fra tjanselisten
    start = {tjans_noegle(f): f["start"][:16].replace("T", " ") for f in forventede}
    graense = (nu - timedelta(days=31)).astimezone(DK).strftime("%Y-%m-%d %H:%M")
    return {a: p for a, p in bundet.items()
            if any(start.get(n, "") >= graense for n in p["tjanser"])}


def ejere(bundet, hs):
    """Ejeren af en aktivitet i bundet er den tjans, den hører til efter sidste læsning af
    Holdsport (med robottens faste koblinger). Har du selv givet tjansen en anden aktivitet, er
    aktiviteten nu den tjans, den viser."""
    for f in hs.get("fundne") or []:
        a = str(f.get("aktivitet") or "")
        if a in bundet:
            bundet[a]["ejer"] = tjans_noegle(f)


def kalender_spejl(hs, forventede, bundet, foer):
    """De tjanser, kalenderen skal vise som en anden tjans: {nøgle: den anden tjans' nøgle}.

    Har Holdsport koblet en tjans' kalender-id til en aktivitet, der er en anden tjans' (bindinger),
    får kalender-id'et den anden tjans' tidspunkt og tekst i kalenderen. Så skriver Holdsport det
    samme ind i aktiviteten fra begge kalender-id'er, og aktiviteten bliver, hvor den skal være.
    Tjansen selv har sin egen aktivitet i Holdsport – en, du har oprettet, eller en, robotten
    opretter og holder på plads. Har tjansen en aktivitet, Holdsport har lavet fra kalenderen, er
    det den, kalender-id'et hører til, og så røres den ikke. Kunne Holdsport ikke læses, gælder
    det samme som ved sidste kørsel."""
    noegler = {tjans_noegle(f) for f in forventede}
    if not hs.get("aktiveret") or hs.get("fejl"):
        return {n: p["spejl"] for n, p in (foer or {}).items()
                if n in noegler and isinstance(p, dict) and p.get("spejl") in noegler}
    egen_kalender = {tjans_noegle(f) for f in hs.get("fundne") or [] if f.get("kilde") == "kalender"}
    ud = {}
    for p in bundet.values():
        ejer = p.get("ejer")
        if ejer not in noegler:
            continue
        for n in p["tjanser"]:
            if n != ejer and n in noegler and n not in egen_kalender:
                ud[n] = ejer
    # en tjans, der selv vises som en anden, kan ikke lægge navn til en tredje
    return {n: e for n, e in ud.items() if e not in ud}


def indstilling(navn, standard):
    """En indstilling fra scripts/indstillinger.py – standard, hvis den ikke står der."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import indstillinger
        return getattr(indstillinger, navn, standard)
    except ImportError:
        return standard


UGEDAGE = ("man", "tir", "ons", "tor", "fre", "lør", "søn")


def kort(s):
    """'2026-10-11 10:30' -> 'søn 11/10 kl. 10.30'."""
    try:
        d = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return s or ""
    return f"{UGEDAGE[d.weekday()]} {d.day}/{d.month} kl. {d:%H.%M}"


def alarm(status, foer, nu):
    """Det, der skal ud som alarm på telefonen (alert.py sender den via ntfy): nye problemer
    siden sidste kørsel, og alle problemer med en tjans inden for AKUT – om dem sendes der ved
    hver kørsel, til de er løst. Har robotten rettet noget i Holdsport, får du også besked, og er
    alt i orden igen efter et problem, kommer der også besked.
    Returnerer (alarm til status.json, det robotten skal huske til næste kørsel)."""
    def tid(s, fmt):
        try:
            return datetime.strptime((s or "")[:16], fmt).replace(tzinfo=DK)
        except ValueError:
            return None

    p = {}                                     # nøgle -> (tekst, hvornår det gælder)
    for h in status["huller"]:
        p[f"hul-{h['kampnr']}"] = (f"{h['start'][:5]}: {h['kamp']} har intet hold på tjans",
                                   tid(h["start"], "%d-%m-%Y %H:%M"))
    for f in status["forsvundne"]:
        p[f"forsvundet-{f['kampnr']}-{f['tjans']}"] = (
            f"{f['tjans']}: kamp {f['kampnr']} ({f['kamp']}) findes ikke længere",
            tid(f["dato"], "%d-%m-%y"))
    for d in status.get("dobbelt_tjans") or []:
        p[f"dobbelt-{d['hold']}-{d['dato']}-{d['tjans1']}"] = (
            f"{d['hold']} har to tjanser samtidig {d['dato'][:5]}", tid(d["dato"], "%d-%m-%Y"))
    for k in status.get("konflikter") or []:
        p[f"konflikt-{k['noegle']}"] = (
            f"{k['hold']} {k['dato'][:5]}: tjansen ligger oven i holdets egen kamp",
            tid(k["dato"], "%d-%m-%Y"))
    hs = status.get("holdsport") or {}
    rettet = hs.get("rettet") or {}
    if hs.get("aktiveret") and hs.get("fejl"):
        p["holdsport-fejl"] = (f"Robotten kunne ikke tjekke Holdsport: {hs['fejl']}", None)
    for e in rettet.get("fejl") or []:
        if e.get("tjans"):
            p[f"skrivefejl-{e['kampnr']}-{e['tjans']}"] = (
                f"Robotten kunne ikke rette {e['hvilken']}: {e['fejl']}",
                tid(e["start"], "%Y-%m-%d %H:%M"))
        else:
            p["skrivefejl"] = (f"Robotten kan ikke rette i Holdsport: {e['fejl']}", None)
    for g in rettet.get("givet_op") or []:
        if g.get("oprettet_foer"):
            tekst = (f"{g['tjans']}'s tjans {kort(g['start'])} ({g['kamp']}): robotten oprettede "
                     "den, men den er slettet i Holdsport igen. Skal den ikke være, så fjern den "
                     "fra tjanselisten – ellers opretter robotten den igen om en uge")
        else:
            tekst = (f"{g['tjans']}'s tjans {kort(g['start'])} ({g['kamp']}) bliver flyttet "
                     f"tilbage i Holdsport igen og igen (aktivitet {g.get('aktivitet')}). Robotten "
                     "har flyttet den 3 gange på 3 døgn – ret den i Holdsport")
        p[f"givetop-{g['kampnr']}-{g['tjans']}"] = (tekst, tid(g["start"], "%Y-%m-%d %H:%M"))
    for m in hs.get("mangler") or []:
        p[f"mangler-{m['kampnr']}-{m['tjans']}"] = (
            f"{m['tjans']}'s tjans {kort(m['start'])} ({m['kamp']}) mangler i Holdsport",
            tid(m["start"], "%Y-%m-%d %H:%M"))
    for r in hs.get("forkert_tid") or []:
        if r.get("dublet"):
            tekst = f"{r['tjans']}: ekstra kopi af tjansen {kort(r['start'])} i Holdsport – slet den"
        else:
            tekst = (f"{r['tjans']}'s tjans skal stå {kort(r['start'])}, men står "
                     f"{kort(r['hs_start'])} i Holdsport")
        p[f"forkert-{r['kampnr']}-{r['tjans']}-{r['hs_start']}-{r.get('aktivitet')}"] = (
            tekst, tid(r["start"], "%Y-%m-%d %H:%M"))
    for g in hs.get("genbrugt") or []:
        p[f"genbrugt-{g['aktivitet']}-{g['nu']}"] = (
            f"{g['tjans']}: Holdsport har lavet tjansen {kort(g['foer_start'])} om til "
            f"{kort(g['nu_start'])} – tjek de tilmeldte", tid(g["nu_start"], "%Y-%m-%d %H:%M"))
    if "Google-arket kunne ikke læses" in (status.get("tjanskilde") or ""):
        p["ark"] = ("Google-arket med tjanselisten kunne ikke læses", None)

    # Det, robotten selv har rettet i denne kørsel – til orientering
    gjort = [f"Flyttet: {r['tjans']}'s tjans {kort(r['start'])} ({r['kamp']}) – stod "
             f"{kort(r['fra'])}" for r in rettet.get("flyttet") or []]
    gjort += [f"Oprettet: {r['tjans']}'s tjans {kort(r['start'])} ({r['kamp']})"
              for r in rettet.get("oprettet") or []]

    nu_dk = nu.astimezone(DK)
    akutte = [k for k, (_, t) in p.items() if t and nu_dk - timedelta(hours=3) <= t <= nu_dk + AKUT]
    foer_noegler = set(((foer or {}).get("_alarm") or {}).get("noegler") or [])
    if foer is not None and "_alarm" not in foer:
        # første kørsel med alarmer: det, der allerede står på siden, er ikke nyt (det akutte
        # sendes stadig)
        foer_noegler = set(p)
    nye = [k for k in p if k not in foer_noegler and k not in akutte]
    i_orden = bool(foer_noegler) and not p
    linjer = ([p[k][0] for k in sorted(akutte, key=lambda k: p[k][1])]
              + [p[k][0] for k in nye])
    andre = len(p) - len(set(akutte) | set(nye))
    if andre and linjer:
        linjer.append(f"… og {andre} andre ting, du allerede har fået besked om")
    if gjort:
        linjer += (["Robotten har rettet i Holdsport:"] if linjer else []) + gjort
    if akutte:
        titel = "AKUT: en tjans inden for 3 døgn står forkert" if len(akutte) == 1 else \
                f"AKUT: {len(akutte)} tjanser inden for 3 døgn står forkert"
    elif nye:
        titel = "Tjanser: noget nyt kræver handling"
    elif gjort:
        titel = "Robotten har rettet i Holdsport"
    else:
        titel = "Tjanser: alt er i orden igen" if i_orden else ""
    return ({"send": bool(akutte or nye or i_orden or gjort), "akut": bool(akutte),
             "titel": titel, "linjer": linjer, "i_orden": i_orden and not gjort,
             "rettet": len(gjort), "problemer": len(p)},
            {"noegler": sorted(p), "tid": nu.isoformat()})


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


def dobbelt_tjans(forventede):
    """Kommende tjanser, hvor samme hold har to tjanser, der overlapper i tid. Holdet kan ikke
    tage begge — og står to tjanser på samme tidspunkt i holdets kalender, laver Holdsport dem
    til én aktivitet, der hører til den ene. Sådan mistede H3 sin tjans 1/11 i 2026: pokaltjansen
    stod en overgang samme tidspunkt, og aktiviteten blev pokaltjansens."""
    i_dag = datetime.now(DK).replace(hour=0, minute=0, second=0, microsecond=0)
    pr_hold = {}
    for f in forventede:
        st, sl = datetime.fromisoformat(f["start"]), datetime.fromisoformat(f["slut"])
        if st >= i_dag:
            pr_hold.setdefault(f["tjans"], []).append((st, sl, f))

    def beskriv(st, f):
        return f"kl. {st:%H:%M} {f['kamp']}" + (f" (kamp {f['kampnr']})" if f["kampnr"] else "")

    ud = []
    for hold, liste in sorted(pr_hold.items()):
        liste.sort(key=lambda x: x[0])
        for i, (st1, sl1, f1) in enumerate(liste):
            for st2, sl2, f2 in liste[i + 1:]:
                if st2 >= sl1:                   # sorteret efter start: resten ligger senere
                    break
                ud.append({"hold": hold, "dato": st1.strftime("%d-%m-%Y"), "_t": st1,
                           "samme_tid": st1 == st2,
                           "tjans1": beskriv(st1, f1), "tjans2": beskriv(st2, f2)})
    ud.sort(key=lambda e: (e["_t"], e["hold"]))
    for e in ud:
        del e["_t"]
    return ud


def kopi_tekst(r, foer=""):
    """Tekst til en ekstra aktivitet med samme kampnummer (r["dublet"]): hvilken der skal væk."""
    if not r.get("dublet"):
        return ""
    return foer + ("ekstra kopi, du selv har oprettet – slet den" if r.get("egen")
                   else "ekstra kopi – slet den")


if __name__ == "__main__":
    main()
