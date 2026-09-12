# 📖 Manual Completo de Instalación, Configuración y Operación
## 🤖 Hermes Grid Bot & Dashboard ERP Web (Open Source - MIT)

Bienvenido a la guía oficial de instalación y puesta en marcha del **Hermes Grid Bot**. Este documento está diseñado para guiar tanto a usuarios principiantes como a administradores avanzados o agentes de Inteligencia Artificial (Hermes, Antigravity, etc.) paso a paso.

---

## 📑 Tabla de Contenidos
1. [Requisitos Previos del Sistema](#1-requisitos-previos-del-sistema)
2. [Obtención de Credenciales de KuCoin](#2-obtención-de-credenciales-de-kucoin)
3. [Instalación en Linux / VPS (Ubuntu, Debian, etc.)](#3-instalación-en-linux--vps-ubuntu-debian-etc)
4. [Instalación en Windows](#4-instalación-en-windows)
5. [Configuración del Entorno (.env)](#5-configuración-del-entorno-env)
6. [Puesta en Marcha y Uso Diario](#6-puesta-en-marcha-y-uso-diario)
7. [Funcionamiento del Motor de IA & Modo 'Seguir Bot'](#7-funcionamiento-del-motor-de-ia--modo-seguir-bot)
8. [Uso como Skill para el Agente Hermes](#8-uso-como-skill-para-el-agente-hermes)
9. [Resolución de Problemas Frecuentes (FAQ)](#9-resolución-de-problemas-frecuentes-faq)

---

## 1. Requisitos Previos del Sistema

- **Sistema Operativo**: Linux (Ubuntu 20.04+, Debian 11+, Raspberry Pi OS) o Windows 10/11.
- **Python**: Versión 3.9 o superior (`python3 --version`).
- **Git**: Instalado para clonar y actualizar el repositorio (`git --version`).
- **Conexión a Internet**: Acceso continuo a la API pública de KuCoin y CoinGecko.

---

## 2. Obtención de Credenciales de KuCoin

Para que el bot pueda operar, necesitas crear una clave API de Spot Trading en tu cuenta de KuCoin:

1. Inicia sesión en [KuCoin](https://www.kucoin.com).
2. Ve a tu perfil en la esquina superior derecha y selecciona **API Management** (Gestión de API).
3. Haz clic en **Create API** (Crear API) > Selecciona **Spot Trading**.
4. Define un nombre descriptivo (por ejemplo: `HermesGridBot`).
5. **Crea una Passphrase segura**: Esta es una contraseña adicional que tú eliges y deberás recordar.
6. **Permisos**:
   - ✅ **General** (Lectura de saldo y mercado).
   - ✅ **Trade** (Permiso para crear y cancelar órdenes de compra y venta).
   - ❌ **Transfer** (Transferencias): **NO activar**.
   - ❌ **Withdrawal** (Retiros): **NUNCA activar** (por seguridad máxima, el bot jamás debe tener permisos de retiro).
7. Confirma la creación mediante tus métodos de seguridad (2FA / email) y copia de inmediato tu **API Key**, **API Secret** y tu **Passphrase**.

---

## 3. Instalación en Linux / VPS (Ubuntu, Debian, etc.)

### Paso 3.1: Clonar el repositorio
```bash
git clone https://github.com/TU_USUARIO/hermes-grid-bot.git
cd hermes-grid-bot
```

### Paso 3.2: Ejecutar el instalador automático
El instalador creará el entorno virtual (`venv`), instalará las librerías necesarias (`ccxt`, `flask`, `requests`, etc.) y preparará el archivo `.env`:
```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

### Paso 3.3: Configurar las claves
Edita el archivo de configuración con tu editor favorito:
```bash
nano .env
```
Rellena tus credenciales (consulta la [Sección 5](#5-configuración-del-entorno-env)). Para guardar en nano: `Ctrl + O` > Enter > `Ctrl + X`.

---

## 4. Instalación en Windows

1. Abre **PowerShell** en la carpeta donde descargaste o clonaste el proyecto.
2. Crea el entorno virtual de Python:
   ```powershell
   python -m venv venv
   ```
3. Activa el entorno virtual:
   ```powershell
   .env\Scripts\Activate.ps1
   ```
4. Instala las dependencias:
   ```powershell
   pip install -r requirements.txt
   ```
5. Copia la plantilla de configuración:
   ```powershell
   Copy-Item .env.example .env
   ```
6. Abre `.env` con el Bloc de notas y rellena tus claves de KuCoin.

---

## 5. Configuración del Entorno (.env)

El archivo `.env` contiene todos los parámetros necesarios. Ejemplo comentado:

```env
# =======================================================
# CREDENCIALES DE KUCOIN (OBLIGATORIO)
# =======================================================
KUCOIN_API_KEY=tu_api_key_aqui
KUCOIN_API_SECRET=tu_api_secret_aqui
KUCOIN_API_PASSPHRASE=tu_passphrase_aqui

# =======================================================
# PAR DE TRADING Y CAPITAL (OBLIGATORIO)
# =======================================================
SYMBOL=KAS/USDT
CAPITAL=16.00

# =======================================================
# ESTRATEGIA INICIAL DE LA CUADRÍCULA
# =======================================================
# Spacing porcentual mínimo entre compras y ventas (ej. 1.35%)
GRID_SPACING_PCT=1.35
# Número de órdenes simultáneas repartidas en la cuadrícula
NUM_GRID_LEVELS=8

# =======================================================
# NOTIFICACIONES EN TELEGRAM (OPCIONAL)
# =======================================================
# Puedes dejar estos campos vacíos si no deseas alertas por Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# =======================================================
# PUERTO DEL DASHBOARD WEB ERP
# =======================================================
PORT=5000
```

---

## 6. Puesta en Marcha y Uso Diario

### Iniciar el Bot y el Dashboard
En Linux:
```bash
./scripts/start.sh
```
En Windows (con el venv activado):
```powershell
# En una terminal: Iniciar el bot
python core/grid_bot.py

# En otra terminal: Iniciar el Dashboard ERP
python erp_dashboard/app.py
```

### Acceso a la Interfaz Gráfica
Abre cualquier navegador web y entra en:
👉 **`http://localhost:5000`** *(o la IP de tu VPS, ej. `http://tu_ip_vps:5000`)*.

Desde el panel web podrás:
- Ver el gráfico TradingView del par en tiempo real.
- Consultar las órdenes de venta activas con su **precio de compra origen**, **margen porcentual** y **ganancia neta estimada**.
- Ajustar el Spacing, Niveles, Capital y Presets (`Conservador`, `Equilibrado`, `Scalping`).
- Ejecutar ventas de emergencia a mercado (`Market Sell`) si deseas liquidar una posición de inmediato.
- Pausar o reanudar el bot con un solo clic.

### Detener los Servicios
En Linux:
```bash
./scripts/stop.sh
```

---

## 7. Funcionamiento del Motor de IA & Modo 'Seguir Bot'

En la cabecera del panel de IA verás el botón **`Seguir Bot`**:

- **`Seguir Bot: OFF` (Modo Manual)**:
  El bot respeta estrictamente los parámetros que tú configures manualmente en el panel de control.
- **`Seguir Bot: ON` (Modo Piloto Automático con IA)**:
  El bot lee el análisis matutino de sentimiento de mercado (índice Fear & Greed de CoinMarketCap y macroeconomía) y aplica de forma automática el preset y el spacing óptimos recomendados para el régimen actual del mercado. Si en cualquier momento desactivas el botón, restaurará automáticamente tus valores personalizados previos.

Para ejecutar manualmente el análisis matutino de sentimiento:
```bash
python3 core/market_sentiment_analyzer.py
```

---

## 8. Uso como Skill para el Agente Hermes

Este repositorio incluye un archivo [`SKILL.md`](./SKILL.md) nativo compatible con **Hermes**, **Antigravity** o cualquier agente basado en el estándar de skills:

1. Copia toda esta carpeta en el directorio de skills de tu agente (ej. `.agents/skills/grid-bot/`).
2. Interactúa en lenguaje natural con tu agente:
   - *"Hermes, instala el grid bot y verifica que el entorno esté listo."*
   - *"Hermes, arranca el bot y el panel web."*
   - *"Hermes, ¿cuál es la recomendación de la IA hoy según el Fear & Greed?"*
3. El agente seguirá los procedimientos definidos en `SKILL.md` de forma autónoma.

---

## 9. Resolución de Problemas Frecuentes (FAQ)

### P: Las órdenes dan error "Order amount too small"
**R**: KuCoin exige un mínimo de **1 USDT** por cada orden individual. Asegúrate de que el cociente `CAPITAL / NUM_LEVELS` sea siempre mayor o igual a **1.5 USDT** para cubrir fluctuaciones (por ejemplo, con 16 USDT usa 8 niveles = 2 USDT por orden).

### P: ¿Mis claves API están seguras?
**R**: Sí. Las claves se leen únicamente a nivel de memoria desde el archivo local `.env`. El archivo `.gitignore` impide que `.env` o cualquier archivo con transacciones se suba jamás al repositorio.

### P: ¿Puedo usar el bot con otra criptomoneda?
**R**: Sí. Puedes cambiar `SYMBOL=BTC/USDT` o `ETH/USDT` en tu `.env` o directamente desde el formulario de estrategia en el Dashboard web.

---

## 📜 Licencia Open Source
Este software se distribuye bajo la licencia **MIT**. Puedes usarlo, estudiarlo, modificarlo, adaptarlo e integrarlo libremente tanto para proyectos personales como comerciales.
