"""
Transfer-learning training script — fine-tunes MobileNetV2 on PlantVillage.
Run on a PC/cloud GPU, then copy the .tflite output to the Pi.

Requirements (install on training machine, NOT the Pi):
    pip install tensorflow pillow

PlantVillage dataset:
    Download from Kaggle: https://www.kaggle.com/datasets/emmarex/plantdisease
    Extract to:  data/PlantVillage/  (each class in its own subdirectory)

Usage:
    python scripts/train_model.py --data data/PlantVillage --epochs 15 --output raspberry_pi/vision/models/plant_disease.tflite
"""

import argparse
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",    default="data/PlantVillage")
    parser.add_argument("--epochs",  type=int, default=15)
    parser.add_argument("--output",  default="raspberry_pi/vision/models/plant_disease.tflite")
    parser.add_argument("--img-size",type=int, default=224)
    parser.add_argument("--batch",   type=int, default=32)
    args = parser.parse_args()

    try:
        import tensorflow as tf
    except ImportError:
        print("TensorFlow not found. Install with: pip install tensorflow")
        return

    IMG_SIZE  = (args.img_size, args.img_size)
    AUTOTUNE  = tf.data.AUTOTUNE

    print(f"Loading dataset from {args.data} ...")
    train_ds = tf.keras.preprocessing.image_dataset_from_directory(
        args.data,
        validation_split=0.2,
        subset="training",
        seed=42,
        image_size=IMG_SIZE,
        batch_size=args.batch,
        label_mode="categorical",
    )
    val_ds = tf.keras.preprocessing.image_dataset_from_directory(
        args.data,
        validation_split=0.2,
        subset="validation",
        seed=42,
        image_size=IMG_SIZE,
        batch_size=args.batch,
        label_mode="categorical",
    )
    class_names = train_ds.class_names
    num_classes = len(class_names)
    print(f"Found {num_classes} classes")

    # Save updated labels
    labels_path = os.path.join(os.path.dirname(args.output), "labels.txt")
    with open(labels_path, "w") as f:
        f.write("\n".join(class_names))
    print(f"Labels saved → {labels_path}")

    # Normalize
    normalization = tf.keras.layers.Rescaling(1.0 / 255)
    train_ds = train_ds.map(lambda x, y: (normalization(x), y)).cache().shuffle(1000).prefetch(AUTOTUNE)
    val_ds   = val_ds.map(lambda x, y: (normalization(x), y)).cache().prefetch(AUTOTUNE)

    # Build model
    base_model = tf.keras.applications.MobileNetV2(
        input_shape=IMG_SIZE + (3,), include_top=False, weights="imagenet"
    )
    base_model.trainable = False   # freeze base during head training

    model = tf.keras.Sequential([
        base_model,
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    print("\n--- Phase 1: Head training ---")
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs // 2)

    # Fine-tune top layers of base model
    base_model.trainable = True
    for layer in base_model.layers[:-30]:
        layer.trainable = False
    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-5),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    print("\n--- Phase 2: Fine-tuning ---")
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs - args.epochs // 2)

    # Convert to TFLite
    print("\nConverting to TFLite ...")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]  # quantize for Pi speed
    tflite_model = converter.convert()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "wb") as f:
        f.write(tflite_model)
    print(f"TFLite model saved → {args.output}")
    print("Copy this file to your Raspberry Pi and restart the dashboard.")

if __name__ == "__main__":
    main()
