import threading
import time
import uuid

import paho.mqtt.client as mqtt
import streamlit as st
import streamlit.components.v1 as components

BASE_APP_URL = "https://mqtt-multipagez.streamlit.app"

# Pega aquí el enlace permanente de tu proyecto guardado en Wokwi:
WOKWI_URL = "https://wokwi.com/projects/new/esp32"

st.set_page_config(
    page_title="CONTROL",
    page_icon="⌖",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ==============================================================================
# 1. CONEXIÓN PERSISTENTE COMPATIBLE CON PAHO 1.X Y 2.X
# ==============================================================================
class MqttChannel:
    def __init__(self, host: str, port: int = 1883, prefix: str = "eq"):
        self.host = host
        self.port = port
        self.client_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
        self._lock = threading.Lock()
        self._connected_event = threading.Event()
        self._connected = False
        self._loop_running = False

        if hasattr(mqtt, "CallbackAPIVersion"):
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
                protocol=mqtt.MQTTv311,
            )
            self._client.on_connect = self._on_connect_v2
            self._client.on_disconnect = self._on_disconnect_v2
        else:
            self._client = mqtt.Client(
                client_id=self.client_id,
                protocol=mqtt.MQTTv311,
            )
            self._client.on_connect = self._on_connect_v1
            self._client.on_disconnect = self._on_disconnect_v1

        self._client.reconnect_delay_set(min_delay=1, max_delay=12)
        self._start_loop()

    def _start_loop(self) -> None:
        if self._loop_running:
            return
        try:
            self._client.connect_async(self.host, self.port, keepalive=45)
            self._client.loop_start()
            self._loop_running = True
        except Exception:
            self._loop_running = False

    def _on_connect_v2(self, client, userdata, connect_flags, reason_code, properties):
        ok = reason_code == 0 or getattr(reason_code, "value", 1) == 0
        self._connected = ok
        if ok:
            self._connected_event.set()
        else:
            self._connected_event.clear()

    def _on_disconnect_v2(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected = False
        self._connected_event.clear()

    def _on_connect_v1(self, client, userdata, flags, rc):
        self._connected = rc == 0
        if self._connected:
            self._connected_event.set()
        else:
            self._connected_event.clear()

    def _on_disconnect_v1(self, client, userdata, rc):
        self._connected = False
        self._connected_event.clear()

    def is_ready(self) -> bool:
        return self._connected and self._client.is_connected()

    def publish(self, topic: str, payload: str, timeout: float = 1.5) -> tuple[bool, float]:
        start = time.perf_counter()
        with self._lock:
            if not self._loop_running:
                self._start_loop()
            if not self.is_ready():
                self._connected_event.wait(timeout=timeout)
            if not self.is_ready():
                return False, (time.perf_counter() - start) * 1000.0
            info = self._client.publish(topic, payload, qos=0)
            return info.rc == mqtt.MQTT_ERR_SUCCESS, (time.perf_counter() - start) * 1000.0


@st.cache_resource(show_spinner=False)
def get_mqtt_channel(host: str, port: int = 1883, prefix: str = "eq") -> MqttChannel:
    return MqttChannel(host=host, port=port, prefix=prefix)


# ==============================================================================
# 2. COMPONENTES (BARRA DE ENLACES + INICIO + VOZ CONTINUA + PULSO)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def get_components():
    top_nav = st.components.v2.component(
        "eq_top_nav",
        html=f"""
        <nav class="eq-nav">
          <a class="eq-link" data-page="Inicio" href="{BASE_APP_URL}/" target="_top">INICIO</a>
          <a class="eq-link" data-page="Voz" href="{BASE_APP_URL}/voz" target="_top">VOZ</a>
          <a class="eq-link" data-page="Pulso" href="{BASE_APP_URL}/pulso" target="_top">PULSO</a>
        </nav>
        """,
        css="""
        :host { display: block; width: 100%; }
        .eq-nav {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          width: 100%;
          margin-top: 6px;
          margin-bottom: 6px;
        }
        .eq-link {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 11px 12px;
          border: 1px solid #26262b;
          background: #0f0f11;
          color: #8a8a93;
          text-decoration: none;
          font-family: 'IBM Plex Mono', ui-monospace, monospace;
          font-size: 12px;
          letter-spacing: 0.22em;
          transition: all 180ms ease;
        }
        .eq-link:hover {
          border-color: #ffffff;
          color: #ffffff;
          background: #17171b;
          transform: translateY(-1px);
        }
        .eq-link.active {
          border-color: #ffffff;
          background: #ffffff;
          color: #080809;
        }
        """,
        js="""
        export default function(component) {
          const { data, parentElement, setTriggerValue } = component;
          const active = (data && data.active) || "Inicio";
          const links = parentElement.querySelectorAll(".eq-link");
          links.forEach((a) => {
            const target = a.dataset.page;
            a.classList.toggle("active", target === active);
            a.onclick = (e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
              e.preventDefault();
              if (target !== active) {
                setTriggerValue("nav", { page: target, ts: Date.now() });
              }
            };
          });
        }
        """,
    )

    inicio_board = st.components.v2.component(
        "eq_inicio_board",
        html=f"""
        <div class="wrap">
          <div class="hero">
            <canvas id="eq-canvas"></canvas>
            <div class="hero-overlay">
              <svg class="emblem" viewBox="0 0 180 180" fill="none">
                <circle cx="90" cy="90" r="78" stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="3 5" class="rot-cw"/>
                <circle cx="90" cy="90" r="56" stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="14 6" class="rot-ccw"/>
                <rect x="46" y="46" width="88" height="88" stroke="rgba(255,255,255,0.16)" stroke-width="1"/>
                <path d="M90 28V74M90 106V152M28 90H74M106 90H152" stroke="#ffffff" stroke-width="1.5"/>
                <path d="M72 42H108M72 138H108M42 72V108M138 72V108" stroke="rgba(255,255,255,0.8)" stroke-width="1.3"/>
                <circle cx="90" cy="90" r="6" stroke="#ffffff" stroke-width="1.3" class="core-pulse"/>
                <circle cx="90" cy="90" r="2" fill="#ffffff"/>
              </svg>
              <div class="coords" id="eq-coords">000 · 000</div>
            </div>
          </div>

          <div class="cards">
            <a class="card" data-page="Voz" href="{BASE_APP_URL}/voz" target="_top">
              <div class="card-top">
                <span class="idx">01</span>
                <svg width="32" height="32" viewBox="0 0 34 34" fill="none">
                  <circle cx="17" cy="17" r="10" stroke="#ffffff" stroke-opacity="0.3" stroke-width="1" class="ring-pulse"/>
                  <rect x="10" y="13" width="2" height="8" fill="#ffffff" class="b1"/>
                  <rect x="16" y="10" width="2" height="14" fill="#ffffff" class="b2"/>
                  <rect x="22" y="13" width="2" height="8" fill="#ffffff" class="b3"/>
                </svg>
              </div>
              <div class="card-title">VOZ</div>
              <div class="card-desc">Dictado continuo.</div>
            </a>

            <a class="card" data-page="Pulso" href="{BASE_APP_URL}/pulso" target="_top">
              <div class="card-top">
                <span class="idx">02</span>
                <svg width="32" height="32" viewBox="0 0 34 34" fill="none">
                  <line x1="6" y1="16" x2="28" y2="16" stroke="#ffffff" stroke-width="1.3" class="beam"/>
                  <circle cx="17" cy="16" r="2" fill="#ffffff"/>
                  <rect x="7" y="25" width="20" height="2" fill="#26262b"/>
                  <rect x="7" y="24" width="6" height="4" fill="#ffffff" class="tog"/>
                </svg>
              </div>
              <div class="card-title">PULSO</div>
              <div class="card-desc">Interruptor y nivel.</div>
            </a>
          </div>
        </div>
        """,
        css="""
        :host { display: block; width: 100%; }
        .wrap { display: flex; flex-direction: column; gap: 12px; font-family: 'Space Grotesk', system-ui, sans-serif; }
        .hero {
          position: relative; width: 100%; height: 240px;
          background: #0b0b0d; border: 1px solid #26262b; overflow: hidden; user-select: none;
        }
        #eq-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
        .hero-overlay {
          position: relative; z-index: 2; height: 100%;
          display: flex; align-items: center; justify-content: center; pointer-events: none;
        }
        .emblem { width: 148px; height: 148px; }
        .rot-cw { transform-origin: 90px 90px; animation: spinCW 32s linear infinite; }
        .rot-ccw { transform-origin: 90px 90px; animation: spinCCW 22s linear infinite; }
        .core-pulse { transform-origin: 90px 90px; animation: pulseCore 3.2s ease-in-out infinite; }
        .coords {
          position: absolute; bottom: 10px; right: 14px;
          font-family: 'IBM Plex Mono', ui-monospace, monospace;
          font-size: 10px; letter-spacing: 0.18em; color: rgba(255,255,255,0.4);
        }
        .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        @media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }
        .card {
          display: block; text-decoration: none;
          background: #0f0f11; border: 1px solid #26262b; padding: 16px 18px;
          transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease;
        }
        .card:hover { border-color: #ffffff; background: #151519; transform: translateY(-2px); }
        .card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
        .idx { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.24em; color: #8a8a93; }
        .card-title { font-size: 16px; letter-spacing: 0.22em; color: #ffffff; margin-bottom: 4px; }
        .card-desc { font-size: 13px; color: #8a8a93; }
        .ring-pulse { transform-origin: 17px 17px; animation: pulseCore 2.2s ease-in-out infinite; }
        .b1 { transform-origin: center; animation: barW 1.1s ease-in-out infinite; }
        .b2 { transform-origin: center; animation: barW 1.1s ease-in-out 0.2s infinite; }
        .b3 { transform-origin: center; animation: barW 1.1s ease-in-out 0.4s infinite; }
        .beam { transform-origin: 17px 16px; animation: tilt 3s ease-in-out infinite; }
        .tog { animation: togS 2.2s ease-in-out infinite; }
        @keyframes spinCW { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes spinCCW { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
        @keyframes pulseCore { 0%, 100% { transform: scale(1); opacity: 0.9; } 50% { transform: scale(1.55); opacity: 0.25; } }
        @keyframes barW { 0%, 100% { transform: scaleY(0.38); } 50% { transform: scaleY(1); } }
        @keyframes tilt { 0%, 100% { transform: rotate(-9deg); } 50% { transform: rotate(9deg); } }
        @keyframes togS { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(10px); } }
        """,
        js="""
        export default function(component) {
          const { parentElement, setTriggerValue } = component;
          const wrap = parentElement.querySelector(".hero");
          const canvas = parentElement.querySelector("#eq-canvas");
          const coords = parentElement.querySelector("#eq-coords");
          const cards = parentElement.querySelectorAll(".card");
          cards.forEach((c) => {
            c.onclick = (e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
              e.preventDefault();
              setTriggerValue("nav", { page: c.dataset.page, ts: Date.now() });
            };
          });
          if (!wrap || !canvas) return;
          const ctx = canvas.getContext("2d");
          const mouse = { x: -999, y: -999, active: false };
          let width = 0, height = 0, rafId = 0;

          const particles = Array.from({ length: 48 }, () => ({
            x: Math.random(), y: Math.random(),
            vx: (Math.random() - 0.5) * 0.00045, vy: (Math.random() - 0.5) * 0.00045,
            r: 0.8 + Math.random() * 1.4, a: 0.2 + Math.random() * 0.5
          }));

          function resize() {
            const rect = wrap.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            width = Math.max(1, rect.width); height = Math.max(1, rect.height);
            canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          }
          function onMove(e) {
            const rect = wrap.getBoundingClientRect();
            mouse.x = e.clientX - rect.left; mouse.y = e.clientY - rect.top; mouse.active = true;
            if (coords) coords.textContent = `${String(Math.max(0, Math.round(mouse.x))).padStart(3,"0")} · ${String(Math.max(0, Math.round(mouse.y))).padStart(3,"0")}`;
          }
          function onLeave() { mouse.active = false; }
          function frame() {
            ctx.clearRect(0, 0, width, height);
            for (const p of particles) {
              p.x = (p.x + p.vx + 1) % 1; p.y = (p.y + p.vy + 1) % 1;
              const px = p.x * width, py = p.y * height;
              if (mouse.active) {
                const dist = Math.hypot(mouse.x - px, mouse.y - py);
                if (dist < 115 && dist > 1) {
                  ctx.strokeStyle = `rgba(255,255,255,${(1 - dist / 115) * 0.24})`;
                  ctx.lineWidth = 0.7;
                  ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
                }
              }
              ctx.fillStyle = `rgba(255,255,255,${p.a})`;
              ctx.fillRect(px, py, p.r, p.r);
            }
            rafId = requestAnimationFrame(frame);
          }
          const ro = new ResizeObserver(resize); ro.observe(wrap); resize();
          wrap.addEventListener("mousemove", onMove); wrap.addEventListener("mouseleave", onLeave);
          rafId = requestAnimationFrame(frame);
          return () => {
            cancelAnimationFrame(rafId); ro.disconnect();
            wrap.removeEventListener("mousemove", onMove); wrap.removeEventListener("mouseleave", onLeave);
          };
        }
        """,
    )

    voice_console = st.components.v2.component(
        "eq_voice_console",
        html="""
        <div class="wrap">
          <div class="steps">
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <circle cx="17" cy="17" r="12" stroke="#ffffff" stroke-opacity="0.25" stroke-width="1"/>
                <circle cx="17" cy="17" r="6" stroke="#ffffff" stroke-width="1.2" class="ring-pulse"/>
                <circle cx="17" cy="17" r="2" fill="#ffffff"/>
              </svg>
              <div><span class="snum">01</span><span class="stxt">Activa</span></div>
            </div>
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <rect x="9" y="12" width="2" height="10" fill="#ffffff" class="b1"/>
                <rect x="16" y="7" width="2" height="20" fill="#ffffff" class="b2"/>
                <rect x="23" y="12" width="2" height="10" fill="#ffffff" class="b3"/>
              </svg>
              <div><span class="snum">02</span><span class="stxt">Habla</span></div>
            </div>
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <circle cx="24" cy="17" r="6" stroke="#ffffff" stroke-opacity="0.45" stroke-width="1"/>
                <path d="M6 17H21M17 13L21 17L17 21" stroke="#ffffff" stroke-width="1.4" class="arr"/>
              </svg>
              <div><span class="snum">03</span><span class="stxt">Envío continuo</span></div>
            </div>
          </div>

          <div class="eq-voice-shell" id="shell">
            <canvas id="voice-canvas"></canvas>
            <div class="eq-voice-top">
              <div class="eq-status-tag"><span class="eq-led"></span><span id="status-text">LISTO</span></div>
              <button type="button" class="eq-mode-btn" id="mode-btn">MODO · EN VIVO</button>
            </div>
            <div class="eq-voice-center">
              <button type="button" class="eq-core-btn" id="mic-btn" aria-label="Activar micrófono">
                <span class="brk tl"></span><span class="brk tr"></span>
                <span class="brk bl"></span><span class="brk br"></span>
                <span class="sheen"></span>
                <svg class="mic-svg" viewBox="0 0 120 120" fill="none">
                  <circle cx="60" cy="60" r="52" stroke="rgba(255,255,255,0.16)" stroke-width="1"/>
                  <circle cx="60" cy="60" r="42" stroke="rgba(255,255,255,0.28)" stroke-width="1" stroke-dasharray="4 6" class="ring-spin"/>
                  <path d="M60 14V26M60 94V106M14 60H26M94 60H106" stroke="rgba(255,255,255,0.55)" stroke-width="1.2"/>
                  <rect x="53" y="40" width="14" height="24" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M45 58V61C45 69.2843 51.7157 76 60 76C68.2843 76 75 69.2843 75 61V58" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M60 76V84M52 84H68" stroke="currentColor" stroke-width="1.6"/>
                </svg>
                <span class="core-label" id="btn-label">ACTIVAR</span>
              </button>
            </div>
            <div class="eq-transcript-box">
              <span class="eq-t-caption">VOZ</span>
              <span class="eq-t-value" id="transcript-view">—</span>
            </div>
          </div>
        </div>
        """,
        css="""
        :host { display: block; width: 100%; }
        .wrap { display: flex; flex-direction: column; gap: 12px; font-family: 'Space Grotesk', system-ui, sans-serif; }
        .steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #26262b; border: 1px solid #26262b; }
        @media (max-width: 600px) { .steps { grid-template-columns: 1fr; } }
        .step { background: #0f0f11; padding: 12px 14px; display: flex; align-items: center; gap: 12px; }
        .ico { width: 32px; height: 32px; flex-shrink: 0; }
        .snum { display: block; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; letter-spacing: 0.2em; color: #8a8a93; }
        .stxt { font-size: 13px; color: #ececf0; }
        .ring-pulse { transform-origin: 17px 17px; animation: pulseR 2.2s ease-in-out infinite; }
        .b1 { transform-origin: center; animation: barW 1.1s ease-in-out infinite; }
        .b2 { transform-origin: center; animation: barW 1.1s ease-in-out 0.2s infinite; }
        .b3 { transform-origin: center; animation: barW 1.1s ease-in-out 0.4s infinite; }
        .arr { animation: arrS 1.8s ease-in-out infinite; }
        .eq-voice-shell {
          position: relative; width: 100%; min-height: 300px; background: #0b0b0d;
          border: 1px solid #26262b; overflow: hidden; display: flex; flex-direction: column;
          justify-content: space-between; padding: 16px 18px; box-sizing: border-box;
        }
        #voice-canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
        .eq-voice-top { position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; }
        .eq-status-tag { display: inline-flex; align-items: center; gap: 8px; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.22em; color: #b4b4bc; }
        .eq-led { width: 8px; height: 8px; background: #4e4e56; transition: all 180ms ease; }
        .eq-voice-shell.listening .eq-led { background: #ffffff; box-shadow: 0 0 12px rgba(255,255,255,0.9); }
        .eq-mode-btn { background: #121215; border: 1px solid #2e2e34; color: #a1a1aa; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; letter-spacing: 0.18em; padding: 6px 10px; cursor: pointer; transition: all 160ms ease; }
        .eq-mode-btn:hover { border-color: #ffffff; color: #ffffff; }
        .eq-voice-center { position: relative; z-index: 2; display: flex; justify-content: center; margin: 14px 0; }
        .eq-core-btn {
          position: relative; width: 204px; height: 160px; background: rgba(14,14,17,0.9);
          border: 1px solid #2f2f36; color: #ffffff; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 8px; cursor: pointer; overflow: hidden;
          transition: border-color 220ms ease, background-color 220ms ease, transform 220ms ease;
        }
        .eq-core-btn:hover { border-color: #ffffff; background: rgba(24,24,28,0.95); transform: translateY(-2px); }
        .eq-voice-shell.listening .eq-core-btn { background: #ffffff; color: #080809; border-color: #ffffff; }
        .eq-voice-shell.listening .mic-svg circle, .eq-voice-shell.listening .mic-svg path { stroke: rgba(8,8,9,0.45); }
        .eq-voice-shell.listening .mic-svg rect, .eq-voice-shell.listening .mic-svg path:nth-of-type(2), .eq-voice-shell.listening .mic-svg path:nth-of-type(3) { stroke: #080809; }
        .brk { position: absolute; width: 8px; height: 8px; border-color: #ffffff; border-style: solid; opacity: 0.45; transition: all 220ms ease; }
        .eq-core-btn:hover .brk { opacity: 1; width: 12px; height: 12px; }
        .tl { top: 6px; left: 6px; border-width: 1px 0 0 1px; }
        .tr { top: 6px; right: 6px; border-width: 1px 1px 0 0; }
        .bl { bottom: 6px; left: 6px; border-width: 0 0 1px 1px; }
        .br { bottom: 6px; right: 6px; border-width: 0 1px 1px 0; }
        .eq-voice-shell.listening .brk { border-color: #080809; opacity: 1; }
        .sheen { position: absolute; inset: 0; background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.12) 50%, transparent 70%); transform: translateX(-120%); transition: transform 500ms ease; pointer-events: none; }
        .eq-core-btn:hover .sheen { transform: translateX(120%); }
        .mic-svg { width: 88px; height: 88px; }
        .ring-spin { transform-origin: 60px 60px; animation: spinSlow 16s linear infinite; }
        .eq-voice-shell.listening .ring-spin { animation: spinSlow 4s linear infinite; }
        .core-label { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.24em; }
        .eq-transcript-box { position: relative; z-index: 2; border-top: 1px solid #232328; padding-top: 10px; display: flex; align-items: baseline; gap: 12px; }
        .eq-t-caption { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; letter-spacing: 0.22em; color: #7c7c85; }
        .eq-t-value { font-size: 15px; color: #ffffff; letter-spacing: 0.04em; min-height: 20px; }
        @keyframes spinSlow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulseR { 0%, 100% { transform: scale(1); opacity: 0.95; } 50% { transform: scale(1.65); opacity: 0.25; } }
        @keyframes barW { 0%, 100% { transform: scaleY(0.35); } 50% { transform: scaleY(1); } }
        @keyframes arrS { 0%, 100% { transform: translateX(-2px); opacity: 0.45; } 50% { transform: translateX(3px); opacity: 1; } }
        """,
        js="""
        export default function(component) {
          const { parentElement, setTriggerValue } = component;
          const shell = parentElement.querySelector("#shell");
          const canvas = parentElement.querySelector("#voice-canvas");
          const micBtn = parentElement.querySelector("#mic-btn");
          const modeBtn = parentElement.querySelector("#mode-btn");
          const btnLabel = parentElement.querySelector("#btn-label");
          const statusText = parentElement.querySelector("#status-text");
          const transcriptView = parentElement.querySelector("#transcript-view");
          if (!shell || !canvas || !micBtn) return;

          const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

          if (!window.__eqVoiceEngine) {
            window.__eqVoiceEngine = {
              wantListening: false,
              continuousMode: true,
              isRunning: false,
              recognition: null,
              restartTimer: null,
              stopTimer: null,
              lastStatus: "LISTO",
              lastTranscript: "—",
              seq: 0,
              pulseEnergy: 0,
              ripples: [],
              uiSync: null,
              emitUtterance: null,
            };
          }
          const eng = window.__eqVoiceEngine;

          if (eng.stopTimer) {
            clearTimeout(eng.stopTimer);
            eng.stopTimer = null;
          }

          function syncUI() {
            const active = eng.wantListening;
            shell.classList.toggle("listening", active);
            btnLabel.textContent = active ? "DETENER" : "ACTIVAR";
            modeBtn.textContent = eng.continuousMode ? "MODO · EN VIVO" : "MODO · ÚNICO";
            statusText.textContent = SR ? eng.lastStatus : "SIN MICRÓFONO";
            transcriptView.textContent = eng.lastTranscript;
          }

          eng.uiSync = syncUI;
          eng.emitUtterance = (text) => {
            eng.seq += 1;
            setTriggerValue("utterance", { text, id: `${Date.now()}-${eng.seq}` });
          };

          function spawnRipple(strong = false) {
            eng.ripples.push({ r: 42, maxR: strong ? 190 : 140, alpha: strong ? 0.85 : 0.45 });
          }

          function createAndStartRecognition() {
            if (!SR || !eng.wantListening || eng.isRunning) return;
            if (eng.recognition) {
              try { eng.recognition.onresult = null; eng.recognition.onend = null; eng.recognition.onerror = null; eng.recognition.abort(); } catch (_) {}
              eng.recognition = null;
            }
            const rec = new SR();
            rec.lang = "es-CO";
            rec.interimResults = true;
            rec.continuous = eng.continuousMode;
            eng.recognition = rec;

            rec.onstart = () => {
              eng.isRunning = true;
              eng.lastStatus = "ESCUCHANDO";
              spawnRipple(false);
              if (eng.uiSync) eng.uiSync();
            };

            rec.onresult = (e) => {
              let interim = "";
              let finalChunk = "";
              for (let i = e.resultIndex; i < e.results.length; i++) {
                const txt = e.results[i][0].transcript;
                if (e.results[i].isFinal) finalChunk += txt + " ";
                else interim += txt;
              }
              eng.pulseEnergy = 1.0;

              if (interim.trim()) {
                eng.lastTranscript = interim.trim() + " …";
                if (eng.uiSync) eng.uiSync();
              }

              const clean = finalChunk.trim();
              if (clean) {
                eng.lastTranscript = clean;
                eng.lastStatus = eng.continuousMode ? "ENVIADO · ESCUCHANDO" : "ENVIADO";
                spawnRipple(true);
                if (!eng.continuousMode) {
                  eng.wantListening = false;
                }
                if (eng.uiSync) eng.uiSync();
                if (eng.emitUtterance) eng.emitUtterance(clean);
              }
            };

            rec.onerror = (e) => {
              if (e.error === "not-allowed" || e.error === "service-not-allowed") {
                eng.wantListening = false;
                eng.isRunning = false;
                eng.lastStatus = "SIN PERMISO";
                if (eng.uiSync) eng.uiSync();
              } else if (e.error === "no-speech") {
                eng.lastStatus = eng.wantListening ? "ESCUCHANDO" : "LISTO";
                if (eng.uiSync) eng.uiSync();
              } else if (e.error !== "aborted") {
                eng.isRunning = false;
              }
            };

            rec.onend = () => {
              eng.isRunning = false;
              if (eng.wantListening && eng.continuousMode) {
                clearTimeout(eng.restartTimer);
                eng.restartTimer = setTimeout(() => {
                  createAndStartRecognition();
                }, 120);
              } else {
                eng.wantListening = false;
                if (eng.lastStatus === "ESCUCHANDO" || eng.lastStatus === "ENVIADO · ESCUCHANDO") {
                  eng.lastStatus = "LISTO";
                }
                if (eng.uiSync) eng.uiSync();
              }
            };

            try {
              rec.start();
            } catch (_) {
              eng.isRunning = false;
              clearTimeout(eng.restartTimer);
              eng.restartTimer = setTimeout(() => createAndStartRecognition(), 250);
            }
          }

          function stopRecognition() {
            eng.wantListening = false;
            clearTimeout(eng.restartTimer);
            eng.lastStatus = "DETENIDO";
            if (eng.recognition) {
              try { eng.recognition.stop(); } catch (_) {}
            }
            eng.isRunning = false;
            syncUI();
          }

          if (!SR) {
            micBtn.disabled = true;
            micBtn.style.opacity = "0.45";
            micBtn.style.cursor = "not-allowed";
          } else {
            micBtn.onclick = () => {
              if (eng.wantListening) {
                stopRecognition();
              } else {
                eng.wantListening = true;
                eng.lastStatus = "INICIANDO";
                syncUI();
                createAndStartRecognition();
              }
            };
          }

          modeBtn.onclick = () => {
            eng.continuousMode = !eng.continuousMode;
            syncUI();
            if (eng.wantListening && eng.recognition) {
              try { eng.recognition.stop(); } catch (_) {}
            }
          };

          syncUI();
          if (eng.wantListening && !eng.isRunning) {
            createAndStartRecognition();
          }

          const ctx = canvas.getContext("2d");
          let width = 0, height = 0, rafId = 0;
          const motes = Array.from({ length: 42 }, (_, i) => ({
            angle: (Math.PI * 2 * i) / 42, radius: 58 + Math.random() * 88,
            speed: (0.002 + Math.random() * 0.004) * (i % 2 === 0 ? 1 : -1),
            size: 1 + Math.random() * 1.4, alpha: 0.18 + Math.random() * 0.45
          }));

          function resize() {
            const rect = shell.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            width = Math.max(1, rect.width); height = Math.max(1, rect.height);
            canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          }

          function draw() {
            ctx.clearRect(0, 0, width, height);
            const cx = width / 2, cy = height / 2 - 4;
            eng.pulseEnergy *= 0.92;
            const active = eng.wantListening;
            for (let i = eng.ripples.length - 1; i >= 0; i--) {
              const rp = eng.ripples[i]; rp.r += 2.6; rp.alpha *= 0.95;
              ctx.strokeStyle = `rgba(255,255,255,${rp.alpha})`; ctx.lineWidth = 1;
              ctx.beginPath(); ctx.arc(cx, cy, rp.r, 0, Math.PI * 2); ctx.stroke();
              if (rp.r > rp.maxR || rp.alpha < 0.02) eng.ripples.splice(i, 1);
            }
            for (const m of motes) {
              m.angle += m.speed * (active ? 2.4 + eng.pulseEnergy * 3.0 : 1);
              const r = m.radius + (active ? Math.sin(m.angle * 3 + eng.pulseEnergy) * (6 + eng.pulseEnergy * 18) : 0);
              ctx.fillStyle = `rgba(255,255,255,${active ? Math.min(0.95, m.alpha + 0.25) : m.alpha})`;
              ctx.fillRect(cx + Math.cos(m.angle) * r, cy + Math.sin(m.angle) * (r * 0.72), m.size, m.size);
            }
            rafId = requestAnimationFrame(draw);
          }

          const ro = new ResizeObserver(resize); ro.observe(shell); resize();
          rafId = requestAnimationFrame(draw);

          return () => {
            cancelAnimationFrame(rafId);
            ro.disconnect();
            if (eng.uiSync === syncUI) eng.uiSync = null;
            eng.stopTimer = setTimeout(() => {
              eng.wantListening = false;
              clearTimeout(eng.restartTimer);
              if (eng.recognition) {
                try { eng.recognition.abort(); } catch (_) {}
              }
              eng.isRunning = false;
            }, 600);
          };
        }
        """,
    )

    pulse_console = st.components.v2.component(
        "eq_pulse_console",
        html="""
        <div class="wrap">
          <div class="steps">
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <rect x="6" y="13" width="22" height="8" stroke="#ffffff" stroke-opacity="0.35" stroke-width="1"/>
                <rect x="8" y="15" width="8" height="4" fill="#ffffff" class="tog"/>
              </svg>
              <div><span class="snum">01</span><span class="stxt">Estado</span></div>
            </div>
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <line x1="6" y1="17" x2="28" y2="17" stroke="#ffffff" stroke-width="1.3" class="beam"/>
                <circle cx="17" cy="17" r="2.2" fill="#ffffff"/>
              </svg>
              <div><span class="snum">02</span><span class="stxt">Nivel</span></div>
            </div>
            <div class="step">
              <svg class="ico" viewBox="0 0 34 34" fill="none">
                <circle cx="17" cy="17" r="11" stroke="#ffffff" stroke-opacity="0.3" stroke-width="1"/>
                <path d="M12 17.5L15.5 21L22.5 13.5" stroke="#ffffff" stroke-width="1.5"/>
              </svg>
              <div><span class="snum">03</span><span class="stxt">Envío</span></div>
            </div>
          </div>

          <div class="eq-pulse-shell" id="pulse-shell">
            <canvas id="pulse-canvas"></canvas>
            <div class="eq-grid">
              <div class="eq-card">
                <div class="eq-card-head"><span>01 · INTERRUPTOR</span><span class="eq-state-badge" id="switch-badge">—</span></div>
                <div class="eq-btn-pair">
                  <button type="button" class="eq-act-btn" id="btn-on">
                    <span class="brk tl"></span><span class="brk tr"></span><span class="brk bl"></span><span class="brk br"></span><span class="sheen"></span>
                    <svg viewBox="0 0 28 28" fill="none" class="btn-ico"><circle cx="14" cy="14" r="10" stroke="currentColor" stroke-width="1.3"/><path d="M14 8V20" stroke="currentColor" stroke-width="1.6"/></svg>
                    <span>ENCENDER</span>
                  </button>
                  <button type="button" class="eq-act-btn" id="btn-off">
                    <span class="brk tl"></span><span class="brk tr"></span><span class="brk bl"></span><span class="brk br"></span><span class="sheen"></span>
                    <svg viewBox="0 0 28 28" fill="none" class="btn-ico"><circle cx="14" cy="14" r="10" stroke="currentColor" stroke-width="1.3"/><path d="M9 14H19" stroke="currentColor" stroke-width="1.6"/></svg>
                    <span>APAGAR</span>
                  </button>
                </div>
              </div>
              <div class="eq-card">
                <div class="eq-card-head"><span>02 · NIVEL</span><span class="eq-num-readout" id="analog-readout">50.0</span></div>
                <div class="eq-dial-row">
                  <svg class="eq-arc-svg" viewBox="0 0 96 64" fill="none">
                    <path d="M12 52 A 36 36 0 1 1 84 52" stroke="#2a2a30" stroke-width="2"/>
                    <path id="arc-fill" d="M12 52 A 36 36 0 1 1 84 52" stroke="#ffffff" stroke-width="2.2" stroke-dasharray="165" stroke-dashoffset="82"/>
                    <line id="arc-needle" x1="48" y1="48" x2="48" y2="18" stroke="#ffffff" stroke-width="1.3"/>
                    <circle cx="48" cy="48" r="2.5" fill="#ffffff"/>
                  </svg>
                  <div class="eq-slider-col">
                    <input type="range" id="analog-range" min="0" max="100" step="0.5" value="50"/>
                    <div class="eq-notches">
                      <button type="button" class="eq-notch" data-v="0">0</button>
                      <button type="button" class="eq-notch" data-v="25">25</button>
                      <button type="button" class="eq-notch" data-v="50">50</button>
                      <button type="button" class="eq-notch" data-v="75">75</button>
                      <button type="button" class="eq-notch" data-v="100">100</button>
                    </div>
                  </div>
                </div>
                <button type="button" class="eq-send-btn" id="btn-send-analog"><span class="sheen"></span>ENVIAR</button>
              </div>
            </div>
          </div>
        </div>
        """,
        css="""
        :host { display: block; width: 100%; }
        .wrap { display: flex; flex-direction: column; gap: 12px; font-family: 'Space Grotesk', system-ui, sans-serif; }
        .steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #26262b; border: 1px solid #26262b; }
        @media (max-width: 600px) { .steps { grid-template-columns: 1fr; } }
        .step { background: #0f0f11; padding: 12px 14px; display: flex; align-items: center; gap: 12px; }
        .ico { width: 32px; height: 32px; flex-shrink: 0; }
        .snum { display: block; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; letter-spacing: 0.2em; color: #8a8a93; }
        .stxt { font-size: 13px; color: #ececf0; }
        .tog { animation: togS 2.2s ease-in-out infinite; }
        .beam { transform-origin: 17px 17px; animation: tilt 3s ease-in-out infinite; }
        @keyframes togS { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(10px); } }
        @keyframes tilt { 0%, 100% { transform: rotate(-9deg); } 50% { transform: rotate(9deg); } }
        .eq-pulse-shell { position: relative; width: 100%; background: #0b0b0d; border: 1px solid #26262b; padding: 18px; box-sizing: border-box; overflow: hidden; }
        #pulse-canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
        .eq-grid { position: relative; z-index: 2; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 720px) { .eq-grid { grid-template-columns: 1fr; } }
        .eq-card { background: rgba(14,14,17,0.88); border: 1px solid #26262b; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 14px; }
        .eq-card-head { display: flex; justify-content: space-between; align-items: center; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.2em; color: #8a8a93; border-bottom: 1px solid #202025; padding-bottom: 10px; }
        .eq-state-badge, .eq-num-readout { color: #ffffff; font-weight: 500; }
        .eq-num-readout { font-size: 16px; letter-spacing: 0.12em; }
        .eq-btn-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; flex: 1; }
        .eq-act-btn { position: relative; min-height: 122px; background: #111114; border: 1px solid #2e2e35; color: #e4e4e7; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; cursor: pointer; overflow: hidden; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.22em; transition: all 180ms ease; }
        .eq-act-btn:hover { border-color: #ffffff; background: #1a1a1f; transform: translateY(-2px); }
        .eq-act-btn.active { background: #ffffff; color: #080809; border-color: #ffffff; }
        .btn-ico { width: 28px; height: 28px; }
        .brk { position: absolute; width: 7px; height: 7px; border-color: #ffffff; border-style: solid; opacity: 0.35; transition: all 200ms ease; }
        .eq-act-btn:hover .brk { opacity: 1; width: 11px; height: 11px; }
        .eq-act-btn.active .brk { border-color: #080809; opacity: 1; }
        .tl { top: 6px; left: 6px; border-width: 1px 0 0 1px; }
        .tr { top: 6px; right: 6px; border-width: 1px 1px 0 0; }
        .bl { bottom: 6px; left: 6px; border-width: 0 0 1px 1px; }
        .br { bottom: 6px; right: 6px; border-width: 0 1px 1px 0; }
        .sheen { position: absolute; inset: 0; background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.12) 50%, transparent 70%); transform: translateX(-120%); transition: transform 480ms ease; pointer-events: none; }
        .eq-act-btn:hover .sheen, .eq-send-btn:hover .sheen { transform: translateX(120%); }
        .eq-dial-row { display: flex; align-items: center; gap: 14px; }
        .eq-arc-svg { width: 88px; height: 60px; flex-shrink: 0; }
        .eq-slider-col { flex: 1; display: flex; flex-direction: column; gap: 10px; }
        input[type="range"] { -webkit-appearance: none; appearance: none; width: 100%; height: 2px; background: #34343b; outline: none; cursor: pointer; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 22px; background: #ffffff; border: 1px solid #080809; cursor: ew-resize; }
        input[type="range"]::-moz-range-thumb { width: 14px; height: 22px; border-radius: 0; background: #ffffff; border: 1px solid #080809; cursor: ew-resize; }
        .eq-notches { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; }
        .eq-notch { background: #121215; border: 1px solid #26262c; color: #8a8a93; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; padding: 4px 0; cursor: pointer; transition: all 140ms ease; }
        .eq-notch:hover { border-color: #ffffff; color: #ffffff; }
        .eq-send-btn { position: relative; overflow: hidden; width: 100%; background: #141418; border: 1px solid #4a4a54; color: #ffffff; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; letter-spacing: 0.24em; padding: 12px 14px; cursor: pointer; transition: all 180ms ease; }
        .eq-send-btn:hover { background: #ffffff; color: #080809; border-color: #ffffff; }
        """,
        js="""
        export default function(component) {
          const { data, parentElement, setTriggerValue } = component;
          const shell = parentElement.querySelector("#pulse-shell");
          const canvas = parentElement.querySelector("#pulse-canvas");
          const btnOn = parentElement.querySelector("#btn-on");
          const btnOff = parentElement.querySelector("#btn-off");
          const badge = parentElement.querySelector("#switch-badge");
          const range = parentElement.querySelector("#analog-range");
          const readout = parentElement.querySelector("#analog-readout");
          const arcFill = parentElement.querySelector("#arc-fill");
          const arcNeedle = parentElement.querySelector("#arc-needle");
          const btnSend = parentElement.querySelector("#btn-send-analog");
          const notches = parentElement.querySelectorAll(".eq-notch");
          if (!shell || !canvas || !btnOn || !btnOff || !range) return;

          const ctx = canvas.getContext("2d");
          let currentSwitch = (data && data.switch) || "";
          let currentAnalog = Number((data && data.analog) ?? 50);
          let width = 0, height = 0, rafId = 0, burst = 0, seq = 0;

          const motes = Array.from({ length: 38 }, () => ({
            x: Math.random(), y: Math.random(), speed: 0.0006 + Math.random() * 0.0014,
            size: 1 + Math.random() * 1.4, alpha: 0.14 + Math.random() * 0.4
          }));

          function syncSwitchUI() {
            btnOn.classList.toggle("active", currentSwitch === "ON");
            btnOff.classList.toggle("active", currentSwitch === "OFF");
            badge.textContent = currentSwitch === "ON" ? "ENCENDIDO" : (currentSwitch === "OFF" ? "APAGADO" : "—");
          }
          function syncAnalogUI(val) {
            currentAnalog = Math.max(0, Math.min(100, Number(val)));
            range.value = String(currentAnalog); readout.textContent = currentAnalog.toFixed(1);
            const ratio = currentAnalog / 100;
            arcFill.setAttribute("stroke-dashoffset", String(165 * (1 - ratio)));
            arcNeedle.setAttribute("transform", `rotate(${-115 + ratio * 230} 48 48)`);
          }
          function resize() {
            const rect = shell.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            width = Math.max(1, rect.width); height = Math.max(1, rect.height);
            canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          }
          function draw() {
            ctx.clearRect(0, 0, width, height); burst *= 0.92;
            const factor = (currentSwitch === "ON" ? 1.8 : (currentSwitch === "OFF" ? 0.2 : 0.65)) * (0.4 + (currentAnalog / 100) * 1.4);
            for (const m of motes) {
              m.y -= m.speed * factor * (1 + burst * 4);
              if (m.y < 0) { m.y = 1; m.x = Math.random(); }
              ctx.fillStyle = `rgba(255,255,255,${Math.min(0.85, m.alpha + burst * 0.4)})`;
              ctx.fillRect(m.x * width, m.y * height, m.size, m.size);
            }
            rafId = requestAnimationFrame(draw);
          }

          btnOn.onclick = () => {
            currentSwitch = "ON"; burst = 1.0; syncSwitchUI(); seq += 1;
            setTriggerValue("command", { kind: "switch", value: "ON", id: `${Date.now()}-${seq}` });
          };
          btnOff.onclick = () => {
            currentSwitch = "OFF"; burst = 0.6; syncSwitchUI(); seq += 1;
            setTriggerValue("command", { kind: "switch", value: "OFF", id: `${Date.now()}-${seq}` });
          };
          range.oninput = (e) => syncAnalogUI(e.target.value);
          notches.forEach((b) => { b.onclick = () => syncAnalogUI(b.dataset.v); });
          btnSend.onclick = () => {
            burst = 1.0; seq += 1;
            setTriggerValue("command", { kind: "analog", value: currentAnalog, id: `${Date.now()}-${seq}` });
          };

          syncSwitchUI(); syncAnalogUI(currentAnalog);
          const ro = new ResizeObserver(resize); ro.observe(shell); resize();
          rafId = requestAnimationFrame(draw);
          return () => { cancelAnimationFrame(rafId); ro.disconnect(); };
        }
        """,
    )

    return top_nav, inicio_board, voice_console, pulse_console


# ==============================================================================
# 3. CSS GLOBAL PURO (CON MARGEN SUPERIOR PARA LIBRAR stAppToolbar)
# ==============================================================================
st.html(
    """<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Space+Grotesk:wght@300;400;500;600&display=swap');

[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stSidebarNav"],
[data-testid="stDecoration"], footer {
  display: none !important; width: 0 !important; visibility: hidden !important;
}
html, body, [data-testid="stAppViewContainer"] {
  background-color: #080809 !important; color: #ececf0 !important;
  font-family: 'Space Grotesk', system-ui, sans-serif !important;
}
[data-testid="stAppViewContainer"] {
  background-image:
    radial-gradient(circle at 50% 0%, rgba(255,255,255,0.045), transparent 55%),
    linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px);
  background-size: 100% 100%, 48px 48px, 48px 48px;
}
[data-testid="stHeader"] {
  background: transparent !important;
  pointer-events: none !important;
}
[data-testid="stToolbar"] {
  pointer-events: none !important;
}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"] {
  pointer-events: auto !important;
}
.block-container {
  max-width: 920px !important;
  padding-top: 4.75rem !important;
  padding-bottom: 3rem !important;
}
h1, h2, h3 {
  font-family: 'Space Grotesk', sans-serif !important; font-weight: 400 !important;
  letter-spacing: 0.24em !important; text-transform: uppercase !important; color: #ffffff !important;
}
[data-testid="stLinkButton"] a {
  border: 1px solid #26262b !important; border-radius: 0px !important;
  background: #0f0f11 !important; color: #b4b4bc !important;
  padding: 0.55rem 0.9rem !important; justify-content: center !important;
  transition: all 180ms ease !important;
}
[data-testid="stLinkButton"] a p {
  font-family: 'IBM Plex Mono', monospace !important; font-size: 0.76rem !important;
  letter-spacing: 0.22em !important; text-transform: uppercase !important; margin: 0 !important;
}
[data-testid="stLinkButton"] a:hover {
  border-color: #ffffff !important; background: #ffffff !important; color: #080809 !important;
}
[data-testid="stLinkButton"] a:hover p { color: #080809 !important; }
[data-testid="stFormSubmitButton"] > button, .stButton > button {
  border-radius: 0px !important; border: 1px solid #4a4a52 !important;
  background: #0f0f11 !important; color: #ffffff !important;
  font-family: 'IBM Plex Mono', monospace !important; font-size: 0.75rem !important;
  letter-spacing: 0.2em !important; text-transform: uppercase !important; transition: all 180ms ease !important;
}
[data-testid="stFormSubmitButton"] > button:hover, .stButton > button:hover {
  background: #ffffff !important; color: #080809 !important; border-color: #ffffff !important;
}
[data-testid="stTextInput"] input {
  border-radius: 0px !important; border: 1px solid #26262b !important;
  background: #0f0f11 !important; color: #ffffff !important;
}
[data-testid="stTextInput"] input:focus { border-color: #ffffff !important; box-shadow: none !important; }
[data-testid="stCaptionContainer"] p {
  font-family: 'IBM Plex Mono', monospace !important; font-size: 0.76rem !important;
  letter-spacing: 0.08em !important; color: #8a8a93 !important;
}
iframe {
  border: 1px solid #26262b !important;
  background: #0b0b0d !important;
}
hr { border-color: #202025 !important; }
</style>"""
)

top_nav, inicio_board, voice_console, pulse_console = get_components()
st.session_state["_eq"] = {
    "get_channel": get_mqtt_channel,
    "voice_console": voice_console,
    "pulse_console": pulse_console,
}


# ==============================================================================
# 4. NAVEGACIÓN ENTRE LAS 3 APPS (RAÍZ /, /voz, /pulso)
# ==============================================================================
def _handle_nav(nav_payload: dict | None, current_title: str) -> None:
    if not nav_payload:
        return
    ts = nav_payload.get("ts")
    if ts and ts != st.session_state.get("_last_nav_ts"):
        st.session_state["_last_nav_ts"] = ts
        target = nav_payload.get("page")
        if target == "Inicio" and current_title != "Inicio":
            st.switch_page(page_inicio)
        elif target == "Voz" and current_title != "Voz":
            st.switch_page(page_voz)
        elif target == "Pulso" and current_title != "Pulso":
            st.switch_page(page_pulso)


def render_inicio() -> None:
    st.session_state.pop("pulso_boot", None)
    st.subheader("CONTROL")
    board_res = inicio_board(key="eq_inicio_board", on_nav_change=lambda: None)
    _handle_nav(getattr(board_res, "nav", None), "Inicio")


page_inicio = st.Page(render_inicio, title="Inicio", default=True)
page_voz = st.Page("pages/1_Control_por_voz.py", title="Voz", url_path="voz")
page_pulso = st.Page("pages/2_Control_MQTT.py", title="Pulso", url_path="pulso")

current_page = st.navigation([page_inicio, page_voz, page_pulso], position="hidden")

nav_res = top_nav(
    key="eq_top_nav",
    data={"active": current_page.title},
    on_nav_change=lambda: None,
)
_handle_nav(getattr(nav_res, "nav", None), current_page.title)

current_page.run()


# ==============================================================================
# 5. MARCO PERMANENTE DE WOKWI (SIN CAMPO DE TEXTO)
# ==============================================================================
st.divider()
c_title, c_link = st.columns([3, 1], vertical_alignment="center")
with c_title:
    st.subheader("SIMULADOR")
with c_link:
    st.link_button("ABRIR EN WOKWI", WOKWI_URL, width="stretch")

components.iframe(WOKWI_URL, height=520, scrolling=True)
