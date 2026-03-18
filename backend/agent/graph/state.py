from typing import TypedDict, List, Dict, Any


class InspectionState(TypedDict, total=False):
    task_id: str
    org_id: str
    image_urls: List[str]
    tool_results: List[Dict[str, Any]]
    conclusion: Dict[str, Any]
