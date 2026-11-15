import json
from datetime import datetime

import streamlit as st

if "_eq" not in st.session_state:
    st.switch_page("Inicio.py")

PULSE_HOST = "157.230.214.127"
PULSE_PORT = 1883
TOPIC_SWITCH = "cmqtt_s"
TOPIC_ANALOG = "cmqtt_a"

eq = st.session_state["_eq"]
channel = eq["get_channel"](PULSE_HOST, PULSE_PORT, prefix="eq-pulso")

if "pulso_boot" not in st.session_state:
    st.session_state["pulso_boot"] = {
        "switch": st.session_state.get("pulse_switch", ""),
        "analog": st.session_state.get("pulse_analog", 50.0),
    }

st.subheader("PULSO")
st.caption("Estado binario y nivel.")

res = eq["pulse_console"](
    key="eq_pulse_widget",
    data=st.session_state["pulso_boot"],
    on_command_change=lambda: None,
)

if getattr(res, "command", None):
    cmd = res.command
    cid = cmd.get("id")
    if cid and cid != st.session_state.get("last_pulse_cmd_id"):
        kind = cmd.get("kind")
        val = cmd.get("value")
        hora = datetime.now().strftime("%H:%M:%S")

        if kind == "switch" and val in ("ON", "OFF"):
            st.session_state["pulse_switch"] = val
            ok, ms = channel.publish(TOPIC_SWITCH, json.dumps({"Act1": val}))
            etiqueta = "Encendido" if val == "ON" else "Apagado"
            st.session_state["last_pulse_status"] = (
                f"{hora} · {etiqueta} · {ms:.0f} ms" if ok else f"{hora} · Sin respuesta"
            )

        elif kind == "analog":
            num = float(val)
            st.session_state["pulse_analog"] = num
            ok, ms = channel.publish(TOPIC_ANALOG, json.dumps({"Analog": num}))
            st.session_state["last_pulse_status"] = (
                f"{hora} · Nivel {num:.1f} · {ms:.0f} ms" if ok else f"{hora} · Sin respuesta"
            )

        st.session_state["last_pulse_cmd_id"] = cid

st.caption(f"● {st.session_state.get('last_pulse_status', 'Listo.')}")
