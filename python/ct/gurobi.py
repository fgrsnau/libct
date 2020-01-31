import gurobipy
from gurobipy import GRB
from collections import namedtuple

from . import libct as lib
from .primals import Primals


class GurobiBase:

    def __init__(self, model, ilp_mode=True):
        self.model = model
        self.gurobi = None
        self.ilp_mode = ilp_mode

    def _add_gurobi_variable(self, obj=0.0, disable_ub=False):
        """Adds a single Gurobi variable.

        State of `ilp_mode` determines if the variable is continuous or binary.
        """
        kwargs = {'lb': 0.0,
                  'ub': 1.0,
                  'obj': obj,
                  'vtype': GRB.BINARY if self.ilp_mode else GRB.CONTINUOUS}
        if disable_ub:
            del kwargs['ub']
        return self.gurobi.addVar(**kwargs)

    def construct(self):
        raise NotImplementedError()

    def update_upper_bound(self, tracker):
        ub = tracker.evaluate_primal()
        self.gurobi.Params.CutOff = ub

    def run(self):
        if self.gurobi is None:
            self.construct()
        self.gurobi.setParam('Method', 3)
        self.gurobi.setParam('Threads', 1)
        self.gurobi.optimize()

    def get_primals(self):
        raise NotImplementedError()


class GurobiStandardModel(GurobiBase):

    def construct(self):
        self.gurobi = gurobipy.Model()
        self._detections = {}
        self._transitions = {}
        self._divisions = {}

        incoming = {}
        outgoing = {}

        for t in range(self.model.no_timesteps()):
            for d in range(self.model.no_detections(t)):
                c_det, c_app, c_dis = self.model._detections[t, d]
                self._detections[t, d] = self._add_gurobi_variable(c_det)
                incoming[t, d] = [self._add_gurobi_variable(c_app)]
                outgoing[t, d] = [self._add_gurobi_variable(c_dis)]

        for k, v in self.model._transitions.items():
            timestep, index_from, index_to = k
            slot_left, slot_right, cost = v

            v = self._add_gurobi_variable(cost)
            self._transitions[k] = v
            outgoing[timestep, index_from].append(v)
            incoming[timestep+1, index_to].append(v)

        for k, v in self.model._divisions.items():
            timestep, index_from, index_to_1, index_to_2 = k
            slot_left, slot_right_1, slot_right_2, cost = v

            v = self._add_gurobi_variable(cost)
            self._divisions[k] = v
            outgoing[timestep, index_from].append(v)
            incoming[timestep+1, index_to_1].append(v)
            incoming[timestep+1, index_to_2].append(v)

        for t in range(self.model.no_timesteps()):
            for d in range(self.model.no_detections(t)):
                var_det = self._detections[t, d]

                self.gurobi.addConstr(sum(incoming[t, d]) == var_det)
                self.gurobi.addConstr(sum(outgoing[t, d]) == var_det)

        for t in range(self.model.no_timesteps()):
            for c in range(self.model.no_conflicts(t)):
                variables = [self._detections[t, d] for d in self.model._conflicts[t, c]]
                self.gurobi.addConstr(sum(variables) <= 1)

    def get_primals(self):
        primals = Primals(self.model)
        for k, v in self._detections.items():
            if v.X > .9:
                primals.detection(*k, True)
        for k, v in self._transitions.items():
            if v.X > .9:
                primals.transition(*k, True)
        for k, v in self._divisions.items():
            if v.X > .9:
                primals.division(*k, True)
        assert primals.check_consistency()
        return primals


class GurobiDecomposedModel(GurobiBase):

    DetectionVariables = namedtuple('DetectionVariables', 'incoming outgoing detection detection_slack')

    def __init__(self, model, tracker, ilp_mode=True):
        super().__init__(model, ilp_mode)
        self.tracker = tracker

    def _add_gurobi_variable(self, obj=0.0):
        """Adds a single Gurobi variable.

        State of `ilp_mode` determines if the variable is continuous or binary.

        WARNING: This function will not set an upper bound for the variable, as
        the reduced costs might be calculated incorrectly. (Those implicit
        constraints are not taken into account and they don't create dual
        variables, see <https://groups.google.com/forum/#!topic/gurobi/GCJxRiHyb34>.)
        """
        return super()._add_gurobi_variable(obj, disable_ub=True)

    def _add_detection(self, timestep, detection):
        """Adds a single cell detection to the Gurobi problem.

        This method will create variables/coefficients/constraints for the
        detection and all incoming/outgoing slots.
        """
        graph = lib.tracker_get_graph(self.tracker.tracker)
        factor = lib.graph_get_detection(graph, timestep, detection)

        v_incoming = []
        for i in range(self.model.no_incoming_edges(timestep, detection)):
            v = self._add_gurobi_variable(lib.detection_get_incoming_cost(factor, i))
            v.VarName = 'incoming_{}_{}_{}'.format(timestep, detection, i)
            v_incoming.append(v)
        v = self._add_gurobi_variable(lib.detection_get_appearance_cost(factor))
        v.VarName = 'appearance_{}_{}'.format(timestep, detection)
        v_incoming.append(v)

        v_outgoing = []
        for i in range(self.model.no_outgoing_edges(timestep, detection)):
            v = self._add_gurobi_variable(lib.detection_get_outgoing_cost(factor, i))
            v.VarName = 'outgoing_{}_{}_{}'.format(timestep, detection, i)
            v_outgoing.append(v)
        v = self._add_gurobi_variable(lib.detection_get_disappearance_cost(factor))
        v.VarName = 'disappearance_{}_{}'.format(timestep, detection)
        v_outgoing.append(v)

        v = self._add_gurobi_variable(lib.detection_get_detection_cost(factor))
        v.VarName = 'detection_{}_{}'.format(timestep, detection)
        self.gurobi.addConstr(sum(v_incoming) == v)
        self.gurobi.addConstr(sum(v_outgoing) == v)

        # We would like to insert the constraint `v <= 1`, but the LP is then
        # not in standard form. Internally, Gurobi seems to create slack
        # variables, because the reduced costs for our own variables are
        # incorrect. Unfortunately, there is no way to access these slack
        # variables. The documentation of `addVar` doesn't provide any
        # insights.
        #
        # The documentation of `addRange` is more informative. It will create a
        # slack variable and we see it when calling `model.getVars()` AFTER
        # `model.update()`. So it is not straight forward to get our hands at
        # the variable.
        #
        # To get around all this, we create our own slack variable here. :)
        v_slack = self._add_gurobi_variable()
        v_slack.VarName = 'slack_{}_{}'.format(timestep, detection)
        self.gurobi.addConstr(v + v_slack == 1)

        return self.DetectionVariables(incoming=v_incoming, outgoing=v_outgoing,
                                       detection=v, detection_slack=v_slack)

    def _add_conflict(self, timestep, conflict):
        """Adds a single conflict factor to the Gurobi problem.

        This method will create variables/coefficients/constraints for the
        conflict factor.
        """
        graph = lib.tracker_get_graph(self.tracker.tracker)
        factor = lib.graph_get_conflict(graph, timestep, conflict)
        detections = self.model._conflicts[timestep, conflict]

        v_conflict = []
        for detection in range(len(detections)):
            v = self._add_gurobi_variable(lib.conflict_get_cost(factor, detection))
            v.VarName = 'conflict_{}_{}_{}'.format(timestep, conflict, detection)
            v_conflict.append(v)
        v = self._add_gurobi_variable()
        v.VarName = 'conflict_{}_{}_off'.format(timestep, conflict)
        v_conflict.append(v)
        self.gurobi.addConstr(sum(v_conflict) == 1)

        return v_conflict

    def construct(self, timesteps=None):
        """Constructs a Gurobi LP/ILP problem.

        The argument `ilp_mode` determines if variables are binary or
        continuous (switches between ILP and LP).

        It is important that the `tracker` was constructed from the same
        underlying `model`. Costs are read off the `tracker` instance, so an
        intermediate reparametrization can be used as input.

        By using `timesteps` you can limit the constructed models to contain
        only a subset of all timesteps. By default (or by passing None) the
        full model is built.
        """
        self.gurobi = gurobipy.Model()
        self._detections = {}
        self._conflicts = {}
        self._timesteps = timesteps

        if timesteps is None:
            timesteps = [i for i in range(self.model.no_timesteps())]

        # Add all factors to ILP.
        for t in timesteps:
            for d in range(self.model.no_detections(t)):
                self._detections[t, d] = self._add_detection(t, d)

            for c in range(self.model.no_conflicts(t)):
                self._conflicts[t, c] = self._add_conflict(t, c)

        # Create constraints for conflict sets.
        for t in timesteps:
            for c in range(self.model.no_conflicts(t)):
                detection_indices = self.model._conflicts[t, c]
                v_conflicts = self._conflicts[t, c]
                v_detections = [self._detections[t, d].detection for d in detection_indices]

                for v_conflict, v_detection in zip(v_conflicts, v_detections):
                    self.gurobi.addConstr(v_conflict == v_detection)

        # Create constraints between the two timesteps (transitions).
        for k, v in self.model._transitions.items():
            t_left, detection_left, detection_right = k
            slot_left, slot_right, _ = v
            t_right = t_left + 1

            if timesteps is not None:
                if t_left not in timesteps or t_right not in timesteps:
                    continue

            v_left = self._detections[t_left, detection_left].outgoing[slot_left]
            v_right = self._detections[t_right, detection_right].incoming[slot_right]
            self.gurobi.addConstr(v_left == v_right)

        # Create constraints between the two timesteps (divisions).
        for k, v in self.model._divisions.items():
            t_left, detection_left, detection_right_1, detection_right_2 = k
            slot_left, slot_right_1, slot_right_2, _ = v
            t_right = t_left + 1

            if timesteps is not None:
                if t_left not in timesteps or t_right not in timesteps:
                    continue

            v_left = self._detections[t_left, detection_left].outgoing[slot_left]
            v_right_1 = self._detections[t_right, detection_right_1].incoming[slot_right_1]
            v_right_2 = self._detections[t_right, detection_right_2].incoming[slot_right_2]
            self.gurobi.addConstr(v_left == v_right_1)
            self.gurobi.addConstr(v_left == v_right_2)

    def get_primals(self):
        primals = Primals(self.model)

        for k, v in self._detections.items():
            if v.detection.X > .9:
                primals.detection(*k, True)

        for k, v in self.model._transitions.items():
            timestep, detection_left, detection_right = k
            slot_left, slot_right, _ = v
            v_left = self._detections[timestep, detection_left].outgoing[slot_left]
            v_right = self._detections[timestep+1, detection_right].incoming[slot_right]
            if v_left.X > .9 or v_right.X > .9:
                primals.transition(*k, True)

        for k, v in self.model._divisions.items():
            timestep, detection_left, detection_right_1, detection_right_2 = k
            slot_left, slot_right_1, slot_right_2, _ = v
            v_left = self._detections[timestep, detection_left].outgoing[slot_left]
            v_right_1 = self._detections[timestep+1, detection_right_1].incoming[slot_right_1]
            v_right_2 = self._detections[timestep+1, detection_right_2].incoming[slot_right_2]
            if v_left.X > .9 or v_right_1.X > .9 or v_right_2.X > .9:
                primals.division(*k, True)

        assert primals.check_consistency()
        return primals

    def update_upper_bound(self):
        super().update_upper_bound(self.tracker)

    def extract_reparametrization(self):
        """Reparametrizes the underlying `tracker` instance.

        The reparametrization is extracted from the Gurobi solver. Calling this
        function is only allowed when (1) `ilp_mode == False`, (2) `run()` got
        called, and (3) the full model was built.
        """
        assert self._timesteps is None
        graph = lib.tracker_get_graph(self.tracker.tracker)

        for t in range(self.model.no_timesteps()):
            for d in range(self.model.no_detections(t)):
                factor = lib.graph_get_detection(graph, t, d)
                variables = self._detections[t, d]

                on_cost = variables.detection.RC
                off_cost = variables.detection_slack.RC
                lib.detection_set_detection_cost(factor, on_cost - off_cost)

                assert len(variables.incoming) == self.model.no_incoming_edges(t, d) + 1
                for i in range(self.model.no_incoming_edges(t, d)):
                    lib.detection_set_incoming_cost(factor, i, variables.incoming[i].RC)
                lib.detection_set_appearance_cost(factor, variables.incoming[-1].RC)

                assert len(variables.outgoing) == self.model.no_outgoing_edges(t, d) + 1
                for i in range(self.model.no_outgoing_edges(t, d)):
                    lib.detection_set_outgoing_cost(factor, i, variables.outgoing[i].RC)
                lib.detection_set_disappearance_cost(factor, variables.outgoing[-1].RC)

            for c in range(self.model.no_conflicts(t)):
                factor = lib.graph_get_conflict(graph, t, c)
                variables = self._conflicts[t, c]
                detections = self.model._conflicts[t, c]

                assert len(detections) + 1 == len(variables)
                for i in range(len(detections)):
                    lib.conflict_set_cost(factor, i, variables[i].RC - variables[-1].RC)

        assert abs(self.gurobi.ObjBound - self.tracker.lower_bound()) < 1e-4


Gurobi = GurobiStandardModel
