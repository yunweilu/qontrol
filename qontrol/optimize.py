from __future__ import annotations

import time
from functools import partial

import jax
import jax.numpy as jnp
import optax
from dynamiqs.gradient import Gradient
from dynamiqs.solver import Solver, Tsit5
from jax import Array
from jaxtyping import ArrayLike
from optax import GradientTransformation, OptState, TransformInitFn

from .cost import Cost
from .model import Model
from .options import OptimizerOptions
from .utils.file_io import save_optimization


def optimize(
    parameters: ArrayLike | dict,
    costs: Cost,
    model: Model,
    *,
    optimizer: GradientTransformation = optax.adam(0.0001, b1=0.99, b2=0.99),  # noqa: B008
    solver: Solver = Tsit5(),  # noqa: B008
    gradient: Gradient | None = None,
    options: OptimizerOptions = OptimizerOptions(),  # noqa: B008
    filepath: str | None = None,
) -> Array | dict:
    r"""Perform gradient descent to optimize Hamiltonian parameters.

    This function takes as input `parameters` which parametrize a `model` when called
    performs time-dynamics simulations using dynamiqs. How to update `parameters` is encoded
    in the list of cost functions `costs` that contains e.g. infidelity contributions, pulse
    amplitude penalties, etc.

    Args:
        parameters _(dict or array-like)_: parameters to optimize
            over that are used to define the Hamiltonian and control times.
        costs _(list of Cost instances)_: List of cost functions used to perform the
            optimization.
        model _(Model)_: Model that is called at each iteration step.
        optimizer _(optax.GradientTransformation)_: optax optimizer to use
            for gradient descent. Defaults to the Adam optimizer.
        solver _(Solver)_: Solver passed to dynamiqs.
        gradient _()Gradient_: Gradient passed to dynamiqs.
        options _(OptimizerOptions)_: Options for grape optimization and dynamiqs
            integration.
        filepath _(str)_: Filepath of where to save optimization results.

    Returns:
        optimized parameters from the final timestep
    """  # noqa E501
    opt_state = optimizer.init(parameters)

    @partial(jax.jit, static_argnames=('_solver', '_gradient', '_options'))
    def step(
        _parameters: ArrayLike | dict,
        _costs: Cost,
        _model: Model,
        _opt_state: OptState,
        _solver: Solver,
        _gradient: Gradient,
        _options: OptimizerOptions,
    ) -> [Array, TransformInitFn, Array]:
        grads, _cost_values_terminate = jax.grad(loss, has_aux=True)(
            _parameters, _costs, _model, _solver, _gradient, _options
        )
        updates, _opt_state = optimizer.update(grads, _opt_state)
        _parameters = optax.apply_updates(_parameters, updates)
        return _parameters, _opt_state, _cost_values_terminate

    if options.verbose and filepath is not None:
        print(f'saving results to {filepath}')
    try:  # trick for catching keyboard interrupt
        for epoch in range(options.epochs):
            epoch_start_time = time.time()
            parameters, opt_state, cost_values_terminate = step(
                parameters, costs, model, opt_state, solver, gradient, options
            )
            cost_values, terminate = cost_values_terminate
            if options.verbose:
                elapsed_time = jnp.around(time.time() - epoch_start_time, decimals=3)
                message = f'epoch: {epoch}, elapsed_time: {elapsed_time} s; '
                message += f'costs = {cost_values}'
                print(message)
            if filepath is not None:
                save_optimization(
                    filepath,
                    {'cost_values': jnp.asarray(cost_values)},
                    parameters,
                    options.__dict__,
                    epoch,
                )
            # early termination
            if options.all_costs and all(terminate):
                print(
                    f'target cost reached for all cost functions after {epoch}'
                    f' epochs'
                )
                print(f'costs = {cost_values}')
                break
            if not options.all_costs and any(terminate):
                print(
                    f'target cost reached for one cost function after {epoch}'
                    f' epochs'
                )
                print(f'costs = {cost_values}')
                break
            if epoch == options.epochs - 1:
                print('reached maximum number of allowed epochs')
                print(f'costs = {cost_values}')
    except KeyboardInterrupt:
        print('terminated on keyboard interrupt')
    return parameters


def loss(
    parameters: Array | dict,
    costs: Cost,
    model: Model,
    solver: Solver,
    gradient: Gradient,
    options: OptimizerOptions,
) -> [float, Array]:
    result, H = model(parameters, solver, gradient, options)
    cost_values, terminate = zip(*costs(result, H))
    total_cost = jax.tree.reduce(jnp.add, cost_values)
    return jnp.log(jnp.sum(jnp.asarray(total_cost))), (cost_values, terminate)