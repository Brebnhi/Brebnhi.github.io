#!/usr/bin/env python3
# sti: tjans/scripts/holdsport.py
"""
Kontrollerer via Holdsports API, at tjans-aktiviteterne stadig ligger i kalenderen —
og på det tidspunkt, kalenderen siger (så en tjans, der ikke er flyttet med kampen, ses).
Det, der står forkert, retter holdsport_skriv.py bagefter.

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
        rolle = h.get("role")              # 1 spiller, 2 træner, 3 assistenttræner … 6 holdleder
        if isinstance(rolle, str) and rolle.strip().isdigit():
            rolle = int(rolle)
        ud.append({"id": h.get("id"), "navn": h.get("name", ""), "rolle": rolle})
    return ud


def hent_aktiviteter(bruger, kode, hold_id, fra_dato, til_dato):
    """Henter aktiviteter fra og med fra_dato, side for side. Returnerer (aktiviteter, hele) –
    hele er False, hvis der var flere sider, end robotten henter (så kan en tjans være overset)."""
    alle, side = [], 1
    while side <= MAKS_SIDER:
        sti = f"teams/{hold_id}/activities?date={fra_dato}&page={side}&per_page={PER_SIDE}"
        data = _kald(sti, bruger, kode)
        akt = data.get("activities", data) if isinstance(data, dict) else data
        if not akt:
            return alle, True
        alle.extend(akt)
        if len(akt) < PER_SIDE:
            return alle, True
        sidste = _start(akt[-1])
        if sidste and sidste.date().isoformat() > til_dato:
            return alle, True
        side += 1
    return alle, False


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


ROBOT_MAERKE = "Oprettet af tjans-robotten"      # sidste linje i kommentaren på robottens egne

# Volleyball Danmarks beskrivelse af en kamp: "<række>\nRunde 4\nKampnr 148197\n…" – uden punktum
VD_RUNDE_RE = re.compile(r"^\s*Runde\s+\d+\s*$", re.M)
RESULTAT_RE = re.compile(r"\s+\d{1,2}\s*-\s*\d{1,2}(\s*\(.*\))?\s*$")


def er_kampen(akt, kamp=""):
    """Er aktiviteten selve kampen og ikke en tjans? Holdene importerer deres kampprogram fra
    Volleyball Danmark i Holdsport, så holdets egne kampe står i kalenderen – med kampnummeret i
    kommentaren ("Kampnr 148197"). Sådan en hedder som kampen ("Aalborg Volleyball - Odense
    Volleyball", evt. med resultatet bagefter) eller har Volleyball Danmarks beskrivelse, og den
    har hverken "tjans" i navnet eller "Kampnr." (med punktum, som tjanserne har) i kommentaren.
    kamp: "hjemmehold - udehold" """
    navn = akt.get("name") or ""
    kommentar = akt.get("comment") or ""
    if "tjans" in _norm(navn) or "kampnr." in kommentar.lower():
        return False
    return bool((kamp and _norm(RESULTAT_RE.sub("", navn)) == _norm(kamp))
                or (VD_RUNDE_RE.search(kommentar) and KAMPNR_RE.search(kommentar)))


def kilde(akt):
    """Hvem har lavet aktiviteten?
      robot    – robotten selv (holdsport_skriv.py): ROBOT_MAERKE står i kommentaren
      kalender – Holdsport ud fra robottens kalender: robottens beskrivelse ("Der skal stilles
                 4 personer …") står i kommentaren. Kun dem opdaterer Holdsport selv.
      egen     – du selv: din egen kommentar"""
    c = (akt.get("comment") or "").lower()
    if ROBOT_MAERKE.lower() in c:
        return "robot"
    return "kalender" if "der skal stilles" in c else "egen"


def fra_kalender(akt):
    """Har Holdsport selv lavet aktiviteten ud fra robottens kalender?"""
    return kilde(akt) == "kalender"


def _par(forventede_hold, aktiviteter, faste=None):
    """Parrer forventede tjanser med Holdsport-aktiviteter, én til én.

    Kampnummeret er den stærke nøgle — det overlever, at en kamp flyttes.
    Findes det ikke (fx hvis kommentarfeltet ikke fulgte med i importen),
    matches på navn plus dato, så på et entydigt navn alene, og til sidst på en aktivitet
    med "tjans" i navnet på tjansens tidspunkt (eller et tidligere) – så findes en tjans,
    holdet selv har omdøbt og fjernet kampnummeret fra, stadig.
    En aktivitet kan kun bruges én gang, så to ens navne ikke dækker hinanden.

    faste: {aktivitet: tjans} – aktiviteter, Holdsport har koblet til flere tjanser (se
    bindinger i build.py). De hører til den tjans, robotten har givet dem, uanset hvad Holdsport
    senere har skrevet i dem; robotten retter dem tilbage. Har tjansen fået en anden aktivitet
    med sit kampnummer (fx en, du selv har oprettet), er det den, der gælder.
    """
    ledige = list(range(len(aktiviteter)))
    fundet = {}

    def tag(i, nøgle):
        ledige.remove(i)
        fundet[nøgle] = i

    # 0. aktiviteter, robotten har givet en bestemt tjans
    for k, f in enumerate(forventede_hold):
        n = f"{f['kampnr'] or f['start'][:10]}-{f['tjans']}"
        for i in list(ledige):
            if k in fundet or str((faste or {}).get(str(aktiviteter[i].get("id")))) != n \
                    or er_kampen(aktiviteter[i], f.get("kamp")):
                continue
            if not any(j != i and f["kampnr"] and _kampnr(aktiviteter[j]) == f["kampnr"]
                       for j in ledige):
                tag(i, k)

    # 1. kampnummer – har Holdsport flere med samme nummer (en ny og en gammel kopi, eller en,
    #    du selv har oprettet), så helst den, der står rigtigt, og derefter den, Holdsport har
    #    lavet ud fra kalenderen, så robottens egen, så din. De andre bliver meldt som kopier.
    rang = {"kalender": 0, "robot": 1, "egen": 2}
    for k, f in enumerate(forventede_hold):
        if k in fundet or not f["kampnr"]:
            continue
        kandidater = [i for i in ledige if _kampnr(aktiviteter[i]) == f["kampnr"]
                      and not er_kampen(aktiviteter[i], f.get("kamp"))]
        if kandidater:
            rigtig = f["start"][:16].replace("T", " ")
            tag(min(kandidater, key=lambda i: (_lokal(aktiviteter[i]) != rigtig,
                                               rang[kilde(aktiviteter[i])])), k)

    # 2. samme navn samme dag
    for k, f in enumerate(forventede_hold):
        if k in fundet:
            continue
        navn = (f["navn"] or "").strip()
        dag = f["start"][:10]
        for i in list(ledige):
            a = aktiviteter[i]
            st = _start(a)
            if (a.get("name") or "").strip() == navn and st and st.date().isoformat() == dag \
                    and not er_kampen(a, f.get("kamp")):
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
        traef = [i for i in ledige if (aktiviteter[i].get("name") or "").strip() == navn
                 and not er_kampen(aktiviteter[i], f.get("kamp"))]
        if len(traef) == 1:
            tag(traef[0], k)

    # 4. "tjans" i navnet og tjansens tidspunkt – nu eller før (en flyttet kamp, tjanselistens
    #    tid). Kun når det er entydigt: én aktivitet, og ingen anden af holdets tjanser på tiden.
    def tider(f):
        return {f["start"][:16].replace("T", " ")} | set(f.get("tidligere") or [])
    for k, f in enumerate(forventede_hold):
        if k in fundet:
            continue
        traef = [i for i in ledige if "tjans" in _norm(aktiviteter[i].get("name"))
                 and _lokal(aktiviteter[i]) in tider(f)]
        if len(traef) != 1:
            continue
        tid = _lokal(aktiviteter[traef[0]])
        if not any(j != k and j not in fundet and tid in tider(g)
                   for j, g in enumerate(forventede_hold)):
            tag(traef[0], k)

    return fundet


def tjek(forventede, konfig, bruger, kode, faste=None):
    """forventede: liste af {tjans, kampnr, navn, start, antal, kamp}
    faste: {aktivitet: tjans} – se _par"""
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

    resultat["alle_hold"] = [{"id": h["id"], "navn": h["navn"], "rolle": h.get("rolle")}
                             for h in hold]
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
                "rolle": h.get("rolle") if h else None,       # din rolle på holdet i Holdsport
                "forventet": len(pr_hold[kode_hold]), "fundet": 0, "mangler": 0}
        if not h:
            post["fejl"] = hvordan
            resultat["hold"].append(post)
            continue
        try:
            akt, hele = hent_aktiviteter(bruger, kode, h["id"], fra, til)
        except Exception as e:
            post["fejl"] = f"Kunne ikke hente aktiviteter: {e}"
            resultat["hold"].append(post)
            continue
        if not hele:
            post["ufuldstaendig"] = True       # så opretter robotten ikke noget på holdet
        liste = pr_hold[kode_hold]
        parret = _par(liste, akt, faste)
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
                    "aktivitet": a.get("id"), "hs_start": _lokal(a), "kilde": kilde(a),
                    "hs_navn": a.get("name") or "", "hold_id": h["id"],
                    "holdsport": h["navn"], "navn": f["navn"], "kamp": f.get("kamp", "")})
            else:
                post["mangler"] += 1
                start = f["start"][:16].replace("T", " ")
                # Ligger der en anden aktivitet på tidspunktet, kan det være tjansen i en
                # skikkelse, robotten ikke kender – så opretter robotten ikke en til
                optaget = next((a.get("name") or "(uden navn)" for i, a in enumerate(akt)
                                if i not in parret.values() and _lokal(a) == start), "")
                resultat["mangler"].append({
                    "tjans": kode_hold, "holdsport": h["navn"], "kampnr": f["kampnr"],
                    "navn": f["navn"], "kamp": f.get("kamp", ""), "hold_id": h["id"],
                    "start": start, "optaget": optaget})
        # En ekstra aktivitet med samme kampnummer som en tjans, der er fundet: Holdsport har
        # lavet en ny i stedet for at flytte den gamle, og den gamle står tilbage.
        brugt = set(parret.values())
        paa_nr = {f["kampnr"]: f for k, f in enumerate(liste) if k in parret and f["kampnr"]}
        for i, a in enumerate(akt):
            nr = _kampnr(a)
            if i in brugt or nr not in paa_nr or er_kampen(a, paa_nr[nr].get("kamp")):
                continue
            f = paa_nr[nr]
            resultat["dubletter"].append({
                "tjans": kode_hold, "kampnr": nr, "holdsport": h["navn"],
                "navn": f["navn"], "kamp": f.get("kamp", ""),
                "start": f["start"][:16].replace("T", " "), "hs_start": _lokal(a),
                "aktivitet": a.get("id"), "kilde": kilde(a),
                "egen": kilde(a) == "egen"})         # oprettet i hånden, ikke af Holdsport
        resultat["hold"].append(post)

    resultat["mangler"].sort(key=lambda m: m["start"])
    return resultat


def _konfig(rod):
    sti = os.path.join(rod, "data", "holdsport_hold.json")
    if not os.path.exists(sti):
        return {}
    try:
        return {k: v for k, v in json.load(open(sti, encoding="utf-8")).items()
                if not k.startswith("_")}
    except Exception as e:
        print(f"ADVARSEL: kunne ikke læse holdsport_hold.json ({e})", file=sys.stderr)
        return {}


def koer(forventede, rod, faste=None):
    bruger = os.environ.get("HOLDSPORT_USER", "").strip()
    kode = os.environ.get("HOLDSPORT_PASSWORD", "").strip()
    if not bruger or not kode:
        return {"aktiveret": False, "fejl": None, "hold": [], "mangler": [],
                "kontrolleret": 0, "fundet": 0, "alle_hold": []}
    return tjek(forventede, _konfig(rod), bruger, kode, faste)


PERS_RE = re.compile(r"(\d+)\s*pers", re.I)
FOER_KAMP = timedelta(minutes=120)       # så længe før kampen kan en tjans begynde


def find_egne(kampe, hold_koder, kendte, rod, foer_egne=None, soeg=None, kendte_akt=None,
              staevne_dage=None):
    """Tjanser, du selv har oprettet i Holdsport til hjemmekampe, der ikke står i tjanselisten –
    fx en ny pokalkamp. Robotten leder i tjanseholdenes kalendere efter
      1. en aktivitet med "Kampnr. <kampens nummer>" i kommentaren eller navnet (eller den
         aktivitet, den fandt sidst), ellers
      2. en aktivitet med "tjans" i navnet og intet kampnummer, der begynder op til to timer før
         kampen (og ikke er en af holdets kendte tjanser).
    Hos de hold, der selv spiller kampen, ledes der ikke: står kampen i deres kalender (fra
    Volleyball Danmarks kampprogram, med kampnummeret), er det kampen og ikke en tjans.
    kampe:      [{kampnr, start (dansk tid), klubhold, udekode, hjemme, ude}] – hjemmekampe, hvor
                tjansen skal findes
    hold_koder: de hold, der har tjanser (D1 … H3)
    kendte:     {hold: {"ÅÅÅÅ-MM-DD TT:MM", ...}} – starttider for holdenes kendte tjanser
    foer_egne:  {kampnr: {tjans, aktivitet, lead, lead_kamp, antal}} fra sidste kørsel – så
                findes en tjans igen, efter at kampen er flyttet
    soeg:       {aktivitet: {tjans, start}} – andre aktiviteter, robotten vil vide, om findes endnu
    kendte_akt: aktiviteter, der er tjanser fra tjanselisten (fra sidste kørsel)
    staevne_dage: {(hold, "ÅÅÅÅ-MM-DD")} – dage, hvor holdet har en stævnetjans i listen. Dén
                kan også have "tjans" i navnet, så dér skal der stå Kampnr. i tjansen
    Returnerer {"ok": alt kunne læses,
                "fundne": {kampnr: {tjans, aktivitet, hs_start, hs_navn, lead, lead_kamp, antal,
                                    sikker}},
                "tvetydige": {kampnr: [hold, ...]} – kampe med flere mulige tjanser,
                "findes": {aktivitet: {hs_start, hs_navn}} – de af soeg, der findes}."""
    ud = {"ok": False, "fundne": {}, "tvetydige": {}, "findes": {}}
    bruger = os.environ.get("HOLDSPORT_USER", "").strip()
    kode = os.environ.get("HOLDSPORT_PASSWORD", "").strip()
    soeg = {str(a): s for a, s in (soeg or {}).items()}
    if not (kampe or soeg) or not bruger or not kode:
        return ud
    try:
        hold = hent_hold(bruger, kode)
    except Exception:                                   # noqa: BLE001 – tjekket melder fejlen
        return ud
    konfig, foer_egne = _konfig(rod), foer_egne or {}
    kendte_akt = {str(a) for a in kendte_akt or ()}
    staevne_dage = set(staevne_dage or ())
    tider = [k["start"] for k in kampe]
    for s in soeg.values():
        try:
            tider.append(datetime.strptime(s["start"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=DK))
        except (KeyError, TypeError, ValueError):
            pass
    if not tider:
        return ud
    fra = (min(tider) - timedelta(days=1)).date().isoformat()
    til = (max(tider) + timedelta(days=1)).date().isoformat()
    akt_pr_hold, ok = {}, True
    for kode_hold in sorted(set(hold_koder) | {s.get("tjans") for s in soeg.values()} - {None}):
        h, _ = find_hold(kode_hold, konfig, hold)
        if not h:
            ok = False
            continue
        try:
            akt, hele = hent_aktiviteter(bruger, kode, h["id"], fra, til)
        except Exception:                               # noqa: BLE001
            ok = False
            continue
        akt_pr_hold[kode_hold] = akt
        ok = ok and hele
    ud["ok"] = ok

    def aware(a):
        st = _start(a)
        if st and st.tzinfo is None:
            st = st.replace(tzinfo=DK)
        return st

    for akt_id, s in soeg.items():
        a = next((a for a in akt_pr_hold.get(s.get("tjans"), []) if str(a.get("id")) == akt_id),
                 None)
        if a is not None:
            ud["findes"][akt_id] = {"hs_start": _lokal(a), "hs_navn": a.get("name") or ""}

    fundne, tvetydige, brugt = ud["fundne"], ud["tvetydige"], {}
    for k in kampe:
        nr, start = k["kampnr"], k["start"]
        start_tekst = start.astimezone(DK).strftime("%Y-%m-%d %H:%M")
        gl = foer_egne.get(nr) or {}
        spiller = {k.get("klubhold"), k.get("udekode")} - {"", None}
        kamp_tekst = f"{k.get('hjemme') or ''} - {k.get('ude') or ''}"
        sikre, mulige = [], []
        for kode_hold, akt in akt_pr_hold.items():
            if kode_hold not in hold_koder or kode_hold in spiller:
                continue                # holdet spiller selv: aktiviteten med kampnummeret er kampen
            for a in akt:
                st = aware(a)
                navn = _norm(a.get("name"))
                if not st or er_kampen(a, kamp_tekst):
                    continue            # selve kampen, importeret fra kampprogrammet
                if (str(a.get("id")) == str(gl.get("aktivitet")) and gl.get("tjans") == kode_hold) \
                        or _kampnr(a) == nr:
                    sikre.append((kode_hold, a))
                elif ("tjans" in navn and not _kampnr(a) and start - FOER_KAMP <= st <= start
                      and _lokal(a) not in kendte.get(kode_hold, ())
                      and str(a.get("id")) not in kendte_akt
                      and (kode_hold, _lokal(a)[:10]) not in staevne_dage):
                    mulige.append((kode_hold, a))
        valg = sikre or mulige
        if len({(h, str(a.get("id"))) for h, a in valg}) != 1:
            if valg:
                tvetydige[nr] = sorted({h for h, _ in valg})
            continue
        kode_hold, a = valg[0]
        egen = int((start - aware(a)).total_seconds() // 60)    # din mødetid i minutter
        samme = str(gl.get("aktivitet")) == str(a.get("id")) and gl.get("lead") is not None
        if samme and gl.get("lead_kamp") and gl["lead_kamp"] != start_tekst and egen != gl["lead"]:
            # kampen er flyttet, og tjansen er ikke fulgt med endnu: behold din mødetid
            lead, lead_kamp = gl["lead"], gl["lead_kamp"]
        elif 0 <= egen <= 180:
            lead, lead_kamp = egen, start_tekst
        else:
            lead, lead_kamp = (gl["lead"] if samme else None), start_tekst
        m = PERS_RE.search(a.get("name") or "") or PERS_RE.search(a.get("comment") or "")
        antal = int(m.group(1)) if m and 1 <= int(m.group(1)) <= 12 else gl.get("antal")
        fundne[nr] = {"tjans": kode_hold, "aktivitet": a.get("id"), "hs_start": _lokal(a),
                      "hs_navn": a.get("name") or "", "lead": lead, "lead_kamp": lead_kamp,
                      "antal": antal, "sikker": bool(sikre)}
        brugt.setdefault(str(a.get("id")), []).append(nr)
    # samme aktivitet til to kampe: ingen af dem kan afgøres
    for akt_id, nre in brugt.items():
        if len(nre) > 1:
            for nr in nre:
                tvetydige[nr] = [fundne.pop(nr)["tjans"]]
    return ud
