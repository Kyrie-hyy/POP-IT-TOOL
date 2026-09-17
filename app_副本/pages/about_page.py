"""About page (关于我们) - new page added in the V3 UI design."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QPixmap

from app.components.worker import TaskWorker
from app.core.config import APP_VERSION
from app.core.paths import resource_path
from app.i18n.language_manager import t, language_manager
from app.theme.colors import colors
from app.services.admin_checker import admin_checker
from app.services.update_service import update_service


class AboutPage(QWidget):
    """关于我们: brand info, version, admin status, update check."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        title = QLabel(t("ab.title"))
        title.setStyleSheet(f"""
            font-size: 20px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        outer.addWidget(title)

        card = QFrame()
        card.setObjectName("aboutCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 16))
        card.setGraphicsEffect(shadow)
        card.setStyleSheet(f"""
            QFrame#aboutCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 18px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(resource_path("assets/logo.png"))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(150, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        layout.addWidget(logo)

        name = QLabel("IT-Toolbox")
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(f"""
            font-size: 20px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(name)

        pill_row = QHBoxLayout()
        pill_row.addStretch()
        version = QLabel(f"v{APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        version.setFixedHeight(22)
        version.setStyleSheet(f"""
            QLabel {{
                background: {colors.pill_yellow};
                color: {colors.pill_text};
                font-size: 11px; font-weight: 800;
                padding: 0 10px;
                border-radius: 10px;
                border: none;
            }}
        """)
        pill_row.addWidget(version)
        pill_row.addStretch()
        layout.addLayout(pill_row)

        desc = QLabel(t("ab.desc"))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        layout.addWidget(desc)

        layout.addSpacing(8)

        self._info_label = QLabel(
            t("ab.privilege_line", status=self._admin_disp()) + "\n"
            + t("ab.copyright")
        )
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setStyleSheet(f"""
            font-size: 11px; color: {colors.text_tertiary}; background: transparent;
        """)
        layout.addWidget(self._info_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.update_btn = QPushButton(t("ab.btn_check"))
        self.update_btn.setFixedHeight(30)
        self.update_btn.setMinimumWidth(100)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self._check_update)
        self.update_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.popmart_yellow};
                border: none;
                border-radius: 12px;
                font-size: 12px; font-weight: 700;
                color: {colors.nav_active_text};
                padding: 0 20px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.popmart_yellow_hover};
            }}
        """)
        btn_row.addWidget(self.update_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        outer.addWidget(card)
        outer.addStretch()

        # 含状态参数的动态文案，整句同步匹配不上占位符词条，切语言时就地重设
        language_manager.language_changed.connect(self._retranslate)

    @staticmethod
    def _admin_disp() -> str:
        """权限状态显示层翻译：服务层只回中文，按当前语言取词（与工具箱一致）。"""
        from app.services.admin_checker import admin_status_display

        return admin_status_display()

    def _retranslate(self) -> None:
        self._info_label.setText(
            t("ab.privilege_line", status=self._admin_disp()) + "\n"
            + t("ab.copyright")
        )

    def _check_update(self) -> None:
        self.update_btn.setEnabled(False)
        self.update_btn.setText(t("ab.checking"))

        def on_finished(result) -> None:
            self.update_btn.setEnabled(True)
            self.update_btn.setText(t("ab.btn_check"))
            from PySide6.QtWidgets import QMessageBox
            try:
                if not result.success:
                    QMessageBox.warning(self, t("ab.btn_check"), result.message)
                    return
                data = result.data or {}
                if data.get("has_update"):
                    QMessageBox.information(
                        self,
                        t("ab.btn_check"),
                        t(
                            "ab.new_version_found",
                            current=APP_VERSION,
                            latest=data.get("latest_version", ""),
                        ),
                    )
                else:
                    QMessageBox.information(
                        self,
                        t("ab.btn_check"),
                        t("ab.up_to_date", version=APP_VERSION),
                    )
            except Exception:
                pass

        def on_error(err: str) -> None:
            self.update_btn.setEnabled(True)
            self.update_btn.setText(t("ab.btn_check"))
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, t("ab.btn_check"), t("ab.update_error", err=err))

        worker = TaskWorker(update_service.check_for_update)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()
