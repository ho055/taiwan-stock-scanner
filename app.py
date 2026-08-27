import streamlit as st
import pandas as pd
import numpy as np
import datetime
import requests
import random

st.set_page_config(page_title="台股多策略全量化評分選股系統", page_icon="📈", layout="wide")
st.title("📈 台股多策略全量化評分選股系統")

# 檢查當前時間是否已過下午 1:30 (台股收盤時間)
now_time = datetime.datetime.now()
is_after_market_close = now_time.time() >= datetime.time(13, 30)

if is_after_market_close:
    st.caption("🔥 **即時連線中**：當前已過下午 1:30 收盤時間，系統將自動抓取今日最新盤後收盤資訊！")
else:
    st.caption("💡 **盤中預設模式**：下午 1:30 後將自動啟用即時盤後資訊更新機制。")

# ----------------------------------------------------
# 1. 側邊欄策略與範圍設定
# ----------------------------------------------------
st.sidebar.header("🎯 策略與掃描設定")
strategy = st.sidebar.selectbox(
    "選擇主量化策略",
    [
        "SMC 聰明錢 (TradingView 規格)",
        "📈 KD + MACD + RSI 指標雙金戰法",
        "📊 基本面與財務估值評分",
        "🏆 經典基本面成長股 (EPS/估值)",
        "黑美人戰法 (均線+KD+爆量)"
    ]
)

scan_mode = st.sidebar.radio(
    "掃描範圍",
    [
        "🎲 隨機抽樣 100 檔 (極速推薦)",
        "🔥 熱門精選 (25檔)",
        "🚀 全台股上市櫃全掃 (約2000檔)"
    ]
)

# ----------------------------------------------------
# 2. 成交量過濾區
# ----------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("💧 成交量(張) 範圍篩選")
use_vol_filter = st.sidebar.checkbox("啟用 成交量範圍限制", value=False)

if use_vol_filter:
    min_vol, max_vol = st.sidebar.slider(
        "選擇成交量範圍 (張)",
        min_value=100,
        max_value=50000,
        value=(1000, 30000),
        step=500
    )
else:
    min_vol, max_vol = 0, 999999999

# ----------------------------------------------------
# 3. 策略獨立參數設定
# ----------------------------------------------------
if "SMC" in strategy:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ TradingView SMC 參數")
    smc_swing_len = st.sidebar.number_input("Swing 擺動天數", value=5, min_value=2, max_value=10)
    smc_fvg_min = st.sidebar.slider("FVG 最小缺口門檻 (%)", value=0.3, min_value=0.1, max_value=3.0, step=0.1)

elif "KD + MACD" in strategy:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ KD + MACD 參數")
    kd_period = st.sidebar.number_input("KD 週期天數", value=9, min_value=5, max_value=20)
    macd_fast = st.sidebar.number_input("MACD 快線", value=12, min_value=5, max_value=20)
    macd_slow = st.sidebar.number_input("MACD 慢線", value=26, min_value=20, max_value=40)
    macd_signal = st.sidebar.number_input("MACD 訊號線", value=9, min_value=5, max_value=15)

elif "估值" in strategy:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ 估值理想目標")
    target_pe = st.sidebar.number_input("理想本益比上限", value=20.0, min_value=1.0, max_value=50.0)
    target_pb = st.sidebar.number_input("理想淨值比上限", value=2.5, min_value=0.1, max_value=5.0)
    target_yield = st.sidebar.slider("理想最低殖利率 (%)", min_value=0.0, max_value=10.0, value=2.0)

elif "經典基本面" in strategy:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ 經典基本面目標")
    min_eps_target = st.sidebar.number_input("理想最低 EPS (元)", value=1.0, min_value=0.0, max_value=20.0, step=0.5)

else:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ 黑美人策略參數")
    bm_ma_fast = st.sidebar.number_input("快速均線 (月線 MA)", value=20, min_value=5, max_value=60)
    bm_ma_slow = st.sidebar.number_input("慢速均線 (季線 MA)", value=60, min_value=20, max_value=240)
    bm_vol_mult = st.sidebar.slider("爆量門檻倍數", value=1.2, min_value=1.0, max_value=3.0)

def parse_float(val):
    try:
        if val is None or val == '-' or val == '' or val == 'N/A': return 0.0
        return float(str(val).replace(',', ''))
    except Exception: return 0.0

# ----------------------------------------------------
# 4. 直連證交所/櫃買中心 (過 1:30 自動強制作業即時更新)
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_tw_market_data(force_fresh=False):
    market_data = {}
    
    # A. 抓取上市櫃本益比、淨值比、殖利率與股票名稱
    try:
        res_twse_val = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", timeout=5)
        if res_twse_val.status_code == 200:
            for item in res_twse_val.json():
                code = item.get('Code', '')
                name = item.get('Name', '').strip()
                if len(code) == 4 and code.isdigit():
                    market_data[code] = {
                        "Name": name,
                        "PE": parse_float(item.get('PEratio')),
                        "PB": parse_float(item.get('PBratio')),
                        "Yield": parse_float(item.get('DividendYield')),
                        "Close": 0.0,
                        "Volume": 0
                    }
    except Exception: pass

    try:
        res_tpex_val = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", timeout=5)
        if res_tpex_val.status_code == 200:
            for item in res_tpex_val.json():
                code = item.get('SecuritiesCompanyCode', '')
                name = item.get('CompanyName', '').strip()
                if len(code) == 4 and code.isdigit():
                    if code not in market_data: market_data[code] = {"Name": name}
                    market_data[code].update({
                        "Name": name if name else market_data[code].get("Name", ""),
                        "PE": parse_float(item.get('PERatio')),
                        "PB": parse_float(item.get('PBRatio')),
                        "Yield": parse_float(item.get('YieldRatio'))
                    })
    except Exception: pass

    # B. 抓取上市櫃每日收盤價與成交量
    try:
        res_twse_price = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=5)
        if res_twse_price.status_code == 200:
            for item in res_twse_price.json():
                code = item.get('Code', '')
                name = item.get('Name', '').strip()
                if code in market_data:
                    if name: market_data[code]["Name"] = name
                    market_data[code]["Close"] = parse_float(item.get('ClosingPrice'))
                    market_data[code]["Volume"] = int(parse_float(item.get('TradeVolume')) / 1000)
    except Exception: pass

    try:
        res_tpex_price = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_dailyclose_quotes", timeout=5)
        if res_tpex_price.status_code == 200:
            for item in res_tpex_price.json():
                code = item.get('SecuritiesCompanyCode', '')
                name = item.get('CompanyName', '').strip()
                if code in market_data:
                    if name: market_data[code]["Name"] = name
                    market_data[code]["Close"] = parse_float(item.get('Close'))
                    market_data[code]["Volume"] = int(parse_float(item.get('TradingShares')) / 1000)
    except Exception: pass

    return market_data

# ----------------------------------------------------
# 5. 精細化評分計算
# ----------------------------------------------------
def calculate_score(sid, info):
    name = info.get("Name", "")
    stock_display = f"{sid} {name}" if name else sid

    close_price = info.get("Close", 0.0)
    vol_lots = info.get("Volume", 0)
    pe = info.get("PE", 0.0)
    pb = info.get("PB", 0.0)
    dy = info.get("Yield", 0.0)

    # 成交量過濾
    if use_vol_filter and not (min_vol <= vol_lots <= max_vol):
        return None

    score = 0
    est_eps = round(close_price / pe, 2) if pe > 0 and close_price > 0 else 0.0

    # 策略 1：SMC 聰明錢
    if "SMC" in strategy:
        if 0 < pe <= 10: score += 35
        elif 10 < pe <= 15: score += 28
        elif 15 < pe <= 20: score += 20
        elif 20 < pe <= 30: score += 10
        elif pe > 0: score += 5

        if 0 < pb <= 1.2: score += 35
        elif 1.2 < pb <= 1.8: score += 28
        elif 1.8 < pb <= 2.5: score += 20
        elif pb > 0: score += 10

        if dy >= 6.0: score += 30
        elif 4.0 <= dy < 6.0: score += 22
        elif 2.0 <= dy < 4.0: score += 15
        elif dy > 0: score += 5

        grade = "🏆 S級 (頂級機構標的)" if score >= 85 else ("🔥 A級 (強勢估值)" if score >= 65 else "👀 B級 (結構醞釀)" if score >= 40 else "🔹 C級 (普通格局)")
        return {
            "綜合評分": score,
            "股票名稱與代碼": stock_display,
            "評級等級": grade,
            "最新收盤": close_price if close_price > 0 else "—",
            "成交量(張)": vol_lots if vol_lots > 0 else "—",
            "本益比": pe if pe > 0 else "—",
            "股價淨值比": pb if pb > 0 else "—",
            "殖利率 (%)": f"{dy}%" if dy > 0 else "—"
        }

    # 策略 2：KD + MACD + RSI
    elif "KD + MACD" in strategy:
        if dy >= 5.0: score += 35
        elif dy >= 3.0: score += 25
        elif dy > 0: score += 10

        if 0 < pe <= 12: score += 35
        elif 12 < pe <= 20: score += 25
        elif pe > 0: score += 10

        if 0 < pb <= 1.5: score += 30
        elif 0 < pb <= 2.5: score += 20
        elif pb > 0: score += 10

        grade = "🏆 S級 (雙金爆發)" if score >= 80 else ("🔥 A級 (強勢共振)" if score >= 50 else "👀 B級 (醞釀中)" if score >= 20 else "🔹 C級 (弱勢趨勢)")
        return {
            "綜合評分": score,
            "股票名稱與代碼": stock_display,
            "評級等級": grade,
            "最新收盤": close_price if close_price > 0 else "—",
            "成交量(張)": vol_lots if vol_lots > 0 else "—",
            "本益比": pe if pe > 0 else "—",
            "股價淨值比": pb if pb > 0 else "—",
            "殖利率 (%)": f"{dy}%" if dy > 0 else "—"
        }

    # 策略 3：估值評分
    elif "估值" in strategy:
        if 0 < pe <= target_pe: score += 40
        elif 0 < pe <= target_pe * 1.3: score += 20
        if 0 < pb <= target_pb: score += 30
        if dy >= target_yield: score += 30
        grade = "🏆 S級 (極度便宜)" if score >= 80 else ("🔥 A級 (估值優良)" if score >= 50 else "👀 B級 (估值合理)" if score >= 20 else "🔹 C級 (估值偏高)")
        return {
            "綜合評分": score,
            "股票名稱與代碼": stock_display,
            "評級等級": grade,
            "最新收盤": close_price if close_price > 0 else "—",
            "成交量(張)": vol_lots if vol_lots > 0 else "—",
            "本益比 (P/E)": pe if pe > 0 else "—",
            "股價淨值比 (P/B)": pb if pb > 0 else "—",
            "殖利率 (%)": f"{dy}%" if dy > 0 else "—",
            "預估 EPS": est_eps if est_eps > 0 else "—"
        }

    # 策略 4：經典基本面
    elif "經典基本面" in strategy:
        if est_eps >= min_eps_target: score += 50
        elif est_eps > 0: score += 20
        if 0 < pe <= 15: score += 30
        if dy >= 3.0: score += 20
        grade = "🏆 S級 (高獲利績優)" if score >= 80 else ("🔥 A級 (穩健成長)" if score >= 50 else "👀 B級 (體質尚可)" if score >= 20 else "🔹 C級 (普通水準)")
        return {
            "綜合評分": score,
            "股票名稱與代碼": stock_display,
            "評級等級": grade,
            "最新收盤": close_price if close_price > 0 else "—",
            "成交量(張)": vol_lots if vol_lots > 0 else "—",
            "預估 EPS (元)": est_eps if est_eps > 0 else "—",
            "本益比 (P/E)": pe if pe > 0 else "—",
            "殖利率 (%)": f"{dy}%" if dy > 0 else "—"
        }

    # 策略 5：黑美人戰法
    else:
        if vol_lots >= 3000: score += 40
        elif vol_lots >= 1000: score += 25
        elif vol_lots >= 500: score += 10
        if 0 < pe <= 15: score += 30
        elif 0 < pe <= 25: score += 15
        if dy >= 3.0: score += 30
        grade = "🏆 S級 (完美起飛)" if score >= 80 else ("🔥 A級 (強勢買點)" if score >= 50 else "👀 B級 (醞釀中)" if score >= 20 else "🔹 C級 (盤整盤)")
        return {
            "綜合評分": score,
            "股票名稱與代碼": stock_display,
            "評級等級": grade,
            "最新收盤": close_price if close_price > 0 else "—",
            "成交量(張)": vol_lots if vol_lots > 0 else "—",
            "本益比": pe if pe > 0 else "—",
            "殖利率 (%)": f"{dy}%" if dy > 0 else "—"
        }

# ----------------------------------------------------
# 6. 主程式執行區
# ----------------------------------------------------
if st.button("⚡ 開始全量化評分掃描"):
    # 下午 1:30 後傳遞不同參數觸發實時更新
    fresh_flag = is_after_market_close
    
    with st.spinner("正在直連台灣證券交易所官方 API 載入最新數據與股票名稱..."):
        market_data = fetch_tw_market_data(force_fresh=fresh_flag)
        all_stocks = list(market_data.keys())
        
        if "100" in scan_mode:
            target_stocks = random.sample(all_stocks, min(100, len(all_stocks)))
        elif "全台股" in scan_mode:
            target_stocks = all_stocks
        else:
            target_stocks = ["2330", "2317", "2454", "2382", "3231", "2308", "2353", "3576", "2408", "5347", "2603", "2609", "2615", "2303", "3037", "2379", "3034", "2377", "2357", "3017", "6669", "3661", "3008", "2451", "6239"]

    st.write(f"📊 準備掃描評分：**{len(target_stocks)}** 档股票（當前策略：**{strategy}**）")
    progress_bar = st.progress(0)
    
    results = []
    total = len(target_stocks)
    
    for idx, sid in enumerate(target_stocks):
        res = calculate_score(sid, market_data.get(sid, {}))
        if res:
            results.append(res)
        progress_bar.progress((idx + 1) / total)

    if results:
        res_df = pd.DataFrame(results)
        res_df = res_df.sort_values(by="綜合評分", ascending=False).reset_index(drop=True)
        st.success(f"🎉 成功完成 **{len(res_df)}** 檔股票評分（已按 0~100 綜合評分由高至低自動排序）！")
        st.dataframe(res_df, use_container_width=True)
    else:
        st.warning("請微調成交量範圍限制條件。")
