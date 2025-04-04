"""
Director script

Run using command:
python src/main.py
"""

from model_pkg import *
from pathlib import Path
import pandas as pd
import torch
from torchinfo import summary
import torch.optim as optim
from torch.utils.data import DataLoader, Subset
import numpy as np


def run():
    print("Starting VAE pipeline...\n")

    model_name = "beta_run_500"
    combine_and_save = False  # When false, will load processed files
    use_toy_set = False  # Use 20% of full dataset or full dataset, does not use test set
    testing = False  # 128 samples for train and val sets for quick run testing
    evaluate = True  # For evaluating
    evaluate_model_path = config.MODELS_DIR / "beta_run_500_be0.3_160325" / "best_loss_epoch_121.pth"
    beta_used = "Beta 0.3"  # For evaluation filename and titles

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
            save_datasets(config.PROCESSED_DIR / "toy_sets", data=[train_data, val_data, rest_of_data], filenames=["train", "val", "test"])
            print()
        else:
            # Split data and save (full datasets)
            print("Preparing FULL datasets...")
            train_data, val_data, test_data = split_data(cleaned_df)
            save_datasets(config.PROCESSED_DIR, data=[train_data, val_data, test_data], filenames=["train", "val", "test"])
            print("\nSplitting test set into diverse evaluation sets...")
            evaluation_sets = split_evaluation_sets(test_data)
            save_datasets(config.PROCESSED_DIR, data=evaluation_sets, filenames=["component_dominance", "component_moderate_dominance", "component_variety", "spatial_compact", "spatial_moderately_spread", "spatial_spread_dispersed"])
            print("\nTraining dataset:")
            summarise_dataset(train_data)
            print("Validation dataset:")
            summarise_dataset(val_data)
            print("Test dataset:")
            summarise_dataset(test_data)

    if evaluate:
        # Load data
        eval_df_dict = load_processed_datasets(config.PROCESSED_DIR, "component_dominance", "component_moderate_dominance", "component_variety", "spatial_compact", "spatial_moderately_spread", "spatial_spread_dispersed", as_dict=True)
        print()

        # Load model
        model = load_model_checkpoint(evaluate_model_path)[0]
        model.eval()

        mean_latents = []
        log_var_latents = []
        ds_labels = []
        ids = []
        loaders = {}

        # Convert each DataFrame to a Dataset and create DataLoader for processing forward pass to obtain mean latent vectors
        for ds_name, df in eval_df_dict.items():
            ds = VoxelDataset(df, max_voxels=config.MAX_VOXELS, name=ds_name)
            loader = DataLoader(ds, batch_size=config.BATCH_SIZE, shuffle=True)
            loaders[ds_name] = loader  # store loader for the dataset for comparison visualisations

            # Obtain mean latent vectors
            with torch.no_grad():
                for robot_ids, data in loader:
                    data = data.to(config.DEVICE)
                    z_mean, log_var, _ = model.encoder(data)  # Forward pass (batch, latent_dim)
                    mean_latents.append(z_mean.cpu())
                    log_var_latents.append(log_var.cpu())

                    ds_labels.extend([ds_name] * len(data))
                    ids.extend(robot_ids.numpy())

        # Concatenate to a single tensor
        all_mean_latents = torch.cat(mean_latents, dim=0)  # (total_ds_samples, latent_dim)
        all_var_latents = torch.cat(log_var_latents, dim=0)

        # Convert to DataFrame for filtering
        df = pd.DataFrame({"robot_id": ids, "dataset": ds_labels, "mean_latent": list(all_mean_latents.numpy()), "var_latent": list(all_var_latents.numpy())})
        print(f"Dataset samples:\n{df.groupby('dataset').size()}\n")

        # Collect the same number of samples per dataset for all categories
        collected_samples_df = pd.DataFrame(columns=df.columns)
        max_dataset_samples = df.groupby('dataset').size().min()

        for group, subset in df.groupby("dataset"):
            sampled = subset.iloc[:max_dataset_samples]
            collected_samples_df = pd.concat([collected_samples_df, sampled], ignore_index=True)

        print(f"Collected samples:\n{collected_samples_df.groupby('dataset').size()}\n")

        # Define datasets per category
        component_datasets = ["component_dominance", "component_moderate_dominance", "component_variety"]
        spatial_datasets = ["spatial_compact", "spatial_moderately_spread", "spatial_spread_dispersed"]

        # Split into categories
        component_df = collected_samples_df[collected_samples_df["dataset"].isin(component_datasets)]
        spatial_df = collected_samples_df[collected_samples_df["dataset"].isin(spatial_datasets)]

        # Extract and convert collected columns
        component_ids = component_df["robot_id"].tolist()
        component_labels = component_df["dataset"].tolist()
        component_mean_latents = np.stack(component_df["mean_latent"])
        component_var_latents = np.stack(component_df["var_latent"])
        spatial_ids = spatial_df["robot_id"].tolist()
        spatial_labels = spatial_df["dataset"].tolist()
        spatial_mean_latents = np.stack(spatial_df["mean_latent"])
        spatial_var_latents = np.stack(spatial_df["var_latent"])

        comp_featured = [199993, 72764, 23732, 123338, 235745, 176868, 171434, 152518, 212129, 4213, 42502, 190757, 10332, 65626, 192293, 230604, 112648, 47325, 233030, 217610, 88901, 152089, 220102, 57830, 252961]  # Component robot ids
        spatial_featured = [214524, 161671, 50115, 214744, 31951, 18577, 132205, 78346, 263742, 46534, 81618, 188259, 23732, 134797, 196955, 174022, 135487, 3457, 139697, 120279, 87338]  # Spatial robots ids

        comp_featured_idxs = [component_ids.index(rob_id) for rob_id in comp_featured]
        spatial_featured_idxs = [spatial_ids.index(rob_id) for rob_id in spatial_featured]

        # comp_featured_idxs = list(range(len(component_ids)))
        # spatial_featured_idxs = list(range(len(spatial_ids)))
        # print(f"ids comp: {np.array(component_ids)[comp_featured_idxs]}")
        # print(f"ids spat: {np.array(spatial_ids)[spatial_featured_idxs]}")

        # Plot using PCA and UMAP
        evaluate_latent_vectors(component_mean_latents, component_labels, title=f"Component Based: {beta_used}", plot_idx=comp_featured_idxs, robot_ids=component_ids, annotate=False)
        # evaluate_latent_vectors(spatial_mean_latents, spatial_labels, title=f"Spatial Based: {beta_used}", plot_idx=spatial_featured_idxs, robot_ids=spatial_ids, annotate=False)

        evaluate_latent_vectors(component_mean_latents, component_labels, title=f"Component Based: {beta_used}")
        evaluate_latent_vectors(spatial_mean_latents, spatial_labels, title=f"Spatial Based: {beta_used}")
        evaluate_latent_vectors(component_mean_latents, component_labels, title=f"Component Based (Dominance): {beta_used}", plot_set_colour="component_dominance")
        evaluate_latent_vectors(spatial_mean_latents, spatial_labels, title=f"Spatial Based (Compact): {beta_used}", plot_set_colour="spatial_compact")
        evaluate_latent_vectors(component_mean_latents, component_labels, title=f"Component Based (Moderate): {beta_used}", plot_set_colour="component_moderate_dominance")
        evaluate_latent_vectors(spatial_mean_latents, spatial_labels, title=f"Spatial Based (Moderate): {beta_used}", plot_set_colour="spatial_moderately_spread")
        evaluate_latent_vectors(component_mean_latents, component_labels, title=f"Component Based (Variety): {beta_used}", plot_set_colour="component_variety")
        evaluate_latent_vectors(spatial_mean_latents, spatial_labels, title=f"Spatial Based (Dispersed): {beta_used}", plot_set_colour="spatial_spread_dispersed")
        
        # Plot features against each other using 3 robots from each dataset
        plot_latent_features(component_mean_latents, component_var_latents, component_ids, component_labels, title=f"Component Based: {beta_used}")
        plot_latent_features(spatial_mean_latents, spatial_var_latents, spatial_ids, spatial_labels, title=f"Spatial Based: {beta_used}")
        plot_latent_features(component_mean_latents, component_var_latents, component_ids, component_labels, title=f"Component Based (Dominance): {beta_used}", plot_set_colour="component_dominance")
        plot_latent_features(spatial_mean_latents, spatial_var_latents, spatial_ids, spatial_labels, title=f"Spatial Based (Compact): {beta_used}", plot_set_colour="spatial_compact")
        plot_latent_features(component_mean_latents, component_var_latents, component_ids, component_labels, title=f"Component Based (Moderate): {beta_used}", plot_set_colour="component_moderate_dominance")
        plot_latent_features(spatial_mean_latents, spatial_var_latents, spatial_ids, spatial_labels, title=f"Spatial Based (Moderate): {beta_used}", plot_set_colour="spatial_moderately_spread")
        plot_latent_features(component_mean_latents, component_var_latents, component_ids, component_labels, title=f"Component Based (Variety): {beta_used}", plot_set_colour="component_variety")
        plot_latent_features(spatial_mean_latents, spatial_var_latents, spatial_ids, spatial_labels, title=f"Spatial Based (Dispersed): {beta_used}", plot_set_colour="spatial_spread_dispersed")
        
        # Plot features against each other using 3 robots from each dataset - Does not work properly.
        # Probably would be better if colour scale could be in log scale to make the changes (mid frequency values) easier to see. Also needs formatting.
        # plot_feature_heatmap(component_mean_latents, component_var_latents, component_labels, title=f"Component Based Latent Feature Comparison Heatmaps: {beta_used}")
        # plot_feature_heatmap(spatial_mean_latents, spatial_var_latents, spatial_labels, title=f"Spatial Based Latent Feature Comparison Heatmaps: {beta_used}")

        # Full datasets
        _, _, test_data = load_processed_datasets(config.PROCESSED_DIR, "train", "val", "test")
        ds = VoxelDataset(test_data, max_voxels=config.MAX_VOXELS)
        test_loader = DataLoader(ds, batch_size=config.BATCH_SIZE, shuffle=True)
        for feat_id in comp_featured + spatial_featured:  # Spatial robots
            print(f"feat:{feat_id}")
            compare_reconstructed(model, test_loader, num_sample=1, filename=f"featured_robot_{beta_used.lower().replace(' ', '_')}", by_id=feat_id)

        # Visualise samples robots from each dataset
        for i, (title, df) in enumerate(eval_df_dict.items()):  # Iterate each loaded dataset
            # if i < 3:
            #     continue
            grids = torch.tensor(df.iloc[:, -(config.EXPANDED_GRID_SIZE ** config.COORDINATE_DIMENSIONS):].values,
                                 dtype=torch.float32)
            grid_data = grids.view(-1, config.EXPANDED_GRID_SIZE, config.EXPANDED_GRID_SIZE, config.EXPANDED_GRID_SIZE)
            sample_ids = df.iloc[:, 0].values
            visualised = 0
            for sample, sample_id in zip(grid_data, sample_ids):  # Iterate each sample
                if sample_id not in collected_samples_df.loc[collected_samples_df['dataset'] == title, 'robot_id'].values:  # Only visualise robots from the collected samples
                    continue
                visualised += 1
                # visualise_robot(sample, title=title.capitalize(), filename=f"{title}_{visualised}")  # Visualise from grid
                compare_reconstructed(model, loaders[title], num_sample=1, filename=f"comparison_{title}_{beta_used.lower().replace(' ', '_')}", by_id=sample_id)  # Comparison reconstruction based on id
                if visualised >= 10:
                    break

        exit(0)

    # Load processed data
    if use_toy_set:
        # toy datasets - test set contains the majority of the data, should not be used
        train_data, val_data = load_processed_datasets(config.PROCESSED_DIR / "toy_sets", "train", "val")
        test_data = None
    else:
        # Full datasets
        train_data, val_data, test_data = load_processed_datasets(config.PROCESSED_DIR, "train", "val", "test")

    # Create datasets and dataloaders
    print("\nTraining dataset:")
    summarise_dataset(train_data)
    train_ds = VoxelDataset(train_data, max_voxels=config.MAX_VOXELS)
    train_loader = DataLoader(train_ds, batch_size=config.BATCH_SIZE, shuffle=True)

    print("Validation dataset:")
    summarise_dataset(val_data)
    val_ds = VoxelDataset(val_data, max_voxels=config.MAX_VOXELS)
    val_loader = DataLoader(val_ds, batch_size=config.BATCH_SIZE, shuffle=False)
    if test_data is not None:
        print("Test dataset:")
        summarise_dataset(test_data)  # type: ignore
        test_ds = VoxelDataset(test_data, max_voxels=config.MAX_VOXELS)
        test_loader = DataLoader(test_ds, batch_size=config.BATCH_SIZE, shuffle=False)
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
    criterion = VaeLoss(lambda_coord=1, lambda_desc=1, lambda_collapse=0.1)
    optimizer = optim.Adam(vae.parameters(), lr=config.LEARNING_RATE)
    """

    if testing:
        # For testing
        print("Using TESTING subsets (128 samples)...")
        subset_indices = list(range(128))  # Indices for the first 128 samples
        subset_train_ds = Subset(train_ds, subset_indices)
        subset_val_ds = Subset(val_ds, subset_indices)

        # Give subset access to attributes
        subset_train_ds.max_voxels = train_ds.max_voxels
        subset_train_ds.coordinate_dim = train_ds.coordinate_dim
        subset_val_ds.max_voxels = train_ds.max_voxels
        subset_val_ds.coordinate_dim = train_ds.coordinate_dim

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
        train_grid_search(train_ds, val_ds, model_name, clear_history_list=False)
        # -----------------------------------------
        # TESTING
        """
        best_history = TrainingHistory.load_history("best_performing_coord_scale_toy_bs64_ld16_mse_adam_lr0.0005_wd1e-05_be0.01_a0.2_dup1_lam0.001_epoch_20.pth")
        best_epoch = 20
        alt_name = f"testing_{best_history.model_name}_epoch_{best_epoch}"
        best_history.save_history(alt_name)
        if best_epoch < best_history.epochs_run:
            best_history.rollback(best_epoch)
        best_model, best_optimizer, _, epochs_run = load_model_checkpoint(best_history)
        criterion = VaeLoss(lambda_coord=1, lambda_desc=1, lambda_collapse=0.1, lambda_reg=0.001)
        history = train_val(best_model, train_loader, val_loader, criterion, best_optimizer, 21, beta=0.01, training_history=best_history,
                            prune_old_checkpoints=False)
        # generate_plots(history, alt_name)
        test_model, _, _, epochs_run = load_model_checkpoint(history)
        compare_reconstructed(test_model, val_loader, 2, filename=f"comparison_{alt_name}", skip_loader_samples=1)
        """
        # -----------------------------------------------

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

        compare_reconstructed(best_model, val_loader, num_sample=5, filename=f"comparison_{alt_name}")
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

        compare_reconstructed(best_loss_model, val_loader, num_sample=5, filename=f"comparison_{alt_loss_name}")
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

        compare_reconstructed(best_f1_model, val_loader, num_sample=5, filename=f"comparison_{alt_f1_name}")
    except (FileNotFoundError, ValueError) as e:
        print(f"{e} Cannot perform latent analysis for {alt_f1_name}.")

    print("\nPipeline complete!")


if __name__ == "__main__":
    run()
