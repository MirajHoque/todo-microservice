"""Agent service — the AI assistant for the todo app.

Layout (compare with services/api/internal/ in Go):

    __main__.py   start the server:  python -m agent
    main.py       create the FastAPI app, wire middleware + routes
    config.py     settings from environment / .env
    log.py        JSON logging + per-request context (request_id)
    routes/       HTTP handlers, one module per area
"""
