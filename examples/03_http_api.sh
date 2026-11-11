#!/bin/sh
# The same call from curl. Start a server first:  sliderule serve --no-browser     (or: sliderule app --api --api-token mysecret)
# With a token, add:  -H "Authorization: Bearer mysecret"

curl -s -X POST http://127.0.0.1:8765/api/rpc -H "Content-Type: application/json" -d '{
  "method": "solve",
  "params": {"calc_id": "civil.column.euler_buckling",
             "inputs": {"E": "200 GPa", "I": "8.0e-6 m^4", "L": "3 m", "K": "1"},
             "solve_for": ["Pcr"], "output_units": {"Pcr": "kN"}}}'
echo
curl -s "http://127.0.0.1:8765/api/convert?value=120&from=km/h&to=m/s"
echo
