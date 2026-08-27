import streamlit as st
import pandas as pd
import numpy as np
import datetime
import requests
import plotly.graph_objects as go

# 頁面配置
st.set_page_config(page_title="台股黑美人量化選股系統", page_icon="📈", layout="wide")
st.title("📈 台股“黑美人”戰法量化篩選系統")
st.caption("均線回踩 + KD金叉 + BOS爆量突破")

# 側邊欄設定
st.sidebar.header("⚙️ 篩選條件設定")
ma_fast = st.sidebar.number_input("快速均線 (月線 MA)", value=20, min_value=5, max_value=60)
ma_slow = st.sidebar.number_input("慢速均線 (季線 MA)", value=60, min_value=20, max_value=240)
volume_mult = st.sidebar.slider("爆量倍數 (較前日成交量)", min_value=1.1, max_value=3.0, value=1.3, step=0.1)

default_stocks = "2330, 2317, 2454, 2382, 3231, 2308, 2353, 3576, 2408, 5347"
stock_input = st.sidebar.text_area("監控股票代碼 (逗號分隔)", value=default_stocks)

@st.cache_data(ttl=3600)
def fetch_stock_data_http(stock_id):
    """直接透過 HTTP API 抓取数据，避免 FinMind 套件在 Python 3.14 下的 anyio 衝突"""
    start_date = (datetime.date.today() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={stock_id}&start_date={start_date}"
    
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("msg") == "success" and data.get("data"):
            df = pd.DataFrame(data["data"])
            df = df.rename(columns={'date':'Date','open':'Open','max':'High','min':'Low','close':'Close','Trading_Volume':'Volume'})
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            return df
    except Exception:
        pass
    return None

def calculate_indicators(df):
    df['MA_Fast'] = df['Close'].rolling(window=ma_fast).mean()
    df['MA_Slow'] = df['Close'].rolling(window=ma_slow).mean()
    
    # KD 指標 (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = np.where((high_max - low_min) == 0, 0, (df['Close'] - low_min) / (high_max - low_min) * 100)
    
    k_vals, d_vals = [50.0], [50.0]
    for r in rsv[1:]:
        r_val = 50.0 if np.isnan(r) else r
        k = (2/3) * k_vals[-1] + (1/3) * r_val
        d = (2/3) * d_vals[-1] + (1/3) * k
        k_vals.append(k)
        d_vals.append(d)

    df['K'], df['D'] = k_vals, d_vals
    return df

stock_list = [s.strip() for s in stock_input.split(",") if s.strip()]

if st.button("🚀 開始黑美人量化篩選"):
    results = []
    progress = st.progress(0)
    
    for idx, sid in enumerate(stock_list):
        df = fetch_stock_data_http(sid)
        if df is not None and len(df) >= ma_slow:
            df = calculate_indicators(df)
            today, yesterday = df.iloc[-1], df.iloc[-2]
            recent_3 = df.iloc[-3:]

            cond_trend = (today['Close'] > today['MA_Fast']) and (today['MA_Fast'] > today['MA_Slow'])
            cond_retest = any((recent_3['Low'] <= recent_3['MA_Fast'] * 1.015) & (recent_3['Close'] >= recent_3['MA_Fast']))
            cond_kd = (yesterday['K'] < yesterday['D']) and (today['K'] > today['D'])
            cond_vol = today['Volume'] >= (yesterday['Volume'] * volume_mult)

            is_signal = cond_trend and cond_retest and cond_kd and cond_vol
            score = (30 if cond_trend else 0) + (30 if cond_retest else 0) + (20 if cond_kd else 0) + (20 if cond_vol else 0)

            results.append({
                "股票代碼": sid,
                "黑美人信號": "🔥 觸發" if is_signal else "—",
                "綜合評分": score,
                "最新收盤": today['Close'],
                "成交量(張)": int(today['Volume']/1000),
                "均線多頭": "✅" if cond_trend else "❌",
                "回踩月線": "✅" if cond_retest else "❌",
                "KD金叉": "✅" if cond_kd else "❌",
                "爆量突破": "✅" if cond_vol else "❌"
            })
        progress.progress((idx + 1) / len(stock_list))

    if results:
        res_df = pd.DataFrame(results)
        st.subheader("📋 選股結果彙整表")
        st.dataframe(res_df.sort_values(by=["黑美人信號", "綜合評分"], ascending=[False, False]), use_container_width=True)
    else:
        st.error("未能成功取得資料，請檢查網路連線或股票代碼。")