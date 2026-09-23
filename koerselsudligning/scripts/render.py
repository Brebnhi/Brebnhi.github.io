#!/usr/bin/env python3
"""Renderer status.json til index.html — siden med den forventede kørselsudligning."""
import html, json, os, sys

E = lambda s: html.escape(str(s if s is not None else ""))

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e6eb;
--ok:#0f7b4f;--okbg:#e7f5ee;--warn:#9a3412;--warnbg:#fdf0e7;--bad:#a11d1d;--badbg:#fbeaea;
--accent:#1b4f9c;--accentbg:#eaf0fa;--hl:#fff8e1}
@media(prefers-color-scheme:dark){:root{--bg:#101216;--card:#181b21;--ink:#e8eaed;
--muted:#9aa1ac;--line:#2a2f38;--ok:#5fd39b;--okbg:#12291f;--warn:#f0a868;--warnbg:#2b1e12;
--bad:#f08a8a;--badbg:#2b1616;--accent:#7fa8ec;--accentbg:#1c2a44;--hl:#2a2616}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:36px 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:14px;margin:0 0 24px}
.banner{border-radius:12px;padding:16px 20px;margin:0 0 20px;border:1px solid transparent}
.banner.ok{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.banner.warn{background:var(--warnbg);border-color:var(--warn);color:var(--warn)}
.banner.bad{background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.banner strong{display:block;font-size:17px;margin-bottom:2px}
.hero{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:0 0 16px}
.hero .lbl{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.hero .big{font-size:40px;font-weight:700;letter-spacing:-.03em;line-height:1.15;margin:4px 0 2px;
font-variant-numeric:tabular-nums}
.hero .big.plus{color:var(--ok)} .hero .big.minus{color:var(--bad)}
.hero p{margin:4px 0 0;color:var(--muted);font-size:14px}
.dele{display:flex;flex-wrap:wrap;gap:6px 18px;margin:10px 0 2px;font-size:14px}
.dele span{color:var(--muted)} .dele b{font-variant-numeric:tabular-nums}
h3{font-size:14px;margin:14px 16px 8px;color:var(--muted);font-weight:600}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;min-width:140px;flex:1}
.stat b{display:block;font-size:21px;line-height:1.2;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:12.5px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;background:var(--card);
border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:600px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:11.5px;
text-transform:uppercase;letter-spacing:.05em;padding:9px 10px;border-bottom:1px solid var(--line)}
td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.d{white-space:nowrap;font-variant-numeric:tabular-nums}
tr.klub td{background:var(--hl);font-weight:600}
.plus{color:var(--ok)} .minus{color:var(--bad)}
.tag{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11.5px;
font-weight:600;background:var(--accentbg);color:var(--accent)}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:0 0 10px}
details>summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"▸";display:inline-block;width:16px;color:var(--muted)}
details[open]>summary:before{content:"▾"}
details .tw{border:0;border-top:1px solid var(--line);border-radius:0 0 12px 12px}
details .meta{color:var(--muted);font-weight:400;font-size:13px}
.muted{color:var(--muted)}
ul.adv{margin:0;padding-left:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px}
.card p{margin:0 0 10px} .card p:last-child{margin:0}
@media(max-width:640px){table{min-width:0}.lav{display:none}th.n{white-space:normal}
.hero .big{font-size:34px}}
footer{margin-top:40px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:16px}
.nav{margin:0 0 18px;font-size:14px}.nav a{color:var(--accent);text-decoration:none}.nav a:hover{text-decoration:underline}
"""


def kr(v, fortegn=True, dec=0):
    """Dansk talformat: 49.228 / +1.234,50 / −512."""
    if v is None:
        return "–"
    s = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if not fortegn:
        return ("−" if v < 0 else "") + s
    return ("+" if v > 0 else "−" if v < 0 else "") + s


def klasse(v):
    return "plus" if v and v > 0 else "minus" if v and v < 0 else ""


def tabel(hoved, raekker_, tom=""):
    if not raekker_:
        return f'<p class="muted">{tom}</p>'
    def th(h):
        lav, h = h.startswith("~"), h.lstrip("~")
        n, h = h.startswith("#"), h.lstrip("#")
        kl = " ".join(k for k, ja in (("n", n), ("lav", lav)) if ja)
        return f'<th class="{kl}">{h}</th>' if kl else f"<th>{h}</th>"
    th = "".join(th(h) for h in hoved)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{"".join(raekker_)}</tbody></table></div>'


def render(st):
    saeson = st.get("saeson") or ""
    total = st.get("total")
    fejl = st.get("fejl")
    klubhold = st.get("klubhold") or []
    takst, bro = st.get("takst"), st.get("bro")

    fejl_html = (f'<div class="banner bad"><strong>Obs</strong>{E(fejl)}</div>' if fejl else "")

    grund, pokal_t, slut_t = st.get("grundspil"), st.get("pokal_total"), st.get("slutspil_total")
    if grund is None and total is not None:          # status fra før pokal/slutspil
        grund, pokal_t, slut_t = total, 0, 0
    if total is None:
        hero = ""
    else:
        hvad = ("Kreditnota fra Volleyball Danmark — klubben får penge" if total >= 0
                else "Faktura fra Volleyball Danmark — klubben betaler")
        har_pokal = any(r.get("status") == "beregnet" for r in st.get("pokal") or [])
        har_slut = bool(st.get("slutspil"))
        dele = "".join(
            f'<div><span>{t}</span> <b class="{klasse(v)}">{kr(v)} kr</b></div>' if har
            else f'<div><span>{t}</span> <b class="muted">–</b></div>'
            for t, v, har in (("Grundspil", grund, True), ("Pokal", pokal_t, har_pokal),
                              ("Slutspil", slut_t, har_slut)))
        hero = (f'<div class="hero"><div class="lbl">Forventet kørselsudligning {E(saeson)}</div>'
                f'<div class="big {klasse(total)}">{kr(total)} kr</div>'
                f'<div class="dele">{dele}</div>'
                f'<p>{hvad}. Pokal og slutspil tæller med, efterhånden som runderne bliver trukket '
                f'og kampene lagt ud. Final4 afregnes efter regning og er ikke med.</p></div>')

    stats = "".join(
        f'<div class="stat"><b class="{klasse(h["udligning"])}">{kr(h["udligning"])} kr</b>'
        f'<span><span class="tag">{E(h["kode"])}</span> {E(h["raekke"])}</span></div>'
        for h in klubhold)

    pr_hold = [
        f'<tr><td><span class="tag">{E(h["kode"])}</span> {E(h["hold"])}</td>'
        f'<td>{E(h["raekke"])} · {E(h["pulje"])}</td>'
        f'<td class="n lav">{h["udekampe"]}</td><td class="n lav">{kr(h["km"], False)}</td>'
        f'<td class="n lav">{h["bro"]}</td><td class="n lav">{kr(h["udgift"], False)}</td>'
        f'<td class="n lav">{kr(h["gennemsnit"], False)}</td>'
        f'<td class="n {klasse(h["udligning"])}"><b>{kr(h["udligning"])}</b></td></tr>'
        for h in klubhold]

    def tag(h):
        return f'<span class="tag">{E(h["kode"])}</span> ' if h.get("kode") else ""

    def klubrække(h, r):
        kamp = ""
        if h.get("ture"):
            t = h["ture"][0]
            kamp = f"ude hos {E(t['modstander'])}"
        elif h.get("hjemmekampe"):
            kamp = f"hjemme mod {E(h['hjemmekampe'][0]['modstander'])}"
        sted = (h.get("ture") or h.get("hjemmekampe") or [{}])[0].get("sted", "")
        km_ = h["ture"][0]["km"] if h.get("ture") else 0
        return (f'<tr><td>{tag(h)}{E(h["hold"])}</td><td>{kamp}</td><td class="lav">{E(sted)}</td>'
                f'<td class="n lav">{km_}</td><td class="n">{kr(h["udgift"], False)}</td>'
                f'<td class="n lav">{kr(h["andel"], False)}</td>'
                f'<td class="n {klasse(h["udligning"])}"><b>{kr(h["udligning"])}</b></td></tr>')

    def alle_kampe(r, hvem):
        rows = [f'<tr><td class="d">{E(k["dato"][:5])}</td><td>{E(k["hjemme"])}</td><td>{E(k["ude"])}</td>'
                f'<td class="lav">{E(k["sted"])}</td><td class="n lav">{k["km"]}</td>'
                f'<td class="n">{kr(k["beloeb"], False)}</td></tr>' for k in r.get("kampe", [])]
        return (f"<h3>Alle kampe {hvem}</h3>" + tabel(
            ["Dato", "Hjemme", "Ude", "~Spillested", "~#Km", "#Kørsel"], rows))

    pokal_html = []
    for r in st.get("pokal") or []:
        if r.get("status") != "beregnet":
            pokal_html.append(f'<div class="card" style="margin-bottom:10px">{E(r["raekke"])} '
                              '<span class="muted">— kampene er ikke lagt ud endnu</span></div>')
            continue
        klub = [h for h in r["hold"] if h["klub"]]
        sum_ = sum(h["udligning"] for h in klub)
        pokal_html.append(
            f'<details><summary>{E(r["raekke"])} <span class="meta">— {r["antal_hold"]} hold · '
            f'gennemsnit {kr(r["gennemsnit"], False)} kr pr. hold · klubben '
            f'<b class="{klasse(sum_)}">{kr(sum_)} kr</b></span></summary>'
            + tabel(["Hold", "Kamp", "~Spillested", "~#Km", "#Udgift", "~#Rundens snit",
                     "#Udligning"], [klubrække(h, r) for h in klub])
            + alle_kampe(r, "i runden") + "</details>")

    slut_html = []
    for r in st.get("slutspil") or []:
        klub = [h for h in r["hold"] if h["klub"]]
        sum_ = sum(h["udligning"] for h in klub)
        rows = [f'<tr class="{"klub" if h["klub"] else ""}"><td>{tag(h)}{E(h["hold"])}</td>'
                f'<td class="n">{h["kampe"]}</td>'
                f'<td class="n lav">{h["udekampe"]}</td><td class="n">{kr(h["udgift"], False)}</td>'
                f'<td class="n lav">{kr(h["andel"], False)}</td>'
                f'<td class="n {klasse(h["udligning"])}"><b>{kr(h["udligning"])}</b></td></tr>'
                for h in r["hold"]]
        slut_html.append(
            f'<details><summary>{E(r["raekke"])} <span class="meta">— {r["antal_kampe"]} kampe · '
            f'gennemsnitspris {kr(r["pris_pr_kamp"], False)} kr pr. kamp · klubben '
            f'<b class="{klasse(sum_)}">{kr(sum_)} kr</b></span></summary>'
            + tabel(["Hold", "#Kampe", "~#Udekampe", "#Udgift", "~#Andel", "#Udligning"], rows)
            + alle_kampe(r, "i slutspillet") + "</details>")

    # kontrol mod faktiske beløb
    kal_html = []
    for k in st.get("kalibrering") or []:
        rows, inden = [], 0
        for l in k["linjer"]:
            raekke, hold = (l["noegle"].split("|", 1) + [""])[:2]
            afv = l["afvigelse"]
            pct = (afv / l["faktisk"] * 100) if afv is not None and l["faktisk"] else None
            if pct is not None and abs(pct) <= 2:
                inden += 1
            rows.append(
                f'<tr><td>{E(hold)}</td><td class="lav">{E(raekke)}</td>'
                f'<td class="n">{kr(l["model"], dec=2)}</td><td class="n">{kr(l["faktisk"], dec=2)}</td>'
                f'<td class="n">{kr(afv) if afv is not None else "–"}'
                f'{f"<span class=lav> ({kr(pct, dec=1)} %)</span>" if pct is not None else ""}</td></tr>')
        rows.append(f'<tr><td><b>I alt</b></td><td class="lav"></td><td class="n"><b>{kr(k["model_total"], dec=2)}</b></td>'
                    f'<td class="n"><b>{kr(k["faktisk_total"], dec=2)}</b></td>'
                    f'<td class="n"><b>{kr(k["model_total"] - k["faktisk_total"])}</b></td></tr>')
        kal_html.append(
            f'<details><summary>{E(k["saeson"])}{" · pokal" if k.get("type") == "pokal" else ""} <span class="meta">— {inden} af {len(k["linjer"])} '
            f'hold ramt inden for 2 % · {E(k.get("kilde", ""))}</span></summary>'
            + tabel(["Hold", "~Række", "#Model", "#Faktisk", "#Afvigelse"], rows) + "</details>")

    # alle hold i rækkerne
    raekke_html = []
    for r in st.get("raekker") or []:
        rows = [
            f'<tr class="{"klub" if h.get("klub") else ""}"><td>{E(h["hold"])}</td><td>{E(h["pulje"])}</td>'
            f'<td class="n lav">{h["udekampe"]}</td><td class="n lav">{kr(h["km"], False)}</td>'
            f'<td class="n lav">{h["bro"]}</td><td class="n">{kr(h["udgift"], False)}</td>'
            f'<td class="n {klasse(h["udligning"])}">{kr(h["udligning"])}</td></tr>'
            for h in r["hold"]]
        raekke_html.append(
            f'<details><summary>{E(r["raekke"])} <span class="meta">— {r["antal_hold"]} hold i '
            f'{E(", ".join(r["puljer"]))} · gennemsnit {kr(r["gennemsnit"], False)} kr · '
            f'{r["biler"]} biler</span></summary>'
            + tabel(["Hold", "Pulje", "~#Udekampe", "~#Km i alt", "~#Broture", "#Udgift", "#Udligning"],
                    rows) + "</details>")

    # klubbens udeture
    ture_html = []
    for h in klubhold:
        rows = [f'<tr><td class="d">{E(t["dato"])}</td><td>{E(t["modstander"])}</td>'
                f'<td class="lav">{E(t["sted"])}</td>'
                f'<td class="n">{t["km"]}{" *" if t.get("skoen") else ""}</td>'
                f'<td class="lav">{"Storebælt" if t["bro"] else ""}</td>'
                f'<td class="n">{kr(t["beloeb"], False)}</td></tr>' for t in h.get("ture", [])]
        ture_html.append(
            f'<details><summary><span class="tag">{E(h["kode"])}</span> {E(h["hold"])} '
            f'<span class="meta">— {h["udekampe"]} udekampe · {kr(h["udgift"], False)} kr</span></summary>'
            + tabel(["Dato", "Hos", "~Spillested", "#Km (enkelt)", "~Bro", "#Beløb"], rows) + "</details>")

    # sæsoner: kontrol-sæsoner vises med samme afgrænsning i begge kolonner
    hist = st.get("historik") or {}
    faktisk = st.get("faktisk") or {}
    kal = {}                       # en sæson kan have både grundspil- og pokalkontrol
    for k in st.get("kalibrering") or []:
        a = kal.setdefault(k["saeson"], {"model_total": 0.0, "faktisk_total": 0.0, "typer": []})
        a["model_total"] += k["model_total"]
        a["faktisk_total"] += k["faktisk_total"]
        a["typer"].append("pokal" if k.get("type") == "pokal" else "grundspil")
    saesoner = sorted(set(hist) | set(faktisk) | set(kal), reverse=True)
    hist_rows = []
    for s_ in saesoner:
        dele = ""
        if s_ in kal:
            model, fak = kal[s_]["model_total"], kal[s_]["faktisk_total"]
            note = "kontrolleret: " + " + ".join(kal[s_]["typer"])
        else:
            h = hist.get(s_, {})
            model, fak = h.get("total"), faktisk.get(s_)
            note = "beregnet " + h["beregnet"] if h.get("beregnet") else ""
            if h.get("pokal") or h.get("slutspil"):
                dele = " · ".join(f"{t} {kr(h.get(t))}" for t in ("grundspil", "pokal", "slutspil")
                                  if t == "grundspil" or h.get(t))
                dele = f' <span class="muted lav">({dele})</span>'

        hist_rows.append(f'<tr><td>{E(s_)}</td><td class="n">{kr(model)}{dele}</td>'
                         f'<td class="n">{kr(fak, dec=2) if fak is not None else "–"}</td>'
                         f'<td class="muted lav">{E(note)}</td></tr>')

    adv = st.get("advarsler") or []
    adv_html = ("<h2>Advarsler</h2><div class='card'><ul class='adv'>"
                + "".join(f"<li>{E(a)}</li>" for a in adv) + "</ul></div>") if adv else ""

    metode = (
        "<div class='card'>"
        "<p><b>Grundspil</b> (Økonomiske retningslinjer § 2): hold med lange ture får penge fra "
        "hold med korte. Det er et nulsumsregnestykke pr. række og køn — Øst, Vest, Syd og Nord "
        "i samme række regnes sammen. Pr. udekamp: biler × (2 × km × "
        f"{kr(takst, False, 2) if takst else '–'} kr + {kr(bro, False) if bro else '–'} kr i "
        "broafgift, hvis turen krydser Storebælt). Liga og 1. division regnes med 3 biler, "
        "2. division med 2. Udligning = holdets udgift minus gennemsnittet pr. hold.</p>"
        "<p><b>Pokal</b> (pokalreglementets § 20): hver runde udlignes for sig — Øst og Vest "
        "samlet, kvinder og herrer hver for sig. Udeholdet regnes med 3 biler fra sin "
        "registrerede hjemmebane. Hvert hold i runden bærer rundens gennemsnit pr. hold — "
        "hjemmeholdet betaler altså sin andel, og udeholdet får sin tur dækket. Kampe uden dato "
        "(fx w.o.) er ikke med. Final4 afregnes efter regning og er ikke med.</p>"
        "<p><b>Slutspil i Volleyligaen</b> (§ 2, pkt. 4): VD finder en gennemsnitspris pr. kamp "
        "for alle slutspils- og placeringskampe og fordeler efter antal spillede kampe. Hvert "
        "hold bærer halvdelen af gennemsnitsprisen pr. kamp, det har spillet, og får sine "
        "egne udeture dækket. Afregnes efter sæsonen.</p>"
        "<p>Plus betyder kreditnota til klubben, minus betyder faktura.</p>"
        "<p class='muted'>Hold, runder og kampe hentes hver nat fra resultater.volleyball.dk "
        "(foreningssider → rækker → puljernes kampprogram). Adresser slås op i DAWA og "
        "vejafstande i OpenStreetMap (OSRM). VD bruger Google Maps, så enkelte ture kan afvige — "
        "især skrå ture på tværs af Jylland. Kontrollen ovenfor viser, hvor tæt modellen har ramt. "
        "Km markeret med * er skønnet. Grundspillet sendes til godkendelse senest 15. oktober.</p>"
        "</div>")

    return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kørselsudligning {E(saeson)} · Aalborg Volley</title>
<style>{CSS}</style></head><body><div class="wrap">
<p class="nav"><a href="../">← Alle projekter</a></p>
<h1>Kørselsudligning {E(saeson)}</h1>
<p class="sub">Aalborg Volley · forventet rejseudligning fra Volleyball Danmark ·
opdateret {E(st.get('opdateret'))}</p>
{fejl_html}{hero}
<div class="stats">{stats}</div>

<h2>Pr. hold</h2>
{tabel(["Hold", "Række · pulje", "~#Udekampe", "~#Km i alt", "~#Broture", "~#Udgift", "~#Rækkens snit", "#Udligning"],
       pr_hold, "Ingen hold i Liga, 1. eller 2. division fundet.")}

<h2>Pokalturneringen</h2>
{"".join(pokal_html) or '<p class="muted">Ingen pokalrunder med klubbens hold endnu.</p>'}

<h2>Slutspil i Volleyligaen</h2>
{"".join(slut_html) or '<p class="muted">Slutspillet kommer med, når kampene er lagt ud — typisk fra februar. Det afregnes efter sæsonen.</p>'}

<h2>Kontrol mod faktiske beløb</h2>
<p class="sub" style="margin-bottom:12px">Modellen regnet på tidligere sæsoner og holdt op mod
VD's kreditnotaer.</p>
{"".join(kal_html) or '<p class="muted">Ingen tidligere sæsoner at sammenligne med endnu.</p>'}

<h2>Alle hold i grundspillet</h2>
{"".join(raekke_html)}

<h2>Klubbens udeture i grundspillet</h2>
{"".join(ture_html)}

<h2>Sådan regnes det</h2>
{metode}

<h2>Sæsoner</h2>
{tabel(["Sæson", "#Modellens estimat", "#Faktisk fra VD", "~"], hist_rows)}
{adv_html}

<footer>Bygget automatisk ud fra de officielle kampprogrammer på resultater.volleyball.dk.
Siden opdateres hver nat. Tilføj det faktiske beløb under <code>faktisk</code> i
<code>koerselsudligning/config.json</code>, når opgørelsen fra VD kommer.</footer>
</div></body></html>"""


if __name__ == "__main__":
    sti = sys.argv[1] if len(sys.argv) > 1 else "status.json"
    st = json.load(open(sti, encoding="utf-8"))
    ud = os.path.join(os.path.dirname(os.path.abspath(sti)), "index.html")
    open(ud, "w", encoding="utf-8").write(render(st))
    print("skrev", ud)
