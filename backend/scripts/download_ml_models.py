"""Pre-download offline ML models for speech-to-text (Whisper) and
vernacular translation (IndicTrans2) for Phase 1/Phase 3 (Owner: S6).

Whisper is downloaded via faster-whisper (CTranslate2), not openai-whisper,
because plan §Phase1 pre-Phase-1-action and Architecture §9.15 both call for
a *quantized* model specifically — quantization is what makes STT viable on
lower-spec edge hardware, which is the whole point of a local fallback for
the least-connected persona. openai-whisper's load_model() downloads a
full-precision checkpoint; it is not a substitute for this.

These are backend deps (backend/requirements.txt), not root — Agent 1 (User
Interaction) is the actual consumer of both models in Phase 1, and this
script only pre-warms the same cache huggingface_hub/faster-whisper read
from at runtime.

Usage (from backend/, with backend/.venv active):
    pip install -r requirements.txt
    python scripts/download_ml_models.py

Also needed at inference time (not for this download step): ffmpeg on PATH,
for faster-whisper/CTranslate2 to decode audio.
"""
import io
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def download_whisper():
    print("\n[1/2] Downloading quantized Whisper model (faster-whisper, int8, for Voice STT)...")
    try:
        from faster_whisper import WhisperModel
        # 'small', int8 — CTranslate2-quantized (~464MB on disk, confirmed by
        # running this), ~2x faster on CPU than full precision (plan/Architecture
        # §9.15). Instantiating triggers the download and cache; no transcription
        # needed for that.
        WhisperModel("small", device="cpu", compute_type="int8")
        print("[OK] faster-whisper ('small', int8) downloaded and cached successfully!")
    except ImportError:
        print("[WARN] 'faster-whisper' not installed in this environment. Run: pip install faster-whisper")
    except Exception as e:  # noqa: BLE001 — best-effort setup script, report and continue
        print(f"[ERROR] Error downloading Whisper: {e}")

def download_indictrans2():
    print("\n[2/2] Downloading AI4Bharat IndicTrans2 models (for Tamil/Hindi translation)...")
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import GatedRepoError

        # Both repos are gated (auto-approved, but still requires being logged
        # in) — confirmed by an actual anonymous download attempt, not assumed.
        # One-time setup: accept the license on each model page while logged
        # into huggingface.co, then `huggingface-cli login` (or set HF_TOKEN)
        # in this environment before running this script.
        for repo_id, direction in [
            ("ai4bharat/indictrans2-indic-en-dist-200M", "Indic -> English"),
            ("ai4bharat/indictrans2-en-indic-dist-200M", "English -> Indic"),
        ]:
            print(f"Downloading {direction} ({repo_id})...")
            snapshot_download(repo_id=repo_id)

        print("[OK] IndicTrans2 translation models downloaded and cached successfully!")
    except ImportError:
        print("[WARN] 'huggingface_hub' not installed in this environment. Run: pip install huggingface_hub")
    except GatedRepoError:
        print(
            "[ERROR] Both IndicTrans2 repos are gated. One-time setup per machine:\n"
            "  1. Log in at https://huggingface.co and accept the license on\n"
            "     https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M and\n"
            "     https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M\n"
            "  2. pip install -U huggingface_hub[cli]\n"
            "  3. huggingface-cli login   (paste a token from https://huggingface.co/settings/tokens)\n"
            "  Then re-run this script."
        )
    except Exception as e:  # noqa: BLE001 — best-effort setup script, report and continue
        print(f"[ERROR] Error downloading IndicTrans2: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("ORCA — Pre-Downloading Local ML Models for S6")
    print("=" * 60)
    download_whisper()
    download_indictrans2()
    print("\nDone! Weights are cached in your local user directory (~/.cache).")
