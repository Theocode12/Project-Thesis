import torch
import torch.nn as nn

from torch.optim import Adam

from autoencoder import SparseAutoEncoder


device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)


model = SparseAutoEncoder(

    input_size=52,
    hidden_size=128,
    latent_size=64,
    dropout=0.1

).to(device)


criterion = nn.MSELoss()

optimizer = Adam(

    model.parameters(),

    lr=1e-3,

    weight_decay=1e-5

)


epochs = 100


for epoch in range(epochs):

    model.train()

    epoch_loss = 0

    for batch in train_loader:

        x = batch.float().to(device)

        optimizer.zero_grad()

        reconstruction = model(x)

        # noise = torch.randn_like(x) * 0.05

        # noisy_x = x + noise

        # reconstruction = model(noisy_x)

        # loss = criterion(reconstruction, x)

        loss = criterion(reconstruction, x)

        loss.backward()

        optimizer.step()

        epoch_loss += loss.item()

    epoch_loss /= len(train_loader)

    print(
        f"Epoch {epoch+1}/{epochs} "
        f"Loss: {epoch_loss:.6f}"
    )


torch.save(
    model.state_dict(),
    "sparse_autoencoder.pt"
)