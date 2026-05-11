# TODO:  Disabled because pytestarch expects a subfolder, e.g. "fincol" under the main "src" folder.  Tests can be enabled when/if project is
#        reorganized according to that structure.

# import pytest
# from pytestarch import EvaluableArchitecture, LayeredArchitecture, get_evaluable_architecture, LayerRule

# @pytest.fixture(scope="session")
# def evaluable(pytestconfig: pytest.Config) -> EvaluableArchitecture:
#     project_root = pytestconfig.rootpath
#     src_path = project_root / "src"
#     return get_evaluable_architecture(str(src_path), "")

# @pytest.fixture(scope="session")
# def layered_architecture() -> LayeredArchitecture:
#     return (
#         LayeredArchitecture()
#         .layer("domain")
#         .containing_modules(["src.domain"])
#         .layer("application")
#         .containing_modules(["src.application"])
#         .layer("infrastructure")
#         .containing_modules(["src.infrastructure"])
#         .layer("presentation_cli")
#         .containing_modules(["src.presentation_cli"])
#     )


# def test_domain_cannot_reference_higher_layers(
#     evaluable: EvaluableArchitecture, layered_architecture: LayeredArchitecture
# ) -> None:
#     """
#     Domain layer must not reference higher layers.
#     """
#     rule = (
#         LayerRule()
#         .based_on(layered_architecture)
#         .layers_that()
#         .are_named("domain")
#         .should_not()
#         .access_layers_that()
#         .are_named(["application", "infrastructure"])
#     )

#     rule.assert_applies(evaluable)