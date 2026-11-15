import json
from datetime import datetime

import streamlit as st

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

eq["header"]("PULSO", "Acción directa y ajuste gradual de intensidad.")

st.html(
    """
    <div class="eq-steps">
      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <rect x="6" y="13" width="22" height="8" stroke="#ffffff" stroke-opacity="0.35" stroke-width="1"/>
          <rect x="8" y="15" width="8" height="4" fill="#ffffff" class="eq-anim-toggle"/>
        </svg>
        <div><span class="eq-step-num">01</span><span class="eq-step-text">Pulso binario</span></div>
      </div>

      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <line x1="6" y1="17" x2="28" y2="17" stroke="#ffffff" stroke-width="1.3" class="eq-anim-beam"/>
          <circle cx="17" cy="17" r="2.2" fill="#ffffff"/>
        </svg>
        <div><span class="eq-step-num">02</span><span class="eq-step-text">Escala continua</span></div>
      </div>

      <div class="eq-step">
        <svg class="eq-step-icon" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="11" stroke="#ffffff" stroke-opacity="0.3" stroke-width="1"/>
          <path d="M12 17.5L15.5 21L22.5 13.5" stroke="#ffffff" stroke-width="1.5"/>
        </svg>
        <div><span class="eq-step-num">03</span><span class="eq-step-text">Confirmación</span></div>
      </div>
    </div>
    """
)

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
                f"{hora} · {etiqueta} · {ms:.0f} ms" if ok else f"{hora} · Sin respuesta ({etiqueta})"
            )
            st.session_state["last_pulse_ok"] = ok

        elif kind == "analog":
            num = float(val)
            st.session_state["pulse_analog"] = num
            ok, ms = channel.publish(TOPIC_ANALOG, json.dumps({"Analog": num}))
            st.session_state["last_pulse_status"] = (
                f"{hora} · Nivel {num:.1f} · {ms:.0f} ms" if ok else f"{hora} · Sin respuesta (Nivel {num:.1f})"
            )
            st.session_state["last_pulse_ok"] = ok

        st.session_state["last_pulse_cmd_id"] = cid

status_msg = st.session_state.get("last_pulse_status", "Sistema listo.")
dot_cls = "eq-dot" if st.session_state.get("last_pulse_ok", True) else "eq-dot eq-dot-dim"

st.html(
    f"""
    <div class="eq-status-strip">
      <span><span class="{dot_cls}"></span>{status_msg}</span>
      <span style="color:#7c7c85;">PULSO</span>
    </div>
    """
)
