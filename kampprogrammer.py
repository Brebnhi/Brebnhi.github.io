#!/usr/bin/env python3
# sti: tjans/scripts/kampprogrammer.py
"""Finder klubbens kampprogrammer og holdkoder hos Volleyball Danmark — hver nat.

Bruger samme opslag som kørselsudligningen (koerselsudligning/scripts/beregn.py):
foreningens holdoversigt på resultater.volleyball.dk (forening_id i
koerselsudligning/config.json) giver hold, række og pulje, og puljens side giver
kalenderen. Så finder robotten selv den nye sæsons kampprogrammer.

Med kommer alle klubbens puljer i Volleyligaen, 1. og 2. division (grundspil, slutspil
og kvalifikation) og i pokalturneringen. Danmarksserien, ungdom o.l. er ikke med — og
heller ikke talentholdene ("Aalborg Volleyball.2 (T)" i 2. division · Talent, okt. 2026).
Kun hold, der hedder "Aalborg Volleyball" med eller uden nummer, tæller, ligesom i
kørselsudligningen. Ellers rykker holdkoderne: talentholdene fik nummer 1 og skubbede
H2/H3/D3 ned til H4/H5/D4.

Holdkoderne (D1, H2 …) følger samme regel som i kørselsudligningen: D1/H1 er holdet i
den bedste række, og i samme række holdet med lavest nummer. Skal et hold have en
anden kode, så skriv det under "hold_koder" i koerselsudligning/config.json, fx
"1. Division Kvinder|Aalborg Volleyball.2": "D2".

Fejler opslaget, bruger build.py data/feeds.json og CLUB_TEAMS som reserve.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # tjans/
KU = os.path.join(os.path.dirname(ROOT), "koerselsudligning")


def holdnoegle(navn):
    """'Aalborg Volleyball.2' og 'Aalborg Volleyball 2' -> 'aalborgvolleyball2'."""
    return re.sub(r"[^0-9a-zæøå]", "", (navn or "").lower())


def koen(raekke):
    """'D' for kvinder, 'H' for herrer, '' hvis rækken ikke siger det."""
    r = (raekke or "").lower()
    return "H" if "herre" in r else "D" if ("kvinde" in r or "dame" in r) else ""


def nummer(navn):
    """'Aalborg Volleyball.3' -> 3, 'Aalborg Volleyball' -> 1."""
    m = re.search(r"(\d+)\s*$", navn or "")
    return int(m.group(1)) if m else 1


def _beregn():
    sti = os.path.join(KU, "scripts")
    if sti not in sys.path:
        sys.path.insert(0, sti)
    import beregn
    return beregn


def find():
    """{"feeds": {navn: url}, "koder": {(køn, holdnøgle): kode}, "hold": [...],
    "puljer": [...]} — eller en fejl, hvis klubbens hold ikke kan findes."""
    b = _beregn()
    kfg = json.load(open(os.path.join(KU, "config.json"), encoding="utf-8"))
    overstyr = {k: v for k, v in (kfg.get("hold_koder") or {}).items() if not k.startswith("_")}

    grund, puljer, udeladt = set(), {}, []
    klub = b.klubregex(kfg)                       # "Aalborg Volleyball", "… .2" osv.
    for h in b.klubbens_hold(kfg["forening_id"]):
        if not klub.fullmatch((h["hold"] or "").strip()):
            udeladt.append(f"{h['hold']} ({h['raekke']} · {h['pulje']})")   # fx talenthold
            continue
        navn = b.raekke_navn(h["raekke"], kfg)       # fx "2. Division Herrer"
        pokal = b.er_pokal(h["raekke"], kfg)
        if not navn and not pokal:
            continue                                  # Danmarksserien, ungdom o.l.
        if navn and b.norm(navn) == b.norm(h["raekke"]):
            grund.add((navn, h["hold"]))              # grundspillet giver holdkoderne
        p = puljer.setdefault(h["pulje_id"], {"raekke": h["raekke"], "pulje": h["pulje"],
                                              "hold": set()})
        p["hold"].add(h["hold"])
    if not grund:
        raise RuntimeError("fandt ingen af klubbens hold i Liga, 1. eller 2. division "
                           f"(ForeningsId {kfg['forening_id']})")

    # D1/H1 = bedste række; samme række: laveste nummer (som i kørselsudligningen)
    koder, hold, taeller = {}, [], {"D": 0, "H": 0}
    for raekke, holdnavn in sorted(grund, key=lambda x: (b.niveau(x[0]), nummer(x[1]))):
        k = koen(raekke)
        if not k:
            continue
        taeller[k] += 1
        kode = overstyr.get(f"{raekke}|{holdnavn}") or f"{k}{taeller[k]}"
        koder[(k, holdnoegle(holdnavn))] = kode
        hold.append({"kode": kode, "hold": holdnavn, "raekke": raekke})

    feeds, info = {}, []
    for pid, p in sorted(puljer.items(), key=lambda x: (x[1]["raekke"], x[1]["pulje"])):
        noegle = b.kalender_noegle(pid)
        url = b.CAL + noegle if noegle else None
        navn = f"{p['raekke']} · {p['pulje']}" if p["pulje"] else p["raekke"]
        koderne = sorted({koder.get((koen(p["raekke"]), holdnoegle(h)), "")
                          for h in p["hold"]} - {""})
        info.append({"navn": navn, "pulje_id": pid, "url": url, "koder": koderne,
                     "hold": sorted(p["hold"])})
        if url:
            feeds[navn] = url
    if not feeds:
        raise RuntimeError("ingen af klubbens puljer har et kampprogram endnu")
    hold.sort(key=lambda h: (h["kode"][0], nummer(h["kode"])))
    return {"feeds": feeds, "koder": koder, "hold": hold, "puljer": info,
            "udeladt": sorted(set(udeladt))}


if __name__ == "__main__":
    r = find()
    for h in r["hold"]:
        print(f"{h['kode']:3} {h['raekke']:22} {h['hold']}")
    for p in r["puljer"]:
        print(f"{', '.join(p['koder']) or '–':8} {p['navn']:45} {p['url'] or 'intet kampprogram endnu'}")
