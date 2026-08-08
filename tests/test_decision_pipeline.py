from app.decision.engine import DecisionEngine
from app.statebuilder.decision_context import DecisionContext


def make_context(**overrides):
    context = {
        # complete valid baseline context
    }

    context.update(overrides)

    return DecisionContext(**context)