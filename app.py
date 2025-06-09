import asyncio, time, pandas as pd, streamlit as st
from graph import workflow, wallet, display_graph_dot

st.set_page_config(page_title="Crypto Multi-Agent", layout="wide")

equity_curve: list[tuple[float, float]] = []
placeholder = st.empty()


async def loop():
    while True:
        result = await workflow.ainvoke({})

        prices  = result["prices"]
        equity  = result["equity"]
        events  = result["events"]

        equity_curve.append((time.time(), equity))

        with placeholder.container():
            col1, col2, col3 = st.columns([1.4, 1.4, 1])

            # ── баланс/график ─────────────────────
            with col1:
                st.subheader("Баланс / Equity")
                st.write(f"Кэш: {wallet.cash:,.2f} USDT")
                st.write("Позиции:", wallet.positions)
                st.metric("Нереализованный P&L",
                        f"{wallet.unrealized_pnl(prices):,.2f} USDT")
                st.metric("Реализованный P&L",
                        f"{wallet.realized:,.2f} USDT")
                st.line_chart(pd.DataFrame(equity_curve,
                                        columns=["ts", "equity"]).set_index("ts"))

            # ── сделки (BUY/SELL) ─────────────────
            with col2:
                st.subheader("Логи")
                for ts, msg in reversed(wallet.history[-25:]):
                    st.text(f"{time.strftime('%H:%M:%S', time.localtime(ts))}  {msg}")

            # ── процессы + reasoning ──────────────
            with col3:
                st.subheader("Процессы")
                for ev in events:
                    st.markdown(f"- **{ev['ts']}** — {ev['msg']}")
                with st.expander("💬 Рассуждения", expanded=False):
                    for ev in events:
                        if ev["extra"]:
                            st.markdown(f"*{ev['msg']}*")
                            st.json(ev["extra"], expanded=False)

            # ── визуализация графа ────────────────
            with st.expander("🗺️ Граф узлов", expanded=False):
                st.graphviz_chart(display_graph_dot())

        await asyncio.sleep(30)        # шаг ≈ 3 мин


asyncio.run(loop())
