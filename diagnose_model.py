"""
Quick model diagnostic - run this from project root:
  .venv\Scripts\python.exe diagnose_model.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ["TORCHDYNAMO_DISABLE"] = "1"

import torch
from torchvision import models
import torch.nn as nn

MODEL_PATH = os.path.join('backend', 'model', 'skin_cancer_densenet_v2_final.pth')

print("=" * 60)
print("STEP 1: Load raw checkpoint")
print("=" * 60)
ck = torch.load(MODEL_PATH, map_location='cpu', weights_only=False)
if isinstance(ck, dict):
    print(f"  Type: dict, top-level keys: {list(ck.keys())}")
    # Find the state dict
    if 'model_state' in ck:
        sd = ck['model_state']
    elif 'state_dict' in ck:
        sd = ck['state_dict']
    elif 'model' in ck:
        sd = ck['model']
    else:
        sd = ck
else:
    sd = ck

all_keys = list(sd.keys())
print(f"  Total saved keys: {len(all_keys)}")
print(f"  First 5 keys: {all_keys[:5]}")
print(f"  Last  5 keys: {all_keys[-5:]}")

print()
print("=" * 60)
print("STEP 2: Build model and compare keys")
print("=" * 60)

CLASSES = ['No Cancer', 'Melanoma', 'Basal Cell Carcinoma', 'Actinic Keratosis', 'Squamous Cell Carcinoma']

def build_model():
    m = models.densenet121(weights=None)
    in_features = m.classifier.in_features
    m.classifier = nn.Sequential(
        nn.Linear(in_features, 512),
        nn.BatchNorm1d(512),
        nn.ReLU(),
        nn.Dropout(0.4),
        nn.Linear(512, 256),
        nn.BatchNorm1d(256),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(256, len(CLASSES)),
    )
    return m

model = build_model()
model_keys = set(model.state_dict().keys())
saved_keys = set(all_keys)

# Strip 'module.' prefix
stripped = {k.replace('module.', ''): v for k, v in sd.items()}
stripped_keys = set(stripped.keys())

missing_from_saved    = model_keys - stripped_keys
extra_in_saved        = stripped_keys - model_keys
matched               = model_keys & stripped_keys

print(f"  Expected keys         : {len(model_keys)}")
print(f"  Matched keys          : {len(matched)}")
print(f"  Missing from .pth     : {len(missing_from_saved)}")
print(f"  Extra in .pth (unused): {len(extra_in_saved)}")

if missing_from_saved:
    print(f"  Missing examples: {list(missing_from_saved)[:5]}")
if extra_in_saved:
    print(f"  Extra examples:   {list(extra_in_saved)[:5]}")

print()
print("=" * 60)
print("STEP 3: Load and run inference on dummy image")
print("=" * 60)

result = model.load_state_dict(stripped, strict=False)
model.eval()

import numpy as np
from PIL import Image
from torchvision import transforms

# Create a dummy skin-colored patch
img = Image.fromarray(np.random.randint(150, 200, (224, 224, 3), dtype=np.uint8))
MEAN = [0.7216, 0.5765, 0.5725]
STD  = [0.1404, 0.1501, 0.1669]
tf = transforms.Compose([transforms.Resize((224,224)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
t = tf(img).unsqueeze(0)

with torch.no_grad():
    logits = model(t)
    probs  = torch.softmax(logits, dim=1)[0]

print("  Class probabilities on random image:")
for i, cls in enumerate(CLASSES):
    print(f"    {cls:30s}: {probs[i].item():.4f}")

top_idx  = probs.argmax().item()
print(f"\n  TOP PREDICTION: {CLASSES[top_idx]} ({probs[top_idx].item()*100:.1f}%)")

# If the model always says "No Cancer" on random noise, the weights are random
if CLASSES[top_idx] == 'No Cancer' and probs[top_idx] > 0.85:
    print("\n  ⚠️  WARNING: Very high confidence 'No Cancer' on random noise.")
    print("     This strongly suggests weights did NOT load correctly.")
    print("     The model is running with random/untrained weights.")
else:
    print("\n  ✅ Model appears to have real learned weights (varied predictions on noise).")
