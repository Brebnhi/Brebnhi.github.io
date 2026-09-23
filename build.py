#!/usr/bin/env python3
"""
Bygger tjans-kalendere (.ics) til Holdsport ud fra tjanselisten og de officielle
kampprogram-feeds fra resultater.volleyball.dk.

Ét feed pr. (hold, antal personer), fordi Holdsport sætter maks. deltagere
én gang pr. import. Tjansen får stabilt UID pr. kampnummer, så en flyttet kamp
flytter tjansen i stedet for at oprette en ny.

Kilder:  data/tjanser.csv, data/feeds.json
Output:  docs/feeds/*.ics, docs/status.json, docs/tjanser/index.html
         (docs/index.html er klubbens startside og bygges ikke her)
"""

import csv, hashlib, json, os, re, shutil, sys, urllib.request
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

# (række i regnearket, holdnavn i turneringssystemet) -> klubbens interne holdnavn
CLUB_TEAMS = {
    ("Volleyligaen Kvinder", "Aalborg Volleyball"):   "D1",
    ("1. Division Kvinder",  "Aalborg Volleyball.2"): "D2",
    ("2. Division Kvinder",  "Aalborg Volleyball.3"): "D3",
    ("1. Division Herrer",   "Aalborg Volleyball"):   "H1",
    ("2. Division Herrer",   "Aalborg Volleyball.2"): "H2",
    ("2. Division Herrer",   "Aalborg Volleyball.3"): "H3",
}

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


def describe(ev):
    """Trækker kampnr, række, hjemme- og udehold ud af en VEVENT."""
    desc = ev.get("DESCRIPTION", "") or ""
    summ = ev.get("SUMMARY", "") or ""
    m = KAMPNR_RE.search(desc) or KAMPNR_RE.search(summ)
    kampnr = m.group(1) if m else ""
    lines = [l.strip() for l in desc.split("\n") if l.strip()]
    raekke_linje = lines[0] if lines else ""
    hjemme, ude = "", ""
    if " - " in summ:
        hjemme, ude = [p.strip() for p in summ.split(" - ", 1)]
    klub = ""
    for (raekke, holdnavn), kort in CLUB_TEAMS.items():
        if hjemme == holdnavn and raekke_linje.startswith(raekke):
            klub = kort
            break
    return {"kampnr": kampnr, "raekke": raekke_linje, "hjemme": hjemme,
            "ude": ude, "klubhold": klub,
            "hjemmekamp": "aalborg volleyball" in norm(hjemme),
            "start": ev.get("DTSTART"), "slut": ev.get("DTEND"),
            "sted": ev.get("LOCATION", "") or ""}


def load_feeds():
    path = os.path.join(ROOT, "data", "feeds.json")
    feeds = json.load(open(path, encoding="utf-8"))
    kampe, fejl, raa = {}, {}, 0
    for navn, url in feeds.items():
        try:
            evs = parse_ics(fetch(url))
        except Exception as exc:
            fejl[navn] = str(exc)
            continue
        raa += len(evs)
        for ev in evs:
            info = describe(ev)
            if not info["kampnr"] or not info["start"]:
                continue
            kampe.setdefault(info["kampnr"], info)   # samme kamp kan stå i to feeds
    return kampe, fejl, raa

# ------------------------------------------------------------------ tjanseliste

def tjans_kilde():
    """Tjanselisten hentes fra Google Sheet hvis SHEET_CSV_URL er sat,
    ellers fra data/tjanser.csv i repoet."""
    url = os.environ.get("SHEET_CSV_URL", "").strip()
    if url:
        try:
            return fetch(url).splitlines(), f"Google Sheet"
        except Exception as exc:
            print(f"ADVARSEL: kunne ikke hente Google Sheet ({exc}) "
                  f"– bruger data/tjanser.csv", file=sys.stderr)
    path = os.path.join(ROOT, "data", "tjanser.csv")
    return open(path, encoding="utf-8").read().splitlines(), "data/tjanser.csv"


def load_tjanser():
    rows = []
    linjer, kilde = tjans_kilde()
    load_tjanser.kilde = kilde
    if True:
        for r in csv.DictReader(linjer):
            r = {k: (v or "").strip() for k, v in r.items()}
            if not r.get("tjans"):
                continue
            r["antal"] = int(r["antal"]) if r["antal"] else 4
            r["ark_start"] = datetime.strptime(
                f"{r['dato']} {r['tid']}", "%d-%m-%y %H:%M").replace(tzinfo=DK)
            r["klubhold"] = CLUB_TEAMS.get((r["raekke"], r["hjemmehold"]), "")
            rows.append(r)
    return rows

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
    rows = load_tjanser()
    kampe, feed_fejl, raa = load_feeds()
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
            match_start, match_slut = kamp["start"], kamp["slut"]
            sted = kamp["sted"] or row["spillested"]
            ude = kamp["ude"] or row["udehold"]
            kilde = "feed"
        else:
            match_start, match_slut = row["ark_start"], None
            sted, ude = row["spillested"], row["udehold"]
            kilde = "mangler i feed" if row["kampnr"] else "regneark"

        antal = row["antal"]
        lead = LEAD_MINUTES.get(antal, 30)
        start = match_start - timedelta(minutes=lead)
        end = (match_slut if match_slut and match_slut > match_start
               else match_start + DEFAULT_LEN.get(antal, DEFAULT_LEN[4]))
        flyttet = bool(kamp) and match_start != row["ark_start"]

        klub = row["klubhold"] or row["raekke"]
        # antallet står også i titlen, så det er synligt selv hvis en
        # kalender-import ikke tager kommentarfeltet med
        summary = (f"Tjans ({antal} pers.): {klub} mod {ude}" if ude
                   else f"Tjans ({antal} pers.): {row['raekke']}")
        desc = (f"{ROLES.get(antal, ROLES[4])}\n\n"
                f"Kampstart kl. {match_start.astimezone(DK).strftime('%H:%M')} "
                f"– mød {lead} minutter før.\n"
                f"{row['raekke']}: {row['hjemmehold'] or klub} - {ude}\n"
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
                           "navn": summary, "start": start.isoformat(),
                           "antal": antal,
                           "kamp": f"{row['hjemmehold'] or klub} - {ude}"})
        rapport.append({**snapshot(row), "status": "ok", "kilde": kilde,
                        "start": start.astimezone(DK).isoformat(),
                        "kampstart": match_start.astimezone(DK).isoformat(),
                        "flyttet": flyttet, "sted": sted, "modstander": ude})

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
    hs = holdsport.koer(forventede, ROOT)

    huller, forsvundne = find_huller(rows, kampe)
    status = {
        "holdsport": hs,
        "tjanskilde": getattr(load_tjanser, "kilde", "data/tjanser.csv"),
        "opdateret": datetime.now(UTC).astimezone(DK).strftime("%d-%m-%Y %H:%M"),
        "feed_fejl": feed_fejl,
        "feed_kampe": len(kampe),
        "feed_raa": raa,
        "feeds": feeds,
        "tjanser": rapport,
        "huller": huller,
        "forsvundne": forsvundne,
        "flyttede": [r for r in rapport if r.get("flyttet")],
    }
    json.dump(status, open(os.path.join(ROOT, "docs", "status.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)

    from render import render
    side_dir = os.path.join(ROOT, "docs", "tjanser")   # startsiden ligger i docs/index.html
    os.makedirs(side_dir, exist_ok=True)
    open(os.path.join(side_dir, "index.html"), "w", encoding="utf-8").write(
        render(status, os.environ.get("BASE_URL", "")))

    print(f"{len(feeds)} feeds, {sum(f['kampe'] for f in feeds)} tjanser")
    print(f"{len(kampe)} kampe fra feeds ({raa} rå events)")
    print(f"huller: {len(huller)} | forsvundne: {len(forsvundne)} | flyttede: {len(status['flyttede'])}")
    if hs["aktiveret"]:
        if hs["fejl"]:
            print(f"Holdsport-tjek: {hs['fejl']}", file=sys.stderr)
        else:
            print(f"Holdsport-tjek: {hs['fundet']}/{hs['kontrolleret']} tjanser fundet"
                  f" | mangler: {len(hs['mangler'])}")
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


def snapshot(row):
    return {k: row[k] for k in ("kampnr", "dato", "tid", "raekke", "hjemmehold",
                                "udehold", "spillested", "antal", "tjans", "klubhold")}


def find_huller(rows, kampe):
    """Hjemmekampe i feed'et uden hold på tjans, og tjanser hvis kamp er væk."""
    daekket = {r["kampnr"] for r in rows if r["kampnr"]}
    huller = []
    for nr, k in kampe.items():
        if not k["hjemmekamp"] or nr in daekket:
            continue
        huller.append({"kampnr": nr, "raekke": k["raekke"], "klubhold": k["klubhold"],
                       "kamp": f"{k['hjemme']} - {k['ude']}", "sted": k["sted"],
                       "start": k["start"].astimezone(DK).strftime("%d-%m-%Y %H:%M")})
    huller.sort(key=lambda h: h["start"][6:10] + h["start"][3:5] + h["start"][:2] + h["start"][11:])
    forsvundne = [{"kampnr": r["kampnr"], "dato": r["dato"], "tjans": r["tjans"],
                   "kamp": f"{r['hjemmehold']} - {r['udehold']}"}
                  for r in rows if r["kampnr"] and r["kampnr"] not in kampe]
    return huller, forsvundne


if __name__ == "__main__":
    main()
