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
    dark_mode: bool = False
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
        tick_vals = [plot_df.index[i] for i in tick_indices]

        if selected_timeframe in ['1wk', '1d']:
            tick_text = [pd.Timestamp(v).strftime('%Y-%m-%d') for v in tick_vals]
        else:
            tick_text = [pd.Timestamp(v).strftime('%m-%d %H:%M') for v in tick_vals]

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
