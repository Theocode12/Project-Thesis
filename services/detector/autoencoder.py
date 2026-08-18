"""
autoencoder.py

PyTorch Autoencoder architecture used by the Edge Detector.

This module contains only the neural network definition.
Training is performed offline. The trained weights are loaded
at runtime using `load_state_dict()`.
"""

import torch
import torch.nn as nn

class Encoder(nn.Module):

    def __init__(
            self,
            input_size,
            hidden_size,
            latent_size,
            dropout):

        super().__init__()

        self.encoder = nn.Sequential(

            nn.Linear(input_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout)
        )

        self.latent = nn.Linear(hidden_size, latent_size)

    def forward(
        self,
        x: torch.Tensor
    ) -> torch.Tensor:

        x = self.encoder(x)
        return self.latent(x)


class Decoder(nn.Module):

    def __init__(
            self,
            input_size,
            hidden_size,
            latent_size,
            dropout):

        super().__init__()

        self.decoder = nn.Sequential(

            nn.Linear(latent_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, input_size)
        )

    def forward(
        self,
        z: torch.Tensor
    ) -> torch.Tensor:


        return self.decoder(z)


class SparseAutoEncoder(nn.Module):

    def __init__(
            self,
            input_size=52,
            hidden_size=128,
            latent_size=64,
            dropout=0.0):

        super().__init__()

        self.encoder = Encoder(
            input_size=input_size,
            hidden_size=hidden_size,
            latent_size=latent_size,
            dropout=dropout
        )

        self.decoder = Decoder(
            input_size=input_size,
            hidden_size=hidden_size,
            latent_size=latent_size,
            dropout=dropout
        )

    def forward(self, x):

        latent = self.encoder(x)

        reconstruction = self.decoder(latent)

        return reconstruction

