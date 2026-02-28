"""Static PNG output using matplotlib with adaptive percentile normalization."""
from __future__ import annotations

import io
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

PLASTIC_CMAP = LinearSegmentedColormap.from_list(
    "plastic",
    [(0.00, "#072b6e"),
     (0.40, "#1565c0"),
     (0.60, "#f5f5f5"),
     (0.75, "#ffb300"),
     (0.88, "#e64a19"),
     (1.00, "#b71c1c")],
)


def make_static_png(
    fdi: np.ndarray,
    plastic_mask: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    lat: float,
    lon: float,
    cloud_mask: Optional[np.ndarray] = None,
    stats: Optional[dict] = None,
    scene_dates: Optional[list] = None,
    rgb_composite: Optional[np.ndarray] = None,
    confidence_map: Optional[np.ndarray] = None,
    hotspots: Optional[list] = None,
    output_path: Optional[str] = None,
    dpi: int = 150,
) -> bytes:
    """Generate static PNG map of FDI results. Returns PNG bytes."""
    n_panels = 2
    if rgb_composite is not None:
        n_panels += 1
    if confidence_map is not None:
        n_panels += 1
    fig, axes = plt.subplots(1, n_panels, figsize=(7 * n_panels, 6),
                             facecolor="#0a1628")
    fig.patch.set_facecolor("#0a1628")
    if not isinstance(axes, np.ndarray):
        axes = [axes]
    else:
        axes = list(axes)

    extent = [float(lons.min()), float(lons.max()),
              float(lats.min()), float(lats.max())]

    panel_idx = 0
    if rgb_composite is not None:
        ax0 = axes[panel_idx]
        ax0.set_facecolor("#0a1628")
        ax0.imshow(rgb_composite, extent=extent, origin="upper", aspect="auto")
        ax0.plot(lon, lat, "b^", markersize=8, zorder=5)
        ax0.set_title("True-color RGB (B4/B3/B2)", color="white", fontsize=12, pad=8)
        _style_ax(ax0)
        panel_idx += 1

    ax1 = axes[panel_idx]
    ax1.set_facecolor("#0a1628")

    valid = ~np.isnan(fdi)
    if valid.any():
        fdi_valid = fdi[valid]
        vmin = float(np.percentile(fdi_valid, 2))
        vmax = float(np.percentile(fdi_valid, 98))
        if vmax - vmin < 1e-6:
            vmin -= 0.005
            vmax += 0.005
    else:
        vmin, vmax = -0.02, 0.05

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    im = ax1.imshow(
        fdi,
        cmap=PLASTIC_CMAP,
        norm=norm,
        extent=extent,
        origin="upper",
        aspect="auto",
    )

    if cloud_mask is not None:
        cloud_overlay = np.where(cloud_mask > 0.5, 1.0, np.nan)
        ax1.imshow(
            cloud_overlay,
            cmap=mcolors.ListedColormap(["#808080"]),
            alpha=0.55,
            extent=extent,
            origin="upper",
            aspect="auto",
        )

    ax1.plot(lon, lat, "b^", markersize=8, label="Центр", zorder=5)
    ax1.set_title("Индекс плавающего мусора (FDI)", color="white", fontsize=12, pad=8)
    _style_ax(ax1)

    cbar = fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("FDI", color="white", fontsize=10)
    cbar.ax.yaxis.set_tick_params(color="white", labelsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
    cbar.set_ticks([vmin, (vmin + vmax) / 2, vmax])
    cbar.set_ticklabels([f"{vmin:.4f}\nВода", f"{(vmin+vmax)/2:.4f}\nРиск", f"{vmax:.4f}\nПластик"])

    if hotspots:
        for hs in hotspots[:15]:
            ax1.plot(hs["lon"], hs["lat"], "rx", markersize=8, markeredgewidth=2, zorder=6)

    ax1.legend(loc="upper right", facecolor="#1a2a3a", labelcolor="white", fontsize=9)

    from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
    km_per_deg = 111.32 * np.cos(np.radians(lat))
    extent_km = (lons[-1] - lons[0]) * km_per_deg
    bar_km = round(extent_km / 4, -1)
    if bar_km < 1:
        bar_km = 1
    bar_deg = bar_km / km_per_deg
    scalebar = AnchoredSizeBar(ax1.transData, bar_deg, f'{bar_km:.0f} км', 'lower left',
                                pad=0.5, color='white', frameon=False,
                                size_vertical=0.002, fontproperties={'size': 9})
    ax1.add_artist(scalebar)

    panel_idx += 1

    ax2 = axes[panel_idx]
    ax2.set_facecolor("#0a1628")

    water_bg = np.where(valid, 0.3, np.nan)
    ax2.imshow(
        water_bg,
        cmap=mcolors.ListedColormap(["#0d47a1"]),
        extent=extent,
        origin="upper",
        aspect="auto",
        alpha=0.85,
    )

    if cloud_mask is not None:
        cloud_overlay = np.where(cloud_mask > 0.5, 1.0, np.nan)
        ax2.imshow(
            cloud_overlay,
            cmap=mcolors.ListedColormap(["#757575"]),
            alpha=0.55,
            extent=extent,
            origin="upper",
            aspect="auto",
        )

    plastic_display = np.where(plastic_mask & valid, 1.0, np.nan)
    ax2.imshow(
        plastic_display,
        cmap=mcolors.ListedColormap(["#dc1e1e"]),
        extent=extent,
        origin="upper",
        aspect="auto",
    )

    ax2.plot(lon, lat, "b^", markersize=8, zorder=5)
    ax2.set_title("Детекция пластика (FDI > порог + вода)", color="white", fontsize=12, pad=8)
    _style_ax(ax2)

    legend_elems = [
        Patch(facecolor="#dc1e1e", label="Пластик/мусор"),
        Patch(facecolor="#0d47a1", label="Вода"),
        Patch(facecolor="#757575", label="Облачность"),
    ]
    ax2.legend(handles=legend_elems, loc="upper right",
               facecolor="#1a2a3a", labelcolor="white", fontsize=9)

    if confidence_map is not None:
        panel_idx += 1
        ax_conf = axes[panel_idx]
        ax_conf.set_facecolor("#0a1628")
        conf_norm = mcolors.Normalize(vmin=0.0, vmax=1.0, clip=True)
        im_conf = ax_conf.imshow(
            confidence_map,
            cmap="RdYlGn_r",
            norm=conf_norm,
            extent=extent,
            origin="upper",
            aspect="auto",
        )
        ax_conf.plot(lon, lat, "b^", markersize=8, zorder=5)
        ax_conf.set_title("Карта уверенности", color="white", fontsize=12, pad=8)
        _style_ax(ax_conf)
        cbar_conf = fig.colorbar(im_conf, ax=ax_conf, fraction=0.046, pad=0.04)
        cbar_conf.set_label("Уверенность", color="white", fontsize=10)
        cbar_conf.ax.yaxis.set_tick_params(color="white", labelsize=8)
        plt.setp(cbar_conf.ax.yaxis.get_ticklabels(), color="white")

    plastic_pct = stats.get("plastic_coverage_pct", 0) if stats else 0
    plastic_km2 = stats.get("plastic_area_km2", 0) if stats else 0
    cloud_pct = stats.get("cloud_coverage_pct", "?") if stats else "?"
    fdi_max = stats.get("fdi_max") if stats else None
    dates_str = ", ".join(scene_dates[:2]) if scene_dates else "—"

    fdi_str = f"  |  FDI макс: {fdi_max:.5f}" if fdi_max is not None else ""
    fdi_threshold = stats.get("fdi_threshold_used") if stats else None
    confidence_mean = stats.get("confidence_mean") if stats else None
    thresh_str = f"  |  Порог FDI: {fdi_threshold:.5f}" if fdi_threshold is not None else ""
    conf_str = f"  |  Ср. уверенность: {confidence_mean:.2f}" if confidence_mean is not None else ""
    stats_text = (
        f"Центр: {lat:.4f}°N, {lon:.4f}°E  |  Снимки: {dates_str}  |  "
        f"Покрытие пластиком: {plastic_pct:.3f}%  |  Площадь: {plastic_km2:.2f} км²  |  "
        f"Облачность: {cloud_pct}%{fdi_str}{thresh_str}{conf_str}"
    )
    fig.text(0.5, 0.01, stats_text, ha="center", va="bottom",
             color="#90a4ae", fontsize=9, transform=fig.transFigure)

    verdict = "⚠  Обнаружены скопления пластика" if plastic_pct > 0.01 else "✓  Зона чистая"
    verdict_color = "#ef5350" if plastic_pct > 0.01 else "#66bb6a"
    fig.suptitle(
        f"antihype · Карта пластика — Sentinel-2 FDI\n"
        f"{verdict}",
        color=verdict_color, fontsize=13, fontweight="bold", y=1.02,
    )

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    png_bytes = buf.read()
    plt.close(fig)

    if output_path:
        with open(output_path, "wb") as f:
            f.write(png_bytes)

    return png_bytes


def _style_ax(ax):
    ax.set_xlabel("Долгота", color="#90a4ae", fontsize=9)
    ax.set_ylabel("Широта", color="#90a4ae", fontsize=9)
    ax.tick_params(colors="#90a4ae", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#37474f")
