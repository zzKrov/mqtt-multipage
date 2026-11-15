import json
from datetime import datetime

import streamlit as st

VOICE_HOST = "broker.mqttdashboard.com"
VOICE_PORT = 1883
VOICE_TOPIC = "voice_ctrl"

eq = st.session_state["_eq"]
channel = eq["get_channel"](VOICE_HOST, VOICE_PORT, prefix="eq-voz")
st.session_state.pop("pulso_boot", None)

st.subheader("VOZ")
st.caption("Dictado directo.")


def _dispatch_voice(text: str) -> None:
    clean = text.strip()
    if not clean:
        return
    payload = json.dumps({"Act1": clean}, ensure_ascii=False)
    ok, ms = channel.publish(VOICE_TOPIC, payload)
    hora = datetime.now().strftime("%H:%M:%S")
    st.session_state["last_voice_status"] = (
        f"{hora} · «{clean}» · {ms:.0f} ms"
        if ok
        else f"{hora} · Sin respuesta"
    )


res = eq["voice_console"](
    key="eq_voice_widget",
    data={"lang": "es-CO"},
    on_utterance_change=lambda: None,
)

if getattr(res, "utterance", None):
    utterance = res.utterance
    uid = utterance.get("id")
    if uid and uid != st.session_state.get("last_voice_id"):
        _dispatch_voice(utterance.get("text", ""))
        st.session_state["last_voice_id"] = uid

with st.form("voz_manual_form", clear_on_submit=True, border=False):
    c_in, c_btn = st.columns([4, 1], vertical_alignment="bottom")
    with c_in:
        typed_cmd = st.text_input(
            "Comando",
            placeholder="Escribir comando…",
            label_visibility="collapsed",
        )
    with c_btn:
        sent_manual = st.form_submit_button("ENVIAR", width="stretch")

if sent_manual and typed_cmd.strip():
    _dispatch_voice(typed_cmd)

st.caption(f"● {st.session_state.get('last_voice_status', 'Listo.')}")
