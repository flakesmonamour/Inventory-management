"""
Run this ONCE from your Python venv (the one that trained lstm_best_model.keras),
from inside the store/ folder:

    python export_lstm_weights.py

It loads the already-trained Python model and re-saves just its weights to an
HDF5 file. Weight files don't carry Keras-version-specific config formatting,
so R can load them even if R's reticulate Python has an older Keras version
than the one that originally trained the model.
"""
from tensorflow import keras

model = keras.models.load_model("lstm_best_model.keras")
model.save_weights("lstm_best_model.weights.h5")
print("Saved lstm_best_model_weights.h5 next to lstm_best_model.keras")