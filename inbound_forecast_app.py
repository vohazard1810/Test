
import io
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="Inbound Planner (3M)", layout="wide")

st.title("📦 Inbound Planner — 3 Months Horizon")

with st.expander("ℹ️ Input data format"):
    st.markdown("""
    **Upload CSV** theo cấu trúc giống file *Template Shop LG.csv* với các cột quan trọng:
    - `sku_id`, `mt_sku_id`, `shop_id`, `shop_name`, `item_name`, `category_cluster`
    - Tồn kho: `total_stock_vncb`, `total_stock_vnn`, `total_stock_vns`, `total_stock_vndb`
    - Inbound: `vncb_inbounding`, `vnn_inbounding`, `vns_inbounding`, `vndb_inbounding`
    - Sales 30 ngày (TB/ngày): `l30_daily_itemsold_vncb`, `l30_daily_itemsold_vnn`, `l30_daily_itemsold_vns`, `l30_daily_itemsold_vndb`
    """)

st.sidebar.header("⚙️ Parameters")
horizon_days = st.sidebar.number_input("Forecast horizon (days)", min_value=7, max_value=180, value=90, step=1)
leadtime_days = st.sidebar.number_input("Leadtime (days)", min_value=0, max_value=60, value=7, step=1)

st.sidebar.markdown("**Safety stock (days)**")
safety_elha = st.sidebar.number_input("ELHA", min_value=0, max_value=90, value=30, step=1)
safety_fmcg = st.sidebar.number_input("FMCG", min_value=0, max_value=90, value=21, step=1)
safety_other = st.sidebar.number_input("Others", min_value=0, max_value=90, value=14, step=1)

st.sidebar.markdown("**Constraints (optional)**")
pack_size = st.sidebar.number_input("Pack size (round to multiples of)", min_value=0, max_value=1000, value=0, step=1)
moq_units = st.sidebar.number_input("MOQ (units)", min_value=0, max_value=100000, value=0, step=1)

uploaded = st.file_uploader("Upload CSV", type=["csv"])

sample_df = None
if uploaded:
    df = pd.read_csv(uploaded)
else:
    st.info("Chưa upload CSV. Bạn có thể thử với dữ liệu mẫu (nhấn nút dưới).")
    if st.button("Dùng dữ liệu mẫu"):
        # Minimal sample to demonstrate logic
        sample_df = pd.DataFrame({
            "sku_id": ["A","B","C"],
            "mt_sku_id": ["111_1", "222_2", "333_3"],
            "shop_id": [1,1,1],
            "shop_name": ["LG Official Store"]*3,
            "item_name": ["SKU A","SKU B","SKU C"],
            "category_cluster": ["ELHA","FMCG","Others"],
            "total_stock_vncb": [100,50,0],
            "total_stock_vnn": [0,0,0],
            "total_stock_vns": [0,0,0],
            "total_stock_vndb": [0,0,0],
            "vncb_inbounding": [10,0,0],
            "vnn_inbounding": [0,0,0],
            "vns_inbounding": [0,0,0],
            "vndb_inbounding": [0,0,0],
            "l30_daily_itemsold_vncb": [2,4,0.5],
            "l30_daily_itemsold_vnn": [0,0,0],
            "l30_daily_itemsold_vns": [0,0,0],
            "l30_daily_itemsold_vndb": [0,0,0],
        })
        df = sample_df

if 'df' in locals():
    # Optional filter by MT SKU
    st.sidebar.markdown("---")
    mt_filter = st.sidebar.text_input("Filter by mt_sku_id (optional)")
    if mt_filter:
        df = df[df["mt_sku_id"].astype(str).str.contains(mt_filter, na=False)]

    # Compute helpers
    df["total_stock"] = df[["total_stock_vncb","total_stock_vnn","total_stock_vns","total_stock_vndb"]].sum(axis=1, skipna=True)
    df["total_inbound"] = df[["vncb_inbounding","vnn_inbounding","vns_inbounding","vndb_inbounding"]].sum(axis=1, skipna=True)
    df["avg_sales_30d"] = df[["l30_daily_itemsold_vncb","l30_daily_itemsold_vnn","l30_daily_itemsold_vns","l30_daily_itemsold_vndb"]].sum(axis=1, skipna=True)

    def safety_days(cat):
        if cat == "ELHA": return safety_elha
        if cat == "FMCG": return safety_fmcg
        return safety_other

    df["safety_stock_days"] = df["category_cluster"].fillna("Others").apply(safety_days)
    df["safety_units"] = df["safety_stock_days"] * df["avg_sales_30d"]
    df["leadtime_units"] = leadtime_days * df["avg_sales_30d"]
    df["forecast_h_units"] = horizon_days * df["avg_sales_30d"]
    df["available_units"] = df["total_stock"] + df["total_inbound"]

    df["inbound_need_units"] = (df["forecast_h_units"] + df["safety_units"] + df["leadtime_units"] - df["available_units"]).clip(lower=0)

    # Rounding by constraints
    def round_constraints(x):
        if moq_units and x > 0:
            x = max(x, moq_units)
        if pack_size and x > 0:
            x = int(np.ceil(x / pack_size) * pack_size)
        return x

    df["IB_suggest_units"] = df["inbound_need_units"].apply(round_constraints)

    # Coverage reached after IB
    with np.errstate(divide='ignore', invalid='ignore'):
        df["coverage_after_IB_days"] = np.where(
            df["avg_sales_30d"]>0,
            (df["available_units"] + df["IB_suggest_units"]) / df["avg_sales_30d"],
            np.nan
        )

    show_cols = [
        "sku_id","mt_sku_id","shop_name","item_name","category_cluster",
        "avg_sales_30d","total_stock","total_inbound",
        "safety_stock_days","forecast_h_units",
        "available_units","inbound_need_units","IB_suggest_units","coverage_after_IB_days"
    ]
    result = df[show_cols].copy()

    st.success(f"Đã tính xong. {len(result)} dòng.")
    st.dataframe(result, use_container_width=True)

    # Download
    csv = result.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Tải kết quả CSV", data=csv, file_name="inbound_suggestion.csv", mime="text/csv")

    st.caption("• Công thức: Inbound = Forecast(h) + Safety + Leadtime − (Stock + Inbound). Áp dụng MOQ/Pack-size nếu có.")
else:
    st.stop()
