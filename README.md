# 🚀 Hermes Grid Bot & ERP Web — AI Trading Skill

Bot de Grid Trading Spot para KuCoin con **Motor de Aprendizaje por IA**, análisis diario de sentimiento (CoinMarketCap Fear & Greed), memoria relacional SQLite y panel de control web ERP en tiempo real.

---

## 🌟 Características Principales

- **Estrategia Grid 1:1 Estricta**: Cuadrícula de órdenes límite en KuCoin con asignación por lote íntegro (+1.35% garantizado sin dilución de capital).
- **Análisis Cuantitativo de Mercado**: Módulo `market_analyzer.py` para cálculo automático de rango geométrico óptimo, volatilidad (ATR) y RSI.
- **Motor de IA & Aprendizaje Continuo**:
  - Registro de lecciones y optimizaciones en base de datos SQLite relacional.
  - Análisis diario de sentimiento de mercado (4x al día) con lectura fiel del índice Fear & Greed de CoinMarketCap.
  - Modo **"Seguir Bot"**: Alterna con un solo clic entre seguir las recomendaciones de la IA o respetar tu configuración personalizada.
- **Dashboard ERP Web Completo**:
  - Gráfico en tiempo real de TradingView sincronizado.
  - Tabla dinámica de órdenes activas ordenada por proximidad de ejecución en tiempo real.
  - Botón de venta de emergencia a mercado (`Market Sell`) y cancelación segura de órdenes individuales.
  - Ajuste dinámico de parámetros (Capital, Spacing, Niveles, Presets, Stop-Loss).
- **Notificaciones Telegram**: Alertas en tiempo real de compras y ventas cerradas con desglose de beneficio neto y fees.

---

## 🔒 Ciberseguridad y Privacidad

- **Cero Credenciales en Código**: Todas las claves privadas se gestionan a través de variables de entorno locales (`.env`).
- **Aislamiento**: El repositorio cuenta con un `.gitignore` estricto que previene subir historiales de operaciones, bases de datos privadas, logs y claves API.

---

## 📚 Documentación y Manuales

- 📖 Consulta el **[Manual Completo de Instalación y Operación](./MANUAL_INSTALACION.md)** para una guía paso a paso detallada (Linux, Windows, API KuCoin y resolución de dudas).
- 🤖 Para agentes de Inteligencia Artificial (Hermes, Antigravity), consulta el archivo maestro **[SKILL.md](./SKILL.md)**.

---

## ⚡ Instalación Rápida

### 1. Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/hermes-grid-bot.git
cd hermes-grid-bot
```

### 2. Ejecutar el instalador
```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

### 3. Configurar credenciales
Edita el archivo `.env` recién creado con tus propias API Keys de KuCoin:
```bash
nano .env
```

### 4. Iniciar el bot y el Dashboard ERP
```bash
./scripts/start.sh
```

Abre tu navegador en:
👉 **`http://localhost:5000`**

Para detener los servicios:
```bash
./scripts/stop.sh
```

---

## 🤖 Uso como Skill para Agentes Hermes / Antigravity

Si utilizas un asistente de IA como Hermes o Antigravity:
1. Copia esta carpeta dentro del directorio de skills de tu agente (por ejemplo `.agents/skills/grid-bot/`).
2. Indícale a tu agente:
   > *"Hermes, instala el grid-bot, configúralo con mis credenciales de KuCoin y arranca el panel de control."*
3. El agente leerá `SKILL.md` y ejecutará todos los pasos de manera autónoma.

---

## 📜 Licencia
Distribuido bajo licencia MIT. Desarrollado con los más altos estándares de seguridad y código limpio.
