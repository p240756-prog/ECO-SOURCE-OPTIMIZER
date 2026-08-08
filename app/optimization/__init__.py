from app.optimization.dispatch import  DispatchPlanner
from app.optimization.constraints import ConstraintEvaluator

def __init__(self) -> None:
    self.constraint_evaluator = ConstraintEvaluator()
    self.dispatch_planner = DispatchPlanner()