import torch
import torch.nn as nn

from SAE import SparseAutoEncoder

model = SparseAutoEncoder()

model.load_state_dict(
    torch.load("sparse_autoencoder.pt")
)

model.eval()

with torch.no_grad():

    reconstruction = model(sample)

    error = ((sample - reconstruction) ** 2).mean(dim=1)