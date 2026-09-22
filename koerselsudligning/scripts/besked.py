#!/usr/bin/env python3
"""Ét GitHub-issue pr. sæson med den forventede kørselsudligning.

Oprettes første gang en sæson er regnet (GitHub sender en mail), og får en
kommentar, hvis estimatet flytter sig mindst GRAENSE kr — fx når en pokalrunde
er trukket, slutspillet er lagt ud, eller et hold trækker sig. Forrige sæsons
issue lukkes, når en ny sæson dukker op."""
import json, os, re, subprocess, sys

LABEL = "koerselsudligning"
GRAENSE = 500
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELE = (("grundspil", "Grundspil"), ("pokal_total", "Pokal"), ("slutspil_total", "Slutspil"))


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def kr(v):
    s = f"{abs(v):,.0f}".replace(",", ".")
    return ("+" if v > 0 else "−" if v < 0 else "") + s


def dele(st):
    """{"grundspil": 48722, "pokal_total": 1807, ...} — kun de dele, der er regnet."""
    ud = {"grundspil": st.get("grundspil", st.get("total"))}
    if any(r.get("status") == "beregnet" for r in st.get("pokal") or []):
        ud["pokal_total"] = st.get("pokal_total") or 0
    if st.get("slutspil"):
        ud["slutspil_total"] = st.get("slutspil_total") or 0
    return {k: round(v) for k, v in ud.items() if v is not None}


def krop(st, side):
    saeson, total = st["saeson"], st["total"]
    d = dele(st)
    linjer = [f"**Forventet kørselsudligning {saeson}: {kr(total)} kr** "
              f"({'kreditnota — klubben får penge' if total >= 0 else 'faktura — klubben betaler'})",
              "", " · ".join(f"{navn} {kr(d[k])} kr" for k, navn in DELE if k in d),
              "", "**Grundspil**", "", "| Hold | Række | Udligning |", "|---|---|---:|"]
    linjer += [f"| {h['kode']} | {h['raekke']} · {h['pulje']} | {kr(h['udligning'])} kr |"
               for h in st["klubhold"]]

    pokal = []
    for r in st.get("pokal") or []:
        if r.get("status") != "beregnet":
            pokal.append(f"| {r['raekke']} | | kampene er ikke lagt ud endnu | |")
            continue
        for h in r["hold"]:
            if h["klub"]:
                kamp = (f"ude hos {h['ture'][0]['modstander']}" if h.get("ture") else
                        f"hjemme mod {h['hjemmekampe'][0]['modstander']}" if h.get("hjemmekampe")
                        else "")
                pokal.append(f"| {r['raekke']} | {h.get('kode') or h['hold']} | {kamp} | "
                             f"{kr(h['udligning'])} kr |")
    if pokal:
        linjer += ["", "**Pokal** (hver runde for sig)", "",
                   "| Runde | Hold | Kamp | Udligning |", "|---|---|---|---:|"] + pokal

    slut = [f"| {r['raekke']} | {h.get('kode') or h['hold']} | {h['kampe']} | {kr(h['udligning'])} kr |"
            for r in st.get("slutspil") or [] for h in r["hold"] if h["klub"]]
    if slut:
        linjer += ["", "**Slutspil**", "", "| Slutspil | Hold | Kampe | Udligning |",
                   "|---|---|---:|---:|"] + slut

    if st.get("advarsler"):
        linjer += ["", "**Værd at kigge på:**"] + [f"- {a}" for a in st["advarsler"]]
    if side:
        linjer += ["", f"Hele beregningen: {side}"]
    marker = " ".join([f"total: {round(total)}"] + [f"{k}: {v}" for k, v in d.items()])
    linjer += ["", f"<!-- {marker} -->"]
    return "\n".join(linjer)


def aendring(foer_krop, st):
    """Kort forklaring af, hvilke dele der har flyttet sig."""
    d, ud = dele(st), []
    if not re.search(r"\bgrundspil: -?\d+", foer_krop or ""):
        return ""                          # issue fra før delene blev gemt
    for k, navn in DELE:
        m = re.search(rf"\b{k}: (-?\d+)", foer_krop or "")
        gl = int(m.group(1)) if m else None
        ny = d.get(k)
        if ny is not None and (gl is None or abs(ny - gl) >= 1) and not (gl is None and ny == 0):
            ud.append(f"{navn.lower()} {kr(gl) if gl is not None else 'ikke regnet'} → {kr(ny)}")
    return f" ({', '.join(ud)})" if ud else ""


def main():
    sti = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "status.json")
    st = json.load(open(sti, encoding="utf-8"))
    if st.get("total") is None or st.get("fejl"):
        print("Ingen ny beregning — ingen besked")
        return 0
    saeson, total = st["saeson"], st["total"]
    titel = f"Kørselsudligning {saeson}"
    tekst = krop(st, os.environ.get("SIDE", ""))

    gh("label", "create", LABEL, "--color", "1B4F9C",
       "--description", "Forventet kørselsudligning fra Volleyball Danmark")
    fundet = gh("issue", "list", "--state", "all", "--label", LABEL,
                "--json", "number,title,state,body", "--limit", "50")
    issues = json.loads(fundet.stdout or "[]")
    denne = next((i for i in issues if i["title"] == titel), None)

    for i in issues:                       # luk tidligere sæsoner
        if i is not denne and i["state"] == "OPEN":
            gh("issue", "comment", str(i["number"]), "--body",
               f"Ny sæson ({saeson}) er regnet — lukker denne.")
            gh("issue", "close", str(i["number"]))

    if not denne:
        r = gh("issue", "create", "--title", titel, "--label", LABEL, "--body", tekst)
        print("Issue oprettet:", r.stdout.strip() or r.stderr.strip())
        return 0

    m = re.search(r"<!-- total: (-?\d+)", denne.get("body") or "")
    foer = int(m.group(1)) if m else None
    if foer is None or abs(round(total) - foer) >= GRAENSE:
        gh("issue", "edit", str(denne["number"]), "--body", tekst)
        if foer is not None:
            gh("issue", "comment", str(denne["number"]), "--body",
               f"Estimatet er ændret fra {kr(foer)} kr til {kr(total)} kr"
               f"{aendring(denne.get('body'), st)}.")
        print(f"Issue #{denne['number']} opdateret")
    else:
        print(f"Issue #{denne['number']} uændret ({kr(total)} kr)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
