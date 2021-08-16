from nnf.operators import implies
import macq.extract as extract
from typing import Dict, Union, Set
from nnf import Aux, Var, And, Or
from .model import Model
from ..trace import ObservationLists, ActionPair, Fluent # for typing
from ..observation import NoisyPartialDisorderedParallelObservation
from ..utils.pysat import to_wcnf

def __set_precond(r, act):
    return Var(str(r)[1:-1] + " is a precondition of " + act.details())

def __set_del(r, act):
    return Var(str(r)[1:-1] + " is deleted by " + act.details())

def __set_add(r, act):
    return Var(str(r)[1:-1] + " is added by " + act.details())

# for easier reference
pre = __set_precond
add = __set_add
delete = __set_del

WMAX = 1

class AMDN:
    def __new__(cls, obs_lists: ObservationLists, occ_threshold: int):
        """Creates a new Model object.

        Args:
            obs_lists (ObservationList):
                The state observations to extract the model from.
        Raises:
            IncompatibleObservationToken:
                Raised if the observations are not identity observation.
        """
        if obs_lists.type is not NoisyPartialDisorderedParallelObservation:
            raise extract.IncompatibleObservationToken(obs_lists.type, AMDN)

        solve = AMDN._solve_constraints(obs_lists, occ_threshold)
        print()
        #return Model(fluents, actions)

    @staticmethod
    def _or_refactor(maybe_lit: Union[Or, Var]):
        """Converts a "Var" fluent to an "Or" fluent.

        Args:
            maybe_lit (Union[Or, Var]):
                Fluent that is either type "Or" or "Var."

        Returns:
            A corresponding fluent of type "Or."
        """
        return Or([maybe_lit]) if isinstance(maybe_lit, Var) else maybe_lit

    @staticmethod
    def _extract_aux_set_weights(cnf_formula: And[Or[Var]], constraints: Dict, prob_disordered: float):
        aux_var = set()
        # find all the auxiliary variables
        for clause in cnf_formula.children:
            for var in clause.children:
                if isinstance(var.name, Aux):
                    aux_var.add(var.name)
            # set each original constraint to be a hard clause
            constraints[clause] = "HARD"
        # aux variables are the soft clauses that get the original weight
        for aux in aux_var:
            constraints[AMDN._or_refactor(Var(aux))] = prob_disordered * WMAX

    @staticmethod
    def _build_disorder_constraints(obs_lists: ObservationLists):
        disorder_constraints = {}
        # iterate through all traces
        for i in range(len(obs_lists.all_par_act_sets)):
            par_act_sets = obs_lists.all_par_act_sets[i]
            # iterate through all pairs of parallel action sets for this trace
            for j in range(len(par_act_sets) - 1):
                # for each pair, iterate through all possible action combinations
                for act_x in par_act_sets[j]:
                    for act_y in par_act_sets[j + 1]:
                        if act_x != act_y:
                            # calculate the probability of the actions being disordered (p)
                            p = obs_lists.probabilities[ActionPair({act_x, act_y})]
                            # for each action combination, iterate through all possible propositions
                            for r in obs_lists.propositions:
                                # enforce the following constraint if the actions are ordered with weight (1 - p) x wmax:
                                AMDN._extract_aux_set_weights(Or([
                                    And([pre(r, act_x), ~delete(r, act_x), delete(r, act_y)]),
                                    And([add(r, act_x), pre(r, act_y)]),
                                    And([add(r, act_x), delete(r, act_y)]),
                                    And([delete(r, act_x), add(r, act_y)])
                                    ]).to_CNF(), disorder_constraints, (1 - p))

                                # likewise, enforce the following constraint if the actions are disordered with weight p x wmax:
                                AMDN._extract_aux_set_weights(Or([
                                    And([pre(r, act_y), ~delete(r, act_y), delete(r, act_x)]),
                                    And([add(r, act_y), pre(r, act_x)]),
                                    And([add(r, act_y), delete(r, act_x)]),
                                    And([delete(r, act_y), add(r, act_x)])
                                ]).to_CNF(), disorder_constraints, p)
            return disorder_constraints

    @staticmethod
    def _build_hard_parallel_constraints(obs_lists: ObservationLists):
        hard_constraints = {}
        # create a list of all <a, r> tuples
        for act in obs_lists.actions:
            for r in obs_lists.probabilities:
                # for each action x proposition pair, enforce the two hard constraints with weight wmax
                hard_constraints[implies(add(r, act), ~pre(r, act))] = WMAX
                hard_constraints[implies(delete(r, act), pre(r, act))] = WMAX
        return hard_constraints

    @staticmethod
    def _build_soft_parallel_constraints(obs_lists: ObservationLists):
        soft_constraints = {}
        # iterate through all traces
        for i in range(len(obs_lists.all_par_act_sets)):
            par_act_sets = obs_lists.all_par_act_sets[i]
            # iterate through all parallel action sets for this trace
            for j in range(len(par_act_sets)):        
                # within each parallel action set, iterate through the same action set again to compare
                # each action to every other action in the set; setting constraints assuming actions are not disordered
                for act_x in par_act_sets[j]:
                    for act_x_prime in par_act_sets[j]:
                        if act_x != act_x_prime:
                            p = obs_lists.probabilities[ActionPair({act_x, act_x_prime})]
                            # iterate through all propositions
                            for r in obs_lists.propositions:
                                # equivalent: if r is in the add or delete list of an action in the set, that implies it 
                                # can't be in the add or delete list of any other action in the set
                                AMDN._extract_aux_set_weights(Or([And([~add(r, act_x_prime), ~delete(r, act_x_prime)]), And([~add(r, act_x), ~delete(r, act_x)])]).to_CNF(), soft_constraints, (1 - p))

        # iterate through all traces
        for i in range(len(obs_lists.all_par_act_sets)):
            par_act_sets = obs_lists.all_par_act_sets[i]
            # then, iterate through all pairs of parallel action sets for each trace
            for j in range(len(par_act_sets) - 1):
                # for each pair, compare every action in act_y to every action in act_x_prime; setting constraints assuming actions are disordered
                for act_y in par_act_sets[j + 1]:
                    for act_x_prime in par_act_sets[j]:
                        if act_y != act_x_prime:
                            p = obs_lists.probabilities[ActionPair({act_y, act_x_prime})]
                            # iterate through all propositions and similarly set the constraint
                            for r in obs_lists.propositions:
                                AMDN._extract_aux_set_weights(Or([And([~add(r, act_x_prime), ~delete(r, act_x_prime)]), And([~add(r, act_y), ~delete(r, act_y)])]).to_CNF(), soft_constraints, p)
        return soft_constraints

    @staticmethod
    def _build_parallel_constraints(obs_lists: ObservationLists):
        return {**AMDN._build_hard_parallel_constraints(obs_lists), **AMDN._build_soft_parallel_constraints(obs_lists)}

    @staticmethod
    def _calculate_all_r_occ(obs_lists: ObservationLists):
        # tracks occurrences of all propositions
        all_occ = 0
        for trace in obs_lists:
            for step in trace:
                all_occ += len([f for f in step.state if step.state[f]])
        return all_occ

    @staticmethod
    def _set_up_occurrences_dict(obs_lists: ObservationLists):
        # set up dict
        occurrences = {}           
        for a in obs_lists.actions:
            occurrences[a] = {}
            for r in obs_lists.propositions:
                occurrences[a][r] = 0
        return occurrences
    
    @staticmethod
    def _noise_constraints_6(obs_lists: ObservationLists, all_occ: int, occ_threshold: int):
        noise_constraints_6 = {}
        occurrences = AMDN._set_up_occurrences_dict(obs_lists)

        # iterate over ALL the plan traces, adding occurrences accordingly
        for i in range(len(obs_lists)):
            # iterate through each step in each trace, omitting the last step because the last action is None/we access the state in the next step
            for j in range(len(obs_lists[i]) - 1):
                true_prop = [f for f in obs_lists[i][j + 1].state if obs_lists[i][j + 1].state[f]]
                for r in true_prop:
                    # count the number of occurrences of each action and its following proposition
                    occurrences[obs_lists[i][j].action][r] += 1

        # iterate through actions
        for a in occurrences:
            # iterate through all propositions for this action
            for r in occurrences[a]:
                occ_r = occurrences[a][r]
                # if the # of occurrences is higher than the user-provided threshold:
                if occ_r > occ_threshold:
                    # set constraint 6 with the calculated weight
                    noise_constraints_6[AMDN._or_refactor(~delete(r, a))] = (occ_r / all_occ)
        return noise_constraints_6

    @staticmethod
    def _noise_constraints_7(obs_lists: ObservationLists, all_occ: int):
        noise_constraints_7 = {}
        # set up dict
        occurrences = {}           
        for r in obs_lists.propositions:
            occurrences[r] = 0

        for trace in obs_lists.states:
            for state in trace:
                true_prop = [r for r in state if state[r]]
                for r in true_prop:
                    occurrences[r] += 1

        # iterate through all traces
        for i in range(len(obs_lists.all_par_act_sets)):
            # get the next trace/states
            par_act_sets = obs_lists.all_par_act_sets[i]
            states = obs_lists.states[i]  
            # iterate through all parallel action sets within the trace
            for j in range(len(par_act_sets)):
                # examine the states before and after each parallel action set; set constraints accordinglly
                true_prop = [r for r in states[j + 1] if states[j + 1][r]]
                for r in true_prop:
                    if not states[j][r]:
                        noise_constraints_7[Or([add(r, act) for act in par_act_sets[j]])] = occurrences[r]/all_occ
   
        return noise_constraints_7

    @staticmethod
    def _noise_constraints_8(obs_lists, all_occ: int, occ_threshold: int):
        noise_constraints_8 = {}
        occurrences = AMDN._set_up_occurrences_dict(obs_lists)

        # iterate over ALL the plan traces, adding occurrences accordingly
        for i in range(len(obs_lists)):
            # iterate through each step in each trace
            for j in range(len(obs_lists[i])):
                true_prop = [f for f in obs_lists[i][j].state if obs_lists[i][j].state[f]]
                for r in true_prop:
                    # count the number of occurrences of each action and its previous proposition
                    occurrences[obs_lists[i][j].action][r] += 1

        # iterate through actions
        for a in occurrences:
            # iterate through all propositions for this action
            for r in occurrences[a]:
                occ_r = occurrences[a][r]
                # if the # of occurrences is higher than the user-provided threshold:
                if occ_r > occ_threshold:
                    # set constraint 8 with the calculated weight
                    noise_constraints_8[AMDN._or_refactor(pre(r, a))] = (occ_r / all_occ)
        return noise_constraints_8

    @staticmethod
    def _build_noise_constraints(obs_lists: ObservationLists, occ_threshold: int):
        # calculate all occurrences for use in weights
        all_occ = AMDN._calculate_all_r_occ(obs_lists)
        return{**AMDN._noise_constraints_6(obs_lists, all_occ, occ_threshold), **AMDN._noise_constraints_7(obs_lists, all_occ), **AMDN._noise_constraints_8(obs_lists, all_occ, occ_threshold)}

    @staticmethod
    def _set_all_constraints(obs_lists: ObservationLists, occ_threshold: int):
        return {**AMDN._build_disorder_constraints(obs_lists), **AMDN._build_parallel_constraints(obs_lists), **AMDN._build_noise_constraints(obs_lists, occ_threshold)}

    @staticmethod
    def _solve_constraints(obs_lists: ObservationLists, occ_threshold: int):
        constraints = AMDN._set_all_constraints(obs_lists, occ_threshold)
        # extract hard constraints
        hard_constraints = []
        for c, weight in constraints.items():
            if weight == "HARD":
                hard_constraints.append(c)
        
        for c in hard_constraints:
            del constraints[c]

        wcnf, decode = to_wcnf(And(constraints.keys()), list(constraints.values()))
        hard_wcnf, decode = to_wcnf(And(hard_constraints), None)
        wcnf.extend(hard_wcnf.soft)

        return wcnf, decode

    @staticmethod
    def _convert_to_model():
        # TODO:
        # convert the result to a Model
        pass