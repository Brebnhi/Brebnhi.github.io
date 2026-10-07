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
.st-ok{color:var(--ok);font-weight:600}.st-taet{color:var(--warn);font-weight:600}
.st-konflikt{color:var(--bad);font-weight:600}
.st-ign{color:var(--muted);text-decoration:line-through;font-weight:400}
tr.ignoreret .aktiv,tr:not(.ignoreret) .ign{display:none}
tr.venter{opacity:.55}
.knap{margin-top:5px;padding:3px 12px;border:1px solid var(--line);border-radius:6px;
background:var(--card);font:600 12.5px/1.4 inherit;color:var(--accent);cursor:pointer}
.knap:hover{border-color:var(--accent)}
.link{border:0;background:none;padding:0;font:inherit;color:var(--accent);cursor:pointer;
text-decoration:underline}
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
    konflikter = status.get("konflikter") or []
    genbrugt = hs.get("genbrugt") or []
    forkert_tid = hs.get("forkert_tid") or []      # står på et andet tidspunkt i Holdsport
    venter_tid = hs.get("venter_tid") or []        # flyttet for nylig, Holdsport har ikke hentet
    andre = len(huller) + len(forsv) + len(slettet) + len(genbrugt) + len(forkert_tid)
    problemer = andre + len(konflikter)

    venter = hs.get("venter") or []
    if not hs.get("aktiveret") or hs.get("fejl"):
        hs_tekst = "."
    elif venter:
        hs_tekst = (f', og {hs["fundet"]} af {hs["kontrolleret"]} tjanser ligger allerede i '
                    f'Holdsport. {len(venter)} {"ny venter" if len(venter) == 1 else "nye venter"} '
                    'på, at Holdsport henter kalenderen.')
    else:
        hs_tekst = f', og alle {hs["fundet"]} tjanser ligger i Holdsport.'
    if venter_tid and hs.get("aktiveret") and not hs.get("fejl"):
        hs_tekst += (f' {len(venter_tid)} {"tjans er" if len(venter_tid) == 1 else "tjanser er"} '
                     'flyttet med kampen og venter på, at Holdsport henter det nye tidspunkt.')
    ok_tekst = ('<strong>Alle hjemmekampe er dækket</strong>'
                f'Alle {status["feed_kampe"]} kampe i kampprogrammet er tjekket mod '
                'tjanselisten — hver hjemmekamp har et hold på tjans' + hs_tekst)
    bits = []
    if huller:
        bits.append(f"{len(huller)} hjemmekamp{'e' if len(huller)>1 else ''} uden hold på tjans")
    if forsv:
        bits.append(f"{len(forsv)} tjans{'er' if len(forsv)>1 else ''} hvor kampen ikke længere findes")
    if slettet:
        bits.append(f"{len(slettet)} tjans{'er' if len(slettet)>1 else ''} slettet i Holdsport")
    if genbrugt:
        bits.append(f"{len(genbrugt)} tjans{'er' if len(genbrugt)>1 else ''} i Holdsport, der har "
                    "fået en andens tilmeldinger")
    if forkert_tid:
        bits.append(f"{len(forkert_tid)} tjans{'er' if len(forkert_tid)>1 else ''} på et forkert "
                    "tidspunkt i Holdsport")
    andre_bits = " og ".join(bits)
    if konflikter:
        bits.append(f"{len(konflikter)} tjans{'er' if len(konflikter)>1 else ''} oven i holdets egen kamp")
    # data-*: så Ignorér-knappen kan rette banneret med det samme (se ign_js nedenfor)
    banner_data = (f' id="banner" data-andre="{andre}" data-bits="{E(andre_bits)}"'
                   if status.get("mellemmand") else "")
    if problemer == 0:
        banner = f'<div class="banner ok"{banner_data}>{ok_tekst}</div>'
    else:
        banner = (f'<div class="banner bad"{banner_data}><strong>{problemer} ting kræver '
                  'handling</strong>' + " og ".join(bits) + ".</div>")
    if banner_data:
        banner += f'<template id="banner-ok">{ok_tekst}</template>'

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
                   f"<td>{E(m['navn'])}"
                   + ("<br><span class='muted'>var i Holdsport før</span>" if m.get("foer_fundet") else "")
                   + "</td>"
                   f"<td><span class='tag'>{E(m['tjans'])}</span></td>"
                   f"<td class='muted'>{E(m['holdsport'])}</td></tr>" for m in slettet]
        ve_rows = [f"<tr><td><code>{E(m['kampnr'])}</code></td><td>{E(m['start'])}</td>"
                   f"<td>{E(m['navn'])}</td>"
                   f"<td><span class='tag'>{E(m['tjans'])}</span></td></tr>" for m in venter]
        hold_rows = []
        for h in hs.get("hold", []):
            status_tekst = (f"{h['fundet']} af {h['forventet']}"
                            + (f" · {h['venter']} venter" if h.get("venter") else "")
                            + (f" · {h['forkert_tid']} på forkert tidspunkt"
                               if h.get("forkert_tid") else "")
                            if not h.get("fejl") else E(h["fejl"]))
            hold_rows.append(
                f"<tr><td><span class='tag'>{E(h['kode'])}</span></td>"
                f"<td>{E(h.get('holdsport') or '—')}</td>"
                f"<td class='muted'>{E(h.get('id') or '')}</td>"
                f"<td>{status_tekst}</td>"
                f"<td class='muted'>{E(h.get('match',''))}</td></tr>")
        alle = ", ".join(f"{E(h['navn'])} (id {E(h['id'])})" for h in hs.get("alle_hold", []))
        gb_rows = [f"<tr><td><span class='tag'>{E(g['tjans'])}</span></td>"
                   f"<td>{E(g['foer_start'])} <span class='muted'>kamp {E(g['foer'].split('-')[0])}</span></td>"
                   f"<td>{E(g['nu_start'])} <span class='muted'>kamp {E(g['nu'].split('-')[0])}</span></td>"
                   f"<td class='muted'>{E(g['aktivitet'])}</td></tr>" for g in genbrugt]
        genbrug_afsnit = (
            "<div class='banner bad'><strong>Holdsport har genbrugt en tjans</strong>"
            "Holdsport har lavet en eksisterende tjans om til en ny, da den hentede kalenderen. "
            "Tilmeldingerne fulgte med, så de står nu på den forkerte dag. Tjek, hvem der er "
            "tilmeldt, og om den gamle tjans er kommet igen.</div>"
            + tabel(gb_rows, ["Hold", "Var tjansen", "Er nu tjansen", "Aktivitet i Holdsport"], "")
            if genbrugt else "")

        def tid_tr(r):
            return (f"<tr><td><span class='tag'>{E(r['tjans'])}</span></td>"
                    f"<td><span class='muted'>{E(r['hs_start'])}</span> → "
                    f"<strong>{E(r['start'])}</strong>"
                    + ("<br><span class='muted'>ekstra kopi på det gamle tidspunkt – slet den"
                       "</span>" if r.get("dublet") else "")
                    + f"</td><td>{E(r['navn'])}<br><span class='muted'>kamp {E(r['kampnr'])}"
                    f"</span></td><td class='muted'>{E(r['holdsport'])}</td></tr>")
        tid_kol = ["Tjans", "Står i Holdsport → skal stå (mødetid)", "Aktivitet",
                   "Hold i Holdsport"]
        tid_afsnit = (
            "<div class='banner bad'><strong>Holdsport har ikke flyttet tjansen med kampen"
            "</strong>Kampen er flyttet, men tjansen står stadig på det gamle tidspunkt i "
            "Holdsport (eller der ligger en ekstra kopi dér). Ret tidspunktet på aktiviteten i "
            "Holdsport — eller slet kopien — og tjek, om de tilmeldte stadig kan.</div>"
            + tabel([tid_tr(r) for r in forkert_tid], tid_kol, "")
            if forkert_tid else "")
        holdsport_afsnit = (
            "<h2>Kontrol mod Holdsport</h2>" + genbrug_afsnit + tid_afsnit +
            f"<p class='sub'>{hs['fundet']} af {hs['kontrolleret']} tjanser fundet i "
            "Holdsport ved sidste kørsel. Holdsport henter kalenderne én gang i døgnet, så en "
            "ny eller flyttet tjans får halvandet døgn til at komme over. En tjans, der har "
            "været i Holdsport og er væk, meldes med det samme.</p>"
            + tabel(sl_rows, ["Kampnr.", "Mødetid", "Aktivitet", "Tjans", "Hold i Holdsport"],
                    "Ingen tjanser er blevet slettet — alle ligger som de skal.")
            + ("<p class='sub' style='margin-top:14px'>Nye i kalenderen — venter på, at "
               "Holdsport henter dem:</p>"
               + tabel(ve_rows, ["Kampnr.", "Mødetid", "Aktivitet", "Tjans"], "")
               if venter else "")
            + ("<p class='sub' style='margin-top:14px'>Flyttet med kampen — venter på, at "
               "Holdsport henter det nye tidspunkt:</p>"
               + tabel([tid_tr(r) for r in venter_tid], tid_kol, "")
               if venter_tid else "")
            + "<h2>Holdopslag</h2>"
            + "<p class='sub'>Sådan er holdene fra tjanselisten koblet til dine hold i "
              "Holdsport. Passer et opslag ikke, så ret navnet eller nummeret i "
              "<code>data/holdsport_hold.json</code>.</p>"
            + tabel(hold_rows, ["Hold", "Hold i Holdsport", "Id", "Fundet", "Fundet ved"], "")
            + (f"<p class='tnote'>Alle hold på din Holdsport-bruger: {alle}</p>" if alle else ""))

    # Sæsonen står ikke i koden: build.py finder den ud fra datoerne i tjanselisten.
    titel = f"Tjanser {status['saeson']}" if status.get("saeson") else "Tjanser"

    # Tjans og egen kamp samme dag — reglen er mindst én kamp imellem
    MAERKE = {"ok": "✓", "taet": "⚠", "konflikt": "⛔"}
    egne = status.get("egen_kamp") or []
    mm = status.get("mellemmand") or ""

    def vurdering(e):
        tekst = f"{MAERKE.get(e['status'], '')} {E(e['tekst'])}"
        if e["status"] == "ok":
            return f"<td class='st-ok'>{tekst}</td>"
        knap = "<br><button type='button' class='knap' data-handling='ignorer'>Ignorér</button>" if mm else ""
        fortryd = (" · <button type='button' class='link' data-handling='fortryd'>fortryd</button>"
                   if mm else "")
        return (f"<td class='st-{E(e['status'])}'><span class='aktiv'>{tekst}{knap}</span>"
                f"<span class='ign'><span class='st-ign'>{tekst}</span><br>"
                f"<span class='muted'>Ignoreret{fortryd}</span></span></td>")

    def egen_tr(e):
        if e["status"] == "ok":
            return "<tr>"
        return (f"<tr data-noegle='{E(e['noegle'])}'"
                f"{' data-konflikt' if e['status'] == 'konflikt' else ''}"
                f"{' class=ignoreret' if e.get('ignoreret') else ''}>")
    egen_rows = [f"{egen_tr(e)}<td style='white-space:nowrap'>{E(e['dato'][:6] + e['dato'][8:])}</td>"
                 f"<td><span class='tag'>{E(e['hold'])}</span></td>"
                 f"{vurdering(e)}"
                 f"<td>{E(e['tjans_kl'])} <span class='muted'>{E(e['tjans_kamp'])}</span></td>"
                 f"<td>{E(e['egen_kl'])} <span class='muted'>{E(e['egen_kamp'])}"
                 f"{'' if e['hjemme'] else ' (ude)'}</span></td></tr>"
                 for e in egne]
    egen_afsnit = ("<h2>Tjans og egen kamp samme dag</h2>"
                   "<p class='sub'>Reglen er mindst én kamp imellem holdets egen kamp og tjansen "
                   "— eller omvendt. Tiderne er Volleyball Danmarks, så tjekket følger med, når "
                   "kampe flyttes. ⛔ betyder, at tjansen ligger oven i holdets egen kamp."
                   + (" Tryk <b>Ignorér</b>, hvis det er i orden — så melder robotten den ikke "
                      "igen, medmindre en af kampene bliver flyttet." if mm else "")
                   + "</p><p class='muted' id='ign-besked' hidden></p>"
                   + tabel(egen_rows, ["Dato", "Hold", "Vurdering", "Tjans", "Egen kamp"],
                           "Ingen kommende tjanser ligger på en dag, hvor holdet selv spiller."))

    # Kampprogrammer og holdkoder, som robotten selv har fundet hos Volleyball Danmark
    kp = status.get("kampprogrammer") or {}
    def kp_raekke(p):
        koder = " ".join(f"<span class='tag'>{E(k)}</span>" for k in p.get("koder") or [])
        kalender = (f"<code>{E(p['url'])}</code>" if p.get("url")
                    else "<span class='muted'>intet kampprogram endnu</span>")
        return f"<tr><td>{E(p['navn'])}</td><td>{koder or '–'}</td><td>{kalender}</td></tr>"
    kp_rows = [kp_raekke(p) for p in kp.get("puljer") or []]
    koder_tekst = " · ".join(f"<span style='white-space:nowrap'><span class='tag'>"
                             f"{E(h['kode'])}</span> {E(h['hold'])} "
                             f"<span class='muted'>({E(h['raekke'])})</span></span>"
                             for h in kp.get("hold") or [])
    if kp.get("puljer"):
        kp_afsnit = ("<h2>Kampprogrammer fra Volleyball Danmark</h2>"
                     "<p class='sub'>Robotten finder selv klubbens kampprogrammer og holdkoder "
                     "hver nat — også i en ny sæson og til pokalrunder og slutspil.</p>"
                     + (f"<p>{koder_tekst}</p>" if koder_tekst else "")
                     + tabel(kp_rows, ["Række og pulje", "Klubbens hold", "Kalender"], "")
                     + (("<p class='sub' style='margin-top:14px'>Ikke med i tjanserne: "
                         + ", ".join(E(u) for u in kp["udeladt"]) + ".</p>")
                        if kp.get("udeladt") else ""))
    else:
        kp_afsnit = ("<h2>Kampprogrammer fra Volleyball Danmark</h2>"
                     "<div class='banner bad'><strong>Kunne ikke finde kampprogrammerne "
                     "automatisk</strong>Bruger adresserne i <code>data/feeds.json</code>. "
                     + E(kp.get("fejl") or "") + "</div>") if kp else ""

    fejl = status.get("feed_fejl") or {}
    fejl_html = ""
    tjanskilde = status.get("tjanskilde") or ""
    if "Google-arket kunne ikke læses" in tjanskilde:
        fejl_html += ('<div class="banner bad"><strong>Google-arket med tjanselisten kunne '
                      'ikke læses</strong>' + E(tjanskilde.split(": ", 1)[-1]) + '. Siden og '
                      'kalenderne bruger data/tjanser.csv, indtil arket kan læses igen.</div>')
    if fejl:
        fejl_html += ('<div class="banner bad"><strong>Kampprogrammet kunne ikke hentes</strong>'
                     + E(", ".join(f"{k}: {v}" for k, v in fejl.items())) + "</div>")

    ign_js = ""
    if mm:
        ign_js = """<script>
(function () {
  "use strict";
  var M = %s;                        // tjansernes mellemmand (scripts/indstillinger.py)
  var besked = document.getElementById("ign-besked");
  var sendt = 0, vist = 0;           // svar på et ældre kald end det viste bruges ikke
  function sig(tekst) {
    besked.textContent = tekst;
    besked.hidden = !tekst;
  }
  function banner() {                // banneret øverst følger med med det samme
    var b = document.getElementById("banner");
    if (!b) return;
    var k = document.querySelectorAll("tr[data-konflikt]:not(.ignoreret)").length;
    var i = +b.getAttribute("data-andre") + k;
    if (!i) {
      b.className = "banner ok";
      b.innerHTML = document.getElementById("banner-ok").innerHTML;
      return;
    }
    var dele = [b.getAttribute("data-bits"),
                k ? k + (k > 1 ? " tjanser" : " tjans") + " oven i holdets egen kamp" : ""];
    var s = document.createElement("strong");
    s.textContent = i + " ting kræver handling";
    b.className = "banner bad";
    b.textContent = "";
    b.appendChild(s);
    b.appendChild(document.createTextNode(dele.filter(Boolean).join(" og ") + "."));
  }
  function vis(liste) {
    var s = {};
    (liste || []).forEach(function (n) { s[n] = 1; });
    document.querySelectorAll("tr[data-noegle]:not(.venter)").forEach(function (tr) {
      tr.classList.toggle("ignoreret", !!s[tr.getAttribute("data-noegle")]);
    });
    banner();
  }
  function kald(spoergsmaal) {
    var nr = ++sendt;
    return fetch(M + spoergsmaal).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      if (!d.ok) throw new Error(d.fejl || "fejl");
      d.nyest = nr > vist;
      if (d.nyest) vist = nr;
      return d;
    });
  }
  function tryk(knap) {
    var tr = knap.closest("tr[data-noegle]");
    var ignorer = knap.getAttribute("data-handling") === "ignorer";
    sig("");
    tr.classList.toggle("ignoreret", ignorer);
    tr.classList.add("venter");
    banner();
    kald("?" + (ignorer ? "ignorer" : "fortryd") + "=" +
         encodeURIComponent(tr.getAttribute("data-noegle"))).then(function (d) {
      tr.classList.remove("venter");
      if (d.nyest) vis(d.ignoreret);
    }).catch(function () {
      tr.classList.remove("venter");
      tr.classList.toggle("ignoreret", !ignorer);
      banner();
      sig("Mellemmanden svarede ikke — prøv igen om lidt.");
    });
  }
  document.addEventListener("click", function (ev) {
    var knap = ev.target.closest ? ev.target.closest("button[data-handling]") : null;
    if (knap) tryk(knap);
  });
  // Den aktuelle liste — også det, der er ignoreret siden robottens sidste kørsel
  kald("").then(function (d) { if (d.nyest) vis(d.ignoreret); }).catch(function () {});
  // Fra mailen: .../tjanser/#ignorer=148228-D1-3fa2
  var m = /^#ignorer=([\w-]+)$/.exec(location.hash);
  if (m) {
    history.replaceState(null, "", location.pathname + location.search);
    var tr = document.querySelector('tr[data-noegle="' + m[1] + '"]');
    var knap = tr && tr.querySelector('button[data-handling="ignorer"]');
    if (!tr) {
      sig("Advarslen fra mailen er her ikke længere — en af kampene er nok blevet flyttet. " +
          "Se den nye vurdering nedenfor.");
      besked.scrollIntoView({block: "center"});
    } else {
      tr.scrollIntoView({block: "center"});
      if (knap && !tr.classList.contains("ignoreret")) tryk(knap);
    }
  }
})();
</script>""" % json.dumps(mm)

    return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(titel)} · Aalborg Volley</title>
<style>{CSS}</style></head><body><div class="wrap">
<p class="nav"><a href="../">← Alle projekter</a></p>
<h1>{E(titel)}</h1>
<p class="sub">Aalborg Volley · opdateret {E(status['opdateret'])} ·
{status['feed_kampe']} kampe hentet fra kampprogrammet ·
tjanseliste: {"Google-arket" if tjanskilde == "Google Sheet" else "data/tjanser.csv"}</p>
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

{egen_afsnit}

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

{kp_afsnit}

<h2>Fordeling</h2>
<div class="stats">{hold_stats}</div>

<h2>Hele sæsonen</h2>
{tabel(sae_rows, ["Dato", "Kampstart", "Mødetid", "Kamp", "Række", "Antal", "Tjans", ""], "")}

<footer>Bygget automatisk ud fra tjanselisten og de officielle kampprogrammer fra
resultater.volleyball.dk. Siden og kalenderne opdateres hver nat og kort efter ændringer i
tjanselisten.</footer>
</div>{ign_js}</body></html>"""


if __name__ == "__main__":
    st = json.load(open(os.path.join(ROOT, "docs", "status.json"), encoding="utf-8"))
    os.makedirs(os.path.join(ROOT, "docs", "tjanser"), exist_ok=True)
    out = os.path.join(ROOT, "docs", "tjanser", "index.html")
    open(out, "w", encoding="utf-8").write(render(st, os.environ.get("BASE_URL", "")))
    print("skrev", out)
