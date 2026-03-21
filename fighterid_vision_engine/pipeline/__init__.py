__all__ = ["StrikeDetector", "VideoRecorder", "VisionMotorV1"]


def __getattr__(name):
    if name == "StrikeDetector":
        from fighterid_vision_engine.pipeline.strike import StrikeDetector
        return StrikeDetector
    if name == "VideoRecorder":
        from fighterid_vision_engine.pipeline.recorder import VideoRecorder
        return VideoRecorder
    if name == "VisionMotorV1":
        from fighterid_vision_engine.pipeline.engine import VisionMotorV1
        return VisionMotorV1
    raise AttributeError(f"module 'fighterid_vision_engine.pipeline' has no attribute {name!r}")
