---
name: hermes-grid-bot
description: >-
  Skill integral para desplegar, operar, monitorear y calibrar el Grid Bot de Trading
  con Motor de Inteligencia Artificial (Fear & Greed, SQLite Memory y Panel ERP Web).
  Proporciona comandos y procedimientos paso a paso para agentes Hermes y humanos.
---

# 🤖 Hermes Grid Bot — Skill de Trading Algorítmico & IA

Esta Skill dota al agente de IA (Hermes / Antigravity) de capacidades para gestionar
de forma autónoma y segura una estrategia de Grid Trading Spot en KuCoin, integrando
análisis de sentimiento macro, memoria relacional SQLite y panel de control ERP.

---

## 🎯 Capacidades de la Skill

1. **Instalación y Despliegue**: Verifica requisitos del sistema, crea entornos aislados (`venv`) e instala dependencias (`ccxt`, `flask`, etc.).
2. **Gestión Segura de Credenciales**: Solicita o verifica las claves de KuCoin en `.env` manteniendo siempre máxima confidencialidad.
3. **Control Operativo del Bot**: Arranca, pausa, reanuda o rebalancea la cuadrícula de órdenes geométricas.
4. **Análisis de IA & Sentimiento**: Consulta el informe matutino de mercado y el índice Fear & Greed de CoinMarketCap, recomendando presets (`conservador`, `equilibrado`, `scalping`) y calibración de spacing.
5. **Panel ERP Web**: Monitorea el estado en vivo a través del servidor web integrado en `http://localhost:5000`.

---

## 📋 Flujo de Trabajo para el Agente (Runbook)

### Paso 1: Instalación inicial
Cuando el usuario solicite instalar o preparar el bot:
```bash
./scripts/install.sh
```
El script creará el entorno virtual y la plantilla `.env`.

### Paso 2: Configuración de Credenciales
Solicita al usuario sus credenciales de KuCoin (API Key, Secret y Passphrase) y guárdalas en `.env`:
```env
KUCOIN_API_KEY=su_api_key
KUCOIN_API_SECRET=su_secret
KUCOIN_API_PASSPHRASE=su_passphrase
SYMBOL=KAS/USDT
CAPITAL=16.00
```
> [!CAUTION]
> Asegúrate de que el archivo `.env` tenga permisos restringidos (`chmod 600 .env`) y nunca lo reveles ni lo incluyas en commits.

### Paso 3: Puesta en marcha
Para arrancar tanto el motor del Grid Bot como el Dashboard ERP:
```bash
./scripts/start.sh
```
Para detener los servicios:
```bash
./scripts/stop.sh
```

### Paso 4: Monitoreo y Diagnóstico con IA
Para consultar el estado operativo, órdenes activas o pedirle a la IA que calibre el bot:
- **Analizar sentimiento y Fear & Greed**:
  ```bash
  python3 core/market_sentiment_analyzer.py
  ```
- **Verificar base de datos de aprendizaje**:
  ```bash
  python3 -c "import sys; sys.path.append('core'); import ai_memory_db; print(ai_memory_db.get_learning_stats())"
  ```
- **Acceso Web**: Dirige al usuario a `http://localhost:5000` para interactuar con la interfaz visual y el botón **Seguir Bot**.
