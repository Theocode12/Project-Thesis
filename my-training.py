# ==========================================================
# Imports
# ==========================================================

import torch
import pyreadr
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset
from torch.utils.data import DataLoader

# ==========================================================
# Device
# ==========================================================

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print(f"Using device: {device}")

# ==========================================================
# Configuration
# ==========================================================

WINDOW_SIZE = 50

BATCH_SIZE = 128

EPOCHS = 50

HIDDEN_SIZE = 128

LATENT_SIZE = 32

LEARNING_RATE = 1e-3

# ==========================================================
# Dataset Class
# ==========================================================

class TEPDataset(Dataset):

    def __init__(self, windows):
        self.windows = windows

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        return self.windows[idx]

# ==========================================================
# Load Training Data
# ==========================================================

result = pyreadr.read_r(
    "TEP_FaultFree_Training.RData"
)

print("Objects found in RData:")
print(result.keys())

df = next(iter(result.values()))

print(f"\nRaw dataframe shape: {df.shape}")

# ==========================================================
# Feature Selection
# ==========================================================

feature_columns = [
    col
    for col in df.columns
    if col not in [
        "faultNumber",
        "simulationRun",
        "sample"
    ]
]

print(f"\nNumber of features: {len(feature_columns)}")

X = df[feature_columns]

# ==========================================================
# Scaling
# ==========================================================

scaler = StandardScaler()

X_scaled = scaler.fit_transform(X)

scaled_df = pd.DataFrame(
    X_scaled,
    columns=feature_columns
)

scaled_df["simulationRun"] = (
    df["simulationRun"].values
)

print(
    f"\nScaled dataframe shape: "
    f"{scaled_df.shape}"
)

# ==========================================================
# Window Creation
# ==========================================================

def create_windows_by_run(
    dataframe,
    window_size
):

    all_windows = []

    runs = sorted(
        dataframe["simulationRun"].unique()
    )

    for run in runs:

        run_df = dataframe[
            dataframe["simulationRun"] == run
        ]

        run_features = run_df[
            feature_columns
        ].values

        for i in range(
            len(run_features)
            - window_size
            + 1
        ):

            window = run_features[
                i:i + window_size
            ]

            all_windows.append(window)

    return np.array(all_windows)

windows = create_windows_by_run(
    scaled_df,
    WINDOW_SIZE
)

print(
    f"\nWindows shape: "
    f"{windows.shape}"
)

# Example:
# (num_windows, 50, 52)

# ==========================================================
# Tensor Conversion
# ==========================================================

windows_tensor = torch.tensor(
    windows,
    dtype=torch.float32
)

print(
    f"\nTensor shape: "
    f"{windows_tensor.shape}"
)

# ==========================================================
# Dataset & DataLoader
# ==========================================================

train_dataset = TEPDataset(
    windows_tensor
)

train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True
)

print(
    f"\nTraining samples: "
    f"{len(train_dataset)}"
)

print(
    f"Number of batches: "
    f"{len(train_loader)}"
)

# ==========================================================
# Sanity Check
# ==========================================================

batch = next(iter(train_loader))

print(
    f"\nBatch shape: "
    f"{batch.shape}"
)

# Expected:
# torch.Size([128, 50, 52])

# ==========================================================
# Model
# ==========================================================

model = LSTMAE(
    input_size=len(feature_columns),
    hidden_size=HIDDEN_SIZE,
    dropout_ratio=0.0,
    latent_size=LATENT_SIZE,
    seq_len=WINDOW_SIZE,
    use_act=False
)

model = model.to(device)

print(model)

# ==========================================================
# Loss & Optimizer
# ==========================================================

criterion = torch.nn.MSELoss()

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LEARNING_RATE
)

# ==========================================================
# Training Function
# ==========================================================

def train_epoch(
    model,
    dataloader,
    optimizer,
    criterion
):

    model.train()

    running_loss = 0.0

    for batch in dataloader:

        batch = batch.to(device)

        optimizer.zero_grad()

        reconstruction = model(batch)

        loss = criterion(
            reconstruction,
            batch
        )

        loss.backward()

        optimizer.step()

        running_loss += loss.item()

    return running_loss / len(dataloader)

# ==========================================================
# Training Loop
# ==========================================================

train_losses = []

for epoch in range(EPOCHS):

    train_loss = train_epoch(
        model,
        train_loader,
        optimizer,
        criterion
    )

    train_losses.append(
        train_loss
    )

    print(
        f"Epoch [{epoch+1}/{EPOCHS}] "
        f"Loss: {train_loss:.6f}"
    )

# ==========================================================
# Plot Training Loss
# ==========================================================

plt.figure(
    figsize=(10, 5)
)

plt.plot(
    train_losses
)

plt.xlabel(
    "Epoch"
)

plt.ylabel(
    "Reconstruction Loss"
)

plt.title(
    "Training Loss"
)

plt.grid(True)

plt.show()

# ==========================================================
# Save Model
# ==========================================================

MODEL_PATH = (
    "lstm_autoencoder.pt"
)

torch.save(
    model.state_dict(),
    MODEL_PATH
)

print(
    f"\nModel saved to "
    f"{MODEL_PATH}"
)

# ==========================================================
# Save Scaler
# ==========================================================

SCALER_PATH = (
    "scaler.pkl"
)

joblib.dump(
    scaler,
    SCALER_PATH
)

print(
    f"Scaler saved to "
    f"{SCALER_PATH}"
)

# ==========================================================
# Download Artifacts
# ==========================================================

from google.colab import files

files.download(
    MODEL_PATH
)

files.download(
    SCALER_PATH
)