"""
Functions to visualise robots
"""

import torch
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches  # For legend
import numpy as np
from pathlib import Path
from ..config import PLOT_DIR, DEVICE, COORDINATE_DIMENSIONS, PLOT
from ..data.dataset import sparse_to_dense


def load_grid_from_file(filepath: str, robot_id: int, robot_id_column_idx: int = 0) -> tuple[torch.Tensor, int]:
    """
    Retrieve grid data for 3D space data from file for robot_id specified.
    Intended to be used on raw (non-combined) csv files.
    If using for combined files, default robot_id_column_idx will refer to the first column (new combined ID),
    for original ID, use idx 2 but note there may be duplicate ID's, first found will be returned.

    :param filepath: Filepath
    :param robot_id: Robot ID to get grid data for
    :param robot_id_column_idx: Column index containing robot ID, default 0
    :return: Grid data as tensor, Row number
    """
    with open(filepath) as file:
        lines = file.readlines()
        for row_idx, line in enumerate(lines):
            robot_encoding = line.split(',')
            # Checks id and skips iteration if not the one we want
            if int(robot_encoding[robot_id_column_idx]) != robot_id:
                continue
            i = 0
            j = 0
            row = []  # x-axis
            roww = []  # y-axis
            matrix = []  # z-axis (vertical)
            for elt in robot_encoding[-1331:]:
                row.append(int(elt))
                i += 1
                if i == 11:
                    roww.append(row)
                    row = []
                    j += 1
                    i = 0
                if j == 11:
                    matrix.append(roww)
                    roww = []
                    j = 0

            return torch.tensor(matrix, dtype=torch.float32), row_idx + 1


def visualise_robot(grid_data: torch.Tensor, title: str = None, filename: str | Path = "robot", ax: plt.axes = None) -> None:
    """
    Visualise robot from tensor of grid data.
    Saves as png in 'PLOT_DIR' as specified in config.

    :param grid_data: 11x11x11 3D space coordinate data
    :param title: Optional plot title
    :param filename: Filename to save generated visualisation. Stores in 'PLOT_DIR' as specified in config
    :param ax: Optional Matplotlib axis object to plot on, used for comparing robot reconstructions with original
    """
    # Verify grid data has 1331 elements (11x11x11 flattened)
    assert grid_data.numel() == 1331, "Grid data does not have the correct number of elements (1331)."

    # Reshape grid data to (11, 11, 11) and ensure integer type
    matrix = grid_data.view(11, 11, 11).numpy().astype(np.int32)

    # Comments show files with no skeleton / files with skeleton
    colours = np.where(matrix == 1, "blue", matrix)  # wheel/skeleton
    colours = np.where(colours == '2', "green", colours)  # joint/wheel
    colours = np.where(colours == '3', "red", colours)  # caster/sensor
    colours = np.where(colours == '4', "orange", colours)  # sensor/joint
    # colours = np.where(colours == '5', "pink", colours)  # not used/caster

    fig = None

    # Plot on provided axis or create new figure
    if ax is None:
        fig = plt.figure()
        ax = fig.add_subplot(projection='3d')

    ax.voxels(matrix, facecolors=colours, edgecolor='k')

    # Set axis limits, can have rendering issues when left to automatic
    ax.set_xlim(0, 11.99)
    ax.set_ylim(0, 11.99)
    ax.set_zlim(0, 11.99)

    # Set equal aspect ratios for all axes
    ax.set_box_aspect([1, 1, 1])

    ax.set_xlabel('X-axis')
    ax.set_ylabel('Y-axis')
    ax.set_zlabel('Z-axis')

    # Set title
    if title:
        ax.set_title(title, pad=20)

    # Create a legend
    legend_elements = [
        # When using files that include the skeleton, change to commented values or add dynamic functionality
        mpatches.Patch(color="blue", label="Wheel"),  # "Skeleton"
        mpatches.Patch(color="green", label="Joint"),  # Wheel
        mpatches.Patch(color="red", label="Caster"),  # Sensor
        mpatches.Patch(color="orange", label="Sensor")  # Joint
        # mpatches.Patch(color="pink", label="Caster")  # Caster (this value is not used with files without skeleton)
    ]

    # Save and show plot if no axis provided
    if fig is not None:
        # Add the legend to the plot
        ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.05, 1), fontsize='small')

        # Save plot
        filepath = Path(PLOT_DIR) / f"{filename}.png"
        if not filepath.parent.exists():
            print(f"Creating directory '{filepath.parent}'...")
            filepath.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(filepath)
        print(f"Robot visualisation plot saved to '{filepath.name}'")

        if PLOT:
            plt.show()
        plt.close(fig)


def compare_reconstructed(model: torch.nn.Module, dataloader: torch.utils.data.DataLoader, num_sample: int, filename: str | Path = "recon_comparison", skip_loader_samples: int = 0, by_id=None):
    """
    Plots original robot and reconstructed robot visualisations side by side.
    When test_transform is True, uses model to obtain transformation matrix, and visualises original and transformed original.

    :param model: Model to use to reconstruct robot
    :param dataloader: Dataloader to use to get samples from
    :param num_sample: Number of robots to visualise (each generated as its own individual plot)
    :param filename: Filename to save plot (without extension), robot ID is appended to the filename, saved in 'PLOT_DIR' as specified in config
    :param skip_loader_samples: Option to skip a given number of samples from the data loader to avoid visualising the same samples
    :param by_id: Reconstruct robots based on robot_id
    """
    model.eval()

    ids = []
    grid_data = []
    skipped = 0

    print("Getting samples for comparison visualisations...")

    # Get samples
    for batch_ids, batch_grid_data in dataloader:
        for robot_id, data in zip(batch_ids, batch_grid_data):
            if skipped < skip_loader_samples:
                skipped += 1
                continue  # Skip the current num_sample

            # Get specified robots when set
            if by_id is not None and robot_id.item() != by_id:
                continue

            ids.append(robot_id.item())
            grid_data.append(data.to(DEVICE))
            if len(ids) >= num_sample:
                break
        if len(ids) >= num_sample:
            break

    # Common legend for the entire figure
    legend_elements = [
        mpatches.Patch(color="blue", label="Wheel"),
        mpatches.Patch(color="green", label="Joint"),
        mpatches.Patch(color="red", label="Caster"),
        mpatches.Patch(color="orange", label="Sensor")
    ]

    with torch.no_grad():
        for i, robot_id in enumerate(ids):
            # Create subplots
            fig, axes = plt.subplots(1, 3, figsize=(12, 6), subplot_kw={'projection': '3d'})
            fig.subplots_adjust(top=0.85, hspace=0.3)  # Adjust spacing between main title and subplot titles
            fig.suptitle(f"Comparison of Original, Transformed and Reconstructed Robot, ID: {robot_id}")

            orig_gird = grid_data[i]

            # Forward pass
            recon_grid, _, _, _, transform_matrix = model(orig_gird.unsqueeze(0))

            # Transform original coordinates
            transformed_grid_batched = orig_gird.unsqueeze(0).clone()
            transformed_grid_batched[:, :, :COORDINATE_DIMENSIONS] = torch.bmm(transformed_grid_batched[:, :, :COORDINATE_DIMENSIONS], transform_matrix)

            # Convert to dense grid
            left_grid_dense = sparse_to_dense(orig_gird)
            middle_grid_dense = sparse_to_dense(transformed_grid_batched.squeeze(0))
            right_grid_dense = sparse_to_dense(recon_grid.squeeze(0))

            # Testing transform matrix
            visualise_robot(left_grid_dense.unsqueeze(0).cpu(), title="Original", ax=axes[0])
            visualise_robot(middle_grid_dense.unsqueeze(0).cpu(), title="Transformed Original", ax=axes[1])
            visualise_robot(right_grid_dense.unsqueeze(0).cpu(), title="Reconstructed", ax=axes[2])

            # Add common legend
            fig.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, 0.945), ncol=4)

            # Adjust layout
            plt.tight_layout()

            # Save visualisation
            filepath = Path(PLOT_DIR) / f"{filename}_{robot_id}.png"
            if not filepath.parent.exists():
                print(f"Creating directory '{filepath.parent}'...")
                filepath.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(filepath)
            print(f"Robot comparison visualisation plot saved to '{filepath.name}'")

            if PLOT:
                plt.show()
            plt.close(fig)
