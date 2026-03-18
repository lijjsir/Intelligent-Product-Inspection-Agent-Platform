from agent.stability.scorer import score


async def analyze(dimensions: dict) -> dict:
    return score(dimensions)
