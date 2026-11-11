#!/bin/sh
# SlideRule from the command line. Run it with:  sh examples/01_command_line.sh
# (needs `pip install .` first, so that the `sliderule` command exists)

# Find calculations by words, discipline or variable
sliderule list -s hydraulic | head -5
sliderule list buckling -d civil              # words in the name, within one discipline
sliderule list -d civil -v modulus | head -5  # calculations that contain a variable about a modulus

# What does one calculation need, and what does it say?
sliderule show civil.column.euler_buckling

# Solve it: Euler buckling load of a 3 m column
sliderule solve civil.column.euler_buckling E="200 GPa" I="8.0e-6 m^4" L="3 m" K=1 --for Pcr --unit Pcr=kN

# ... and with the worked solution (units and conversions at every step)
sliderule solve civil.column.euler_buckling E="200 GPa" I="8.0e-6 m^4" L="3 m" K=1 --for Pcr --unit Pcr=kN --steps numeric

# Solve for a different unknown: the second moment of area that carries 2000 kN
sliderule solve civil.column.euler_buckling Pcr="2000 kN" E="200 GPa" L="3 m" K=1 --for I --unit I=mm^4

# Units
sliderule convert 120 km/h m/s
sliderule convert 10 ppg kg/m^3

# Property data with its source and basis (add --at for a temperature-dependent property)
sliderule data list
sliderule data value materials-typical aluminium-6061-t6 youngs_modulus --unit GPa
sliderule data value fluids-coolprop water-liquid dynamic_viscosity --at 20 --at-unit degC --unit "mPa*s"
sliderule data value nist-cryo 304-stainless thermal_conductivity --at 77 --at-unit K
