#!/usr/bin/env python3
# sti: tjans/scripts/indstillinger.py
"""Indstillinger til tjans-robotten. Ret direkte på GitHub og gem."""

# Adressen på tjansernes mellemmand: Google Apps Script-webappen, der gør Ignorér-knappen
# på tjansesiden til ét tryk. Den slutter på /exec. Tom = ingen Ignorér-knap.
# Sådan laves den: se tjans/MELLEMMAND.md.
MELLEMMAND = "https://script.google.com/macros/s/AKfycbwV4aZDlauDsiEw2f6IL084Ej313qLnObzAv8ENXxdh3u4sjXWhPHIbRp95lPYNN2W1/exec"

# Robotten retter selv i Holdsport ved hver kørsel: flytter en tjans, der står på et forkert
# tidspunkt, og opretter en tjans, der mangler. Den sletter aldrig noget. False = robotten
# læser kun og slår alarm, så du selv retter.
HOLDSPORT_RETTER = True

# Alarm på telefonen med appen ntfy (gratis, ingen konto): installér ntfy, tryk + og abonnér
# på emnet herunder. Robotten sender en besked, når noget nyt kræver handling, når den selv har
# rettet noget – og ved hver kørsel, så længe en tjans inden for 3 døgn står forkert eller
# mangler. Tom = ingen alarm.
ALARM_NTFY = "aav-tjans-x7t6nj282s"
