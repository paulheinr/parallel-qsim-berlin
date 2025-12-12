# Project Setup (Conda)

This project uses a Conda environment to manage Python dependencies in a portable way.

## Prerequisites

- Conda installed (Anaconda or Miniconda)

## Initial Environment Creation (First-Time Setup)

These steps were used to create the environment initially:

1. Create a new Conda environment:
   ```bash
   conda create -n router -y
    ```
2. Activate the environment:
   ```bash
   conda activate router
   ```
3. Install required packages:
   ```bash
   conda install -y <packages>
    ```
4. Export the environment to a YAML file:
   ```bash
   conda env export --no-builds > environment.yml
    ```

## Recreating the Environment

To set up the environment on a new machine or after cloning the repository, follow these steps:

1. Create the environment from the `environment.yml` file:
   ```bash
   conda env create -f environment.yml
   ```
2. Activate the environment:
   ```bash
   conda activate router
   ```
3. Optional: Update the environment if `environment.yml` has changed:
   ```bash
   conda env update -f environment.yml --prune
   ```