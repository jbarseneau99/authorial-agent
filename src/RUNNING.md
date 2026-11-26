# Integrated prototype
Python 3.10+ and openpyxl are required. Run `python -m unittest discover`.

Configure AGENT_API_KEY, AGENT_MODEL and AGENT_ENDPOINT locally (HTTPS Chat Completions-compatible endpoint). Optional role-specific models: AGENT_CONSTRUCTION_MODEL, AGENT_EXPRESSION_MODEL, AGENT_CHECKING_MODEL.

Run `python run_agent.py --live --intent 'Explain episodic envelopes in agent memory' --support 'episodic memory temporal context' --challenge 'episodic memory limitations temporal context'`.

The report includes draft sentences, checking results, retrieval directions and execution state. The database persists the graph and checkpoints. Omitting both queries disables external research. Queries are supplied by the operator, not generated automatically. Retrieved evidence remains unassessed; source independence and sufficiency are not enforced. The CLI does not approve or resume runs. No live provider test has been performed. Do not commit credentials or sensitive authorial memory. Model providers receive authorial context.
