"""
Pestaña de Salud y Análisis del Sueño con Gráficos Interactivos de Matplotlib en PySide6.
Presenta 4 estadísticas esenciales de descanso, llanto, snapshots inteligentes e historial a largo plazo.
"""

import os
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from typing import Optional, Tuple, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QFrame, QFileDialog, QMessageBox, QScrollArea, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.services.analytics_service import BabyAnalyticsService

class AnalyticsTabWidget(QWidget):
    def __init__(self, analytics_service: BabyAnalyticsService, user_config: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.analytics_service = analytics_service
        self.user_config = user_config or {}
        self._init_ui()

    def get_thresholds(self) -> Tuple[float, float]:
        """Obtiene los umbrales dinámicos actuales de movimiento y audio según la configuración del usuario."""
        m_thresh = float(self.user_config.get("motion_sensitivity", 0.03)) * 100.0
        s_thresh = float(self.user_config.get("sound_threshold", 0.06)) * 100.0
        return m_thresh, s_thresh

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. ENCABEZADO Y CONTROLES SUPERIORES
        # -------------------------------------------------------------
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("📊 Panel de Salud y Calidad de Sueño del Bebé", self)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8;")
        lbl_subtitle = QLabel("Telemetría continua, microdespertares y archivo por snapshots inteligentes", self)
        lbl_subtitle.setStyleSheet("font-size: 11px; color: #94A3B8;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_style = """
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #334155; border-color: #38BDF8; }
        """

        # Selector de Vista (En Vivo vs Historial Completo)
        self.combo_view = QComboBox(self)
        self.combo_view.addItems(["🟢 Sesión Actual (En Vivo)", "📅 Historial Total (Snapshots)"])
        self.combo_view.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: bold;")
        self.combo_view.currentIndexChanged.connect(self.refresh_charts)
        header_layout.addWidget(self.combo_view)

        btn_snapshot = QPushButton("📸 Guardar Snapshot", self)
        btn_snapshot.setStyleSheet("""
            QPushButton {
                background-color: #065F46;
                color: #A7F3D0;
                border: 1px solid #047857;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #047857; color: white; }
        """)
        btn_snapshot.clicked.connect(self._on_snapshot_clicked)

        btn_refresh = QPushButton("🔄 Actualizar", self)
        btn_refresh.setStyleSheet(btn_style)
        btn_refresh.clicked.connect(self.refresh_charts)

        btn_export = QPushButton("💾 Exportar Reporte", self)
        btn_export.setStyleSheet(btn_style)
        btn_export.clicked.connect(self._on_export_clicked)

        btn_clear = QPushButton("🗑️ Nueva Sesión", self)
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #3B1621;
                color: #FCA5A5;
                border: 1px solid #7F1D1D;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #991B1B; color: white; }
        """)
        btn_clear.clicked.connect(self._on_clear_clicked)

        header_layout.addWidget(btn_snapshot)
        header_layout.addWidget(btn_refresh)
        header_layout.addWidget(btn_export)
        header_layout.addWidget(btn_clear)
        main_layout.addLayout(header_layout)

        # -------------------------------------------------------------
        # 2. FILA DE 4 TARJETAS KPI (MÉTRICAS CLAVE DESTACADAS)
        # -------------------------------------------------------------
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_score, self.lbl_score_val = self._create_kpi_card("🌙 Calidad de Sueño", "100 / 100", "#10B981")
        self.card_hours, self.lbl_hours_val = self._create_kpi_card("⏱️ Tiempo Monitoreado", "0.0 Horas", "#38BDF8")
        self.card_deep, self.lbl_deep_val = self._create_kpi_card("😴 Sueño Profundo", "0.0%", "#A855F7")
        self.card_crying, self.lbl_crying_val = self._create_kpi_card("📢 Picos de Llanto / Alertas", "0 Eventos", "#F59E0B")

        kpi_layout.addWidget(self.card_score)
        kpi_layout.addWidget(self.card_hours)
        kpi_layout.addWidget(self.card_deep)
        kpi_layout.addWidget(self.card_crying)
        main_layout.addLayout(kpi_layout)

        # -------------------------------------------------------------
        # 3. CUADRANTE DE 4 GRÁFICOS CON MATPLOTLIB
        # -------------------------------------------------------------
        self.fig = Figure(figsize=(10, 6), facecolor="#0F172A")
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setStyleSheet("background-color: #0F172A; border-radius: 8px;")
        main_layout.addWidget(self.canvas, stretch=1)

        # Actualización inicial y timer periódico cada 1 segundo para tiempo real fluido
        self._is_tab_active = False
        self.refresh_charts()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_charts)
        self.timer.start(1000)

    def set_active_view(self, is_active: bool):
        """Ajusta la frecuencia de actualización: 1s si está visible, 15s en segundo plano."""
        self._is_tab_active = is_active
        if is_active:
            self.refresh_charts()
            self.timer.setInterval(1000)
        else:
            self.timer.setInterval(15000)

    def _create_kpi_card(self, title: str, initial_val: str, accent_color: str) -> tuple:
        card = QFrame(self)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E293B;
                border: 1px solid #334155;
                border-left: 4px solid {accent_color};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        lbl_t = QLabel(title, card)
        lbl_t.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: bold; border: none;")
        lbl_v = QLabel(initial_val, card)
        lbl_v.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {accent_color}; border: none;")

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return card, lbl_v

    def refresh_charts(self):
        """Calcula estadísticas y redibuja los 4 gráficos con Matplotlib en tiempo real."""
        view_mode = "ALL_HISTORY" if self.combo_view.currentIndex() == 1 else "LIVE"
        stats = self.analytics_service.compute_summary_statistics(view_mode=view_mode)
        motion_thresh_pct, sound_thresh_pct = self.get_thresholds()

        # Actualizar valores de las tarjetas KPI
        score = stats["sleep_quality_score"]
        self.lbl_score_val.setText(f"{score} / 100")
        if score >= 80:
            self.lbl_score_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981; border: none;")
        elif score >= 50:
            self.lbl_score_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #F59E0B; border: none;")
        else:
            self.lbl_score_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #EF4444; border: none;")

        snap_txt = f" ({stats.get('snapshots_count', 0)} Snapshots)" if view_mode == "ALL_HISTORY" else ""
        self.lbl_hours_val.setText(f"{stats['total_hours']} Horas{snap_txt}")
        self.lbl_deep_val.setText(f"{stats['deep_sleep_pct']}%")
        self.lbl_crying_val.setText(f"{stats['crying_episodes']} Eventos")

        # Limpiar figura
        self.fig.clear()
        self.fig.subplots_adjust(left=0.06, right=0.96, top=0.92, bottom=0.10, wspace=0.25, hspace=0.38)

        # -------------------------------------------------------------
        # GRÁFICO 1 (Superior Izq): Distribución de Estados de Sueño (Donut)
        # -------------------------------------------------------------
        ax1 = self.fig.add_subplot(2, 2, 1)
        ax1.set_facecolor("#0F172A")
        ax1.set_title("1. Distribución del Estado de Sueño", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)

        dist = stats["sleep_distribution"]
        labels = []
        sizes = []
        colors_map = {
            "Sueño Profundo": "#10B981",
            "Sueño Ligero": "#38BDF8",
            "Despierto": "#F59E0B",
            "Fuera de Cuna": "#64748B"
        }
        colors = []

        for k, v in dist.items():
            if v > 0:
                labels.append(k)
                sizes.append(v)
                colors.append(colors_map.get(k, "#38BDF8"))

        if sizes:
            wedges, texts, autotexts = ax1.pie(
                sizes, labels=labels, autopct="%1.0f%%", startangle=140,
                colors=colors, textprops=dict(color="#F8FAFC", fontsize=8),
                wedgeprops=dict(width=0.45, edgecolor="#0F172A")
            )
            for autotext in autotexts:
                autotext.set_color("#FFFFFF")
                autotext.set_fontweight("bold")
        else:
            ax1.text(0.5, 0.5, "Registrando datos...", color="#94A3B8", ha="center", va="center", fontsize=9)
            ax1.axis("off")

        # -------------------------------------------------------------
        # GRÁFICO 2 (Superior Der): Actividad de Movimiento y Agitación en Tiempo Real
        # -------------------------------------------------------------
        ax2 = self.fig.add_subplot(2, 2, 2)
        ax2.set_facecolor("#1E293B")

        live_m = stats.get("live_motions", []) or stats.get("motions", [])
        if live_m:
            m_sub = live_m[-60:]
            x_vals = list(range(len(m_sub)))
            curr_m = m_sub[-1]
            ax2.plot(x_vals, m_sub, color="#38BDF8", linewidth=1.8, label="Movimiento %")
            ax2.fill_between(x_vals, m_sub, color="#38BDF8", alpha=0.25)
            # Punto indicador en vivo en la última muestra
            dot_color = "#EF4444" if curr_m >= motion_thresh_pct else "#10B981"
            ax2.scatter([len(m_sub) - 1], [curr_m], color=dot_color, s=45, zorder=5, label=f"Actual ({curr_m:.1f}%)")
            ax2.axhline(y=motion_thresh_pct, color="#EF4444", linestyle="--", linewidth=1.2, label=f"Umbral Alerta ({motion_thresh_pct:.1f}%)")
            ax2.set_title(f"2. Movimiento en Vivo: {curr_m:.1f}% (Umbral: {motion_thresh_pct:.1f}%)", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            ax2.set_ylim(0, max(8.0, max(max(m_sub), motion_thresh_pct) * 1.35))
            ax2.tick_params(colors="#94A3B8", labelsize=8)
            ax2.grid(True, linestyle=":", color="#334155", alpha=0.7)
            ax2.legend(facecolor="#0F172A", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=7, loc="upper right")
        else:
            ax2.set_title("2. Actividad de Movimiento y Agitación", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            ax2.text(0.5, 0.5, "Registrando muestras de movimiento...", color="#94A3B8", ha="center", va="center", fontsize=9)
            ax2.tick_params(colors="#94A3B8", labelsize=8)

        # -------------------------------------------------------------
        # GRÁFICO 3 (Inferior Izq): Picos de Audio y Llanto en Tiempo Real
        # -------------------------------------------------------------
        ax3 = self.fig.add_subplot(2, 2, 3)
        ax3.set_facecolor("#1E293B")

        live_a = stats.get("live_audios", []) or stats.get("audios", [])
        if live_a:
            a_sub = live_a[-60:]
            x_vals = list(range(len(a_sub)))
            curr_a = a_sub[-1]
            bar_colors = ["#EF4444" if val >= sound_thresh_pct else ("#F59E0B" if val >= sound_thresh_pct * 0.70 else "#10B981") for val in a_sub]
            ax3.bar(x_vals, a_sub, color=bar_colors, width=0.85, label="Volumen %")
            dot_color = "#EF4444" if curr_a >= sound_thresh_pct else "#38BDF8"
            ax3.scatter([len(a_sub) - 1], [curr_a], color=dot_color, s=35, zorder=5)
            ax3.axhline(y=sound_thresh_pct, color="#F59E0B", linestyle="--", linewidth=1.2, label=f"Umbral Disparo ({int(sound_thresh_pct)}%)")
            ax3.set_title(f"3. Nivel de Audio en Vivo: {int(curr_a)}% (Umbral: {int(sound_thresh_pct)}%)", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            ax3.set_ylim(0, max(20.0, max(max(a_sub), sound_thresh_pct) * 1.35))
            ax3.tick_params(colors="#94A3B8", labelsize=8)
            ax3.grid(True, linestyle=":", color="#334155", alpha=0.7)
            ax3.legend(facecolor="#0F172A", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=7, loc="upper right")
        else:
            ax3.set_title("3. Nivel de Audio Ambiental y Llanto", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            ax3.text(0.5, 0.5, "Registrando muestras de audio...", color="#94A3B8", ha="center", va="center", fontsize=9)
            ax3.tick_params(colors="#94A3B8", labelsize=8)
            ax3.tick_params(colors="#94A3B8", labelsize=8)

        # -------------------------------------------------------------
        # GRÁFICO 4 (Inferior Der): Resumen de Descanso o Tendencia de Snapshots
        # -------------------------------------------------------------
        ax4 = self.fig.add_subplot(2, 2, 4)
        ax4.set_facecolor("#1E293B")

        snapshots = self.analytics_service.load_all_snapshots()
        if view_mode == "ALL_HISTORY" and snapshots:
            ax4.set_title("4. Evolución de Calidad por Snapshots / Días", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            snap_dates = [s["date"].replace("snapshot_", "")[:10] for s in snapshots][-10:]
            snap_scores = [s["sleep_quality_score"] for s in snapshots][-10:]
            bars = ax4.bar(snap_dates, snap_scores, color="#10B981", width=0.5)
            ax4.set_ylim(0, 105)
            ax4.tick_params(colors="#94A3B8", labelsize=7)
            ax4.set_ylabel("Score (0-100)", color="#94A3B8", fontsize=8)
            ax4.grid(axis="y", linestyle=":", color="#334155", alpha=0.7)
            for b in bars:
                h = b.get_height()
                ax4.text(b.get_x() + b.get_width()/2.0, h + 1, f"{int(h)}", ha="center", va="bottom", color="#F8FAFC", fontsize=7, fontweight="bold")
        else:
            ax4.set_title("4. Horas Totales por Fase de Descanso", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
            categories = ["Sueño Prof.", "Sueño Lig.", "Despierto", "Fuera Cuna"]
            hours_data = [
                (dist["Sueño Profundo"] * 5.0) / 3600.0,
                (dist["Sueño Ligero"] * 5.0) / 3600.0,
                (dist["Despierto"] * 5.0) / 3600.0,
                (dist["Fuera de Cuna"] * 5.0) / 3600.0
            ]
            bar_c = ["#10B981", "#38BDF8", "#F59E0B", "#64748B"]
            bars = ax4.bar(categories, hours_data, color=bar_c, width=0.55)
            ax4.tick_params(colors="#94A3B8", labelsize=8)
            ax4.set_ylabel("Horas", color="#94A3B8", fontsize=8)
            ax4.grid(axis="y", linestyle=":", color="#334155", alpha=0.7)

            for b in bars:
                h = b.get_height()
                if h > 0:
                    ax4.text(b.get_x() + b.get_width()/2.0, h + 0.02, f"{h:.1f}h", ha="center", va="bottom", color="#F8FAFC", fontsize=7, fontweight="bold")

        self.canvas.draw_idle()

    def _on_snapshot_clicked(self):
        snap_path = self.analytics_service.create_snapshot()
        if snap_path:
            QMessageBox.information(
                self, "Snapshot Guardado",
                f"✨ Snapshot condensado archivado con éxito en:\n{snap_path}\n\nLos datos históricos están a salvo y consolidados."
            )
            self.refresh_charts()
        else:
            QMessageBox.warning(self, "Sin Muestras", "Aún no hay suficientes datos para crear un snapshot.")

    def _on_export_clicked(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Exportar Reporte Consolidado",
            os.path.expanduser("~/baby_health_sleep_report.csv"),
            "Archivos CSV (*.csv)"
        )
        if dest:
            if self.analytics_service.export_consolidated_report(dest):
                QMessageBox.information(self, "Exportación Exitosa", f"El reporte histórico consolidado se guardó en:\n{dest}")
            else:
                QMessageBox.warning(self, "Error al Exportar", "No se encontraron datos para exportar.")

    def _on_clear_clicked(self):
        reply = QMessageBox.question(
            self, "Nueva Sesión",
            "¿Deseas guardar un Snapshot de la sesión actual antes de reiniciar el monitor para una nueva sesión?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save
        )
        if reply == QMessageBox.Save:
            self.analytics_service.create_snapshot()
            self.analytics_service.clear_live_session()
            self.refresh_charts()
            QMessageBox.information(self, "Nueva Sesión", "Snapshot archivado y nueva sesión iniciada.")
        elif reply == QMessageBox.Discard:
            self.analytics_service.clear_live_session()
            self.refresh_charts()
            QMessageBox.information(self, "Nueva Sesión", "Nueva sesión iniciada.")
