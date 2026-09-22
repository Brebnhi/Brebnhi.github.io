#!/usr/bin/env python3
"""
Forventet kørselsudligning for klubbens hold — Volleyball Danmarks
rejseudligning, regnet ud fra de officielle kampprogrammer.

Tre slags udligning, hver med VD's egen metode:

  Grundspil (Økonomiske retningslinjer § 2, pkt. 1-3)
    * Én pulje pr. række og køn (fx 1. Division Herrer). Øst, Vest, Syd og
      Nord i samme række regnes sammen.
    * Udgift = holdets udekampe: biler × (2 × km × statens laveste km-takst
      + broafgift, hvis turen krydser Storebælt). Liga og 1. division: 3 biler,
      2. division: 2 biler.
    * Udligning = holdets udgift − gennemsnittet pr. hold i puljen.

  Pokal (Pokalturneringens reglement § 20)
    * Hver runde for sig, kvinder og herrer hver for sig. Udeholdet: 3 biler.
    * Udligning = holdets udgift − rundens gennemsnit pr. hold.
    * Final4 afregnes efter regning og er ikke med.

  Slutspil i Volleyligaen (§ 2, pkt. 4 — "øvrige kampe")
    * Gennemsnitspris pr. kamp for alle slutspils- og placeringskampe (pr. køn).
    * Udligning = holdets udgift − antal spillede kampe × gennemsnitsprisen / 2.
    * Afregnes efter sæsonen.

  km = vejafstand fra udeholdets hjemmebane til spillestedet.
  Plus = kreditnota (klubben får penge), minus = faktura (klubben betaler).

Klubbens hold, pokalrunder og slutspil findes automatisk via foreningssiderne
på resultater.volleyball.dk, så intet skal rettes, når en ny sæson starter —
kun km-taksten og broprisen i config.json en gang om året.

Kilder:  config.json · resultater.volleyball.dk · DAWA (adresser → koordinater)
         · OSRM/OpenStreetMap (vejafstande)
Cache:   cache/*.json — gemmes mellem kørsler af GitHub Actions
Output:  <ud>/index.html og <ud>/status.json
"""

import argparse, html as htmlmod, json, math, os, re, sys, time, traceback
import urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK, UTC = ZoneInfo("Europe/Copenhagen"), timezone.utc
TMS = "https://resultater.volleyball.dk/tms/Turneringer-og-resultater/"
CAL = "https://resultater.volleyball.dk/cal/Puljekampprogram.ashx?key="
DAWA = "https://api.dataforsyningen.dk/"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = os.environ.get("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
UA = ("aalborg-volley-koerselsudligning/1.0 "
      "(+https://github.com/Brebnhi/Tjanser-i-Holdsport)")
SKOEN_FAKTOR = 1.3          # vejlængde ≈ fugleflugt × 1,3, hvis OSRM svigter
SLUTSPIL_DAGE_FOER = 60     # led efter slutspil fra ca. 2 mdr. før grundspillet slutter

ADVARSLER = []


def advar(tekst):
    if tekst not in ADVARSLER:
        ADVARSLER.append(tekst)
        print("ADVARSEL:", tekst, file=sys.stderr)

# ------------------------------------------------------------------ netværk

_sidst = {}


def hent(url, accept="*/*", pause=0.0, forsoeg=3):
    """GET med få genforsøg. `pause` holder mindst så mange sekunder mellem
    kald til samme vært (Nominatim og OSRM beder om max ét kald i sekundet)."""
    vaert = urllib.parse.urlsplit(url).netloc
    fejl = None
    for n in range(forsoeg):
        if pause:
            vent = _sidst.get(vaert, 0) + pause - time.time()
            if vent > 0:
                time.sleep(vent)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                tegnsaet = r.headers.get_content_charset() or "utf-8"
            _sidst[vaert] = time.time()
            try:                                  # samme som tjans: UTF-8 først
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode(tegnsaet if tegnsaet.lower() != "utf-8" else "latin-1",
                                   errors="replace")
        except Exception as exc:          # noqa: BLE001 — vi prøver igen
            fejl = exc
            _sidst[vaert] = time.time()
            if n + 1 < forsoeg:
                time.sleep(2 * (n + 1))
    raise RuntimeError(f"{url} kunne ikke hentes: {fejl}")


def hent_json(url, pause=0.0):
    return json.loads(hent(url, "application/json", pause=pause))


class Cache:
    """Små JSON-filer i cache/. GitHub Actions gemmer mappen mellem kørsler."""

    def __init__(self, mappe):
        self.mappe = mappe
        self.data = {}
        os.makedirs(mappe, exist_ok=True)

    def __call__(self, navn):
        if navn not in self.data:
            sti = os.path.join(self.mappe, navn + ".json")
            try:
                with open(sti, encoding="utf-8") as f:
                    self.data[navn] = json.load(f)
            except Exception:             # noqa: BLE001 — tom cache er fint
                self.data[navn] = {}
        return self.data[navn]

    def gem(self):
        for navn, d in self.data.items():
            with open(os.path.join(self.mappe, navn + ".json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True, default=str)

# ------------------------------------------------------------------ ical
# Samme parser som tjans/scripts/build.py (kører allerede hver nat på feeds'ene)


def unfold(text):
    ud = []
    for linje in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linje[:1] in (" ", "\t") and ud:
            ud[-1] += linje[1:]
        else:
            ud.append(linje)
    return ud


def unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def parse_dt(value):
    value = value.strip()
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if "T" in value:
            return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=DK)
        return datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=DK)
    except ValueError:
        return None


def parse_ics(text):
    events, cur, dybde = [], None, 0
    for linje in unfold(text):
        u = linje.upper()
        if u.startswith("BEGIN:VEVENT"):
            cur, dybde = {}, 0
            continue
        if u.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        if u.startswith("BEGIN:"):
            dybde += 1
            continue
        if u.startswith("END:"):
            dybde -= 1
            continue
        if dybde > 0 or ":" not in linje:
            continue
        hoved, _, vaerdi = linje.partition(":")
        navn = hoved.split(";")[0].upper()
        cur[navn] = parse_dt(vaerdi) if navn in ("DTSTART", "DTEND") else unescape(vaerdi)
    return events

# ------------------------------------------------------------------ html

A_RE = re.compile(r"<a\b[^>]*?href\s*=\s*(['\"])(.*?)\1[^>]*>(.*?)</a\s*>", re.I | re.S)
TR_RE = re.compile(r"<tr\b.*?</tr\s*>", re.I | re.S)
TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.I | re.S)
GENERISKE = {"stilling", "kampprogram", "komplet kampprogram", "holdoversigt",
             "til opslagstavlen", "udskriv", ""}


def tekst(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def ankre(s):
    return [(htmlmod.unescape(m.group(2)), tekst(m.group(3))) for m in A_RE.finditer(s or "")]


def id_fra(href, navn):
    m = re.search(rf"[?&]{navn}=(\d+)", href or "", re.I)
    return int(m.group(1)) if m else None


def norm(s):
    s = (s or "").lower().replace("é", "e").replace("è", "e")
    return re.sub(r"\s+", " ", re.sub(r"[^\wæøå.]+", " ", s)).strip()


def husnr(gade):
    """'Stadion Alle 2 B' → 'Stadion Alle 2B' (samme skrivemåde som DAWA)."""
    return re.sub(r"(\d+)\s+([A-Za-z])\b", r"\1\2", re.sub(r"\s+", " ", gade or "")).strip()

# ------------------------------------------------------------------ turneringssystemet


def klubbens_hold(forening_id):
    """Alle en klubs hold i indeværende sæson: hold, række (id) og pulje (id)."""
    side = hent(f"{TMS}Forening-Holdoversigt.aspx?ForeningsId={forening_id}", "text/html")
    ud = []
    for raekke_html in TR_RE.findall(side):
        hold = raekke = pulje = None
        for href, txt in ankre(raekke_html):
            if id_fra(href, "HoldId") is not None:
                hold = hold or (id_fra(href, "HoldId"), txt)
            elif id_fra(href, "RaekkeId") is not None:
                raekke = raekke or (id_fra(href, "RaekkeId"), txt)
            elif id_fra(href, "PuljeId") is not None:
                pulje = pulje or (id_fra(href, "PuljeId"), txt)
        if raekke and pulje:
            if not hold:
                celler = TD_RE.findall(raekke_html)
                hold = (None, tekst(celler[0]) if celler else "")
            ud.append({"hold": hold[1], "hold_id": hold[0], "raekke": raekke[1],
                       "raekke_id": raekke[0], "pulje": pulje[1], "pulje_id": pulje[0]})
    return ud


def puljer_i_raekke(raekke_id):
    """PuljeId'er i en række. En række med kun én pulje viser puljen direkte."""
    side = hent(f"{TMS}Pulje-Oversigt.aspx?RaekkeId={raekke_id}", "text/html")
    navne, orden = {}, []
    for href, txt in ankre(side):
        pid = id_fra(href, "PuljeId")
        if pid is None or id_fra(href, "HoldId") is not None:
            continue
        if pid not in navne:
            navne[pid] = ""
            orden.append(pid)
        if txt.lower() not in GENERISKE and not navne[pid]:
            navne[pid] = txt
    return [(pid, navne[pid]) for pid in orden]


def kalender_noegle(pulje_id):
    for side_navn in ("Pulje-Komplet-Kampprogram.aspx", "Pulje-Kampprogram.aspx"):
        try:
            side = hent(f"{TMS}{side_navn}?PuljeId={pulje_id}", "text/html")
        except RuntimeError:
            continue
        m = re.search(r"Puljekampprogram\.ashx\?key=([0-9A-Fa-f-]{36})", side)
        if m:
            return m.group(1)
    return None


class IngenKampe(RuntimeError):
    """Puljen findes, men kampprogrammet er ikke lagt ud endnu (typisk om sommeren)."""


KAMPNR_RE = re.compile(r"Kampnr\.?\s*(\d{3,9})", re.I)
POSTNR_RE = re.compile(r"^(\d{4})\s+(\S.*)$")
# Spillede kampe har resultatet i titlen: "Ikast KFUM.2 - ASV Aarhus.2 3 - 1"
RESULTAT_RE = re.compile(r"\s+\d{1,2}\s*-\s*\d{1,2}(\s*\(.*\))?\s*$")


def parse_kamp(ev):
    """Én kamp fra puljens kalender. DESCRIPTION ser sådan ud:
    række pulje / Runde n / Kampnr n / (tom) / Hjemme - Ude / spillested /
    gade / postnr by / dato."""
    raa = re.sub(r"\s+", " ", (ev.get("SUMMARY") or "")).strip()
    summ = RESULTAT_RE.sub("", raa)
    if " - " not in summ:                # "resultatet" var en del af holdnavnene
        summ = raa
    if " - " not in summ:
        return None
    hjemme, ude = [x.strip() for x in summ.split(" - ", 1)]
    linjer = [re.sub(r"\s+", " ", l).strip() for l in (ev.get("DESCRIPTION") or "").split("\n")]
    sted = (ev.get("LOCATION") or "").strip()
    gade = postnr = by = ""
    i = next((n for n, l in enumerate(linjer) if l in (raa, summ)), None)
    if i is None:
        i = next((n for n, l in enumerate(linjer) if " - " in l and n > 0), None)
    if i is not None:
        rest = [l for l in linjer[i + 1:] if l]
        for j, l in enumerate(rest[:7]):
            m = POSTNR_RE.match(l)
            if m and j >= 1:
                sted = rest[0] or sted
                gade = ", ".join(rest[1:j])
                postnr, by = m.group(1), m.group(2).strip()
                break
    m = KAMPNR_RE.search(ev.get("DESCRIPTION") or "")
    k = {"kampnr": m.group(1) if m else (ev.get("UID") or ""), "hjemme": hjemme,
         "ude": ude, "sted": sted, "gade": gade, "postnr": postnr, "by": by,
         "start": ev.get("DTSTART"), "linje1": next((l for l in linjer if l), "")}
    k["key"] = sted_noegle(k)
    return k


def sted_noegle(k):
    if k.get("gade") and k.get("postnr"):
        return norm(f"{husnr(k['gade'])}, {k['postnr']}")
    return "navn:" + norm(k.get("sted"))


def kampe_i_pulje(pulje_id, cache):
    noegler = cache("noegler")
    noegle = noegler.get(str(pulje_id)) or kalender_noegle(pulje_id)
    if not noegle:
        raise RuntimeError(f"fandt ikke puljens kalender (pulje {pulje_id})")
    noegler[str(pulje_id)] = noegle
    kampe, set_ = [], set()
    for ev in parse_ics(hent(CAL + noegle, "text/calendar")):
        k = parse_kamp(ev)
        if not k or k["kampnr"] in set_:
            continue
        set_.add(k["kampnr"])
        kampe.append(k)
    if not kampe:
        raise IngenKampe(f"puljens kalender er tom (pulje {pulje_id})")
    return kampe


def registrerede_spillesteder(pulje_id, cache):
    """{hold: {"id", "navn"}} — holdenes registrerede hjemmebane i puljen."""
    c = cache("registreret")
    if str(pulje_id) in c:
        return c[str(pulje_id)]
    side = hent(f"{TMS}Pulje-Holdoversigt.aspx?PuljeId={pulje_id}", "text/html")
    ud = {}
    for raekke_html in TR_RE.findall(side):
        hold = sted = None
        for href, txt in ankre(raekke_html):
            if id_fra(href, "HoldId") is not None and hold is None:
                hold = txt
            elif id_fra(href, "SpillestedsId") is not None and sted is None:
                sted = {"id": id_fra(href, "SpillestedsId"), "navn": txt}
        if hold and sted:
            ud[hold] = sted
    c[str(pulje_id)] = ud
    return ud


def parse_adresse(linjer):
    """['Vrenderupvej 40 C', 'Vrenderup', '6818 Årre', 'Danmark'] → gade/postnr/by."""
    linjer = [l for l in (x.strip() for x in linjer) if l]
    for i, l in enumerate(linjer):
        m = POSTNR_RE.match(l)
        if m and i >= 1:
            foran = linjer[:i]
            gade = next((x for x in foran if re.search(r"\d", x)), foran[0])
            return {"gade": gade, "postnr": m.group(1),
                    "by": re.sub(r"\s+Danmark$", "", m.group(2)).strip()}
    samlet = " ".join(linjer)
    m = re.match(r"^(.*?\d+\s?[A-Za-z]?)\b.*?\b(\d{4})\s+(.+?)(?:\s+Danmark)?$", samlet)
    if m:
        return {"gade": m.group(1).strip(), "postnr": m.group(2), "by": m.group(3).strip()}
    return None


def spillested_adresse(sid, cache):
    """Adressen på et spillested (Spillested-Information), cachet for altid."""
    c = cache("spillesteder")
    if str(sid) in c:
        return c[str(sid)]
    side = hent(f"{TMS}Spillested-Information.aspx?SpillestedsId={sid}", "text/html")
    res = None
    for raekke_html in TR_RE.findall(side):
        celler = TD_RE.findall(raekke_html)
        if len(celler) >= 2 and tekst(celler[0]).lower().startswith("adresse"):
            dele = re.split(r"<br\s*/?>|</div>|</p>|</span>|\n", celler[1], flags=re.I)
            res = parse_adresse([tekst(d) for d in dele])
            break
    c[str(sid)] = res
    return res


def forening_for_hold(hold_id, cache):
    """ForeningsId for et hold (via holdets informationsside), cachet for altid."""
    c = cache("foreninger")
    if str(hold_id) in c:
        return c[str(hold_id)]
    side = hent(f"{TMS}Hold-Information.aspx?HoldId={hold_id}", "text/html")
    m = re.search(r"ForeningsId=(\d+)", side)
    c[str(hold_id)] = int(m.group(1)) if m else None
    return c[str(hold_id)]


def hold_i_pulje(pulje_id):
    """[(hold_id, holdnavn)] fra puljens holdoversigt."""
    side = hent(f"{TMS}Pulje-Holdoversigt.aspx?PuljeId={pulje_id}", "text/html")
    ud, set_ = [], set()
    for href, txt in ankre(side):
        hid = id_fra(href, "HoldId")
        if hid is not None and hid not in set_:
            set_.add(hid)
            ud.append((hid, txt))
    return ud

# ------------------------------------------------------------------ steder og afstande


def adresse_kandidater(gade, postnr, by):
    gade = husnr(gade)
    ud = [f"{gade}, {postnr} {by}"]
    if "," in gade:                      # "v/ Holbæk By Skole, Bispehøjen 2"
        ud.append(f"{gade.split(',')[-1].strip()}, {postnr} {by}")
    return ud


def _dawa(adr):
    d = hent_json(f"{DAWA}adresser?struktur=mini&per_side=1&q=" + urllib.parse.quote(adr))
    if d:
        return {"lat": d[0]["y"], "lon": d[0]["x"], "kilde": "DAWA",
                "praecision": "adresse", "fundet": d[0].get("betegnelse", "")}


def _dawa_vask(adr):
    d = hent_json(f"{DAWA}datavask/adresser?betegnelse=" + urllib.parse.quote(adr))
    r = (d.get("resultater") or [None])[0]
    if not r:
        return None
    a = r.get("aktueladresse") or r.get("adresse") or {}
    if not a.get("href"):
        return None
    m = hent_json(a["href"] + ("&" if "?" in a["href"] else "?") + "struktur=mini")
    kat = d.get("kategori", "?")
    return {"lat": m["y"], "lon": m["x"], "kilde": f"DAWA datavask ({kat})",
            "praecision": "adresse" if kat in ("A", "B") else "usikker adresse",
            "fundet": m.get("betegnelse", "")}


def _nominatim(gade, postnr, by):
    q = {"format": "jsonv2", "limit": "1", "countrycodes": "dk",
         "street": gade, "postalcode": postnr, "city": by}
    d = hent_json(NOMINATIM + "?" + urllib.parse.urlencode(q), pause=1.1)
    if d:
        return {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]),
                "kilde": "OpenStreetMap", "praecision": "adresse",
                "fundet": d[0].get("display_name", "")}


def _postnummer(postnr):
    d = hent_json(f"{DAWA}postnumre/{postnr}")
    lon, lat = d["visueltcenter"]
    return {"lat": lat, "lon": lon, "kilde": "DAWA postnummer",
            "praecision": "postnummer", "fundet": f"{postnr} {d.get('navn', '')}"}


def geokod(k, cache, manuelle):
    """Koordinater til et spillested (cachet)."""
    geo = cache("steder")
    key = k["key"]
    adr = f"{k.get('gade', '')}, {k.get('postnr', '')} {k.get('by', '')}".strip(", ")
    for n_ in (adr, k.get("sted"), key):
        if n_ in manuelle:
            lat, lon = manuelle[n_]
            return {"lat": lat, "lon": lon, "kilde": "config.json", "praecision": "manuel",
                    "navn": k.get("sted"), "adresse": adr}
    if key in geo:
        return geo[key]
    res = None
    if k.get("postnr") and not k.get("gade"):
        try:
            res = _postnummer(k["postnr"])
        except Exception:                 # noqa: BLE001
            res = None
    if k.get("gade") and k.get("postnr"):
        kilder = [(_dawa, a) for a in adresse_kandidater(k["gade"], k["postnr"], k["by"])]
        kilder += [(_dawa_vask, adr), (lambda _a: _nominatim(k["gade"], k["postnr"], k["by"]), adr),
                   (lambda _a: _postnummer(k["postnr"]), adr)]
        for fn, a in kilder:
            try:
                res = fn(a)
            except Exception as exc:     # noqa: BLE001 — næste kilde
                print(f"  geokodning via {getattr(fn, '__name__', 'kilde')} fejlede for "
                      f"{a}: {exc}", file=sys.stderr)
                res = None
            if res:
                break
    if not res:
        advar(f"Kunne ikke finde {k.get('sted') or key} ({adr}). Tilføj koordinater under "
              "\"steder\" i config.json.")
        return None
    if res["praecision"] != "adresse":
        advar(f"{k.get('sted')} ({adr}) er placeret ud fra {res['praecision']} "
              f"({res['fundet']}).")
    res.update({"navn": k.get("sted"), "adresse": adr})
    geo[key] = res
    return res


def punkt(g):
    return f"{g['lat']:.5f},{g['lon']:.5f}"


def fugleflugt(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def sikr_afstande(punkter, cache):
    """Henter vejafstande mellem alle punkter i én OSRM-tabel, hvis nogen mangler."""
    af = cache("afstande")
    pts = sorted(set(punkter))
    if len(pts) < 2 or all(f"{a}|{b}" in af for a in pts for b in pts if a != b):
        return
    for start in range(0, len(pts), 90):             # OSRM tager max 100 punkter
        del_ = pts if len(pts) <= 90 else sorted(set(pts[start:start + 90]))
        coords = ";".join(f"{p.split(',')[1]},{p.split(',')[0]}" for p in del_)
        try:
            d = hent_json(f"{OSRM}/table/v1/driving/{coords}?annotations=distance", pause=1.1)
            if d.get("code") != "Ok":
                raise RuntimeError(d.get("message") or d.get("code"))
            for i, a in enumerate(del_):
                for j, b in enumerate(del_):
                    v = d["distances"][i][j]
                    if i != j and v is not None:
                        af[f"{a}|{b}"] = round(v / 1000, 2)
        except Exception as exc:          # noqa: BLE001
            advar(f"Vejafstande kunne ikke hentes ({exc}). Manglende afstande er skønnet "
                  "som fugleflugt × 1,3.")
        if len(pts) <= 90:
            break


def afstand(a, b, cache):
    """(km, skønnet?) fra a til b."""
    if punkt(a) == punkt(b):
        return 0.0, False
    v = cache("afstande").get(f"{punkt(a)}|{punkt(b)}")
    if v is not None:
        return v, False
    return round(fugleflugt(a, b) * SKOEN_FAKTOR, 1), True


def side(g, laengdegrad):
    if g["lon"] > 14.6:
        return "bornholm"
    return "øst" if g["lon"] > laengdegrad else "vest"


def km_rettelser(kfg):
    """{(fra-nøgle, til-nøgle): km} fra config — begge retninger."""
    ud = {}
    for k, v in (kfg.get("km_rettelser") or {}).items():
        if k.startswith("_") or v is None or ">" not in k:
            continue
        dele = []
        for s in k.split(">", 1):
            m = re.match(r"\s*(.+?),\s*(\d{4})", s)
            dele.append(norm(f"{husnr(m.group(1))}, {m.group(2)}") if m else "navn:" + norm(s))
        ud[(dele[0], dele[1])] = ud[(dele[1], dele[0])] = float(v)
    return ud

# ------------------------------------------------------------------ fælles motor


class Kontekst:
    """Det, alle beregninger i en sæson deler."""

    def __init__(self, cache, kfg, takst, bro):
        self.cache, self.kfg, self.takst, self.bro = cache, kfg, takst, bro
        self.manuelle = {k: v for k, v in kfg.get("steder", {}).items() if not k.startswith("_")}
        self.lg = float(kfg.get("storebaelt_laengdegrad", 10.98))
        self.bornholm_pris = kfg.get("bornholm_pris_16_personer")
        self.rettelser = km_rettelser(kfg)
        self.reserve = {}                 # hold → hjemmebane fra grundspillet (reserve)
        self.startaar = None


def rejse(ktx, fra_k, til_k, biler, bropris):
    """(beløb, km, krydser Storebælt, skønnet) for én udekamp, eller None."""
    fra = geokod(fra_k, ktx.cache, ktx.manuelle)
    til = geokod(til_k, ktx.cache, ktx.manuelle)
    if not fra or not til:
        return None
    if fra_k["key"] == til_k["key"]:
        km, skoen = 0.0, False
    elif (fra_k["key"], til_k["key"]) in ktx.rettelser:
        km, skoen = ktx.rettelser[(fra_k["key"], til_k["key"])], False
    else:
        km, skoen = afstand(fra, til, ktx.cache)
    km = round(km)                                   # VD regner i hele km
    s_fra, s_til = side(fra, ktx.lg), side(til, ktx.lg)
    if "bornholm" in (s_fra, s_til) and s_fra != s_til:
        if ktx.bornholm_pris:
            return float(ktx.bornholm_pris), km, False, skoen
        advar("Der er en tur til/fra Bornholm. Den er regnet som almindelig kørsel — "
              "sæt \"bornholm_pris_16_personer\" i config.json.")
        return biler * 2 * km * ktx.takst, km, False, skoen
    krydser = s_fra != s_til
    return biler * (2 * km * ktx.takst + (bropris if krydser else 0)), km, krydser, skoen


def hjemmebaner_fra_kampe(kampe):
    """{hold: sted} — det spillested holdet oftest bruger til hjemmekampe."""
    taelling, info = {}, {}
    for k in sorted(kampe, key=lambda k: k["start"] or datetime.max.replace(tzinfo=UTC)):
        taelling.setdefault(k["hjemme"], Counter())[k["key"]] += 1
        info.setdefault(k["key"], k)
    return {h: info[c.most_common(1)[0][0]] for h, c in taelling.items()}


def beregn_pulje(navn, puljer, ktx, biler, klubnavne, metode="snit", hjem="kampe",
                 bropris=None, par_unik=False):
    """Fælles motor for alle tre slags udligning.

    puljer:  [(pulje_id, pulje_navn, kampe)] — regnes som én udligningspulje
    metode:  "snit"    udligning = udgift − samlet udgift / antal hold
             "pr_kamp" udligning = udgift − spillede kampe × (samlet / antal kampe) / 2
    hjem:    "kampe"       udeholdets hjemmebane = oftest brugte spillested i puljen
             "registreret" holdets registrerede spillested (pokal og slutspil)
    par_unik: kun den seneste kamp mellem to hold tæller (omkampe i pokalen)
    """
    bropris = ktx.bro if bropris is None else bropris
    hold, alle_kampe = {}, []

    def nyt(h, pnavn):
        return hold.setdefault(h, {"hold": h, "pulje": pnavn, "kampe": 0, "udekampe": 0,
                                   "km": 0, "bro": 0, "udgift": 0.0, "skoen": 0, "ture": [],
                                   "klub": h in klubnavne})

    for pid, pnavn, kampe in puljer:
        if par_unik:
            seneste = {}
            for k in sorted(kampe, key=lambda k: k["start"] or datetime.min.replace(tzinfo=UTC)):
                seneste[frozenset((k["hjemme"], k["ude"]))] = k
            kampe = list(seneste.values())
        lokale = hjemmebaner_fra_kampe(kampe)
        for h, k in lokale.items():
            ktx.reserve.setdefault(h, k)
        steder = {k["key"]: k for k in kampe}
        if hjem == "registreret":
            reg = {}
            try:
                reg = registrerede_spillesteder(pid, ktx.cache)
            except Exception as exc:      # noqa: BLE001 — reserven klarer det
                print(f"  holdoversigt for pulje {pid} fejlede: {exc}", file=sys.stderr)
            oprindelse = {}
            for k in kampe:
                for h in (k["hjemme"], k["ude"]):
                    if h in oprindelse:
                        continue
                    sted = None
                    if h in reg:
                        try:
                            adr = spillested_adresse(reg[h]["id"], ktx.cache)
                        except Exception:  # noqa: BLE001
                            adr = None
                        if adr:
                            sted = {"sted": reg[h]["navn"], **adr}
                            sted["key"] = sted_noegle(sted)
                    oprindelse[h] = sted or ktx.reserve.get(h) or lokale.get(h)
        else:
            oprindelse = lokale
        for s in oprindelse.values():
            if s:
                steder.setdefault(s["key"], s)
        geo = {key: geokod(s, ktx.cache, ktx.manuelle) for key, s in steder.items()}
        sikr_afstande([punkt(g) for g in geo.values() if g], ktx.cache)

        for k in kampe:
            nyt(k["hjemme"], pnavn)["kampe"] += 1
            h = nyt(k["ude"], pnavn)
            h["kampe"] += 1
            fra = oprindelse.get(k["ude"])
            r = rejse(ktx, fra, k, biler, bropris) if fra else None
            if r is None:
                h["mangler"] = h.get("mangler", 0) + 1
                continue
            beloeb, km, krydser, skoen = r
            h["udekampe"] += 1
            h["km"] += 2 * km
            h["bro"] += int(krydser)
            h["skoen"] += int(skoen)
            h["udgift"] += beloeb
            dato = k["start"].astimezone(DK).strftime("%d-%m-%Y") if k["start"] else ""
            alle_kampe.append({"dato": dato, "hjemme": k["hjemme"], "ude": k["ude"],
                               "sted": k["sted"], "km": km, "bro": krydser,
                               "beloeb": round(beloeb, 2)})
            if h["klub"]:
                h["ture"].append({"dato": dato, "modstander": k["hjemme"], "sted": k["sted"],
                                  "km": km, "bro": krydser, "skoen": skoen,
                                  "beloeb": round(beloeb, 2)})
        for k in kampe:                  # klubbens hjemmekampe (til pokal/slutspil)
            h = hold[k["hjemme"]]
            if h["klub"] and hjem == "registreret":
                h.setdefault("hjemmekampe", []).append(
                    {"dato": k["start"].astimezone(DK).strftime("%d-%m-%Y") if k["start"] else "",
                     "modstander": k["ude"], "sted": k["sted"]})

    # hold uden kendt hjemmebane: sæt udgiften til puljens median (sjældent)
    for h in hold.values():
        if h.get("mangler"):
            advar(f"{h['hold']} ({navn}): {h['mangler']} udekamp(e) kunne ikke placeres — "
                  "tallet er lidt usikkert.")
            if h["udekampe"] == 0:
                andre = sorted(x["udgift"] for x in hold.values()
                               if x["pulje"] == h["pulje"] and not x.get("mangler"))
                if andre:
                    h["udgift"] = andre[len(andre) // 2]

    n = len(hold)
    total = sum(h["udgift"] for h in hold.values())
    antal_kampe = sum(h["kampe"] for h in hold.values()) / 2
    snit = total / n if n else 0.0
    pris = total / antal_kampe if antal_kampe else 0.0
    for h in hold.values():
        andel = h["kampe"] * pris / 2 if metode == "pr_kamp" else snit
        h["andel"] = round(andel, 2)
        h["udligning"] = round(h["udgift"] - andel, 2)
        h["udgift"] = round(h["udgift"], 2)
        h["ture"].sort(key=lambda t: t["dato"][6:] + t["dato"][3:5] + t["dato"][:2])
    return {"raekke": navn, "biler": biler, "takst": ktx.takst, "bro": bropris,
            "puljer": [p[1] for p in puljer], "antal_hold": n,
            "antal_kampe": int(antal_kampe), "gennemsnit": round(snit, 2),
            "pris_pr_kamp": round(pris, 2), "total": round(total, 2), "metode": metode,
            "kampe": sorted(alle_kampe, key=lambda t: t["dato"][6:] + t["dato"][3:5] + t["dato"][:2]),
            "hold": sorted(hold.values(), key=lambda h: -h["udligning"])}

# ------------------------------------------------------------------ grundspil


def aarsvaerdi(tabel, aar, navn, stille=False):
    vals = {int(k): v for k, v in (tabel or {}).items() if str(k).isdigit() and v is not None}
    if aar in vals:
        return vals[aar]
    if not vals:
        raise RuntimeError(f"{navn} mangler helt i config.json")
    brug = max([a for a in vals if a <= aar] or [min(vals)])
    if not stille:
        advar(f"{navn} for {aar} mangler i config.json — bruger {brug}-værdien "
              f"({str(vals[brug]).replace('.', ',')}). Ret config.json, når den nye er kendt.")
    return vals[brug]


def raekke_navn(linje1, kfg):
    """'1. Division Herrer Vest' → '1. Division Herrer' (længste nøgle i config)."""
    kandidater = [k for k in kfg["biler_pr_raekke"] if not k.startswith("_")
                  and norm(linje1).startswith(norm(k))]
    return max(kandidater, key=len) if kandidater else None


def saeson_af(datoer):
    d = min(datoer).astimezone(DK)
    start = d.year if d.month >= 7 else d.year - 1
    return start, f"{start}/{str(start + 1)[2:]}"


def hent_raekke(raekke_id, cache):
    """[(pulje_id, pulje_navn, kampe)] for alle puljer i rækken."""
    ud = []
    for pid, pnavn in puljer_i_raekke(raekke_id):
        kampe = kampe_i_pulje(pid, cache)
        if not pnavn:
            l1 = kampe[0]["linje1"]
            pnavn = l1.split()[-1] if l1 else str(pid)
        ud.append((pid, pnavn, kampe))
    if not ud:
        raise RuntimeError(f"ingen puljer fundet i række {raekke_id}")
    return ud


def niveau(raekke):
    r = raekke.lower()
    grad = 0 if "liga" in r else 1 if r.startswith("1.") else 2 if r.startswith("2.") else 3
    return (grad, "herrer" in r)


def klubregex(kfg):
    return re.compile(re.escape(kfg.get("klub", "Aalborg Volleyball")) + r"(\s?\.?\s?\d+)?")


def klub_i(kampe, kfg, kendte=()):
    rx = klubregex(kfg)
    alle = {k[f] for k in kampe for f in ("hjemme", "ude")}
    return {h for h in alle if rx.fullmatch(h)} | set(kendte)


def beregn_grundspil(raekke_ids, cache, kfg, klubnavne=None, stille=False):
    """Regner alle grundspilsrækker i listen og returnerer (resultat, kontekst)."""
    data, datoer = [], []
    for rid in raekke_ids:
        puljer = hent_raekke(rid, cache)
        l1 = puljer[0][2][0]["linje1"]
        navn = raekke_navn(l1, kfg)
        if not navn:
            advar(f"Rækken \"{l1}\" (id {rid}) er ikke med i biler_pr_raekke i config.json "
                  "og springes over.")
            continue
        datoer += [k["start"] for _, _, ks in puljer for k in ks if k["start"]]
        data.append((rid, navn, puljer))
    if not data:
        raise RuntimeError("ingen rækker at regne på")
    start, saeson = saeson_af(datoer)
    takst = aarsvaerdi(kfg["km_takst"], start, "Km-taksten", stille)
    bro = aarsvaerdi(kfg["bropris"], start, "Broprisen", stille)
    ktx = Kontekst(cache, kfg, takst, bro)
    ktx.startaar = start
    raekker = []
    for rid, navn, puljer in sorted(data, key=lambda x: niveau(x[1])):
        biler = int(kfg["biler_pr_raekke"][navn])
        navne = klub_i([k for _, _, ks in puljer for k in ks], kfg, (klubnavne or {}).get(navn, ()))
        r = beregn_pulje(navn, puljer, ktx, biler, navne)
        r["raekke_id"] = rid
        r["sidste_kamp"] = max((k["start"] for _, _, ks in puljer for k in ks if k["start"]),
                               default=None)
        raekker.append(r)
    return {"saeson": saeson, "startaar": start, "takst": takst, "bro": bro,
            "raekker": raekker}, ktx


def klubhold_liste(resultat, kfg):
    """Klubbens hold med koder (D1, H1 ...). D1/H1 = holdet i den bedste række."""
    koder = {k: v for k, v in kfg.get("hold_koder", {}).items() if not k.startswith("_")}
    ud = []
    for r in resultat["raekker"]:
        for h in r["hold"]:
            if h["klub"]:
                ud.append({**{k: v for k, v in h.items() if k not in ("klub", "hjemmekampe")},
                           "raekke": r["raekke"], "gennemsnit": r["gennemsnit"],
                           "biler": r["biler"]})

    def suffiks(navn):
        m = re.search(r"(\d+)\s*$", navn)
        return int(m.group(1)) if m else 1

    ud.sort(key=lambda h: (niveau(h["raekke"]), suffiks(h["hold"])))
    tael = Counter()
    for h in ud:
        koen = "H" if "herrer" in h["raekke"].lower() else "D"
        tael[koen] += 1
        h["kode"] = koder.get(f"{h['raekke']}|{h['hold']}") or f"{koen}{tael[koen]}"
    return sorted(ud, key=lambda h: (h["kode"][0], int(h["kode"][1:] or 0)
                                     if h["kode"][1:].isdigit() else 99))


def kode_for(hold, raekke, klubhold):
    """Holdkode (D1, H2 ...) for et klubhold i pokal/slutspil ud fra køn + holdnavn."""
    koen = "H" if "herrer" in raekke.lower() else "D"
    for h in klubhold:
        if h["hold"] == hold and h["kode"].startswith(koen):
            return h["kode"]
    return ""

# ------------------------------------------------------------------ pokal og slutspil


def pokal_kfg(kfg):
    p = kfg.get("pokal") or {}
    return {"prefiks": p.get("raekke_prefiks", "Pokalturneringen"),
            "biler": int(p.get("biler", 3)),
            "undtag": [u.lower() for u in p.get("undtag", ["final4", "final 4", "final four"])]}


def er_pokal(navn, kfg):
    p = pokal_kfg(kfg)
    return (norm(navn).startswith(norm(p["prefiks"]))
            and not any(u in navn.lower() for u in p["undtag"]))


def beregn_pokalrunde(rid, navn, ktx, klubnavne, pulje_ids=None):
    p = pokal_kfg(ktx.kfg)
    if pulje_ids is None:
        puljer = hent_raekke(rid, ktx.cache)
    else:
        puljer = [(pid, "", kampe_i_pulje(pid, ktx.cache)) for pid in pulje_ids]
    navn = navn or re.sub(r"\s+Pokal .*$", "", puljer[0][2][0]["linje1"]) or f"Runde {rid}"
    tabel = ktx.kfg.get("bropris_pokal") or {}
    if not any(str(k).isdigit() and v is not None for k, v in tabel.items()):
        tabel = ktx.kfg["bropris"]              # tom = samme som grundspillet
    bropris = aarsvaerdi(tabel, ktx.startaar, "Broprisen (pokal)", True)
    navne = klub_i([k for _, _, ks in puljer for k in ks], ktx.kfg, klubnavne)
    r = beregn_pulje(navn, puljer, ktx, p["biler"], navne, metode="snit",
                     hjem="registreret", bropris=bropris, par_unik=True)
    r["raekke_id"] = rid
    r["foerste_dato"] = min((k["start"] for _, _, ks in puljer for k in ks if k["start"]),
                            default=None)
    return r


def slutspil_undtag(kfg):
    return [u.lower() for u in (kfg.get("slutspil") or {}).get("undtag", ["kvalifikation"])]


def slutspils_raekker(liga, cache, kfg):
    """Alle slutspils- og placeringsrækker i Volleyligaen for samme køn som `liga`
    (et grundspilsresultat). Findes via foreningssiderne for alle ligaens klubber."""
    undtag = slutspil_undtag(kfg)
    foreninger = {kfg["forening_id"]}
    for pid in puljer_i_raekke(liga["raekke_id"]):
        for hid, _navn in hold_i_pulje(pid[0]):
            try:
                fid = forening_for_hold(hid, cache)
            except Exception:             # noqa: BLE001
                fid = None
            if fid:
                foreninger.add(fid)
    fundet = {}
    for fid in sorted(foreninger):
        try:
            rows = klubbens_hold(fid)
        except Exception as exc:          # noqa: BLE001
            print(f"  foreningsside {fid} fejlede: {exc}", file=sys.stderr)
            continue
        for h in rows:
            n = h["raekke"]
            if (norm(n).startswith(norm(liga["raekke"])) and norm(n) != norm(liga["raekke"])
                    and not any(u in n.lower() for u in undtag)):
                fundet[h["raekke_id"]] = n
    return fundet


def beregn_slutspil(liga, ktx, klubnavne):
    """Øvrige kampe i Volleyligaen for ét køn, samlet i én pulje."""
    raekker = slutspils_raekker(liga, ktx.cache, ktx.kfg)
    puljer, med = [], []
    for rid, navn in sorted(raekker.items()):
        try:
            for pid, pnavn, kampe in hent_raekke(rid, ktx.cache):
                puljer.append((pid, navn, kampe))
            med.append(navn)
        except IngenKampe:
            continue
    if not puljer:
        return None
    biler = int((ktx.kfg.get("slutspil") or {}).get("biler", 3))
    navne = klub_i([k for _, _, ks in puljer for k in ks], ktx.kfg, klubnavne)
    r = beregn_pulje(f"Slutspil — {liga['raekke']}", puljer, ktx, biler, navne,
                     metode="pr_kamp", hjem="registreret")
    r["raekker"] = med
    return r

# ------------------------------------------------------------------ kalibrering


def kalibrer(cache, kfg):
    """Regner tidligere sæsoner og sammenligner med de faktiske beløb fra VD."""
    gemt = cache("kalibrering")
    ud = []
    for post in kfg.get("kalibrering", []):
        noegle = json.dumps(post, sort_keys=True) + json.dumps(
            [kfg.get("km_takst"), kfg.get("bropris"), kfg.get("bropris_pokal"),
             kfg.get("biler_pr_raekke"), kfg.get("pokal"), kfg.get("km_rettelser")],
            sort_keys=True)
        if noegle in gemt and os.environ.get("FORNY_KALIBRERING") != "1":
            ud.append(gemt[noegle])
            continue
        try:
            model, navne = {}, {}
            if post.get("type") == "pokal":
                runder = []
                for gruppe in post["runder"]:
                    kampe = kampe_i_pulje(gruppe[0], cache)
                    start, _ = saeson_af([k["start"] for k in kampe if k["start"]])
                    ktx = Kontekst(cache, kfg, aarsvaerdi(kfg["km_takst"], start, "", True),
                                   aarsvaerdi(kfg["bropris"], start, "", True))
                    ktx.startaar = start
                    r = beregn_pokalrunde(None, "", ktx, (), pulje_ids=gruppe)
                    runder.append(r)
                    navne[str(gruppe[0])] = r["raekke"]
                    for h in r["hold"]:
                        model[f"{gruppe[0]}|{h['hold']}"] = h["udligning"]
                takst, bro = runder[0]["takst"], runder[0]["bro"]
            else:
                res, _ktx = beregn_grundspil(post["raekke_ids"], cache, kfg, stille=True)
                takst, bro = res["takst"], res["bro"]
                for r in res["raekker"]:
                    for h in r["hold"]:
                        model[f"{r['raekke']}|{h['hold']}"] = h["udligning"]
            linjer = []
            for k, faktisk in post["faktisk"].items():
                m = model.get(k)
                del_ = k.split("|", 1)
                vis = f"{navne.get(del_[0], del_[0])}|{del_[1]}" if len(del_) == 2 else k
                linjer.append({"noegle": vis, "faktisk": faktisk, "model": m,
                               "afvigelse": None if m is None else round(m - faktisk, 2)})
            post_ud = {"saeson": post["saeson"], "kilde": post.get("kilde", ""),
                       "type": post.get("type", "grundspil"),
                       "linjer": linjer, "takst": takst, "bro": bro,
                       "model_total": round(sum(l["model"] or 0 for l in linjer), 2),
                       "faktisk_total": round(sum(l["faktisk"] for l in linjer), 2)}
            gemt[noegle] = post_ud
            ud.append(post_ud)
        except Exception as exc:          # noqa: BLE001
            advar(f"Kontrollen mod {post.get('saeson')} kunne ikke regnes: {exc}")
    return ud

# ------------------------------------------------------------------ hovedprogram


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ud", default=os.path.join(ROOT, "docs"),
                    help="mappe til index.html og status.json")
    ap.add_argument("--cache", default=os.path.join(ROOT, "cache"))
    ap.add_argument("--nu", default=None, help="kun til test: dato som ÅÅÅÅ-MM-DD")
    args = ap.parse_args()

    kfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    cache = Cache(args.cache)
    nu = (datetime.fromisoformat(args.nu).replace(tzinfo=DK) if args.nu
          else datetime.now(UTC).astimezone(DK))
    os.makedirs(args.ud, exist_ok=True)

    status = None
    try:
        hold = klubbens_hold(kfg["forening_id"])
        grund, klubnavne, pokal, slut_egne = {}, {}, {}, {}
        for h in hold:
            navn = raekke_navn(h["raekke"], kfg)
            if navn and norm(navn) == norm(h["raekke"]):   # ikke "kvalifikation" o.l.
                grund[h["raekke_id"]] = navn
                klubnavne.setdefault(navn, set()).add(h["hold"])
            elif er_pokal(h["raekke"], kfg):
                pokal.setdefault(h["raekke_id"], {"navn": h["raekke"], "hold": set()})
                pokal[h["raekke_id"]]["hold"].add(h["hold"])
            elif (norm(h["raekke"]).startswith("volleyligaen")
                  and not any(u in h["raekke"].lower() for u in slutspil_undtag(kfg))):
                slut_egne.setdefault(h["raekke_id"], h["raekke"])
        if not grund:
            raise RuntimeError("fandt ingen af klubbens hold i Liga, 1. eller 2. division "
                               f"på foreningssiden (ForeningsId {kfg['forening_id']})")
        print(f"Klubbens hold i grundspillet: {sum(len(v) for v in klubnavne.values())} "
              f"i {len(grund)} rækker · pokalrunder: {len(pokal)}")
        res, ktx = beregn_grundspil(list(grund), cache, kfg, klubnavne=klubnavne)
        klubhold = klubhold_liste(res, kfg)
        grundspil = round(sum(h["udligning"] for h in klubhold), 2)

        # ---- pokal: hver runde for sig
        runder = []
        for rid, info in sorted(pokal.items()):
            try:
                r = beregn_pokalrunde(rid, info["navn"], ktx, info["hold"])
                r["status"] = "beregnet"
            except IngenKampe:
                r = {"raekke": info["navn"], "raekke_id": rid, "status": "ikke trukket",
                     "hold": [], "kampe": []}
            except Exception as exc:      # noqa: BLE001
                advar(f"{info['navn']} kunne ikke regnes: {exc}")
                continue
            for h in r["hold"]:
                if h["klub"]:
                    h["kode"] = kode_for(h["hold"], r["raekke"], klubhold)
            runder.append(r)
        runder.sort(key=lambda r: (r.get("foerste_dato") or datetime.max.replace(tzinfo=UTC),
                                   r["raekke"]))
        pokal_total = round(sum(h["udligning"] for r in runder for h in r["hold"]
                                if h["klub"]), 2)

        # ---- slutspil i Volleyligaen (øvrige kampe)
        slutspil = []
        for r in res["raekker"]:
            if not r["raekke"].lower().startswith("volleyligaen"):
                continue
            egne = any(norm(n).startswith(norm(r["raekke"])) for n in slut_egne.values())
            sidste = r.get("sidste_kamp")
            naer_slut = sidste and nu >= sidste.astimezone(DK) - timedelta(days=SLUTSPIL_DAGE_FOER)
            if not (egne or naer_slut):
                continue
            try:
                s = beregn_slutspil(r, ktx, klubnavne.get(r["raekke"], ()))
            except Exception as exc:      # noqa: BLE001
                advar(f"Slutspillet i {r['raekke']} kunne ikke regnes: {exc}")
                continue
            if s:
                for h in s["hold"]:
                    if h["klub"]:
                        h["kode"] = kode_for(h["hold"], r["raekke"], klubhold)
                slutspil.append(s)
        slutspil_total = round(sum(h["udligning"] for s in slutspil for h in s["hold"]
                                   if h["klub"]), 2)

        total = round(grundspil + pokal_total + slutspil_total, 2)
        historik = cache("historik")
        historik[res["saeson"]] = {"total": total, "grundspil": grundspil,
                                   "pokal": pokal_total, "slutspil": slutspil_total,
                                   "beregnet": nu.strftime("%d-%m-%Y"),
                                   "hold": {h["kode"]: h["udligning"] for h in klubhold}}

        def let(r):   # uden alle holdenes ture (siden viser kun klubbens)
            return {**{k: v for k, v in r.items() if k not in ("sidste_kamp", "foerste_dato")},
                    "hold": [{k: v for k, v in h.items() if k != "ture" or h["klub"]}
                             for h in r["hold"]]}

        status = {
            "opdateret": nu.strftime("%d-%m-%Y %H:%M"),
            "saeson": res["saeson"], "startaar": res["startaar"],
            "klub": kfg.get("klub"), "total": total, "grundspil": grundspil,
            "pokal_total": pokal_total, "slutspil_total": slutspil_total,
            "klubhold": klubhold,
            "raekker": [{**let(r), "kampe": []} for r in res["raekker"]],
            "pokal": [let(r) for r in runder],
            "slutspil": [let(s) for s in slutspil],
            "takst": res["takst"], "bro": res["bro"],
            "faktisk": {k: v for k, v in kfg.get("faktisk", {}).items()
                        if not k.startswith("_")},
            "historik": historik,
            "fejl": None,
        }
        cache("sidste").clear()
        cache("sidste").update(json.loads(json.dumps(status, default=str)))
    except Exception as exc:              # noqa: BLE001 — vis sidste gode tal
        traceback.print_exc()
        sidste = dict(cache("sidste"))
        if isinstance(exc, IngenKampe):
            grund_ = "Kampprogrammet for den nye sæson er ikke lagt ud endnu."
        else:
            grund_ = f"Nattens opdatering fejlede ({exc})."
        if sidste:
            status = {**sidste, "fejl": f"{grund_} Siden viser beregningen fra "
                                        f"{sidste.get('opdateret')}."}
        else:
            status = {"opdateret": nu.strftime("%d-%m-%Y %H:%M"), "saeson": "",
                      "klubhold": [], "raekker": [], "pokal": [], "slutspil": [],
                      "total": None, "historik": {}, "faktisk": {}, "fejl": grund_}

    status["kalibrering"] = kalibrer(cache, kfg)
    status["advarsler"] = list(ADVARSLER)
    cache.gem()

    json.dump(status, open(os.path.join(args.ud, "status.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render import render
    open(os.path.join(args.ud, "index.html"), "w", encoding="utf-8").write(render(status))

    if status.get("total") is not None:
        print(f"Kørselsudligning {status['saeson']}: {status['total']:+,.0f} kr "
              f"(grundspil {status.get('grundspil', 0):+,.0f} · pokal "
              f"{status.get('pokal_total', 0):+,.0f} · slutspil "
              f"{status.get('slutspil_total', 0):+,.0f})")
        for h in status["klubhold"]:
            print(f"  {h['kode']:3} {h['raekke']:22} {h['hold']:22} {h['udligning']:+10,.0f} kr")
    for adv in ADVARSLER:
        print("  advarsel:", adv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
