"""
Panel Lateral de Control y Ajustes (SettingsPanel).
Organizado en sub-pestañas temáticas ultra-compactas (Detección, Alertas/Audio, Álbum/Vetos)
para eliminar la necesidad de scroll vertical y optimizar la experiencia de usuario (UX).
"""
from typing import Optional
from PySide6.QtCore import Qt, Signal, QTime
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QSlider, QComboBox, QLineEdit, QTimeEdit, QGroupBox,
    QTabWidget, QWidget
)
from src.gui.widgets import AudioThresholdProgressBar

class SettingsPanel(QFrame):
    """
    Panel lateral derecho con pestañas compactas y organizadas.
    """
    roi_mode_toggled = Signal(bool)
    crop_mode_toggled = Signal(bool)
    reset_zoom_requested = Signal()
    reconfigure_camera_requested = Signal()
    test_popup_requested = Signal()
    save_raw_requested = Signal()
    rebuild_pkl_requested = Signal()
    help_guide_requested = Signal()
    pause_alerts_requested = Signal()
    close_app_requested = Signal()
    config_changed = Signal(str, object)

    def __init__(self, user_config, detector, parent=None):
        super().__init__(parent)
        self.user_config = user_config
        self.detector = detector
        self.setFixedWidth(365)
        self.setStyleSheet("""
            QFrame { background-color: #0F172A; border-radius: 10px; }
            QTabWidget::pane { border: 1px solid #1E293B; background-color: #0F172A; border-radius: 6px; }
            QTabBar::tab { background: #1E293B; color: #94A3B8; padding: 6px 10px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #0284C7; color: #FFFFFF; }
            QTabBar::tab:hover:!selected { background: #334155; color: #F8FAFC; }
            QGroupBox { font-size: 11px; font-weight: bold; color: #38BDF8; border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 14px; padding-bottom: 6px; padding-left: 6px; padding-right: 6px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; top: -5px; padding: 1px 4px; background-color: #0F172A; }
            QLabel { font-size: 11px; color: #F8FAFC; }
            QPushButton { background-color: #334155; color: white; border-radius: 5px; padding: 5px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #475569; }
            QCheckBox { color: white; font-size: 11px; spacing: 5px; }
            QSlider::groove:horizontal { height: 5px; background: #334155; border-radius: 2px; }
            QSlider::handle:horizontal { background: #38BDF8; width: 14px; margin: -5px 0; border-radius: 7px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # -------------------------------------------------------------
        # SUB-PESTAÑAS TEMÁTICAS (Zero-scroll)
        # -------------------------------------------------------------
        self.sub_tabs = QTabWidget(self)
        
        # PESTAÑA 1: DETECCIÓN & CUNA
        self.tab_detection = QWidget()
        layout_det = QVBoxLayout(self.tab_detection)
        layout_det.setContentsMargins(6, 6, 6, 6)
        layout_det.setSpacing(6)

        # Grupo: Zona Monitoreada
        grp_roi = QGroupBox("🎯 Zona Monitoreada & Cuna", self.tab_detection)
        layout_roi = QVBoxLayout(grp_roi)
        layout_roi.setSpacing(5)

        self.chk_use_roi = QCheckBox("🎯 Usar Límite por Región Cuna", grp_roi)
        self.chk_use_roi.setChecked(self.user_config.get("use_roi", True))
        layout_roi.addWidget(self.chk_use_roi)

        # Sensibilidad en una sola fila compacta
        sens_row = QHBoxLayout()
        self.lbl_sens = QLabel(f"Sensibilidad: {self.detector.sensitivity*100:.1f}%", grp_roi)
        self.lbl_sens.setFixedWidth(130)
        self.slider_sens = QSlider(Qt.Horizontal, grp_roi)
        self.slider_sens.setRange(5, 100)
        self.slider_sens.setValue(int(self.detector.sensitivity * 1000))
        sens_row.addWidget(self.lbl_sens)
        sens_row.addWidget(self.slider_sens)
        layout_roi.addLayout(sens_row)

        roi_btn_row = QHBoxLayout()
        self.btn_mode_roi = QPushButton("🎯 Definir Zona Cuna", grp_roi)
        self.btn_mode_roi.setCheckable(True)
        self.btn_mode_roi.setStyleSheet("""
            QPushButton { background-color: #1E293B; color: #94A3B8; border: 1px solid #334155; border-radius: 5px; padding: 5px; font-weight: bold; font-size: 10px; }
            QPushButton:checked { background-color: #0284C7; color: white; border: 1px solid #38BDF8; }
            QPushButton:hover { background-color: #334155; }
        """)
        self.btn_mode_roi.clicked.connect(lambda: self.roi_mode_toggled.emit(self.btn_mode_roi.isChecked()))

        btn_reset_zoom = QPushButton("🔍 Zoom 1.0x", grp_roi)
        btn_reset_zoom.setStyleSheet("background-color: #0284C7; color: white; border-radius: 4px; padding: 5px; font-size: 10px;")
        btn_reset_zoom.clicked.connect(lambda: self.reset_zoom_requested.emit())
        
        roi_btn_row.addWidget(self.btn_mode_roi)
        roi_btn_row.addWidget(btn_reset_zoom)
        layout_roi.addLayout(roi_btn_row)

        self.chk_clean_osd = QCheckBox("🧹 Visión Limpia (Ocultar OSD en video)", grp_roi)
        self.chk_clean_osd.setChecked(self.user_config.get("clean_osd", True))
        layout_roi.addWidget(self.chk_clean_osd)
        layout_det.addWidget(grp_roi)

        # Grupo: Reconocimiento del Bebé
        self.grp_baby = QGroupBox("👶 Reconocimiento por IA & Fotos", self.tab_detection)
        self.layout_baby = QVBoxLayout(self.grp_baby)
        self.layout_baby.setSpacing(5)

        name_layout = QHBoxLayout()
        lbl_name = QLabel("🏷️ Nombre:", self.grp_baby)
        lbl_name.setStyleSheet("font-size: 10px; font-weight: bold; color: #94A3B8;")
        self.txt_baby_name = QLineEdit(self.grp_baby)
        self.txt_baby_name.setText(self.user_config.get("baby_name", "Bebé"))
        self.txt_baby_name.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px 5px; font-size: 11px;")
        name_layout.addWidget(lbl_name)
        name_layout.addWidget(self.txt_baby_name)
        self.layout_baby.addLayout(name_layout)

        self.chk_show_persons = QCheckBox("👤 Mostrar Cajas de Personas (Adultos)", self.grp_baby)
        self.chk_show_persons.setChecked(self.user_config.get("show_persons", False))
        self.layout_baby.addWidget(self.chk_show_persons)

        self.chk_template = QCheckBox("🖼️ Reconocimiento por Foto/Partes", self.grp_baby)
        self.chk_template.setChecked(self.user_config.get("template_enabled", True))
        self.layout_baby.addWidget(self.chk_template)

        self.chk_only_baby_motion = QCheckBox("👶 Alertar Solo si Bebé Reconocido", self.grp_baby)
        self.chk_only_baby_motion.setChecked(self.user_config.get("only_baby_motion", False))
        self.layout_baby.addWidget(self.chk_only_baby_motion)

        # Slider de Similitud compacto en línea
        tmpl_row = QHBoxLayout()
        self.lbl_template_thresh = QLabel(f"Similitud Fotos: {self.detector.template_threshold*100:.0f}%", self.grp_baby)
        self.lbl_template_thresh.setFixedWidth(130)
        self.slider_template_thresh = QSlider(Qt.Horizontal, self.grp_baby)
        self.slider_template_thresh.setRange(10, 90)
        self.slider_template_thresh.setValue(int(self.detector.template_threshold * 100))
        tmpl_row.addWidget(self.lbl_template_thresh)
        tmpl_row.addWidget(self.slider_template_thresh)
        self.layout_baby.addLayout(tmpl_row)

        self.btn_mode_crop = QPushButton("✂️ Recortar Foto del Bebé con Ratón", self.grp_baby)
        self.btn_mode_crop.setCheckable(True)
        self.btn_mode_crop.setStyleSheet("""
            QPushButton { background-color: #0284C7; color: white; border: 1px solid #38BDF8; border-radius: 5px; padding: 5px; font-weight: bold; font-size: 10px; }
            QPushButton:checked { background-color: #F59E0B; color: black; border: 1px solid #FBBF24; }
            QPushButton:hover { background-color: #0369A1; }
        """)
        self.btn_mode_crop.clicked.connect(lambda: self.crop_mode_toggled.emit(self.btn_mode_crop.isChecked()))
        self.layout_baby.addWidget(self.btn_mode_crop)

        # Contenedor de Vista Previa de Recorte
        self.crop_box = QFrame(self.grp_baby)
        self.crop_box.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 4px;")
        crop_box_layout = QVBoxLayout(self.crop_box)
        crop_box_layout.setContentsMargins(4, 4, 4, 4)
        crop_box_layout.setSpacing(4)

        self.lbl_crop_preview_title = QLabel("✂️ Ningún recorte seleccionado", self.crop_box)
        self.lbl_crop_preview_title.setStyleSheet("font-size: 10px; color: #94A3B8; font-style: italic;")
        crop_box_layout.addWidget(self.lbl_crop_preview_title)

        self.lbl_crop_img = QLabel(self.crop_box)
        self.lbl_crop_img.setFixedHeight(65)
        self.lbl_crop_img.setAlignment(Qt.AlignCenter)
        self.lbl_crop_img.setStyleSheet("background-color: #020617; border-radius: 4px;")
        crop_box_layout.addWidget(self.lbl_crop_img)

        crop_btn_layout = QHBoxLayout()
        self.btn_save_photo = QPushButton("👶 Guardar", self.crop_box)
        self.btn_save_photo.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; font-size: 10px; padding: 4px;")
        self.btn_save_photo.setEnabled(False)

        self.btn_veto_photo = QPushButton("🚫 Vetar", self.crop_box)
        self.btn_veto_photo.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; font-size: 10px; padding: 4px;")
        self.btn_veto_photo.setEnabled(False)

        self.btn_discard_photo = QPushButton("🗑️ Descartar", self.crop_box)
        self.btn_discard_photo.setStyleSheet("background-color: #64748B; color: white; font-weight: bold; font-size: 10px; padding: 4px;")
        self.btn_discard_photo.setEnabled(False)

        crop_btn_layout.addWidget(self.btn_save_photo)
        crop_btn_layout.addWidget(self.btn_veto_photo)
        crop_btn_layout.addWidget(self.btn_discard_photo)
        crop_box_layout.addLayout(crop_btn_layout)
        self.layout_baby.addWidget(self.crop_box)

        layout_det.addWidget(self.grp_baby)
        layout_det.addStretch()
        self.sub_tabs.addTab(self.tab_detection, "🎯 Detección")

        # PESTAÑA 2: ALERTAS & AUDIO
        self.tab_alerts = QWidget()
        layout_alerts_tab = QVBoxLayout(self.tab_alerts)
        layout_alerts_tab.setContentsMargins(6, 6, 6, 6)
        layout_alerts_tab.setSpacing(6)

        grp_audio = QGroupBox("🔊 Monitor de Audio Ambiental", self.tab_alerts)
        layout_audio = QVBoxLayout(grp_audio)
        layout_audio.setSpacing(5)

        saved_sound_th = float(self.user_config.get("sound_threshold", 0.35))
        self.lbl_audio_vol = QLabel(f"Nivel Audio: 0%  (Umbral Disparo: {int(saved_sound_th*100)}%)", grp_audio)
        layout_audio.addWidget(self.lbl_audio_vol)

        self.progress_audio = AudioThresholdProgressBar(grp_audio)
        self.progress_audio.set_threshold(saved_sound_th)
        layout_audio.addWidget(self.progress_audio)

        sound_th_row = QHBoxLayout()
        self.lbl_sound_thresh = QLabel(f"Tolerancia Sonido: {int(saved_sound_th*100)}%", grp_audio)
        self.lbl_sound_thresh.setFixedWidth(130)
        self.slider_sound_thresh = QSlider(Qt.Horizontal, grp_audio)
        self.slider_sound_thresh.setRange(1, 90)
        self.slider_sound_thresh.setValue(int(saved_sound_th * 100))
        sound_th_row.addWidget(self.lbl_sound_thresh)
        sound_th_row.addWidget(self.slider_sound_thresh)
        layout_audio.addLayout(sound_th_row)

        self.chk_live_audio = QCheckBox("🔊 Escuchar Audio en Vivo", grp_audio)
        self.chk_live_audio.setChecked(self.user_config.get("live_audio", False))
        layout_audio.addWidget(self.chk_live_audio)
        layout_alerts_tab.addWidget(grp_audio)

        grp_triggers = QGroupBox("🚨 Disparadores de Alerta", self.tab_alerts)
        layout_triggers = QVBoxLayout(grp_triggers)
        layout_triggers.setSpacing(5)

        self.chk_alert_motion = QCheckBox("👁️ Alerta por Movimiento", grp_triggers)
        self.chk_alert_motion.setChecked(self.user_config.get("alert_motion", True))
        layout_triggers.addWidget(self.chk_alert_motion)

        motion_dur_layout = QHBoxLayout()
        lbl_motion_dur = QLabel("⏱️ Movimiento Continuo:", grp_triggers)
        lbl_motion_dur.setStyleSheet("font-size: 10px; font-weight: bold; color: #94A3B8;")
        self.combo_motion_min_duration = QComboBox(grp_triggers)
        self.combo_motion_min_duration.addItems([
            "Inmediato (0 seg)", "1 Segundo", "2 Segundos", "3 Segundos", "4 Segundos",
            "5 Segundos", "8 Segundos (Por defecto)", "10 Segundos", "15 Segundos",
            "20 Segundos", "25 Segundos", "30 Segundos"
        ])
        saved_motion_dur = self.user_config.get("motion_min_duration_sec", 8)
        dur_map = {0: "Inmediato (0 seg)", 1: "1 Segundo", 2: "2 Segundos", 3: "3 Segundos", 4: "4 Segundos",
                   5: "5 Segundos", 8: "8 Segundos (Por defecto)", 10: "10 Segundos", 15: "15 Segundos",
                   20: "20 Segundos", 25: "25 Segundos", 30: "30 Segundos"}
        self.combo_motion_min_duration.setCurrentText(dur_map.get(saved_motion_dur, "8 Segundos (Por defecto)"))
        self.combo_motion_min_duration.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-size: 10px;")
        motion_dur_layout.addWidget(lbl_motion_dur)
        motion_dur_layout.addWidget(self.combo_motion_min_duration)
        layout_triggers.addLayout(motion_dur_layout)

        self.chk_alert_sound = QCheckBox("👶 Alerta por Llanto / Ruido", grp_triggers)
        self.chk_alert_sound.setChecked(self.user_config.get("alert_sound", True))
        layout_triggers.addWidget(self.chk_alert_sound)

        popup_row = QHBoxLayout()
        self.chk_alert_popup = QCheckBox("🪟 Pop-up", grp_triggers)
        self.chk_alert_popup.setChecked(self.user_config.get("alert_popup", True))
        self.combo_popup_duration = QComboBox(grp_triggers)
        self.combo_popup_duration.addItems(["5 Segundos", "10 Segundos", "15 Segundos", "30 Segundos", "45 Segundos", "60 Segundos"])
        saved_dur = self.user_config.get("popup_duration_sec", 30)
        p_map = {5: "5 Segundos", 10: "10 Segundos", 15: "15 Segundos", 30: "30 Segundos", 45: "45 Segundos", 60: "60 Segundos"}
        self.combo_popup_duration.setCurrentText(p_map.get(saved_dur, "30 Segundos"))
        self.combo_popup_duration.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-size: 10px;")
        popup_row.addWidget(self.chk_alert_popup)
        popup_row.addWidget(QLabel("⏱️ Duración:", grp_triggers))
        popup_row.addWidget(self.combo_popup_duration)
        layout_triggers.addLayout(popup_row)

        self.chk_mute_alarm_sound = QCheckBox("🔕 Silenciar Tono Sonoro de Alertas", grp_triggers)
        self.chk_mute_alarm_sound.setChecked(self.user_config.get("mute_alarm_sound", False))
        layout_triggers.addWidget(self.chk_mute_alarm_sound)

        layout_alerts_tab.addWidget(grp_triggers)

        # Grupo: Horario Silencioso y Pausa
        grp_modes = QGroupBox("🔇 Horario Silencioso & Pausa", self.tab_alerts)
        layout_modes = QVBoxLayout(grp_modes)
        layout_modes.setSpacing(5)

        self.chk_silent_sched = QCheckBox("🔇 Horario Silencioso (Modo Trabajo)", grp_modes)
        self.chk_silent_sched.setChecked(self.user_config.get("silent_sched_enabled", False))
        layout_modes.addWidget(self.chk_silent_sched)

        sched_time_layout = QHBoxLayout()
        lbl_from = QLabel("De:", grp_modes)
        lbl_from.setStyleSheet("font-size: 10px; color: #94A3B8;")
        self.time_start = QTimeEdit(grp_modes)
        self.time_start.setDisplayFormat("HH:mm")
        st_parts = self.user_config.get("silent_sched_start", "09:00").split(":")
        self.time_start.setTime(QTime(int(st_parts[0]), int(st_parts[1])))
        self.time_start.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-size: 10px;")

        lbl_to = QLabel("A:", grp_modes)
        lbl_to.setStyleSheet("font-size: 10px; color: #94A3B8;")
        self.time_end = QTimeEdit(grp_modes)
        self.time_end.setDisplayFormat("HH:mm")
        et_parts = self.user_config.get("silent_sched_end", "18:00").split(":")
        self.time_end.setTime(QTime(int(et_parts[0]), int(et_parts[1])))
        self.time_end.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-size: 10px;")

        sched_time_layout.addWidget(lbl_from)
        sched_time_layout.addWidget(self.time_start)
        sched_time_layout.addWidget(lbl_to)
        sched_time_layout.addWidget(self.time_end)
        layout_modes.addLayout(sched_time_layout)

        pause_layout = QHBoxLayout()
        lbl_pause_dur = QLabel("⏱️ Pausa:", grp_modes)
        lbl_pause_dur.setStyleSheet("font-size: 10px; font-weight: bold; color: #94A3B8;")
        self.combo_pause_duration = QComboBox(grp_modes)
        self.combo_pause_duration.addItems(["1 Minuto", "5 Minutos", "10 Minutos", "15 Minutos", "30 Minutos"])
        saved_pause = self.user_config.get("pause_duration_str", "30 Minutos")
        self.combo_pause_duration.setCurrentText(saved_pause)
        self.combo_pause_duration.setStyleSheet("background-color: #1E293B; color: white; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-size: 10px;")
        
        self.btn_pause_alerts = QPushButton("⏸️ Pausar Alertas", grp_modes)
        self.btn_pause_alerts.setStyleSheet("""
            QPushButton { background-color: #0284C7; color: white; font-weight: bold; border-radius: 5px; padding: 4px 8px; }
            QPushButton:hover { background-color: #0369A1; }
        """)
        self.btn_pause_alerts.clicked.connect(lambda: self.pause_alerts_requested.emit())
        
        pause_layout.addWidget(lbl_pause_dur)
        pause_layout.addWidget(self.combo_pause_duration)
        pause_layout.addWidget(self.btn_pause_alerts)
        layout_modes.addLayout(pause_layout)

        layout_alerts_tab.addWidget(grp_modes)
        layout_alerts_tab.addStretch()
        self.sub_tabs.addTab(self.tab_alerts, "🔔 Alertas & Audio")

        # PESTAÑA 3: ÁLBUM & VETOS
        self.tab_album = QWidget()
        self.tab_album_layout = QVBoxLayout(self.tab_album)
        self.tab_album_layout.setContentsMargins(6, 6, 6, 6)
        self.tab_album_layout.setSpacing(6)

        self.chk_suggestions = QCheckBox("💡 Galería de Sugerencias Detectadas", self.tab_album)
        self.chk_suggestions.setChecked(self.user_config.get("suggestions_enabled", False))
        self.tab_album_layout.addWidget(self.chk_suggestions)

        # Los widgets de GalleryPanel se agregarán aquí dinámicamente desde pyside_app.py
        self.sub_tabs.addTab(self.tab_album, "🖼️ Álbum & Vetos")

        main_layout.addWidget(self.sub_tabs)

        # -------------------------------------------------------------
        # BOTONES DE ACCIÓN GENERALES (Footer compacto)
        # -------------------------------------------------------------
        footer_frame = QFrame(self)
        footer_frame.setStyleSheet("background-color: #1E293B; border-radius: 6px; padding: 2px;")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(4, 4, 4, 4)
        footer_layout.setSpacing(4)

        row1 = QHBoxLayout()
        btn_save_raw = QPushButton("📸 Captura Limpia", footer_frame)
        btn_save_raw.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 5px; font-size: 10px;")
        btn_save_raw.clicked.connect(lambda: self.save_raw_requested.emit())
        
        btn_config_cam = QPushButton("⚙️ Conexión Cámara", footer_frame)
        btn_config_cam.setStyleSheet("background-color: #334155; color: #F8FAFC; font-weight: bold; padding: 5px; font-size: 10px;")
        btn_config_cam.clicked.connect(lambda: self.reconfigure_camera_requested.emit())
        row1.addWidget(btn_save_raw)
        row1.addWidget(btn_config_cam)
        footer_layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_test = QPushButton("🔔 Probar Alarma", footer_frame)
        btn_test.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; padding: 5px; font-size: 10px;")
        btn_test.clicked.connect(lambda: self.test_popup_requested.emit())

        btn_quit = QPushButton("❌ Salir", footer_frame)
        btn_quit.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold; padding: 5px; font-size: 10px;")
        btn_quit.clicked.connect(lambda: self.close_app_requested.emit())
        row2.addWidget(btn_test)
        row2.addWidget(btn_quit)
        footer_layout.addLayout(row2)

        main_layout.addWidget(footer_frame)
