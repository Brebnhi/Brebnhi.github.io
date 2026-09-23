#!/usr/bin/env python3
"""Renderer status.json til docs/tjanser/index.html — klubbens live-overblik over tjanser."""
import html, json, os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E = lambda s: html.escape(str(s or ""))

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e6eb;
--ok:#0f7b4f;--okbg:#e7f5ee;--warn:#9a3412;--warnbg:#fdf0e7;--bad:#a11d1d;--badbg:#fbeaea;
--accent:#1b4f9c;--accentbg:#eaf0fa}
@media(prefers-color-scheme:dark){:root{--bg:#101216;--card:#181b21;--ink:#e8eaed;
--muted:#9aa1ac;--line:#2a2f38;--ok:#5fd39b;--okbg:#12291f;--warn:#f0a868;--warnbg:#2b1e12;
--bad:#f08a8a;--badbg:#2b1616;--accent:#7fa8ec;--accentbg:#16203040}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:36px 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:14px;margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.banner{border-radius:12px;padding:16px 20px;margin:0 0 24px;border:1px solid transparent}
.banner.ok{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.banner.bad{background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.banner strong{display:block;font-size:17px;margin-bottom:2px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;min-width:120px;flex:1}
.stat b{display:block;font-size:24px;line-height:1.2;letter-spacing:-.02em}
.stat span{color:var(--muted);font-size:12.5px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:640px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:11.5px;
text-transform:uppercase;letter-spacing:.05em;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
.tag{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11.5px;
font-weight:600;background:var(--accentbg);color:var(--accent)}
.tag.n6{background:var(--warnbg);color:var(--warn)}
.pill{font-size:11.5px;color:var(--muted)}
.pill.flyt{color:var(--warn);font-weight:600}
code{background:var(--bg);border:1px solid var(--line);border-radius:5px;
padding:1px 6px;font-size:12px;word-break:break-all}
.muted{color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:16px}
.nav{margin:0 0 18px;font-size:14px}.nav a{color:var(--accent);text-decoration:none}.nav a:hover{text-decoration:underline}
"""


def render(status, base_url=""):
    huller, forsv, flyt = status["huller"], status["forsvundne"], status["flyttede"]
    hs = status.get("holdsport") or {"aktiveret": False, "mangler": [], "hold": [],
                                     "alle_hold": [], "fejl": None,
                                     "kontrolleret": 0, "fundet": 0}
    slettet = hs.get("mangler", [])
    tj = [t for t in status["tjanser"] if t["status"] == "ok"]
    pr_hold = Counter(t["tjans"] for t in status["tjanser"])
    problemer = len(huller) + len(forsv) + len(slettet)

    if problemer == 0:
        banner = ('<div class="banner ok"><strong>Alle hjemmekampe er dækket</strong>'
                  f'Alle {status["feed_kampe"]} kampe i kampprogrammet er tjekket mod '
                  'tjanselisten — hver hjemmekamp har et hold på tjans'
                  + (f', og alle {hs["fundet"]} tjanser ligger i Holdsport.'
                     if hs.get("aktiveret") and not hs.get("fejl") else '.')
                  + '</div>')
    else:
        bits = []
        if huller:
            bits.append(f"{len(huller)} hjemmekamp{'e' if len(huller)>1 else ''} uden hold på tjans")
        if forsv:
            bits.append(f"{len(forsv)} tjans{'er' if len(forsv)>1 else ''} hvor kampen ikke længere findes")
        if slettet:
            bits.append(f"{len(slettet)} tjans{'er' if len(slettet)>1 else ''} slettet i Holdsport")
        banner = (f'<div class="banner bad"><strong>{problemer} ting kræver handling</strong>'
                  + " og ".join(bits) + ".</div>")

    def tabel(rows, cols, empty):
        if not rows:
            return f'<p class="muted">{empty}</p>'
        head = "".join(f"<th>{c}</th>" for c in cols)
        return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

    hul_rows = [f"<tr><td><code>{E(h['kampnr'])}</code></td><td>{E(h['start'])}</td>"
                f"<td>{E(h['kamp'])}</td><td>{E(h['raekke'])}</td><td>{E(h['sted'])}</td></tr>"
                for h in huller]
    fo_rows = [f"<tr><td><code>{E(f['kampnr'])}</code></td><td>{E(f['dato'])}</td>"
               f"<td>{E(f['kamp'])}</td><td><span class='tag'>{E(f['tjans'])}</span></td></tr>"
               for f in forsv]
    fl_rows = [f"<tr><td><code>{E(f['kampnr'])}</code></td><td>{E(f['dato'])} {E(f['tid'])}</td>"
               f"<td>{E(f['kampstart'][:16].replace('T',' '))}</td>"
               f"<td><span class='tag'>{E(f['tjans'])}</span></td>"
               f"<td>{E(f['hjemmehold'])} - {E(f['modstander'])}</td></tr>" for f in flyt]

    feed_rows = []
    for f in status["feeds"]:
        url = f"{base_url}feeds/{f['fil']}" if base_url else f"../feeds/{f['fil']}"
        n = "n6" if f["antal"] == 6 else ""
        feed_rows.append(
            f"<tr><td><span class='tag'>{E(f['hold'])}</span></td>"
            f"<td><span class='tag {n}'>{f['antal']} pers.</span></td>"
            f"<td>{f['kampe']}</td><td class='muted'>{E(f['foerste'])} – {E(f['sidste'])}</td>"
            f"<td><code>{E(url)}</code></td></tr>")

    sae_rows = []
    for t in sorted(status["tjanser"], key=lambda r: (r["dato"][6:8], r["dato"][3:5], r["dato"][:2], r["tid"])):
        staevne = t["status"] == "stævne"
        n = "n6" if t["antal"] == 6 else ""
        kamp = (f"{E(t['hjemmehold'] or t['raekke'])}"
                + (f" - {E(t.get('modstander') or t['udehold'])}" if t["udehold"] else ""))
        moede = "" if staevne else E(t["start"][11:16])
        note = ""
        if staevne:
            note = "<span class='pill'>stævne – oprettes manuelt</span>"
        elif t.get("flyttet"):
            note = "<span class='pill flyt'>flyttet siden tjanselisten</span>"
        elif t["kilde"] == "mangler i feed":
            note = "<span class='pill flyt'>ikke fundet i kampprogrammet</span>"
        sae_rows.append(
            f"<tr><td>{E(t['dato'])}</td><td>{E(t['tid'])}</td><td>{moede}</td>"
            f"<td>{kamp}</td><td class='muted'>{E(t['raekke'])}</td>"
            f"<td><span class='tag {n}'>{t['antal']}</span></td>"
            f"<td><span class='tag'>{E(t['tjans'])}</span></td><td>{note}</td></tr>")

    hold_stats = "".join(
        f'<div class="stat"><b>{v}</b><span>tjanser til {E(k)}</span></div>'
        for k, v in sorted(pr_hold.items()))

    if not hs.get("aktiveret"):
        holdsport_afsnit = (
            '<h2>Kontrol mod Holdsport</h2>'
            '<p class="muted">Ikke slået til. Læg <code>HOLDSPORT_USER</code> og '
            '<code>HOLDSPORT_PASSWORD</code> ind som hemmeligheder i repoet, '
            'så kontrollerer robotten hver nat, at alle tjanser stadig ligger '
            'i Holdsport.</p>')
    elif hs.get("fejl"):
        holdsport_afsnit = ('<h2>Kontrol mod Holdsport</h2>'
                            f'<div class="banner bad"><strong>Kunne ikke tjekke Holdsport</strong>'
                            f'{E(hs["fejl"])}</div>')
    else:
        sl_rows = [f"<tr><td><code>{E(m['kampnr'])}</code></td><td>{E(m['start'])}</td>"
                   f"<td>{E(m['navn'])}</td>"
                   f"<td><span class='tag'>{E(m['tjans'])}</span></td>"
                   f"<td class='muted'>{E(m['holdsport'])}</td></tr>" for m in slettet]
        hold_rows = []
        for h in hs.get("hold", []):
            status_tekst = (f"{h['fundet']} af {h['forventet']}"
                            if not h.get("fejl") else E(h["fejl"]))
            hold_rows.append(
                f"<tr><td><span class='tag'>{E(h['kode'])}</span></td>"
                f"<td>{E(h.get('holdsport') or '—')}</td>"
                f"<td class='muted'>{E(h.get('id') or '')}</td>"
                f"<td>{status_tekst}</td>"
                f"<td class='muted'>{E(h.get('match',''))}</td></tr>")
        alle = ", ".join(f"{E(h['navn'])} (id {E(h['id'])})" for h in hs.get("alle_hold", []))
        holdsport_afsnit = (
            "<h2>Kontrol mod Holdsport</h2>"
            f"<p class='sub'>{hs['fundet']} af {hs['kontrolleret']} tjanser fundet i "
            "Holdsport ved sidste kørsel. Mangler en, er den blevet slettet.</p>"
            + tabel(sl_rows, ["Kampnr.", "Mødetid", "Aktivitet", "Tjans", "Hold i Holdsport"],
                    "Ingen tjanser er blevet slettet — alle ligger som de skal.")
            + "<h2>Holdopslag</h2>"
            + "<p class='sub'>Sådan er holdene fra tjanselisten koblet til dine hold i "
              "Holdsport. Passer et opslag ikke, så ret navnet eller nummeret i "
              "<code>data/holdsport_hold.json</code>.</p>"
            + tabel(hold_rows, ["Hold", "Hold i Holdsport", "Id", "Fundet", "Fundet ved"], "")
            + (f"<p class='tnote'>Alle hold på din Holdsport-bruger: {alle}</p>" if alle else ""))

    fejl = status.get("feed_fejl") or {}
    fejl_html = ""
    if fejl:
        fejl_html = ('<div class="banner bad"><strong>Kampprogrammet kunne ikke hentes</strong>'
                     + E(", ".join(f"{k}: {v}" for k, v in fejl.items())) + "</div>")

    return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tjanser 2026/27 · Aalborg Volley</title>
<style>{CSS}</style></head><body><div class="wrap">
<p class="nav"><a href="../">← Alle projekter</a></p>
<h1>Tjanser 2026/27</h1>
<p class="sub">Aalborg Volley · opdateret {E(status['opdateret'])} ·
{status['feed_kampe']} kampe hentet fra kampprogrammet</p>
{fejl_html}{banner}
<div class="stats">
<div class="stat"><b>{len(tj)}</b><span>tjanser i kalenderne</span></div>
<div class="stat"><b>{len(status['feeds'])}</b><span>feeds til Holdsport</span></div>
<div class="stat"><b>{len(flyt)}</b><span>flyttede kampe</span></div>
<div class="stat"><b>{len(huller)}</b><span>kampe uden tjans</span></div>
<div class="stat"><b>{len(slettet) if hs.get("aktiveret") else "–"}</b><span>slettet i Holdsport</span></div>
</div>

<h2>Hjemmekampe uden hold på tjans</h2>
{tabel(hul_rows, ["Kampnr.", "Dato", "Kamp", "Række", "Sted"],
       "Ingen — hver hjemmekamp i kampprogrammet har et hold på tjans.")}

<h2>Tjanser hvor kampen ikke længere findes i kampprogrammet</h2>
{tabel(fo_rows, ["Kampnr.", "Dato i ark", "Kamp", "Tjans"],
       "Ingen — alle tjanser peger på en kamp der stadig findes.")}

<h2>Kampe der er flyttet siden tjanselisten blev lavet</h2>
{tabel(fl_rows, ["Kampnr.", "Stod til", "Er nu", "Tjans", "Kamp"],
       "Ingen kampe er flyttet. Tjanserne følger med automatisk, hvis det sker.")}

{holdsport_afsnit}

<h2>Feeds til Holdsport</h2>
<p class="sub">Importér ét feed pr. hold under Kalender → Mere → Importer kampprogram →
WebCal. Sæt maks. antal deltagere til tallet i kolonnen, og slå automatisk
opdatering én gang i døgnet til.</p>
{tabel(feed_rows, ["Hold", "Maks. deltagere", "Tjanser", "Periode", "Feed-adresse"], "")}
<p class="muted" style="font-size:13px;margin-top:10px">Importerne i Holdsport blev lavet, da repoet hed
Tjanser-i-Holdsport, og peger på <code>{E(base_url or "../")}Tjanser-i-Holdsport/feeds/…</code>.
Den adresse opdateres hver nat sammen med de nye, så importerne skal ikke laves om.
Nye importer kan bruge adresserne i tabellen.</p>

<h2>Fordeling</h2>
<div class="stats">{hold_stats}</div>

<h2>Hele sæsonen</h2>
{tabel(sae_rows, ["Dato", "Kampstart", "Mødetid", "Kamp", "Række", "Antal", "Tjans", ""], "")}

<footer>Bygget automatisk ud fra tjanselisten og de officielle kampprogrammer fra
resultater.volleyball.dk. Siden og kalenderne opdateres hver nat.</footer>
</div></body></html>"""


if __name__ == "__main__":
    st = json.load(open(os.path.join(ROOT, "docs", "status.json"), encoding="utf-8"))
    os.makedirs(os.path.join(ROOT, "docs", "tjanser"), exist_ok=True)
    out = os.path.join(ROOT, "docs", "tjanser", "index.html")
    open(out, "w", encoding="utf-8").write(render(st, os.environ.get("BASE_URL", "")))
    print("skrev", out)
