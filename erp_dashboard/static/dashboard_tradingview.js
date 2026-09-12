// Módulo dedicado para integración y widget oficial de TradingView
const SYMBOL_TO_COIN = {
    'KAS/USDT': 'kaspa', 'BTC/USDT': 'bitcoin', 'ETH/USDT': 'ethereum', 'SOL/USDT': 'solana',
    'XRP/USDT': 'ripple', 'ADA/USDT': 'cardano', 'DOGE/USDT': 'dogecoin', 'DOT/USDT': 'polkadot',
    'LTC/USDT': 'litecoin', 'LINK/USDT': 'chainlink'
};

/**
 * Función: onStrategySymbolChange
 * Sincroniza el par seleccionado en el panel con el gráfico TradingView y recalcula límites sugeridos.
 */
async function onStrategySymbolChange() {
    const sel = document.getElementById('stratSymbol');
    if (!sel) return;
    const sym = sel.value;
    const coinId = SYMBOL_TO_COIN[sym] || 'kaspa';

    currentCoin = coinId;
    const coinSelect = document.getElementById('coinSelect');
    if (coinSelect) coinSelect.value = coinId;

    initTradingViewWidget(coinId);
    await fetchLivePrice();

    const p = currentLivePrice || 1.0;
    const decimals = (p < 1.0) ? 5 : ((p > 50) ? 2 : 4);
    
    const minInput = document.getElementById('stratGridMin');
    const maxInput = document.getElementById('stratGridMax');
    if (minInput) minInput.value = (p * 0.93).toFixed(decimals);
    if (maxInput) maxInput.value = (p * 1.07).toFixed(decimals);
}

// Script Principal Dashboard ERP Grid Bot - Gestión TradingView, órdenes y estrategias KuCoin

// Estado global de la interfaz
let currentCoin = 'kaspa';
let currentTradingViewWidget = null;
let currentTradeTab = 'all';
let currentTradePage = 1;
const TRADE_PAGE_SIZE = 10;
let cachedOpenOrders = [];
let cachedRawTrades = [];
let currentBotRunning = true;
let currentLivePrice = 0.0356;
let currentStopLossMode = 'hold';
let currentGridSpacing = 1.35;

// Mapeo de monedas a símbolos oficiales de TradingView
const TRADINGVIEW_SYMBOLS = {
    'kaspa': 'MEXC:KASUSDT', 'bitcoin': 'BINANCE:BTCUSDT', 'ethereum': 'BINANCE:ETHUSDT', 'solana': 'BINANCE:SOLUSDT',
    'ripple': 'BINANCE:XRPUSDT', 'cardano': 'BINANCE:ADAUSDT', 'dogecoin': 'BINANCE:DOGEUSDT', 'polkadot': 'BINANCE:DOTUSDT',
    'litecoin': 'BINANCE:LTCUSDT', 'chainlink': 'BINANCE:LINKUSDT'
};

/**
 * Función: formatCurrency
 * Formatea valores numéricos con decimales apropiados según la magnitud del precio.
 */
function formatCurrency(val, minDecimals = 4) {
    if (val === undefined || val === null || isNaN(val)) return '—';
    const num = parseFloat(val);
    if (num >= 100) return '$' + num.toFixed(2);
    if (num >= 1) return '$' + num.toFixed(4);
    return '$' + num.toFixed(minDecimals);
}

/**
 * Función: initTradingViewWidget
 * Inicializa y renderiza el Widget Oficial Avanzado de TradingView.
 * Proporciona escala automática, herramientas de dibujo, temporalidades y velas reales.
 */
function initTradingViewWidget(coinId) {
    const symbol = TRADINGVIEW_SYMBOLS[coinId] || 'BINANCE:BTCUSDT';
    const container = document.getElementById('tradingview_widget_box');
    if (!container) return;

    container.innerHTML = '';
    const widgetDiv = document.createElement('div');
    widgetDiv.id = 'tv_chart_' + Math.random().toString(36).substring(7);
    widgetDiv.style.height = '100%';
    widgetDiv.style.width = '100%';
    container.appendChild(widgetDiv);

    try {
        currentTradingViewWidget = new TradingView.widget({
            "autosize": true, "symbol": symbol, "interval": "60", "timezone": "Europe/Madrid",
            "theme": "dark", "style": "1", "locale": "es", "toolbar_bg": "#161b22",
            "enable_publishing": false, "allow_symbol_change": true, "save_image": false,
            "container_id": widgetDiv.id, "hide_side_toolbar": false,
            "studies": ["MASimple@tv-basicstudies"]
        });

        const titleEl = document.getElementById('chartSymbolTitle');
        if (titleEl) {
            titleEl.textContent = `Gráfico en Vivo: ${symbol}`;
        }
    } catch (err) {
        console.error('Error al inicializar TradingView Widget:', err);
    }
}

