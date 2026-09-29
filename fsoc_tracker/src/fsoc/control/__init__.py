"""
src/fsoc/control/__init__.py
============================
Gimbal control laws for FSOC optical tracking.
"""
from .pid_controller import PIDController

__all__ = ["PIDController"]
