.. _faq:

**************************
Frequently Asked Questions
**************************

General
=======

Q: What is the Hybrid Symbolic-Numeric Framework in ANDES?

A: It is a modeling and simulation framework that uses symbolic computation for descriptive
modeling and code generation for fast numerical simulation.
The goal of the framework is to reduce the programming efforts associated with implementing
complex models and automate the research workflow of modeling, simulation, and documentation.

The framework reduces the modeling efforts from two aspects:
(1) allowing modeling by typing in equations, and (2) allowing modeling using modularized
control blocks and discontinuous components.
One only needs to describe the model using equations and blocks without having to write the
numerical code to implement the computation.
The framework automatically generate symbolic expressions, computes partial derivatives,
and generates vectorized numerical code.

Modeling
========

Admittance matrix
-----------------

Q: Where to find the line admittance matrix?

A: ANDES does not build line admittance matrix for computing
line power injections. Instead, line power injections are
computed as vectors on the two line terminal. This approach
generalizes line as a power injection model.

Q: Without admittance matrix, how to switch out lines?

A: Lines can be switched out and in by using ``Toggler``.
See the example in ``cases/kundur/kundur_full.xlsx``.
One does not need to manually trigger a Jacobian matrix rebuild
because ``Toggler`` automatically triggers it using the new
connectivity status.

Reference of the existing model
-----------------
Q: Is there any further reference of the existing model?
S: Most of them can be searched online, such as ESIG and PowerWorld.
