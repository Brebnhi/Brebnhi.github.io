#!/usr/bin/env python3
"""Åbner, opdaterer eller lukker ét GitHub-issue afhængigt af, om der er huller
i tjansedækningen. GitHub sender selv mail, når issuet oprettes eller ændres,
så der kommer kun besked, når noget faktisk mangler."""
import json, os, subprocess, sys

TITEL = "Tjanser: noget mangler"
LABEL = "tjans"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gh(*args, **kw):
    return subprocess.run(["gh", *args], capture_output=True, text=True, **kw)


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

    gh("label", "create", LABEL, "--color", "B60205",
       "--description", "Huller i tjansedækningen")

    fundet = gh("issue", "list", "--state", "open", "--label", LABEL,
                "--json", "number,body", "--limit", "1")
    aabne = json.loads(fundet.stdout or "[]")

    if not (huller or forsvundne or slettet or arkfejl or konflikter or genbrugt or forkert_tid):
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
        linjer += [f"## {len(forkert_tid)} tjans(er) står på et forkert tidspunkt i Holdsport", "",
                   "Kampen er flyttet, men Holdsport har ikke flyttet tjansen med (eller der ligger "
                   "en ekstra kopi på det gamle tidspunkt). Ret tidspunktet på aktiviteten i "
                   "Holdsport — eller slet kopien — og tjek, om de tilmeldte stadig kan.", "",
                   "| Tjans | Aktivitet | Skal stå (mødetid) | Står i Holdsport | Hold i Holdsport |",
                   "|---|---|---|---|---|"]
        linjer += [f"| {r['tjans']} | {r['navn']} (kamp {r['kampnr']}) | {r['start']} | "
                   f"{r['hs_start']}{' – ekstra kopi, slet den' if r.get('dublet') else ''} | "
                   f"{r['holdsport']} |" for r in forkert_tid]
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
    linjer.append("Ret tjanselisten eller genopret aktiviteten i Holdsport, "
                  "så lukker issuet sig selv ved næste kørsel.")
    if side:
        linjer.append(f"\nHele overblikket: {side}")
    krop = "\n".join(linjer)

    if aabne:
        nr = str(aabne[0]["number"])
        # Første linje ("Tjekket <tidspunkt> …") skifter ved hver kørsel – den alene er ingen ændring
        if indhold(aabne[0].get("body")) != indhold(krop):
            gh("issue", "edit", nr, "--body", krop)
            gh("issue", "comment", nr, "--body", "Status ændret — se opdateret oversigt ovenfor.")
            print(f"Issue #{nr} opdateret")
        else:
            print(f"Issue #{nr} uændret")
    else:
        r = gh("issue", "create", "--title", TITEL, "--label", LABEL, "--body", krop)
        print("Issue oprettet:", r.stdout.strip() or r.stderr.strip())


if __name__ == "__main__":
    sys.exit(main())
