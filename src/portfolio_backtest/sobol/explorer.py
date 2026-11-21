"""Interactive volatility vs CAGR chart of a Sobol study.

- One dot per Sobol portfolio, coloured by CAGR / volatility (jet: blue = low, red = high).
- Grey diamonds: 100 % in one ETF, labelled with its ticker. White diamond: the reference mix (--mix).
  Circles: the notable portfolios.
- Click a dot to show or hide its allocation.
- Right-hand strip: one filter per ETF (tick box + min-max slider); only portfolios matching ALL
  ticked filters stay visible. Reset switches every filter off.
- "Custom mix" Qt side panel (Qt backend only): type other weights, "Plot" shows that mix as a
  black diamond, "Back to reference" removes it.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from matplotlib.widgets import Button, CheckButtons, RangeSlider

from ..engine import perform_backtest
from ..etfs import ETFS
from ..plotting import use_style
from .study import SobolStudy

LABEL_BOX = dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85)  # readable over the dots
CLICK_RADIUS_PX = 6


class SobolExplorer:
    def __init__(self, study: SobolStudy, my_mix: dict[str, float], invest: float, start: str | None,
                 end: str | None, rebalance: str, filters: dict[str, tuple[float, float]] | None = None,
                 prices: pd.DataFrame | None = None):
        self.study = study
        self.my_mix = dict(my_mix)
        self.bt_args = dict(invest=invest, start=start, end=end, rebalance=rebalance, prices=prices)
        self.rebalance = rebalance
        self.initial_filters = filters or {}

        r = study.result
        self.n = study.n_samples
        self.vol, self.cagr, self.ratio = r.volatility, r.cagr, study.ratio
        self.visible = np.ones(len(study.allocs), bool)  # the diamonds are always visible
        self.labels: dict[int, object] = {}               # portfolio index -> click label

        use_style()
        self.fig, self.ax = plt.subplots(figsize=(13.5, 7.5))
        # chart in the left 70 %, then the colour bar, then the filter strip (from x = 0.77)
        self.fig.subplots_adjust(left=0.06, right=0.70, bottom=0.08, top=0.90)
        self._draw_chart()
        self._build_filters()
        self._attach_qt_panel()

        for c in study.etfs:
            self.checks[c].on_clicked(self.update_filter)
            self.sliders[c].on_changed(self.update_filter)
        self.reset_btn.on_clicked(self.reset)
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.update_filter()
        self.plot_mix(list(self.my_mix.values()))

    # ------------------------------------------------------------------ chart --
    def _backtest_mix(self, weights):
        r = perform_backtest(etfs=list(self.my_mix), allocs=[weights], **self.bt_args)
        return r.volatility[0], r.cagr[0]

    def _draw_chart(self) -> None:
        ax, n, s = self.ax, self.n, self.study
        vol, cagr, ratio = self.vol, self.cagr, self.ratio

        self.cloud = ax.scatter(vol[:n], cagr[:n], c=ratio[:n], cmap="jet", s=26, alpha=0.7,
                                edgecolors="black", linewidths=0.3, zorder=2, label=f"Sobol portfolios ({n:,})", rasterized=True)
        self.cloud.set_clim(ratio[:n].min(), ratio[:n].max())  # fixed scale, so filtering keeps the colours
        self.fig.colorbar(self.cloud, cax=self.fig.add_axes([0.708, 0.08, 0.012, 0.82]), label="CAGR / volatility")

        ax.scatter(vol[s.singles], cagr[s.singles], marker="D", s=70, color="#9e9e9e", edgecolors="black",
                   linewidths=0.8, zorder=4, label="100% in one ETF")
        for i in s.singles:
            ax.annotate(ETFS[s.etfs[i - n]].label, (vol[i], cagr[i]), xytext=(8, -3),
                        textcoords="offset points", fontsize=8.5)

        x, y = self._backtest_mix(list(self.my_mix.values()))
        ax.scatter(x, y, marker="D", s=120, color="white", edgecolor="black", lw=1.4, zorder=6,
                   label="Reference mix")
        ax.annotate(f"Reference mix\nCAGR {y:.1%} | Vol {x:.1%}", (x, y), xytext=(10, -12),
                    textcoords="offset points", va="top", fontsize=9, fontweight="bold", zorder=7, bbox=LABEL_BOX)

        self.my_star = ax.scatter([], [], marker="D", s=120, color="black", edgecolor="white", lw=1.2, zorder=6,
                                  label="Edited mix")
        self.my_label = ax.annotate("", (0, 0), xytext=(10, 14), textcoords="offset points", va="bottom",
                                    fontsize=9, fontweight="bold", zorder=7, bbox=LABEL_BOX)

        picks = s.picks()
        for i in picks.values():  # red circles around the notable portfolios
            ax.scatter(vol[i], cagr[i], marker="o", s=110, facecolor="none", edgecolor="red", lw=1.6, zorder=5)

        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi + 0.10 * (hi - lo))  # room on the right for the diamond labels

        # labels of the notable portfolios, on two lines, placed after the limits are final so they can be
        # kept inside the axes: to the right of the circle near the left edge, below it near the top
        two_lines = {"Highest CAGR": "Highest\nCAGR", "Lowest volatility": "Lowest\nvolatility",
                     "Best CAGR / volatility": "Best CAGR /\nvolatility"}
        for name, i in picks.items():
            fx, fy = ax.transAxes.inverted().transform(ax.transData.transform((vol[i], cagr[i])))
            dx, ha = (10, "left") if fx < 0.25 else (-10, "right")
            dy, va = (-10, "top") if fy > 0.85 else (10, "bottom")
            ax.annotate(two_lines.get(name, name), (vol[i], cagr[i]), xytext=(dx, dy), textcoords="offset points",
                        ha=ha, va=va, multialignment=ha, fontsize=8.5, color="red", zorder=7, bbox=LABEL_BOX)
        ax.set_xlabel("Volatility (annualised)")
        ax.set_ylabel("CAGR")
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
        d = s.result.dates
        ax.set_title(f"Sobol study: {n:,} allocations, {d[0]:%b %Y} - {d[-1]:%b %Y}, {self.rebalance} rebalancing\n"
                     "Click a point to show its allocation in %:  " + " / ".join(ETFS[c].label for c in s.etfs),
                     fontsize=11)
        ax.legend(loc="lower right", fontsize=8.5)
        ax.grid(True, color="#dddddd", lw=0.6)

    # ---------------------------------------------------------------- filters --
    def _build_filters(self) -> None:
        fig, etfs = self.fig, self.study.etfs
        fig.text(0.775, 0.885, "Filter portfolios", fontsize=11, fontweight="bold")
        fig.text(0.775, 0.862, "show only those matching ALL ticked filters (weight in %)", fontsize=8, color="#555555")
        self.checks, self.sliders = {}, {}
        row_h, top = 0.062, 0.80  # in figure fractions
        for k, c in enumerate(etfs):
            y = top - k * row_h
            cax = fig.add_axes([0.770, y, 0.075, 0.045])
            cax.set_frame_on(False)
            self.checks[c] = CheckButtons(cax, [ETFS[c].label], [c in self.initial_filters],
                                          frame_props={"edgecolor": "black"}, check_props={"facecolor": "red"})
            self.checks[c].labels[0].set_fontsize(9)
            self.sliders[c] = RangeSlider(fig.add_axes([0.850, y + 0.012, 0.085, 0.022]), "", 0, 100,
                                          valinit=self.initial_filters.get(c, (0, 100)), valstep=1, color="red")
            self.sliders[c].valtext.set_fontsize(8.5)
        bottom = top - len(etfs) * row_h
        self.reset_btn = Button(fig.add_axes([0.775, bottom - 0.005, 0.07, 0.04]), "Reset",
                                color="#eeeeee", hovercolor="#ffcccc")
        self.count_text = fig.text(0.775, bottom - 0.06, "", fontsize=9, va="top")

    def update_filter(self, *_) -> None:
        """Recompute which Sobol points stay visible (called on every tick-box click and slider move)."""
        n, allocs = self.n, self.study.allocs
        keep = np.ones(n, bool)
        active = []
        for j, c in enumerate(self.study.etfs):
            lo, hi = self.sliders[c].val
            rng = f"{lo:g}%" if lo == hi else f"{lo:g}-{hi:g}%"
            self.sliders[c].valtext.set_text(rng)
            if self.checks[c].get_status()[0]:
                keep &= (allocs[:n, j] >= lo) & (allocs[:n, j] <= hi)
                active.append(f"{ETFS[c].label} {rng}")
        self.cloud.set_offsets(np.column_stack([self.vol[:n][keep], self.cagr[:n][keep]]))
        self.cloud.set_array(self.ratio[:n][keep])
        self.visible[:n] = keep
        for i in [i for i in self.labels if not self.visible[i]]:  # drop labels of hidden points
            self.labels.pop(i).remove()
        self.count_text.set_text(f"{keep.sum():,} of {n:,} portfolios shown\nwith " + "\nand ".join(active)
                                 if active else f"No filter active\nall {n:,} portfolios shown")
        self.fig.canvas.draw_idle()

    def reset(self, _=None) -> None:
        for c in self.study.etfs:
            if self.checks[c].get_status()[0]:
                self.checks[c].set_active(0)  # set_active toggles, so only on ticked boxes
            self.sliders[c].set_val((0, 100))
        self.update_filter()

    # ------------------------------------------------------------------ click --
    def on_click(self, event) -> None:
        ax, fig = self.ax, self.fig
        toolbar = fig.canvas.toolbar
        if event.inaxes is not ax or event.button != 1 or (toolbar and toolbar.mode):
            return
        xy = ax.transData.transform(np.column_stack([self.vol, self.cagr]))
        d = np.hypot(xy[:, 0] - event.x, xy[:, 1] - event.y)
        d[~self.visible] = np.inf
        i = int(d.argmin())
        if d[i] > CLICK_RADIUS_PX:
            return
        if i in self.labels:
            self.labels.pop(i).remove()
        else:
            v, g, rt = self.vol[i], self.cagr[i], self.ratio[i]
            fx, fy = ax.transAxes.inverted().transform(ax.transData.transform((v, g)))
            dx, ha = (-12, "right") if fx > 0.7 else (12, "left")   # keep the label inside the axes
            dy, va = (-12, "top") if fy > 0.85 else (12, "bottom")
            self.labels[i] = ax.annotate(
                " ".join(f"{x:.0f}" for x in self.study.allocs[i]) + f"\nCAGR {g:.1%} | Vol {v:.1%} | Ratio {rt:.2f}",
                (v, g), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, multialignment="left",
                fontsize=8.5, family="monospace", zorder=10,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=0.8, alpha=0.95),
                arrowprops=dict(arrowstyle="-", color="black", lw=0.8))
        fig.canvas.draw_idle()

    # ----------------------------------------------------------- edited mix --
    def plot_mix(self, weights) -> None:
        """Black diamond at the mix ``weights`` (% in my_mix order); hidden when it equals the reference mix."""
        edited = list(weights) != list(self.my_mix.values())
        if edited:
            x, y = self._backtest_mix(list(weights))
            self.my_star.set_offsets([[x, y]])
            self.my_label.xy = (x, y)
            self.my_label.set_text(f"Edited mix\nCAGR {y:.1%} | Vol {x:.1%}")
        else:
            self.my_star.set_offsets(np.empty((0, 2)))
        self.my_label.set_visible(edited)
        self.fig.canvas.draw_idle()

    def _attach_qt_panel(self) -> None:
        """Native Qt side panel for typing weights; skipped with a non-Qt backend."""
        window = getattr(self.fig.canvas.manager, "window", None)
        try:
            from matplotlib.backends.qt_compat import QtCore, QtWidgets
        except ImportError:
            return
        if not isinstance(window, QtWidgets.QMainWindow):
            return

        codes = list(self.my_mix)
        panel = QtWidgets.QWidget()
        panel.setFixedWidth(320)
        form = QtWidgets.QFormLayout(panel)
        form.addRow(QtWidgets.QLabel("Weights in %; Plot is active when the sum is 100."))
        spins = {}
        for c in codes:
            spins[c] = QtWidgets.QDoubleSpinBox(decimals=1, minimum=0, maximum=100, singleStep=1, suffix=" %")
            spins[c].setValue(self.my_mix[c])
            form.addRow(f"{c}  ({ETFS[c].name})".replace("&", "&&"), spins[c])  # && shows a literal & in Qt
        sum_label = QtWidgets.QLabel()
        form.addRow("Sum", sum_label)
        plot_btn = QtWidgets.QPushButton("Plot")
        back_btn = QtWidgets.QPushButton("Back to reference")
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(plot_btn)
        buttons.addWidget(back_btn)
        form.addRow(buttons)

        weights = lambda: [spins[c].value() for c in codes]  # noqa: E731

        def update_sum():
            total = sum(weights())
            ok = abs(total - 100) < 0.05
            sum_label.setText(f"{total:g} %")
            sum_label.setStyleSheet("color: green; font-weight: bold" if ok else "color: red; font-weight: bold")
            plot_btn.setEnabled(ok)

        def back():
            for c in codes:
                spins[c].setValue(self.my_mix[c])
            self.plot_mix(weights())

        for c in codes:
            spins[c].valueChanged.connect(update_sum)
        plot_btn.clicked.connect(lambda: self.plot_mix(weights()))
        back_btn.clicked.connect(back)
        update_sum()

        dock = QtWidgets.QDockWidget("Custom mix", window)
        dock.setWidget(panel)
        window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        window.resize(window.width() + panel.width(), window.height())  # chart keeps its size
        self._qt_refs = (panel, dock, spins)  # keep the widgets alive
