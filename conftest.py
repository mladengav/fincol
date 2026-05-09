"""Pytest root marker: presence of this file makes the project root the rootdir
and adds it to ``sys.path`` so test modules under ``test/`` can import the
top-level modules (``fincol``, etc.) and packages such as ``infrastructure`` directly.
"""
