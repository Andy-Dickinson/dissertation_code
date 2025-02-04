"""
Defines VAE model modules
"""

import torch
import torch.nn as nn
from ..config import NUM_CLASSES

class Encoder(nn.Module):
    """
    Encoder module.
    """
    def __init__(self, latent_dim: int):
        """
        :param latent_dim: Dimensionality of latent space
        """
        super(Encoder, self).__init__()
        # Convolutional layers
        self.conv1 = nn.Conv3d(1, 64, kernel_size=3, stride=1, padding=1)  # (B, 64, 11, 11, 11)
        self.bn1 = nn.BatchNorm3d(64)
        self.conv2 = nn.Conv3d(64, 128, kernel_size=3, stride=2, padding=1)  # (B, 128, 6, 6, 6)
        self.bn2 = nn.BatchNorm3d(128)
        self.conv3 = nn.Conv3d(128, 256, kernel_size=3, stride=1, padding=1)  # (B, 256, 6, 6, 6)
        self.bn3 = nn.BatchNorm3d(256)
        self.conv4 = nn.Conv3d(256, 256, kernel_size=3, stride=1, padding=1)  # (B, 256, 6, 6, 6)
        self.bn4 = nn.BatchNorm3d(256)

        # Fully connected and flatten layers
        self.flatten = nn.Flatten()

        self.z_mean_fc = nn.Linear(256 * 6 * 6 * 6, latent_dim)
        self.z_log_var_fc = nn.Linear(256 * 6 * 6 * 6, latent_dim)

        self.leaky = nn.LeakyReLU(0.1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        :param x: Input tensor with shape (batch_size, *input_dim)
        :return:
            z_mean - Latent space mean with shape (batch_size, latent_dim),
            z_log_var - Log variance of latent space with shape (batch_size, latent_dim)
        """
        x = x.unsqueeze(1)  # Add channel dimension for 3D convolution input: (B, 1, 11, 11, 11)

        x = self.leaky(self.bn1(self.conv1(x)))  # (B, 64, 11, 11, 11)
        x = self.leaky(self.bn2(self.conv2(x)))  # (B, 128, 6, 6, 6)
        x = self.leaky(self.bn3(self.conv3(x)))  # (B, 256, 6, 6, 6)
        x = self.leaky(self.bn4(self.conv4(x)))  # (B, 256, 6, 6, 6)

        x = self.flatten(x)

        z_mean = self.z_mean_fc(x)
        z_log_var = self.z_log_var_fc(x)

        return z_mean, z_log_var


class Decoder(nn.Module):
    """
    Decoder module.
    """
    def __init__(self, latent_dim: int):
        """
        :param latent_dim: Dimensionality of latent space
        """
        super(Decoder, self).__init__()

        self.fc = nn.Linear(latent_dim, 256 * 6 * 6 * 6)
        self.bn_fc = nn.BatchNorm1d(256 * 6 * 6 * 6)

        # Transposed convolutional layers for reconstruction, conv layers for refining
        self.conv1 = nn.Conv3d(256, 256, kernel_size=3, stride=1, padding=1)  # (B, 256, 6, 6, 6)
        self.bn1 = nn.BatchNorm3d(256)
        self.conv2 = nn.Conv3d(256, 128, kernel_size=3, stride=1, padding=1)  # (B, 128, 6, 6, 6)
        self.bn2 = nn.BatchNorm3d(128)
        self.deconv1 = nn.ConvTranspose3d(128, 64, kernel_size=3, stride=2, padding=1)  # (B, 64, 11, 11, 11)
        self.bn3 = nn.BatchNorm3d(64)
        self.conv3 = nn.Conv3d(64, 1, kernel_size=3, stride=1, padding=1)  # (B, 1, 11, 11, 11)

        self.leaky = nn.LeakyReLU(0.1)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        Normalises using sigmoid and scales to range [0, 4].
        Output values are floats.

        :param z: Sampled latent vector with shape (batch_size, latent_dim)
        :return: Reconstructed input with shape (batch_size, *input_dim)
        """
        x = self.leaky(self.bn_fc(self.fc(z)))
        x = x.view(-1, 256, 6, 6, 6)  # Reshape for input to deconvolution layers

        x = self.leaky(self.bn1(self.conv1(x)))  # (B, 256, 6, 6, 6)
        x = self.leaky(self.bn2(self.conv2(x)))  # (B, 128, 6, 6, 6)
        x = self.leaky(self.bn3(self.deconv1(x)))  # (B, 64, 11, 11, 11)
        x = self.conv3(x)  # (B, 1, 11, 11, 11)

        x = torch.sigmoid(x) * (NUM_CLASSES - 1)  # Scales to range [0, 4]
        x = x.squeeze(1)  # Remove channel dimension (B, 11, 11, 11)

        return x


class Sample(nn.Module):
    """
    Reparameterization trick to allow backpropagation and sampling.
    """
    def forward(self, z_mean: torch.Tensor, z_log_var: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        :param z_mean: Latent space mean with shape (batch_size, latent_dim)
        :param z_log_var: Log variance of latent space with shape (batch_size, latent_dim)
        :return: Sampled latent vector with shape (batch_size, latent_dim)
        """
        epsilon = torch.randn_like(z_mean)

        return z_mean + torch.exp(0.5 * z_log_var) * epsilon


class VAE(nn.Module):
    """
    Implements encoder, sampling (reparameterization trick) and decoder modules for complete VAE architecture.

    Attributes:
        encoder: Input to latent space (z_mean, z_log_var)
        sampling: Reparameterization trick to sample z
        decoder: Reconstructs input from sampled z
    """
    def __init__(self, input_dim: tuple[int, int, int], latent_dim: int, model_name: str):
        """
        :param input_dim: Dimensions of input tensor (and reconstructed), (e.g., (11, 11, 11))
        :param latent_dim: Dimensionality of latent space
        :param model_name: Name of model instance, used to identify models and name saved files, ENSURE UNIQUE to avoid overwriting
        """
        super(VAE, self).__init__()
        self.name = model_name
        self.input_dim = input_dim
        self.latent_dim = latent_dim

        self.encoder = Encoder(latent_dim)
        self.sampling = Sample()
        self.decoder = Decoder(latent_dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        :param x: Input tensor with shape (batch_size, *input_dim)
        :return:
            x_reconstructed - Reconstructed input with shape (batch_size, *input_dim),
            z - Sampled latent vector with shape (batch_size, latent_dim),
            z_mean - Latent space mean with shape (batch_size, latent_dim),
            z_log_var - Log variance of latent space with shape (batch_size, latent_dim)
        """
        z_mean, z_log_var = self.encoder(x)
        z = self.sampling(z_mean, z_log_var)
        x_reconstructed = self.decoder(z)

        return x_reconstructed, z, z_mean, z_log_var
