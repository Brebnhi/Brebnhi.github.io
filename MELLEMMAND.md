<!-- sti: tjans/MELLEMMAND.md -->
# Tjansernes mellemmand

Gør **Ignorér** på tjansesiden til ét tryk. Mellemmanden er et lille Google Apps Script på
din Google-konto, der husker, hvilke advarsler du har ignoreret. Tjansesiden spørger den,
når den åbnes, og når du trykker. Robotten spørger hver nat. Der gemmes intet på GitHub,
så et tryk kræver ingen commit. Det er samme slags script som *Bestyrelsens mellemmand*.

## Opsætning (én gang – nemmest på en computer)

1. **Valgfrit – lav en nøgle:** [ny fine-grained token](https://github.com/settings/personal-access-tokens/new?name=Tjansernes%20mellemmand&description=Lader%20Ignor%C3%A9r-knappen%20p%C3%A5%20tjansesiden%20starte%20tjans-robotten&target_name=Brebnhi&expires_in=none&actions=write).
   Vælg *Only select repositories* → `Brebnhi.github.io`, tryk **Generate token** og kopiér
   nøglen. Med den kører robotten med det samme efter et tryk, så issuet og startsiden
   følger med efter et par minutter. Uden den sker det ved robottens næste kørsel om natten.
   Tjansesiden følger med med det samme uanset hvad.
2. **Lav scriptet:** gå til [script.google.com](https://script.google.com) → **Nyt projekt**.
   Kald det *Tjansernes mellemmand*, slet det, der står, og indsæt koden nedenfor. Har du
   lavet en nøgle, så sæt den ind i stedet for `SÆT-DIN-NØGLE-IND-HER`. Gem.
3. **Udgiv det:** **Implementer → Ny implementering** → tandhjulet → **Webapp**.
   *Udfør som:* Mig · *Hvem har adgang:* Alle → **Implementer** → godkend adgangen
   (*Avanceret → Gå til Tjansernes mellemmand*). Kopiér webappens adresse (slutter på `/exec`).
4. **Sæt adressen ind** i [`tjans/scripts/indstillinger.py`](https://github.com/Brebnhi/Brebnhi.github.io/edit/main/tjans/scripts/indstillinger.py)
   mellem anførselstegnene og tryk **Commit changes**. Robotten kører med det samme, og et
   par minutter efter står knappen på tjansesiden.

## Godt at vide

- **Ignorér gælder tjansen, som den ligger nu.** Flytter Volleyball Danmark tjansens kamp
  eller holdets egen kamp, vurderer robotten den igen.
- Alle, der åbner tjansesiden, kan se knappen. Det, der er ignoreret, står altid
  overstreget med *fortryd* ved siden af.
- Svarer mellemmanden ikke, bruger robotten listen fra sidste kørsel.
- **Tjek nøglen:** vælg `tjekGitHub` i menuen foroven i editoren og tryk **Kør**.
- **Retter du i koden** (fx for at sætte en nøgle ind senere), så brug **Implementer →
  Administrer implementeringer → blyanten → Version: Ny version → Implementer**. Så beholder
  mellemmanden sin adresse.
- Nøglen ligger kun i dit Google-script – aldrig i det offentlige repo. Vil du lukke for
  den, så slet den på GitHub under *Settings → Developer settings → Fine-grained tokens*.

## Koden

```javascript
/**
 * Tjansernes mellemmand – Aalborg Volley
 *
 * Husker, hvilke advarsler du har ignoreret på tjansesiden (brebnhi.github.io/tjanser/).
 * Siden spørger her, når den åbnes, og når du trykker Ignorér. Robotten spørger hver nat.
 *
 *   .../exec                          giver listen
 *   .../exec?ignorer=148228-D1-3fa2   ignorerer den advarsel
 *   .../exec?fortryd=148228-D1-3fa2   fortryder
 */

// Valgfrit: din GitHub-nøgle (Actions: Read and write på Brebnhi.github.io). Med den kører
// robotten med det samme efter hvert tryk, så issuet og startsiden følger med med det samme.
// Uden den sker det ved robottens næste kørsel. Tjansesiden følger med med det samme uanset hvad.
const NOEGLE = 'SÆT-DIN-NØGLE-IND-HER';

const REPO = 'Brebnhi/Brebnhi.github.io';
const WORKFLOW = 'main.yml';
const GYLDIG = /^\d{1,8}-[A-Za-z0-9]{1,8}-[0-9a-f]{4}$/;  // kampnr-hold-aftryk
const MAKS = 300;                                         // de ældste ryger ud

function doGet(e) {
  const p = (e && e.parameter) || {};
  const noegle = String(p.ignorer || p.fortryd || '');
  if (!noegle) return svar({ ok: true, ignoreret: hent() });
  if (!GYLDIG.test(noegle)) return svar({ ok: false, fejl: 'ukendt advarsel', ignoreret: hent() });

  const laas = LockService.getScriptLock();
  laas.waitLock(10000);
  let liste;
  try {
    liste = hent().filter(function (n) { return n !== noegle; });
    if (p.ignorer) liste.push(noegle);
    liste = liste.slice(-MAKS);
    PropertiesService.getScriptProperties().setProperty('ignoreret', JSON.stringify(liste));
  } finally {
    laas.releaseLock();
  }
  koerRobotten();
  return svar({ ok: true, ignoreret: liste });
}

function hent() {
  try {
    const liste = JSON.parse(PropertiesService.getScriptProperties().getProperty('ignoreret') || '[]');
    return Array.isArray(liste) ? liste : [];
  } catch (fejl) {
    return [];
  }
}

function svar(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

// Starter robotten på GitHub, hvis der er en nøgle. GitHub svarer 204, når det lykkes.
function koerRobotten() {
  const noegle = NOEGLE.trim();
  if (!/^(github_pat_|ghp_)/.test(noegle)) return 0;
  try {
    return UrlFetchApp.fetch(
      'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', {
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify({ ref: 'main' }),
        headers: { Authorization: 'Bearer ' + noegle, Accept: 'application/vnd.github+json' },
        muteHttpExceptions: true
      }).getResponseCode();
  } catch (fejl) {
    return -1;
  }
}

// Vælg tjekGitHub i menuen foroven og tryk Kør for at tjekke nøglen.
function tjekGitHub() {
  const kode = koerRobotten();
  Logger.log(kode === 204 ? 'Nøglen virker – robotten er startet.'
    : kode === 0 ? 'Der står ingen nøgle i NOEGLE øverst i koden.'
    : 'GitHub svarede ' + kode + ' – tjek at nøglen har Actions: Read and write på Brebnhi.github.io.');
}
```
