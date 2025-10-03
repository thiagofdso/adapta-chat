# Gemini Development Guidelines

This document outlines the standard operating procedures for developing and maintaining this project. Please adhere to these guidelines in all future interactions.

## 1. Dependency Management with Poetry

This project uses [Poetry](https://python-poetry.org/) to manage dependencies and virtual environments.

### Running Scripts

Always execute Python scripts or applications within the project's managed environment using `poetry run`.

**Examples:**
```sh
# Run a Python script
poetry run python your_script.py

# Run the Streamlit application
poetry run streamlit run src/app_chat.py
```

### Updating Dependencies

When you add or modify dependencies in the `pyproject.toml` file, follow this two-step process:

1.  **Update the Lock File:** This resolves and locks the new dependency versions.
    ```sh
    poetry lock
    ```

2.  **Install Dependencies:** This installs the packages specified in the updated `poetry.lock` file.
    ```sh
    poetry install
    ```

## 2. Git Workflow

We follow a feature branch workflow to ensure the `master` branch always remains stable.

### Core Rule

**NEVER commit or develop directly on the `master` branch.**

### Development Process

1.  **Create a Feature Branch:** Before starting any new work (e.g., adding a feature, fixing a bug), create a new branch from the `master` branch.
    ```sh
    # Make sure you are on master and up-to-date
    git checkout master

    # Create and switch to your new branch
    git checkout -b <branch-name>
    ```

2.  **Develop:** Make all your changes and commits on your feature branch.

3.  **Merge to Master:** Once your work is complete and tested, merge the feature branch back into `master`.
    ```sh
    # Switch to the master branch
    git checkout master

    # Merge your feature branch
    git merge <branch-name>
    ```

4.  **Delete the Feature Branch:** After a successful merge, delete the local feature branch to keep the repository clean.
    ```sh
    git branch -d <branch-name>
    ```

### Branch Naming Conventions

Use the following prefixes and conventions for clear and consistent branch names:

-   **`feature/<description>`:** For adding new features (e.g., `feature/add-user-authentication`).
-   **`fix/<description>`:** For fixing bugs (e.g., `fix/resolve-import-error`).
-   **`chore/<description>`:** For maintenance tasks that don't add features or fix bugs (e.g., `chore/update-readme`, `chore/refactor-logger`).

**Guidelines:**
- Use lowercase letters.
- Separate words with hyphens (`-`).
- Keep the description short but descriptive.
