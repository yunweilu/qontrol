import equinox as eqx
from jax import Array, vmap
import jax
import jax.numpy as jnp
from jaxtyping import ArrayLike

from dynamiqs._utils import cdtype
from dynamiqs import TimeArray
from dynamiqs.time_array import SummedTimeArray
from dynamiqs.result import Result
from .fidelity import infidelity_incoherent, infidelity_coherent


class Cost(eqx.Module):
    cost_multiplier: float = 1.0

    def evaluate(self, result: Result, H: TimeArray):
        raise NotImplementedError


class IncoherentInfidelity(Cost):
    target_states: Array

    def __init__(self, target_states: ArrayLike, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_states = jnp.asarray(target_states, dtype=cdtype())

    def evaluate(self, result: Result, H: TimeArray):
        final_states = result.states[..., -1, :, :]
        return self.cost_multiplier * infidelity_incoherent(
            final_states, self.target_states, average=True
        )


class CoherentInfidelity(Cost):
    target_states: Array

    def __init__(self, target_states: ArrayLike, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_states = jnp.asarray(target_states, dtype=cdtype())

    def evaluate(self, result: Result, H: TimeArray):
        final_states = result.states[..., -1, :, :]
        infid = infidelity_coherent(final_states, self.target_states)
        return self.cost_multiplier * jnp.average(infid)


class ForbiddenStates(Cost):
    """
    forbidden_states should be a list of lists of forbidden states for each
    respective initial state. The resulting self.forbidden_states has
    dimensions sbid where b is the batch dimension over multiple forbidden states
    """
    forbidden_states: Array

    def __init__(self, forbidden_states: list[Array], *args, **kwargs):
        super().__init__(*args, **kwargs)
        state_shape = forbidden_states[0][0].shape
        num_states = len(forbidden_states)
        num_forbid_per_state = jnp.asarray([
            len(forbid_list) for forbid_list in forbidden_states
        ])
        max_num_forbid = jnp.max(num_forbid_per_state)
        arr_indices = [(state_idx, forbid_idx)
                       for state_idx in range(num_states)
                       for forbid_idx in range(max_num_forbid)]
        forbid_array = jnp.zeros((num_states, max_num_forbid, *state_shape), dtype=cdtype())
        for state_idx, forbid_idx in arr_indices:
            forbidden_state = forbidden_states[state_idx][forbid_idx]
            forbid_array = forbid_array.at[state_idx, forbid_idx].set(forbidden_state)
        self.forbidden_states = forbid_array

    def evaluate(self, result: Result, H: TimeArray):
        # states has dims ...stid, where s is initial_states batching, t has
        # dimension of tsave and id are the state dimensions.
        forbidden_ovlps = jnp.einsum(
            "...stid,sfid->...stf", result.states, self.forbidden_states
        )
        forbidden_pops = jnp.real(jnp.mean(forbidden_ovlps * jnp.conj(forbidden_ovlps)))
        return self.cost_multiplier * forbidden_pops


class Control(Cost):

    def __init__(self, *args, **kwargs):
        # TODO allow weighting for different Hamiltonian controls
        super().__init__(*args, **kwargs)

    def evaluate_controls(self, result: Result, H: TimeArray, func):

        def _evaluate_at_tsave(_H):
            if hasattr(_H, "prefactor"):
                return jnp.sum(func(vmap(_H.prefactor)(result.tsave)))
            else:
                return jnp.array(0.0)

        if isinstance(H, SummedTimeArray):
            control_val = 0.0
            # ugly for loop, having trouble with vmap or scan because only PWCTimeArray
            # and ModulatedTimeArray have attributes prefactor
            for timearray in H.timearrays:
                control_val += jnp.sum(vmap(_evaluate_at_tsave)(timearray))
        else:
            control_val = _evaluate_at_tsave(H)

        return self.cost_multiplier * control_val


class ControlNorm(Control):

    def evaluate(self, result: Result, H: TimeArray):
        return self.evaluate_controls(result, H, lambda x: x ** 2)


class ControlArea(Control):

    def evaluate(self, result: Result, H: TimeArray):
        return self.evaluate_controls(result, H, lambda x: x)


class CustumCost(Control):
    cost_fun: callable

    def __init__(self, cost_fun: callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cost_fun = jax.tree_util.Partial(cost_fun)

    def evaluate(self, result: Result, H: TimeArray):
        return self.cost_fun(result, H)