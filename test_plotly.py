import pandas as pd
import numpy as np
import plotly.graph_objects as go
import kaleido

df = pd.DataFrame({"Open": [1,2], "High": [2,3], "Low": [1,2], "Close": [2,3]})
df.index = pd.to_datetime(["2026-05-22 10:00", "2026-05-22 10:05"])

fig = go.Figure(data=[go.Candlestick(x=df.index, open=df.Open, high=df.High, low=df.Low, close=df.Close)])

# Pass Timestamp to tickvals
tick_vals = [df.index[0], df.index[1]]
fig.update_xaxes(type='category', tickvals=tick_vals, ticktext=["A", "B"])

try:
    fig.to_image(format="png", engine="kaleido")
    print("SUCCESS")
except Exception as e:
    print("FAILED:", e)

# Now test with strings for tickvals
fig2 = go.Figure(data=[go.Candlestick(x=df.index, open=df.Open, high=df.High, low=df.Low, close=df.Close)])
tick_vals2 = [str(df.index[0]), str(df.index[1])]
fig2.update_xaxes(type='category', tickvals=tick_vals2, ticktext=["A", "B"])

try:
    fig2.to_image(format="png", engine="kaleido")
    print("SUCCESS 2 (String tickvals)")
except Exception as e:
    print("FAILED 2:", e)

# Now test with strings for everything (x values and tickvals)
fig3 = go.Figure(data=[go.Candlestick(x=df.index.astype(str), open=df.Open, high=df.High, low=df.Low, close=df.Close)])
fig3.update_xaxes(type='category', tickvals=tick_vals2, ticktext=["A", "B"])

try:
    fig3.to_image(format="png", engine="kaleido")
    print("SUCCESS 3 (String everything)")
except Exception as e:
    print("FAILED 3:", e)
