"""Inference Module for Deployment
"""
import json
import random
from glob import glob
from pathlib import Path

import torch
from torchvision import datasets, transforms
from torchvision.utils import make_grid

import config
import utils
from dataloaders import dataloaders
from models import models


class InferVAE:
    """Inference Module"""

    def __init__(
        self,
        artifact_path: Path = config.ARTIFACT_PATH,
        data_path: Path = config.DATA_PATH,
    ):
        """Inference Instance

        Args:
            artifact_path (Path, optional): Path to artifacts to access model checkpoints. Defaults to config.ARTIFACT_PATH.
            data_path (Path, optional): Path to dataset to access images. Defaults to config.DATA_PATH.
        """
        model_paths = glob(
            str(artifact_path / "model_ckpt" / "**" / "*.pt"), recursive=True
        )
        self.model_dict = {}
        for model_path in model_paths:
            model_name = model_path.split("/")[-1][:-3]
            model_type, hidden_size, dataset = model_name.split("_")
            hidden_size = int(hidden_size)
            _, input_size = dataloaders[dataset]
            self.model_dict[model_name] = models[model_type](
                input_size=input_size, hidden_size=hidden_size
            )
            self.model_dict[model_name].eval().to(config.DEVICE)
            utils.load_model(self.model_dict[model_name], model_path)

        print(self.model_dict.keys())

        infer_transforms = transforms.Compose(
            [transforms.RandomCrop(28, padding=4), transforms.ToTensor()]
        )

        self.datasets = {
            "mnist": datasets.MNIST(
                data_path, download=True, train=True, transform=infer_transforms
            )
        }

        self.index_dict = {}
        for dataset in self.datasets.keys():
            with open(str(config.DEPLOY_PATH / "jsons" / f"{dataset}.json"), "r") as f:
                self.index_dict[dataset] = json.load(f)

    def sample_image(self, class_no: int, dataset: str) -> torch.tensor:
        """Sample an image from a class of a dataset

        Args:
            class_no (int): Class Number
            dataset (str): Dataset to sample from

        Returns:
            torch.tensor: Sampled Image
        """
        img_idx = random.choice(self.index_dict[dataset][str(class_no)])
        target_img, _ = self.datasets[dataset][img_idx]
        return target_img

    def reconstruction(
        self, target_img: torch.tensor, model_type: str, hidden_size: int, dataset: str
    ):
        """Reconstruction Feature. Take a random image of a specified class from the dataset, generate lalent vector distribution and
        reconstruct using Decoder. Quality of reconstruction is based on model type and hidden size of latent vector.

        Args:
            target_img (torch.tensor): Target Image for reconstruction
            model_type (str): Model checkpoint to load for reconstruction process
            hidden_size (int): Number of dimensions (features) of Latent Vector Space
            dataset (str): Dataset used for inference

        Returns:
            Tuple(torch.tensor, torch.tensor): Target Image, Reconstructed Image
        """
        model_name = "_".join([model_type, str(hidden_size), dataset])

        recon_img, _, _ = self.model_dict[model_name](
            target_img.unsqueeze(0).to(config.DEVICE)
        )

        return recon_img.squeeze(0).cpu()

    def encode(
        self, input_img: torch.tensor, model_type: str, hidden_size: int, dataset: str
    ) -> torch.tensor:
        """Encode sample image to latent distribution and sample a latent vector from the output distribution

        Args:
            input_img (torch.tensor): Input Image
            model_type (str): Model Type
            hidden_size (int): No of dimensions of latent subspace
            dataset (str): Dataset Used

        Returns:
            torch.tensor: Sampled Latent Representation of the input image
        """
        model_name = "_".join([model_type, str(hidden_size), dataset])
        mu, logvar = self.model_dict[model_name].encode(
            input_img.unsqueeze(0).to(config.DEVICE)
        )
        hidden_vector = self.model_dict[model_name].reparameterize(mu, logvar)
        return hidden_vector.squeeze(0)

    def decode(
        self,
        hidden_vector: torch.tensor,
        model_type: str,
        hidden_size: int,
        dataset: str,
    ) -> torch.tensor:
        """Reconstruct Latent Vector to image

        Args:
            hidden_vector (torch.tensor): Latent Vector representing an image in latent space
            model_type (str): Model Type
            hidden_size (int): No of dimensions of latent subspace
            dataset (str): Dataset Used

        Returns:
            torch.tensor: Reconstructed Image
        """
        model_name = "_".join([model_type, str(hidden_size), dataset])
        recon_img = self.model_dict[model_name].decode(
            hidden_vector.unsqueeze(0).to(config.DEVICE)
        )
        return recon_img.squeeze(0).cpu()

    def interpolate(
        self,
        first_img: torch.tensor,
        second_img: torch.tensor,
        model_type: str,
        hidden_size: int,
        dataset: int,
    ) -> torch.tensor:
        """Generate samples in-between 2 input images in latent space

        Args:
            first_img (torch.tensor): Input First Image
            second_img (torch.tensor): Input Second Image
            model_type (str): Model Type
            hidden_size (int): No of dimensions of latent subspace
            dataset (str): Dataset Used

        Returns:
            torch.tensor: Interpolated Images
        """
        first_hidden = self.encode(first_img, model_type, hidden_size, dataset)
        second_hidden = self.encode(second_img, model_type, hidden_size, dataset)
        intermediate_hiddens = [
            first_hidden * (1 - w) + second_hidden * w
            for w in torch.arange(0.1, 1, 0.1)
        ]
        intermediate_imgs = [
            self.decode(hidden, model_type, hidden_size, dataset)
            for hidden in intermediate_hiddens
        ]
        imgs = [first_img] + intermediate_imgs + [second_img]
        return make_grid(imgs, nrow=len(imgs))


if __name__ == "__main__":
    infer_cls = InferVAE()
    first_img = infer_cls.sample_image(3, "mnist")
    second_img = infer_cls.sample_image(7, "mnist")
    int_img = infer_cls.interpolate(first_img, second_img, "ConvVAE", 2, "mnist")
    print(int_img.size())