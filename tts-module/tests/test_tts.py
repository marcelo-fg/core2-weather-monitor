"""
tests/test_tts.py
=================
Rôle du fichier :
Tests automatiques du module TTS, exécutables avec pytest.

Point CLÉ : on ne veut PAS appeler la vraie API Google pendant les tests
(ça coûte de l'argent et exige des credentials valides). On "mocke" donc
(= on remplace par une fausse version) la fonction qui parle à Google.
Ainsi les tests sont rapides, gratuits, et fonctionnent partout.

Pour lancer les tests, depuis la racine du projet :
    pytest
"""

import pytest

import config
from tts import announcements, cache
from tts import service
from tts import stt
from tts import llm
from app import create_app


# ===========================================================================
# Fixture : un client de test Flask, avec Google "mocké" et cache temporaire
# ===========================================================================

@pytest.fixture
def client(monkeypatch, tmp_path):
    """Prépare un environnement de test isolé et renvoie un client Flask.

    - monkeypatch : outil pytest pour remplacer temporairement des fonctions/
                    variables le temps d'un test.
    - tmp_path    : dossier temporaire fourni par pytest (nettoyé automatiquement).
    """

    # 1) On remplace l'appel Google par une fausse fonction qui renvoie des
    #    octets bidon. Ainsi AUCUN appel réseau réel n'a lieu.
    def fake_synth(text):
        return b"FAKE_WAV_BYTES"

    monkeypatch.setattr(service, "synthesize_to_wav", fake_synth)

    # 2) On mocke aussi la reconnaissance vocale (Google STT) et le LLM (Google
    #    Gemini), pour tester l'endpoint /listen SANS appel réseau réel ni credentials.
    #    On remplace directement generate_reply : le test reste donc valable quel
    #    que soit le fournisseur LLM utilisé derrière (OpenAI hier, Gemini aujourd'hui).
    monkeypatch.setattr(stt, "transcribe_wav", lambda audio: "Quelle est la température ?")
    monkeypatch.setattr(llm, "generate_reply", lambda texte: "Il fait dix-huit degrés.")

    # 3) On redirige le cache vers un dossier temporaire (on ne pollue pas le projet).
    monkeypatch.setattr(config, "AUDIO_CACHE_DIR", str(tmp_path))

    # 4) On vide la mémoire du rate-limiting pour partir d'un état propre.
    announcements._last_announced.clear()

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


# ===========================================================================
# Tests de la logique des annonces
# ===========================================================================

def test_morning_briefing_mentionne_parapluie_si_pluie():
    """Avec rain=True, l'annonce matinale DOIT parler de parapluie."""
    texte = announcements.build_announcement_text(
        "morning_briefing", {"temp": 18, "rain": True, "humidity": 35}
    )
    assert "parapluie" in texte.lower()


def test_morning_briefing_sans_pluie():
    """Avec rain=False, l'annonce ne doit PAS parler de parapluie."""
    texte = announcements.build_announcement_text(
        "morning_briefing", {"temp": 18, "rain": False, "humidity": 35}
    )
    assert "parapluie" not in texte.lower()


def test_tous_les_event_types_supportes():
    """Chaque event_type prévu doit produire un texte non vide."""
    for event_type in [
        "morning_briefing",
        "humidity_alert",
        "air_quality_alert",
        "welcome",
        "weather_update",
    ]:
        texte = announcements.build_announcement_text(event_type)
        assert isinstance(texte, str)
        assert len(texte) > 0


def test_event_type_inconnu_leve_erreur():
    """Un event_type inconnu doit lever une ValueError."""
    with pytest.raises(ValueError):
        announcements.build_announcement_text("event_qui_nexiste_pas")


# ===========================================================================
# Tests du rate-limiting
# ===========================================================================

def test_rate_limiting():
    """Après une émission, le même event_type doit être bloqué."""
    announcements._last_announced.clear()

    # Au départ : jamais émis -> pas bloqué.
    assert announcements.is_rate_limited("welcome") is False

    # On marque comme émis.
    announcements.mark_announced("welcome")

    # Maintenant : émis il y a < 1h -> bloqué.
    assert announcements.is_rate_limited("welcome") is True


# ===========================================================================
# Tests du cache
# ===========================================================================

def test_cache_save_then_get(monkeypatch, tmp_path):
    """Ce qu'on sauvegarde doit pouvoir être relu à l'identique."""
    monkeypatch.setattr(config, "AUDIO_CACHE_DIR", str(tmp_path))

    cache.save_audio("Bonjour", b"123")
    assert cache.get_cached_audio("Bonjour") == b"123"

    # Un texte jamais sauvegardé renvoie None.
    assert cache.get_cached_audio("JamaisVu") is None


# ===========================================================================
# Tests des routes Flask (via le client de test)
# ===========================================================================

def test_health(client):
    """GET /health doit répondre 200 avec {"status": "ok"}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_speak_ok(client):
    """POST /speak avec un texte valide doit renvoyer du WAV."""
    resp = client.post("/speak", json={"text": "Bonjour le monde"})
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"
    assert resp.data == b"FAKE_WAV_BYTES"


def test_speak_sans_texte(client):
    """POST /speak sans champ 'text' doit renvoyer une erreur 400."""
    resp = client.post("/speak", json={})
    assert resp.status_code == 400


def test_announce_ok(client):
    """POST /announce avec un event_type valide doit renvoyer du WAV."""
    resp = client.post("/announce", json={"event_type": "welcome"})
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"


def test_announce_rate_limited(client):
    """La 2e annonce identique immédiate doit être refusée (429)."""
    r1 = client.post("/announce", json={"event_type": "welcome"})
    assert r1.status_code == 200

    r2 = client.post("/announce", json={"event_type": "welcome"})
    assert r2.status_code == 429


def test_announce_force_bypass_rate_limit(client):
    """Avec 'force': true, le rate-limiting est contourné (toujours 200)."""
    r1 = client.post("/announce", json={"event_type": "welcome"})
    assert r1.status_code == 200

    # Sans force -> bloqué (429).
    assert client.post("/announce", json={"event_type": "welcome"}).status_code == 429

    # Avec force -> passe quand même (200).
    r3 = client.post("/announce", json={"event_type": "welcome", "force": True})
    assert r3.status_code == 200
    assert r3.mimetype == "audio/wav"


def test_announce_event_inconnu(client):
    """POST /announce avec un event_type inconnu doit renvoyer 400."""
    resp = client.post("/announce", json={"event_type": "blabla"})
    assert resp.status_code == 400


# ===========================================================================
# Tests de l'endpoint /listen (mode conversation : voix -> texte -> LLM -> voix)
# ===========================================================================

def test_listen_ok(client):
    """POST /listen avec de l'audio doit renvoyer un WAV de réponse."""
    # On envoie des octets bidon : la transcription est mockée de toute façon.
    resp = client.post("/listen", data=b"FAUX_AUDIO_WAV", content_type="audio/wav")
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"
    assert resp.data == b"FAKE_WAV_BYTES"


def test_listen_sans_audio(client):
    """POST /listen sans audio doit renvoyer une erreur 400."""
    resp = client.post("/listen", data=b"", content_type="audio/wav")
    assert resp.status_code == 400


def test_listen_transcription_vide(client, monkeypatch):
    """Si Google ne comprend rien, on renvoie quand même un WAV (message poli)."""
    # On remplace la transcription mockée par une chaîne vide.
    monkeypatch.setattr(stt, "transcribe_wav", lambda audio: "")
    resp = client.post("/listen", data=b"FAUX_AUDIO_WAV", content_type="audio/wav")
    assert resp.status_code == 200
    assert resp.mimetype == "audio/wav"


def test_listen_llm_en_panne(client, monkeypatch):
    """Si le LLM lève une exception, on renvoie une erreur 503 (pas de crash)."""
    def llm_qui_plante(texte):
        raise RuntimeError("Gemini indisponible")

    monkeypatch.setattr(llm, "generate_reply", llm_qui_plante)
    resp = client.post("/listen", data=b"FAUX_AUDIO_WAV", content_type="audio/wav")
    assert resp.status_code == 503
