# 📖 User Guide & Manual — Tapo C225 AI Monitor

<p align="center">
  <a href="#-english"><b>🇬🇧 English</b></a> • 
  <a href="#-español"><b>🇪🇸 Español</b></a>
</p>

---

# 🇬🇧 English

## 1. Setting up your Tapo Camera Account
1. Open the **TP-Link Tapo App** on your smartphone ([Google Play](https://play.google.com/store/apps/details?id=com.tplink.iot) / [App Store](https://apps.apple.com/app/tp-link-tapo/id1472718009)) connected to your home Wi-Fi.
2. Go to camera **Settings ⚙️** -> **Advanced Settings** -> **Camera Account**. *(See [Official TP-Link FAQ 2680](https://www.tp-link.com/support/faq/2680/))*.
3. Create a local username and password. These credentials will be used for your RTSP stream.
4. Locate your camera's local IP address under **Settings ⚙️** -> **Device Info** -> **IP Address** (e.g. `192.168.0.30`).

---

## 2. Comprehensive Interface Walkthrough

<p align="center">
  <img src="assets/main_interface_overview.png" alt="Main Interface Overview" width="800">
</p>

### 📹 Tab 1: Live Monitoring & AI Vision Controls

#### 🎯 Region of Interest (Crib ROI) & Movement Sensitivity
* **`Usar Límite por Región Cuna` (Checkbox):** Enables bounding box enforcement. Vision models and alarms will focus solely inside the designated crib area, ignoring ambient room movements (e.g. parents walking by or curtains swaying).
* **`Sensibilidad Movimiento` (Slider: 0.5% – 10.0%):** Controls the threshold of pixel change required to classify the baby as *Moving/Restless*. Default is `3.0%`.
* **`Definir Zona Cuna con Ratón` (Button):** Activates drawing mode. Click and drag a rectangle over the baby's crib or bed directly on the video canvas.
* **`Restablecer Zoom (1.0x)` (Button):** Resets the canvas zoom level back to 100%. *(Tip: Use the mouse wheel to zoom in up to 4.0x on the crib, and right-click drag to pan)*.
* **`Visión Limpia (Info Fuera de Cámara)` (Checkbox):** Keeps the video feed pristine. Status badges, similarity scores, and movement percentages are moved to the lower status bar and transparent corner tags instead of covering the child's image.

#### ✂️ Baby Detection & Multi-Angle Photo Recognition
* **`Nombre Etiqueta` (Text field):** Custom label displayed on alerts (default: `Bebé`).
* **`Mostrar Cajas de Personas (Adultos)` (Checkbox):** Visualizes YOLO bounding boxes for adult caregivers in the room.
* **`Reconocimiento por Foto/Partes` (Checkbox):** Activates multi-angle template correlation to distinguish the baby from blankets and stuffed toys.
* **`Alertar Solo si Bebé Reconocido` (Checkbox):** Filters out general room motion alarms unless the baby's presence is positively verified.
* **`Similitud Fotos Bebé` (Slider: 10% – 90%):** Detection threshold for template matching.
* **`Recortar Foto del Bebé con Ratón` (Button):** Click and drag a box over your baby's face, feet, or body on the live feed.
  * **`Guardar Bebé` (Green Button):** Adds the crop to the positive template album (`Álbum de Fotos Guardadas`).
  * **`Vetar Falso Positivo` (Red Button):** Adds candidate patches (e.g., bedding folds, adult arms, patterned sheets) to the negative veto gallery (`Falsos Positivos Vetados`).
  * **`Descartar` (Gray Button):** Cancels the current crop.
* **`Optimizar Caché (.pkl)` (Green Button):** Precomputes normalized 64x64 binary correlation caches for instant 30 FPS inference and fast application startup.

---

<p align="center">
  <img src="assets/main_interface_controls.png" alt="Audio & Alert Settings" width="800">
</p>

#### 🔊 Audio Ambient Monitor, Alarms & Scheduling
* **`Nivel Audio` (Dynamic Progress Bar & Sound Threshold):** Displays real-time sound volume. Set `Tolerancia Umbral Sonido` (e.g. `6%`) to trigger alarms when crying occurs.
* **`Alerta por Movimiento` (Checkbox & Duration Dropdown):** Triggers when continuous movement lasts longer than selected (e.g. `8 Segundos`), preventing alarms from single micro-movements.
* **`Alerta por Llanto / Ruido` (Checkbox):** Triggers instant alerts when ambient decibels exceed the configured sound threshold.
* **`Pop-up Emergente Esquina` (Checkbox & Duration):** Shows a non-intrusive, Always-on-Top floating notification in the bottom-right corner with a live snapshot of the crib.
* **`Silenciar Tono Sonoro de Alertas` (Checkbox):** Suppresses audio beeps while preserving visual notifications.
* **`Escuchar Audio en Vivo` (Checkbox):** Streams live microphone audio from the camera directly to your PC speakers.
* **`Horario Silencioso (Modo Trabajo)` (Checkbox & Time Pickers):** Automatically silences beeps during your working hours (e.g. `09:00` to `18:00`).
* **`Pausar Alertas` (Button & Duration Dropdown):** Temporarily mutes all alarms for 5, 10, 15, 30, or 60 minutes while feeding or soothing the baby.
* **`Guardar Captura Limpia (Sin Procesar)` (Button):** Saves a high-resolution, unannotated snapshot to `captures/`.
* **`Configurar Conexión Cámara` (Button):** Reopens the network wizard to change IP or credentials.
* **`Probar Alarma Sonora y Pop-Up` (Button):** Verifies sound synthesis and floating PiP pop-up functionality.

---

### 📊 Tab 2: Pediatric Sleep Health & Analytics Dashboard

<p align="center">
  <img src="assets/analytics_dashboard.png" alt="Pediatric Sleep Health Dashboard" width="800">
</p>

* **Top KPI Metric Cards:**
  * 🌙 **Calidad de Sueño:** Overall restorative score (0-100) computed from motion stability and uninterrupted sleep intervals.
  * ⏱️ **Tiempo Monitoreado:** Total continuous monitoring duration in hours.
  * 😴 **Sueño Profundo (%):** Percentage of total time spent in calm, restorative deep sleep.
  * 📢 **Picos de Llanto / Alertas:** Count of acoustic anomalies and crying episodes detected.
* **Interactive 4-Quadrant Visualizer:**
  1. **Distribución del Estado de Sueño (Donut):** Proportions of *Sueño Profundo*, *Sueño Ligero*, *Despierto*, and *Fuera de Cuna*.
  2. **Actividad de Movimiento en Vivo:** Real-time waveform stream updated second-by-second with a live status indicator dot and dynamic user threshold line.
  3. **Picos de Audio y Llanto en Vivo:** Real-time volume histogram with dynamic color coding (Green: normal, Red: above threshold).
  4. **Resumen de Descanso:** Cumulative hourly sleep efficiency chart.
* **`Guardar Snapshot` (Button):** Generates a 1 KB compressed JSON snapshot of current telemetry.
* **`Exportar Reporte` (Button):** Exports complete historical CSV logs and summary charts for pediatric consultation.
* **`Nueva Sesión` (Button):** Resets telemetry counters to begin a new sleep session.

---

<br>

---

# 🇪🇸 Español

## 1. Configurar la Cuenta de Cámara Local Tapo
1. Abre la app **TP-Link Tapo** en tu celular ([Google Play](https://play.google.com/store/apps/details?id=com.tplink.iot) / [App Store](https://apps.apple.com/app/tp-link-tapo/id1472718009)) en la misma red Wi-Fi.
2. Entra a **Ajustes ⚙️** -> **Ajustes Avanzados** -> **Cuenta de la Cámara** *(Ver [Guía Oficial FAQ 2680](https://www.tp-link.com/support/faq/2680/))*.
3. Crea un usuario y contraseña local.
4. Anota la IP de la cámara en **Ajustes ⚙️** -> **Información del Dispositivo** -> **Dirección IP** (ej. `192.168.0.30`).

---

## 2. Guía Detallada de la Interfaz y Controles

<p align="center">
  <img src="assets/main_interface_overview.png" alt="Vista General de la Interfaz" width="800">
</p>

### 📹 Pestaña 1: Monitoreo en Vivo y Visión Artificial

#### 🎯 Región de Interés (Zona Cuna ROI) y Sensibilidad
* **`Usar Límite por Región Cuna`:** Fuerza a que todas las alertas y detecciones de movimiento se limiten estrictamente al espacio de la cuna, ignorando el resto de la habitación.
* **`Sensibilidad Movimiento` (0.5% a 10.0%):** Define qué porcentaje de cambio en los píxeles se considera inquietud o movimiento (valor por defecto: `3.0%`).
* **`Definir Zona Cuna con Ratón`:** Permite hacer clic y arrastrar un recuadro azul sobre la cuna directamente en la pantalla de video.
* **`Restablecer Zoom (1.0x)`:** Regresa la imagen a tamaño completo. *(Tip: Con la rueda del ratón puedes hacer zoom hasta 4.0x sobre la cuna, y con clic derecho arrastrar la vista)*.
* **`Visión Limpia (Info Fuera de Cámara)`:** Mantiene el video limpio y libre de textos superpuestos, enviando las métricas a la barra inferior.

#### ✂️ Reconocimiento del Bebé y Gestión de Plantillas
* **`Reconocimiento por Foto/Partes`:** Activa la correlación multi-ángulo para distinguir al bebé de almohadas, sábanas o juguetes.
* **`Alertar Solo si Bebé Reconocido`:** Evita falsas alarmas de movimiento si el bebé no está presente en la cuna.
* **`Similitud Fotos Bebé` (Slider 10% a 90%):** Ajusta la tolerancia de coincidencia visual.
* **`Recortar Foto del Bebé con Ratón`:** Haz clic y arrastra sobre la cara, cuerpo o pies del bebé en el video en vivo.
  * **`Guardar Bebé` (Botón Verde):** Agrega la foto al álbum positivo (`Álbum de Fotos Guardadas`).
  * **`Vetar Falso Positivo` (Botón Rojo):** Guarda recortes de sábanas, almohadas o brazos de adultos en la galería negativa (`Falsos Positivos Vetados`) para bloquear detecciones erróneas mediante puntuación competitiva (`Score = Score_pos - 0.70 × Score_neg`).
* **`Optimizar Caché (.pkl)`:** Compila las fotos en memoria binaria para un inicio ultrarrápido a 30 FPS.

---

<p align="center">
  <img src="assets/main_interface_controls.png" alt="Ajustes de Audio y Notificaciones" width="800">
</p>

#### 🔊 Monitor de Audio Ambiental, Alertas y Horarios
* **`Nivel Audio` y `Tolerancia Umbral Sonido`:** Indicador dinámico de decibeles con barra de umbral (ej. `6%`) para capturar llantos.
* **`Alerta por Movimiento`:** Dispara alarma si el movimiento continuo supera el tiempo seleccionado (ej. `8 Segundos`), evitando falsos avisos por micro-movimientos aislados.
* **`Alerta por Llanto / Ruido`:** Alerta instantánea si el sonido supera el umbral de disparo.
* **`Pop-up Emergente Esquina`:** Notificación flotante Always-on-Top en la esquina inferior derecha con foto en vivo del bebé sobre cualquier juego o programa de trabajo.
* **`Silenciar Tono Sonoro de Alertas`:** Desactiva pitidos sonoros manteniendo avisos visuales.
* **`Escuchar Audio en Vivo`:** Reproduce el micrófono de la cámara en los altavoces de la PC.
* **`Horario Silencioso (Modo Trabajo)`:** Silencia automáticamente los sonidos durante videollamadas o jornadas laborales (ej. `09:00` a `18:00`).
* **`Pausar Alertas`:** Suspende alertas por 5, 10, 15, 30 o 60 minutos durante la alimentación o cambio de pañales.
* **`Guardar Captura Limpia`:** Guarda una foto limpia sin marcas en la carpeta `captures/`.
* **`Configurar Conexión Cámara`:** Permite reconfigurar IP y credenciales en cualquier momento.
* **`Probar Alarma Sonora y Pop-Up`:** Verifica el funcionamiento de los sonidos y la ventana emergente.

---

### 📊 Pestaña 2: Salud y Calidad del Sueño

<p align="center">
  <img src="assets/analytics_dashboard.png" alt="Dashboard de Analítica del Sueño" width="800">
</p>

* **Tarjetas KPI Superiores:** Métricas destacadas de Calidad de Sueño (0-100), Horas Monitoreadas, Porcentaje de Sueño Profundo y Eventos de Llanto.
* **Cuadrante de Gráficos en Tiempo Real:**
  1. **Distribución del Estado de Sueño:** Gráfico de dona con porcentajes de Sueño Profundo, Ligero, Despierto y Fuera de Cuna.
  2. **Movimiento en Vivo:** Curva de agitación continua que se actualiza cada segundo con punto indicador en vivo y línea de umbral dinámico.
  3. **Picos de Audio en Vivo:** Oscilograma de barras en tiempo real que reacciona de verde a rojo según el umbral configurado.
  4. **Resumen de Descanso:** Historial acumulativo de descanso.
* **`Guardar Snapshot`:** Crea un registro comprimido de 1 KB con la telemetría actual.
* **`Exportar Reporte`:** Genera un archivo CSV con todo el historial para revisiones pediátricas.
* **`Nueva Sesión`:** Reinicia las métricas para monitorear una nueva siesta o noche.
