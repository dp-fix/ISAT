// ──────────────────────────────────────────────
// Tipe Data
// ──────────────────────────────────────────────
interface Termin {
  id: number;
  label: string;
  target_price: number;
  allocation: number;
  rationale: string;
  distance_pct: number | null;
  lots: number;
  shares: number;
  actual_cost: number;
  remaining_cash: number;
}

interface PhaseInfo {
  phase: string;
  phase_label: string;
  phase_color: string;
  description: string;
}

interface AccumulationInfo {
  signal: string;
  score: number;
  note: string;
}

interface StrategyData {
  symbol: string;
  company: string;
  total_portfolio: number;
  max_allocation: number;
  ultra_reserve: number;
  reserve_instrument: string;
  horizon: string;
  target_win_rate: string;
  method: string;
  target_conservative: number;
  target_consensus_min: number;
  target_consensus_max: number;
  dividend_per_share_conservative: number;
  dividend_per_share_optimistic: number;
  dividend_window: string;
  termins: Termin[];
}

interface IsatData {
  timestamp: string;
  timestamp_unix: number;
  market_status: string;
  symbol: string;
  company: string;
  current_price: number;
  prev_close: number;
  change: number;
  change_pct: number;
  indicators: {
    ma20: number | null;
    ma50: number | null;
    rsi14: number | null;
    vol_ma20: number | null;
    latest_volume: number;
    vol_ratio: number;
    prev_close: number;
    day_high: number;
    day_low: number;
    day_open: number;
  };
  phase: PhaseInfo;
  accumulation: AccumulationInfo;
  strategy: StrategyData;
  checklist_reminder: {
    point_1: string;
    point_2: string;
    point_3: string;
  };
}

// ──────────────────────────────────────────────
// State & LocalStorage
// ──────────────────────────────────────────────
const STORAGE_KEY = "isat_dashboard_state";

interface AppState {
  bought: Record<number, boolean>;   // termin id -> bought
  prices: Record<number, number>;    // termin id -> custom price
  checklist: [boolean, boolean, boolean];
}

function loadState(): AppState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    console.warn("Gagal load state:", e);
  }
  return {
    bought: {},
    prices: {},
    checklist: [false, false, false]
  };
}

function saveState(state: AppState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

let appState = loadState();
let isatData: IsatData | null = null;

// ──────────────────────────────────────────────
// Utility
// ──────────────────────────────────────────────
function formatRupiah(n: number): string {
  return "Rp" + n.toLocaleString("id-ID");
}

function formatNumber(n: number): string {
  return n.toLocaleString("id-ID");
}

function formatLot(lots: number): string {
  return `${formatNumber(lots)} lot (${formatNumber(lots * 100)} lembar)`;
}

function timeAgo(isoString: string): string {
  const then = new Date(isoString).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return `${diffSec} detik lalu`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} menit lalu`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} jam lalu`;
  return `${Math.floor(diffSec / 86400)} hari lalu`;
}

// ──────────────────────────────────────────────
// Fetch Data
// ──────────────────────────────────────────────
async function fetchData(): Promise<IsatData> {
  // Path relatif agar jalan di GitHub Pages
  const res = await fetch("./data/isat.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Gagal fetch data: ${res.status}`);
  return res.json();
}

// ──────────────────────────────────────────────
// Render: Header & Price
// ──────────────────────────────────────────────
function renderHeader(data: IsatData): void {
  const el = document.getElementById("header-price");
  if (!el) return;

  const changeClass = data.change >= 0 ? "positive" : "negative";
  const changeIcon = data.change >= 0 ? "▲" : "▼";
  const marketBadge = data.market_status === "OPEN"
    ? `<span class="badge badge-open">● PASAR BUKA</span>`
    : `<span class="badge badge-closed">● PASAR TUTUP</span>`;

  el.innerHTML = `
    <div class="header-top">
      <div>
        <h1 class="stock-symbol">${data.symbol}</h1>
        <p class="stock-company">${data.company}</p>
      </div>
      <div class="header-right">
        ${marketBadge}
        <span class="timestamp">Update: ${timeAgo(data.timestamp)}</span>
      </div>
    </div>
    <div class="price-row">
      <span class="current-price">${formatRupiah(data.current_price)}</span>
      <span class="price-change ${changeClass}">
        ${changeIcon} ${formatRupiah(Math.abs(data.change))} (${data.change_pct >= 0 ? "+" : ""}${data.change_pct.toFixed(2)}%)
      </span>
    </div>
  `;
}

// ──────────────────────────────────────────────
// Render: Phase Banner
// ──────────────────────────────────────────────
function renderPhaseBanner(data: IsatData): void {
  const el = document.getElementById("phase-banner");
  if (!el) return;

  el.style.borderLeftColor = data.phase.phase_color;
  el.innerHTML = `
    <div class="phase-label" style="color: ${data.phase.phase_color}">
      ${data.phase.phase_label}
    </div>
    <p class="phase-desc">${data.phase.description}</p>
  `;
}

// ──────────────────────────────────────────────
// Render: Indikator Teknikal
// ──────────────────────────────────────────────
function renderIndicators(data: IsatData): void {
  const el = document.getElementById("indicators-grid");
  if (!el) return;

  const ind = data.indicators;
  const rsiColor = ind.rsi14 !== null
    ? (ind.rsi14 < 30 ? "#ff4757" : ind.rsi14 > 70 ? "#22c55e" : "#eab308")
    : "#888";

  const volStatus = ind.vol_ratio > 1.3
    ? `<span style="color:#ff4757">Tinggi (${ind.vol_ratio}x)</span>`
    : ind.vol_ratio < 0.7
    ? `<span style="color:#00d4aa">Menyusut (${ind.vol_ratio}x)</span>`
    : `<span style="color:#eab308">Normal (${ind.vol_ratio}x)</span>`;

  el.innerHTML = `
    <div class="indicator-card">
      <div class="indicator-label">MA20</div>
      <div class="indicator-value">${ind.ma20 ? formatRupiah(ind.ma20) : "-"}</div>
      <div class="indicator-sub">${ind.ma20 && data.current_price > ind.ma20 ? "Di atas MA20 ✓" : "Di bawah MA20 ✗"}</div>
    </div>
    <div class="indicator-card">
      <div class="indicator-label">MA50</div>
      <div class="indicator-value">${ind.ma50 ? formatRupiah(ind.ma50) : "-"}</div>
      <div class="indicator-sub">${ind.ma50 && data.current_price > ind.ma50 ? "Di atas MA50 ✓" : "Di bawah MA50 ✗"}</div>
    </div>
    <div class="indicator-card">
      <div class="indicator-label">RSI (14)</div>
      <div class="indicator-value" style="color:${rsiColor}">${ind.rsi14 !== null ? ind.rsi14.toFixed(1) : "-"}</div>
      <div class="indicator-sub">${ind.rsi14 !== null ? (ind.rsi14 < 30 ? "Oversold" : ind.rsi14 > 70 ? "Overbought" : "Netral") : "-"}</div>
    </div>
    <div class="indicator-card">
      <div class="indicator-label">Vol vs MA20</div>
      <div class="indicator-value">${volStatus}</div>
      <div class="indicator-sub">Vol hari ini: ${formatNumber(ind.latest_volume)} lot</div>
    </div>
  `;
}

// ──────────────────────────────────────────────
// Render: Akumulasi Bandar
// ──────────────────────────────────────────────
function renderAccumulation(data: IsatData): void {
  const el = document.getElementById("accumulation-panel");
  if (!el) return;

  const acc = data.accumulation;
  const signalColor = acc.signal === "ACCUMULATION_DETECTED" ? "#00d4aa"
    : acc.signal === "DISTRIBUTION" ? "#ff4757"
    : acc.signal === "SELLING_DRYING_UP" ? "#eab308"
    : "#64748b";

  el.innerHTML = `
    <h3>🔍 Deteksi Akumulasi Bandar</h3>
    <div class="acc-signal" style="color:${signalColor}">
      <strong>${acc.signal.replace(/_/g, " ")}</strong>
      <span class="acc-score">Skor: ${acc.score}/100</span>
    </div>
    <div class="acc-bar">
      <div class="acc-bar-fill" style="width:${acc.score}%; background:${signalColor}"></div>
    </div>
    <p class="acc-note">${acc.note}</p>
  `;
}

// ──────────────────────────────────────────────
// Render: Kalkulator Piramida
// ──────────────────────────────────────────────
function renderCalculator(data: IsatData): void {
  const el = document.getElementById("calculator");
  if (!el) return;

  const strat = data.strategy;

  let terminsHtml = strat.termins.map(t => {
    const currentPrice = appState.prices[t.id] ?? t.target_price;
    const isBought = appState.bought[t.id] === true;
    const lots = Math.floor(t.allocation / (currentPrice * 100));
    const actualCost = lots * currentPrice * 100;

    return `
      <div class="termin-card ${isBought ? "bought" : ""}" data-termin="${t.id}">
        <div class="termin-header">
          <label class="termin-check">
            <input type="checkbox" class="bought-checkbox" data-id="${t.id}" ${isBought ? "checked" : ""}>
            <span class="termin-label">${t.label}</span>
          </label>
          <span class="termin-status">${isBought ? "✅ TERBELI" : "⏳ PENDING"}</span>
        </div>
        <p class="termin-rationale">${t.rationale}</p>
        <div class="termin-inputs">
          <div class="input-group">
            <label>Harga Target</label>
            <input type="number" class="price-input" data-id="${t.id}"
                   value="${currentPrice}" step="5" min="50">
          </div>
          <div class="input-group">
            <label>Alokasi Dana</label>
            <input type="text" value="${formatRupiah(t.allocation)}" disabled class="disabled-input">
          </div>
        </div>
        <div class="termin-result">
          <div><span>Est. Lot:</span> <strong>${formatLot(lots)}</strong></div>
          <div><span>Est. Biaya:</span> <strong>${formatRupiah(actualCost)}</strong></div>
          <div><span>Sisa Cash:</span> <strong>${formatRupiah(t.allocation - actualCost)}</strong></div>
        </div>
      </div>
    `;
  }).join("");

  el.innerHTML = `
    <div class="calc-strategy-info">
      <div class="strat-row"><span>Metode:</span> <strong>${strat.method}</strong></div>
      <div class="strat-row"><span>Horizon:</span> <strong>${strat.horizon}</strong></div>
      <div class="strat-row"><span>Target Win Rate:</span> <strong>${strat.target_win_rate}</strong></div>
      <div class="strat-row"><span>Total Portofolio:</span> <strong>${formatRupiah(strat.total_portfolio)}</strong></div>
      <div class="strat-row"><span>Maks Alokasi ISAT:</span> <strong>${formatRupiah(strat.max_allocation)}</strong></div>
      <div class="strat-row highlight"><span>Ultra Reserve (RDPU):</span> <strong>${formatRupiah(strat.ultra_reserve)}</strong></div>
    </div>
    <div class="termins-list">${terminsHtml}</div>
    <div id="calc-summary"></div>
  `;

  updateSummary(data);
  bindCalculatorEvents(data);
}

function updateSummary(data: IsatData): void {
  const summaryEl = document.getElementById("calc-summary");
  if (!summaryEl) return;

  const strat = data.strategy;
  let totalShares = 0;
  let totalCost = 0;
  let totalAllocationUsed = 0;
  let terminsBought = 0;

  strat.termins.forEach(t => {
    if (appState.bought[t.id]) {
      const price = appState.prices[t.id] ?? t.target_price;
      const lots = Math.floor(t.allocation / (price * 100));
      const cost = lots * price * 100;
      totalShares += lots * 100;
      totalCost += cost;
      totalAllocationUsed += t.allocation;
      terminsBought++;
    }
  });

  const avgPrice = totalShares > 0 ? totalCost / totalShares : 0;
  const remainingReserve = strat.ultra_reserve; // tidak tersentuh
  const remainingAllocation = strat.max_allocation - totalAllocationUsed;

  // Estimasi dividen
  const divConservative = totalShares * strat.dividend_per_share_conservative;
  const divOptimistic = totalShares * strat.dividend_per_share_optimistic;

  // Potensi gain di harga konservatif
  const gainAtConservative = totalShares > 0
    ? (strat.target_conservative - avgPrice) / avgPrice * 100
    : 0;
  const gainRupiah = totalShares > 0
    ? totalShares * (strat.target_conservative - avgPrice)
    : 0;

  const allocPct = (totalAllocationUsed / strat.max_allocation * 100).toFixed(1);

  summaryEl.innerHTML = `
    <div class="summary-card">
      <h3>📊 Ringkasan Eksekusi</h3>
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">Termin Terbeli</div>
          <div class="summary-value">${terminsBought} / ${strat.termins.length}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Total Lembar</div>
          <div class="summary-value">${formatNumber(totalShares)} lembar</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Harga Rata-rata</div>
          <div class="summary-value">${avgPrice > 0 ? formatRupiah(Math.round(avgPrice)) : "-"}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Total Modal Terpakai</div>
          <div class="summary-value">${formatRupiah(totalCost)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Sisa Alokasi ISAT</div>
          <div class="summary-value">${formatRupiah(remainingAllocation)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Ultra Reserve (RDPU)</div>
          <div class="summary-value safe">${formatRupiah(remainingReserve)}</div>
        </div>
      </div>

      <div class="allocation-bar">
        <div class="allocation-bar-label">Alokasi terpakai: ${allocPct}%</div>
        <div class="allocation-bar-track">
          <div class="allocation-bar-fill" style="width:${allocPct}%"></div>
        </div>
      </div>

      ${totalShares > 0 ? `
        <div class="projection-section">
          <h4>🎯 Proyeksi di Harga Target ${formatRupiah(strat.target_conservative)}</h4>
          <div class="projection-grid">
            <div>
              <div class="proj-label">Potensi Gain</div>
              <div class="proj-value positive">+${gainAtConservative.toFixed(2)}%</div>
            </div>
            <div>
              <div class="proj-label">Gain (Rupiah)</div>
              <div class="proj-value positive">+${formatRupiah(Math.round(gainRupiah))}</div>
            </div>
            <div>
              <div class="proj-label">Nilai Portofolio</div>
              <div class="proj-value">${formatRupiah(Math.round(totalShares * strat.target_conservative))}</div>
            </div>
          </div>

          <h4>💰 Estimasi Dividen ${strat.dividend_window}</h4>
          <div class="dividend-grid">
            <div class="div-card conservative">
              <div class="div-label">Konservatif (${strat.dividend_per_share_conservative}/lbr)</div>
              <div class="div-value">${formatRupiah(divConservative)}</div>
              <div class="div-yield">Yield: ${(divConservative / totalCost * 100).toFixed(1)}%</div>
            </div>
            <div class="div-card optimistic">
              <div class="div-label">Optimistis (${strat.dividend_per_share_optimistic}/lbr)</div>
              <div class="div-value">${formatRupiah(divOptimistic)}</div>
              <div class="div-yield">Yield: ${(divOptimistic / totalCost * 100).toFixed(1)}%</div>
            </div>
          </div>
        </div>
      ` : `
        <div class="empty-projection">
          <p>☑️ Centang minimal 1 termin yang sudah dibeli untuk melihat proyeksi.</p>
        </div>
      `}
    </div>
  `;
}

function bindCalculatorEvents(data: IsatData): void {
  // Checkbox "Bought"
  document.querySelectorAll(".bought-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const target = e.target as HTMLInputElement;
      const id = parseInt(target.dataset.id || "0");
      appState.bought[id] = target.checked;
      saveState(appState);
      renderCalculator(data);
    });
  });

  // Input harga custom
  document.querySelectorAll(".price-input").forEach(input => {
    input.addEventListener("change", (e) => {
      const target = e.target as HTMLInputElement;
      const id = parseInt(target.dataset.id || "0");
      const newPrice = parseFloat(target.value);
      if (newPrice > 0) {
        appState.prices[id] = newPrice;
        saveState(appState);
        renderCalculator(data);
      }
    });
  });
}

// ──────────────────────────────────────────────
// Render: Checklist 3 Poin
// ──────────────────────────────────────────────
function renderChecklist(data: IsatData): void {
  const el = document.getElementById("checklist");
  if (!el) return;

  const reminders = data.checklist_reminder;
  const labels = [reminders.point_1, reminders.point_2, reminders.point_3];

  let itemsHtml = labels.map((label, i) => `
    <label class="checklist-item">
      <input type="checkbox" class="checklist-checkbox" data-index="${i}"
             ${appState.checklist[i] ? "checked" : ""}>
      <span class="checklist-text">${label}</span>
    </label>
  `).join("");

  const allChecked = appState.checklist.every(c => c);

  el.innerHTML = `
    <h3>✅ Checklist Sebelum Instant Redeem</h3>
    <div class="checklist-items">${itemsHtml}</div>
    <div id="checklist-banner" class="checklist-banner ${allChecked ? "green" : "red"}">
      ${allChecked
        ? "🟢 SINYAL HIJAU: Siap Instant Redeem dari RDPU"
        : "🔴 TAHAN DANA DI RDPU: Belum semua kriteria terpenuhi"}
    </div>
  `;

  // Bind events
  document.querySelectorAll(".checklist-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const target = e.target as HTMLInputElement;
      const idx = parseInt(target.dataset.index || "0");
      appState.checklist[idx] = target.checked;
      saveState(appState);
      updateChecklistBanner();
    });
  });
}

function updateChecklistBanner(): void {
  const banner = document.getElementById("checklist-banner");
  if (!banner) return;
  const allChecked = appState.checklist.every(c => c);
  banner.className = `checklist-banner ${allChecked ? "green" : "red"}`;
  banner.textContent = allChecked
    ? "🟢 SINYAL HIJAU: Siap Instant Redeem dari RDPU"
    : "🔴 TAHAN DANA DI RDPU: Belum semua kriteria terpenuhi";
}

// ──────────────────────────────────────────────
// Render: Sentimen Panel
// ──────────────────────────────────────────────
function renderSentiment(): void {
  const el = document.getElementById("sentiment-panel");
  if (!el) return;

  el.innerHTML = `
    <h3>📰 Sentimen & Katalis</h3>
    <div class="sentiment-section negative">
      <h4>⚠️ Negatif (Jangka Pendek)</h4>
      <ul>
        <li>Kekhawatiran pengetatan pasokan chip AI Nvidia di Asia Tenggara → potensi tunda monetisasi AI Cloud.</li>
        <li>Belanja modal (CapEx) 5G masih tinggi menekan arus kas bebas.</li>
        <li>Breakdown dari konsolidasi 1.340–1.430, terkunci ARB di 1.310.</li>
      </ul>
    </div>
    <div class="sentiment-section positive">
      <h4>✅ Positif (Jangka Menengah 3–12 Bulan)</h4>
      <ul>
        <li>Pertumbuhan laba bersih 9M-2026: <strong>+37,2%</strong>.</li>
        <li>Potensi <em>window dressing</em> akhir tahun (Desember).</li>
        <li>Ekspektasi dividen 2027: yield 9,8%–13,4% dari harga bawah.</li>
        <li>Net Foreign Sell mingguan mengecil ke -Rp2,86 M (distribusi asing mereda).</li>
        <li>Volume jual harian (~900rb lot) masih di bawah MA20 volume (2,85jt lot) → selling pressure berkurang.</li>
      </ul>
    </div>
  `;
}

// ──────────────────────────────────────────────
// Render: TradingView Widget
// ──────────────────────────────────────────────
function initTradingView(): void {
  const container = document.getElementById("tradingview_chart");
  if (!container || typeof (window as any).TradingView === "undefined") return;

  new (window as any).TradingView.widget({
    "autosize": true,
    "symbol": "IDX:ISAT",
    "interval": "D",
    "timezone": "Asia/Jakarta",
    "theme": "dark",
    "style": "1",
    "locale": "id",
    "toolbar_bg": "#0f0f1a",
    "enable_publishing": false,
    "hide_top_toolbar": false,
    "withdateranges": true,
    "container_id": "tradingview_chart"
  });
}

// ──────────────────────────────────────────────
// Main Init
// ──────────────────────────────────────────────
async function init(): Promise<void> {
  try {
    isatData = await fetchData();

    // Inisialisasi harga default jika belum ada di state
    isatData.strategy.termins.forEach(t => {
      if (appState.prices[t.id] === undefined) {
        appState.prices[t.id] = t.target_price;
      }
    });

    renderHeader(isatData);
    renderPhaseBanner(isatData);
    renderIndicators(isatData);
    renderAccumulation(isatData);
    renderCalculator(isatData);
    renderChecklist(isatData);
    renderSentiment();

    // TradingView (load script dulu)
    const tvScript = document.createElement("script");
    tvScript.src = "https://s3.tradingview.com/tv.js";
    tvScript.onload = initTradingView;
    document.head.appendChild(tvScript);

  } catch (err) {
    console.error("Init error:", err);
    const el = document.getElementById("header-price");
    if (el) {
      el.innerHTML = `
        <div class="error-message">
          <h2>⚠️ Gagal Memuat Data</h2>
          <p>${(err as Error).message}</p>
          <p>Pastikan <code>data/isat.json</code> sudah di-generate oleh GitHub Actions.</p>
          <button onclick="location.reload()">🔄 Coba Lagi</button>
        </div>
      `;
    }
  }
}

document.addEventListener("DOMContentLoaded", init);
