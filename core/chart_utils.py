import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def generate_trade_chart(
    df_chart: pd.DataFrame, 
    selected_asset_name: str, 
    selected_timeframe: str, 
    ema_fast: int, 
    ema_slow: int, 
    last_high: float = np.nan, 
    last_low: float = np.nan,
    dark_mode: bool = False,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    signal_side: str = "",
) -> go.Figure:
    """
    Generates a standardized Plotly Candlestick chart used across the UI and automated alerts.
    """
    fig_merge = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.02,
        row_heights=[0.75, 0.25]
    )

    plot_df = df_chart.copy() if not df_chart.empty else df_chart

    if not plot_df.empty:
        plot_df.index = pd.to_datetime(plot_df.index, errors="coerce")
        # Standardize column names dynamically based on what's available
        o_col = 'Open' if 'Open' in plot_df else 'open'
        h_col = 'High' if 'High' in plot_df else 'high'
        l_col = 'Low' if 'Low' in plot_df else 'low'
        c_col = 'Close' if 'Close' in plot_df else 'close'

        # Compute hover text
        plot_df['CandleChgPct'] = ((plot_df[c_col] - plot_df[o_col]) / plot_df[o_col]) * 100
        hover_text_series = (
            "Date: "          + plot_df.index.strftime('%b %d %H:%M') + "<br>" +
            "Open: "          + plot_df[o_col].map('{:.2f}'.format)  + "<br>" +
            "High: "          + plot_df[h_col].map('{:.2f}'.format)  + "<br>" +
            "Low: "           + plot_df[l_col].map('{:.2f}'.format)   + "<br>" +
            "Close: "         + plot_df[c_col].map('{:.2f}'.format) + "<br>" +
            "Candle Change: " + plot_df['CandleChgPct'].map('{:.2f}%'.format)
        )
        plot_df['HoverText'] = hover_text_series

        fig_merge.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df[o_col],
            high=plot_df[h_col],
            low=plot_df[l_col],
            close=plot_df[c_col],
            name='Price',
            increasing_line_color='#00FF00',
            decreasing_line_color='#FF0000',
            text=plot_df['HoverText'],
            hoverinfo='text'
        ), row=1, col=1)

    # ── EMAs ──
    fast_ema_col = 'fast_ema' if 'fast_ema' in plot_df.columns else 'EMA_fast' if 'EMA_fast' in plot_df.columns else None
    if fast_ema_col:
        fig_merge.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df[fast_ema_col],
            mode='lines', name=f'Fast EMA ({ema_fast})',
            line=dict(color='purple', width=1)
        ), row=1, col=1)

    slow_ema_col = 'slow_ema' if 'slow_ema' in plot_df.columns else 'EMA_slow' if 'EMA_slow' in plot_df.columns else None
    if slow_ema_col:
        fig_merge.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df[slow_ema_col],
            mode='lines', name=f'Slow EMA ({ema_slow})',
            line=dict(color='white', width=1)
        ), row=1, col=1)

    # ── Fractal High / Low horizontal lines ──
    if pd.notna(last_high):
        fig_merge.add_hline(
            y=last_high, line_dash="dot", line_color="rgba(16,185,129,0.5)", line_width=1,
            annotation_text=f"High {last_high:,.2f}",
            annotation_font_color="#10b981", annotation_position="right",
            row=1, col=1
        )
    if pd.notna(last_low):
        fig_merge.add_hline(
            y=last_low, line_dash="dot", line_color="rgba(239,68,68,0.5)", line_width=1,
            annotation_text=f"Low {last_low:,.2f}",
            annotation_font_color="#ef4444", annotation_position="right",
            row=1, col=1
        )

    if entry_price is not None and not (isinstance(entry_price, float) and np.isnan(entry_price)) and entry_price > 0:
        fig_merge.add_hline(
            y=float(entry_price), line_dash="solid", line_color="#fbbf24", line_width=1.5,
            annotation_text=f"Entry {entry_price:,.2f}",
            annotation_font_color="#fbbf24", annotation_position="right",
            row=1, col=1,
        )
    if stop_loss is not None and not (isinstance(stop_loss, float) and np.isnan(stop_loss)) and stop_loss > 0:
        fig_merge.add_hline(
            y=float(stop_loss), line_dash="dash", line_color="#ef4444", line_width=1.5,
            annotation_text=f"SL {stop_loss:,.2f}",
            annotation_font_color="#ef4444", annotation_position="left",
            row=1, col=1,
        )
    if take_profit is not None and not (isinstance(take_profit, float) and np.isnan(take_profit)) and take_profit > 0:
        fig_merge.add_hline(
            y=float(take_profit), line_dash="dash", line_color="#22c55e", line_width=1.5,
            annotation_text=f"TP {take_profit:,.2f}",
            annotation_font_color="#22c55e", annotation_position="left",
            row=1, col=1,
        )

    # ── BUY / SELL SIGNALS ──
    if 'Signal_Vis' in plot_df.columns and not plot_df.empty:
        l_col = 'Low' if 'Low' in plot_df else 'low'
        h_col = 'High' if 'High' in plot_df else 'high'
        
        buy_signals  = plot_df[plot_df['Signal_Vis'] == 'BUY']
        sell_signals = plot_df[plot_df['Signal_Vis'] == 'SELL']

        if not buy_signals.empty:
            fig_merge.add_trace(go.Scatter(
                x=buy_signals.index,
                y=buy_signals[l_col] * 0.999,
                mode='markers+text',
                name='BUY Signal',
                marker=dict(symbol='triangle-up', color='#00FF00', size=14),
                text='BUY',
                textposition='bottom center',
                textfont=dict(color='#00FF00')
            ), row=1, col=1)

        if not sell_signals.empty:
            fig_merge.add_trace(go.Scatter(
                x=sell_signals.index,
                y=sell_signals[h_col] * 1.001,
                mode='markers+text',
                name='SELL Signal',
                marker=dict(symbol='triangle-down', color='#FF0000', size=14),
                text='SELL',
                textposition='top center',
                textfont=dict(color='#FF0000')
            ), row=1, col=1)

    # ── Custom Ticks for Category Axis (to hide gaps) ──
    if len(plot_df) > 0:
        tick_indices = np.linspace(0, len(plot_df) - 1, num=10, dtype=int)
        tick_vals_raw = [plot_df.index[i] for i in tick_indices]
        tick_vals = [str(v) for v in tick_vals_raw]

        if selected_timeframe in ['1wk', '1d']:
            tick_text = [pd.Timestamp(v).strftime('%Y-%m-%d') for v in tick_vals_raw]
        else:
            tick_text = [pd.Timestamp(v).strftime('%m-%d %H:%M') for v in tick_vals_raw]

        xaxis_config = dict(
            type='category',
            showgrid=False,
            rangeslider=dict(visible=False),
            tickmode='array',
            tickvals=tick_vals,
            ticktext=tick_text
        )
    else:
        xaxis_config = dict(showgrid=False, rangeslider=dict(visible=False))

    # ── VOLUME CHART TRACES ──
    v_col = 'Volume' if 'Volume' in plot_df else 'volume'
    if v_col in plot_df.columns and not plot_df.empty:
        fig_merge.add_trace(go.Bar(
            x=plot_df.index, y=plot_df[v_col],
            name='Volume',
            marker_color='#3E3454'
        ), row=2, col=1)

    if 'Vol_MA' in plot_df.columns and not plot_df.empty:
        fig_merge.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['Vol_MA'],
            mode='lines', name='Vol MA',
            line=dict(color='#D460E6', width=1, dash='dot')
        ), row=2, col=1)

    bg_color = 'rgba(0,0,0,0)' if not dark_mode else '#0a0e1a'
    margins = dict(l=0, r=0, t=50, b=0) if not dark_mode else dict(l=20, r=20, t=60, b=20)

    fig_merge.update_layout(
        title=dict(
            text=f"{selected_asset_name} — Dow Theory {selected_timeframe}",
            font=dict(size=24, color='#E0E0E0')
        ),
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        font=dict(color='#A090BC'),
        height=650,
        width=900 if dark_mode else None, # Fixed width for snapshot exports only
        margin=margins,
        legend=dict(orientation="h", y=1.02, x=0, bgcolor='rgba(0,0,0,0)'),
        showlegend=False,
        dragmode='pan'
    )

    # ── Apply common axis settings ──
    fig_merge.update_xaxes(**xaxis_config, row=1, col=1)
    fig_merge.update_xaxes(**xaxis_config, row=2, col=1)

    fig_merge.update_yaxes(showgrid=True, gridcolor='#2D2638', row=1, col=1)
    fig_merge.update_yaxes(showgrid=False, row=2, col=1)

    return fig_merge


def _resolve_ema_columns(plot_df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Match EMA columns regardless of naming (EMA_Fast, fast_ema, etc.)."""
    fast = slow = None
    for c in plot_df.columns:
        cl = str(c).lower().replace(" ", "")
        if cl in ("ema_fast", "fast_ema", "ema_short"):
            fast = c
        if cl in ("ema_slow", "slow_ema", "ema_long"):
            slow = c
    return fast, slow


def _draw_trade_levels(
    ax,
    *,
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    side: str = "",
) -> None:
    """Overlay entry / SL / TP on mplfinance price axis with right-side labels."""
    levels: list[tuple[float, str, str, str]] = []
    if entry is not None and not (isinstance(entry, float) and np.isnan(entry)) and entry > 0:
        levels.append((float(entry), "#fbbf24", "-", f"Entry {entry:,.2f}"))
    if stop_loss is not None and not (isinstance(stop_loss, float) and np.isnan(stop_loss)) and stop_loss > 0:
        levels.append((float(stop_loss), "#ef4444", "--", f"SL {stop_loss:,.2f}"))
    if take_profit is not None and not (isinstance(take_profit, float) and np.isnan(take_profit)) and take_profit > 0:
        levels.append((float(take_profit), "#22c55e", "--", f"TP {take_profit:,.2f}"))

    if not levels:
        return

    x_right = ax.get_xlim()[1]
    for y, color, ls, label in levels:
        ax.axhline(
            y,
            color=color,
            linestyle=ls,
            linewidth=2.0 if "Entry" in label else 1.6,
            alpha=0.92,
            zorder=6,
        )
        ax.annotate(
            label,
            xy=(x_right, y),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=8,
            color=color,
            fontweight="bold",
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="#0f172a",
                edgecolor=color,
                alpha=0.92,
            ),
            zorder=7,
        )

    if side in ("BUY", "SELL"):
        ax.set_title(
            (ax.get_title() or "") + f"  |  {side}",
            fontsize=11,
            color="#e2e8f0",
        )


def generate_static_trade_chart(
    df_chart: pd.DataFrame,
    selected_asset_name: str,
    selected_timeframe: str,
    ema_fast: int,
    ema_slow: int,
    last_high: float = np.nan,
    last_low: float = np.nan,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    signal_side: str = "",
) -> bytes:
    """
    Generates a static, high-res PNG byte stream using mplfinance.
    This runs entirely in-memory using the 'agg' backend, avoiding heavy
    Chromium/Plotly browser dependencies for background Telegram notifications.
    """
    import mplfinance as mpf
    import io

    if df_chart is None or df_chart.empty:
        return None

    plot_df = df_chart.copy()
    plot_df.index = pd.to_datetime(plot_df.index, errors="coerce")

    # Add breathing room on the right side of the chart (8 empty candles)
    if len(plot_df) > 1:
        time_diff = plot_df.index[-1] - plot_df.index[-2]
        pad_idx = [plot_df.index[-1] + time_diff * i for i in range(1, 9)]
        pad_df = pd.DataFrame(index=pad_idx, columns=plot_df.columns)
        plot_df = pd.concat([plot_df, pad_df])

    # mplfinance requires specific column names: Open, High, Low, Close, Volume
    plot_df.rename(columns=lambda x: x.capitalize() if x.lower() != 'volume' else 'Volume', inplace=True)

    # 1. Custom Style (Premium Dark Theme)
    mc = mpf.make_marketcolors(
        up='#10b981', down='#ef4444',     # Tailwind Emerald and Red
        edge='inherit', wick='inherit',
        volume='#1e293b', ohlc='inherit'
    )
    s = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='#1e293b',              # Subtle grid lines
        facecolor='#0f172a',              # Deep slate background
        edgecolor='#334155',              # Axis edge colors
        figcolor='#0f172a',               # Outer background
        rc={'text.color': '#94a3b8', 'axes.labelcolor': '#94a3b8', 'xtick.color': '#64748b', 'ytick.color': '#64748b'}
    )

    # 2. Addplots (EMAs, Markers)
    ap = []

    # EMAs
    fast_col, slow_col = _resolve_ema_columns(plot_df)
    if fast_col:
        ap.append(mpf.make_addplot(plot_df[fast_col], color='#c084fc', width=1.2))
    if slow_col:
        ap.append(mpf.make_addplot(plot_df[slow_col], color='#38bdf8', width=1.2))

    # BUY/SELL Markers (column name varies after capitalize)
    sig_col = None
    for c in plot_df.columns:
        if str(c).lower() == "signal_vis":
            sig_col = c
            break
    if sig_col:
        buy_signals = np.where(plot_df[sig_col] == 'BUY', plot_df['Low'] * 0.9995, np.nan)
        sell_signals = np.where(plot_df[sig_col] == 'SELL', plot_df['High'] * 1.0005, np.nan)
        
        if not np.isnan(buy_signals).all():
            ap.append(mpf.make_addplot(buy_signals, type='scatter', markersize=80, marker='^', color='#10b981'))
        if not np.isnan(sell_signals).all():
            ap.append(mpf.make_addplot(sell_signals, type='scatter', markersize=80, marker='v', color='#ef4444'))

    # Structural Lines (last_high, last_low)
    hlines = dict(hlines=[], colors=[], linestyle='--')
    if pd.notna(last_high):
        hlines['hlines'].append(last_high)
        hlines['colors'].append('#10b981') # Green dashed
    if pd.notna(last_low):
        hlines['hlines'].append(last_low)
        hlines['colors'].append('#ef4444') # Red dashed
    
    # 3. Render
    buf = io.BytesIO()
    
    kwargs = dict(
        type='candle',
        style=s,
        addplot=ap,
        volume=True if 'Volume' in plot_df.columns else False,
        title=f"{selected_asset_name} — {selected_timeframe}",
        figsize=(10, 6),
        tight_layout=True,
        savefig=dict(fname=buf, dpi=150, format='png', bbox_inches='tight'),
        returnfig=True
    )
    
    if hlines['hlines']:
        kwargs['hlines'] = hlines

    # Explicitly use non-interactive backend
    import matplotlib
    matplotlib.use('Agg')
    
    fig, axlist = mpf.plot(plot_df, **kwargs)

    if axlist is not None and len(axlist) > 0:
        _draw_trade_levels(
            axlist[0],
            entry=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            side=signal_side,
        )

    # Cleanup memory
    import matplotlib.pyplot as plt
    plt.close(fig)
    
    buf.seek(0)
    return buf.getvalue()

