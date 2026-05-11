from pytestarch import get_evaluable_architecture, DEFAULT_EXCLUSIONS, LayeredArchitecture
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
EXCLUSIONS = DEFAULT_EXCLUSIONS + ("cache", "test", "testcache", "testdata")

evaluable = get_evaluable_architecture(PROJECT_ROOT, PROJECT_ROOT / "src")

arch = (
    LayeredArchitecture() 
    .layer("domain") 
    .have_modules_with_names_matching("domain.*")
    .layer("application") 
    .have_modules_with_names_matching("application.*")
    .layer("infrastructure") 
    .have_modules_with_names_matching("infrastructure.*")
    .layer("presentation_cli") 
    .have_modules_with_names_matching("presentation_cli.*")
)