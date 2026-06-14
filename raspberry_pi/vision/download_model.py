"""
Downloads a pre-trained MobileNetV2 TFLite model fine-tuned on PlantVillage.
Run once on the Raspberry Pi before starting the dashboard:

    cd raspberry_pi/vision
    python download_model.py
"""

import os
import urllib.request
import zipfile
import json

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# 38-class PlantVillage labels (matches standard PlantVillage split)
LABELS = [
    "Apple___Apple_scab", "Apple___Black_rot", "Apple___Cedar_apple_rust", "Apple___healthy",
    "Blueberry___healthy", "Cherry___Powdery_mildew", "Cherry___healthy",
    "Corn___Cercospora_leaf_spot", "Corn___Common_rust", "Corn___Northern_Leaf_Blight", "Corn___healthy",
    "Grape___Black_rot", "Grape___Esca_Black_Measles", "Grape___Leaf_blight", "Grape___healthy",
    "Orange___Haunglongbing", "Peach___Bacterial_spot", "Peach___healthy",
    "Pepper___Bacterial_spot", "Pepper___healthy",
    "Potato___Early_blight", "Potato___Late_blight", "Potato___healthy",
    "Raspberry___healthy", "Soybean___healthy",
    "Squash___Powdery_mildew", "Strawberry___Leaf_scorch", "Strawberry___healthy",
    "Tomato___Bacterial_spot", "Tomato___Early_blight", "Tomato___Late_blight",
    "Tomato___Leaf_Mold", "Tomato___Septoria_leaf_spot",
    "Tomato___Spider_mites", "Tomato___Target_Spot",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato___Tomato_mosaic_virus", "Tomato___healthy",
]

def write_labels():
    path = os.path.join(MODELS_DIR, "labels.txt")
    with open(path, "w") as f:
        f.write("\n".join(LABELS))
    print(f"Labels written → {path}")

def download_model():
    """
    Try to fetch a publicly available TFLite plant disease model.
    Falls back to a notice if the URL is unavailable.

    For production, use one of:
    - TensorFlow Hub: https://tfhub.dev/google/lite-model/imagenet/mobilenet_v2_100_224/classification/5/default/1
      (fine-tune on PlantVillage yourself with transfer learning)
    - Kaggle dataset + custom training script in scripts/train_model.py
    """
    model_path = os.path.join(MODELS_DIR, "plant_disease.tflite")
    if os.path.exists(model_path):
        print(f"Model already exists at {model_path}")
        return

    # Prefer a small Plant-disease model hosted on GitHub (fallback URL)
    # This repository includes a prebuilt TFLite from community projects.
    # You can replace this with your own hosted .tflite URL.
    url = "https://raw.githubusercontent.com/akshayrana30/plant-disease-detection/master/model/model.tflite"

    print(f"Downloading model from {url} ...")
    try:
        # If the URL points directly to a .tflite file, save it to model_path
        if url.lower().endswith('.tflite'):
            urllib.request.urlretrieve(url, model_path)
            print(f"Model downloaded → {model_path}")
        else:
            # Otherwise assume a zip archive containing a .tflite
            zip_path = os.path.join(MODELS_DIR, "mobilenet_tmp.zip")
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as z:
                for name in z.namelist():
                    if name.endswith(".tflite"):
                        data = z.read(name)
                        with open(model_path, "wb") as f:
                            f.write(data)
                        print(f"Model extracted → {model_path}")
                        break
            os.remove(zip_path)
        print("\nNOTE: Verify this model's labels and accuracy for your use-case.")
        print("For best results fine-tune on PlantVillage using scripts/train_model.py")
    except Exception as e:
        print(f"Download failed: {e}")
        print("You can manually place your .tflite model at:", model_path)

if __name__ == "__main__":
    write_labels()
    download_model()
    print("\nSetup complete. Start the dashboard with:")
    print("  cd raspberry_pi && python dashboard/app.py")
