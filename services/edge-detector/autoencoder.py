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
    """
    Encoder network.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        latent_size: int,
        dropout: float = 0.0,
    ) -> None:

        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),
        )

        self.latent = nn.Linear(
            hidden_size,
            latent_size
        )

    def forward(
        self,
        x: torch.Tensor
    ) -> torch.Tensor:

        x = self.network(x)
        return self.latent(x)


class Decoder(nn.Module):
    """
    Decoder network.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        latent_size: int,
        dropout: float = 0.0,
    ) -> None:

        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(latent_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(dropout),

            nn.Linear(hidden_size, input_size),
        )

    def forward(
        self,
        z: torch.Tensor
    ) -> torch.Tensor:

        return self.network(z)


class SparseAutoEncoder(nn.Module):
    """
    Feed-forward Autoencoder used for anomaly detection.

    """

    def __init__(
        self,
        input_size: int = 52,
        hidden_size: int = 128,
        latent_size: int = 64,
        dropout: float = 0.0,
    ) -> None:

        super().__init__()

        self.encoder = Encoder(
            input_size=input_size,
            hidden_size=hidden_size,
            latent_size=latent_size,
            dropout=dropout,
        )

        self.decoder = Decoder(
            input_size=input_size,
            hidden_size=hidden_size,
            latent_size=latent_size,
            dropout=dropout,
        )

    def forward(
        self,
        x: torch.Tensor
    ) -> torch.Tensor:

        latent = self.encoder(x)

        reconstruction = self.decoder(latent)

        return reconstruction