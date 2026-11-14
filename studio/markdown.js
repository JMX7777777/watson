// Watson – gemeinsame Darstellung der Antworten (Laptop + Handy) und „Ganze Nachricht kopieren“.
// Markdown -> sicheres HTML (alles wird zuerst maskiert, nur bekannte Formatierungen werden umgesetzt).
(function () {
  const esc = t => String(t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  // Formatierung innerhalb einer Zeile: Code, Links, fett, kursiv, durchgestrichen
  function inline(t) {
    const codes = [], links = [];
    const merk = html => { links.push(html); return `\u0001${links.length - 1}\u0001`; };   // Links vor fett/kursiv schützen
    let s = esc(t).replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, txt, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${txt}</a>`.replace(/href="[^"]*"/, h => merk(h)));
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)\u0001]+[^\s<).,!?:;"'\u0001])/g, (_, vor, url) => vor + merk(`<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`));
    s = s.replace(/\*\*(?=\S)([\s\S]+?)\*\*/g, "<b>$1</b>").replace(/__(?=\S)([^_\n]+?)__/g, "<b>$1</b>");
    s = s.replace(/(^|[^\w*])\*(?=\S)([^*\n]+?)\*(?!\w)/g, "$1<i>$2</i>").replace(/(^|[^\w])_(?=\S)([^_\n]+?)_(?!\w)/g, "$1<i>$2</i>");
    s = s.replace(/~~(?=\S)([^~\n]+?)~~/g, "<s>$1</s>");
    s = s.replace(/\u0001(\d+)\u0001/g, (_, n) => links[+n]);
    return s.replace(/\u0000(\d+)\u0000/g, (_, n) => `<code>${codes[+n]}</code>`);
  }

  const IST_LISTE = /^(\s*)([-*•+]|\d+[.)])\s+/;
  const IST_TABELLE = /^\s*\|.*\|\s*$/;
  const TRENNER = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

  function block(text) {
    const z = String(text || "").replace(/\r/g, "").split("\n"), out = [];
    let i = 0;
    const istBlockStart = s => /^\s*```/.test(s) || IST_TABELLE.test(s) || IST_LISTE.test(s) || /^#{1,6}\s/.test(s) ||
                                /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(s) || /^\s*&gt;|^\s*>/.test(s);
    while (i < z.length) {
      const zeile = z[i];
      if (/^\s*```/.test(zeile)) {                                   // Code-Block
        const code = []; i++;
        while (i < z.length && !/^\s*```/.test(z[i])) code.push(z[i++]);
        i++; out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`); continue;
      }
      if (IST_TABELLE.test(zeile)) {                                 // Tabelle
        const rows = [];
        while (i < z.length && IST_TABELLE.test(z[i])) rows.push(z[i++]);
        const zellen = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        const kopf = rows.length > 1 && TRENNER.test(rows[1]);
        const body = (kopf ? rows.slice(2) : rows).filter(r => !TRENNER.test(r));
        out.push('<div class="mdTabelle"><table>' + (kopf ? "<thead><tr>" + zellen(rows[0]).map(c => `<th>${inline(c)}</th>`).join("") + "</tr></thead>" : "") +
                 "<tbody>" + body.map(r => "<tr>" + zellen(r).map(c => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table></div>");
        continue;
      }
      if (IST_LISTE.test(zeile)) {                                   // Liste (auch verschachtelt, nummeriert)
        const stapel = [];
        const oeffnen = (art, start, tiefe) => { stapel.push({art, tiefe}); out.push(art === "ol" && start > 1 ? `<ol start="${start}">` : `<${art}>`); };
        while (i < z.length && (IST_LISTE.test(z[i]) || (/^\s{2,}\S/.test(z[i]) && stapel.length))) {
          const m = z[i].match(IST_LISTE);
          if (!m) { out[out.length - 1] = out[out.length - 1].replace(/<\/li>$/, " " + inline(z[i].trim()) + "</li>"); i++; continue; }
          const tiefe = m[1].replace(/\t/g, "    ").length, art = /\d/.test(m[2]) ? "ol" : "ul";
          while (stapel.length && tiefe < stapel[stapel.length - 1].tiefe) out.push(`</${stapel.pop().art}>`);
          if (!stapel.length || tiefe > stapel[stapel.length - 1].tiefe) oeffnen(art, parseInt(m[2]) || 1, tiefe);
          else if (stapel[stapel.length - 1].art !== art) { out.push(`</${stapel.pop().art}>`); oeffnen(art, parseInt(m[2]) || 1, tiefe); }
          out.push(`<li>${inline(z[i].slice(m[0].length))}</li>`); i++;
        }
        while (stapel.length) out.push(`</${stapel.pop().art}>`);
        continue;
      }
      const h = zeile.match(/^(#{1,6})\s+(.*?)\s*#*$/);               // Überschrift
      if (h) { const n = Math.min(4, h[1].length + 1); out.push(`<h${n}>${inline(h[2])}</h${n}>`); i++; continue; }
      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(zeile)) { out.push("<hr>"); i++; continue; }   // Linie
      if (/^\s*>/.test(zeile)) {                                      // Zitat
        const q = [];
        while (i < z.length && /^\s*>/.test(z[i])) q.push(z[i++].replace(/^\s*>\s?/, ""));
        out.push(`<blockquote>${block(q.join("\n"))}</blockquote>`); continue;
      }
      if (!zeile.trim()) { i++; continue; }
      const p = [];                                                    // Absatz
      while (i < z.length && z[i].trim() && (!istBlockStart(z[i]) || !p.length)) p.push(z[i++]);
      out.push(`<p>${p.map(inline).join("<br>")}</p>`);
    }
    return out.join("");
  }

  // Für eigene Nachrichten: nur Text mit Zeilenumbrüchen (keine Formatierung), Links anklickbar
  function einfach(text) {
    return esc(text).replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>').replace(/\n/g, "<br>");
  }

  // Lesbarer Klartext einer dargestellten Nachricht (Tabellen mit Tabs, Listen mit Punkten) – zum Kopieren
  function klartext(el) {
    const teile = [];
    const lauf = (n, liste) => {
      for (const k of n.childNodes) {
        if (k.nodeType === 3) { teile.push(k.nodeValue); continue; }
        if (k.nodeType !== 1 || k.matches(".kopierKnopf,.who")) continue;
        const t = k.tagName;
        if (t === "BR") { teile.push("\n"); continue; }
        if (t === "TABLE") {
          for (const tr of k.querySelectorAll("tr")) teile.push([...tr.children].map(c => c.innerText.trim()).join("\t") + "\n");
          teile.push("\n"); continue;
        }
        if (t === "UL" || t === "OL") { lauf(k, t); teile.push("\n"); continue; }
        if (t === "LI") {
          let tiefe = 0; for (let a = k.parentNode.parentNode; a && a !== el; a = a.parentNode) if (/^(UL|OL)$/.test(a.tagName)) tiefe++;
          const nr = liste === "OL" ? ([...k.parentNode.children].indexOf(k) + (+k.parentNode.getAttribute("start") || 1)) + ". " : "• ";
          if (teile.length && !/\n$/.test(teile[teile.length - 1])) teile.push("\n");
          teile.push("    ".repeat(tiefe) + nr); lauf(k, liste); teile.push("\n"); continue;
        }
        if (t === "PRE") { teile.push(k.innerText.replace(/\n?$/, "\n\n")); continue; }
        lauf(k, liste);
        if (/^(P|H\d|BLOCKQUOTE|DIV|HR)$/.test(t)) teile.push(t === "HR" ? "———\n\n" : "\n\n");
      }
    };
    lauf(el);
    return teile.join("").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  async function kopieren(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
    try {                                                               // Ersatz für ältere Browser / ohne Freigabe
      const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:-1000px;opacity:0"; document.body.appendChild(ta); ta.select();
      const ok = document.execCommand("copy"); ta.remove(); return ok;
    } catch (e) { return false; }
  }

  // Kopier-Knopf an eine Nachricht hängen (ganze Nachricht als Klartext); Teile markieren geht weiterhin normal
  function kopierKnopf(blase, inhalt) {
    const k = document.createElement("button");
    k.className = "kopierKnopf"; k.type = "button"; k.title = "Ganze Nachricht kopieren";
    k.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
    k.onclick = async e => {
      e.stopPropagation();
      const ok = await kopieren(klartext(inhalt || blase));
      k.classList.add(ok ? "ok" : "nein");
      k.innerHTML = ok ? "✓" : "!";
      k.title = ok ? "Kopiert" : "Kopieren ging nicht – bitte markieren";
      setTimeout(() => { k.classList.remove("ok", "nein"); k.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>'; k.title = "Ganze Nachricht kopieren"; }, 1600);
    };
    blase.appendChild(k);
    return k;
  }

  window.watsonMarkdown = block;
  window.watsonEinfach = einfach;
  window.watsonKlartext = klartext;
  window.watsonKopieren = kopieren;
  window.watsonKopierKnopf = kopierKnopf;
})();
