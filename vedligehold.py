#!/usr/bin/env python3
# sti: tjans/scripts/vedligehold.py
"""Holder klubbens værktøjer kørende fra sæson til sæson.

Kører i natkørslen efter kørselsudligningen og før siden lægges ud:

1. Natkørslen holdes i live. GitHub slår planlagte kørsler fra, når et offentligt
   repo har været uden aktivitet i 60 dage. Robotten slår workflowet til hver nat
   (som at trykke Enable workflow, det nulstiller uret), og er der ikke committet
   i 50 dage, skriver den også et livstegn i data/puls.txt.
2. Påmindelser til en ny sæson som GitHub-issues med labelen "ny sæson" – GitHub
   sender en mail, når et issue oprettes. Dem robotten selv kan tjekke (tjanseliste,
   takster, kontingentsatser, turpriser), lukker sig selv, når det er gjort. Try-out og budget
   kan robotten ikke se – de issues lukker du selv, når du er færdig.
3. docs/paamindelser.json, som startsiden viser øverst.

Prøv uden at røre GitHub:  python scripts/vedligehold.py --test --nu 2027-08-15
"""
import argparse, hashlib, json, os, re, subprocess, sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # tjans/
REPO_ROD = os.path.dirname(ROOT)
DK = ZoneInfo("Europe/Copenhagen")
REPO = os.environ.get("GITHUB_REPOSITORY", "Brebnhi/Brebnhi.github.io")
SIDE = (os.environ.get("SIDE") or "https://brebnhi.github.io/").rstrip("/") + "/"
ISSUES = f"https://github.com/{REPO}/issues"
LABEL = "ny sæson"
TRYOUT_GUIDE = "https://docs.google.com/document/d/19cpzGXU_s858MQe_A-r4YyGGtSu8ppPURRt6Rq8Q1bY/edit"
LIVSTEGN_DAGE = 50


# ----------------------------------------------------------------------------- hjælpere
def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)


def laes_json(*sti):
    try:
        return json.load(open(os.path.join(*sti), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kort(start):
    """2027 -> "27/28"."""
    return f"{start % 100:02d}/{(start + 1) % 100:02d}"


def lang(start):
    """2027 -> "2027/28"."""
    return f"{start}/{(start + 1) % 100:02d}"


def startaar(saeson):
    """"2027/28" eller "27/28" -> 2027. Ukendt -> None."""
    m = re.match(r"\s*(\d{2,4})\s*/", str(saeson or ""))
    if not m:
        return None
    aar = int(m.group(1))
    return aar + 2000 if aar < 100 else aar


def maerke(noegle, tekst=""):
    """Skjult mærke sidst i issuet: hvilken påmindelse det er, og et fingeraftryk af
    teksten, så robotten kun skriver issuet om, når indholdet faktisk har ændret sig."""
    aftryk = hashlib.sha1(tekst.encode()).hexdigest()[:8] if tekst else ""
    return f"<!-- påmindelse: {noegle} {aftryk}".rstrip() + " -->"


# ----------------------------------------------------------------------------- påmindelser
def tjanseliste(nu):
    """Kampprogrammet for en ny sæson er lagt ud, men tjanselisten er fra sidste sæson."""
    vd = laes_json(ROOT, "docs", "koerselsudligning", "status.json").get("saeson")
    tj = laes_json(ROOT, "docs", "status.json")
    vd_start, tj_start = startaar(vd), tj.get("saeson_start") or startaar(tj.get("saeson"))
    if not vd_start:
        return None
    aktiv = tj_start is None or vd_start > tj_start
    gl = f"stadig fra {lang(tj_start)}" if tj_start else "tom"
    if tj.get("tjanskilde") == "Google Sheet":
        hvor = ("Lav den i det samme Google-ark som sidst (gem evt. en kopi af den gamle "
                "først). Robotten læser arket hver nat.")
    else:
        hvor = ("Lav den i Google Sheets som sidst. Udgiver du arket som CSV og lægger "
                "linket i `SHEET_CSV_URL`, læser robotten det selv hver nat — se "
                "«Tjanselisten» i `tjans/README.md`.")
    tekst = f"""Volleyball Danmark har lagt kampprogrammet for **{lang(vd_start)}** ud, men tjanselisten er {gl}. Kalenderne i Holdsport får først de nye tjanser, når listen er lavet.

- [ ] **Tjanselisten for {lang(vd_start)}.** {hvor}
- [ ] **Holdsport:** importerne skal ikke laves om, for kalenderne beholder deres navne. Står der et feed på tjansesiden, som ikke er importeret endnu (fx første gang et hold har 6-personers-tjanser), så importér det.

Kampprogrammerne og holdkoderne finder robotten selv hos Volleyball Danmark.
Issuet lukker sig selv, når tjanselisten er fra {lang(vd_start)}.
Tjansesiden: {SIDE}tjanser/"""
    return {"noegle": "tjanseliste", "auto": True, "aktiv": aktiv,
            "titel": f"Ny sæson {lang(vd_start)}: tjanselisten",
            "kort": f"kampprogrammet er ude, tjanselisten er {gl}",
            "link": f"{SIDE}tjanser/", "tekst": tekst}


def takster(nu):
    """Hver januar: årets km-takst og bropris i koerselsudligning/config.json."""
    if nu < date(nu.year, 1, 10):
        return None
    kfg = laes_json(REPO_ROD, "koerselsudligning", "config.json")
    aar = str(nu.year)
    km = aar in (kfg.get("km_takst") or {})
    bro = aar in (kfg.get("bropris") or {})
    if not kfg:
        return None
    ok = lambda b: "✓ står der" if b else "mangler"
    tekst = f"""Kørselsudligningen for {lang(nu.year)} regnes med årets takster. Tilføj dem i `koerselsudligning/config.json` (ret direkte på GitHub og gem):

- [{'x' if km else ' '}] **`km_takst` → `"{aar}"`**: statens laveste km-takst (over 20.000 km om året) – skat.dk, satser for kørselsgodtgørelse. ({ok(km)})
- [{'x' if bro else ' '}] **`bropris` → `"{aar}"`**: Storebælt pr. bil tur/retur med weekendrabat. Samme pris som sidste år? Så skriv den igen. ({ok(bro)})

Indtil da bruger robotten sidste års tal og skriver en advarsel på siden.
Issuet lukker sig selv, når begge tal står der."""
    return {"noegle": "takster", "auto": True, "aktiv": not (km and bro),
            "titel": f"Kørselsudligning: takster for {aar}",
            "kort": "km-takst og bropris i config.json",
            "link": f"https://github.com/{REPO}/edit/main/koerselsudligning/config.json",
            "tekst": tekst}


def kontingent(nu):
    """Fra 1. august: kontingentsiden skal have den nye sæsons satser."""
    try:
        side = open(os.path.join(ROOT, "docs", "kontingent", "index.html"), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'var\s+BUDGET_SAESON\s*=\s*"(\d{2})/(\d{2})"', side)
    if not m:
        return None
    side_start = 2000 + int(m.group(1))
    nu_start = nu.year if nu.month >= 8 else nu.year - 1
    ny = kort(nu_start)
    tekst = f"""Kontingentsiden regner stadig med satser og budget fra **{kort(side_start)}**. Når budgettet for {ny} er klar, rettes øverst i scriptet i `tjans/docs/kontingent/index.html`:

- [ ] `BUDGET_SAESON` til `"{ny}"`
- [ ] `HOLD` (takst, antal, kompensation og budget pr. hold) og `BUDGET_IALT` – tallene står på fanen «Kontingent status» i budgetarket
- [ ] Nye hold eller holdnavne i Holdsport? Så også `MOENSTRE` og `ERMIX`

Overskrifter, U17-årgang og budgetboks følger med af sig selv. Claude kan lave rettelserne ud fra budgetarket.
Issuet lukker sig selv, når siden står til {ny}."""
    return {"noegle": "kontingent", "auto": True, "aktiv": nu_start > side_start,
            "titel": f"Kontingentsiden: satser for {ny}",
            "kort": f"satserne er fra {kort(side_start)}",
            "link": f"{SIDE}kontingent/", "tekst": tekst}


def turpris(nu):
    """Kampprogrammet for en ny sæson er ude, men priserne i turprisen er fra sidste sæson."""
    try:
        side = open(os.path.join(ROOT, "docs", "turpris", "index.html"), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'var\s+PRISER_SAESON\s*=\s*"(\d{4})/(\d{2})"', side)
    vd_start = startaar(laes_json(ROOT, "docs", "koerselsudligning", "status.json").get("saeson"))
    if not m or not vd_start:
        return None
    side_start = int(m.group(1))
    ny = lang(vd_start)
    tekst = f"""Turprisen regner sæsonens udeture for **{ny}** ud af sig selv, men priserne er stadig fra **{lang(side_start)}**. Tjek dem øverst i scriptet i `tjans/docs/turpris/index.html`:

- [ ] `PRISER_SAESON` til `"{ny}"`
- [ ] **Billeje** (`STANDARD.biler`): leje og Premium pr. dag, km inkluderet, pris pr. ekstra km og rabat – fra den nye sæsons første booking
- [ ] **Færge** (`faerge`, pr. bil pr. vej) og **hotel** pr. dobbeltweekend (`hotel`)
- [ ] **Brændstof**: diesel (`pris_l`) og benzin (`SAESON.benzin`)
- [ ] **Hvem lejer biler til Sjælland?** `SAESON.lejebilHold` og `SAESON.dobbeltHold` (i {lang(side_start)}: D1)
- [ ] **Mangler der udekampe** i Volleyball Danmarks program (fx et hold, der har afløst et andet)? Så tilføj dem i `EKSTRA_UDEKAMPE` – de gamle gælder kun deres egen sæson

Kampene, dobbeltweekenderne og km følger med af sig selv fra kørselsudligningen. Claude kan lave rettelserne ud fra nye bookinger.
Issuet lukker sig selv, når priserne står til {ny}."""
    return {"noegle": "turpris", "auto": True, "aktiv": vd_start > side_start,
            "titel": f"Turpris: priser for {ny}",
            "kort": f"kampene er ude, priserne er fra {lang(side_start)}",
            "link": f"{SIDE}turpris/", "tekst": tekst}


def tryout(nu):
    """1. juni: try-out-systemet skal vækkes og gøres klar. Lukkes af dig."""
    if nu < date(nu.year, 6, 1):
        return None
    tekst = f"""Try-out-systemet har sovet siden sidste år. Guiden: [Try-out – guide til nyt try-out-år]({TRYOUT_GUIDE})

- [ ] **Væk Supabase senest i juni** – Resume project (afsnit 3.1). Kan kun vækkes inden for et år efter, at det gik på pause.
- [ ] **Vercel:** Production står som Ready, og Node.js-versionen er den nyeste (afsnit 3.2)
- [ ] **Resend:** domænet står som Verified (afsnit 3.3)
- [ ] **Nyt sæsonår** i databasen, trænerlisten, tilmeldingstekster og Holdsport-link (afsnit 4.1–4.4)
- [ ] **Login-mails** via Resend og årets opdateringer (afsnit 4.5–4.6)
- [ ] **Testlisten**, før tilmeldingen åbner (afsnit 5)
- [ ] **Udtagelsesmails** efter holdsætningen (afsnit 6)
- [ ] **Slet billederne via /oprydning 30 dage efter holdsætningen** – det er lovet i samtykket (afsnit 6)

Luk issuet, når billederne er slettet. Robotten minder dig om billederne i slutningen af september."""
    return {"noegle": "tryout", "auto": False, "aktiv": True,
            "opret": nu <= date(nu.year, 7, 31),
            "titel": f"Try-out {nu.year}: væk systemet og gør det klar",
            "kort": "Supabase skal vækkes senest i juni", "link": TRYOUT_GUIDE, "tekst": tekst,
            "opfoelgning": (date(nu.year, 9, 20), "billeder",
                            "Påmindelse: billederne fra try-out skal slettes via **/oprydning** "
                            "senest 30 dage efter holdsætningen – det er lovet i samtykket "
                            "(afsnit 6 i guiden). Luk issuet, når det er gjort.")}


def budget(nu):
    """1. juni: nyt regnskabsår i budgetarket. Lukkes af dig."""
    if nu < date(nu.year, 6, 1):
        return None
    gl, ny = kort(nu.year - 1), kort(nu.year)
    tekst = f"""Regnskabsåret starter 1. juni. Til sæson {ny}:

- [ ] **Nyt budget for {ny}** (afløser «Bud på Budget {gl}»)
- [ ] **Nyt budgetark** videreført fra {gl}-arket – faner, formler og holdkoblinger følger med
- [ ] **Primosaldo pr. 01.06.{nu.year % 100:02d}** for Konto 1 og Konto 2 fra kontoudtogene
- [ ] **Holdlisten og rækkeopstillingen** for {ny}
- [ ] **Budgetsiden** kobles til det nye ark: åbn {SIDE}budget/#opsaetning og følg de fire trin (scriptet i arket, og til sidst ret `adresse.txt`)
- [ ] **Kontingentsiden** får de nye satser – der kommer et issue om det fra 1. august

Sig til Claude: «ny sæson i budgettet» – så tager budget-skillen den derfra.
Luk issuet, når det nye ark er i brug."""
    return {"noegle": "budget", "auto": False, "aktiv": True,
            "opret": nu <= date(nu.year, 8, 31),
            "titel": f"Budget {ny}: nyt regnskabsår",
            "kort": "nyt budgetark og primosaldi pr. 1. juni",
            "link": ISSUES, "tekst": tekst}


PAAMINDELSER = (tjanseliste, takster, kontingent, turpris, tryout, budget)


# ----------------------------------------------------------------------------- GitHub-issues
def behandl(paam, issues, nu, test):
    """Opretter, lukker eller følger op på ét issue. Returnerer linket, hvis
    påmindelsen stadig er aktuel (til startsiden), ellers None."""
    titel, noegle = paam["titel"], paam["noegle"]
    denne = next((i for i in issues if i["title"] == titel), None)
    familie = f"<!-- påmindelse: {noegle} "
    gamle = [i for i in issues if i is not denne and i["state"] == "OPEN"
             and familie in (i.get("body") or "")]
    krop = paam["tekst"] + "\n\n" + maerke(noegle, paam["tekst"])

    if paam["auto"] and not paam["aktiv"]:
        if denne and denne["state"] == "OPEN":
            print(f"  ✓ {titel} – på plads, lukker #{denne['number']}")
            if not test:
                gh("issue", "comment", str(denne["number"]), "--body",
                   "Det er på plads nu – lukker automatisk.")
                gh("issue", "close", str(denne["number"]))
        return None

    if denne and denne["state"] != "OPEN":
        print(f"  – {titel} – lukket af dig, rører den ikke")
        return None

    if not denne:
        if not paam.get("opret", True):
            return None          # vinduet for at oprette den er passeret i år
        print(f"  + {titel} – opretter issue")
        url = ISSUES
        if not test:
            r = gh("issue", "create", "--title", titel, "--label", LABEL, "--body", krop)
            url = r.stdout.strip() or url
            if r.returncode:
                print(f"    kunne ikke oprette: {r.stderr.strip()}")
        for g in gamle:      # sidste års udgave af samme påmindelse
            print(f"    afløser #{g['number']} ({g['title']})")
            if not test:
                gh("issue", "comment", str(g["number"]), "--body", f"Afløst af {url}")
                gh("issue", "close", str(g["number"]), "--reason", "not planned")
        return url

    print(f"  · {titel} – åben (#{denne['number']})")
    # Robottens egne påmindelser skrives om, hvis indholdet har ændret sig (fx når den ene
    # af to takster er kommet). Dine egne flueben i try-out og budget røres aldrig.
    if paam["auto"] and maerke(noegle, paam["tekst"]) not in (denne.get("body") or ""):
        print("    teksten er ændret – opdaterer issuet")
        if not test:
            gh("issue", "edit", str(denne["number"]), "--body", krop)
    opf = paam.get("opfoelgning")
    if opf and nu >= opf[0] and not test:
        tag = f"<!-- opfølgning: {opf[1]} -->"
        r = gh("issue", "view", str(denne["number"]), "--json", "comments")
        kommentarer = json.loads(r.stdout or "{}").get("comments", [])
        if not any(tag in (k.get("body") or "") for k in kommentarer):
            gh("issue", "comment", str(denne["number"]), "--body", f"{opf[2]}\n\n{tag}")
            print("    skrev opfølgning")
    return denne.get("url") or ISSUES


def hent_issues(test):
    if test:
        return []
    gh("label", "create", LABEL, "--color", "0E8A16",
       "--description", "Skal gøres til en ny sæson – robotten opretter og lukker")
    r = gh("issue", "list", "--label", LABEL, "--state", "all", "--limit", "100",
           "--json", "number,title,state,body,url")
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "gh issue list fejlede")
    return json.loads(r.stdout or "[]")


# ----------------------------------------------------------------------------- livstegn
def hold_i_live(nu_tid, test):
    ref = os.environ.get("GITHUB_WORKFLOW_REF", "")          # ejer/repo/.github/workflows/main.yml@refs/...
    wf = os.path.basename(ref.split("@")[0]) or "main.yml"
    if test:
        print(f"  [test] ville slå {wf} til via GitHubs API")
    else:
        r = gh("api", "-X", "PUT", f"repos/{REPO}/actions/workflows/{wf}/enable")
        print(f"  natkørslen ({wf}) slået til – GitHubs 60-dages-ur er nulstillet" if r.returncode == 0
              else f"  kunne ikke slå {wf} til: {r.stderr.strip()} (kræver 'actions: write')")

    r = git("log", "-1", "--format=%ct")
    if r.returncode or not r.stdout.strip():
        print("  ingen git-historik her – springer livstegnet over")
        return
    dage = max(0, (nu_tid - datetime.fromtimestamp(int(r.stdout.strip()), timezone.utc)).days)
    if dage < LIVSTEGN_DAGE:
        print(f"  seneste commit for {dage} dage siden – intet livstegn nødvendigt")
        return
    print(f"  seneste commit for {dage} dage siden – skriver livstegn i data/puls.txt")
    if test:
        return
    open(os.path.join(ROOT, "data", "puls.txt"), "w", encoding="utf-8").write(
        f"Livstegn {nu_tid.astimezone(DK):%d-%m-%Y %H:%M}\n\n"
        "Robotten skriver her, når repoet har været uden ændringer i "
        f"{LIVSTEGN_DAGE} dage, så GitHub ikke slår natkørslen fra.\n")
    navn = ["-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
    git("add", "data/puls.txt")
    git(*navn, "commit", "-q", "-m", "Robot: livstegn", "--", "data/puls.txt")
    p = git("push", "-q")
    print("  livstegn gemt" if p.returncode == 0 else f"  kunne ikke gemme livstegn: {p.stderr.strip()}")


# ----------------------------------------------------------------------------- hovedprogram
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--test", action="store_true", help="vis hvad der ville ske – rør ikke GitHub")
    ap.add_argument("--nu", help="kun til test: dato som ÅÅÅÅ-MM-DD")
    args = ap.parse_args()
    nu_tid = (datetime.fromisoformat(args.nu).replace(hour=5, tzinfo=DK) if args.nu
              else datetime.now(timezone.utc).astimezone(DK))
    nu = nu_tid.date()

    print("Natkørslen:")
    try:
        hold_i_live(nu_tid, args.test)
    except Exception as exc:                         # noqa: BLE001 – må aldrig vælte natkørslen
        print(f"  fejl: {exc}")

    print(f"Påmindelser til ny sæson ({nu:%d-%m-%Y}):")
    paam = [p for p in (f(nu) for f in PAAMINDELSER) if p]
    try:
        issues = hent_issues(args.test)
        github_ok = True
    except Exception as exc:                         # noqa: BLE001
        print(f"  kunne ikke læse issues ({exc}) – opretter intet i nat")
        issues, github_ok = [], False

    vis = []
    for p in paam:
        if github_ok:
            link = behandl(p, issues, nu, args.test)
        else:                                        # uden GitHub: vis det, der er aktuelt nu
            link = p["link"] if p["aktiv"] and p.get("opret", True) else None
        if link and p["aktiv"]:
            vis.append({"noegle": p["noegle"], "titel": p["titel"], "kort": p["kort"],
                        "link": link if link != ISSUES else p["link"]})
    if not paam:
        print("  intet at minde om")

    ud = os.path.join(ROOT, "docs", "paamindelser.json")
    json.dump({"opdateret": nu_tid.strftime("%d-%m-%Y %H:%M"), "paamindelser": vis},
              open(ud, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Startsiden viser {len(vis)} påmindelse(r)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
