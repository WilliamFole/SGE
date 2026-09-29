/* app.js — gráficos SVG leves (sem libs externas, 100% offline) +
   utilitários globais: encerrar app, formatação 5 decimais, balancete helpers.
*/

// ==========================================================================
// Gráficos SVG leves (barras simples) — usados no Dashboard / Relatórios
// ==========================================================================
function renderDualChart(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const labels = JSON.parse(el.dataset.labels || "[]");
  const serie1 = JSON.parse(el.dataset.serie1 || "[]");
  const serie2 = el.dataset.serie2 ? JSON.parse(el.dataset.serie2) : null;
  const color1 = el.dataset.color1 || "#2F5233";
  const color2 = el.dataset.color2 || "#C1440E";
  const label1 = el.dataset.label1 || "";
  const label2 = el.dataset.label2 || "";
  const single = el.dataset.single === "1";

  if (!labels.length) {
    el.innerHTML = '<p class="empty-hint">Sem dados suficientes no período seleccionado.</p>';
    return;
  }

  const width = el.clientWidth || 400;
  const height = el.clientHeight || 200;
  const padL = 34, padB = 26, padT = 10, padR = 10;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const allValues = single ? serie1 : serie1.concat(serie2 || []);
  const maxVal = Math.max(1, ...allValues.map(v => Math.abs(v)));
  const minVal = Math.min(0, ...allValues);
  const range = maxVal - minVal || 1;

  const n = labels.length;
  const barGroupW = plotW / n;
  const zeroY = padT + plotH - ((0 - minVal) / range) * plotH;

  function yFor(v) { return padT + plotH - ((v - minVal) / range) * plotH; }

  let bars = "";
  const barW = single ? Math.min(24, barGroupW * 0.5) : Math.min(14, barGroupW * 0.32);

  labels.forEach((lbl, i) => {
    const cx = padL + i * barGroupW + barGroupW / 2;
    if (single) {
      const v = serie1[i];
      const y = yFor(v);
      const h = Math.abs(zeroY - y);
      const barColor = v < 0 ? color2 : color1;
      bars += `<rect x="${cx - barW/2}" y="${Math.min(y, zeroY)}" width="${barW}" height="${Math.max(h,1)}" fill="${barColor}" rx="2"><title>${lbl}: ${v}</title></rect>`;
    } else {
      const v1 = serie1[i];
      const y1 = yFor(v1);
      const h1 = Math.abs(zeroY - y1);
      bars += `<rect x="${cx - barW - 1}" y="${Math.min(y1, zeroY)}" width="${barW}" height="${Math.max(h1,1)}" fill="${color1}" rx="2"><title>${label1} ${lbl}: ${v1}</title></rect>`;
      if (serie2) {
        const v2 = serie2[i];
        const y2 = yFor(v2);
        const h2 = Math.abs(zeroY - y2);
        bars += `<rect x="${cx + 1}" y="${Math.min(y2, zeroY)}" width="${barW}" height="${Math.max(h2,1)}" fill="${color2}" rx="2"><title>${label2} ${lbl}: ${v2}</title></rect>`;
      }
    }
  });

  const step = Math.max(1, Math.ceil(n / 7));
  let xLabels = "";
  labels.forEach((lbl, i) => {
    if (i % step !== 0) return;
    const cx = padL + i * barGroupW + barGroupW / 2;
    const curto = lbl.length > 5 ? lbl.slice(5) : lbl;
    xLabels += `<text x="${cx}" y="${height - 6}" font-size="9.5" fill="#6B7268" text-anchor="middle">${curto}</text>`;
  });

  const legend = single ? "" : `
    <g transform="translate(${padL}, 2)">
      <rect width="9" height="9" fill="${color1}" rx="2"></rect>
      <text x="13" y="8" font-size="10" fill="#23281F">${label1}</text>
      <rect x="90" width="9" height="9" fill="${color2}" rx="2"></rect>
      <text x="103" y="8" font-size="10" fill="#23281F">${label2}</text>
    </g>`;

  const svg = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <line x1="${padL}" y1="${zeroY}" x2="${width - padR}" y2="${zeroY}" stroke="#E3E0D6" stroke-width="1"/>
      ${bars}
      ${xLabels}
      ${legend}
    </svg>`;
  el.innerHTML = svg;
}

// ==========================================================================
// Redesenha gráficos ao redimensionar janela (debounced)
// ==========================================================================
let resizeTimer;
window.addEventListener("resize", function () {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () {
    document.querySelectorAll(".chart-box[data-labels]").forEach(function (el) {
      renderDualChart(el.id);
    });
  }, 200);
});

// ==========================================================================
// Encerramento da App (botão ⏻ Encerrar no top-header)
// Envia POST para /api/shutdown para o Flask matar o processo frozen,
// tenta fechar a janela e, como fallback, redirecciona para /logout.
// ==========================================================================
function sairEncerrarApp() {
  if (!confirm('Deseja realmente encerrar o SGE?\n\nTodos os processos serão terminados.')) {
    return;
  }
  try {
    fetch('/api/shutdown', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).catch(function(){});
  } catch (e) {}

  setTimeout(function(){
    try { window.close(); } catch(e){}
    window.location.href = '/logout';
  }, 600);
}

// ==========================================================================
// Helpers de formatação (5 casas decimais, moeda, datas)
// ==========================================================================
function fmt5(v) {
  const n = Number(v);
  if (isNaN(n)) return '0.00000';
  return n.toFixed(5);
}
function fmtMoeda(v, simbolo) {
  const s = simbolo || 'MZN';
  const n = Number(v) || 0;
  return s + ' ' + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// ==========================================================================
// Balancetes: atalhos de período rápido (mensal corrente, trimestral, anual)
// ==========================================================================
function periodoRapido(tipo) {
  const hoje = new Date();
  let ini, fim;
  const y = hoje.getFullYear();
  const m = hoje.getMonth();
  if (tipo === 'mes') {
    ini = new Date(y, m, 1);
    fim = new Date(y, m + 1, 0);
  } else if (tipo === 'trimestre') {
    const t = Math.floor(m / 3);
    ini = new Date(y, t * 3, 1);
    fim = new Date(y, t * 3 + 3, 0);
  } else if (tipo === 'ano') {
    ini = new Date(y, 0, 1);
    fim = new Date(y, 11, 31);
  } else if (tipo === 'mes-ant') {
    ini = new Date(y, m - 1, 1);
    fim = new Date(y, m, 0);
  }
  if (ini && fim) {
    const pad = n => String(n).padStart(2, '0');
    const di = ini.getFullYear() + '-' + pad(ini.getMonth()+1) + '-' + pad(ini.getDate());
    const df = fim.getFullYear() + '-' + pad(fim.getMonth()+1) + '-' + pad(fim.getDate());
    const i = document.querySelector('input[name="data_ini"]');
    const f = document.querySelector('input[name="data_fim"]');
    if (i) i.value = di;
    if (f) f.value = df;
  }
}
