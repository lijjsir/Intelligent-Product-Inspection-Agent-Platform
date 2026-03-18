from worker.celery_app import celery_app
from agent.graph.inspection_graph import InspectionGraph


@celery_app.task
def run_inspection(task_payload: dict) -> dict:
    graph = InspectionGraph()
    return graph.state
