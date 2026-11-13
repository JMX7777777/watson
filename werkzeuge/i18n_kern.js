(function () {
  const D = window.WATSON_EN; if (!D) return;
  const norm = s => s.replace(/\s+/g, " ").trim();
  const esc = s => s.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  // Muster wie "Antworten {0} · bewertet {1}" -> Regex; längste zuerst (genauere Treffer)
  const muster = D.muster.slice().sort((a, b) => b[0].length - a[0].length).map(([de, en]) => {
    const teile = de.split(/\{(\d)\}/), reihenfolge = [];
    let re = "^";
    teile.forEach((t, i) => { if (i % 2) { re += "([\\s\\S]+?)"; reihenfolge.push(+t); } else re += esc(t); });
    return {re: new RegExp(re + "$"), en, reihenfolge};
  });
  function tr(text) {
    const n = norm(text);
    if (!n) return null;
    let e = D.exakt[n];
    if (e === undefined) {
      for (const m of muster) {
        const t = m.re.exec(n);
        if (t) {
          const werte = {}; m.reihenfolge.forEach((nr, i) => { werte[nr] = trWert(t[i + 1]); });
          e = m.en.replace(/\{(\d)\}/g, (_, nr) => werte[nr] ?? "");
          break;
        }
      }
    }
    if (e === undefined || e === n) return null;
    const vorne = text.match(/^\s*/)[0], hinten = text.match(/\s*$/)[0];
    return vorne + e + hinten;
  }
  const trWert = w => { const t = tr(w); return t === null ? w : t; };   // eingesetzte Werte auch übersetzen (auch Muster)
  // Nie anfassen: Gespräche, Eingaben, Code, Watson-Antworten
  const TABU = "script,style,textarea,input,code,pre,.msg,.msgText,#chat .msg,[data-kein-uebersetzen]";
  const istTabu = el => el && el.closest && el.closest(TABU);
  function knoten(n) {
    if (n.nodeType === 3) {
      if (istTabu(n.parentElement)) return;
      const t = tr(n.nodeValue); if (t !== null) n.nodeValue = t;
    } else if (n.nodeType === 1) {
      if (n.matches && n.matches(TABU) && !n.matches("input,textarea")) return;
      for (const a of ["title", "placeholder", "aria-label"]) {
        if (n.hasAttribute && n.hasAttribute(a)) { const t = tr(n.getAttribute(a)); if (t !== null) n.setAttribute(a, t); }
      }
      if (n.tagName === "INPUT" && (n.type === "button" || n.type === "submit") && n.value) { const t = tr(n.value); if (t !== null) n.value = t; }
      if (istTabu(n) && !n.matches("input,textarea")) return;
      for (const k of Array.from(n.childNodes)) knoten(k);
    }
  }
  let an = false, beob = null;
  window.watsonSprache = function (code) {
    an = code === "en";
    document.documentElement.lang = an ? "en" : "de";
    if (!an) { if (beob) beob.disconnect(); beob = null; return; }
    knoten(document.body);
    if (!beob) {
      beob = new MutationObserver(liste => {
        for (const m of liste) {
          if (m.type === "characterData") knoten(m.target);
          else if (m.type === "attributes") knoten(m.target);
          else m.addedNodes.forEach(knoten);
        }
      });
      beob.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true,
                                   attributeFilter: ["title", "placeholder", "aria-label"]});
    }
  };
  window.watsonTr = t => (an ? tr(t) ?? t : t);   // für Texte, die per JavaScript in Dialoge gehen
})();
