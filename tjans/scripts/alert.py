#!/usr/bin/env python3
# sti: tjans/scripts/alert.py
"""Åbner, opdaterer eller lukker ét GitHub-issue afhængigt af, om der er huller
i tjansedækningen – og sender en alarm til telefonen (ntfy), når noget nyt kræver handling,
når robotten selv har rettet noget i Holdsport, eller når en tjans inden for 3 døgn står
forkert. Issuet tildeles og @-nævner ejeren af repoet, så GitHub også giver besked."""
import json, os, subprocess, sys, urllib.request

TITEL = "Tjanser: noget mangler"
LABEL = "tjans"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gh(*args, **kw):
    return subprocess.run(["gh", *args], capture_output=True, text=True, **kw)


def indstilling(navn, standard):
    """En indstilling fra scripts/indstillinger.py – standard, hvis den ikke står der."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import indstillinger
        return getattr(indstillinger, navn, standard)
    except ImportError:
        return standard


def push(st, side):
    """Alarm på telefonen med ntfy (ALARM_NTFY i scripts/indstillinger.py). Hvad der skal
    sendes, har build.py regnet ud (status.json → "alarm"). Fejler det, kører resten videre."""
    a = st.get("alarm") or {}
    emne = (indstilling("ALARM_NTFY", "") or "").strip()
    if not a.get("send") or not emne:
        print("Ingen alarm til telefonen" + ("" if emne else " (ALARM_NTFY er tom)"))
        return
    problem = a.get("titel", "").startswith("Tjanser: noget nyt")
    data = {"topic": emne, "title": a.get("titel") or "Tjanser",
            "message": "\n".join((a.get("linjer") or [])[:10]) or (a.get("titel") or "Tjanser"),
            "priority": 5 if a.get("akut") else 4 if problem else 3,
            "tags": (["rotating_light"] if a.get("akut") else ["warning"] if problem else
                     ["wrench"] if a.get("rettet") else ["white_check_mark"])}
    if side:
        data["click"] = side
    req = urllib.request.Request("https://ntfy.sh", data=json.dumps(data).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Alarm sendt til telefonen ({r.status}): {data['title']}")
    except Exception as exc:                       # noqa: BLE001 – issuet skal stadig med
        print(f"Kunne ikke sende alarm til telefonen: {exc}", file=sys.stderr)


def indhold(tekst):
    """Issuets tekst uden første linje, så et nyt tidspunkt alene ikke giver en kommentar
    (og en mail) ved hver kørsel."""
    return (tekst or "").replace("\r\n", "\n").split("\n", 1)[-1].strip()


def main():
    st = json.load(open(os.path.join(ROOT, "docs", "status.json"), encoding="utf-8"))
    huller, forsvundne = st["huller"], st["forsvundne"]
    hs = st.get("holdsport") or {}
    slettet = hs.get("mangler", [])
    side = os.environ.get("SIDE", "")
    kilde = st.get("tjanskilde") or ""
    arkfejl = kilde.split(": ", 1)[-1] if "Google-arket kunne ikke læses" in kilde else ""
    konflikter = st.get("konflikter") or []
    genbrugt = hs.get("genbrugt") or []
    forkert_tid = hs.get("forkert_tid") or []     # Holdsport har ikke flyttet tjansen med kampen
    dobbelt = st.get("dobbelt_tjans") or []       # samme hold, to tjanser på samme tid
    hsfejl = hs.get("fejl") if hs.get("aktiveret") else None
    rettet = hs.get("rettet") or {}               # det, robotten selv har rettet i Holdsport
    skrivefejl = (rettet.get("fejl") or []) + (rettet.get("givet_op") or [])
    ejer = os.environ.get("GITHUB_REPOSITORY_OWNER") or "Brebnhi"

    push(st, side)

    gh("label", "create", LABEL, "--color", "B60205",
       "--description", "Huller i tjansedækningen")

    fundet = gh("issue", "list", "--state", "open", "--label", LABEL,
                "--json", "number,body", "--limit", "1")
    aabne = json.loads(fundet.stdout or "[]")

    if not (huller or forsvundne or slettet or arkfejl or konflikter or genbrugt or forkert_tid
            or dobbelt or hsfejl or skrivefejl):
        if aabne:
            nr = str(aabne[0]["number"])
            gh("issue", "comment", nr, "--body",
               "Alt er i orden igen: hver hjemmekamp har et hold på tjans, "
               "og alle tjanser ligger i Holdsport. Lukker automatisk.")
            gh("issue", "close", nr)
            print("Ingen huller – issue lukket")
        else:
            print("Ingen huller")
        return

    linjer = [f"Tjekket {st['opdateret']} mod {st['feed_kampe']} kampe i kampprogrammet.", ""]
    if hsfejl:
        linjer += ["## Robotten kunne ikke tjekke Holdsport", "",
                   f"{hsfejl}. Indtil det virker igen, ser robotten ikke, om tjanserne står "
                   "rigtigt i Holdsport.", ""]
    if skrivefejl:
        linjer += [f"## Robotten kunne ikke rette {len(skrivefejl)} ting i Holdsport", "",
                   "Robotten prøver igen ved næste kørsel.", "",
                   "| Tjans | Hvad der gik galt |", "|---|---|"]
        for e in rettet.get("fejl") or []:
            linjer.append(f"| {e.get('hvilken') or 'Holdsport'} | {e['fejl']} |")
        for g in rettet.get("givet_op") or []:
            linjer.append(f"| {g['hvilken']} | " + (
                "Robotten oprettede den, men den er slettet igen. Skal den ikke være, så fjern "
                "den fra tjanselisten." if g.get("oprettet_foer") else
                f"Bliver flyttet tilbage i Holdsport igen og igen (aktivitet {g.get('aktivitet')})"
                " – ret den i Holdsport.") + " |")
        linjer.append("")
    if arkfejl:
        linjer += ["## Google-arket med tjanselisten kunne ikke læses", "",
                   f"{arkfejl}. Robotten bruger `data/tjanser.csv`, så rettelser i arket når "
                   "ikke Holdsport. Tjek, at den rigtige fane er udgivet, og at overskriftsrækken "
                   "har Kampnr. og Tjans.", ""]
    if huller:
        linjer += [f"## {len(huller)} hjemmekamp(e) uden hold på tjans", "",
                   "| Kampnr. | Dato | Kamp | Række | Sted |", "|---|---|---|---|---|"]
        linjer += [f"| {h['kampnr']} | {h['start']} | {h['kamp']} | {h['raekke']} | {h['sted']} |"
                   for h in huller]
        linjer.append("")
    if forsvundne:
        linjer += [f"## {len(forsvundne)} tjans(er) hvor kampen ikke længere findes", "",
                   "| Kampnr. | Dato i ark | Kamp | Tjans |", "|---|---|---|---|"]
        linjer += [f"| {f['kampnr']} | {f['dato']} | {f['kamp']} | {f['tjans']} |"
                   for f in forsvundne]
        linjer.append("")
    if dobbelt:
        linjer += [f"## {len(dobbelt)} gang(e) har et hold to tjanser på samme tid", "",
                   "Holdet kan ikke tage begge. Og står to tjanser på samme tidspunkt i holdets "
                   "kalender, laver Holdsport dem til én aktivitet, så den ene tjans forsvinder. "
                   "Giv den ene tjans til et andet hold i tjanselisten.", "",
                   "| Dato | Hold | Tjans | Samtidig med |", "|---|---|---|---|"]
        linjer += [f"| {d['dato']} | {d['hold']} | {d['tjans1']} | {d['tjans2']} |" for d in dobbelt]
        linjer.append("")
    if konflikter:
        mm = st.get("mellemmand")
        linjer += [f"## {len(konflikter)} tjans(er) oven i holdets egen kamp", "",
                   "Holdet kan ikke nå både egen kamp og tjansen. Byt tjansen i tjanselisten"
                   + (" — eller tryk **Ignorér**, hvis det er i orden." if mm else "."), ""]
        if mm:
            linjer += ["| Dato | Hold | Tjans | Egen kamp | |", "|---|---|---|---|---|"]
        else:
            linjer += ["| Dato | Hold | Tjans | Egen kamp |", "|---|---|---|---|"]
        for k in konflikter:
            raekke = (f"| {k['dato']} | {k['hold']} | kl. {k['tjans_kl']} {k['tjans_kamp']} | "
                      f"kl. {k['egen_kl']} {k['egen_kamp']}{'' if k['hjemme'] else ' (ude)'} |")
            if mm:
                raekke += f" [Ignorér]({side}#ignorer={k['noegle']}) |"
            linjer.append(raekke)
        linjer.append("")
    if forkert_tid:
        linjer += [f"## {len(forkert_tid)} tjans(er) står forkert i Holdsport", "",
                   "Tjansen står på et andet tidspunkt i Holdsport end kampen, eller der ligger en "
                   "ekstra kopi. Robotten flytter selv en tjans, der står forkert – det her kunne "
                   "den ikke. Ret tidspunktet på aktiviteten i Holdsport — eller slet kopien — "
                   "og tjek, om de tilmeldte stadig kan.", "",
                   "| Tjans | Aktivitet | Skal stå (mødetid) | Står i Holdsport | Hold i Holdsport |",
                   "|---|---|---|---|---|"]
        def kopi(r):
            if not r.get("dublet"):
                return ""
            return {"egen": " – ekstra kopi, du selv har oprettet – slet den",
                    "robot": " – ekstra kopi, robotten har oprettet – slet den"}.get(
                        r.get("kilde"), " – ekstra kopi, slet den")
        linjer += [f"| {r['tjans']} | {r['navn']} (kamp {r['kampnr']}) | {r['start']} | "
                   f"{r['hs_start']}{kopi(r)} | {r['holdsport']} |" for r in forkert_tid]
        linjer.append("")
    if slettet:
        linjer += [f"## {len(slettet)} tjans(er) er slettet i Holdsport", "",
                   "| Kampnr. | Mødetid | Aktivitet | Tjans | Hold i Holdsport |",
                   "|---|---|---|---|---|"]
        linjer += [f"| {m['kampnr']} | {m['start']} | {m['navn']}"
                   + (" (var i Holdsport før)" if m.get("foer_fundet") else "")
                   + f" | {m['tjans']} | {m['holdsport']} |" for m in slettet]
        linjer.append("")
    if genbrugt:
        linjer += [f"## Holdsport har genbrugt {len(genbrugt)} tjans(er)", "",
                   "Holdsport har lavet en eksisterende tjans om til en ny, da den hentede "
                   "kalenderen. Tilmeldingerne fulgte med, så de står nu på den forkerte dag. "
                   "Tjek, hvem der er tilmeldt, og om den gamle tjans er kommet igen.", "",
                   "| Hold | Var tjansen | Er nu tjansen | Aktivitet i Holdsport |",
                   "|---|---|---|---|"]
        linjer += [f"| {g['tjans']} | {g['foer_start']} (kamp {g['foer'].split('-')[0]}) | "
                   f"{g['nu_start']} (kamp {g['nu'].split('-')[0]}) | {g['aktivitet']} |"
                   for g in genbrugt]
        linjer.append("")
    # Det, robotten selv har rettet, står på siden og kommer på telefonen – ikke i issuet, så
    # det ikke giver to mails (en når det kommer, en når det forsvinder igen).
    linjer.append("Robotten retter selv det, den kan, i Holdsport. Når resten er rettet – i "
                  "tjanselisten eller i Holdsport – lukker issuet sig selv ved næste kørsel.")
    if side:
        linjer.append(f"\nHele overblikket: {side}")
    krop = "\n".join(linjer) + f"\n\n@{ejer}"      # @-nævnt: GitHub giver ejeren besked

    if aabne:
        nr = str(aabne[0]["number"])
        # Første linje ("Tjekket <tidspunkt> …") skifter ved hver kørsel – den alene er ingen ændring
        if indhold(aabne[0].get("body")) != indhold(krop):
            gh("issue", "edit", nr, "--body", krop)
            gh("issue", "comment", nr, "--body",
               f"@{ejer} Status ændret — se opdateret oversigt ovenfor.")
            print(f"Issue #{nr} opdateret")
        else:
            print(f"Issue #{nr} uændret")
    else:
        r = gh("issue", "create", "--title", TITEL, "--label", LABEL, "--body", krop,
               "--assignee", ejer)
        if r.returncode:                            # kan ejeren ikke tildeles, så uden
            r = gh("issue", "create", "--title", TITEL, "--label", LABEL, "--body", krop)
        print("Issue oprettet:", r.stdout.strip() or r.stderr.strip())


if __name__ == "__main__":
    sys.exit(main())
