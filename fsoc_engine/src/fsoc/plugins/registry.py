"""
Plugin Registry for NETRA Plugin Playground.
Thread-safe pending-swap registry for Vision, Tracking, and Control slots.
"""

from typing import Callable, Any, Optional
import time
import threading
import logging
import math

logger = logging.getLogger("fsoc.plugins.registry")

SLOTS = ["vision", "tracking", "control"]


class PluginRegistry:
    """
    Manages active plugin functions, pending swaps from GUI thread,
    slot persistent states, timings, and crash fallback.
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()
        
        # Increment version whenever a plugin swap happens so engines can clear their states
        self.version = 0
        
        # Engine reference for default adapters
        self._engine: Any = None
        
        # Functions registered
        self._defaults: dict[str, Callable] = {}
        self._active: dict[str, Callable] = {}
        self._pending: dict[str, Optional[tuple[Callable, dict, str]]] = {
            slot: None for slot in SLOTS
        }
        
        # Metadata
        self._labels: dict[str, str] = {slot: "NETRA Default" for slot in SLOTS}
        self._is_custom: dict[str, bool] = {slot: False for slot in SLOTS}
        self._params: dict[str, dict] = {slot: {} for slot in SLOTS}
        self._timing: dict[str, float] = {slot: 0.0 for slot in SLOTS}
        self._error_counts: dict[str, int] = {slot: 0 for slot in SLOTS}
        self._call_counts: dict[str, int] = {slot: 0 for slot in SLOTS}
        self._last_error: dict[str, Optional[str]] = {slot: None for slot in SLOTS}

    def register_defaults(self, engine: Any, default_vision: Callable, default_tracking: Callable, default_control: Callable) -> None:
        """Register default adapter functions bound to engine instance.

        Called once per engine construction. Active *custom* plugins are preserved
        so that rebuilding the engine (config change, reset) does not silently
        un-hook a researcher's plugin; only un-hooked slots are re-initialised.
        """
        self._engine = engine
        self._defaults["vision"] = default_vision
        self._defaults["tracking"] = default_tracking
        self._defaults["control"] = default_control

        first = not hasattr(self, "_initialised") or not self._initialised
        self._initialised = True
        for slot in SLOTS:
            if first or not self._is_custom.get(slot, False):
                self._active[slot] = self._defaults[slot]
                self._labels[slot] = "NETRA Default"
                self._is_custom[slot] = False
                self._params[slot] = {}
                self._error_counts[slot] = 0
                self._call_counts[slot] = 0
                self._last_error[slot] = None
            # A custom slot keeps its function/label/params; only pending swaps
            # for non-custom slots are cleared (fresh defaults, nothing to apply).
            if not self._is_custom.get(slot, False):
                self._pending[slot] = None

    def request(self, slot: str, func: Callable, params: dict, label: str) -> None:
        """
        GUI Thread calls this to request a plugin swap.
        The swap will be safely applied at the frame boundary by apply_pending().
        """
        if slot not in SLOTS:
            raise ValueError(f"Unknown slot '{slot}'. Valid slots: {SLOTS}")
        with self._lock:
            self._pending[slot] = (func, params, label)

    def apply_pending(self) -> None:
        """
        Engine Thread calls this at the very top of engine.step().
        Atomically applies any pending plugin swaps.
        """
        with self._lock:
            swapped = False
            for slot in SLOTS:
                pending = self._pending[slot]
                if pending is not None:
                    func, params, label = pending
                    self._pending[slot] = None
                    self._active[slot] = func
                    self._params[slot] = params
                    self._labels[slot] = label
                    self._error_counts[slot] = 0
                    self._call_counts[slot] = 0
                    self._last_error[slot] = None
                    is_def = (func == self._defaults.get(slot))
                    self._is_custom[slot] = not is_def
                    swapped = True
                    logger.info(f"Applied plugin swap for [{slot}]: {label} (custom={not is_def})")
            if swapped:
                self.version += 1

    def call(self, slot: str, *args, **kwargs) -> Any:
        """
        Execute active plugin function for a slot with timing and fallback safety.
        """
        if slot not in SLOTS:
            raise ValueError(f"Unknown slot '{slot}'")

        func = self._active.get(slot) or self._defaults.get(slot)
        if func is None:
            raise RuntimeError(f"No plugin function registered for slot '{slot}'")

        params = self._params.get(slot, {})
        is_custom = self._is_custom[slot]

        # Pass _engine kwarg to default functions if needed
        if func == self._defaults.get(slot):
            kwargs["_engine"] = self._engine

        t0 = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            self._timing[slot] = dt_ms
            self._call_counts[slot] += 1
            
            # Validate output basic shape
            self._validate_result(slot, result)
            return result

        except Exception as e:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            self._timing[slot] = dt_ms
            err_msg = f"Error in plugin [{slot}] '{self._labels[slot]}': {e}"
            logger.error(err_msg, exc_info=True)
            self._error_counts[slot] += 1
            self._last_error[slot] = str(e)

            # If custom plugin failed, auto-fallback to default for this call
            if is_custom and self._defaults.get(slot):
                logger.warning(f"Auto-falling back to default adapter for [{slot}]")
                try:
                    fallback_func = self._defaults[slot]
                    return fallback_func(*args, _engine=self._engine, **kwargs)
                except Exception as fb_err:
                    logger.critical(f"Default fallback for [{slot}] failed: {fb_err}")
                    return self._safe_null_return(slot)
            return self._safe_null_return(slot)

    def _validate_result(self, slot: str, result: Any) -> None:
        """Sanity check plugin outputs to avoid corrupting downstream engine steps."""
        if slot == "vision":
            if result is None:
                return
            if not isinstance(result, dict) or "x" not in result or "y" not in result:
                raise ValueError("Vision plugin output must be dict with 'x', 'y' or None")
        elif slot == "tracking":
            if not isinstance(result, dict) or not {"x", "y", "vx", "vy"}.issubset(result.keys()):
                raise ValueError("Tracking plugin output must be dict with 'x', 'y', 'vx', 'vy'")
        elif slot == "control":
            if not isinstance(result, dict) or not {"pan_rate", "tilt_rate"}.issubset(result.keys()):
                raise ValueError("Control plugin output must be dict with 'pan_rate', 'tilt_rate'")

        # NaN/Inf guard
        if isinstance(result, dict):
            for key, val in result.items():
                if isinstance(val, (float, int)):
                    if math.isnan(val) or math.isinf(val):
                        result[key] = 0.0
                        logger.error(f"Plugin returned NaN/Inf for '{key}', replaced with 0.0")

    def _safe_null_return(self, slot: str) -> Any:
        if slot == "vision":
            return None
        elif slot == "tracking":
            return {"x": 320.0, "y": 240.0, "vx": 0.0, "vy": 0.0}
        elif slot == "control":
            return {"pan_rate": 0.0, "tilt_rate": 0.0}

    def reset_slot(self, slot: str) -> None:
        """Reset specified slot back to NETRA default."""
        if slot in SLOTS and slot in self._defaults:
            self.request(slot, self._defaults[slot], {}, "NETRA Default")

    def reset_all(self) -> None:
        """Reset all slots back to NETRA defaults."""
        for slot in SLOTS:
            self.reset_slot(slot)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                slot: {
                    "label": self._labels[slot],
                    "is_custom": self._is_custom[slot],
                    "calls": self._call_counts[slot],
                    "errors": self._error_counts[slot],
                    "last_error": self._last_error[slot],
                    "avg_timing_ms": self._timing[slot],
                    "params": self._params[slot]
                }
                for slot in SLOTS
            }

    def is_custom(self, slot: str) -> bool:
        return self._is_custom.get(slot, False)

    def any_custom(self) -> bool:
        return any(self._is_custom.values())

    def get_label(self, slot: str) -> str:
        return self._labels.get(slot, "NETRA Default")

    def get_timing(self, slot: str) -> float:
        return self._timing.get(slot, 0.0)

    def get_params(self, slot: str) -> dict:
        return self._params.setdefault(slot, {})

    def update_params(self, slot: str, params: dict) -> None:
        self._params[slot].update(params)

    def get_status(self, slot: str) -> dict:
        return {
            "label": self.get_label(slot),
            "is_custom": self.is_custom(slot),
            "timing_ms": self.get_timing(slot),
            "calls": self._call_counts.get(slot, 0),
            "errors": self._error_counts.get(slot, 0),
            "last_error": self._last_error.get(slot),
        }


# Global singleton instance used throughout application
registry = PluginRegistry()
