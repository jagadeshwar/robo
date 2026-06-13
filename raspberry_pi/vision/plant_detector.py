"""
Plant disease detector — works from uploaded image files (no camera required).
Uses TensorFlow Lite for on-device inference on Raspberry Pi 5.

Supported labels (PlantVillage dataset subset — 38 classes):
  See models/labels.txt after downloading the model.

Quick-start without a real model:
  Run `python download_model.py` in this folder to fetch a pre-trained
  MobileNetV2 model fine-tuned on PlantVillage.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Optional TFLite import — graceful fallback so the app starts even if
# tflite_runtime is not yet installed on the Pi.
try:
    from tflite_runtime.interpreter import Interpreter
    _TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow as tf
        Interpreter = tf.lite.Interpreter
        _TFLITE_AVAILABLE = True
    except ImportError:
        _TFLITE_AVAILABLE = False
        logger.warning("TFLite not available — detector will return mock results.")


HEALTHY_KEYWORDS = {"healthy"}


class PlantDetector:
    def __init__(self, model_path: str, labels_path: str, img_size: tuple = (224, 224)):
        self.img_size    = img_size
        self.labels      = self._load_labels(labels_path)
        self.interpreter = None

        if _TFLITE_AVAILABLE and os.path.exists(model_path):
            self.interpreter = Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            self._input_details  = self.interpreter.get_input_details()
            self._output_details = self.interpreter.get_output_details()
            logger.info("TFLite model loaded from %s (%d classes)", model_path, len(self.labels))
        else:
            if not os.path.exists(model_path):
                logger.warning("Model file not found at %s — using mock detector", model_path)

    # ── public API ──────────────────────────────────────────────────────────────

    def analyze(self, image_path: str) -> dict:
        """
        Analyze a plant image file and return a result dict:
        {
          "label":      str,       # top predicted class e.g. "Tomato Early Blight"
          "plant":      str,       # plant name e.g. "Tomato"
          "disease":    str,       # disease name or "Healthy"
          "is_healthy": bool,
          "confidence": float,     # 0.0 – 1.0
          "all_scores": [          # top-5 sorted descending
              {"label": str, "confidence": float}, ...
          ],
          "action":     str,       # recommended action for the robot
          "error":      str | None
        }
        """
        try:
            img = self._preprocess(image_path)
        except Exception as e:
            return self._error(str(e))

        if self.interpreter is None:
            return self._mock_result(image_path)

        try:
            scores = self._run_inference(img)
        except Exception as e:
            return self._error(f"Inference failed: {e}")

        return self._build_result(scores)

    # ── internals ───────────────────────────────────────────────────────────────

    def _preprocess(self, path: str) -> np.ndarray:
        img = Image.open(path).convert("RGB").resize(self.img_size)
        arr = np.array(img, dtype=np.float32) / 255.0
        return np.expand_dims(arr, axis=0)   # shape (1, H, W, 3)

    def _run_inference(self, img: np.ndarray) -> np.ndarray:
        self.interpreter.set_tensor(self._input_details[0]["index"], img)
        self.interpreter.invoke()
        raw = self.interpreter.get_tensor(self._output_details[0]["index"])[0]
        # Softmax if logits (max > 1.0 indicates raw logits)
        if raw.max() > 1.0:
            e = np.exp(raw - raw.max())
            raw = e / e.sum()
        return raw

    def _build_result(self, scores: np.ndarray) -> dict:
        top_idx   = int(np.argmax(scores))
        top_score = float(scores[top_idx])
        label     = self.labels[top_idx] if top_idx < len(self.labels) else f"class_{top_idx}"

        top5_idx  = np.argsort(scores)[::-1][:5]
        all_scores = [
            {"label": self.labels[i] if i < len(self.labels) else f"class_{i}",
             "confidence": round(float(scores[i]), 4)}
            for i in top5_idx
        ]

        plant, disease = self._split_label(label)
        is_healthy     = any(kw in disease.lower() for kw in HEALTHY_KEYWORDS)
        action         = self._recommend_action(is_healthy, disease, top_score)

        return {
            "label":      label,
            "plant":      plant,
            "disease":    disease,
            "is_healthy": is_healthy,
            "confidence": round(top_score, 4),
            "all_scores": all_scores,
            "action":     action,
            "error":      None,
        }

    @staticmethod
    def _split_label(label: str) -> tuple:
        # PlantVillage labels look like "Tomato___Early_blight" or "Tomato_healthy"
        parts = label.replace("___", "|").replace("__", "|").split("|")
        if len(parts) >= 2:
            return parts[0].replace("_", " "), parts[1].replace("_", " ").title()
        return label, label

    @staticmethod
    def _recommend_action(is_healthy: bool, disease: str, conf: float) -> str:
        if conf < 0.50:
            return "LOW_CONFIDENCE — take another photo in better lighting"
        if is_healthy:
            return "NO_ACTION — plant appears healthy"
        disease_lower = disease.lower()
        if any(w in disease_lower for w in ["blight", "spot", "mold", "mildew", "rust"]):
            return "SPRAY_FUNGICIDE"
        if any(w in disease_lower for w in ["virus", "mosaic", "curl"]):
            return "SPRAY_INSECTICIDE — check for aphids/whitefly"
        if "weed" in disease_lower:
            return "ACTIVATE_WEED_REMOVER"
        return "SPRAY_GENERAL_TREATMENT"

    @staticmethod
    def _load_labels(path: str) -> list:
        if not os.path.exists(path):
            logger.warning("Labels file not found: %s", path)
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    @staticmethod
    def _error(msg: str) -> dict:
        return {
            "label": "", "plant": "", "disease": "",
            "is_healthy": None, "confidence": 0.0,
            "all_scores": [], "action": "ERROR", "error": msg
        }

    def _mock_result(self, path: str) -> dict:
        """Deterministic mock result for development without a real model."""
        fname = Path(path).stem.lower()
        if "healthy" in fname:
            label, disease = "Tomato___Healthy", "Healthy"
            is_healthy, action = True, "NO_ACTION — plant appears healthy"
        elif "blight" in fname:
            label, disease = "Tomato___Early_blight", "Early Blight"
            is_healthy, action = False, "SPRAY_FUNGICIDE"
        else:
            label, disease = "Tomato___Late_blight", "Late Blight"
            is_healthy, action = False, "SPRAY_FUNGICIDE"
        return {
            "label": label, "plant": "Tomato", "disease": disease,
            "is_healthy": is_healthy, "confidence": 0.88,
            "all_scores": [{"label": label, "confidence": 0.88}],
            "action": action, "error": None,
        }
