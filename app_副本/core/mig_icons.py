"""mig_icons — 缓存迁移模块专用 galaxy 图标（内嵌 SVG，离线可用）。

来源：galaxy-main 图标库（提取于 2026-09-10），仅迁移功能使用。
用法：
    from app.core.mig_icons import icon_pixmap, apply_to_button, apply_to_label
    btn.setIcon(icon_pixmap("search", "#07C160", 14))
"""

from typing import Dict, Tuple

from PySide6.QtCore import QSize, QRectF, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

# 无 currentColor 的图标：渲染时给未带 fill 的 <path> 注入颜色
_INJECT_FILL = {
    "wechat",
    "server",
}

_ICONS: Dict[str, str] = {
    "wechat":
        "<svg viewBox=\"0 0 100 100\"><g><path d=\"M 30.7873,85.113394 30.7873,46.556405 C 30.7873,41.101961 36.826342,35.342 40.898074,35.342 H 59.113981 C 63.73287,35.342 69.29995,40.103201 69.29995,46.784744\"></path><path d=\"M 13.461999,65.039335 H 58.028684 C 63.483128,65.039335 69.243089,59.000293 69.243089,54.928561 V 45.605853 C 69.243089,40.986964 65.02087,35.419884 58.339327,35.419884\"></path></g><circle cx=\"42.5\" cy=\"50.7\" r=\"1.9\"></circle><circle r=\"1.9\" cy=\"50.7\" cx=\"49.9\"></circle><circle cx=\"57.3\" cy=\"50.7\" r=\"1.9\"></circle></svg>",
    "feishu":
        "<svg stroke=\"currentColor\" stroke-width=\"1.5\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\" ><path d=\"M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5\" stroke-linejoin=\"round\" stroke-linecap=\"round\" ></path></svg>",
    "search":
        "<svg xmlns=\"http://www.w3.org/2000/svg\" aria-hidden=\"true\" viewBox=\"0 0 24 24\" stroke-width=\"2\" fill=\"none\" stroke=\"currentColor\"><path d=\"M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z\" stroke-linejoin=\"round\" stroke-linecap=\"round\"></path></svg>",
    "x":
        "<svg stroke=\"currentColor\" stroke-width=\"4\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M6 18L18 6M6 6l12 12\" stroke-linejoin=\"round\" stroke-linecap=\"round\"></path></svg>",
    "check":
        "<svg stroke=\"currentColor\" stroke-width=\"4\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M4.5 12.75l6 6 9-13.5\" stroke-linejoin=\"round\" stroke-linecap=\"round\"></path></svg>",
    "plus":
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" fill=\"none\" ><path d=\"M12 4v16m8-8H4\" stroke-width=\"2\" stroke-linejoin=\"round\" stroke-linecap=\"round\" ></path></svg>",
    "gear":
        "<svg stroke-linejoin=\"round\" stroke-linecap=\"round\" stroke-width=\"2\" stroke=\"currentColor\" fill=\"none\" viewBox=\"0 0 24 24\" xmlns=\"http://www.w3.org/2000/svg\" ><path d=\"M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z\" ></path><circle r=\"3\" cy=\"12\" cx=\"12\"></circle></svg>",
    "external":
        "<svg viewBox=\"0 0 20 20\"><path d=\"M16.198,10.896c-0.252,0-0.455,0.203-0.455,0.455v2.396c0,0.626-0.511,1.137-1.138,1.137H5.117c-0.627,0-1.138-0.511-1.138-1.137V7.852c0-0.626,0.511-1.137,1.138-1.137h5.315c0.252,0,0.456-0.203,0.456-0.455c0-0.251-0.204-0.455-0.456-0.455H5.117c-1.129,0-2.049,0.918-2.049,2.047v5.894c0,1.129,0.92,2.048,2.049,2.048h9.488c1.129,0,2.048-0.919,2.048-2.048v-2.396C16.653,11.099,16.45,10.896,16.198,10.896z\"></path><path d=\"M14.053,4.279c-0.207-0.135-0.492-0.079-0.63,0.133c-0.137,0.211-0.077,0.493,0.134,0.63l1.65,1.073c-4.115,0.62-5.705,4.891-5.774,5.082c-0.084,0.236,0.038,0.495,0.274,0.581c0.052,0.019,0.103,0.027,0.154,0.027c0.186,0,0.361-0.115,0.429-0.301c0.014-0.042,1.538-4.023,5.238-4.482l-1.172,1.799c-0.137,0.21-0.077,0.492,0.134,0.629c0.076,0.05,0.163,0.074,0.248,0.074c0.148,0,0.294-0.073,0.382-0.207l1.738-2.671c0.066-0.101,0.09-0.224,0.064-0.343c-0.025-0.118-0.096-0.221-0.197-0.287L14.053,4.279z\"></path></svg>",
    "folder":
        "<svg viewBox=\"0 0 24 24\" fill=\"none\"><g stroke-width=\"2\" stroke-linecap=\"round\" stroke=\"currentColor\" fill-rule=\"evenodd\" clip-rule=\"evenodd\"><path d=\"m3 7h17c.5523 0 1 .44772 1 1v11c0 .5523-.4477 1-1 1h-16c-.55228 0-1-.4477-1-1z\"></path><path d=\"m3 4.5c0-.27614.22386-.5.5-.5h6.29289c.13261 0 .25981.05268.35351.14645l2.8536 2.85355h-10z\"></path></g></svg>",
    "server":
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 512 512\"><path d=\"M64 32C28.7 32 0 60.7 0 96v64c0 35.3 28.7 64 64 64H448c35.3 0 64-28.7 64-64V96c0-35.3-28.7-64-64-64H64zm280 72a24 24 0 1 1 0 48 24 24 0 1 1 0-48zm48 24a24 24 0 1 1 48 0 24 24 0 1 1 -48 0zM64 288c-35.3 0-64 28.7-64 64v64c0 35.3 28.7 64 64 64H448c35.3 0 64-28.7 64-64V352c0-35.3-28.7-64-64-64H64zm280 72a24 24 0 1 1 0 48 24 24 0 1 1 0-48zm56 24a24 24 0 1 1 48 0 24 24 0 1 1 -48 0z\"></path></svg>",
    "restore":
        "<svg fill=\"none\" stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"2\" viewBox=\"0 0 24 24\" xmlns=\"http://www.w3.org/2000/svg\" ><path d=\"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path><path d=\"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16\"></path><path d=\"M8 16H3v5\"></path></svg>",
    "link":
        "<svg stroke-linejoin=\"round\" stroke-linecap=\"round\" stroke-width=\"2\" stroke=\"currentColor\" fill=\"none\" viewBox=\"0 0 24 24\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71\"></path><path d=\"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71\"></path></svg>",
}

_cache: Dict[Tuple[str, str, int, float], QPixmap] = {}


def _prepare(name: str, color: str) -> str:
    svg = _ICONS.get(name, "")
    if not svg:
        return ''
    svg = svg.replace("currentColor", color)
    if name in _INJECT_FILL:
        svg = svg.replace("<path ", f'<path fill="{color}" ')
        # 防止重复 fill 覆盖已有属性（简单去重：fill 在 stroke 前无碍）
    return svg


def icon_pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    """渲染图标为 QPixmap（DPR 安全：显式目标矩形，高分屏不裁剪）。"""
    key = (name, color, int(size), round(float(dpr), 2))
    pm = _cache.get(key)
    if pm is not None and not pm.isNull():
        return pm
    d = max(1, int(round(size * float(dpr))))
    pm = QPixmap(d, d)
    pm.fill(Qt.transparent)
    try:
        pm.setDevicePixelRatio(float(dpr))
    except Exception:
        pass
    svg = _prepare(name, color)
    if svg:
        renderer = QSvgRenderer(bytes(svg, encoding='utf-8'))
        if renderer.isValid():
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p, QRectF(0, 0, size, size))
            p.end()
    _cache[key] = pm
    return pm


def apply_to_button(btn, name: str, color: str, size: int = 14) -> None:
    """给按钮设置图标（文字保留，图标在左）。"""
    pm = icon_pixmap(name, color, size)
    if not pm.isNull():
        btn.setIcon(QIcon(pm))
        btn.setIconSize(QSize(size, size))


def apply_to_label(lbl, name: str, color: str, size: int) -> None:
    """给 QLabel 设置图标 pixmap。"""
    pm = icon_pixmap(name, color, size)
    if not pm.isNull():
        lbl.setPixmap(pm)
        lbl.setFixedSize(size, size)


def available(name: str) -> bool:
    return name in _ICONS
