"""
Director script

Run using command:
python src/main.py
"""

from model_pkg import *
from pathlib import Path
import pandas as pd
from torchinfo import summary
import torch.optim as optim


def run():
    print("Starting VAE pipeline...\n")

    grid_search_model_name = "batch_norm_toy"
    combine_and_save = False  # When false, will load processed files
    use_toy_set = True  # Use 20% of full dataset or full dataset, does not use test set
    testing = False  # 128 samples for train and val sets for quick run testing

    if combine_and_save:
        # Combine all CSV files and clean
        combined_data = combine_csv_files(config.DATA_DIR)
        print("Combined full dataset:")
        summarise_dataset(combined_data)
        cleaned_df = clean_data(combined_data)
        print("Cleaned dataset:")
        summarise_dataset(cleaned_df)

        if use_toy_set:
            # Split data and save (toy datasets)
            print("Preparing TOY datasets...")
            # Train and validation sets are 20% of what they normally would be, test set will contain the rest - not used
            train_data, val_data, rest_of_data = split_data(cleaned_df, val_size=0.02, test_size=0.84)
            save_split_datasets(config.PROCESSED_DIR / "toy_sets", train_data, val_data, rest_of_data)
        else:
            # Split data and save (full datasets)
            print("Preparing FULL datasets...")
            train_data, val_data, test_data = split_data(cleaned_df)
            save_split_datasets(config.PROCESSED_DIR, train_data, val_data, test_data)
            print("Training dataset:")
            summarise_dataset(train_data)
            print("Validation dataset:")
            summarise_dataset(val_data)
            print("Test dataset:")
            summarise_dataset(test_data)

    # Load processed data
    if use_toy_set:
        # toy datasets - test set contains the majority of the data, should not be used
        train_data, val_data, _ = load_processed_datasets(config.PROCESSED_DIR / "toy_sets")
        test_data = None
    else:
        # Full datasets
        train_data, val_data, test_data = load_processed_datasets(config.PROCESSED_DIR)

    # Create datasets and dataloaders
    print("\nTraining dataset:")
    summarise_dataset(train_data)
    train_ds, train_loader = create_dataset_and_loader(train_data, batch_size=config.BATCH_SIZE, shuffle=True)
    print("Validation dataset:")
    summarise_dataset(val_data)
    val_ds, val_loader = create_dataset_and_loader(val_data, batch_size=config.BATCH_SIZE)
    if test_data is not None:
        print("Test dataset:")
        summarise_dataset(test_data)  # type: ignore
        test_ds, test_loader = create_dataset_and_loader(test_data, batch_size=config.BATCH_SIZE)  # type: ignore
        print(f"Preprocessed datasets loaded: train ({len(train_ds)}), val ({len(val_ds)}), and test ({len(test_ds)}) sets.\n")
    else:
        print(f"Preprocessed datasets loaded: train ({len(train_ds)}) and val ({len(val_ds)}) sets.\n")

    # Sample
    robot_ids, grid_data = next(iter(train_loader))
    print(f"robot_ids batch shape: {robot_ids.shape}, sample ID: {robot_ids[0]}")
    print(f"grid_data batch shape: {grid_data.shape}, grid data sample shape: {grid_data[0].shape}\n")

    # visualise_robot(grid_data[0], "Test title")

    # Define model
    vae = VAE(config.INPUT_DIM, config.LATENT_DIM, "test").to(config.DEVICE)
    
    # Inspect
    print("Model summary:")
    summary(vae, input_size=(1, *config.INPUT_DIM), col_names=("input_size", "output_size", "num_params"))  # Add batch size of 1
    print("\nModel parameters:")
    for name, param in vae.named_parameters():
        print(f"Parameter: {name}, Requires Grad: {param.requires_grad}")
    print()
    """
    # Initialise training components
    criterion = VaeLoss("mse")
    optimizer = optim.Adam(vae.parameters(), lr=config.LEARNING_RATE)
    """

    if testing:
        # For testing
        print("Using TESTING subsets (128 samples)...")
        from torch.utils.data import DataLoader, Subset
        subset_indices = list(range(128))  # Indices for the first 128 samples
        subset_train_ds = Subset(train_ds, subset_indices)
        subset_val_ds = Subset(val_ds, subset_indices)
        # subset_train_loader = DataLoader(subset_train_ds, batch_size=config.BATCH_SIZE, shuffle=True)
        # subset_val_loader = DataLoader(subset_val_ds, batch_size=config.BATCH_SIZE)

        # Train VAE
        # history = train_val(vae, subset_train_loader, subset_val_loader, criterion, optimizer, config.EPOCHS)  # History will be to the latest model, which most likely will not be the best model
        # print(history)

        # history = TrainingHistory.load_history("test_history.pth")
        # print(history)
        # history.rollback("last_improved_model")  # Rollback does not save history
        # history.save_history()  # Saving rolled back history will overwrite old history (models unaffected)

        # model, optimizer, scheduler, epoch = load_model_checkpoint(history)

        train_grid_search(subset_train_ds, subset_val_ds, "test", clear_history_list=False)  # type: ignore
    else:
        # Grid search training
        train_grid_search(train_ds, val_ds, grid_search_model_name, clear_history_list=False)

    # Grid search using balanced loss and F1 to score
    print("Starting gridsearch for best trade-off performance model...")
    best_history, best_score, best_epoch = search_grid_history(loss_f1_tradeoff=0.7)
    alt_name = f"best_performing_{best_history.model_name}_epoch_{best_epoch}"
    print()
    best_history.save_history(alt_name)  # Updates alt_history_filename which is used in the plots

    generate_plots(best_history, alt_name)
    print()

    # Rollback to best performing history epoch to load model checkpoint
    if best_epoch < best_history.epochs_run:
        best_history.rollback(best_epoch)  # Rollback does not save history

    try:
        # Load best tradeoff model checkpoint
        best_model, _, _, epochs_run = load_model_checkpoint(best_history)

        # Updates name for analysis plots and saved history if intended checkpoint to load does not exist
        if epochs_run != best_epoch:
            alt_name = f"closest_checkpoint_best_performing_{best_history.model_name}_epoch_{epochs_run}"

        # Analyse latent space for best tradeoff model and store to history
        latent_metrics = analyse_latent_space(best_model, train_loader, val_loader, k=5, filename=alt_name)
        best_history.latent_analysis = latent_metrics  # Adds metrics to history
        print()
        best_history.save_history(alt_name)

        compare_reconstructed(best_model, val_loader, 3, filename=f"comparison_{alt_name}")
        print()
    except (FileNotFoundError, ValueError) as e:
        print(f"{e} Cannot perform latent analysis for {alt_name}.")

    # Grid search using only loss to score
    print("Starting gridsearch for best loss model...")
    best_loss_history, best_loss_score, best_loss_epoch = search_grid_history(loss_f1_tradeoff=1)
    alt_loss_name = f"best_loss_{best_loss_history.model_name}_epoch_{best_loss_epoch}"
    print()
    best_loss_history.save_history(alt_loss_name)  # Updates alt_history_filename which is used in the plots

    generate_plots(best_loss_history, alt_loss_name)
    print()

    # Rollback to best performing history epoch to load model checkpoint
    if best_loss_epoch < best_loss_history.epochs_run:
        best_loss_history.rollback(best_loss_epoch)  # Rollback does not save history

    try:
        # Load best tradeoff model checkpoint
        best_loss_model, _, _, loss_epochs_run = load_model_checkpoint(best_loss_history)

        # Updates name for analysis plots and saved history if intended checkpoint to load does not exist
        if loss_epochs_run != best_loss_epoch:
            alt_loss_name = f"closest_checkpoint_best_loss_{best_loss_history.model_name}_epoch_{loss_epochs_run}"

        # Analyse latent space for best tradeoff model and store to history
        latent_metrics = analyse_latent_space(best_loss_model, train_loader, val_loader, k=5, filename=alt_loss_name)
        best_loss_history.latent_analysis = latent_metrics  # Adds metrics to history
        print()
        best_loss_history.save_history(alt_loss_name)

        compare_reconstructed(best_loss_model, val_loader, 3, filename=f"comparison_{alt_loss_name}")
        print()
    except (FileNotFoundError, ValueError) as e:
        print(f"{e} Cannot perform latent analysis for {alt_loss_name}.")

    # Grid search using only weighted F1 to score
    print("Starting gridsearch for best weighted F1 model...")
    best_f1_history, best_f1_score, best_f1_epoch = search_grid_history(loss_f1_tradeoff=0)
    alt_f1_name = f"best_f1_{best_f1_history.model_name}_epoch_{best_f1_epoch}"
    print()
    best_f1_history.save_history(alt_f1_name)  # Updates alt_history_filename which is used in the plots

    generate_plots(best_f1_history, alt_f1_name)
    print()

    # Rollback to best performing history epoch to load model checkpoint
    if best_f1_epoch < best_f1_history.epochs_run:
        best_f1_history.rollback(best_f1_epoch)  # Rollback does not save history

    try:
        # Load best tradeoff model checkpoint
        best_f1_model, _, _, f1_epochs_run = load_model_checkpoint(best_f1_history)

        # Updates name for analysis plots and saved history if intended checkpoint to load does not exist
        if f1_epochs_run != best_f1_epoch:
            alt_f1_name = f"closest_checkpoint_best_performing_{best_f1_history.model_name}_epoch_{f1_epochs_run}"

        # Analyse latent space for best tradeoff model and store to history
        latent_metrics = analyse_latent_space(best_f1_model, train_loader, val_loader, k=5, filename=alt_f1_name)
        best_f1_history.latent_analysis = latent_metrics  # Adds metrics to history
        print()
        best_f1_history.save_history(alt_f1_name)

        compare_reconstructed(best_f1_model, val_loader, 3, filename=f"comparison_{alt_f1_name}")
    except (FileNotFoundError, ValueError) as e:
        print(f"{e} Cannot perform latent analysis for {alt_f1_name}.")

    print("\nPipeline complete!")


def generate_plots(history: TrainingHistory, model_name: str):
    plot_metrics_vs_epochs(history, "recon", "beta_kl", filename=f"{model_name}_recon-beta_kl_vs_epochs")
    plot_metrics_vs_epochs(history, "f1_weighted_avg", filename=f"{model_name}_f1_vs_epochs")
    plot_metrics_vs_epochs(history, "total_loss", filename=f"{model_name}_total_loss_vs_epochs")
    plot_metrics_vs_epochs(history, "accuracy", filename=f"{model_name}_acc_vs_epochs")
    plot_loss_tradeoffs(history, "kl", filename=f"{model_name}_kl_vs_recon")
    plot_loss_tradeoffs(history, "kl_beta", filename=f"{model_name}_beta_kl_vs_recon")
    plot_loss_tradeoffs(history, "total_loss", filename=f"{model_name}_total_loss_vs_f1")


if __name__ == "__main__":
    run()
