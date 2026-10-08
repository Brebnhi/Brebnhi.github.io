#!/usr/bin/env python3
"""
Kontrollerer via Holdsports API, at tjans-aktiviteterne stadig ligger i kalenderen —
og på det tidspunkt, kalenderen siger (så en tjans, der ikke er flyttet med kampen, ses).

Kører kun hvis HOLDSPORT_USER og HOLDSPORT_PASSWORD er sat som hemmeligheder.
Er de ikke sat, springes tjekket helt over, og resten af bygningen kører videre.

API: https://github.com/Holdsport/holdsport-api  (HTTP Basic auth)
"""

import base64, json, os, re, sys, urllib.error, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DK = ZoneInfo("Europe/Copenhagen")

API = "https://api.holdsport.dk/v1"
TIMEOUT = 45
MAKS_SIDER = 25
PER_SIDE = 50


def _kald(sti, bruger, kode):
    req = urllib.request.Request(
        f"{API}/{sti}",
        headers={
            "Accept": "application/json",
            "Authorization": "Basic " + base64.b64encode(
                f"{bruger}:{kode}".encode()).decode(),
            "User-Agent": "aalborg-volley-tjans/1.0",
        })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def hent_hold(bruger, kode):
    data = _kald("teams", bruger, kode)
    hold = data.get("teams", data) if isinstance(data, dict) else data
    ud = []
    for h in hold or []:
        ud.append({"id": h.get("id"), "navn": h.get("name", ""), "rolle": h.get("role")})
    return ud


def hent_aktiviteter(bruger, kode, hold_id, fra_dato, til_dato):
    """Henter aktiviteter fra og med fra_dato, side for side."""
    alle, side = [], 1
    while side <= MAKS_SIDER:
        sti = f"teams/{hold_id}/activities?date={fra_dato}&page={side}&per_page={PER_SIDE}"
        data = _kald(sti, bruger, kode)
        akt = data.get("activities", data) if isinstance(data, dict) else data
        if not akt:
            break
        alle.extend(akt)
        if len(akt) < PER_SIDE:
            break
        sidste = _start(akt[-1])
        if sidste and sidste.date().isoformat() > til_dato:
            break
        side += 1
    return alle


def _start(a):
    for felt in ("starttime", "start_time", "startTime"):
        v = a.get(felt)
        if not v:
            continue
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _lokal(a):
    """Aktivitetens starttid som 'ÅÅÅÅ-MM-DD TT:MM' i dansk tid – samme form som robottens
    egne tider. Tom, hvis Holdsport ikke har en."""
    st = _start(a)
    if not st:
        return ""
    if st.tzinfo is None:                 # uden tidszone: Holdsport regner i dansk tid
        st = st.replace(tzinfo=DK)
    return st.astimezone(DK).strftime("%Y-%m-%d %H:%M")


def _norm(s):
    s = (s or "").lower()
    for a, b in (("æ", "ae"), ("ø", "oe"), ("å", "aa")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# Bud på hvad holdene kan hedde i Holdsport, hvis der ikke er sat noget i konfigurationen
GÆT = {
    "D1": ["d1", "damer 1", "dame 1", "damer senior 1", "kvinder 1", "damer elite"],
    "D2": ["d2", "damer 2", "dame 2", "damer senior 2", "kvinder 2"],
    "D3": ["d3", "damer 3", "dame 3", "damer senior 3", "kvinder 3"],
    "H1": ["h1", "herrer 1", "herre 1", "herrer senior 1", "maend 1"],
    "H2": ["h2", "herrer 2", "herre 2", "herrer senior 2", "maend 2"],
    "H3": ["h3", "herrer 3", "herre 3", "herrer senior 3", "maend 3"],
}


def find_hold(kode, konfig, hold):
    """Slår et af vores holdnavne (D1, H2 ...) op i listen fra Holdsport."""
    ønske = str(konfig.get(kode, "") or "").strip()
    if ønske.isdigit():
        for h in hold:
            if str(h["id"]) == ønske:
                return h, "id fra konfiguration"
        return None, f"holdnummer {ønske} findes ikke på din bruger"
    if ønske:
        n = _norm(ønske)
        for h in hold:
            if _norm(h["navn"]) == n:
                return h, "navn fra konfiguration"
        for h in hold:
            if n and n in _norm(h["navn"]):
                return h, "navn fra konfiguration (delvis)"
        return None, f"intet hold der hedder “{ønske}”"
    for forslag in GÆT.get(kode, []):
        for h in hold:
            if _norm(h["navn"]) == forslag:
                return h, "gættet ud fra navnet"
    for forslag in GÆT.get(kode, []):
        for h in hold:
            if forslag in _norm(h["navn"]).split() or forslag in _norm(h["navn"]):
                return h, "gættet ud fra navnet"
    return None, "kunne ikke gættes — skriv holdets navn i data/holdsport_hold.json"


KAMPNR_RE = re.compile(r"Kampnr\.?\s*(\d{4,8})", re.I)


def _kampnr(akt):
    m = (KAMPNR_RE.search(akt.get("comment") or "")
         or KAMPNR_RE.search(akt.get("name") or ""))
    return m.group(1) if m else ""


def fra_kalender(akt):
    """Har Holdsport selv lavet aktiviteten ud fra robottens kalender? Så står robottens
    beskrivelse ("Der skal stilles 4 personer …") i kommentaren. En aktivitet, du selv har
    oprettet, har din egen kommentar. Holdsport opdaterer kun dem, den selv har lavet."""
    return "der skal stilles" in (akt.get("comment") or "").lower()


def _par(forventede_hold, aktiviteter):
    """Parrer forventede tjanser med Holdsport-aktiviteter, én til én.

    Kampnummeret er den stærke nøgle — det overlever, at en kamp flyttes.
    Findes det ikke (fx hvis kommentarfeltet ikke fulgte med i importen),
    matches på navn plus dato, og til sidst på et entydigt navn alene.
    En aktivitet kan kun bruges én gang, så to ens navne ikke dækker hinanden.
    """
    ledige = list(range(len(aktiviteter)))
    fundet = {}

    def tag(i, nøgle):
        ledige.remove(i)
        fundet[nøgle] = i

    # 1. kampnummer – har Holdsport flere med samme nummer (en ny og en gammel kopi, eller en,
    #    du selv har oprettet), så helst den, der står rigtigt og er lavet ud fra kalenderen –
    #    den holder Holdsport opdateret. De andre bliver meldt som kopier.
    for k, f in enumerate(forventede_hold):
        if k in fundet or not f["kampnr"]:
            continue
        kandidater = [i for i in ledige if _kampnr(aktiviteter[i]) == f["kampnr"]]
        if kandidater:
            rigtig = f["start"][:16].replace("T", " ")
            tag(min(kandidater, key=lambda i: (_lokal(aktiviteter[i]) != rigtig,
                                               not fra_kalender(aktiviteter[i]))), k)

    # 2. samme navn samme dag
    for k, f in enumerate(forventede_hold):
        if k in fundet:
            continue
        navn = (f["navn"] or "").strip()
        dag = f["start"][:10]
        for i in list(ledige):
            a = aktiviteter[i]
            st = _start(a)
            if (a.get("name") or "").strip() == navn and st and st.date().isoformat() == dag:
                tag(i, k)
                break

    # 3. entydigt navn alene (fanger en aktivitet der er flyttet)
    for k, f in enumerate(forventede_hold):
        if k in fundet:
            continue
        navn = (f["navn"] or "").strip()
        if not navn:
            continue
        if sum(1 for g in forventede_hold if (g["navn"] or "").strip() == navn) != 1:
            continue
        traef = [i for i in ledige if (aktiviteter[i].get("name") or "").strip() == navn]
        if len(traef) == 1:
            tag(traef[0], k)

    return fundet


def tjek(forventede, konfig, bruger, kode):
    """forventede: liste af {tjans, kampnr, navn, start, antal, kamp}"""
    resultat = {"aktiveret": True, "fejl": None, "hold": [], "mangler": [], "fundne": [],
                "dubletter": [], "kontrolleret": 0, "fundet": 0, "alle_hold": []}
    try:
        hold = hent_hold(bruger, kode)
    except urllib.error.HTTPError as e:
        resultat["fejl"] = ("Login afvist af Holdsport (401) — tjek brugernavn og kodeord"
                            if e.code == 401 else f"Holdsport svarede {e.code}")
        return resultat
    except Exception as e:
        resultat["fejl"] = f"Kunne ikke nå Holdsport: {e}"
        return resultat

    resultat["alle_hold"] = [{"id": h["id"], "navn": h["navn"]} for h in hold]
    if not hold:
        resultat["fejl"] = "Din Holdsport-bruger er ikke tilknyttet nogen hold"
        return resultat

    datoer = sorted(f["start"][:10] for f in forventede)
    fra = (datetime.fromisoformat(datoer[0]) - timedelta(days=3)).date().isoformat()
    til = datoer[-1]

    pr_hold = {}
    for f in forventede:
        pr_hold.setdefault(f["tjans"], []).append(f)

    for kode_hold in sorted(pr_hold):
        h, hvordan = find_hold(kode_hold, konfig, hold)
        post = {"kode": kode_hold, "holdsport": h["navn"] if h else None,
                "id": h["id"] if h else None, "match": hvordan,
                "forventet": len(pr_hold[kode_hold]), "fundet": 0, "mangler": 0}
        if not h:
            post["fejl"] = hvordan
            resultat["hold"].append(post)
            continue
        try:
            akt = hent_aktiviteter(bruger, kode, h["id"], fra, til)
        except Exception as e:
            post["fejl"] = f"Kunne ikke hente aktiviteter: {e}"
            resultat["hold"].append(post)
            continue
        liste = pr_hold[kode_hold]
        parret = _par(liste, akt)
        post["aktiviteter"] = len(akt)
        for k, f in enumerate(liste):
            resultat["kontrolleret"] += 1
            if k in parret:
                post["fundet"] += 1
                resultat["fundet"] += 1
                a = akt[parret[k]]
                # aktivitetens nummer i Holdsport – så kan build.py se, hvis Holdsport
                # senere genbruger aktiviteten til en anden tjans – og dens tidspunkt, så
                # build.py kan se, om Holdsport har flyttet tjansen med kampen
                resultat["fundne"].append({
                    "tjans": kode_hold, "kampnr": f["kampnr"],
                    "start": f["start"][:16].replace("T", " "),
                    "aktivitet": a.get("id"), "hs_start": _lokal(a),
                    "holdsport": h["navn"], "navn": f["navn"], "kamp": f.get("kamp", "")})
            else:
                post["mangler"] += 1
                resultat["mangler"].append({
                    "tjans": kode_hold, "holdsport": h["navn"], "kampnr": f["kampnr"],
                    "navn": f["navn"], "kamp": f.get("kamp", ""),
                    "start": f["start"][:16].replace("T", " ")})
        # En ekstra aktivitet med samme kampnummer som en tjans, der er fundet: Holdsport har
        # lavet en ny i stedet for at flytte den gamle, og den gamle står tilbage.
        brugt = set(parret.values())
        paa_nr = {f["kampnr"]: f for k, f in enumerate(liste) if k in parret and f["kampnr"]}
        for i, a in enumerate(akt):
            nr = _kampnr(a)
            if i in brugt or nr not in paa_nr:
                continue
            f = paa_nr[nr]
            resultat["dubletter"].append({
                "tjans": kode_hold, "kampnr": nr, "holdsport": h["navn"],
                "navn": f["navn"], "kamp": f.get("kamp", ""),
                "start": f["start"][:16].replace("T", " "), "hs_start": _lokal(a),
                "aktivitet": a.get("id"),
                "egen": not fra_kalender(a)})        # oprettet i hånden, ikke af Holdsport
        resultat["hold"].append(post)

    resultat["mangler"].sort(key=lambda m: m["start"])
    return resultat


def koer(forventede, rod):
    bruger = os.environ.get("HOLDSPORT_USER", "").strip()
    kode = os.environ.get("HOLDSPORT_PASSWORD", "").strip()
    if not bruger or not kode:
        return {"aktiveret": False, "fejl": None, "hold": [], "mangler": [],
                "kontrolleret": 0, "fundet": 0, "alle_hold": []}
    sti = os.path.join(rod, "data", "holdsport_hold.json")
    konfig = {}
    if os.path.exists(sti):
        try:
            konfig = {k: v for k, v in json.load(open(sti, encoding="utf-8")).items()
                      if not k.startswith("_")}
        except Exception as e:
            print(f"ADVARSEL: kunne ikke læse holdsport_hold.json ({e})", file=sys.stderr)
    return tjek(forventede, konfig, bruger, kode)
