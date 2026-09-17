"""Fluent Design color system for POP IT Toolbox V2.

Enterprise-grade color palette inspired by Microsoft Fluent Design,
Windows Security, and Microsoft 365 Admin Center.

Primary: #FFC928 (POP MART Yellow)
Background: #F7F8FA
Surface: #FFFFFF
Border: #EAEAEA
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class FluentColors:
    """POP IT Toolbox V2 color tokens — Microsoft Fluent Design inspired."""

    # ── Brand ──
    primary: str = "#FFC928"
    primary_hover: str = "#FFB300"
    primary_pressed: str = "#E09C00"

    # POP MART brand
    popmart_yellow: str = "#FFC928"
    popmart_yellow_hover: str = "#FFB300"
    popmart_yellow_dark: str = "#E09C00"
    popmart_yellow_light: str = "#FFF8E1"

    # ── Microsoft 365 Colors ──
    m365_blue: str = "#0078D4"
    m365_green: str = "#107C10"
    m365_orange: str = "#FF8C00"
    m365_purple: str = "#5C2D91"
    m365_red: str = "#D13438"
    m365_teal: str = "#00B7C3"
    m365_pink: str = "#E3008C"

    # ── Semantic ──
    success: str = "#107C10"
    warning: str = "#FF8C00"
    danger: str = "#D13438"
    info: str = "#0078D4"

    # Status card colors
    status_green: str = "#107C10"
    status_blue: str = "#0078D4"
    status_orange: str = "#FF8C00"
    status_purple: str = "#5C2D91"

    # ── Backgrounds ──
    background: str = "#F7F8FA"
    surface: str = "#FFFFFF"
    surface_alt: str = "#FAFAFA"

    # ── Sidebar (white) ──
    sidebar_bg: str = "#FFFFFF"
    sidebar_hover: str = "#FFF6D5"
    sidebar_active: str = "#FFC928"
    sidebar_active_bg: str = "#FFF8E1"
    sidebar_text: str = "#4A4A4A"
    sidebar_text_active: str = "#222222"

    # ── Header ──
    header_bg: str = "#FFFFFF"

    # ── Text ──
    text_primary: str = "#222222"
    text_secondary: str = "#707070"
    text_tertiary: str = "#9CA3AF"
    text_on_dark: str = "#FFFFFF"

    # ── Borders ──
    border: str = "#EAEAEA"
    border_light: str = "#F0F0F0"

    # ── Shadow ──
    shadow: str = "rgba(0,0,0,0.08)"

    # V3 design tokens (2026-08-05, restored from the UI design image)
    page_bg: str = "#F8F8F8"          # page content background
    logo_badge_start: str = "#F1798F" # header POP MART badge gradient start
    logo_badge_end: str = "#E6344B"   # header POP MART badge gradient end
    pill_yellow: str = "#F5D352"      # version pill background
    pill_text: str = "#4A4E5D"        # version pill text
    avatar_teal: str = "#56C4C9"      # avatar circle background
    footer_bg: str = "#F2F2F5"        # footer status bar background
    footer_border: str = "#E4E4E8"    # footer status bar top border
    footer_text: str = "#6B7280"      # footer status bar text
    input_border: str = "#E2E2E6"     # line edit border
    card_border: str = "#EBEBEF"      # card border
    tool_btn_bg: str = "#F7F7F9"      # card action button background
    tool_btn_text: str = "#4A4E5D"    # card action button text
    nav_active_text: str = "#3B2E00"  # sidebar active item text

    # Network tool icon colors (sampled from the design image)
    net_title_icon: str = "#06A2DE"
    net_ping: str = "#4BC457"
    net_dns: str = "#4D7DFC"
    net_flush: str = "#0F919A"
    net_renew: str = "#3399FB"
    net_ip: str = "#A779F5"
    net_tracert: str = "#FD923D"
    net_release: str = "#FA6250"
    net_winsock: str = "#6AC754"


# Global color instance
colors = FluentColors()


def get_status_color(status: str) -> str:
    """Get the appropriate color for a given status."""
    status_map: Dict[str, str] = {
        "success": colors.success,
        "warning": colors.warning,
        "danger": colors.danger,
        "info": colors.info,
        "active": colors.success,
        "inactive": colors.text_tertiary,
        "normal": colors.success,
        "error": colors.danger,
        "healthy": colors.success,
        "unhealthy": colors.danger,
    }
    return status_map.get(status.lower(), colors.text_secondary)
