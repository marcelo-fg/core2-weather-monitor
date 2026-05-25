import streamlit as st
import sys
import os

# Add parent directory to path so we can import services
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.api_client import post_device_command, post_stt_only, post_process_text_to_device

st.set_page_config(
    page_title="M5Stack Remote",
    page_icon="📱",
    layout="centered",
)

# Responsive mobile-first CSS
st.markdown("""
<style>
    /* Big buttons for touch */
    .stButton>button {
        height: 60px;
        font-size: 18px;
        border-radius: 12px;
    }
    
    /* Header styling */
    .remote-header {
        text-align: center;
        padding-bottom: 20px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 20px;
    }
    
    /* Hide some Streamlit chrome for a cleaner app feel */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='remote-header'><h2>📱 Télécommande M5Stack</h2></div>", unsafe_allow_html=True)

# --- 1. Screen & Hardware Controls ---
st.subheader("🖥️ Écran & Matériel")

col_bri, col_vol = st.columns(2)

with col_bri:
    brightness = st.slider("Luminosité", min_value=0, max_value=100, value=50, step=10)
    if st.button("Set Luminosité", use_container_width=True):
        if post_device_command("set_brightness", brightness):
            st.toast("Luminosité mise à jour !", icon="✅")
        else:
            st.toast("Erreur réseau", icon="❌")

with col_vol:
    volume = st.slider("Volume", min_value=0, max_value=100, value=100, step=10)
    if st.button("Set Volume", use_container_width=True):
        if post_device_command("set_volume", volume):
            st.toast("Volume mis à jour !", icon="✅")
        else:
            st.toast("Erreur réseau", icon="❌")

st.markdown("<br>", unsafe_allow_html=True)

# --- 2. Page Navigation ---
st.subheader("📄 Navigation Pages")

pcol1, pcol2 = st.columns(2)
pcol3, pcol4 = st.columns(2)

def set_page(idx):
    if post_device_command("set_page", idx):
        st.toast(f"Page {idx} activée !", icon="✅")
    else:
        st.toast("Erreur réseau", icon="❌")

with pcol1:
    if st.button("0 - Accueil", use_container_width=True): set_page(0)
with pcol2:
    if st.button("1 - Prévisions", use_container_width=True): set_page(1)
with pcol3:
    if st.button("2 - Historique", use_container_width=True): set_page(2)
with pcol4:
    if st.button("3 - Paramètres", use_container_width=True): set_page(3)

st.markdown("<br>", unsafe_allow_html=True)

# --- 3. Voice Assistant (2-Step) ---
st.subheader("🎙️ Assistant Vocal")

st.markdown("""
*Étape 1 : Enregistrez votre message.*
""")
audio_val = st.audio_input("Parlez", label_visibility="collapsed")

if audio_val is not None:
    # Si c'est un nouvel enregistrement, on fait juste le STT (sans LLM)
    if "last_audio_bytes" not in st.session_state or st.session_state["last_audio_bytes"] != audio_val.getvalue():
        st.info("Traduction en texte...")
        audio_bytes = audio_val.getvalue()
        resp = post_stt_only(audio_bytes)
        
        if resp and resp.get("status") == "ok":
            st.session_state["transcript"] = resp.get("transcript", "")
            st.session_state["last_audio_bytes"] = audio_bytes
        else:
            st.error("Erreur de reconnaissance vocale.")

if "transcript" in st.session_state:
    st.markdown("*Étape 2 : Vérifiez et modifiez si besoin, puis envoyez.*")
    edited_text = st.text_input("Texte reconnu :", value=st.session_state["transcript"])
    
    if st.button("🚀 Envoyer au M5Stack", type="primary", use_container_width=True):
        if edited_text.strip():
            st.info("Génération de la réponse IA...")
            # Envoi du texte final au LLM et génération du TTS
            resp = post_process_text_to_device(edited_text, {})
            if resp and resp.get("status") == "ok":
                st.success("✅ Réponse envoyée ! Le M5Stack va parler dans quelques secondes.")
            else:
                st.error("Erreur lors de la génération de la réponse.")
        else:
            st.warning("Le texte est vide.")
