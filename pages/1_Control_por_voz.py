import json
from datetime import datetime

import streamlit as st

VOICE_HOST = "broker.mqttdashboard.com"
VOICE_PORT = 1883
VOICE_TOPIC = "voice_ctrl"

eq = st.session_state["_eq"]
channel = eq["get_channel"](VOICE_HOST, VOICE_PORT, prefix="eq-voz")
st.session_state.pop("pulso_boot", None)

eq["header"]("VOZ", "Dicta una instrucción breve. Se transmite al finalizar la frase.")

st.html(
    """
    <div class="eq-steps">
      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="13" stroke="#ffffff" stroke-opacity="0.25" stroke-width="1"/>
          <circle cx="17" cy="17" r="6" stroke="#ffffff" stroke-width="1.2" class="eq-anim-ring"/>
          <circle cx="17" cy="17" r="2" fill="#ffffff"/>
        </svg>
        <div><span class="eq-step-num">01</span><span class="eq-step-text">Pulsa el núcleo</span></div>
      </div>

      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <rect x="9" y="12" width="2" height="10" fill="#ffffff" class="eq-anim-bar-1"/>
          <rect x="16" y="7" width="2" height="20" fill="#ffffff" class="eq-anim-bar-2"/>
          <rect x="23" y="12" width="2" height="10" fill="#ffffff" class="eq-anim-bar-3"/>
        </svg>
        <div><span class="eq-step-num">02</span><span class="eq-step-text">Pronuncia la orden</span></div>
      </div>

      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <circle cx="24" cy="17" r="6" stroke="#ffffff" stroke-opacity="0.45" stroke-width="1"/>
          <path d="M6 17H21M17 13L21 17L17 21" stroke="#ffffff" stroke-width="1.4" class="eq-anim-arrow"/>
        </svg>
        <div><span class="eq-step-num">03</span><span class="eq-step-text">Envío inmediato</span></div>
      </div>
    </div>
    """
)


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
        else f"{hora} · Sin respuesta al enviar «{clean}»"
    )
    st.session_state["last_voice_ok"] = ok


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
            "Alternativa escrita",
            placeholder="Escribe una orden si no usas micrófono…",
            label_visibility="collapsed",
        )
    with c_btn:
        sent_manual = st.form_submit_button("ENVIAR", width="stretch")

if sent_manual and typed_cmd.strip():
    _dispatch_voice(typed_cmd)

status_msg = st.session_state.get("last_voice_status", "En espera de instrucción.")
dot_cls = "eq-dot" if st.session_state.get("last_voice_ok", True) else "eq-dot eq-dot-dim"

st.html(
    f"""
    <div class="eq-status-strip">
      <span><span class="{dot_cls}"></span>{status_msg}</span>
      <span style="color:#7c7c85;">VOZ</span>
    </div>
    """
)
