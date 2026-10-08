#!/usr/bin/env python3
# sti: koerselsudligning/test/test_beregn.py
"""Offline-test af hele kæden uden netværk.

fixtures.json indeholder rigtige puljer, spillesteder (koordinater) og
vejafstande (OSRM) for 2024/25, 2025/26 og 2026/27. Testen bygger sider og
kalenderfeeds i volleyball.dk's format ud fra dem (plus pokalrunder og et
slutspil), kører beregn.py mod en falsk `hent` og tjekker resultatet mod
håndberegnede tal, en uafhængig genberegning og VD's kreditnotaer.
Den ene pokalrunde har en pulje, hvor ingen kampe har fået dato endnu, og en
kamp uden dato i en anden pulje — resten af runden skal regnes alligevel.

Kør:  python koerselsudligning/test/test_beregn.py
"""
import json, os, re, shutil, sys, tempfile, urllib.parse
from datetime import datetime, timedelta, timezone

HER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HER, "..", "scripts"))
import beregn  # noqa: E402

FX = json.load(open(os.path.join(HER, "fixtures.json"), encoding="utf-8"))
KLUB = "Aalborg Volleyball"
# Talentpuljer (fra 2026/27): VD's talenthold spiller hjemme i Ikast mod 2. divisionsholdene, der
# står med "(T)" efter navnet. VD (okt. 2026): kampene er med i den almindelige kørselsudligning som
# helt normale kampe — (T)-holdet er det almindelige hold (samme kode), og turen til Ikast er en
# udekamp mere i rækken. Talentholdet selv er ikke med i snittet (kan slås til i config.json).
# Som i virkeligheden ligger én kamp i "Hyldgårdsskolens Sal", hvor VD har stavet adressen forkert —
# den skal regnes som Hyldgårdsskolen (samme_sted i config.json).
FX["steder"]["Hyldgårdsskolens Sal"] = {**FX["steder"]["Hyldgårdsskolens Hal"],
                                       "adr": "Hyldsgårdsalle 9, 7430 Ikast", "ukendt": True}
TALENT = {"2372": (4303, [("Aalborg Volleyball.2 (T)", "2026-12-18", "Hyldgårdsskolens Sal"),
                          ("VK Vendsyssel (T)", "2027-01-17"),
                          ("Aalborg Volleyball.3 (T)", "2027-03-24")]),
          "2374": (4302, [("Aalborg Volleyball.3 (T)", "2026-11-25"), ("Randers VK (T)", "2027-02-10")])}
for _rid, (_pid, _kampe) in TALENT.items():
    FX["saesoner"]["2026/27"]["raekker"][_rid]["puljer"][str(_pid)] = {
        "navn": "Talent", "hold": {"Talenthold": "Hyldgårdsskolens Hal", **{k[0]: None for k in _kampe}},
        "kampe": [("Talenthold", *k) for k in _kampe]}
# Vendsyssel → Hyldgårdsskolen mangler i fixtures (skøn: fugleflugt 140,8 km × 1,12)
_a, _h = FX["steder"]["Toftegårdshallen"], FX["steder"]["Hyldgårdsskolens Hal"]
_ka, _kh = f"{_a['lat']:.5f},{_a['lon']:.5f}", f"{_h['lat']:.5f},{_h['lon']:.5f}"
FX["afstande"][f"{_ka}|{_kh}"] = FX["afstande"][f"{_kh}|{_ka}"] = 157700.0
SID = {navn: 5000 + i for i, navn in enumerate(sorted(FX["steder"]))}   # SpillestedsId
SID_NAVN = {v: k for k, v in SID.items()}

# Pokalrunde (pulje Vest) og slutspil — kampe mellem steder med kendte afstande
POKAL = {
    2390: {"navn": "Pokalturneringen Herrer 2. runde", "puljer": {4154: {"navn": "Vest", "kampe": [
        ("Kolding VK.2", "Aalborg Volleyball", "2026-10-21"),
        ("Randers VK", "Aalborg Volleyball.2", "2026-10-22"),
        ("Aalborg Volleyball.3", "Bedsted KFUM", "2026-10-23"),
        ("Nordenskov UIF.2", "ASV Aarhus.2", "2026-10-24"),
        ("IF Lyseng", "DHV Odense", "2026-10-10"),        # annulleret — spillet om
        ("IF Lyseng", "DHV Odense", "2026-10-24"),
        ("VK Raptus", "Ikast KFUM.2", "2026-10-25")]}}},
    2393: {"navn": "Pokalturneringen Kvinder 1. runde", "puljer": {4147: {"navn": "Vest",
                                                                            "kampe": []}}},
    # Som 3. runde 26/27: "På tværs" har kun en kamp uden dato (= tom kalender), og i Vest
    # mangler én kamp dato. Kampe uden dato er ikke i kalenderen, men holdene står i puljen.
    2427: {"navn": "Pokalturneringen Kvinder 3. runde", "puljer": {
        4192: {"navn": "Øst", "kampe": [
            ("Amager Volley.2", "Team Køge", "2026-10-06"),
            ("Gentofte Volley.2", "Hvidovre VK", "2026-10-06"),
            ("VLI.2", "VLI", "2026-10-14")]},
        4193: {"navn": "Vest", "kampe": [
            ("ASV Aarhus.2", "Aalborg Volleyball.2", "2026-10-07"),
            ("IF Lyseng", "Volleyball Esbjerg", "2026-10-08"),
            ("SIK Viborg", "Bedsted KFUM", "2026-10-11")],
               "uden_dato": [("Odense Volleyball", "DSIO Odense")]},
        4194: {"navn": "På tværs", "kampe": [], "uden_dato": [("Ikast KFUM.2", "KSV")]}}},
}
SLUTSPIL = {
    2400: {"navn": "Volleyligaen Kvinder Kvartfinaler", "puljer": {4200: {"navn": "Kvart", "kampe": [
        ("Brøndby VK", "Ikast KFUM", "2027-03-01"), ("Ikast KFUM", "Brøndby VK", "2027-03-05"),
        ("Brøndby VK", "Ikast KFUM", "2027-03-08"), ("Gentofte Volley", "DHV Odense", "2027-03-01"),
        ("DHV Odense", "Gentofte Volley", "2027-03-05")]}}},
    2401: {"navn": "Volleyligaen Kvinder 7-9. plads", "puljer": {4201: {"navn": "7-9", "kampe": [
        ("Farum VK", KLUB, "2027-03-07"), (KLUB, "Team Køge", "2027-03-14"),
        ("Team Køge", "Farum VK", "2027-03-21"), (KLUB, "Farum VK", "2027-03-28"),
        ("Team Køge", KLUB, "2027-04-04"), ("Farum VK", "Team Køge", "2027-04-11")]}}},
    2402: {"navn": "Volleyligaen Kvinder kvalifikation", "puljer": {4202: {"navn": "Kval", "kampe": [
        ("Holte IF", "Hvidovre VK", "2027-04-20")]}}},
}
VIS_SLUTSPIL = {"ja": False}


def hjem_for(hold):
    """Registreret hjemmebane: fra grundspillet i fixtures, ellers klubbens."""
    for s in FX["saesoner"].values():
        for r in s["raekker"].values():
            for p in r["puljer"].values():
                if hold in p["hold"]:
                    return p["hold"][hold]
    base = re.sub(r"[ .]?\d+$", "", hold)
    return hjem_for(base) if base != hold else None


def klub_af(hold):
    return re.sub(r"[ .]?\d+$", "", re.sub(r"\s*\(T\)$", "", hold))


FID = {}


def forening_id(klub):
    return 156 if klub == KLUB else FID.setdefault(klub, 900 + len(FID))


HID = {}


def hold_id(hold):
    return HID.setdefault(hold, 30000 + len(HID))


def adr_dele(sted):
    adr = re.sub(r"\s*\(.*?\)", "", FX["steder"][sted]["adr"])
    gade, postby = adr.rsplit(", ", 1)
    return gade, postby


def raekke(rid):
    for s in FX["saesoner"].values():
        if str(rid) in s["raekker"]:
            return s["raekker"][str(rid)]
    for tabel in (POKAL, SLUTSPIL):
        if int(rid) in tabel:
            r = tabel[int(rid)]
            return {"navn": r["navn"], "puljer": {str(k): v for k, v in r["puljer"].items()}}
    return None


def pulje(pid):
    for s in FX["saesoner"].values():
        for r in s["raekker"].values():
            if str(pid) in r["puljer"]:
                return s, r, r["puljer"][str(pid)]
    for tabel in (POKAL, SLUTSPIL):
        for r in tabel.values():
            if int(pid) in r["puljer"]:
                return None, r, r["puljer"][int(pid)]
    return None, None, None

# ------------------------------------------------------------------ falske sider


def raekke_html(hold, pid, rid, rnavn, pnavn):
    return (f'<tr><td><a href="Hold-Information.aspx?PuljeId={pid}&amp;HoldId={hold_id(hold)}">'
            f'{hold}</a></td><td><a href="Pulje-Oversigt.aspx?RaekkeId={rid}">{rnavn}</a></td>'
            f'<td><a href="Pulje-Holdoversigt.aspx?PuljeId={pid}">{pnavn}</a></td></tr>')


def side_forening(fid):
    rows = []
    s = FX["saesoner"]["2026/27"]
    for rid, r in s["raekker"].items():
        for pid, p in r["puljer"].items():
            for hold in p["hold"]:
                if forening_id(klub_af(hold)) == fid:
                    rows.append(raekke_html(hold, pid, rid, r["navn"], p["navn"]))
    tabeller = [POKAL] + ([SLUTSPIL] if VIS_SLUTSPIL["ja"] else [])
    for tabel in tabeller:
        for rid, r in tabel.items():
            for pid, p in r["puljer"].items():
                hold = {x for k in p["kampe"] + p.get("uden_dato", []) for x in k[:2]}
                if tabel is POKAL and rid == 2393 and fid == 156:
                    hold = {"Aalborg Volleyball.2"}
                for h in sorted(hold):
                    if forening_id(klub_af(h)) == fid:
                        rows.append(raekke_html(h, pid, rid, r["navn"], p["navn"]))
    if fid == 156:                                # rækker der IKKE er med
        rows.append(raekke_html("Aalborg Volleyball.4", 4144, 2387, "Danmarksserien Nord",
                                "Pulje 1"))
        rows.append(raekke_html(KLUB, 9998, 9999, "Volleyligaen Kvinder kvalifikation", "Øst"))
    return ('<html><body><table class="grid"><tr><th>Hold</th><th>Række</th><th>Pulje</th></tr>'
            + "".join(rows) + "</table></body></html>")


def side_pulje_oversigt(rid):
    r = raekke(rid)
    if r is None:
        return "<html><body>Rækken findes ikke</body></html>"
    if len(r["puljer"]) == 1:                    # én pulje: siden viser puljen direkte
        pid, p = next(iter(r["puljer"].items()))
        links = "".join(f'<a href="https://resultater.volleyball.dk/tms/Turneringer-og-resultater/'
                        f'{x}.aspx?PuljeId={pid}">{t}</a> ' for x, t in
                        (("Pulje-Stilling", "Stilling"), ("Pulje-Kampprogram", "Kampprogram"),
                         ("Pulje-Komplet-Kampprogram", "Komplet kampprogram"),
                         ("Pulje-Holdoversigt", "Holdoversigt")))
        return f"<html><body>{links}</body></html>"
    links = "".join(f'<tr><td><a href="Pulje-Stilling.aspx?PuljeId={pid}">{p["navn"]}</a></td></tr>'
                    for pid, p in r["puljer"].items())
    return f"<html><body><h1>{r['navn']}</h1><table>{links}</table></body></html>"


def side_komplet(pid):
    return (f'<html><body><a href="webcal://resultater.volleyball.dk/cal/Puljekampprogram.ashx?'
            f'key=00000000-0000-0000-0000-{int(pid):012d}">Abonnér</a><table></table></body></html>')


def hold_liste(pid):
    s, r, p = pulje(pid)
    if "hold" in p:
        return list(p["hold"])
    return sorted({x for k in p["kampe"] + p.get("uden_dato", []) for x in k[:2]})


def side_holdoversigt(pid):
    rows = []
    for h in hold_liste(pid):
        sted = hjem_for(h)
        rows.append(f'<tr><td><a href="https://resultater.volleyball.dk/tms/Turneringer-og-resultater/'
                    f'Hold-Information.aspx?HoldId={hold_id(h)}">{h}</a></td>'
                    f'<td><a href="Spillested-Information.aspx?SpillestedsId={SID[sted]}">{sted}</a></td>'
                    f'<td>Rød</td><td>Sort</td></tr>')
    return ("<html><body><table><tr><th>Hold</th><th>Spillested</th><th></th><th></th></tr>"
            + "".join(rows) + "</table></body></html>")


def side_spillested(sid):
    gade, postby = adr_dele(SID_NAVN[sid])
    return (f"<html><body><h1>{SID_NAVN[sid]} (5019)</h1><table>"
            f"<tr><td>Forbund/kreds</td><td>Volleyball Danmark</td></tr>"
            f"<tr><td>Adresse</td><td>{gade}<br />{postby}<br />Danmark</td></tr>"
            f"<tr><td>Telefon</td><td>Ikke angivet</td></tr></table></body></html>")


def side_hold_info(hid):
    hold = next(h for h, i in HID.items() if i == hid)
    return (f'<html><body><a href="Forening-Information.aspx?ForeningsId='
            f'{forening_id(klub_af(hold))}">{klub_af(hold)}</a></body></html>')


def ics_event(nr, raekke_navn, pnavn, h, u, sted, dato):
    gade, postby = adr_dele(sted)
    titel = f"{h} - {u}" + (" 3 - 1" if nr % 3 == 0 else "")   # spillede kampe: resultat i titlen
    desc = (f"{raekke_navn} {pnavn}\\nRunde 1\\nKampnr {nr}\\n\\n{titel}\\n{sted}\\n"
            f"{gade.replace(' ', '  ', 1) if nr % 7 == 0 else gade}\\n{postby}\\n"
            f"{dato.strftime('%d-%m-%Y %H:%M')}")
    return "\r\n".join([
        "BEGIN:VEVENT", "PRODID:-//DBU//DA", f"UID:item_{nr}",
        f"DTSTART:{dato.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{(dato + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{titel}", f"DESCRIPTION:{desc}", f"LOCATION:{sted}",
        "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", "DESCRIPTION:Reminder",
        "END:VALARM", "END:VEVENT"])


def ics(pid):
    s, r, p = pulje(pid)
    ev, nr = [], 100000 + int(pid) * 100
    if "kampe" in p:                             # pokal/slutspil/talent: givne kampe
        for h, u, d, *sted in p["kampe"]:
            nr += 1
            ev.append(ics_event(nr, r["navn"], p["navn"], h, u, sted[0] if sted else hjem_for(h),
                                datetime.fromisoformat(d).replace(hour=18, tzinfo=timezone.utc)))
    else:                                        # grundspil: dobbeltturnering
        hold = list(p["hold"])
        start = datetime.fromisoformat(s["start"]).replace(hour=12, tzinfo=timezone.utc)
        for i, h in enumerate(hold):
            for j, u in enumerate(hold):
                if i == j:
                    continue
                nr += 1
                dato = start + timedelta(days=7 * ((i + j + (i > j) * 9) % 18))
                ev.append(ics_event(nr, r["navn"], p["navn"], h, u, p["hold"][h], dato))
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:VD\r\n" + "\r\n".join(ev)
            + "\r\nEND:VCALENDAR\r\n")


def nominatim(url):
    """Falsk OpenStreetMap: finder adressen blandt spillestederne i fixtures. Søgning på
    spillestedets navn eller kun postnummer giver intet – så slår en ukendt adresse fejl."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    if "street" not in q:
        return "[]"
    gade, postnr = beregn.norm(beregn.husnr(q["street"])), q.get("postalcode", "")
    for navn, s in FX["steder"].items():
        if s.get("ukendt"):
            continue
        g, pb = adr_dele(navn)
        g = re.sub(r"(\d+)\s+([A-Za-z])\b", r"\1\2", g)
        if pb.startswith(postnr) and beregn.norm(g) == gade:
            return json.dumps([{"lat": str(s["lat"]), "lon": str(s["lon"]), "display_name": s["adr"]}])
    return "[]"


def osrm(coords):
    pts = [(float(c.split(",")[1]), float(c.split(",")[0])) for c in coords.split(";")]
    keys = [f"{la:.5f},{lo:.5f}" for la, lo in pts]
    mat = [[0 if a == b else FX["afstande"].get(f"{a}|{b}") for b in keys] for a in keys]
    return json.dumps({"code": "Ok", "distances": mat})


NET = {"slaa_fra": set(), "kald": [], "tom_kalender": False}


def falsk_hent(url, accept="*/*", pause=0.0, forsoeg=3):
    NET["kald"].append(url)
    for del_ in NET["slaa_fra"]:
        if del_ in url:
            raise RuntimeError(f"{url}: netværk slået fra i testen")
    if "Forening-Holdoversigt.aspx" in url:
        return side_forening(beregn.id_fra(url, "ForeningsId"))
    if "Pulje-Oversigt.aspx" in url:
        return side_pulje_oversigt(beregn.id_fra(url, "RaekkeId"))
    if "Pulje-Komplet-Kampprogram.aspx" in url:
        return side_komplet(beregn.id_fra(url, "PuljeId"))
    if "Pulje-Holdoversigt.aspx" in url:
        return side_holdoversigt(beregn.id_fra(url, "PuljeId"))
    if "Spillested-Information.aspx" in url:
        return side_spillested(beregn.id_fra(url, "SpillestedsId"))
    if "Hold-Information.aspx" in url:
        return side_hold_info(beregn.id_fra(url, "HoldId"))
    if "Puljekampprogram.ashx?key=" in url:
        if NET["tom_kalender"]:
            return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
        return ics(int(url.rsplit("-", 1)[1]))
    if "nominatim.openstreetmap.org/search" in url:
        return nominatim(url)
    if "/table/v1/driving/" in url:
        return osrm(url.split("/table/v1/driving/")[1].split("?")[0])
    raise RuntimeError(f"{url}: ukendt i testen")

# ------------------------------------------------------------------ uafhængig genberegning


def km(fra, til):
    if fra == til:
        return 0
    a, b = FX["steder"][fra], FX["steder"][til]
    return round(FX["afstande"][f"{a['lat']:.5f},{a['lon']:.5f}|{b['lat']:.5f},{b['lon']:.5f}"]
                 / 1000)


def rejse(fra, til, takst=2.28, bro=346):
    kryds = (FX["steder"][fra]["lon"] > 10.98) != (FX["steder"][til]["lon"] > 10.98)
    return 3 * (2 * km(fra, til) * takst + (bro if kryds else 0))


def forventet_pokal(rid=2390):
    """Én runde regnet uafhængigt: alle puljer samlet, kun kampe med dato."""
    kampe = {}
    for p in POKAL[rid]["puljer"].values():
        for h, u, d in p["kampe"]:
            kampe[frozenset((h, u))] = (h, u)      # seneste tæller
    udgift = {x: 0.0 for k in kampe.values() for x in k}
    for h, u in kampe.values():
        udgift[u] += rejse(hjem_for(u), hjem_for(h))
    snit = sum(udgift.values()) / len(udgift)
    return {h: udgift[h] - snit for h in udgift}


def talentture(rid):
    """{hold: tur til Ikast} for talentkampene i en række, regnet uafhængigt: 2 biler fra
    holdets hjemmebane i rækkens almindelige pulje til Hyldgårdsskolen."""
    puljer = FX["saesoner"]["2026/27"]["raekker"][rid]["puljer"].values()
    ture = {}
    for hold, *_ in TALENT[rid][1]:
        base = re.sub(r"\s*\(T\)$", "", hold)
        hjem = next(p["hold"][base] for p in puljer if p["hold"].get(base))
        ture[base] = ture.get(base, 0) + 2 * 2 * km(hjem, "Hyldgårdsskolens Hal") * 2.28
    return ture


def forventet_slutspil():
    kampe = [k for rid in (2400, 2401) for k in SLUTSPIL[rid]["puljer"][4200 + rid - 2400]["kampe"]]
    udgift, antal = {}, {}
    for h, u, _ in kampe:
        udgift[u] = udgift.get(u, 0) + rejse(hjem_for(u), hjem_for(h))
        udgift.setdefault(h, 0)
        antal[h] = antal.get(h, 0) + 1
        antal[u] = antal.get(u, 0) + 1
    pris = sum(udgift.values()) / len(kampe)
    return {h: udgift[h] - antal[h] * pris / 2 for h in udgift}

# ------------------------------------------------------------------ selve testen


def koer(rod, ud, cache, nu=None):
    sys.argv = ["beregn.py", "--ud", ud, "--cache", cache] + (["--nu", nu] if nu else [])
    beregn.ROOT = rod
    beregn.ADVARSLER.clear()
    beregn.main()
    return json.load(open(os.path.join(ud, "status.json"), encoding="utf-8"))


def naer(a, b, tol=1.0):
    return a is not None and abs(a - b) <= tol


def main():
    beregn.hent = falsk_hent
    tmp = tempfile.mkdtemp()
    rod, ud, cache = tmp, os.path.join(tmp, "docs"), os.path.join(tmp, "cache")
    kfg = json.load(open(os.path.join(HER, "..", "config.json"), encoding="utf-8"))
    kfg["kalibrering"] = [
        {"saeson": "2024/25", "kilde": "Kreditnota 107041", "raekke_ids": [2071, 2082],
         "faktisk": {"1. Division Herrer|Aalborg Volleyball": 9427.55,
                     "1. Division Kvinder|Aalborg Volleyball": 9787.47}},
        {"saeson": "2025/26", "kilde": "Kreditnota 107996", "raekke_ids": [2249, 2250],
         "faktisk": {"Volleyligaen Kvinder|Aalborg Volleyball": 11014.96,
                     "1. Division Herrer|Aalborg Volleyball": 10071.13}}]
    # Fixtures har VD's afstande til Ikast KFUM's hjemmebane, som den stod i kampprogrammet
    # (Sportscenter Ikast). Reglen om, at alle kampe mod Ikast spilles på Hyldgårdsskolen,
    # testes for sig i trin 9 — her gælder samme_sted kun talentholdet og stedets navn.
    hyld = kfg["samme_sted"]["Hyldgårdsskolen"]
    ikast_regel = dict(hyld)
    hyld["hjemmehold"] = ["Talenthold"]
    fp0 = forventet_pokal()          # pokalkontrol: samme runde som "faktura"
    kfg["kalibrering"].append(
        {"saeson": "2025/26", "type": "pokal", "kilde": "Test-faktura", "runder": [[4154]],
         "faktisk": {f"4154|{h}": round(v, 2) for h, v in fp0.items() if h.startswith(KLUB)}})
    json.dump(kfg, open(os.path.join(rod, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    fejl = []

    def tjek(ok, tekst):
        print(("  ok   " if ok else "  FEJL ") + tekst)
        if not ok:
            fejl.append(tekst)

    print("1) Første kørsel (alt hentes) — grundspil + pokal")
    st = koer(rod, ud, cache, nu="2026-09-22")
    koder = {h["kode"]: h for h in st["klubhold"]}
    tjek(st["saeson"] == "2026/27", f"sæson = {st['saeson']}")
    tjek(sorted(koder) == ["D1", "D2", "D3", "H1", "H2", "H3"], f"hold: {sorted(koder)}")
    # H1 er med VD's egne 200 km Aalborg–Årre (km_rettelser i config.json); uden: 10.708
    forventet = {"D1": 19042, "D2": 12820, "D3": 3086, "H1": 10203, "H2": 1786, "H3": 1786}
    grund_forventet = 48723                    # uden talentkampene
    # Talentkampene er almindelige udekampe: holdets tur til Ikast lægges oven i, og rækkens snit
    # stiger med alle talentture delt på rækkens hold (30 herrer, 29 kvinder – uden talentholdet)
    for kode, rid, hold, n in (("H2", "2372", "Aalborg Volleyball.2", 30),
                               ("H3", "2372", "Aalborg Volleyball.3", 30),
                               ("D3", "2374", "Aalborg Volleyball.3", 29)):
        ture = talentture(rid)
        forventet[kode] += ture[hold] - sum(ture.values()) / n
        grund_forventet += ture[hold] - sum(ture.values()) / n
    for k, v in forventet.items():
        tjek(naer(koder.get(k, {}).get("udligning"), v, 1.5),
             f"{k} {koder.get(k, {}).get('raekke')}: {koder.get(k, {}).get('udligning')} ≈ {v:.2f}")
    tjek(naer(st["grundspil"], grund_forventet, 3),
         f"grundspil {st['grundspil']} ≈ {grund_forventet:.2f}")
    aarre = [t for t in koder["H1"]["ture"] if "Årre" in (t.get("adresse") or t.get("sted") or "")
             or "Granly" in (t.get("sted") or "")]
    tjek(len(aarre) == 1 and aarre[0]["km"] == 200,
         f"km-rettelse: H1 til Årre = {[t['km'] for t in aarre]} km (VD's tal)")
    tjek(koder["D1"]["bro"] == 6 and koder["H1"]["bro"] == 0, "broture: D1 = 6, H1 = 0")
    tjek(koder["D1"]["udekampe"] == 9 and len(koder["D1"]["ture"]) == 9, "D1 har 9 udeture")
    tjek(all("kvalifikation" not in r["raekke"] for r in st["raekker"]),
         "kvalifikation/pokal/DS er ikke regnet som grundspil")
    for r in st["raekker"]:
        tjek(abs(sum(h["udligning"] for h in r["hold"])) < 0.5,
             f"{r['raekke']}: nulsum over {r['antal_hold']} hold")
    kal = {}
    for k in st["kalibrering"]:
        kal.setdefault(k["saeson"], {}).update({l["noegle"]: l for l in k["linjer"]})
    pk = [l for l in kal["2025/26"].values() if l["noegle"].startswith("Pokalturneringen")]
    tjek(len(pk) == 3 and all(naer(l["model"], l["faktisk"], 0.02) for l in pk),
         f"pokalkontrol: {[(l['noegle'], l['model'], l['faktisk']) for l in pk]}")
    tjek(naer(kal["2024/25"]["1. Division Herrer|Aalborg Volleyball"]["model"], 9469.03, 1),
         "kontrol 24/25 1. div H ≈ 9.469 (VD: 9.427,55)")
    tjek(naer(kal["2024/25"]["1. Division Kvinder|Aalborg Volleyball"]["model"], 9808.21, 1),
         "kontrol 24/25 1. div K ≈ 9.808 (VD: 9.787,47)")
    tjek(naer(kal["2025/26"]["1. Division Herrer|Aalborg Volleyball"]["model"], 10083.17, 1),
         "kontrol 25/26 1. div H ≈ 10.083 (VD: 10.071,13)")

    runder = {r["raekke"]: r for r in st["pokal"]}
    r2 = runder.get("Pokalturneringen Herrer 2. runde", {})
    tjek(r2.get("status") == "beregnet" and r2.get("antal_hold") == 12 and r2.get("antal_kampe") == 6,
         f"pokal 2. runde: {r2.get('antal_hold')} hold / {r2.get('antal_kampe')} kampe (omkamp tæller én gang)")
    tjek(abs(sum(h["udligning"] for h in r2.get("hold", []))) < 0.5, "pokalrunden går i nul")
    fp = forventet_pokal()
    for h in r2.get("hold", []):
        if h["klub"]:
            tjek(naer(h["udligning"], fp[h["hold"]], 0.05),
                 f"pokal {h.get('kode') or '–'} {h['hold']}: {h['udligning']:.2f} = {fp[h['hold']]:.2f}")
    tjek(runder.get("Pokalturneringen Kvinder 1. runde", {}).get("status") == "ikke trukket",
         "runde uden kampe vises som 'ikke trukket'")
    r3 = runder.get("Pokalturneringen Kvinder 3. runde", {})
    tjek(r3.get("status") == "beregnet" and r3.get("antal_hold") == 12
         and r3.get("hold_i_runden") == 16 and r3.get("uden_dato") == ["På tværs"],
         f"3. runde regnes, selv om en pulje mangler dato: {r3.get('status')} · "
         f"{r3.get('antal_hold')} af {r3.get('hold_i_runden')} hold · uden dato {r3.get('uden_dato')}")
    tjek(abs(sum(h["udligning"] for h in r3.get("hold", []))) < 0.5, "3. runde går i nul")
    fp3 = forventet_pokal(2427)
    d2 = [h for h in r3.get("hold", []) if h["klub"]]
    tjek(len(d2) == 1 and d2[0].get("kode") == "D2"
         and naer(d2[0]["udligning"], fp3["Aalborg Volleyball.2"], 0.05),
         f"pokal 3. runde D2: {[(h.get('kode'), h['udligning']) for h in d2]} = "
         f"{fp3['Aalborg Volleyball.2']:.2f}")
    tjek(naer(st["pokal_total"], sum(v for f in (fp, fp3) for k, v in f.items()
                                     if k.startswith(KLUB)), 0.05),
         f"pokal i alt {st['pokal_total']:.2f}")
    tjek(not st["slutspil"], "intet slutspil i september")
    tjek(naer(st["total"], st["grundspil"] + st["pokal_total"], 0.01), "total = grundspil + pokal")
    html = open(os.path.join(ud, "index.html"), encoding="utf-8").read()
    tjek("Pokalturneringen Herrer 2. runde" in html, "siden viser pokalrunden")
    tjek('3. runde <span class="meta">— 12 af 16 hold ·' in html
         and "4 af 16 hold har ikke en kamp med dato endnu" in html,
         "siden viser, at 4 hold i 3. runde endnu ikke har kamp med dato")
    tjek('2. runde <span class="meta">— 12 hold ·' in html, "en fuldt datosat runde vises som før")
    tjek("kontrolleret: grundspil + pokal" in html, "sæsontabellen lægger grundspil- og pokalkontrol sammen")
    tjek(not st["advarsler"], f"ingen advarsler ({st['advarsler']})")
    talent = st.get("talent") or []
    tjek(sorted(t["kode"] for t in talent) == ["D3", "H2", "H3"],
         f"talentkampe med grundspillets koder: {[(t['kode'], t['hold']) for t in talent]}")
    t2 = next((t for t in talent if t["kode"] == "H2"), {})
    tjek(t2.get("sted") == "Hyldgårdsskolen" and t2.get("dato") == "18-12-2026" and t2.get("km") == 125
         and naer(t2.get("beloeb"), 2 * 2 * 125 * 2.28, 0.01),
         f"H2's tur til talentholdet: {t2.get('km')} km, {t2.get('beloeb')} kr (2 biler)")
    tjek(any(t.get("talent") and t["modstander"] == "Talenthold" for t in koder["H2"]["ture"])
         and koder["H2"]["udekampe"] == 10 and koder["H3"]["udekampe"] == 10
         and koder["D3"]["udekampe"] == 10,
         "talentkampen er en udekamp mere for H2, H3 og D3 (10 i alt)")
    r2h = next(r for r in st["raekker"] if r["raekke"] == "2. Division Herrer")
    tjek("Talent" in r2h["puljer"] and r2h.get("talent_puljer") == ["Talent"]
         and r2h.get("talenthold") == ["Talenthold"] and r2h["antal_hold"] == 30,
         f"2. div H: {r2h['antal_hold']} hold, puljer {r2h['puljer']} – talentpuljen er med, "
         "talentholdet tæller ikke i snittet")
    vend = next((h for h in r2h["hold"] if h["hold"] == "VK Vendsyssel"), {})
    tjek(vend.get("udekampe") == 10 and vend.get("pulje") == "Nord",
         f"også de andre klubbers talentkampe tæller: VK Vendsyssel {vend.get('udekampe')} udekampe")
    tjek(all("(T)" not in h["hold"] and h["hold"] != "Talenthold" for r in st["raekker"] for h in r["hold"]),
         "ingen (T)-hold eller talenthold som hold i rækkernes udligning")
    tjek("<h2>Talentkampe</h2>" in html and "med i tallene ovenfor" in html
         and "+ kampene i Talent" in html and "Talent er ikke med" not in html
         and "Talentholdet har ingen udgifter og er ikke regnet med i rækkens snit" in html,
         "siden viser, at talentkampene er med")
    t3 = next((t for t in talent if t["kode"] == "H3"), {})
    tjek(t2.get("sted") == t3.get("sted") == "Hyldgårdsskolen" and t2.get("km") == t3.get("km"),
         f"Salen med forkert adresse og Hallen er begge Hyldgårdsskolen: {t2.get('sted')} "
         f"{t2.get('km')} km / {t3.get('sted')} {t3.get('km')} km")
    tjek(not any("Hyldgårdsskolens Sal" in a for a in st["advarsler"]),
         "ingen advarsel om Salens forkerte adresse")

    print("2) Anden kørsel — adresser og afstande kommer fra cachen")
    NET["kald"].clear()
    NET["slaa_fra"] = {"nominatim", "/table/v1/"}
    st2 = koer(rod, ud, cache, nu="2026-09-22")
    tjek(naer(st2["total"], st["total"], 0.01), f"samme total fra cache ({st2['total']})")
    tjek(not any("Pulje-Komplet" in u for u in NET["kald"]), "kalender-nøgler genbruges")
    tjek(not any("RaekkeId=2071" in u for u in NET["kald"]), "kontrol-sæsoner genbruges")
    tjek(not any("Spillested-Information" in u for u in NET["kald"]), "spillesteder genbruges")

    print("3) Slutspil i april — findes via de andre klubbers sider")
    VIS_SLUTSPIL["ja"] = True
    NET["slaa_fra"] = set()
    st5 = koer(rod, ud, cache, nu="2027-04-15")
    ss = st5["slutspil"][0] if st5["slutspil"] else {}
    tjek(sorted(ss.get("raekker", [])) == ["Volleyligaen Kvinder 7-9. plads",
                                          "Volleyligaen Kvinder Kvartfinaler"],
         f"slutspilsrækker: {ss.get('raekker')} (kvalifikation holdt ude)")
    tjek(ss.get("antal_kampe") == 11, f"{ss.get('antal_kampe')} kampe i slutspillet")
    tjek(abs(sum(h["udligning"] for h in ss.get("hold", []))) < 0.5, "slutspillet går i nul")
    fs = forventet_slutspil()
    for h in ss.get("hold", []):
        tjek(naer(h["udligning"], fs[h["hold"]], 0.05),
             f"slutspil {h['hold']}: {h['udligning']:.2f} = {fs[h['hold']]:.2f}")
    tjek(naer(st5["total"], st5["grundspil"] + st5["pokal_total"] + st5["slutspil_total"], 0.01),
         "total = grundspil + pokal + slutspil")
    html5 = open(os.path.join(ud, "index.html"), encoding="utf-8").read()
    tjek("4 af 16 hold havde ingen kamp med dato (typisk w.o.)" in html5
         and "kamp med dato endnu" not in html5,
         "en spillet pokalrunde kalder hold uden dato for w.o., ikke 'endnu'")
    VIS_SLUTSPIL["ja"] = False

    print("4) Turneringssystemet er nede — siden viser sidste gode tal")
    NET["slaa_fra"] = {"resultater.volleyball.dk"}
    st3 = koer(rod, ud, cache)
    tjek(st3["fejl"] and naer(st3["total"], st5["total"], 0.01),
         f"fejlbesked + sidste total ({st3['total']})")

    print("5) Ny sæson uden kampprogram endnu")
    NET["slaa_fra"] = set()
    NET["tom_kalender"] = True
    st4 = koer(rod, ud, cache)
    tjek(st4["fejl"] and "ikke lagt ud endnu" in st4["fejl"], f"venlig besked ({st4['fejl'][:60]}…)")
    NET["tom_kalender"] = False

    print("6) Ukendt årstal → bruger seneste takst og advarer")
    kfg2 = dict(kfg, km_takst={"2025": 2.23})
    json.dump(kfg2, open(os.path.join(rod, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    st6 = koer(rod, ud, cache, nu="2026-09-22")
    tjek(any("Km-taksten for 2026 mangler" in a for a in st6["advarsler"]), "advarsel om takst")

    print("7) Adressefelt fra spillestedssiden")
    tjek(beregn.parse_adresse(["Vrenderupvej 40 C", "Vrenderup", "6818 Årre", "Danmark"])
         == {"gade": "Vrenderupvej 40 C", "postnr": "6818", "by": "Årre"}, "flere linjer")
    tjek(beregn.parse_adresse(["v/ Holbæk By Skole", "Bispehøjen 2", "4300 Holbæk"])["gade"]
         == "Bispehøjen 2", "første linje uden husnummer springes over")
    tjek(beregn.parse_adresse(["Sandbjerggade 35 2200 København N Danmark"])
         == {"gade": "Sandbjerggade 35", "postnr": "2200", "by": "København N"}, "én linje")

    print("8) Noten om hold uden dato: spillet runde (w.o.) eller runde i gang")
    import render as rnd

    def runde(navn, antal, i_alt, *datoer):
        return {"raekke": navn, "status": "beregnet", "antal_hold": antal, "hold_i_runden": i_alt,
                "uden_dato": [], "gennemsnit": 500, "hold": [],
                "kampe": [{"dato": d, "hjemme": "A", "ude": "B", "sted": "", "km": 0, "beloeb": 0}
                          for d in datoer]}
    side = rnd.render({"opdateret": "06-10-2026 10:27", "saeson": "2026/27", "total": 0,
                       "pokal": [runde("Pokalturneringen Herrer 2. runde", 26, 28, "27-09-2026"),
                                 runde("Pokalturneringen Herrer 3. runde", 12, 16, "07-10-2026"),
                                 runde("Pokalturneringen Kvinder 1. runde", 4, 6, "20-09-2026"),
                                 runde("Pokalturneringen Kvinder 2. runde", 26, 28, "27-09-2026")]})
    tjek("2 af 28 hold havde ingen kamp med dato (typisk w.o.)" in side,
         "herrernes 2. runde er spillet, fordi 3. runde er i gang")
    tjek("4 af 16 hold har ikke en kamp med dato endnu" in side, "herrernes 3. runde er i gang")
    tjek("2 af 6 hold havde ingen kamp med dato (typisk w.o.)" in side,
         "en runde over 14 dage gammel er spillet")
    tjek("2 af 28 hold har ikke en kamp med dato endnu" in side,
         "damernes 2. runde (9 dage, ingen 3. runde) kan stadig nå at få datoer")

    print("9) Alle kampe mod Ikast spilles på Hyldgårdsskolen (samme_sted i config.json)")
    kfg9 = json.loads(json.dumps(kfg))
    kfg9["samme_sted"]["Hyldgårdsskolen"] = ikast_regel
    json.dump(kfg9, open(os.path.join(rod, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    st9 = koer(rod, ud, cache, nu="2026-09-22")
    k9 = {h["kode"]: h for h in st9["klubhold"]}
    ikast = [t for t in k9["D1"]["ture"] if t["modstander"].startswith("Ikast KFUM")]
    tjek(len(ikast) == 1 and ikast[0]["sted"] == "Hyldgårdsskolen" and ikast[0]["km"],
         f"D1's tur til Ikast KFUM går til Hyldgårdsskolen: {[(t['sted'], t['km']) for t in ikast]}")
    gl = [t for t in koder["D1"]["ture"] if t["modstander"].startswith("Ikast KFUM")]
    tjek(gl and gl[0]["sted"] == "Sportscenter Ikast", "uden reglen stod den til Sportscenter Ikast")
    for r in st9["raekker"]:
        tjek(abs(sum(h["udligning"] for h in r["hold"])) < 0.5,
             f"{r['raekke']}: stadig nulsum med Ikast på Hyldgårdsskolen")
    tidl = [l for k in st9["kalibrering"] if k["saeson"] == "2025/26" and k.get("type") != "pokal"
            for l in k["linjer"] if l["noegle"] == "Volleyligaen Kvinder|Aalborg Volleyball"]
    tjek(tidl and naer(tidl[0]["model"], kal["2025/26"]["Volleyligaen Kvinder|Aalborg Volleyball"]["model"], 0.01),
         "reglen gælder fra 1/7 2026 — kontrollen af 2025/26 er uændret")

    print("10) Talentholdet tæller med i rækkens snit (config.json → talent)")
    kfg10 = json.loads(json.dumps(kfg))
    kfg10["talent"] = {"talenthold_i_snittet": True}
    json.dump(kfg10, open(os.path.join(rod, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    st10 = koer(rod, ud, cache, nu="2026-09-22")
    k10 = {h["kode"]: h for h in st10["klubhold"]}
    for r in st10["raekker"]:
        tjek(abs(sum(h["udligning"] for h in r["hold"])) < 0.5, f"{r['raekke']}: stadig nulsum")
    for navn_, n_, koder_ in (("2. Division Herrer", 31, ("H2", "H3")), ("2. Division Kvinder", 30, ("D3",))):
        r10 = next(r for r in st10["raekker"] if r["raekke"] == navn_)
        r1 = next(r for r in st["raekker"] if r["raekke"] == navn_)
        th = next((h for h in r10["hold"] if h["hold"] == "Talenthold"), {})
        tjek(r10["antal_hold"] == n_ and th.get("udgift") == 0 and th.get("pulje") == "Talent"
             and naer(th.get("udligning"), -r10["gennemsnit"], 0.01),
             f"{navn_}: {r10['antal_hold']} hold, talentholdet betaler snittet "
             f"({th.get('udligning')} kr)")
        for kode in koder_:
            tjek(naer(k10[kode]["udligning"],
                      koder[kode]["udligning"] + r1["gennemsnit"] - r10["gennemsnit"], 0.02),
                 f"{kode}: {k10[kode]['udligning']} = {koder[kode]['udligning']} + lavere snit "
                 f"({r1['gennemsnit']} → {r10['gennemsnit']})")
    html10 = open(os.path.join(ud, "index.html"), encoding="utf-8").read()
    tjek("Talentholdet tæller med som et hold i rækkens snit" in html10, "siden siger det")

    print("11) Et (T)-hold, der ikke spiller i rækkens andre puljer, kan ikke placeres")
    p4303 = FX["saesoner"]["2026/27"]["raekker"]["2372"]["puljer"]["4303"]
    p4303["kampe"].append(("Talenthold", "Ukendt VK (T)", "2027-02-01"))
    p4303["hold"]["Ukendt VK (T)"] = None
    json.dump(kfg, open(os.path.join(rod, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    st11 = koer(rod, ud, cache, nu="2026-09-22")
    r11 = next(r for r in st11["raekker"] if r["raekke"] == "2. Division Herrer")
    tjek(any("Ukendt VK (T)" in a and "ikke regnet med" in a for a in st11["advarsler"]),
         f"advarsel: {[a for a in st11['advarsler'] if 'Ukendt' in a]}")
    tjek(r11["antal_hold"] == 30 and naer(r11["gennemsnit"], r2h["gennemsnit"], 0.01)
         and not any(h["hold"].startswith("Ukendt") for h in r11["hold"]),
         "kampen er ikke med, og rækken er som før")
    p4303["kampe"].pop()
    del p4303["hold"]["Ukendt VK (T)"]

    shutil.rmtree(tmp)
    print("\nALT OK" if not fejl else f"\n{len(fejl)} FEJL")
    return 1 if fejl else 0


if __name__ == "__main__":
    sys.exit(main())
