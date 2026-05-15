import re
from archunitpython import project_files, metrics, assert_passes, project_slices

def test_no_circular_dependencies():
    rule = project_files("src/").in_folder("src/**").should().have_no_cycles()
    assert_passes(rule)

def test_no_large_files():
    rule = metrics("src/").count().lines_of_code().should_be_below(1000)
    assert_passes(rule)

def test_adhere_to_diagram():
    diagram = """
@startuml
  component [domain]
  component [application]
  component [infrastructure]
  component [presentation_cli]
  [application] --> [domain]
  [infrastructure] --> [application]
  [infrastructure] --> [domain]
  [presentation_cli] --> [infrastructure]
  [presentation_cli] --> [application]
  [presentation_cli] --> [domain]
@enduml"""

    rule = (
        project_slices("src/")
        .defined_by_regex(re.compile(r"/src/(domain|application|infrastructure|presentation_cli)(?:/|$)"))
        .should()
        .adhere_to_diagram(diagram)
    )
    assert_passes(rule)


# TODO:  Need to understand what is a reasonable LCOM metric for this project.
# def test_high_cohesion():
#     # LCOM metric (lack of cohesion of methods), low = high cohesion
#     rule = metrics("src/").lcom().lcom96b().should_be_below(0.3)
#     assert_passes(rule)
