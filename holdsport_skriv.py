#!/usr/bin/env python3
# sti: tjans/scripts/holdsport_skriv.py
"""
Robotten retter selv i Holdsport.

Ved hver kørsel har holdsport.py læst Holdsport og fundet hver tjans' aktivitet. Her retter
robotten det, der står forkert:
  - en tjans på et forkert tidspunkt flyttes til det rigtige (mødetiden)
  - en tjans, der mangler, oprettes
  - en tjans, der ikke har holdets aktivitetstype til tjanser ("Tjans"), får den – så den ikke
    ligner en kamp i kalenderen
Robotten sletter aldrig noget, og den ændrer ikke navnet på en tjans: holdene må gerne skrive
deres egne. Flytter den en tjans, ændres kun tidspunktet (og linjen "Kampstart kl. …").

Holdsports officielle API (api.holdsport.dk/v1) kan kun læse aktiviteter. Robotten skriver
derfor gennem det API, Holdsports egen app bruger (www.holdsport.dk/graphql), med samme login
som tjekket (hemmelighederne HOLDSPORT_USER og HOLDSPORT_PASSWORD). Det login kræver dit
Holdsport-brugernavn – ikke din e-mail. Slå det fra med HOLDSPORT_RETTER i indstillinger.py.

Sikkerhed:
  - robotten skifter til holdet og skriver først, når Holdsport har bekræftet skiftet
  - en aktivitet læses, før den ændres, og alle dens indstillinger sendes med tilbage – Holdsport
    nulstiller ellers de felter, der ikke kommer med (påmindelser, tilmeldingstype osv.)
  - gentagne aktiviteter og betalingsaktiviteter røres ikke
  - højst MAKS_FLYT flytninger, MAKS_OPRET nye aktiviteter og MAKS_TYPE typeskift pr. kørsel –
    de første tjanser først
  - en tjans oprettes ikke, hvis der ligger en anden aktivitet på tidspunktet – den kan være
    tjansen i en skikkelse, robotten ikke kender; så får du besked i stedet
  - en tjans, robotten har oprettet, oprettes ikke igen inden for GENOPRET; er den væk igen,
    slår robotten alarm i stedet
  - en aktivitet, robotten har flyttet MAKS_SAMME gange inden for SAMME_VINDUE, flyttes ikke
    igen – så er der noget, der flytter den tilbage, og robotten slår alarm
  - Holdsports svar tjekkes efter hver ændring, og bagefter læser build.py Holdsport igen
"""

import json, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from holdsport import ROBOT_MAERKE        # sidste linje i kommentaren på robottens egne

DK, UTC = ZoneInfo("Europe/Copenhagen"), timezone.utc

GRAPHQL = "https://www.holdsport.dk/graphql"
APP_VERSION = "8.0.199"          # app-API'et svarer kun, når der står en app-version
TIMEOUT = 45
MAKS_FLYT = 12
MAKS_OPRET = 8
GENOPRET = timedelta(days=7)
MAKS_SAMME = 3
SAMME_VINDUE = timedelta(hours=72)
MAKS_TYPE = 25                   # typeskift pr. kørsel
MAKS_TYPE_LAES = 80              # aktiviteter, robotten læser for at tjekke typen pr. kørsel
TYPE_TJEKKET = timedelta(hours=20)   # så længe stoler robotten på en type, den har tjekket

LOG_IND = """mutation SignIn($username: String, $password: String) {
  SignIn(input: {username: $username, password: $password}) { access_token }
}"""
SKIFT_HOLD = """mutation ChangeCurrentTeam($team: Int!) {
  ChangeCurrentTeam(input: {team_id: $team}) { team { id name } }
}"""
TYPER = """query ListEventTypes($team: Int) {
  activities_event_types(team_id: $team) { id name }
}"""
LAES = """query ShowActivityForEdit($id: Int!) {
  activity(id: $id) {
    id name place comment pickup_time
    starttime { iso8601 } endtime { iso8601 }
    event_type { id } max_attender teams { id name }
    is_repeated_activity is_root_of_repeated_activities has_future_repeated_activities
    is_payment_activity type reminder2 reminder5 hide_unattend ride_enabled ride_comment
    only_player_participation_counts has_waiting_list hide_activity_players_registration
    pickup_place rating
    absolute_registration_deadline { iso8601 } registration_start_at { iso8601 }
  }
}"""
SVAR = "id name starttime { iso8601 } endtime { iso8601 } event_type { id name } teams { id name }"
RET = ("mutation UpdateActivity($input: UpdateActivityInput!) {\n"
       "  UpdateActivity(input: $input) { activity { " + SVAR + " } }\n}")
OPRET = ("mutation CreateActivity($input: CreateActivityInput!) {\n"
         "  CreateActivity(input: $input) { activity { " + SVAR + " } }\n}")

# Indstillinger, Holdsport nulstiller, hvis de ikke sendes med: (felt i svaret, felt i input)
INDSTILLINGER = (("type", "activity_type"), ("reminder2", "reminder2"),
                 ("reminder5", "reminder5"), ("hide_unattend", "hide_unattend"),
                 ("ride_enabled", "ride"), ("ride_comment", "ride_comment"),
                 ("only_player_participation_counts", "only_player_participation_counts"),
                 ("has_waiting_list", "has_waiting_list"),
                 ("hide_activity_players_registration", "hide_activity_players_registration"),
                 ("pickup_place", "pickup_place"), ("rating", "rating"))
TIDSFELTER = (("absolute_registration_deadline", "absolute_registration_deadline_date",
               "absolute_registration_deadline_time"),
              ("registration_start_at", "registration_start_date", "registration_start_time"))
# Det, en ny tjans arver fra holdets andre tjanser: tilmeldingstype og påmindelser
ARVES = ("activity_type", "reminder2", "reminder5", "hide_unattend",
         "only_player_participation_counts", "has_waiting_list",
         "hide_activity_players_registration")
UGEDAGE = ("man", "tir", "ons", "tor", "fre", "lør", "søn")


class SkriveFejl(Exception):
    """Holdsport ville ikke – teksten kommer på siden og i alarmen."""


def vaegur(iso):
    """'2026-10-11T08:30:00Z' -> '2026-10-11 10:30' (dansk tid). Tom ved intet."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:                  # app-API'et svarer i UTC
        d = d.replace(tzinfo=UTC)
    return d.astimezone(DK).strftime("%Y-%m-%d %H:%M")


def _dt(s):
    return datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")


def _tal(v):
    """Holdsports id'er er tal – også hvis de kommer tilbage som tekst."""
    return int(v) if isinstance(v, str) and v.isdigit() else v


def _post(url, krop, hoveder):
    req = urllib.request.Request(url, data=json.dumps(krop).encode("utf-8"),
                                 headers=hoveder, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            tekst = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SkriveFejl(f"Holdsport svarede {e.code}") from None
    except Exception as e:                         # noqa: BLE001
        raise SkriveFejl(f"kunne ikke nå Holdsport ({e})") from None
    try:
        return json.loads(tekst)
    except ValueError:
        raise SkriveFejl("Holdsport svarede ikke med data") from None


class Klient:
    """Holdsports app-API. Alle fejl kommer som SkriveFejl."""

    def __init__(self, bruger, kode, post=None):
        self.bruger, self.kode = bruger, kode
        self.post = post or _post
        self.token = None
        self.hold = None

    def gql(self, forespoergsel, variabler=None, login=True):
        hoveder = {"Content-Type": "application/json", "Accept": "application/json",
                   "X-App-Version": APP_VERSION, "User-Agent": "aalborg-volley-tjans/1.0"}
        if login:
            hoveder["Authorization"] = self.log_ind()
        svar = self.post(GRAPHQL, {"query": forespoergsel, "variables": variabler or {}}, hoveder)
        if not isinstance(svar, dict):
            raise SkriveFejl("uventet svar fra Holdsport")
        if svar.get("errors"):
            tekst = "; ".join(str((e or {}).get("message") or "?") if isinstance(e, dict)
                              else str(e) for e in svar["errors"])
            raise SkriveFejl(f"Holdsport: {tekst[:300]}")
        data = svar.get("data")
        if not isinstance(data, dict) or not data:
            raise SkriveFejl("Holdsport svarede tomt – app-API'et afviste robotten")
        return data

    def log_ind(self):
        if self.token:
            return self.token
        try:
            data = self.gql(LOG_IND, {"username": self.bruger, "password": self.kode}, login=False)
        except SkriveFejl as e:
            raise SkriveFejl(f"login til Holdsports app blev afvist ({e})") from None
        token = str((data.get("SignIn") or {}).get("access_token") or "").strip()
        if not token:
            raise SkriveFejl("login til Holdsports app blev afvist – hemmeligheden HOLDSPORT_USER "
                             "skal være dit Holdsport-brugernavn, ikke din e-mail")
        self.token = token
        return token

    def skift_hold(self, hold_id):
        """Holdsport skriver altid på 'det aktuelle hold'. Skift, og tjek at det lykkedes."""
        if self.hold == str(hold_id):
            return
        self.hold = None
        data = self.gql(SKIFT_HOLD, {"team": int(hold_id)})
        hold = ((data.get("ChangeCurrentTeam") or {}).get("team") or {})
        if str(hold.get("id")) != str(hold_id):
            raise SkriveFejl(f"Holdsport skiftede ikke til hold {hold_id} "
                             f"(svarede {hold.get('id') or 'intet'}) – intet er skrevet")
        self.hold = str(hold_id)

    def typer(self, hold_id):
        data = self.gql(TYPER, {"team": int(hold_id)})
        return [t for t in data.get("activities_event_types") or [] if isinstance(t, dict)]

    def laes(self, akt_id):
        a = self.gql(LAES, {"id": int(akt_id)}).get("activity")
        if not isinstance(a, dict) or not a.get("id"):
            raise SkriveFejl(f"aktivitet {akt_id} findes ikke i Holdsport")
        return a

    def flyt(self, akt_id, hold_id, start, slut, nyt=None, kampstart=""):
        """Flytter aktiviteten til start–slut ('ÅÅÅÅ-MM-DD TT:MM', dansk tid). nyt: andre felter,
        der skal ændres (fx event_type_id). kampstart: den nye linje "Kampstart kl. …", som
        erstatter den gamle i kommentaren – resten af kommentaren og navnet røres ikke.
        Returnerer (gammel start, ny start)."""
        a = self.laes(akt_id)
        hold = {str(h.get("id")) for h in a.get("teams") or [] if isinstance(h, dict)}
        if str(hold_id) not in hold:
            raise SkriveFejl(f"aktivitet {akt_id} hører ikke til holdet – robotten rører den ikke")
        if (a.get("is_repeated_activity") or a.get("is_root_of_repeated_activities")
                or a.get("has_future_repeated_activities")):
            raise SkriveFejl(f"aktivitet {akt_id} gentages – robotten rører den ikke")
        if a.get("is_payment_activity"):
            raise SkriveFejl(f"aktivitet {akt_id} er en betalingsaktivitet – robotten rører den ikke")
        ind = _input(a)
        gl_start = ind.get("start_time", "")
        try:
            delta = _dt(start) - _dt(gl_start)
        except ValueError:
            delta = timedelta(0)
        if delta:
            # mødetid og tilmeldingsfrist følger med aktiviteten
            if ind.get("pickup_time"):
                try:
                    ind["pickup_time"] = (_dt(f"{gl_start[:10]} {ind['pickup_time'][:5]}")
                                          + delta).strftime("%H:%M")
                except ValueError:
                    pass
            for _, dato, kl in TIDSFELTER:
                if ind.get(dato) and ind.get(kl):
                    try:
                        ny = _dt(f"{ind[dato]} {ind[kl]}") + delta
                        ind[dato], ind[kl] = ny.strftime("%Y-%m-%d"), ny.strftime("%H:%M")
                    except ValueError:
                        pass
        ind["start_time"], ind["end_time"] = start, slut
        if kampstart and ind.get("comment"):
            ind["comment"] = "\n".join(kampstart if l.strip().startswith("Kampstart kl.") else l
                                       for l in ind["comment"].split("\n"))
        ind.update(nyt or {})
        self.skift_hold(hold_id)
        ny = (self.gql(RET, {"input": ind}).get("UpdateActivity") or {}).get("activity") or {}
        faar = vaegur((ny.get("starttime") or {}).get("iso8601"))
        if faar != start:
            raise SkriveFejl(f"Holdsport gemte ikke det nye tidspunkt for aktivitet {akt_id} "
                             f"(svarede {faar or 'intet'})")
        if "event_type_id" in (nyt or {}) and str((ny.get("event_type") or {}).get("id")) \
                != str(nyt["event_type_id"]):
            raise SkriveFejl(f"Holdsport flyttede aktivitet {akt_id}, men gemte ikke "
                             "aktivitetstypen")
        return gl_start, faar

    def saet_type(self, akt_id, hold_id, type_id):
        """Giver aktiviteten aktivitetstypen type_id og ændrer intet andet. Returnerer den gamle
        types id – eller None, hvis den allerede havde typen (så skrives der intet)."""
        a = self.laes(akt_id)
        gl = (a.get("event_type") or {}).get("id")
        if str(gl) == str(type_id):
            return None
        hold = {str(h.get("id")) for h in a.get("teams") or [] if isinstance(h, dict)}
        if str(hold_id) not in hold:
            raise SkriveFejl(f"aktivitet {akt_id} hører ikke til holdet – robotten rører den ikke")
        if (a.get("is_repeated_activity") or a.get("is_root_of_repeated_activities")
                or a.get("has_future_repeated_activities")):
            raise SkriveFejl(f"aktivitet {akt_id} gentages – robotten rører den ikke")
        if a.get("is_payment_activity"):
            raise SkriveFejl(f"aktivitet {akt_id} er en betalingsaktivitet – robotten rører den ikke")
        ind = _input(a)
        ind["event_type_id"] = _tal(type_id)
        self.skift_hold(hold_id)
        ny = (self.gql(RET, {"input": ind}).get("UpdateActivity") or {}).get("activity") or {}
        if str((ny.get("event_type") or {}).get("id")) != str(type_id):
            raise SkriveFejl(f"Holdsport gemte ikke aktivitetstypen for aktivitet {akt_id}")
        if vaegur((ny.get("starttime") or {}).get("iso8601")) != ind.get("start_time", ""):
            raise SkriveFejl(f"Holdsport ændrede tidspunktet for aktivitet {akt_id}, da typen "
                             "blev sat – tjek den")
        return gl if gl is not None else ""

    def opret(self, hold_id, felter, skabelon=None):
        """Opretter en aktivitet på holdet. felter: name, start_time, end_time, place, comment,
        max_number_of_attendees (og evt. event_type_id). skabelon: en af holdets andre tjanser
        (fra laes); den nye arver dens tilmeldingstype og påmindelser.
        Returnerer (aktivitetens nummer, advarsel) – advarsel er tom, når alt passer. Fejler det,
        før noget er oprettet, kommer en SkriveFejl."""
        ind, ekstra = dict(felter), {}
        if skabelon:
            s = _input(skabelon)
            ekstra = {k: s[k] for k in ARVES if k in s}
            if "event_type_id" not in ind and "event_type_id" in s:
                ind["event_type_id"] = s["event_type_id"]
        self.skift_hold(hold_id)
        try:
            data = self.gql(OPRET, {"input": {**ind, **ekstra}})
        except SkriveFejl as e:
            # Kender Holdsport ikke et af de arvede felter, afvises hele forespørgslen, før noget
            # er oprettet – så prøves igen uden dem. Andre fejl prøves ikke igen.
            tekst = str(e).lower()
            if not ekstra or not any(k.lower() in tekst
                                     for k in list(ekstra) + ["input", "argument", "variable"]):
                raise
            data = self.gql(OPRET, {"input": ind})
        ny = (data.get("CreateActivity") or {}).get("activity") or {}
        if not ny.get("id"):
            raise SkriveFejl("Holdsport oprettede ikke aktiviteten (svarede intet)")
        hold = {str(h.get("id")) for h in ny.get("teams") or [] if isinstance(h, dict)}
        if hold and str(hold_id) not in hold:
            return ny["id"], (f"Holdsport lagde den på et andet hold ({', '.join(sorted(hold))})"
                              " – slet den dér")
        faar = vaegur((ny.get("starttime") or {}).get("iso8601"))
        if faar and faar != felter["start_time"]:
            return ny["id"], f"Holdsport lagde den på et andet tidspunkt ({faar})"
        return ny["id"], ""


def _input(a):
    """Alt det, en aktivitet har, som input til UpdateActivity – Holdsport nulstiller de felter,
    der ikke kommer med."""
    ind = {"id": _tal(a["id"]), "name": (a.get("name") or "").strip()}
    for felt, navn in INDSTILLINGER:
        if a.get(felt) is not None:
            ind[navn] = a[felt]
    for felt, dato, kl in TIDSFELTER:
        v = vaegur((a.get(felt) or {}).get("iso8601"))
        if v:
            ind[dato], ind[kl] = v[:10], v[11:]
    st = vaegur((a.get("starttime") or {}).get("iso8601"))
    sl = vaegur((a.get("endtime") or {}).get("iso8601"))
    if st:
        ind["start_time"] = st
    if sl:
        ind["end_time"] = sl
    if str(a.get("pickup_time") or "").strip():
        ind["pickup_time"] = str(a["pickup_time"]).strip()
    if (a.get("event_type") or {}).get("id") is not None:
        ind["event_type_id"] = _tal(a["event_type"]["id"])
    for felt, navn in (("place", "place"), ("comment", "comment"),
                       ("max_attender", "max_number_of_attendees")):
        if a.get(felt) is not None:
            ind[navn] = a[felt]
    return ind


def _gange(liste, nu, vindue):
    """Hvor mange af de gemte tidspunkter, der ligger inden for vinduet."""
    ud = 0
    for t in liste or []:
        try:
            if nu - datetime.fromisoformat(t) < vindue:
                ud += 1
        except (TypeError, ValueError):
            continue
    return ud


def tjans_tekst(t):
    """'H3 søn 11/10 kl. 10.30 (Aalborg Volleyball.2 - Aalborg Volleyball)'."""
    try:
        d = _dt(t["start"])
        tid = f"{UGEDAGE[d.weekday()]} {d.day}/{d.month} kl. {d:%H.%M}"
    except (KeyError, TypeError, ValueError):
        tid = t.get("start", "")
    return f"{t['tjans']} {tid}" + (f" ({t['kamp']})" if t.get("kamp") else "")


def _kort(t):
    return {"tjans": t["tjans"], "kampnr": t["kampnr"], "start": t["start"],
            "kamp": t.get("kamp", ""), "navn": t["navn"], "hvilken": tjans_tekst(t)}


def _norm(s):
    s = (s or "").lower()
    for a, b in (("æ", "ae"), ("ø", "oe"), ("å", "aa")):
        s = s.replace(a, b)
    return " ".join(s.replace("/", " ").replace("-", " ").split())


def tjans_type(typer):
    """Holdets aktivitetstype til tjanser: den, der hedder "Tjans", ellers en med "tjans" i navnet
    (fx "Tjans/opgave"), ellers en med "opgave". Returnerer (id, navn) – eller None."""
    bedst, point = None, 0
    for t in typer or []:
        n = _norm(t.get("name"))
        p = (4 if n == "tjans" else 3 if n.startswith("tjans") else 2 if "tjans" in n
             else 1 if "opgave" in n else 0)
        if p > point and t.get("id") is not None:
            bedst, point = (_tal(t["id"]), (t.get("name") or "").strip()), p
    return bedst


def ret(hs, tjanser, skrevet, nu, klient, tilladt=True):
    """Retter Holdsport efter tjanselisten.

    hs:       holdsport.py's resultat (fundne, mangler, hold) fra denne kørsel
    tjanser:  {nøgle: {tjans, kampnr, kamp, start, slut, navn, beskrivelse, sted, antal}} –
              start/slut som 'ÅÅÅÅ-MM-DD TT:MM' i dansk tid
    skrevet:  det, robotten har skrevet før (fra historikken): {"oprettet": {nøgle: [tid]},
              "flyttet": {aktivitet: [tid]}, "type_ok": {aktivitet: tid}, "typer": {hold: navn}}
    Returnerer (rapport, skrevet) – rapporten kommer i status.json under holdsport → rettet."""
    rapport = {"slaaet_til": bool(tilladt), "flyttet": [], "oprettet": [], "fejl": [],
               "udskudt": [], "givet_op": [], "type_sat": [], "type_venter": 0, "typer": {},
               "optaget": []}
    gemt = skrevet or {}
    skrevet = {art: {str(k): [t for t in v if _gange([t], nu, vindue)]
                     for k, v in (gemt.get(art) or {}).items() if isinstance(v, list)}
               for art, vindue in (("oprettet", GENOPRET), ("flyttet", SAMME_VINDUE))}
    skrevet = {art: {k: v for k, v in d.items() if v} for art, d in skrevet.items()}
    # aktiviteter, der havde tjans-typen, da robotten sidst tjekkede – tjekkes igen efter et døgn
    skrevet["type_ok"] = {str(k): v for k, v in (gemt.get("type_ok") or {}).items()
                          if isinstance(v, str) and _gange([v], nu, TYPE_TJEKKET)}
    skrevet["typer"] = {k: v for k, v in (gemt.get("typer") or {}).items() if isinstance(v, str)}
    rapport["typer"] = dict(skrevet["typer"])
    if not hs.get("aktiveret") or hs.get("fejl"):
        return rapport, skrevet
    nu_dk = nu.astimezone(DK).strftime("%Y-%m-%d %H:%M")
    hold = {p.get("kode"): p for p in hs.get("hold") or []}

    # Det, der skal rettes: kun kommende tjanser, på hold robotten kunne læse
    flyt, opret, typ = [], [], []
    for f in hs.get("fundne") or []:
        t = tjanser.get(f"{f['kampnr'] or f['start'][:10]}-{f['tjans']}")
        p = hold.get(f["tjans"]) or {}
        if not t or t["start"] <= nu_dk or not f.get("aktivitet") or not p.get("id"):
            continue
        if f.get("hs_start") and f["hs_start"] != t["start"]:
            flyt.append((t, f, p))
        elif str(f["aktivitet"]) not in skrevet["type_ok"]:
            typ.append((t, f, p))
    for m in hs.get("mangler") or []:
        n = f"{m['kampnr'] or m['start'][:10]}-{m['tjans']}"
        t = tjanser.get(n)
        p = hold.get(m["tjans"]) or {}
        # opret kun, hvis hele holdets kalender kunne læses – ellers kan den bare være overset
        if not t or t["start"] <= nu_dk or not p.get("id") or p.get("fejl") \
                or p.get("ufuldstaendig"):
            continue
        if m.get("optaget"):
            # en anden aktivitet ligger på tidspunktet: måske tjansen med et andet navn og uden
            # kampnummer – så ingen ny, men besked
            rapport["optaget"].append({**_kort(t), "aktivitet_navn": m["optaget"]})
            continue
        opret.append((n, t, p))
    flyt.sort(key=lambda x: x[0]["start"])
    opret.sort(key=lambda x: x[1]["start"])
    typ.sort(key=lambda x: x[0]["start"])
    if not flyt and not opret and not typ:
        return rapport, skrevet
    if not tilladt:
        rapport["udskudt"] = ([{**_kort(t), "hvad": "flyt", "hs_start": f["hs_start"]}
                               for t, f, _ in flyt]
                              + [{**_kort(t), "hvad": "opret"} for _, t, _ in opret])
        return rapport, skrevet

    try:
        klient.log_ind()
    except SkriveFejl as e:
        rapport["fejl"].append({"fejl": str(e)})
        return rapport, skrevet

    typer = {}                       # hold-id -> (id, navn), None (ingen) eller False (ukendt)

    def holdets_type(p):
        hid = str(p["id"])
        if hid not in typer:
            try:
                typer[hid] = tjans_type(klient.typer(p["id"]))
            except SkriveFejl:
                typer[hid] = False
            if typer[hid] is not False:
                navn = typer[hid][1] if typer[hid] else ""
                skrevet["typer"][p.get("kode")] = rapport["typer"][p.get("kode")] = navn
        return typer[hid] or None

    stop = False                     # holdskiftet slog fejl: skriv intet mere i denne kørsel
    for t, f, p in flyt:
        akt = str(f["aktivitet"])
        if stop or len(rapport["flyttet"]) >= MAKS_FLYT:
            rapport["udskudt"].append({**_kort(t), "hvad": "flyt", "hs_start": f["hs_start"]})
            continue
        if _gange(skrevet["flyttet"].get(akt), nu, SAMME_VINDUE) >= MAKS_SAMME:
            rapport["givet_op"].append({**_kort(t), "hs_start": f["hs_start"], "aktivitet": akt})
            continue
        tt = holdets_type(p)
        kampstart = next((l for l in t["beskrivelse"].split("\n")
                          if l.startswith("Kampstart kl.")), "")
        try:
            fra, til = klient.flyt(akt, p["id"], t["start"], t["slut"],
                                   {"event_type_id": tt[0]} if tt else None, kampstart)
        except SkriveFejl as e:
            rapport["fejl"].append({**_kort(t), "fejl": str(e), "aktivitet": akt})
            stop = "skiftede ikke" in str(e)
            continue
        skrevet["flyttet"].setdefault(akt, []).append(nu.isoformat())
        if tt:
            skrevet["type_ok"][akt] = nu.isoformat()
        rapport["flyttet"].append({**_kort(t), "fra": fra or f["hs_start"], "til": til,
                                   "aktivitet": akt, "holdsport": p.get("holdsport", ""),
                                   "kilde": f.get("kilde", "")})

    skabeloner = {}
    for n, t, p in opret:
        if stop or len(rapport["oprettet"]) >= MAKS_OPRET:
            rapport["udskudt"].append({**_kort(t), "hvad": "opret"})
            continue
        if _gange(skrevet["oprettet"].get(n), nu, GENOPRET):
            # robotten har oprettet den for nylig, og nu er den væk: nogen har slettet den
            rapport["givet_op"].append({**_kort(t), "oprettet_foer": True})
            continue
        hid = str(p["id"])
        if hid not in skabeloner:            # holdets egne tjanser er skabelon for den nye
            skabeloner[hid] = None
            for g in hs.get("fundne") or []:
                if g["tjans"] == t["tjans"] and g.get("kilde") in ("kalender", "robot") \
                        and g.get("aktivitet"):
                    try:
                        skabeloner[hid] = klient.laes(g["aktivitet"])
                    except SkriveFejl:
                        pass
                    break
        tt = holdets_type(p)
        try:
            felter = {"name": t["navn"], "start_time": t["start"], "end_time": t["slut"],
                      "place": t["sted"], "comment": f"{t['beskrivelse']}\n\n{ROBOT_MAERKE}",
                      "max_number_of_attendees": int(t["antal"])}
            if tt:
                felter["event_type_id"] = tt[0]
            akt, advarsel = klient.opret(p["id"], felter, skabeloner[hid])
        except SkriveFejl as e:
            rapport["fejl"].append({**_kort(t), "fejl": str(e)})
            stop = "skiftede ikke" in str(e)
            continue
        skrevet["oprettet"].setdefault(n, []).append(nu.isoformat())
        rapport["oprettet"].append({**_kort(t), "aktivitet": str(akt),
                                    "holdsport": p.get("holdsport", "")})
        if advarsel:
            rapport["fejl"].append({**_kort(t), "fejl": f"Aktivitet {akt}: {advarsel}",
                                    "aktivitet": str(akt)})
            stop = stop or "andet hold" in advarsel

    # Aktivitetstypen: kommende tjanser, der ikke har holdets tjans-type, får den
    laest = 0
    for t, f, p in typ:
        tt = holdets_type(p) if not stop else None
        if not tt:
            continue
        if len(rapport["type_sat"]) >= MAKS_TYPE or laest >= MAKS_TYPE_LAES:
            rapport["type_venter"] += 1
            continue
        akt = str(f["aktivitet"])
        laest += 1
        try:
            gl = klient.saet_type(akt, p["id"], tt[0])
        except SkriveFejl as e:
            rapport["fejl"].append({**_kort(t), "fejl": f"aktivitetstypen: {e}", "aktivitet": akt})
            stop = True            # fejler det, er det nok det samme for dem alle – prøv i morgen
            continue
        skrevet["type_ok"][akt] = nu.isoformat()
        if gl is not None:
            rapport["type_sat"].append({**_kort(t), "aktivitet": akt, "type": tt[1],
                                        "holdsport": p.get("holdsport", "")})
    return rapport, skrevet
