# Getting started

qontrol is a quantum optimal control package built on top of [dynamiqs](https://github.com/dynamiqs/dynamiqs). You can define your controls however you would in [dynamiqs](https://github.com/dynamiqs/dynamiqs), specifying only how to update the Hamiltonian at each optimizer step. [dynamiqs](https://github.com/dynamiqs/dynamiqs) also has strong native support for batching, which qontrol can leverage e.g. for randomizing over uncertain parameters.

## Installation

For now we support only installing directly from github
```bash
pip install git+https://github.com/dkweiss31/qontrol
```

Requires Python 3.10+


## Documentation

Documentation is available at [https://dkweiss.net/qontrol/](https://dkweiss.net/qontrol/)

## Quick example

Optimal control of a Kerr oscillator, with piece-wise constant drives on the I and Q quadratures and optimizing for a `Y` gate

```python
import dynamiqs as dq
import jax.numpy as jnp
import optax
import qontrol as ql

# hyper parameters
n = 5  # system size
K = -0.2 * 2.0 * jnp.pi  # Kerr nonlinearity
time = 40.0  # total simulation time
dt = 2.0  # control dt
seed_amplitude = 1e-3  # pulse seed amplitude
learning_rate = 1e-4  # learning rate for optimizer

# define model to optimize
a = dq.destroy(5)
H0 = 0.5 * K * dq.dag(a) @ dq.dag(a) @ a @ a
H1s = [a + dq.dag(a), 1j * (a - dq.dag(a))]


def H_pwc(drive_params):
    H = H0
    for idx, _H1 in enumerate(H1s):
        H += dq.pwc(tsave, drive_params[idx], _H1)
    return H

initial_states = [dq.basis(n, 0), dq.basis(n, 1)]
ntimes = int(time // dt) + 1
tsave = jnp.linspace(0, time, ntimes)
model = ql.sesolve_model(H_pwc, initial_states, tsave)

# define optimization
parameters = seed_amplitude * jnp.ones((len(H1s), ntimes - 1))
target_states = [-1j * dq.basis(n, 1), 1j * dq.basis(n, 0)]
cost = ql.cost.coherent_infidelity(target_states=target_states)
optimizer = optax.adam(learning_rate=0.0001)
options = ql.OptimizerOptions(save_states=False, progress_meter=None, verbose=False)

# run optimization
opt_params = ql.optimize(parameters, cost, model, optimizer=optimizer, options=options)
```
We initialize the `sesolve_model` which when called with `parameters` as input runs `sesolve`
and returns that result as well as the updated Hamiltonian. These are in turn passed to 
the cost functions, which tell the optimizer how to update `parameters`.

## Jump in

If this has piqued your interest, please see the example jupyter notebooks that demonstrate different use cases of `qontrol`, including optimizing qubit pulses to be robust to frequency variations [here](https://github.com/dkweiss31/qontrol/blob/main/docs/examples/qubit.ipynb) as well as performing time-optimal control and master-equation optimization [here](https://github.com/dkweiss31/qontrol/blob/main/docs/examples/Kerr_oscillator.ipynb). More examples coming soon!

## Citation

If you found this package useful in academic work, please cite

```bibtex
@unpublished{qontrol2024,
  title  = {qontrol: Quantum optimal control based on dynamiqs, diffrax and JAX},
  author = {Daniel K. Weiss},
  year   = {2024},
  url    = {https://github.com/dkweiss31/qontrol}
}
```

Also please consider starring the project on [github](https://github.com/dkweiss31/qontrol/)!
