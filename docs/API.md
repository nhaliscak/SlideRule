# Using SlideRule from other programs

Every function of SlideRule is reachable over HTTP, so scripts, spreadsheets, MATLAB or a local web app can run calculations. Runnable clients are in [`examples/03_http_api.py`](../examples/03_http_api.py) (Python standard library only) and [`examples/03_http_api.sh`](../examples/03_http_api.sh) (curl). The routes and their schemas are at `/api/docs` while a server runs; from Python, the same functions are in `sliderule.api` ([`examples/02_python_api.py`](../examples/02_python_api.py)).

**Use SlideRule from other programs.** `sliderule app --api` also starts the API on a known port (default 8765, `--api-port`), for scripts, spreadsheets, MATLAB or a local web app to call while the window is open (it stops when the window closes; `sliderule serve --no-browser` runs a server without a window, with the same Host and Origin protection but no token). Every function is reachable through one endpoint, `POST /api/rpc` with `{"method": ..., "params": ...}`; the other routes and their schemas are at `/api/docs`.

```bash
sliderule app --api --api-token "$(openssl rand -hex 16)"      # choose a token and keep it; the app never prints it
curl -X POST http://127.0.0.1:8765/api/rpc -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"method": "solve", "params": {"calc_id": "civil.column.euler_buckling", "inputs": {"E": "200 GPa", "I": "8.0e-6 m^4", "L": "3 m", "K": "1"}, "solve_for": ["Pcr"]}}'
```

The API server answers only on 127.0.0.1, only to the host names `localhost`, `127.0.0.1` and `[::1]` (so a web page cannot reach it by DNS rebinding), and refuses requests that a web page on another site makes (an `Origin` header) unless you list that origin with `--api-origin http://localhost:3000`. `--api-token` (or `$SLIDERULE_API_TOKEN`) requires a bearer token on every request except the API description; without one any program on the computer can use it, and the app says so when it starts. It serves only the API, never the web page, and it is not meant for a network: there is no encryption or user accounts. The API can write your equation and list files, so treat the token like a password.

`sliderule serve` has the same Host and Origin protection (no token, because the web page itself would have to send it): a web page on another site cannot make your browser drive the local server. `sliderule serve --host 0.0.0.0` makes it reachable from other computers, and then warns: there is no login or encryption, so use it only on a network you trust.
