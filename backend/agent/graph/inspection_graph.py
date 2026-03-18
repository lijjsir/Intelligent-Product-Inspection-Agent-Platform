from agent.graph.state import InspectionState


class InspectionGraph:
    def __init__(self):
        self.state = InspectionState()

    async def run(self, state: InspectionState) -> InspectionState:
        # Placeholder for LangGraph orchestration
        return state
