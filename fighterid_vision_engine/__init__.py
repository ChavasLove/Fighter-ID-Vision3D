"""
FighterID Vision Engine — modular AI vision package
Estructura:
  config/    → settings desde .env
  camera/    → captura de video (CameraStream)
  detection/ → pose YOLO + tracker (PoseDetector, SimpleTracker)
  pipeline/  → detección de golpes + motor (StrikeDetector, VisionMotorV1)
  models/    → directorio para archivos .pt / .onnx

Entry point: python main.py --fight-id <uuid>
"""

__all__ = ["VisionMotorV1"]


def __getattr__(name):
    if name == "VisionMotorV1":
        from fighterid_vision_engine.pipeline.engine import VisionMotorV1
        return VisionMotorV1
    raise AttributeError(f"module 'fighterid_vision_engine' has no attribute {name!r}")
