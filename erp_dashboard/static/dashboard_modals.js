/**
 * ==============================================================================
 * GESTIÓN DEL MODAL DE SEGURIDAD PARA CREDENCIALES KUCOIN
 * ==============================================================================
 */
/**
 * Función: openConfigModal
 * Abre el diálogo modal de configuración de claves de API de KuCoin y consulta el estado actual.
 */
window.openConfigModal = function() {
    const modal = document.getElementById('configModal'), msg = document.getElementById('modalStatusMsg'), help = document.getElementById('currentKeyHelp');
    if (msg) msg.style.display = 'none';
    if (modal) modal.style.display = 'flex';
    if (help) help.textContent = 'Consultando clave actual en el servidor...';
    fetch('/api/config/keys').then(r => r.json()).then(data => {
        if (help) help.textContent = 'Clave actual: ' + (data.api_key_masked || 'No configurada');
    }).catch(() => { if (help) help.textContent = 'Clave actual: No disponible'; });
};

/**
 * Función: closeConfigModal
 * Cierra el diálogo modal de configuración de API de KuCoin.
 */
window.closeConfigModal = function() {
    const modal = document.getElementById('configModal');
    if (modal) modal.style.display = 'none';
};

/**
 * Función: openGridBotModal
 * Abre el modal de configuración de estrategias y controles operativos del Grid Bot.
 */
window.openGridBotModal = function() {
    const modal = document.getElementById('gridBotModal');
    const msg = document.getElementById('strategyStatusMsg');
    if (msg) msg.style.display = 'none';
    if (modal) modal.style.display = 'flex';
    loadStrategyConfig();
};

/**
 * Función: closeGridBotModal
 * Cierra el modal del Grid Bot.
 */
window.closeGridBotModal = function() {
    const modal = document.getElementById('gridBotModal');
    if (modal) modal.style.display = 'none';
};

/**
 * Función: saveKucoinCredentials
 * Envía las nuevas claves a /api/config/keys con cifrado seguro y reinicia el bot.
 */
async function saveKucoinCredentials() {
    const keyInput = document.getElementById('cfgApiKey'), secInput = document.getElementById('cfgApiSecret'), passInput = document.getElementById('cfgApiPassphrase');
    const msg = document.getElementById('modalStatusMsg'), btnSave = document.getElementById('btnSaveConfig');
    const apiKey = keyInput ? keyInput.value.trim() : '', apiSecret = secInput ? secInput.value.trim() : '', apiPassphrase = passInput ? passInput.value.trim() : '';

    if (!apiKey || !apiSecret || !apiPassphrase) {
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '⚠️ Debes rellenar los 3 campos (Key, Secret y Passphrase).'; msg.style.display = 'block'; }
        return;
    }
    if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Guardando y Reiniciando...'; }

    try {
        const resp = await fetch('/api/config/keys', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, api_passphrase: apiPassphrase })
        });
        const res = await resp.json();
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Guardar y Reiniciar Bot'; }
        if (res.success) {
            if (msg) { msg.className = 'modal-status success'; msg.textContent = '✅ Credenciales actualizadas y Grid Bot reiniciado con éxito.'; msg.style.display = 'block'; }
            setTimeout(() => {
                window.closeConfigModal();
                if (keyInput) keyInput.value = ''; if (secInput) secInput.value = ''; if (passInput) passInput.value = '';
                refreshDashboard();
            }, 1600);
        } else if (msg) {
            msg.className = 'modal-status error'; msg.textContent = '❌ Error: ' + (res.error || 'No se pudo guardar la configuración'); msg.style.display = 'block';
        }
    } catch (e) {
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Guardar y Reiniciar Bot'; }
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '❌ Error de comunicación con el servidor.'; msg.style.display = 'block'; }
    }
}

