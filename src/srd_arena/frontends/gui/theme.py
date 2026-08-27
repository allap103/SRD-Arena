"""Provide theme support for the gui package."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .floating_labels import BATTLEFIELD_FLOATING_LABEL_STYLE

FANTASY_STYLESHEET = (
    """
QWidget {
    background: #1b1712;
    color: #eadfca;
    font-family: "Palatino", "Georgia", "Times New Roman";
    font-size: 14px;
}

QMainWindow {
    background: #140f0b;
}

QLabel {
    background: transparent;
    color: #eadfca;
}
"""
    + BATTLEFIELD_FLOATING_LABEL_STYLE.qt_tooltip_rule()
    + """
QFrame#panel,
QFrame#untitledPanel,
QFrame#sidebarPanel,
QFrame#rollRail,
QFrame#overlayCard {
    background: #241c15;
    border: 1px solid #8e6d3b;
    border-radius: 12px;
}

QFrame#scenePanel,
QFrame#choicesPanel,
QWidget#encounterPanel {
    background: #1d1711;
    border: 1px solid #73552c;
    border-radius: 14px;
}

QWidget#rootCentral {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #16110d,
        stop: 0.5 #221a13,
        stop: 1 #110d0a
    );
}

QTextEdit,
QScrollArea,
QStackedWidget {
    background: #2a2119;
    color: #f2e8d5;
    border: 1px solid #80613a;
    border-radius: 10px;
}

QTextEdit {
    padding: 10px;
    selection-background-color: #8a6730;
}

QPushButton {
    background: #5b4020;
    color: #f7edd9;
    border: 1px solid #c59a4b;
    border-radius: 10px;
    padding: 9px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background: #755229;
    border-color: #e1bb73;
}

QPushButton:pressed {
    background: #493116;
}

QPushButton:disabled {
    background: #34271c;
    color: #9d8a72;
    border-color: #5e4b36;
}

QPushButton[availability="unimplemented"] {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #6f2727,
        stop: 0.18 #6f2727,
        stop: 0.19 #401d1d,
        stop: 0.36 #401d1d,
        stop: 0.37 #6f2727,
        stop: 0.54 #6f2727,
        stop: 0.55 #401d1d,
        stop: 0.72 #401d1d,
        stop: 0.73 #6f2727,
        stop: 1 #6f2727
    );
    color: #f0c4c4;
    border-color: #a74b4b;
}

QPushButton#sidebarButton {
    text-align: left;
    padding-left: 16px;
    min-height: 40px;
}

QPushButton#endTurnButton {
    min-width: 150px;
}

QPushButton#movementButton {
    font-size: 18px;
    font-weight: 700;
}

QWidget#actionHeader {
    background: #30241a;
    border: 1px solid #7d6038;
    border-radius: 10px;
}

QLabel#sectionTitle,
QLabel#windowTitle,
QLabel#overlayTitle {
    color: #f3deb0;
    font-size: 18px;
    font-weight: 700;
}

QLabel#sectionSubtitle {
    color: #c9b89b;
}

QLabel#targetAllocationStatus {
    color: #fff4cf;
    background: #302712;
    border: 1px solid #d4ad45;
    border-radius: 7px;
    padding: 8px;
    font-weight: 700;
}

QWidget#combatBoard {
    background: #211a14;
    border: 1px solid #7a5c33;
    border-radius: 12px;
}

QWidget#dicePanel {
    background: #221b15;
}

QFrame#initiativeCard {
    background: #2b2118;
    border: 1px solid #7f6137;
    border-radius: 10px;
}

QFrame#accordionSection {
    background: #241c15;
    border: 1px solid #7d6038;
    border-radius: 8px;
}

QWidget#accordionHeader {
    background: #30241a;
    border-radius: 7px;
}

QToolButton#accordionToggle {
    background: #30241a;
    color: #f3deb0;
    border: none;
    border-radius: 7px;
    padding: 9px;
    font-weight: 700;
    text-align: left;
}

QToolButton#accordionToggle:hover {
    background: #493116;
}

QToolButton#accordionToggle[centered="true"] {
    text-align: center;
}

QWidget#accordionBody {
    background: #241c15;
}

QWidget#accordionBody QPushButton {
    padding: 4px 8px;
}

QFrame#initiativeCard[active="true"] {
    background: #3a2a16;
    border: 1px solid #d4ad58;
}

QLabel#initiativeTitle {
    color: #f3deb0;
    font-size: 13px;
    font-weight: 700;
}

QLabel#initiativeName {
    color: #eadfca;
    font-size: 14px;
    font-weight: 700;
}

QLabel#initiativeScore {
    color: #f3deb0;
    font-size: 15px;
    font-weight: 700;
}

QFrame#victoryOverlay {
    background: rgba(10, 8, 6, 200);
    border-radius: 16px;
}
"""
)


def apply_fantasy_theme(app: QApplication) -> None:
    """Apply fantasy theme."""

    app.setStyleSheet(FANTASY_STYLESHEET)
    font = QFont("Palatino")
    font.setPointSize(11)
    app.setFont(font)
