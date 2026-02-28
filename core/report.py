"""Auto-generate PDF mission report with FDI map, stats, hotspots, drift, and route."""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


def generate_pdf_report(
    lat: float,
    lon: float,
    stats: dict,
    fdi: Optional[np.ndarray] = None,
    plastic_mask: Optional[np.ndarray] = None,
    lons_arr: Optional[np.ndarray] = None,
    lats_arr: Optional[np.ndarray] = None,
    cloud_mask: Optional[np.ndarray] = None,
    scene_dates: Optional[list[str]] = None,
    hotspots: Optional[list[dict]] = None,
    drift_result=None,
    route_result=None,
    output_path: Optional[str] = None,
) -> bytes:
    """Generate PDF mission report. Returns PDF as bytes."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            Image as RLImage, HRFlowable, PageBreak
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise ImportError("Install reportlab: pip install reportlab")

    _FONT_PATHS = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold"),
    ]
    _cyrillic_font = "Helvetica"
    for fpath, fname in _FONT_PATHS:
        try:
            import os
            if os.path.exists(fpath):
                pdfmetrics.registerFont(TTFont(fname, fpath))
                _cyrillic_font = "DejaVuSans"
        except Exception:
            pass

    png_bytes = None
    if fdi is not None and plastic_mask is not None:
        try:
            from viz.plots import make_static_png
            png_bytes = make_static_png(
                fdi=fdi, plastic_mask=plastic_mask,
                lons=lons_arr, lats=lats_arr,
                lat=lat, lon=lon,
                cloud_mask=cloud_mask,
                stats=stats,
                scene_dates=scene_dates or [],
                dpi=120,
            )
        except Exception as e:
            logger.warning(f"Could not generate map image: {e}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 4 * cm
    F = _cyrillic_font
    FB = _cyrillic_font + "-Bold" if _cyrillic_font == "DejaVuSans" else "Helvetica-Bold"

    title_style = ParagraphStyle(
        "EcoTitle", parent=styles["Title"],
        fontSize=20, spaceAfter=6,
        fontName=FB, textColor=colors.HexColor("#0d47a1"),
    )
    h1_style = ParagraphStyle(
        "EcoH1", parent=styles["Heading1"],
        fontSize=14, spaceAfter=4, spaceBefore=14,
        fontName=FB, textColor=colors.HexColor("#1565c0"),
    )
    h2_style = ParagraphStyle(
        "EcoH2", parent=styles["Heading2"],
        fontSize=11, spaceAfter=3, spaceBefore=8,
        fontName=FB, textColor=colors.HexColor("#1976d2"),
    )
    body_style = ParagraphStyle("EcoBody", parent=styles["Normal"],
                                fontSize=9, leading=14, fontName=F)
    caption_style = ParagraphStyle(
        "Caption", parent=styles["Normal"],
        fontSize=8, textColor=colors.grey,
        alignment=TA_CENTER, fontName=F,
    )

    def _table_style(extra=None):
        """Base table style with Cyrillic font."""
        base = [
            ("FONTNAME", (0, 0), (-1, -1), F),
            ("FONTNAME", (0, 0), (-1, 0), FB),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if extra:
            base.extend(extra)
        return TableStyle(base)

    story = []

    subtitle_style = ParagraphStyle(
        "EcoSubtitle", parent=styles["Normal"],
        fontSize=11, textColor=colors.HexColor("#546e7a"),
        spaceAfter=8, alignment=TA_CENTER, fontName=F,
    )
    story.append(Paragraph("🌊 antihype · Миссионный отчёт", title_style))
    story.append(Paragraph("Карта скоплений пластика — Sentinel-2 FDI", subtitle_style))
    story.append(HRFlowable(width=W, thickness=2, color=colors.HexColor("#1565c0")))
    story.append(Spacer(1, 0.3 * cm))

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    dates_str = ", ".join(scene_dates[:3]) if scene_dates else "—"
    mission_data = [
        ["Параметр", "Значение"],
        ["Дата отчёта", now],
        ["Координаты центра", f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.4f}°{'E' if lon >= 0 else 'W'}"],
        ["Анализируемые снимки", dates_str],
        ["Источник данных", "Sentinel-2 L2A · Microsoft Planetary Computer"],
        ["Метод детекции", "FDI (Biermann et al. 2020)"],
    ]

    mission_table = Table(mission_data, colWidths=[6 * cm, W - 6 * cm])
    mission_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), F),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FB),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#e3f2fd")),
        ("FONTNAME", (0, 1), (0, -1), FB),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(mission_table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("📊 Результаты анализа", h1_style))

    plastic_pct = stats.get("plastic_coverage_pct", 0)
    plastic_km2 = stats.get("plastic_area_km2", 0)
    total_km2 = stats.get("total_area_km2", 0)
    cloud_pct = stats.get("cloud_coverage_pct", "?")
    fdi_max = stats.get("fdi_max")
    fdi_mean = stats.get("fdi_mean")
    fdi_p95 = stats.get("fdi_p95")

    verdict = "⚠️ ОБНАРУЖЕНЫ СКОПЛЕНИЯ ПЛАСТИКА" if plastic_pct > 0.01 else "✅ СКОПЛЕНИЯ НЕ ОБНАРУЖЕНЫ"
    verdict_color = colors.HexColor("#c62828") if plastic_pct > 0.01 else colors.HexColor("#2e7d32")

    verdict_style = ParagraphStyle(
        "Verdict", parent=styles["Normal"],
        fontSize=12, fontName=FB,
        textColor=verdict_color, alignment=TA_CENTER,
        spaceAfter=8, spaceBefore=4,
    )
    story.append(Paragraph(verdict, verdict_style))

    stats_data = [
        ["Показатель", "Значение", "Примечание"],
        ["Покрытие пластиком", f"{plastic_pct:.4f}%", "% от анализируемой площади"],
        ["Площадь пластика", f"{plastic_km2:.2f} км²", "FDI > порог + вода + без водорослей"],
        ["Общая площадь анализа", f"{total_km2:.1f} км²", "Без облачных пикселей"],
        ["FDI максимальный", f"{fdi_max:.5f}" if fdi_max else "—", "Пиковое значение индекса"],
        ["FDI средний", f"{fdi_mean:.5f}" if fdi_mean else "—", "По воде"],
        ["FDI 95й перцентиль", f"{fdi_p95:.5f}" if fdi_p95 else "—", ""],
        ["Облачность (композит)", f"{cloud_pct}%", "Доля облачных пикселей"],
    ]
    conf_mean = stats.get("confidence_mean")
    conf_max = stats.get("confidence_max")
    fdi_thresh = stats.get("fdi_threshold_used")
    if fdi_thresh is not None:
        stats_data.append(["Порог FDI", f"{fdi_thresh:.5f}", "Адаптивный (Otsu)"])
    if conf_mean is not None:
        stats_data.append(["Средняя уверенность", f"{conf_mean:.1%}", "По пластиковым пикселям"])
    if conf_max is not None:
        stats_data.append(["Макс. уверенность", f"{conf_max:.1%}", ""])

    stats_table = Table(stats_data, colWidths=[5.5 * cm, 3.5 * cm, W - 9 * cm])
    stats_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), F),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FB),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#e3f2fd")),
        ("FONTNAME", (0, 1), (0, -1), FB),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 0.5 * cm))

    if png_bytes:
        story.append(Paragraph("🗺️ Карта FDI и детекции пластика", h1_style))
        img = RLImage(io.BytesIO(png_bytes), width=W, height=W * 0.45)
        story.append(img)
        story.append(Paragraph(
            "Слева: тепловая карта FDI (синий→жёлтый→красный). "
            "Справа: бинарная маска пластика (красный = обнаружен пластик).",
            caption_style
        ))
        story.append(Spacer(1, 0.4 * cm))

    if fdi is not None and fdi.size > 0:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker

            fdi_flat = fdi.ravel()
            fdi_flat = fdi_flat[np.isfinite(fdi_flat)]
            fdi_thresh = stats.get("fdi_threshold_used")

            fig, ax = plt.subplots(figsize=(7, 2.8))
            fig.patch.set_facecolor("#0a1628")
            ax.set_facecolor("#0a1628")

            ax.hist(
                fdi_flat, bins=80, color="#1976d2", alpha=0.85,
                edgecolor="none", linewidth=0,
            )

            if fdi_thresh is not None:
                ax.axvline(
                    fdi_thresh, color="#ef5350", linewidth=1.5,
                    linestyle="--", label=f"Порог FDI = {fdi_thresh:.4f}",
                )
                ax.legend(
                    fontsize=8, facecolor="#0d1f3c",
                    edgecolor="#1976d2", labelcolor="#e3f2fd",
                )

            ax.set_xlabel("FDI", color="#90caf9", fontsize=9)
            ax.set_ylabel("Пикселей", color="#90caf9", fontsize=9)
            ax.tick_params(colors="#90caf9", labelsize=8)
            for spine in ax.spines.values():
                spine.set_edgecolor("#1565c0")

            fig.tight_layout(pad=0.6)

            hist_buf = io.BytesIO()
            fig.savefig(hist_buf, format="png", dpi=120, facecolor="#0a1628")
            plt.close(fig)
            hist_buf.seek(0)

            hist_img_height = W * 0.4
            story.append(Paragraph("📈 Распределение значений FDI", h1_style))
            story.append(RLImage(hist_buf, width=W, height=hist_img_height))
            story.append(Paragraph("Распределение значений FDI", caption_style))
            story.append(Spacer(1, 0.4 * cm))
        except Exception as e:
            logger.warning(f"Could not generate FDI histogram: {e}")

    if hotspots:
        story.append(Paragraph(f"📍 Горячие точки (топ-{min(len(hotspots), 10)})", h1_style))
        hs_data = [["#", "Широта", "Долгота", "FDI макс", "Площадь, км²", "Пикселей"]]
        for i, hs in enumerate(hotspots[:10], 1):
            hs_data.append([
                str(i),
                f"{hs['lat']:.4f}°",
                f"{hs['lon']:.4f}°",
                f"{hs['fdi_max']:.5f}",
                f"{hs['area_km2']:.3f}",
                str(hs['n_pixels']),
            ])
        hs_table = Table(hs_data, colWidths=[1*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
        hs_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), F),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FB),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(hs_table)
        story.append(Spacer(1, 0.4 * cm))

    if drift_result is not None:
        story.append(Paragraph("🌊 Прогноз дрейфа пластика", h1_style))
        dr = drift_result
        synthetic_note = " (синтетическая модель — демо)" if dr.is_synthetic else f" ({dr.source})"

        drift_data = [["Параметр", "Значение"]]
        if dr.positions_24h:
            drift_data.append(["Позиция через 24ч", f"{dr.positions_24h[0]:.4f}°N, {dr.positions_24h[1]:.4f}°E"])
            drift_data.append(["Смещение за 24ч", f"{dr.distance_km_24h:.1f} км"])
        if dr.positions_48h:
            drift_data.append(["Позиция через 48ч", f"{dr.positions_48h[0]:.4f}°N, {dr.positions_48h[1]:.4f}°E"])
            drift_data.append(["Смещение за 48ч", f"{dr.distance_km_48h:.1f} км"])
        drift_data.append(["Скорость течения", f"{dr.current_speed_ms:.3f} м/с"])
        drift_data.append(["Направление течения", f"{dr.current_direction_deg:.0f}°"])
        drift_data.append(["Источник данных", dr.source + synthetic_note])

        drift_table = Table(drift_data, colWidths=[6 * cm, W - 6 * cm])
        drift_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), F),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FB),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#e3f2fd")),
            ("FONTNAME", (0, 1), (0, -1), FB),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(drift_table)
        story.append(Spacer(1, 0.4 * cm))

    if route_result is not None and route_result.waypoints:
        story.append(Paragraph("🧭 Оптимальный маршрут плота", h1_style))
        story.append(Paragraph(
            f"Общее расстояние: {route_result.total_distance_km} км · "
            f"ETA: {route_result.total_eta_hours} ч ({route_result.total_eta_days} дн)",
            body_style
        ))

        route_data = [["WP", "Широта", "Долгота", "Курс, °", "Дист, км", "ETA, ч", "FDI макс"]]
        for wp in route_result.waypoints:
            route_data.append([
                wp.label,
                f"{wp.lat:.4f}°",
                f"{wp.lon:.4f}°",
                f"{wp.bearing_from_prev_deg:.0f}°",
                f"{wp.distance_from_prev_km:.1f}",
                f"{wp.eta_hours:.1f}",
                f"{wp.fdi_max:.4f}",
            ])

        route_table = Table(route_data, colWidths=[1.5*cm, 3*cm, 3*cm, 2*cm, 2.5*cm, 2*cm, 3*cm])
        route_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), F),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FB),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(route_table)
        story.append(Spacer(1, 0.4 * cm))

    story.append(PageBreak())
    story.append(Paragraph("📚 Методология", h1_style))

    methods = [
        ("Спектральный индекс FDI",
         "Floating Debris Index (Biermann et al. 2020) — наиболее валидированный индекс для "
         "обнаружения плавающего пластика в открытом океане. Формула: FDI = B8A − [B6 + (B11−B6) × "
         "(λ8A−λ6)/(λ11−λ6)], где B6=740нм, B8A=865нм, B11=1610нм. Положительный FDI указывает "
         "на плавающий материал с аномальным отражением в NIR."),
        ("Маскировка облаков (SCL)",
         "Используется Scene Classification Layer (SCL) Sentinel-2 L2A для исключения облачных пикселей. "
         "Маскируются классы: 3 (тень от облаков), 8 (облака ср. плотности), 9 (плотные облака), "
         "10 (тонкая дымка), 11 (снег/лёд). Итоговый снимок — медианный композит по нескольким датам."),
        ("Водяная маска (NDWI)",
         "NDWI = (B3−B8)/(B3+B8). Пиксели с NDWI > 0 считаются водой. Это исключает ложные "
         "срабатывания на суше и береговой линии."),
        ("Фильтр водорослей (NDVI)",
         "NDVI = (B8−B4)/(B8+B4). Пиксели с NDVI > 0.15 классифицируются как биологический "
         "мусор (Саргассум, фитопланктон), а не пластик, и исключаются из детекции."),
        ("Данные",
         "Sentinel-2 L2A — мультиспектральные данные ESA (разрешение 10-20м, 13 каналов). "
         "Доступ через Microsoft Planetary Computer (бесплатно, STAC API). Обработка — "
         "на стороне сервера, результат — только готовая карта (~100 КБ PNG)."),
    ]

    for title, text in methods:
        story.append(Paragraph(title, h2_style))
        story.append(Paragraph(text, body_style))

    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#90caf9")))
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                                  textColor=colors.grey, alignment=TA_CENTER, fontName=F)
    story.append(Paragraph(
        f"antihype · Чистый Океан · Экспедиция Фёдора Конюхова · "
        f"Сгенерировано: {now} · Sentinel-2 FDI · Planetary Computer",
        footer_style
    ))

    doc.build(story)
    buf.seek(0)
    pdf_bytes = buf.read()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
