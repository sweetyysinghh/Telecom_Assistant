import os

# Expose top-level project packages (config, ui, agents, orchestration, utils, data)
# by adding the project root to this package's __path__ so imports like
# "telecom_assistant.config.config" resolve to the top-level "config" package.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure __path__ is treated as a list (important for namespace package compatibility)
if "__path__" in locals():
    if not isinstance(__path__, list):
        __path__ = list(__path__)
    
    if project_root not in __path__:
        __path__.append(project_root)
