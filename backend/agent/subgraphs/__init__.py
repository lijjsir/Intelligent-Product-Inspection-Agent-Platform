__all__ = [
    "QualityAnalysisGraph",
    "VisionInspectionGraph",
    "LabDetectionGraph",
]


def __getattr__(name: str):
    if name == "QualityAnalysisGraph":
        from agent.subgraphs.quality_analysis import QualityAnalysisGraph

        return QualityAnalysisGraph
    if name == "VisionInspectionGraph":
        from agent.subgraphs.vision_inspection import VisionInspectionGraph

        return VisionInspectionGraph
    if name == "LabDetectionGraph":
        from agent.subgraphs.lab_detection import LabDetectionGraph

        return LabDetectionGraph
    raise AttributeError(name)
