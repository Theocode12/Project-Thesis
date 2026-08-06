import torch
import torch.nn as nn


class FaultClassifier(nn.Module):
    def __init__(self, input_dim: int, num_classes: int):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_dim, 100),
            nn.SELU(),

            nn.Linear(100, 100),
            nn.SELU(),

            nn.Linear(100, num_classes)
        )

    def forward(self, x):
        return self.network(x)